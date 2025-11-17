from django.contrib import admin
from django.utils.html import format_html
from .models import (
    StrategyConfig,
    StrategyLearning,
    TradingScheduleConfig,
    MarketOpeningState,
    SGXNiftyData,
    DailyTradingAnalysis,
    TradingInsight
)


@admin.register(StrategyConfig)
class StrategyConfigAdmin(admin.ModelAdmin):
    list_display = ['account', 'strategy_type', 'is_active', 'initial_margin_usage_pct']
    list_filter = ['strategy_type', 'is_active', 'allow_averaging']
    search_fields = ['account__account_name']


@admin.register(StrategyLearning)
class StrategyLearningAdmin(admin.ModelAdmin):
    list_display = ['pattern_name', 'strategy_type', 'times_occurred', 'win_rate', 'profit_factor', 'is_reliable']
    list_filter = ['strategy_type', 'is_reliable']
    search_fields = ['pattern_name', 'pattern_description']
    readonly_fields = ['created_at', 'updated_at', 'last_occurrence']


@admin.register(TradingScheduleConfig)
class TradingScheduleConfigAdmin(admin.ModelAdmin):
    """
    Admin interface for configurable trading schedule

    Allows easy UI-based configuration of task timings
    """
    list_display = [
        'status_indicator',
        'get_task_name_display',
        'scheduled_time',
        'is_recurring_display',
        'days_display',
        'last_executed_display',
        'execution_count'
    ]
    list_filter = ['is_enabled', 'is_recurring', 'task_name']
    search_fields = ['display_name', 'description']
    readonly_fields = ['last_executed_at', 'execution_count', 'last_status', 'created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('task_name', 'display_name', 'description', 'is_enabled')
        }),
        ('Schedule Configuration', {
            'fields': ('scheduled_time', 'is_recurring', 'interval_minutes', 'start_time', 'end_time', 'days_of_week')
        }),
        ('Task Parameters', {
            'fields': ('task_parameters',),
            'classes': ('collapse',)
        }),
        ('Execution Tracking', {
            'fields': ('last_executed_at', 'execution_count', 'last_status', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_indicator(self, obj):
        """Show colored status indicator"""
        if obj.is_enabled:
            return format_html('<span style="color: green; font-size: 18px;">✓</span>')
        return format_html('<span style="color: red; font-size: 18px;">✗</span>')
    status_indicator.short_description = 'Status'

    def is_recurring_display(self, obj):
        """Display recurring status"""
        if obj.is_recurring:
            return format_html(
                '<span style="color: blue;">Every {} mins</span>',
                obj.interval_minutes or '?'
            )
        return format_html('<span style="color: gray;">One-time</span>')
    is_recurring_display.short_description = 'Type'

    def days_display(self, obj):
        """Display days of week"""
        if not obj.days_of_week:
            return 'All days'

        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        days = [day_names[d] for d in sorted(obj.days_of_week) if d < 7]
        return ', '.join(days) if days else 'All days'
    days_display.short_description = 'Days'

    def last_executed_display(self, obj):
        """Display last execution time"""
        if obj.last_executed_at:
            return obj.last_executed_at.strftime('%Y-%m-%d %H:%M')
        return '-'
    last_executed_display.short_description = 'Last Run'

    actions = ['enable_tasks', 'disable_tasks']

    def enable_tasks(self, request, queryset):
        """Enable selected tasks"""
        updated = queryset.update(is_enabled=True)
        self.message_user(request, f'{updated} task(s) enabled successfully.')
    enable_tasks.short_description = 'Enable selected tasks'

    def disable_tasks(self, request, queryset):
        """Disable selected tasks"""
        updated = queryset.update(is_enabled=False)
        self.message_user(request, f'{updated} task(s) disabled successfully.')
    disable_tasks.short_description = 'Disable selected tasks'


@admin.register(MarketOpeningState)
class MarketOpeningStateAdmin(admin.ModelAdmin):
    """Admin interface for market opening states"""
    list_display = [
        'trading_date',
        'gap_type_display',
        'gap_percent',
        'opening_sentiment',
        'is_substantial_movement',
        'vix_9_15'
    ]
    list_filter = ['gap_type', 'opening_sentiment', 'is_substantial_movement', 'is_expiry_day', 'is_event_day']
    search_fields = ['trading_date']
    readonly_fields = ['captured_at', 'updated_at_9_30', 'created_at', 'updated_at']

    fieldsets = (
        ('Trading Date', {
            'fields': ('trading_date', 'is_trading_day', 'is_expiry_day', 'is_event_day')
        }),
        ('Opening Prices (9:15 AM)', {
            'fields': ('prev_close', 'nifty_open', 'nifty_9_15_price', 'vix_9_15')
        }),
        ('Gap Analysis', {
            'fields': ('gap_points', 'gap_percent', 'gap_type', 'opening_sentiment')
        }),
        ('9:15 to 9:30 Movement', {
            'fields': (
                'nifty_9_30_price',
                'movement_9_15_to_9_30_points',
                'movement_9_15_to_9_30_percent',
                'is_substantial_movement'
            )
        }),
        ('Global Markets', {
            'fields': ('sgx_nifty_change', 'us_nasdaq_change', 'us_dow_change', 'sgx_correlation_accurate')
        }),
        ('Metadata', {
            'fields': ('captured_at', 'updated_at_9_30', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def gap_type_display(self, obj):
        """Display gap type with color"""
        colors = {
            'GAP_UP': 'green',
            'GAP_DOWN': 'red',
            'FLAT': 'gray'
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.gap_type, 'black'),
            obj.gap_type
        )
    gap_type_display.short_description = 'Gap Type'


@admin.register(SGXNiftyData)
class SGXNiftyDataAdmin(admin.ModelAdmin):
    """Admin interface for SGX Nifty data"""
    list_display = [
        'trading_date',
        'sgx_change_percent_display',
        'implied_gap_percent_display',
        'sgx_last_traded',
        'data_source'
    ]
    list_filter = ['data_source']
    search_fields = ['trading_date']
    readonly_fields = ['fetched_at', 'created_at', 'updated_at']

    def sgx_change_percent_display(self, obj):
        """Display SGX change with color"""
        if obj.sgx_change_percent is None:
            return '-'
        color = 'green' if obj.sgx_change_percent > 0 else 'red' if obj.sgx_change_percent < 0 else 'gray'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:+.2f}%</span>',
            color,
            obj.sgx_change_percent
        )
    sgx_change_percent_display.short_description = 'SGX Change'

    def implied_gap_percent_display(self, obj):
        """Display implied gap with color"""
        if obj.implied_gap_percent is None:
            return '-'
        color = 'green' if obj.implied_gap_percent > 0 else 'red' if obj.implied_gap_percent < 0 else 'gray'
        return format_html(
            '<span style="color: {};">{:+.2f}%</span>',
            color,
            obj.implied_gap_percent
        )
    implied_gap_percent_display.short_description = 'Implied Gap'


@admin.register(DailyTradingAnalysis)
class DailyTradingAnalysisAdmin(admin.ModelAdmin):
    """Admin interface for daily trading analysis"""
    list_display = [
        'trading_date',
        'total_pnl_display',
        'win_rate_display',
        'total_trades_entered',
        'market_regime',
        'notification_sent'
    ]
    list_filter = ['market_regime', 'notification_sent']
    search_fields = ['trading_date']
    readonly_fields = ['analysis_completed_at', 'created_at', 'updated_at']

    fieldsets = (
        ('Trading Date', {
            'fields': ('trading_date', 'market_regime')
        }),
        ('Market Summary', {
            'fields': ('nifty_open', 'nifty_high', 'nifty_low', 'nifty_close', 'nifty_change_percent', 'vix_open', 'vix_close', 'vix_change_percent')
        }),
        ('Trading Activity', {
            'fields': ('total_trades_entered', 'total_trades_exited', 'total_trades_open')
        }),
        ('Performance Metrics', {
            'fields': ('total_pnl', 'realized_pnl', 'unrealized_pnl', 'winning_trades', 'losing_trades', 'win_rate', 'capital_deployed', 'return_on_capital')
        }),
        ('Filter Analysis', {
            'fields': ('filters_run', 'filters_passed', 'filters_failed', 'filter_accuracy'),
            'classes': ('collapse',)
        }),
        ('Entry/Exit Analysis', {
            'fields': ('entry_timing_analysis', 'strike_selection_analysis', 'position_sizing_analysis', 'exit_timing_analysis', 'exit_reasons'),
            'classes': ('collapse',)
        }),
        ('Pattern Recognition', {
            'fields': ('successful_patterns', 'failed_patterns')
        }),
        ('Learning Insights', {
            'fields': ('key_learnings', 'recommendations', 'parameter_adjustments', 'overall_strategy_confidence', 'sgx_prediction_accuracy')
        }),
        ('Metadata', {
            'fields': ('analysis_completed_at', 'analysis_version', 'notification_sent', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def total_pnl_display(self, obj):
        """Display total P&L with color"""
        color = 'green' if obj.total_pnl > 0 else 'red' if obj.total_pnl < 0 else 'gray'
        return format_html(
            '<span style="color: {}; font-weight: bold;">₹{:,.0f}</span>',
            color,
            obj.total_pnl
        )
    total_pnl_display.short_description = 'Total P&L'

    def win_rate_display(self, obj):
        """Display win rate with color"""
        color = 'green' if obj.win_rate >= 60 else 'orange' if obj.win_rate >= 40 else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color,
            obj.win_rate
        )
    win_rate_display.short_description = 'Win Rate'


@admin.register(TradingInsight)
class TradingInsightAdmin(admin.ModelAdmin):
    """Admin interface for trading insights"""
    list_display = [
        'insight_type',
        'title',
        'trading_date',
        'confidence_score',
        'estimated_impact',
        'is_active'
    ]
    list_filter = ['insight_type', 'estimated_impact', 'is_active']
    search_fields = ['title', 'description']
    readonly_fields = ['times_validated', 'times_contradicted', 'created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('insight_type', 'title', 'description', 'trading_date', 'is_active')
        }),
        ('Insight Data', {
            'fields': ('insight_data',),
            'classes': ('collapse',)
        }),
        ('Validation & Confidence', {
            'fields': ('confidence_score', 'times_validated', 'times_contradicted', 'estimated_impact')
        }),
        ('Action', {
            'fields': ('action_recommended', 'action_taken', 'action_taken_at')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
