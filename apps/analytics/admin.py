from django.contrib import admin
from .models import (
    DailyPnL,
    Performance,
    LearningSession,
    TradePerformance,
    LearningPattern,
    ParameterAdjustment,
    PerformanceMetric,
)


@admin.register(DailyPnL)
class DailyPnLAdmin(admin.ModelAdmin):
    list_display = ['account', 'date', 'total_pnl', 'trades_count', 'winning_trades', 'losing_trades']
    list_filter = ['account']
    search_fields = ['account__account_name']
    date_hierarchy = 'date'


@admin.register(Performance)
class PerformanceAdmin(admin.ModelAdmin):
    list_display = ['account', 'period_type', 'period_start', 'period_end', 'total_pnl', 'win_rate']
    list_filter = ['account', 'period_type']
    search_fields = ['account__account_name']


@admin.register(LearningSession)
class LearningSessionAdmin(admin.ModelAdmin):
    list_display = ['name', 'status', 'started_at', 'stopped_at', 'trades_analyzed', 'patterns_discovered', 'parameters_adjusted']
    list_filter = ['status', 'started_at']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at', 'started_at', 'stopped_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'status', 'started_at', 'stopped_at')
        }),
        ('Configuration', {
            'fields': ('min_trades_required', 'confidence_threshold')
        }),
        ('Progress', {
            'fields': ('trades_analyzed', 'patterns_discovered', 'parameters_adjusted')
        }),
        ('Performance', {
            'fields': ('pre_learning_win_rate', 'post_learning_win_rate', 'improvement_pct')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TradePerformance)
class TradePerformanceAdmin(admin.ModelAdmin):
    list_display = ['position', 'entry_score', 'exit_score', 'entry_time_quality', 'hold_duration_minutes', 'created_at']
    list_filter = ['entry_time_quality', 'created_at']
    search_fields = ['position__symbol']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Position', {
            'fields': ('position',)
        }),
        ('Entry Analysis', {
            'fields': ('entry_conditions', 'entry_score', 'entry_time_quality')
        }),
        ('Exit Analysis', {
            'fields': ('exit_conditions', 'exit_score')
        }),
        ('Performance Metrics', {
            'fields': ('max_favorable_excursion', 'max_adverse_excursion', 'hold_duration_minutes')
        }),
        ('Insights', {
            'fields': ('what_worked', 'what_failed', 'lessons_learned')
        }),
        ('Pattern Matching', {
            'fields': ('similar_patterns_count', 'pattern_success_rate')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(LearningPattern)
class LearningPatternAdmin(admin.ModelAdmin):
    list_display = ['name', 'pattern_type', 'success_rate', 'confidence_score', 'occurrences', 'is_actionable', 'validation_status']
    list_filter = ['pattern_type', 'is_actionable', 'validation_status', 'session']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'last_validated']
    fieldsets = (
        ('Basic Information', {
            'fields': ('session', 'pattern_type', 'name', 'description')
        }),
        ('Pattern Definition', {
            'fields': ('conditions',)
        }),
        ('Statistics', {
            'fields': ('occurrences', 'profitable_occurrences', 'unprofitable_occurrences', 'success_rate')
        }),
        ('Financial Metrics', {
            'fields': ('avg_profit', 'avg_loss')
        }),
        ('Confidence & Recommendation', {
            'fields': ('confidence_score', 'is_actionable', 'recommendation')
        }),
        ('Validation', {
            'fields': ('validation_status', 'last_validated')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ParameterAdjustment)
class ParameterAdjustmentAdmin(admin.ModelAdmin):
    list_display = ['parameter_name', 'current_value', 'suggested_value', 'expected_improvement_pct', 'confidence', 'risk_level', 'status', 'reviewed_by']
    list_filter = ['status', 'risk_level', 'parameter_category', 'session']
    search_fields = ['parameter_name', 'reason']
    readonly_fields = ['created_at', 'updated_at', 'reviewed_at', 'applied_at']
    fieldsets = (
        ('Session', {
            'fields': ('session',)
        }),
        ('Parameter', {
            'fields': ('parameter_name', 'parameter_category', 'current_value', 'suggested_value')
        }),
        ('Analysis', {
            'fields': ('reason', 'supporting_data', 'expected_improvement_pct', 'confidence', 'risk_level')
        }),
        ('Review', {
            'fields': ('status', 'reviewed_by', 'reviewed_at', 'review_notes')
        }),
        ('Testing', {
            'fields': ('applied_at', 'test_start_date', 'test_end_date', 'actual_improvement_pct')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PerformanceMetric)
class PerformanceMetricAdmin(admin.ModelAdmin):
    list_display = ['metric_type', 'metric_value', 'strategy', 'time_period', 'session', 'calculation_date']
    list_filter = ['metric_type', 'session', 'calculation_date']
    search_fields = ['strategy', 'notes']
    readonly_fields = ['calculation_date']
    fieldsets = (
        ('Metric', {
            'fields': ('session', 'metric_type', 'metric_value')
        }),
        ('Context', {
            'fields': ('strategy', 'time_period')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('calculation_date',)
        }),
    )
