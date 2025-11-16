"""
Trading Admin Configuration - Manage trade suggestions and approvals
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from apps.trading.models import TradeSuggestion, AutoTradeConfig, TradeSuggestionLog


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
        'created_at',
        'approved_by_display',
    ]

    list_filter = [
        'status',
        'strategy',
        'suggestion_type',
        'created_at',
        ('approved_by', admin.RelatedOnlyFieldListFilter),
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
        'logs_display',
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'strategy', 'suggestion_type', 'instrument', 'direction')
        }),
        ('Algorithm Data', {
            'fields': ('algorithm_reasoning_display', 'position_details_display'),
            'classes': ('collapse',),
        }),
        ('Approval Status', {
            'fields': ('status', 'approved_by', 'approval_timestamp', 'approval_notes', 'is_auto_trade')
        }),
        ('Execution', {
            'fields': ('executed_position',),
            'classes': ('collapse',),
        }),
        ('Timestamps & Audit', {
            'fields': ('created_at', 'updated_at', 'expires_at', 'logs_display'),
            'classes': ('collapse',),
        }),
    )

    actions = ['approve_selected', 'reject_selected', 'mark_expired']

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
            'PENDING': '#ffc107',
            'APPROVED': '#17a2b8',
            'AUTO_APPROVED': '#20c997',
            'REJECTED': '#dc3545',
            'EXECUTED': '#28a745',
            'EXPIRED': '#6c757d',
            'CANCELLED': '#6c757d',
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = 'Status'

    def approved_by_display(self, obj):
        """Display who approved"""
        if obj.approved_by:
            return obj.approved_by.username
        return '-'
    approved_by_display.short_description = 'Approved By'

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

    def logs_display(self, obj):
        """Display associated logs"""
        logs = obj.logs.all().order_by('-created_at')
        if not logs:
            return 'No logs'

        html = '<ul style="margin: 0; padding-left: 20px;">'
        for log in logs[:5]:  # Show last 5 logs
            html += f'<li>{log.created_at.strftime("%Y-%m-%d %H:%M:%S")} - {log.get_action_display()}'
            if log.user:
                html += f' by {log.user.username}'
            if log.notes:
                html += f': {log.notes}'
            html += '</li>'
        html += '</ul>'

        if logs.count() > 5:
            html += f'<p><em>... and {logs.count() - 5} more logs</em></p>'

        return format_html(html)
    logs_display.short_description = 'Audit Logs'

    def approve_selected(self, request, queryset):
        """Admin action to approve selected suggestions"""
        count = 0
        for suggestion in queryset.filter(status='PENDING'):
            suggestion.status = 'APPROVED'
            suggestion.approved_by = request.user
            from django.utils import timezone
            suggestion.approval_timestamp = timezone.now()
            suggestion.save()
            count += 1

        self.message_user(request, f'{count} suggestions approved.')
    approve_selected.short_description = 'Approve selected suggestions'

    def reject_selected(self, request, queryset):
        """Admin action to reject selected suggestions"""
        count = 0
        for suggestion in queryset.filter(status='PENDING'):
            suggestion.status = 'REJECTED'
            suggestion.approval_notes = 'Rejected by admin'
            suggestion.save()
            count += 1

        self.message_user(request, f'{count} suggestions rejected.')
    reject_selected.short_description = 'Reject selected suggestions'

    def mark_expired(self, request, queryset):
        """Admin action to mark suggestions as expired"""
        count = queryset.exclude(status__in=['EXECUTED', 'REJECTED', 'CANCELLED']).update(status='EXPIRED')
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
