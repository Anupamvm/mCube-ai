"""
URL Configuration for Level 2 Deep-Dive Analysis API
"""

from django.urls import path
from apps.trading.views_level2 import (
    FuturesDeepDiveView,
    DeepDiveStatusView,
    DeepDiveDecisionView,
    TradeCloseView,
    DeepDiveHistoryView,
    PerformanceMetricsView
)

app_name = 'trading_level2'

urlpatterns = [
    # Generate deep-dive analysis (async with fresh data)
    path('futures/deep-dive/', FuturesDeepDiveView.as_view(), name='futures-deep-dive'),

    # Status checking (for polling)
    path('deep-dive/<int:analysis_id>/status/', DeepDiveStatusView.as_view(), name='deep-dive-status'),

    # Decision management
    path('deep-dive/<int:analysis_id>/decision/', DeepDiveDecisionView.as_view(), name='deep-dive-decision'),
    path('deep-dive/<int:analysis_id>/close/', TradeCloseView.as_view(), name='trade-close'),

    # History and performance
    path('deep-dive/history/', DeepDiveHistoryView.as_view(), name='deep-dive-history'),
    path('deep-dive/performance/', PerformanceMetricsView.as_view(), name='performance-metrics'),
]
