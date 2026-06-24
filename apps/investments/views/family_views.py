from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum
from ..models import FamilyMember, InvestmentProduct, PortfolioSnapshot, PortfolioHealthScore
from ..serializers import FamilyMemberSerializer, PortfolioSnapshotSerializer, PortfolioHealthScoreSerializer


class FamilyMemberListCreateView(generics.ListCreateAPIView):
    serializer_class = FamilyMemberSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return FamilyMember.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class FamilyMemberDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FamilyMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FamilyMember.objects.filter(user=self.request.user)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def member_net_worth(request, pk):
    try:
        member = FamilyMember.objects.get(pk=pk, user=request.user)
    except FamilyMember.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    products = InvestmentProduct.objects.filter(
        investment_account__family_member=member,
        is_active=True,
    ).select_related('investment_account')

    asset_allocation = {}
    total_invested = 0.0
    total_current = 0.0
    account_ids = set()

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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def member_analytics(request, pk):
    try:
        member = FamilyMember.objects.get(pk=pk, user=request.user)
    except FamilyMember.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    latest_snapshot = PortfolioSnapshot.objects.filter(family_member=member).first()
    latest_score = PortfolioHealthScore.objects.filter(family_member=member).first()

    return Response({
        'snapshot': PortfolioSnapshotSerializer(latest_snapshot).data if latest_snapshot else None,
        'health_score': PortfolioHealthScoreSerializer(latest_score).data if latest_score else None,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def member_insights(request, pk):
    try:
        member = FamilyMember.objects.get(pk=pk, user=request.user)
    except FamilyMember.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    latest_score = PortfolioHealthScore.objects.filter(family_member=member).first()
    insights = latest_score.insights if latest_score else []
    return Response({'insights': insights})
