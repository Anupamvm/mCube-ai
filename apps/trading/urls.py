"""
Trading URLs
"""

from django.urls import path
from . import views, api_views

app_name = 'trading'

urlpatterns = [
    # Manual Trade Triggers
    path('triggers/', views.manual_triggers_refactored, name='manual_triggers'),  # New refactored version (replaced old)
    path('triggers-old/', views.manual_triggers, name='manual_triggers_old'),  # Old version kept as backup
    path('view-trades/', views.view_trades, name='view_trades'),  # View active positions
    path('trigger/futures/', views.trigger_futures_algorithm, name='trigger_futures'),
    path('trigger/strangle/', views.trigger_nifty_strangle, name='trigger_strangle'),
    path('trigger/verify/', views.verify_future_trade, name='verify_trade'),
    path('trigger/get-contracts/', views.get_contracts, name='get_contracts'),
    path('trigger/start-trendlyne-fetch/', views.start_trendlyne_fetch, name='start_trendlyne_fetch'),
    path('trigger/trendlyne-logs/<str:session_id>/', views.stream_trendlyne_logs, name='stream_trendlyne_logs'),
    path('trigger/update-breeze-session/', views.update_breeze_session, name='update_breeze_session'),
    path('trigger/update-neo-session/', views.update_neo_session, name='update_neo_session'),
    path('trigger/calculate-position-sizing/', views.calculate_position_sizing, name='calculate_position_sizing'),
    path('trigger/execute-strangle/', views.execute_strangle_orders, name='execute_strangle'),

    # Position Sizing API Endpoints
    path('api/calculate-position/', api_views.calculate_position_sizing, name='api_calculate_position'),
    path('api/calculate-pnl/', api_views.calculate_pnl_scenarios, name='api_calculate_pnl'),
    path('api/place-futures-order/', api_views.place_futures_order, name='api_place_futures_order'),
    path('api/order-status/<str:order_id>/', api_views.check_order_status, name='api_check_order_status'),
    path('api/get-margins/', api_views.get_margin_data, name='api_get_margins'),

    # Trade Suggestions API Endpoints
    path('api/suggestions/', api_views.get_trade_suggestions, name='api_get_suggestions'),
    path('api/suggestions/<int:suggestion_id>/', api_views.get_suggestion_details, name='api_get_suggestion_details'),
    path('api/suggestions/update/', api_views.update_suggestion_status, name='api_update_suggestion'),
    path('api/suggestions/update-parameters/', api_views.update_suggestion_parameters, name='api_update_suggestion_parameters'),
    path('api/get-lot-size/', api_views.get_lot_size, name='api_get_lot_size'),
    path('api/get-contract-details/', api_views.get_contract_details, name='api_get_contract_details'),

    # Order Execution Control
    path('api/create-execution-control/', api_views.create_execution_control, name='api_create_execution_control'),
    path('api/cancel-execution/', api_views.cancel_execution, name='api_cancel_execution'),
    path('api/execution-progress/<int:suggestion_id>/', api_views.get_execution_progress, name='api_execution_progress'),

    # Option Chain Data
    path('api/get-option-premiums/', api_views.get_option_premiums, name='api_get_option_premiums'),

    # Active Positions Management
    path('api/get-positions/', api_views.get_active_positions, name='api_get_positions'),
    path('api/get-position-details/', api_views.get_position_details, name='api_get_position_details'),
    path('api/close-position/', api_views.close_position, name='api_close_position'),
    path('api/close-live-position/', api_views.close_live_position, name='api_close_live_position'),
    path('api/close-position-progress/<str:broker>/<path:symbol>/', api_views.get_close_position_progress, name='api_close_position_progress'),
    path('api/cancel-order-placement/', api_views.cancel_order_placement, name='api_cancel_order_placement'),
    path('api/analyze-averaging/', api_views.analyze_position_averaging, name='api_analyze_averaging'),

    # Manual Trade Execution (Live Orders)
    path('manual/prepare/', views.prepare_manual_execution, name='prepare_manual_execution'),
    path('manual/confirm/', views.confirm_manual_execution, name='confirm_manual_execution'),

    # Trade Suggestions
    path('suggestions/', views.pending_suggestions, name='pending_suggestions'),
    path('suggestion/<int:suggestion_id>/', views.suggestion_detail, name='suggestion_detail'),
    path('suggestion/<int:suggestion_id>/approve/', views.approve_suggestion, name='approve'),
    path('suggestion/<int:suggestion_id>/reject/', views.reject_suggestion, name='reject'),
    path('suggestion/<int:suggestion_id>/execute/', views.execute_suggestion, name='execute_suggestion'),
    path('suggestion/<int:suggestion_id>/confirm/', views.confirm_execution, name='confirm_execution'),

    # Auto-Trade Configuration
    path('config/auto-trade/', views.auto_trade_config, name='auto_trade_config'),

    # History and Export
    path('history/', views.suggestion_history, name='suggestion_history'),
    path('history/export/', views.export_suggestions_csv, name='export_csv'),
]
