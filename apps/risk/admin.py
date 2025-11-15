from django.contrib import admin
from .models import RiskLimit, CircuitBreaker


@admin.register(RiskLimit)
class RiskLimitAdmin(admin.ModelAdmin):
    list_display = ['account', 'limit_type', 'current_value', 'limit_value', 'is_breached', 'period_start']
    list_filter = ['limit_type', 'is_breached', 'warning_sent']
    search_fields = ['account__account_name']


@admin.register(CircuitBreaker)
class CircuitBreakerAdmin(admin.ModelAdmin):
    list_display = ['account', 'trigger_type', 'risk_level', 'is_active', 'positions_closed', 'created_at']
    list_filter = ['trigger_type', 'risk_level', 'is_active']
    search_fields = ['account__account_name']
    readonly_fields = ['created_at', 'updated_at', 'reset_at']
