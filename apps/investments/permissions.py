from rest_framework.permissions import BasePermission
from .models import FamilyMember


class OwnsFamilyMember(BasePermission):
    """Ensure the family member belongs to the requesting user."""

    def has_object_permission(self, request, view, obj):
        if isinstance(obj, FamilyMember):
            return obj.user == request.user
        if hasattr(obj, 'family_member'):
            return obj.family_member.user == request.user
        if hasattr(obj, 'investment_account'):
            return obj.investment_account.family_member.user == request.user
        return False
