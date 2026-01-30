"""
Analytics app URL configuration

Includes:
- Learning system URLs
- Pattern and suggestion management
- Legacy API endpoints
- Dashboard API endpoints
- ML insights API endpoints
- Export API endpoints
"""

from django.urls import path
from apps.analytics import views

app_name = 'analytics'

urlpatterns = [
    # ==========================================================================
    # DASHBOARD
    # ==========================================================================
    path('dashboard/', views.dashboard, name='dashboard'),

    # ==========================================================================
    # LEARNING CONTROL
    # ==========================================================================
    path('learning/', views.learning_dashboard, name='learning_dashboard'),
    path('learning/start/', views.start_learning, name='start_learning'),
    path('learning/<int:session_id>/stop/', views.stop_learning, name='stop_learning'),
    path('learning/<int:session_id>/pause/', views.pause_learning, name='pause_learning'),
    path('learning/<int:session_id>/resume/', views.resume_learning, name='resume_learning'),

    # ==========================================================================
    # PATTERNS
    # ==========================================================================
    path('patterns/', views.view_patterns, name='view_patterns'),
    path('patterns/<int:pattern_id>/', views.view_pattern_detail, name='view_pattern_detail'),

    # ==========================================================================
    # SUGGESTIONS
    # ==========================================================================
    path('suggestions/', views.view_suggestions, name='view_suggestions'),
    path('suggestions/<int:suggestion_id>/approve/', views.approve_suggestion, name='approve_suggestion'),
    path('suggestions/<int:suggestion_id>/reject/', views.reject_suggestion, name='reject_suggestion'),

    # ==========================================================================
    # API ENDPOINTS
    # ==========================================================================
    path('api/learning-status/', views.api_learning_status, name='api_learning_status'),
    path('api/performance-metrics/', views.api_performance_metrics, name='api_performance_metrics'),
    path('api/pnl-data/', views.api_pnl_data, name='api_pnl_data'),
    path('api/positions-data/', views.api_positions_data, name='api_positions_data'),

    # ==========================================================================
    # DASHBOARD API ENDPOINTS
    # ==========================================================================
    path('api/dashboard/summary/', views.api_dashboard_summary, name='api_dashboard_summary'),
    path('api/dashboard/pnl-chart/', views.api_pnl_chart_data, name='api_pnl_chart_data'),
    path('api/dashboard/cumulative-returns/', views.api_cumulative_returns, name='api_cumulative_returns'),
    path('api/dashboard/win-loss-distribution/', views.api_win_loss_distribution, name='api_win_loss_distribution'),
    path('api/dashboard/strategy-performance/', views.api_strategy_performance, name='api_strategy_performance'),
    path('api/dashboard/drawdown-chart/', views.api_drawdown_chart, name='api_drawdown_chart'),
    path('api/dashboard/heatmap/', views.api_performance_heatmap, name='api_performance_heatmap'),
    path('api/dashboard/best-worst-trades/', views.api_best_worst_trades, name='api_best_worst_trades'),
    path('api/dashboard/benchmark-comparison/', views.api_benchmark_comparison, name='api_benchmark_comparison'),

    # ==========================================================================
    # ML INSIGHTS API ENDPOINTS
    # ==========================================================================
    path('api/ml/decision-patterns/', views.api_decision_patterns, name='api_decision_patterns'),
    path('api/ml/recommendation-accuracy/', views.api_recommendation_accuracy, name='api_recommendation_accuracy'),

    # ==========================================================================
    # EXPORT API ENDPOINTS
    # ==========================================================================
    path('api/export/trades/', views.api_export_trades, name='api_export_trades'),
    path('api/export/ml-data/', views.api_export_ml_data, name='api_export_ml_data'),

    # ==========================================================================
    # FY TRADE ANALYTICS API ENDPOINTS
    # ==========================================================================
    path('api/fy/monthly-performance/', views.api_fy_monthly_performance, name='api_fy_monthly_performance'),
    path('api/fy/broker-breakdown/', views.api_fy_broker_breakdown, name='api_fy_broker_breakdown'),

    # ==========================================================================
    # BROKER TRADE ANALYTICS API ENDPOINTS
    # These endpoints use CSV imported contract data (BrokerContractPnL)
    # ==========================================================================
    path('api/broker/summary/', views.api_broker_trade_summary, name='api_broker_trade_summary'),
    path('api/broker/daily-pnl/', views.api_broker_daily_pnl, name='api_broker_daily_pnl'),
    path('api/broker/symbol-performance/', views.api_broker_symbol_performance, name='api_broker_symbol_performance'),
    path('api/broker/fy-summary/', views.api_broker_fy_summary, name='api_broker_fy_summary'),
    path('api/broker/monthly-summary/', views.api_broker_monthly_summary, name='api_broker_monthly_summary'),

    # ==========================================================================
    # SMART TRADING INTELLIGENCE API
    # Data scientist + trader perspective analysis with actionable conclusions
    # ==========================================================================
    path('api/smart-suggestions/', views.api_smart_suggestions, name='api_smart_suggestions'),
]
