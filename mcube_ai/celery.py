"""
Celery Configuration for mCube Trading System

This module configures Celery for asynchronous task execution and scheduled tasks.

Tasks include:
- Market data synchronization
- Position monitoring
- Strategy evaluation (entry/exit)
- Risk limit checks
- Delta monitoring
- Daily reports
"""

from __future__ import absolute_import, unicode_literals

import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')

# Create Celery application
app = Celery('mcube_ai')

# Load configuration from Django settings with 'CELERY' namespace
# This means all celery-related config keys should have 'CELERY_' prefix in settings.py
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed apps
# This will look for tasks.py in each app
app.autodiscover_tasks()


# Celery Beat Schedule - Automated Tasks
app.conf.beat_schedule = {
    # =========================================================================
    # MARKET DATA TASKS
    # =========================================================================

    'fetch-trendlyne-data-daily': {
        'task': 'apps.data.tasks.fetch_trendlyne_data',
        'schedule': crontab(hour=8, minute=30),  # 8:30 AM daily
        'options': {'queue': 'data'},
    },

    'import-trendlyne-data-daily': {
        'task': 'apps.data.tasks.import_trendlyne_data',
        'schedule': crontab(hour=9, minute=0),  # 9:00 AM daily
        'options': {'queue': 'data'},
    },

    'update-pre-market-data': {
        'task': 'apps.data.tasks.update_pre_market_data',
        'schedule': crontab(hour=8, minute=30, day_of_week='1-5'),  # Mon-Fri 8:30 AM
        'options': {'queue': 'data'},
    },

    'update-live-market-data': {
        'task': 'apps.data.tasks.update_live_market_data',
        'schedule': crontab(
            hour='9-15',
            minute='*/5',
            day_of_week='1-5'
        ),  # Every 5 min during market hours (9 AM - 3:30 PM), Mon-Fri
        'options': {'queue': 'data'},
    },

    'update-post-market-data': {
        'task': 'apps.data.tasks.update_post_market_data',
        'schedule': crontab(hour=15, minute=30, day_of_week='1-5'),  # Mon-Fri 3:30 PM
        'options': {'queue': 'data'},
    },

    # =========================================================================
    # KOTAK STRANGLE STRATEGY TASKS
    # =========================================================================

    'evaluate-kotak-strangle-entry': {
        'task': 'apps.strategies.tasks.evaluate_kotak_strangle_entry',
        'schedule': crontab(
            hour=10,
            minute=0,
            day_of_week='1,2'  # Monday, Tuesday only
        ),
        'options': {'queue': 'strategies'},
    },

    'evaluate-kotak-strangle-exit-thursday': {
        'task': 'apps.strategies.tasks.evaluate_kotak_strangle_exit',
        'schedule': crontab(
            hour=15,
            minute=15,
            day_of_week='4'  # Thursday
        ),
        'options': {'queue': 'strategies'},
    },

    'evaluate-kotak-strangle-exit-friday': {
        'task': 'apps.strategies.tasks.evaluate_kotak_strangle_exit',
        'schedule': crontab(
            hour=15,
            minute=15,
            day_of_week='5'  # Friday (mandatory exit)
        ),
        'options': {'queue': 'strategies', 'kwargs': {'mandatory': True}},
    },

    'monitor-strangle-delta': {
        'task': 'apps.strategies.tasks.monitor_all_strangle_deltas',
        'schedule': crontab(
            hour='9-15',
            minute='*/5',
            day_of_week='1-5'
        ),  # Every 5 min during market hours
        'options': {'queue': 'monitoring'},
    },

    # =========================================================================
    # ICICI FUTURES STRATEGY TASKS
    # =========================================================================

    'screen-futures-opportunities': {
        'task': 'apps.strategies.tasks.screen_futures_opportunities',
        'schedule': crontab(
            hour='9-14',
            minute='*/30',
            day_of_week='1-5'
        ),  # Every 30 min during market hours (9 AM - 2:30 PM)
        'options': {'queue': 'strategies'},
    },

    'check-futures-averaging': {
        'task': 'apps.strategies.tasks.check_futures_averaging',
        'schedule': crontab(
            hour='9-15',
            minute='*/10',
            day_of_week='1-5'
        ),  # Every 10 min during market hours
        'options': {'queue': 'monitoring'},
    },

    # =========================================================================
    # POSITION MONITORING TASKS
    # =========================================================================

    'monitor-all-positions': {
        'task': 'apps.positions.tasks.monitor_all_positions',
        'schedule': 10.0,  # Every 10 seconds during market hours
        'options': {'queue': 'monitoring'},
    },

    'update-position-pnl': {
        'task': 'apps.positions.tasks.update_position_pnl',
        'schedule': 15.0,  # Every 15 seconds
        'options': {'queue': 'monitoring'},
    },

    'check-exit-conditions': {
        'task': 'apps.positions.tasks.check_exit_conditions',
        'schedule': 30.0,  # Every 30 seconds
        'options': {'queue': 'monitoring'},
    },

    # =========================================================================
    # RISK MANAGEMENT TASKS
    # =========================================================================

    'check-risk-limits-all-accounts': {
        'task': 'apps.risk.tasks.check_risk_limits_all_accounts',
        'schedule': 60.0,  # Every 1 minute
        'options': {'queue': 'risk'},
    },

    'monitor-circuit-breakers': {
        'task': 'apps.risk.tasks.monitor_circuit_breakers',
        'schedule': 30.0,  # Every 30 seconds
        'options': {'queue': 'risk'},
    },

    # =========================================================================
    # REPORTING & ANALYTICS TASKS
    # =========================================================================

    'generate-daily-pnl-report': {
        'task': 'apps.analytics.tasks.generate_daily_pnl_report',
        'schedule': crontab(hour=16, minute=0, day_of_week='1-5'),  # 4:00 PM daily
        'options': {'queue': 'reports'},
    },

    'update-learning-patterns': {
        'task': 'apps.analytics.tasks.update_learning_patterns',
        'schedule': crontab(hour=17, minute=0, day_of_week='1-5'),  # 5:00 PM daily
        'options': {'queue': 'reports'},
    },

    'send-weekly-summary': {
        'task': 'apps.analytics.tasks.send_weekly_summary',
        'schedule': crontab(hour=18, minute=0, day_of_week='5'),  # Friday 6:00 PM
        'options': {'queue': 'reports'},
    },
}


# Task routing - distribute tasks across queues for better performance
app.conf.task_routes = {
    'apps.data.tasks.*': {'queue': 'data'},
    'apps.strategies.tasks.*': {'queue': 'strategies'},
    'apps.positions.tasks.*': {'queue': 'monitoring'},
    'apps.risk.tasks.*': {'queue': 'risk'},
    'apps.analytics.tasks.*': {'queue': 'reports'},
}


# Task execution settings
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Kolkata',  # Indian Standard Time
    enable_utc=False,

    # Task time limits
    task_time_limit=300,  # 5 minutes max (hard limit)
    task_soft_time_limit=240,  # 4 minutes (soft limit - raises exception)

    # Task result settings
    result_expires=3600,  # Results expire after 1 hour
    result_backend='redis://localhost:6379/1',  # Store results in Redis DB 1

    # Worker settings
    worker_prefetch_multiplier=4,  # Prefetch 4 tasks per worker
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks (prevent memory leaks)

    # Retry settings
    task_acks_late=True,  # Acknowledge task after execution (not before)
    task_reject_on_worker_lost=True,  # Reject task if worker dies
)


@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup"""
    print(f'Request: {self.request!r}')
