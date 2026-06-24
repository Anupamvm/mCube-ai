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
        metrics = compute_risk_metrics(nav_qs)
        return Response({'isin': isin, 'period': period, **metrics})
    except Exception as e:
        logger.error('Risk metrics error for %s: %s', isin, e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
