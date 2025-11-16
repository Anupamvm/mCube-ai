"""
Algorithm Testing Admin Configuration
"""

from django.contrib import admin
from .models import AlgoTestScenario, OptionsTestLog, FuturesTestLog, PositionMonitorSnapshot


@admin.register(AlgoTestScenario)
class AlgoTestScenarioAdmin(admin.ModelAdmin):
    list_display = ('name', 'strategy', 'user', 'created_at')
    list_filter = ('strategy', 'created_at', 'is_template')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(OptionsTestLog)
class OptionsTestLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'nifty_spot', 'india_vix', 'status', 'decision')
    list_filter = ('status', 'created_at', 'user')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


@admin.register(FuturesTestLog)
class FuturesTestLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'symbol', 'composite_score', 'status', 'decision')
    list_filter = ('status', 'created_at', 'user')
    search_fields = ('symbol', 'user__username')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


@admin.register(PositionMonitorSnapshot)
class PositionMonitorSnapshotAdmin(admin.ModelAdmin):
    list_display = ('position', 'current_time', 'unrealized_pnl', 'action')
    list_filter = ('created_at', 'action')
    readonly_fields = ('created_at',)
