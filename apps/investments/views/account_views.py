from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from ..models import InvestmentAccount, FamilyMember
from ..serializers import InvestmentAccountSerializer, InvestmentProductSerializer


class AccountListCreateView(generics.ListCreateAPIView):
    serializer_class = InvestmentAccountSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = InvestmentAccount.objects.filter(family_member__user=self.request.user)
        if self.request.query_params.get('include_archived', '').lower() not in ('true', '1', 'yes'):
            qs = qs.filter(is_active=True)
        member_id = self.request.query_params.get('member_id')
        if member_id:
            qs = qs.filter(family_member_id=member_id)
        account_type = self.request.query_params.get('account_type')
        if account_type:
            qs = qs.filter(account_type=account_type)
        return qs

    def perform_create(self, serializer):
        member = FamilyMember.objects.get(
            pk=self.request.data.get('family_member'),
            user=self.request.user
        )
        serializer.save(family_member=member)


class AccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = InvestmentAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InvestmentAccount.objects.filter(family_member__user=self.request.user)

    def perform_destroy(self, instance):
        permanent = self.request.query_params.get('mode', '').lower() == 'permanent'
        if permanent:
            instance.delete()
        else:
            instance.is_active = False
            instance.save(update_fields=['is_active'])


class AccountProductsView(generics.ListAPIView):
    serializer_class = InvestmentProductSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        account_id = self.kwargs['pk']
        account = get_object_or_404(
            InvestmentAccount, pk=account_id, family_member__user=self.request.user
        )
        return account.products.filter(is_active=True)
