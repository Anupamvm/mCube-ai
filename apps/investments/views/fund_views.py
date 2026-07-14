import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..models import MutualFundScheme, NAVHistory
from ..serializers import MutualFundSchemeSerializer, NAVHistorySerializer
from ..services.mfapi_client import MFAPIClient

logger = logging.getLogger('apps.investments')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fund_detail(request, isin):
    try:
        scheme = MutualFundScheme.objects.get(isin=isin)
    except MutualFundScheme.DoesNotExist:
        # Try to fetch from MFAPI on-demand
        client = MFAPIClient()
        isin_map = client.get_isin_map()
        scheme_code = isin_map.get(isin)
        if not scheme_code:
            return Response({'error': 'Fund not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            scheme = client.fetch_and_save_scheme(scheme_code, isin)
        except Exception as e:
            logger.error('MFAPI fetch error for %s: %s', isin, e)
            return Response({'error': 'Could not fetch fund details'}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(MutualFundSchemeSerializer(scheme).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fund_nav_history(request, isin):
    period = request.query_params.get('period', '1Y')
    try:
        scheme = MutualFundScheme.objects.get(isin=isin)
    except MutualFundScheme.DoesNotExist:
        return Response({'error': 'Fund not found'}, status=status.HTTP_404_NOT_FOUND)

    from datetime import date, timedelta
    period_map = {'1Y': 365, '3Y': 365 * 3, '5Y': 365 * 5}
    days = period_map.get(period, 365)
    since = date.today() - timedelta(days=days)
    nav_qs = NAVHistory.objects.filter(scheme=scheme, date__gte=since).order_by('date')
    data = [{'date': str(n.date), 'nav': float(n.nav)} for n in nav_qs]
    return Response({'isin': isin, 'period': period, 'nav_history': data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fund_risk_metrics(request, isin):
    period = request.query_params.get('period', '3Y')
    try:
        scheme = MutualFundScheme.objects.get(isin=isin)
    except MutualFundScheme.DoesNotExist:
        return Response({'error': 'Fund not found'}, status=status.HTTP_404_NOT_FOUND)

    from ..services.analytics.risk_metrics import compute_risk_metrics
    from datetime import date, timedelta
    period_map = {'1Y': 365, '3Y': 365 * 3, '5Y': 365 * 5}
    days = period_map.get(period, 365 * 3)
    since = date.today() - timedelta(days=days)

    nav_qs = NAVHistory.objects.filter(scheme=scheme, date__gte=since).order_by('date')
    if nav_qs.count() < 30:
        return Response({'error': 'Insufficient NAV history for risk metrics'}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    try:
        metrics = compute_risk_metrics(nav_qs, sub_category=scheme.sub_category, scheme_name=scheme.scheme_name)
        return Response({'isin': isin, 'period': period, **metrics})
    except Exception as e:
        logger.error('Risk metrics error for %s: %s', isin, e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fund_returns(request, isin):
    """Trailing point-to-point returns (1W/1M/3M/6M/1Y/3Y/5Y, CAGR beyond 1Y)."""
    try:
        scheme = MutualFundScheme.objects.get(isin=isin)
    except MutualFundScheme.DoesNotExist:
        return Response({'error': 'Fund not found'}, status=status.HTTP_404_NOT_FOUND)

    from ..services.analytics.returns_calculator import compute_trailing_returns
    nav_qs = NAVHistory.objects.filter(scheme=scheme)
    returns = compute_trailing_returns(nav_qs)
    if not returns:
        return Response({'error': 'Insufficient NAV history for returns'}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    return Response({'isin': isin, 'scheme_name': scheme.scheme_name, 'returns': returns})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fund_my_holding(request, isin):
    """
    Aggregate the requesting user's own holdings of a single ISIN across every
    family member and account — e.g. the same mutual fund held in both a
    parent's and a spouse's folio, combined into one XIRR.
    """
    from ..models import FamilyMember, InvestmentProduct
    from ..services.analytics.xirr_calculator import compute_fund_xirr

    members = FamilyMember.objects.filter(user=request.user)
    products = InvestmentProduct.objects.filter(
        isin=isin,
        investment_account__family_member__in=members,
        is_active=True,
    ).select_related('investment_account', 'investment_account__family_member')

    if not products.exists():
        return Response({'error': 'No holdings found for this ISIN'}, status=status.HTTP_404_NOT_FOUND)

    total_invested = sum(float(p.invested_value) for p in products)
    total_current = sum(float(p.current_value) for p in products)

    holdings = [{
        'product_id': p.id,
        'name': p.name,
        'member_name': p.investment_account.family_member.name,
        'account_name': p.investment_account.account_name,
        'invested_value': float(p.invested_value),
        'current_value': float(p.current_value),
        'xirr': float(p.xirr) if p.xirr is not None else None,
    } for p in products]

    return Response({
        'isin': isin,
        'total_invested_value': round(total_invested, 2),
        'total_current_value': round(total_current, 2),
        'total_gain_loss': round(total_current - total_invested, 2),
        'gain_loss_pct': round(
            ((total_current - total_invested) / total_invested * 100) if total_invested else 0, 2
        ),
        'xirr': compute_fund_xirr(isin, members),
        'holdings': holdings,
    })
