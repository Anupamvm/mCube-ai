from django.contrib import admin
from .models import (
    CredentialStore,
    TradingSchedule,
    NseFlag,
    BkLog,
    DayReport,
    TodaysPosition,
    SystemSettings
)


@admin.register(CredentialStore)
class CredentialStoreAdmin(admin.ModelAdmin):
    list_display = ['service', 'name', 'username', 'created_at', 'last_session_update']
    list_filter = ['service']
    search_fields = ['service', 'name', 'username']
    readonly_fields = ['created_at', 'last_session_update']

    fieldsets = (
        ('Service Information', {
            'fields': ('service', 'name')
        }),
        ('API Credentials', {
            'fields': ('api_key', 'api_secret', 'session_token'),
            'classes': ('collapse',)
        }),
        ('Username/Password Credentials', {
            'fields': ('username', 'password'),
        }),
        ('Additional Fields', {
            'fields': ('pan', 'neo_password', 'sid'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_session_update'),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Make password fields use password input widget
        if 'password' in form.base_fields:
            form.base_fields['password'].widget.attrs['type'] = 'password'
        if 'neo_password' in form.base_fields:
            form.base_fields['neo_password'].widget.attrs['type'] = 'password'
        if 'api_secret' in form.base_fields:
            form.base_fields['api_secret'].widget.attrs['type'] = 'password'
        return form


@admin.register(TradingSchedule)
class TradingScheduleAdmin(admin.ModelAdmin):
    list_display = ['date', 'enabled', 'open_time', 'take_trade_time', 'close_pos_time', 'note']
    list_filter = ['enabled', 'date']
    search_fields = ['date', 'note']
    date_hierarchy = 'date'

    fieldsets = (
        ('Date & Status', {
            'fields': ('date', 'enabled', 'note')
        }),
        ('Trading Times', {
            'fields': (
                'open_time',
                'take_trade_time',
                'last_trade_time',
                'close_pos_time',
                'mkt_close_time',
                'close_day_time'
            )
        }),
    )


@admin.register(NseFlag)
class NseFlagAdmin(admin.ModelAdmin):
    list_display = ['flag', 'value', 'updated_at']
    list_filter = ['updated_at']
    search_fields = ['flag', 'value', 'description']
    readonly_fields = ['updated_at']

    fieldsets = (
        ('Flag', {
            'fields': ('flag', 'value', 'description')
        }),
        ('Metadata', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(BkLog)
class BkLogAdmin(admin.ModelAdmin):
    list_display = [
        'colored_timestamp',
        'status_icon',
        'colored_level',
        'task_category',
        'background_task',
        'action',
        'short_message',
        'exec_time'
    ]
    list_filter = [
        'level',
        'task_category',
        'success',
        'background_task',
        ('timestamp', admin.DateFieldListFilter),
    ]
    search_fields = ['action', 'message', 'background_task', 'task_id']
    readonly_fields = [
        'timestamp',
        'level',
        'action',
        'message',
        'background_task',
        'task_category',
        'task_id',
        'execution_time_ms',
        'formatted_context_data',
        'error_details',
        'success'
    ]
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']

    fieldsets = (
        ('Basic Information', {
            'fields': ('timestamp', 'level', 'success', 'action', 'message')
        }),
        ('Task Details', {
            'fields': ('background_task', 'task_category', 'task_id', 'execution_time_ms')
        }),
        ('Context Data', {
            'fields': ('formatted_context_data',),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('error_details',),
            'classes': ('collapse',)
        }),
    )

    def colored_timestamp(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<span style="font-family: monospace;">{}</span>',
            obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        )
    colored_timestamp.short_description = 'Timestamp'
    colored_timestamp.admin_order_field = 'timestamp'

    def status_icon(self, obj):
        from django.utils.html import format_html
        if obj.success:
            return format_html('<span style="color: green; font-size: 16px;">✓</span>')
        else:
            return format_html('<span style="color: red; font-size: 16px;">✗</span>')
    status_icon.short_description = 'Status'
    status_icon.admin_order_field = 'success'

    def colored_level(self, obj):
        from django.utils.html import format_html
        colors = {
            'debug': '#6c757d',
            'info': '#0dcaf0',
            'warning': '#ffc107',
            'error': '#dc3545',
            'critical': '#8b0000',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.level, '#000'),
            obj.level.upper()
        )
    colored_level.short_description = 'Level'
    colored_level.admin_order_field = 'level'

    def short_message(self, obj):
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    short_message.short_description = 'Message'

    def exec_time(self, obj):
        from django.utils.html import format_html
        if obj.execution_time_ms:
            if obj.execution_time_ms > 5000:  # > 5 seconds
                color = 'red'
            elif obj.execution_time_ms > 2000:  # > 2 seconds
                color = 'orange'
            else:
                color = 'green'

            return format_html(
                '<span style="color: {};">{} ms</span>',
                color,
                obj.execution_time_ms
            )
        return '-'
    exec_time.short_description = 'Exec Time'
    exec_time.admin_order_field = 'execution_time_ms'

    def formatted_context_data(self, obj):
        from django.utils.html import format_html
        import json
        if obj.context_data:
            formatted_json = json.dumps(obj.context_data, indent=2)
            return format_html('<pre>{}</pre>', formatted_json)
        return '-'
    formatted_context_data.short_description = 'Context Data'

    # Add actions for bulk operations
    actions = ['mark_as_reviewed', 'export_to_csv']

    def mark_as_reviewed(self, request, queryset):
        # This is a placeholder - you can add a 'reviewed' field to the model if needed
        self.message_user(request, f'{queryset.count()} logs marked as reviewed.')
    mark_as_reviewed.short_description = 'Mark selected logs as reviewed'

    def export_to_csv(self, request, queryset):
        import csv
        from django.http import HttpResponse
        from datetime import datetime

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="task_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Timestamp', 'Level', 'Task Category', 'Background Task',
            'Action', 'Message', 'Success', 'Execution Time (ms)'
        ])

        for log in queryset:
            writer.writerow([
                log.timestamp,
                log.level,
                log.task_category,
                log.background_task,
                log.action,
                log.message,
                'Yes' if log.success else 'No',
                log.execution_time_ms or ''
            ])

        return response
    export_to_csv.short_description = 'Export selected logs to CSV'


@admin.register(DayReport)
class DayReportAdmin(admin.ModelAdmin):
    list_display = ['date', 'day_of_week', 'pnl', 'num_legs', 'is_closed', 'expiry_date']
    list_filter = ['is_closed', 'day_of_week', 'date']
    search_fields = ['date', 'notes']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'date'

    fieldsets = (
        ('Date Information', {
            'fields': ('date', 'day_of_week', 'expiry_date')
        }),
        ('Trading Results', {
            'fields': ('num_legs', 'pnl', 'is_closed')
        }),
        ('Additional Info', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TodaysPosition)
class TodaysPositionAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'symbol', 'option_type', 'strike_price',
        'net_trd_qty_lot', 'realized_pl', 'last_price'
    ]
    list_filter = ['date', 'symbol', 'option_type', 'exchange']
    search_fields = ['symbol', 'instrument_name']
    readonly_fields = ['created_at']
    date_hierarchy = 'date'

    fieldsets = (
        ('Position Details', {
            'fields': ('date', 'symbol', 'instrument_name', 'instrument_token')
        }),
        ('Contract Details', {
            'fields': ('exchange', 'segment', 'expiry_date', 'option_type', 'strike_price')
        }),
        ('Buy Side', {
            'fields': (
                'buy_traded_qty_lot', 'buy_traded_val', 'buy_trd_avg',
                'buy_open_qty_lot', 'buy_open_val'
            ),
            'classes': ('collapse',)
        }),
        ('Sell Side', {
            'fields': (
                'sell_traded_qty_lot', 'sell_traded_val', 'sell_trd_avg',
                'sell_open_qty_lot', 'sell_open_val'
            ),
            'classes': ('collapse',)
        }),
        ('Net Position', {
            'fields': (
                'net_trd_qty_lot', 'net_trd_value', 'actual_net_trd_value',
                'realized_pl', 'last_price', 'average_stock_price'
            )
        }),
        ('Margins', {
            'fields': (
                'span_margin', 'span_margin_total',
                'exposure_margin', 'exposure_margin_total', 'premium'
            ),
            'classes': ('collapse',)
        }),
    )


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    """
    Admin interface for SystemSettings model
    Singleton model - only one instance should exist
    """
    list_display = ['__str__', 'updated_at']
    readonly_fields = ['created_at', 'updated_at', 'singleton_id']

    fieldsets = (
        ('Market Data Task Timings', {
            'fields': (
                ('trendlyne_fetch_hour', 'trendlyne_fetch_minute'),
                ('trendlyne_import_hour', 'trendlyne_import_minute'),
                ('premarket_update_hour', 'premarket_update_minute'),
                ('postmarket_update_hour', 'postmarket_update_minute'),
                ('live_data_interval_minutes', 'live_data_start_hour', 'live_data_end_hour'),
            )
        }),
        ('Strategy Task Timings', {
            'fields': (
                ('futures_screening_interval_minutes', 'futures_screening_start_hour', 'futures_screening_end_hour'),
                'futures_averaging_interval_minutes',
            )
        }),
        ('Position Monitoring Task Timings', {
            'fields': (
                'monitor_positions_interval_seconds',
                'update_pnl_interval_seconds',
                'check_exit_interval_seconds',
            )
        }),
        ('Risk Management Task Timings', {
            'fields': (
                'risk_check_interval_seconds',
                'circuit_breaker_interval_seconds',
            )
        }),
        ('Reporting & Analytics Task Timings', {
            'fields': (
                ('daily_pnl_report_hour', 'daily_pnl_report_minute'),
                ('learning_patterns_hour', 'learning_patterns_minute'),
                ('weekly_summary_hour', 'weekly_summary_minute', 'weekly_summary_day_of_week'),
            )
        }),
        ('Task Enable/Disable Flags', {
            'fields': (
                'enable_market_data_tasks',
                'enable_strategy_tasks',
                'enable_position_monitoring',
                'enable_risk_monitoring',
                'enable_reporting_tasks',
            ),
            'classes': ('wide',)
        }),
        ('Metadata', {
            'fields': ('singleton_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        """
        Prevent adding new instances - singleton pattern
        """
        return not SystemSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """
        Prevent deleting the settings - singleton pattern
        """
        return False
