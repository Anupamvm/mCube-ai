"""
Trading Admin Configuration - Manage trade suggestions and approvals
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from apps.trading.models import TradeSuggestion, AutoTradeConfig, TradeSuggestionLog, PositionSize


@admin.register(TradeSuggestion)
class TradeSuggestionAdmin(admin.ModelAdmin):
    """Admin interface for trade suggestions"""

    list_display = [
        'id',
        'user_username',
        'instrument',
        'direction_colored',
        'strategy',
        'status_colored',
        'recommended_lots',
        'margin_required',
        'created_at',
        'pnl_display',
    ]

    list_filter = [
        'status',
        'strategy',
        'suggestion_type',
        'created_at',
    ]

    search_fields = [
        'user__username',
        'instrument',
        'strategy',
    ]

    readonly_fields = [
        'user',
        'created_at',
        'updated_at',
        'algorithm_reasoning_display',
        'position_details_display',
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'strategy', 'suggestion_type', 'instrument', 'direction', 'status')
        }),
        ('Market Data', {
            'fields': ('spot_price', 'vix', 'expiry_date', 'days_to_expiry'),
        }),
        ('Strike Details (Options)', {
            'fields': ('call_strike', 'put_strike', 'call_premium', 'put_premium', 'total_premium'),
            'classes': ('collapse',),
        }),
        ('Position Sizing', {
            'fields': ('recommended_lots', 'margin_required', 'margin_available', 'margin_per_lot', 'margin_utilization'),
        }),
        ('Risk Metrics', {
            'fields': ('max_profit', 'max_loss', 'breakeven_upper', 'breakeven_lower', 'risk_reward_ratio'),
            'classes': ('collapse',),
        }),
        ('P&L Tracking', {
            'fields': ('entry_value', 'exit_value', 'realized_pnl', 'return_on_margin'),
        }),
        ('Algorithm Data', {
            'fields': ('algorithm_reasoning_display', 'position_details_display'),
            'classes': ('collapse',),
        }),
        ('Status Tracking', {
            'fields': ('taken_timestamp', 'closed_timestamp', 'rejected_timestamp', 'user_notes'),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'expires_at'),
            'classes': ('collapse',),
        }),
    )

    actions = ['mark_expired']

    def user_username(self, obj):
        """Display user username"""
        return obj.user.username
    user_username.short_description = 'User'

    def direction_colored(self, obj):
        """Color-code direction"""
        colors = {
            'LONG': '#28a745',
            'SHORT': '#dc3545',
            'NEUTRAL': '#6c757d',
        }
        color = colors.get(obj.direction, '#000000')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.direction
        )
    direction_colored.short_description = 'Direction'

    def status_colored(self, obj):
        """Color-code status"""
        colors = {
            'SUGGESTED': '#3B82F6',
            'TAKEN': '#8B5CF6',
            'REJECTED': '#6B7280',
            'ACTIVE': '#F59E0B',
            'CLOSED': '#6B7280',
            'SUCCESSFUL': '#10B981',
            'LOSS': '#EF4444',
            'BREAKEVEN': '#FBBF24',
            'EXPIRED': '#6B7280',
            'CANCELLED': '#6B7280',
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = 'Status'

    def pnl_display(self, obj):
        """Display P&L if closed"""
        if obj.realized_pnl:
            color = '#10B981' if obj.realized_pnl > 0 else '#EF4444'
            return format_html(
                '<span style="color: {}; font-weight: bold;">₹{:,.2f}</span> ({:.2f}% ROM)',
                color,
                float(obj.realized_pnl),
                float(obj.return_on_margin or 0)
            )
        return '-'
    pnl_display.short_description = 'Realized P&L'

    def algorithm_reasoning_display(self, obj):
        """Display algorithm reasoning as formatted JSON"""
        import json
        if obj.algorithm_reasoning:
            return format_html(
                '<pre style="background-color: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto;">{}</pre>',
                json.dumps(obj.algorithm_reasoning, indent=2)
            )
        return 'No reasoning data'
    algorithm_reasoning_display.short_description = 'Algorithm Reasoning'

    def position_details_display(self, obj):
        """Display position details as formatted JSON"""
        import json
        if obj.position_details:
            return format_html(
                '<pre style="background-color: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto;">{}</pre>',
                json.dumps(obj.position_details, indent=2)
            )
        return 'No position details'
    position_details_display.short_description = 'Position Details'

    def mark_expired(self, request, queryset):
        """Admin action to mark suggestions as expired"""
        count = queryset.filter(status='SUGGESTED').update(status='EXPIRED')
        self.message_user(request, f'{count} suggestions marked as expired.')
    mark_expired.short_description = 'Mark selected as expired'

    def has_add_permission(self, request):
        """Prevent manual creation of suggestions through admin"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Allow deletion only for executed or rejected suggestions"""
        if obj:
            return obj.status in ['EXECUTED', 'REJECTED', 'EXPIRED', 'CANCELLED']
        return True


