from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..models import InvestmentProduct, ProductValuationHistory, InvestmentAccount, MutualFundScheme
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
