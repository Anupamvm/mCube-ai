from __future__ import annotations
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..models import FamilyMember, PortfolioGroup, InvestmentProduct, PortfolioHealthScore
from ..serializers import PortfolioSnapshotSerializer, PortfolioHealthScoreSerializer
from ..tasks import update_all_prices_task

logger = logging.getLogger('apps.investments')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def consolidated_portfolio(request):
    member_ids_param = request.query_params.get('member_ids', '')
    if member_ids_param:
        member_ids = [int(x) for x in member_ids_param.split(',') if x.strip().isdigit()]
        members = FamilyMember.objects.filter(pk__in=member_ids, user=request.user)
    else:
        members = FamilyMember.objects.filter(user=request.user)

    products = InvestmentProduct.objects.filter(
        investment_account__family_member__in=members,
        is_active=True,
    ).select_related('investment_account')

    total_invested = 0.0
    total_current = 0.0
    asset_allocation: dict[str, float] = {}
    account_ids: set[int] = set()

    for p in products:
        iv = float(p.invested_value)
        cv = float(p.current_value)
        total_invested += iv
        total_current += cv
        asset_allocation[p.product_type] = asset_allocation.get(p.product_type, 0.0) + cv
        account_ids.add(p.investment_account_id)

    return Response({
        'total_invested_value': round(total_invested, 2),
        'total_current_value': round(total_current, 2),
        'total_gain_loss': round(total_current - total_invested, 2),
        'gain_loss_pct': round(
            ((total_current - total_invested) / total_invested * 100) if total_invested else 0, 2
        ),
        'asset_allocation': {k: round(v, 2) for k, v in asset_allocation.items()},
        'accounts_count': len(account_ids),
        'products_count': products.count(),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_price_update(request):
    member_ids_param = request.data.get('member_ids', [])
    try:
        task = update_all_prices_task.delay(
            user_id=request.user.id,
            member_ids=member_ids_param or None,
        )
        return Response({'status': 'price_update_queued', 'task_id': task.id})
    except Exception as e:
        # Broker unavailable — run synchronously so the user still gets a result.
        logger.warning('Celery broker unavailable, running price update synchronously: %s', e)
        try:
            from apps.investments.tasks import update_all_prices_task as task_fn
            result = task_fn(user_id=request.user.id, member_ids=member_ids_param or None)
            return Response({'status': 'price_update_complete', 'result': result})
        except Exception as sync_err:
            logger.error('Synchronous price update failed: %s', sync_err)
            return Response({'error': str(sync_err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def overlap_analysis(request):
    member_ids = request.data.get('member_ids', [])
    if not member_ids:
        members = FamilyMember.objects.filter(user=request.user)
        member_ids = list(members.values_list('id', flat=True))

    from ..services.analytics.overlap_analyzer import compute_overlap
    try:
        result = compute_overlap(member_ids, request.user)
        return Response(result)
    except Exception as e:
        logger.error('Overlap analysis error: %s', e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def health_score_view(request):
    member_id = request.query_params.get('member_id')
    group_id = request.query_params.get('group_id')

    if member_id:
        try:
            member = FamilyMember.objects.get(pk=member_id, user=request.user)
        except FamilyMember.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        score = PortfolioHealthScore.objects.filter(family_member=member).first()
    elif group_id:
        try:
            group = PortfolioGroup.objects.get(pk=group_id, user=request.user)
        except PortfolioGroup.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        score = PortfolioHealthScore.objects.filter(portfolio_group=group).first()
    else:
        return Response({'error': 'member_id or group_id required'}, status=status.HTTP_400_BAD_REQUEST)

    if not score:
        return Response({'error': 'No health score computed yet'}, status=status.HTTP_404_NOT_FOUND)

    return Response(PortfolioHealthScoreSerializer(score).data)
