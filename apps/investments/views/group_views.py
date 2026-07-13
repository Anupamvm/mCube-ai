from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..models import PortfolioGroup, InvestmentProduct
from ..serializers import PortfolioGroupSerializer


class PortfolioGroupListCreateView(generics.ListCreateAPIView):
    serializer_class = PortfolioGroupSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return PortfolioGroup.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PortfolioGroupDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PortfolioGroupSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PortfolioGroup.objects.filter(user=self.request.user)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def group_net_worth(request, pk):
    try:
        group = PortfolioGroup.objects.get(pk=pk, user=request.user)
    except PortfolioGroup.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    members = group.members.all()
    products = InvestmentProduct.objects.filter(
        investment_account__family_member__in=members,
        is_active=True,
    )

    total_invested = sum(float(p.invested_value) for p in products)
    total_current = sum(float(p.current_value) for p in products)

    breakdown = {}
    for p in products:
        key = p.product_type
        if key not in breakdown:
            breakdown[key] = {'invested': 0, 'current': 0, 'count': 0}
        breakdown[key]['invested'] += float(p.invested_value)
        breakdown[key]['current'] += float(p.current_value)
        breakdown[key]['count'] += 1

    from ..services.analytics.xirr_calculator import compute_family_xirr

    return Response({
        'group_id': group.id,
        'group_name': group.name,
        'members': [{'id': m.id, 'name': m.name} for m in members],
        'total_invested': round(total_invested, 2),
        'current_value': round(total_current, 2),
        'gain_loss': round(total_current - total_invested, 2),
        'gain_loss_pct': round(
            ((total_current - total_invested) / total_invested * 100) if total_invested else 0, 2
        ),
        'xirr': compute_family_xirr(members),
        'breakdown_by_type': breakdown,
    })
