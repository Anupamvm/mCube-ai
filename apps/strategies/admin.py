from django.contrib import admin
from .models import StrategyConfig, StrategyLearning


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
