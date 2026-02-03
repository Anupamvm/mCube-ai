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


# =============================================================================
# DYNAMIC SCHEDULE LOADING
# =============================================================================
# Schedule is loaded dynamically from TradingScheduleConfig model
# This allows UI-based configuration without code changes

def get_static_schedule():
    """
    Returns the static schedule dictionary (all tasks, regardless of enabled state).
    Used by UI to display all available tasks.
    """
    return {
    # =========================================================================
    # MARKET DATA TASKS
    # =========================================================================

    'morning-data-sync': {
        'task': 'morning_data_sync',  # Uses custom name from @shared_task(name='morning_data_sync')
        'schedule': crontab(hour=7, minute=0),  # 7:00 AM daily - full morning data sync
        'options': {'queue': 'data'},
    },

    'update-pre-market-data': {
        'task': 'update_pre_market_data',  # Uses custom name from @shared_task
        'schedule': crontab(hour=8, minute=50, day_of_week='1-5'),  # Mon-Fri 8:50 AM
        'options': {'queue': 'data'},
    },

    'update-live-market-data': {
        'task': 'update_live_market_data',  # Uses custom name from @shared_task
        'schedule': crontab(hour=9, minute=15, day_of_week='1-5'),  # Mon-Fri 9:15 AM (market open)
        'options': {'queue': 'data'},
    },

    'update-post-market-data': {
        'task': 'update_post_market_data',  # Uses custom name from @shared_task
        'schedule': crontab(hour=15, minute=35, day_of_week='1-5'),  # Mon-Fri 3:35 PM (after close)
        'options': {'queue': 'data'},
    },

    # =========================================================================
    # STRATEGY EXECUTION TASKS - DAILY TRADING WORKFLOW
    # =========================================================================

    # Pre-market futures screening (8:30 AM)
    'execute-futures-algorithm': {
        'task': 'apps.strategies.tasks.execute_futures_algorithm',
        'schedule': crontab(hour=8, minute=30, day_of_week='1-5'),  # 8:30 AM Mon-Fri
        'options': {'queue': 'strategies'},
        'kwargs': {'this_month_volume': 1000, 'next_month_volume': 800, 'min_score': 65},
    },

    'setup-trading-day': {
        'task': 'apps.strategies.tasks.setup_trading_day',
        'schedule': crontab(hour=8, minute=55, day_of_week='1-5'),  # 8:55 AM Mon-Fri
        'options': {'queue': 'strategies'},
    },

    'start-trading-day': {
        'task': 'apps.strategies.tasks.start_trading_day',
        'schedule': crontab(hour=9, minute=15, day_of_week='1-5'),  # 9:15 AM Mon-Fri
        'options': {'queue': 'strategies'},
    },

    'evaluate-options-strategy': {
        'task': 'apps.strategies.tasks.evaluate_options_strategy',
        'schedule': crontab(hour=9, minute=30, day_of_week='1-5'),  # 9:30 AM Mon-Fri
        'options': {'queue': 'strategies'},
    },

    'start-options-trade': {
        'task': 'apps.strategies.tasks.start_options_trade',
        'schedule': crontab(hour=9, minute=40, day_of_week='1-5'),  # 9:40 AM Mon-Fri
        'options': {'queue': 'strategies'},
    },

    'batch-options-averaging': {
        'task': 'apps.strategies.tasks.batch_options_averaging',
        'schedule': crontab(
            hour=9,
            minute='40,45,50,55',
            day_of_week='1-5'
        ),  # Every 5 min from 9:40-10:15 AM
        'options': {'queue': 'strategies'},
    },

    'batch-options-averaging-10am': {
        'task': 'apps.strategies.tasks.batch_options_averaging',
        'schedule': crontab(
            hour=10,
            minute='0,5,10,15',
            day_of_week='1-5'
        ),  # Continue until 10:15 AM
        'options': {'queue': 'strategies'},
    },

    'screen-futures-opportunities': {
        'task': 'apps.strategies.tasks.screen_futures_opportunities',
        'schedule': crontab(hour=9, minute=45, day_of_week='1-5'),  # 9:45 AM Mon-Fri
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

    'close-trading-day': {
        'task': 'apps.strategies.tasks.close_trading_day',
        'schedule': crontab(hour=15, minute=25, day_of_week='1-5'),  # 3:25 PM Mon-Fri
        'options': {'queue': 'strategies'},
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
        'schedule': crontab(hour=16, minute=0, day_of_week='1-5'),  # 4:00 PM Mon-Fri
        'options': {'queue': 'reports'},
    },

    'sync-benchmark-data': {
        'task': 'apps.analytics.tasks.sync_benchmark_data',
        'schedule': crontab(hour=16, minute=0, day_of_week='1-5'),  # 4:00 PM Mon-Fri
        'options': {'queue': 'reports'},
    },

    'daily-data-aggregation': {
        'task': 'apps.analytics.tasks.daily_data_aggregation',
        'schedule': crontab(hour=16, minute=30, day_of_week='1-5'),  # 4:30 PM Mon-Fri
        'options': {'queue': 'reports'},
    },

    'update-equity-curves': {
        'task': 'apps.analytics.tasks.update_equity_curves',
        'schedule': crontab(hour=17, minute=0, day_of_week='1-5'),  # 5:00 PM Mon-Fri
        'options': {'queue': 'reports'},
    },
}


def get_all_tasks_for_display():
    """
    Get ALL tasks (static + dynamic) for UI display.
    Returns all tasks regardless of enabled/disabled state.
    """
    from apps.strategies.services.dynamic_scheduler import get_dynamic_beat_schedule

    all_tasks = get_static_schedule().copy()

    # Load dynamic schedule from database
    try:
        dynamic_schedule = get_dynamic_beat_schedule()
        all_tasks.update(dynamic_schedule)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to load dynamic schedule: {e}")

    return all_tasks


def load_beat_schedule():
    """
    Load beat schedule dynamically from database.

    Combines static tasks (data tasks) with dynamic strategy tasks.
    Only includes tasks that are explicitly enabled in CeleryTaskState.
    Tasks are disabled by default - users must enable them via UI.

    This is used by Celery Beat to determine which tasks to run.
    """
    all_tasks = get_all_tasks_for_display()

    # Filter out disabled tasks
    # Note: Tasks are disabled by default. Only enabled tasks will run.
    try:
        from apps.core.models import CeleryTaskState
        enabled_keys = CeleryTaskState.get_enabled_task_keys()

        # Initialize any missing tasks in the database (as disabled)
        CeleryTaskState.initialize_static_tasks(all_tasks, force=False)

        # Filter schedule to only include enabled tasks
        filtered_schedule = {}
        for key, config in all_tasks.items():
            # Skip dynamic tasks (those managed by TradingScheduleConfig)
            if any(d in key.lower() for d in ['premarket', 'market_open', 'trade_start', 'trade_monitor', 'trade_stop', 'day_close', 'analyze_day']):
                # Dynamic tasks are controlled by TradingScheduleConfig.is_enabled
                filtered_schedule[key] = config
            elif key in enabled_keys:
                filtered_schedule[key] = config
            # If not in enabled_keys, task is disabled and excluded from schedule

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Loaded beat schedule: {len(filtered_schedule)} tasks enabled out of {len(all_tasks)} total")

        return filtered_schedule

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not filter disabled tasks: {e}. Loading all tasks.")
        return all_tasks


# Load beat schedule
# Wrap in try-except to handle module load before Django is fully initialized
try:
    app.conf.beat_schedule = load_beat_schedule()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Could not load beat schedule at startup: {e}. Using static schedule.")
    app.conf.beat_schedule = get_static_schedule()


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
