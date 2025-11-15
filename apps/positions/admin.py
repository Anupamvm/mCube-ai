from django.contrib import admin
from .models import Position, MonitorLog


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ['instrument', 'direction', 'status', 'account', 'entry_price', 'current_price', 'unrealized_pnl', 'entry_time']
    list_filter = ['status', 'direction', 'strategy_type', 'account']
    search_fields = ['instrument', 'account__account_name']
    readonly_fields = ['created_at', 'updated_at', 'entry_time', 'exit_time']
    date_hierarchy = 'entry_time'
    
    fieldsets = (
        ('Position Details', {
            'fields': ('account', 'strategy_type', 'instrument', 'direction', 'status')
        }),
        ('Sizing', {
            'fields': ('quantity', 'lot_size', 'margin_used', 'entry_value')
        }),
        ('Pricing', {
            'fields': ('entry_price', 'current_price', 'stop_loss', 'target', 'exit_price')
        }),
        ('Strangle Specific', {
            'fields': ('call_strike', 'put_strike', 'call_premium', 'put_premium', 'premium_collected', 'current_delta'),
            'classes': ('collapse',)
        }),
        ('P&L', {
            'fields': ('realized_pnl', 'unrealized_pnl')
        }),
        ('Timing', {
            'fields': ('expiry_date', 'entry_time', 'exit_time', 'exit_reason')
        }),
        ('Averaging', {
            'fields': ('averaging_count', 'original_entry_price', 'partial_booked', 'partial_quantity'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )


@admin.register(MonitorLog)
class MonitorLogAdmin(admin.ModelAdmin):
    list_display = ['position', 'check_type', 'result', 'price_at_check', 'pnl_at_check', 'created_at']
    list_filter = ['check_type', 'result']
    search_fields = ['position__instrument', 'message']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
