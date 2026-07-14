from datetime import datetime
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..models import InvestmentProduct, ProductValuationHistory, InvestmentAccount, MutualFundScheme, Transaction
from ..serializers import InvestmentProductSerializer, ProductValuationHistorySerializer
from apps.data.models import TLStockData


class ProductListView(generics.ListAPIView):
    serializer_class = InvestmentProductSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = InvestmentProduct.objects.select_related(
            'investment_account', 'investment_account__family_member'
        ).filter(
            investment_account__family_member__user=self.request.user
        )
        member_id = self.request.query_params.get('member_id')
        if member_id:
            qs = qs.filter(investment_account__family_member_id=member_id)
        account_id = self.request.query_params.get('account_id')
        if account_id:
            qs = qs.filter(investment_account_id=account_id)
        product_type = self.request.query_params.get('product_type')
        if product_type:
            qs = qs.filter(product_type=product_type)
        is_active = self.request.query_params.get('is_active', 'true')
        qs = qs.filter(is_active=(is_active.lower() == 'true'))
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        products = list(self.get_queryset())
        isins = [p.isin for p in products if p.isin]
        if isins:
            context['mf_schemes'] = {
                s.isin: s for s in MutualFundScheme.objects.filter(isin__in=isins)
            }
        equity_isins = [p.isin for p in products if p.isin and p.product_type == 'EQUITY']
        if equity_isins:
            context['equity_stocks'] = {
                s.isin: s for s in TLStockData.objects.filter(isin__in=equity_isins)
            }
        return context


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = InvestmentProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InvestmentProduct.objects.filter(
            investment_account__family_member__user=self.request.user
        )

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class ProductCreateView(generics.CreateAPIView):
    serializer_class = InvestmentProductSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        account_id = self.kwargs.get('account_pk') or self.request.data.get('investment_account')
        account = InvestmentAccount.objects.get(
            pk=account_id,
            family_member__user=self.request.user
        )
        product = serializer.save(investment_account=account)
        # Auto-compute value for FD/RD on creation
        from apps.investments.services.valuation_engine import compute_product_value
        compute_product_value(product)


