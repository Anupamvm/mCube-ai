from django.contrib import admin
from .models import TradeVerificationSnapshot


@admin.register(TradeVerificationSnapshot)
class TradeVerificationSnapshotAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'expiry_date', 'position', 'requested_by', 'llm_provider', 'created_at']
    list_filter = ['llm_provider']
    search_fields = ['symbol']
    readonly_fields = ['created_at', 'updated_at']
