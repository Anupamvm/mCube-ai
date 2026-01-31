"""
URL configuration for core app
"""

from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # System Configuration (comprehensive settings page)
    path('configuration/', views.broker_settings, name='system_configuration'),
    path('broker-settings/', views.broker_settings, name='broker_settings'),  # Backward compatibility

    # Dashboard API
    path('api/dashboard/refresh/<str:stat_type>/', views.refresh_dashboard_stat, name='refresh_dashboard_stat'),

    # Testing
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

    # Background Tasks Control (Celery + Django Background Tasks)
    # Note: Using celery_task_control as background_tasks_control is not yet implemented
    path('background-tasks/', views.celery_task_control, name='background_tasks_control'),

    # Celery Task Control
    path('celery/', views.celery_task_control, name='celery_task_control'),
    path('celery/toggle/<int:task_id>/', views.toggle_celery_task, name='toggle_celery_task'),
    path('celery/toggle-static/', views.toggle_static_task, name='toggle_static_task'),
    path('celery/control-all/', views.celery_control_all, name='celery_control_all'),
    path('celery/control-all-static/', views.control_all_static_tasks, name='control_all_static_tasks'),
    path('celery/control-category/', views.control_category_tasks, name='control_category_tasks'),
    path('celery/task-logs/', views.get_task_logs, name='get_task_logs'),
    path('celery/all-logs/', views.get_all_celery_logs, name='get_all_celery_logs'),
    path('celery/reload/', views.reload_celery_schedule, name='reload_celery_schedule'),
    path('celery/config/', views.get_task_config, name='get_task_config'),
    path('celery/config/save/', views.save_task_config, name='save_task_config'),

    # Django Background Tasks Control
    path('bg-tasks/toggle/<int:task_id>/', views.toggle_bg_task, name='toggle_bg_task'),
    path('bg-tasks/control-all/', views.control_all_bg_tasks, name='control_all_bg_tasks'),
    path('bg-tasks/delete/<int:task_id>/', views.delete_bg_task, name='delete_bg_task'),
]