class ProductValuationHistoryView(generics.ListCreateAPIView):
    serializer_class = ProductValuationHistorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        product_id = self.kwargs['pk']
        return ProductValuationHistory.objects.filter(
            product_id=product_id,
            product__investment_account__family_member__user=self.request.user,
        )

    def perform_create(self, serializer):
        product_id = self.kwargs['pk']
        product = InvestmentProduct.objects.get(
            pk=product_id,
            investment_account__family_member__user=self.request.user,
        )
        valuation = serializer.save(product=product)
        # Update product current value with the latest manual valuation
        product.current_value = valuation.value
        product.as_of_date = valuation.date
        product.save()


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_product_value(request, pk):
    try:
        product = InvestmentProduct.objects.get(
            pk=pk,
            investment_account__family_member__user=request.user,
        )
    except InvestmentProduct.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    new_value = request.data.get('value')
    if new_value is None:
        return Response({'error': 'value is required'}, status=status.HTTP_400_BAD_REQUEST)

    date = request.data.get('date') or timezone.now().date().isoformat()
    notes = request.data.get('notes', '')

    ProductValuationHistory.objects.update_or_create(
        product=product,
        date=date,
        defaults={'value': new_value, 'source': 'MANUAL', 'notes': notes},
    )
    product.current_value = new_value
    product.as_of_date = date
    product.save()

    return Response(InvestmentProductSerializer(product).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_product_category(request, pk):
    """Manually set (or clear) a holding's fund category — wins over MFAPI/parse-time values."""
    try:
        product = InvestmentProduct.objects.get(
            pk=pk,
            investment_account__family_member__user=request.user,
        )
    except InvestmentProduct.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    category = (request.data.get('category') or '').strip()
    if not category:
        return Response({'error': 'category is required'}, status=status.HTTP_400_BAD_REQUEST)

    product.extra_data = {**(product.extra_data or {}), 'category': category, 'category_source': 'manual'}
    product.save(update_fields=['extra_data'])

    return Response(InvestmentProductSerializer(product).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def merge_products(request):
    """
    Merge a 'source' holding (e.g. a pre-merger scheme that's now closed)
    into a 'target' holding (the surviving scheme) — moves all of source's
    transaction history onto target, so XIRR can span the corporate action,
    then deactivates source.

    Deliberately does NOT touch target.invested_value/current_value — those
    should already correctly reflect target's own CAS-reported current
    state. AMC mergers reallot units based on the NAV ratio at merger time
    (value-preserving, not unit-count-preserving), so unit counts across the
    two schemes aren't on the same scale — only the dated rupee cashflows
    (transactions) are safe to carry across.
    """
    source_id = request.data.get('source_id')
    target_id = request.data.get('target_id')
    if not source_id or not target_id:
        return Response({'error': 'source_id and target_id are required'}, status=status.HTTP_400_BAD_REQUEST)
    if str(source_id) == str(target_id):
        return Response({'error': 'Cannot merge a scheme into itself'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        source = InvestmentProduct.objects.get(pk=source_id, investment_account__family_member__user=request.user)
        target = InvestmentProduct.objects.get(pk=target_id, investment_account__family_member__user=request.user)
    except InvestmentProduct.DoesNotExist:
        return Response({'error': 'Scheme not found'}, status=status.HTTP_404_NOT_FOUND)

    if source.investment_account.family_member_id != target.investment_account.family_member_id:
        return Response({'error': 'Both schemes must belong to the same family member'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        moved = Transaction.objects.filter(product=source).update(product=target)

        source_folios = (source.extra_data or {}).get('folios', [])
        target_extra = dict(target.extra_data or {})
        if source_folios:
            target_extra['folios'] = list(dict.fromkeys(target_extra.get('folios', []) + source_folios))
        target_extra.setdefault('merged_from', []).append({
            'product_id': source.id, 'name': source.name, 'isin': source.isin,
        })
        target.extra_data = target_extra
        target.save(update_fields=['extra_data'])

        source.is_active = False
        source.extra_data = {**(source.extra_data or {}), 'merged_into': {'product_id': target.id, 'name': target.name}}
        source.save(update_fields=['is_active', 'extra_data'])

    try:
        from ..tasks import compute_portfolio_analytics_task
        compute_portfolio_analytics_task.delay(target.investment_account.family_member_id)
    except Exception:
        pass

    return Response({
        'transactions_moved': moved,
        'source': {'id': source.id, 'name': source.name},
        'target': {'id': target.id, 'name': target.name},
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def product_cashflow_gap(request, pk):
    """
    Report whether a product's known transaction history covers enough of its
    invested_value for XIRR to be trustworthy (see xirr_calculator's 90%
    threshold), and if not, the missing ("gap") amount — so the UI can prompt
    for a manual legacy purchase date/amount to fill it in.
    """
    try:
        product = InvestmentProduct.objects.get(pk=pk, investment_account__family_member__user=request.user)
    except InvestmentProduct.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    purchases = Transaction.objects.filter(
        product=product, transaction_type__in=['PURCHASE', 'SIP'],
    ).order_by('transaction_date')
    known_total = sum(float(t.amount) for t in purchases if t.amount is not None)
    invested = float(product.invested_value)
    earliest = purchases.first().transaction_date if purchases.exists() else None
    gap = round(invested - known_total, 2)

    return Response({
        'invested_value': invested,
        'known_purchases_total': round(known_total, 2),
        'gap_amount': gap if gap > 0 else 0,
        'has_gap': invested > 0 and known_total < invested * 0.9,
        'earliest_known_date': str(earliest) if earliest else None,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_legacy_purchase(request, pk):
    """
    Manually record a legacy purchase (date + amount) for a product whose CAS
    import didn't cover its full transaction history — a normal MF Central
    limitation (it only exports transactions within the queried date
    window). Once captured purchases reach the invested_value threshold,
    XIRR becomes computable instead of being suppressed as unreliable.
    """
    try:
        product = InvestmentProduct.objects.get(pk=pk, investment_account__family_member__user=request.user)
    except InvestmentProduct.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    date_str = request.data.get('date')
    amount = request.data.get('amount')
    if not date_str or amount is None:
        return Response({'error': 'date and amount are required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        purchase_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        amount = Decimal(str(amount))
    except (ValueError, TypeError):
        return Response({'error': 'Invalid date or amount'}, status=status.HTTP_400_BAD_REQUEST)

    if amount <= 0:
        return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)

    txn = Transaction.objects.create(
        investment_account=product.investment_account,
        product=product,
        isin=product.isin,
        transaction_date=purchase_date,
        order_no='',
        amount=amount,
        description='Manually entered — legacy investment predating CAS transaction window',
        transaction_type='PURCHASE',
        units_debit=0, units_credit=0, units_balance=0,
    )

    try:
        from ..tasks import compute_portfolio_analytics_task
        compute_portfolio_analytics_task.delay(product.investment_account.family_member_id)
    except Exception:
        pass

    from ..services.analytics.xirr_calculator import compute_product_xirr
    xirr = compute_product_xirr(product)
    if xirr is not None:
        product.xirr = xirr
        product.save(update_fields=['xirr'])

    return Response({
        'transaction_id': txn.id,
        'xirr_pct': round(xirr * 100, 2) if xirr is not None else None,
    })