@admin.register(AutoTradeConfig)
class AutoTradeConfigAdmin(admin.ModelAdmin):
    """Admin interface for auto-trade configuration"""

    list_display = [
        'user_username',
        'strategy',
        'is_enabled_colored',
        'auto_approve_threshold',
        'max_daily_positions',
        'max_daily_loss',
    ]

    list_filter = [
        'is_enabled',
        'strategy',
        'updated_at',
    ]

    search_fields = [
        'user__username',
        'strategy',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
    ]

    fieldsets = (
        ('User & Strategy', {
            'fields': ('user', 'strategy')
        }),
        ('Auto-Trade Settings', {
            'fields': ('is_enabled', 'auto_approve_threshold')
        }),
        ('Risk Controls', {
            'fields': ('max_daily_positions', 'max_daily_loss')
        }),
        ('Special Rules', {
            'fields': ('require_human_on_weekend', 'require_human_on_high_vix', 'vix_threshold')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def user_username(self, obj):
        """Display user username"""
        return obj.user.username
    user_username.short_description = 'User'

    def is_enabled_colored(self, obj):
        """Color-code enabled status"""
        color = '#28a745' if obj.is_enabled else '#dc3545'
        status = 'ENABLED' if obj.is_enabled else 'DISABLED'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            status
        )
    is_enabled_colored.short_description = 'Status'


@admin.register(TradeSuggestionLog)
class TradeSuggestionLogAdmin(admin.ModelAdmin):
    """Admin interface for trade suggestion audit logs (read-only)"""

    list_display = [
        'suggestion_id',
        'action_colored',
        'user_display',
        'created_at',
        'notes_preview',
    ]

    list_filter = [
        'action',
        'created_at',
        ('user', admin.RelatedOnlyFieldListFilter),
    ]

    search_fields = [
        'suggestion__id',
        'suggestion__instrument',
        'user__username',
        'notes',
    ]

    readonly_fields = [
        'suggestion',
        'action',
        'user',
        'notes',
        'created_at',
    ]

    fieldsets = (
        ('Log Information', {
            'fields': ('suggestion', 'action', 'user', 'created_at')
        }),
        ('Details', {
            'fields': ('notes',)
        }),
    )

    def suggestion_id(self, obj):
        """Display suggestion ID with link"""
        url = reverse('admin:trading_tradesuggestion_change', args=[obj.suggestion.id])
        return format_html('<a href="{}">{}</a>', url, obj.suggestion.id)
    suggestion_id.short_description = 'Suggestion'

    def action_colored(self, obj):
        """Color-code action"""
        colors = {
            'CREATED': '#17a2b8',
            'APPROVED': '#28a745',
            'AUTO_APPROVED': '#20c997',
            'REJECTED': '#dc3545',
            'EXECUTED': '#6f42c1',
            'EXPIRED': '#6c757d',
            'CANCELLED': '#6c757d',
        }
        color = colors.get(obj.action, '#000000')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_action_display()
        )
    action_colored.short_description = 'Action'

    def user_display(self, obj):
        """Display user"""
        if obj.user:
            return obj.user.username
        return 'System'
    user_display.short_description = 'User'

    def notes_preview(self, obj):
        """Display preview of notes"""
        if obj.notes:
            preview = obj.notes[:50]
            if len(obj.notes) > 50:
                preview += '...'
            return preview
        return '-'
    notes_preview.short_description = 'Notes'

    def has_add_permission(self, request):
        """Prevent manual log creation"""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent modification of logs"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of logs"""
        return False


@admin.register(PositionSize)
class PositionSizeAdmin(admin.ModelAdmin):
    """Admin interface for position sizing calculations"""

    list_display = [
        'id',
        'user_username',
        'symbol',
        'instrument_type_colored',
        'recommended_lots',
        'total_quantity',
        'margin_required',
        'max_loss_profit',
        'status_colored',
        'created_at',
    ]

    list_filter = [
        'instrument_type',
        'direction',
        'status',
        'margin_source',
        'created_at',
    ]

    search_fields = [
        'user__username',
        'symbol',
    ]

    readonly_fields = [
        'user',
        'created_at',
        'updated_at',
        'calculation_details_display',
        'averaging_data_display',
    ]

    fieldsets = (
        ('Trade Information', {
            'fields': ('user', 'symbol', 'instrument_type', 'direction')
        }),
        ('Price Levels', {
            'fields': ('entry_price', 'stop_loss', 'target')
        }),
        ('Contract Details', {
            'fields': ('lot_size', 'strike', 'option_type')
        }),
        ('Margin Information', {
            'fields': ('available_margin', 'margin_per_lot', 'margin_source')
        }),
        ('Position Sizing Results', {
            'fields': ('recommended_lots', 'total_quantity', 'margin_required', 'max_loss', 'max_profit', 'risk_reward_ratio')
        }),
        ('Averaging Down', {
            'fields': ('averaging_data_display',),
            'classes': ('collapse',),
        }),
        ('Full Calculation', {
            'fields': ('calculation_details_display',),
            'classes': ('collapse',),
        }),
        ('Status & Timestamps', {
            'fields': ('status', 'created_at', 'updated_at', 'expires_at')
        }),
    )

    def user_username(self, obj):
        return obj.user.username
    user_username.short_description = 'User'

    def instrument_type_colored(self, obj):
        color = '#2563EB' if obj.instrument_type == 'FUTURES' else '#10B981'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.instrument_type
        )
    instrument_type_colored.short_description = 'Type'

    def max_loss_profit(self, obj):
        return format_html(
            'Loss: <span style="color: #dc3545;">₹{:,.2f}</span> | Profit: <span style="color: #28a745;">₹{:,.2f}</span>',
            float(obj.max_loss),
            float(obj.max_profit)
        )
    max_loss_profit.short_description = 'Max Loss/Profit'

    def status_colored(self, obj):
        colors = {
            'ACTIVE': '#17a2b8',
            'EXECUTED': '#28a745',
            'EXPIRED': '#6c757d',
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = 'Status'

    def calculation_details_display(self, obj):
        import json
        if obj.calculation_details:
            return format_html(
                '<pre style="background-color: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto;">{}</pre>',
                json.dumps(obj.calculation_details, indent=2)
            )
        return 'No data'
    calculation_details_display.short_description = 'Full Calculation'

    def averaging_data_display(self, obj):
        import json
        if obj.averaging_data:
            return format_html(
                '<pre style="background-color: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto;">{}</pre>',
                json.dumps(obj.averaging_data, indent=2)
            )
        return 'N/A (Options only have single position)'
    averaging_data_display.short_description = 'Averaging Down Data'

    def has_add_permission(self, request):
        return False
