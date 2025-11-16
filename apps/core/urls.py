"""
URL configuration for core app
"""

from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('test/', views.system_test_page, name='system_test'),
    path('test/trigger-trendlyne/', views.trigger_trendlyne_download, name='trigger_trendlyne'),
    path('test/trigger-fno-data/', views.trigger_fno_data_download, name='trigger_fno_data'),
    path('test/trigger-trendlyne-full/', views.trigger_trendlyne_full_cycle, name='trigger_trendlyne_full'),
    path('test/trigger-market-snapshot/', views.trigger_market_snapshot_download, name='trigger_market_snapshot'),
    path('test/trigger-forecaster/', views.trigger_forecaster_download, name='trigger_forecaster'),
    path('test/verify-kotak-login/', views.verify_kotak_login, name='verify_kotak_login'),
    path('test/verify-breeze-login/', views.verify_breeze_login, name='verify_breeze_login'),
    # Telegram test trigger endpoints
    path('test/trigger-telegram-simple/', views.trigger_telegram_simple, name='trigger_telegram_simple'),
    path('test/trigger-telegram-critical/', views.trigger_telegram_critical, name='trigger_telegram_critical'),
    path('test/trigger-telegram-sl-alert/', views.trigger_telegram_sl_alert, name='trigger_telegram_sl_alert'),
    path('test/trigger-telegram-target-alert/', views.trigger_telegram_target_alert, name='trigger_telegram_target_alert'),
    path('test/trigger-telegram-risk-alert/', views.trigger_telegram_risk_alert, name='trigger_telegram_risk_alert'),
    path('test/trigger-telegram-circuit-breaker/', views.trigger_telegram_circuit_breaker, name='trigger_telegram_circuit_breaker'),
    path('test/trigger-telegram-summary/', views.trigger_telegram_summary, name='trigger_telegram_summary'),
    path('docs/<str:doc_name>/', views.view_documentation, name='view_documentation'),
]
