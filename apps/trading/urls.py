"""
Trading URLs
"""

from django.urls import path
from . import views, api_views

app_name = 'trading'

urlpatterns = [
    # Manual Trade Triggers
    path('triggers/', views.manual_triggers, name='manual_triggers'),
    path('trigger/futures/', views.trigger_futures_algorithm, name='trigger_futures'),
    path('trigger/strangle/', views.trigger_nifty_strangle, name='trigger_strangle'),
    path('trigger/verify/', views.verify_future_trade, name='verify_trade'),
    path('trigger/get-contracts/', views.get_contracts, name='get_contracts'),
    path('trigger/refresh-trendlyne/', views.refresh_trendlyne_data, name='refresh_trendlyne'),
    path('trigger/update-breeze-session/', views.update_breeze_session, name='update_breeze_session'),
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
    path('api/get-lot-size/', api_views.get_lot_size, name='api_get_lot_size'),
    path('api/get-contract-details/', api_views.get_contract_details, name='api_get_contract_details'),

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
