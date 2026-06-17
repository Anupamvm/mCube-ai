"""
URL configuration for brokers app
"""

from django.urls import path
from apps.brokers import views

app_name = 'brokers'

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('', views.broker_dashboard, name='dashboard'),

    # Kotak Neo URLs
    path('kotakneo/login/', views.kotakneo_login, name='kotakneo_login'),
    path('kotakneo/data/', views.kotakneo_data, name='kotakneo_data'),

    # Breeze URLs
    path('breeze/login/', views.breeze_login, name='breeze_login'),
    path('breeze/auto-login/', views.breeze_auto_login, name='breeze_auto_login'),
    path('breeze/update-credentials/', views.breeze_update_credentials, name='breeze_update_credentials'),
    path('breeze/session-status/', views.breeze_session_status, name='breeze_session_status'),
    path('breeze/otp-status/', views.breeze_otp_status, name='breeze_otp_status'),
    path('breeze/submit-otp/', views.breeze_submit_otp, name='breeze_submit_otp'),
    path('breeze/data/', views.breeze_data, name='breeze_data'),
    path('breeze/nifty-quote/', views.nifty_quote, name='nifty_quote'),
    path('breeze/option-chain/', views.breeze_option_chain, name='option_chain'),
    path('breeze/historical/', views.breeze_historical, name='historical'),

    # API endpoints
    path('api/positions/', views.api_positions, name='api_positions'),
    path('api/limits/', views.api_limits, name='api_limits'),

    # Future trade validation
    path('validate-future-trade/', views.validate_future_trade, name='validate_future_trade'),

    # Trade Sync
    path('trade-sync/', views.trade_sync_dashboard, name='trade_sync_dashboard'),
    path('api/sync-trades/', views.api_sync_trades, name='api_sync_trades'),
    path('api/sync-breeze-trades/', views.api_sync_breeze_trades, name='api_sync_breeze_trades'),
    path('api/sync-neo-trades/', views.api_sync_neo_trades, name='api_sync_neo_trades'),
    path('api/trade-sync-status/', views.api_trade_sync_status, name='api_trade_sync_status'),

    # CSV Upload
    path('csv-upload/', views.csv_upload_dashboard, name='csv_upload_dashboard'),
    path('api/upload-csv/', views.api_upload_csv, name='api_upload_csv'),
    path('api/delete-import/<str:batch_id>/', views.api_delete_import_batch, name='api_delete_import_batch'),
    path('api/import-logs/', views.api_import_logs, name='api_import_logs'),
    path('api/imported-pnl-summary/', views.api_imported_pnl_summary, name='api_imported_pnl_summary'),
]
