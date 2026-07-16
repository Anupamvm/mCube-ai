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

# macOS's Objective-C runtime aborts/crashes a forked child that touches
# certain frameworks (Security/Network, used transitively by libraries like
# curl_cffi — required by yfinance since Yahoo now blocks plain requests —
# and potentially other native deps in this project, e.g. Selenium for
# Breeze auto-login) after the parent process initialized them pre-fork.
# Celery's default 'prefork' pool forks a fresh worker per task, which is
# exactly the pattern that triggers this. This is Apple's own documented
# opt-out of that safety check; must be set before any worker forks.
if 'OBJC_DISABLE_INITIALIZE_FORK_SAFETY' not in os.environ:
    os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'

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
    # INFRASTRUCTURE HEALTH CHECKS
    # =========================================================================

    # Runs at 06:45 — 2+ hours before market open — so broker auth/network
    # issues can be fixed before trading begins.
    'health-check-brokers': {
        'task': 'apps.core.tasks.health_check_brokers',
        'schedule': crontab(hour=6, minute=45, day_of_week='1-5'),
        'options': {'queue': 'risk'},
    },

    # Checks overnight news for every open (carried-forward) position.
    # Fires 5 min before market open to give the trader time to react.
    'review-overnight-positions': {
        'task': 'apps.core.tasks.review_overnight_positions',
        'schedule': crontab(hour=8, minute=55, day_of_week='1-5'),
        'options': {'queue': 'monitoring'},
    },

    # Opening volatility sampling — runs every 5 min from 09:00 to 09:20.
    # Sets market_stable_for_trading Redis flag consumed by evaluate_options_strategy.
    'monitor-opening-volatility': {
        'task': 'apps.core.tasks.monitor_opening_volatility',
        'schedule': crontab(hour=9, minute='0,5,10,15,20', day_of_week='1-5'),
        'options': {'queue': 'monitoring'},
    },

    # Single consolidated morning briefing replaces scattered pre-market msgs.
    'send-morning-briefing': {
        'task': 'apps.core.tasks.send_morning_briefing',
        'schedule': crontab(hour=9, minute=0, day_of_week='1-5'),
        'options': {'queue': 'monitoring'},
    },

    # =========================================================================
    # MARKET DATA TASKS
    # =========================================================================

    'morning-data-sync': {
        'task': 'morning_data_sync',  # Uses custom name from @shared_task(name='morning_data_sync')
        'schedule': crontab(hour=7, minute=0, day_of_week='1-5'),  # 7:00 AM Mon-Fri
        'options': {'queue': 'data'},
    },

    'update-pre-market-data': {
        'task': 'update_pre_market_data',  # Uses custom name from @shared_task
        'schedule': crontab(hour=9, minute=10, day_of_week='1-5'),  # Mon-Fri 9:10 AM (after broker auto-login window)
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

    # OI Intelligence Engine — runs after import_trendlyne_data (9:00 AM) to
    # capture daily OI snapshots and generate multi-day pattern analysis.
    'process-oi-intelligence': {
        'task': 'process_oi_intelligence',
        'schedule': crontab(hour=9, minute=15, day_of_week='1-5'),  # Mon-Fri 9:15 AM
        'options': {'queue': 'data'},
    },

    # Exchange filings — NSE/BSE corporate announcements (3× daily)
    # Disabled by default via TASK_DEFAULT_CONFIG is_enabled=False
    # Enable via Task Control UI after staging validation.
    'fetch-exchange-filings-morning': {
        'task': 'fetch_exchange_filings',
        'schedule': crontab(hour=7, minute=30, day_of_week='1-5'),   # 7:30 AM IST
        'options': {'queue': 'data'},
    },
    'fetch-exchange-filings-midday': {
        'task': 'fetch_exchange_filings',
        'schedule': crontab(hour=12, minute=0, day_of_week='1-5'),   # 12:00 PM IST
        'options': {'queue': 'data'},
    },
    'fetch-exchange-filings-eod': {
        'task': 'fetch_exchange_filings',
        'schedule': crontab(hour=15, minute=45, day_of_week='1-5'),  # 3:45 PM IST
        'options': {'queue': 'data'},
    },

    # =========================================================================
    # STRATEGY EXECUTION TASKS - DAILY TRADING WORKFLOW
    # =========================================================================

    # Futures screening (9:40 AM) - after market stabilizes
    # Flow: Screen → Telegram confirmation → User confirms → Immediate execution
    'execute-futures-algorithm': {
        'task': 'apps.strategies.tasks.execute_futures_algorithm',
        'schedule': crontab(hour=9, minute=40, day_of_week='1-5'),  # 9:40 AM Mon-Fri
        'options': {'queue': 'strategies'},
        'kwargs': {
            'this_month_volume': 1000,
            'next_month_volume': 800,
            'min_score': 65,
            'top_contracts': 50,
            'batch_size': 3,  # Smaller batches = faster completion, less timeout risk
        },
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
            minute='0,5,10,15,20,25,30',
            day_of_week='1-5'
        ),  # Extended window until 10:30 AM
        'options': {'queue': 'strategies'},
    },

    'screen-futures-opportunities': {
        'task': 'apps.strategies.tasks.screen_futures_opportunities',
        'schedule': crontab(hour=9, minute=30, day_of_week='1-5'),  # 9:30 AM Mon-Fri (15 min after market open)
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
        'schedule': crontab(hour=15, minute=25, day_of_week='1-5'),  # 3:25 PM Mon-Fri (5 min buffer before close)
        'options': {'queue': 'strategies'},
    },

    # Strangle delta drift monitoring — every 15 min during market hours.
    # Task exists in apps/strategies/tasks.py but was missing from schedule.
    'monitor-all-strangle-deltas': {
        'task': 'apps.strategies.tasks.monitor_all_strangle_deltas',
        'schedule': crontab(hour='9-15', minute='*/15', day_of_week='1-5'),
        'options': {'queue': 'strategies'},
    },

    # Pre-close position alert — informs trader of open positions 10 min
    # before close_trading_day fires so they can make a conscious decision.
    'alert-open-positions-pre-close': {
        'task': 'apps.positions.tasks.alert_open_positions_pre_close',
        'schedule': crontab(hour=15, minute=15, day_of_week='1-5'),
        'options': {'queue': 'monitoring'},
    },

    # EOD reconciliation — syncs broker state and reports open positions
    # after market close. Runs AFTER close_trading_day (15:25) and
    # update_post_market_data (15:35) have had time to complete.
    'reconcile-positions-eod': {
        'task': 'apps.positions.tasks.reconcile_positions_eod',
        'schedule': crontab(hour=15, minute=45, day_of_week='1-5'),
        'options': {'queue': 'monitoring'},
    },

    # =========================================================================
    # TRADE CONFIRMATION TASKS
    # =========================================================================

    'check-confirmation-timeouts': {
        'task': 'apps.trading.tasks.check_confirmation_timeouts',
        'schedule': crontab(
            hour='9-15',
            minute='*',
            day_of_week='1-5'
        ),  # Every minute 9 AM - 3 PM Mon-Fri
        'options': {'queue': 'monitoring'},
    },

    # =========================================================================
    # POSITION MONITORING TASKS
    # =========================================================================

    'monitor-and-manage-positions': {
        'task': 'apps.positions.tasks.monitor_and_manage_positions',
        'schedule': crontab(hour='9-14', minute='*', day_of_week='1-5'),  # Every minute 9 AM-2:59 PM Mon-Fri
        'options': {'queue': 'monitoring'},
    },
    'monitor-and-manage-positions-close': {
        'task': 'apps.positions.tasks.monitor_and_manage_positions',
        # Every minute 3:00-3:30 PM Mon-Fri — stops at NSE market close (3:30 PM),
        # unlike the old hour='9-15' entry which kept firing until 3:59 PM.
        'schedule': crontab(hour=15, minute='0-30', day_of_week='1-5'),
        'options': {'queue': 'monitoring'},
    },

    # =========================================================================
    # RISK MANAGEMENT TASKS
    # =========================================================================

    'check-risk-limits-all-accounts': {
        'task': 'apps.risk.tasks.check_risk_limits_all_accounts',
        'schedule': crontab(hour='9-15', minute='*', day_of_week='1-5'),  # Every minute 9 AM-3:59 PM Mon-Fri
        'options': {'queue': 'risk'},
    },

    'monitor-circuit-breakers': {
        'task': 'apps.risk.tasks.monitor_circuit_breakers',
        'schedule': crontab(hour='9-15', minute='*', day_of_week='1-5'),  # Every minute 9 AM-3:59 PM Mon-Fri
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
        'schedule': crontab(hour=16, minute=15, day_of_week='1-5'),  # 4:15 PM Mon-Fri
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

    # =========================================================================
    # HINDSIGHT TRACKER — What-If Analysis
    # =========================================================================

    # Morning: fetch opening prices for today's pending checkpoints
    'seed-hindsight-opening-prices': {
        'task': 'apps.analytics.tasks.seed_hindsight_opening_prices',
        'schedule': crontab(hour=9, minute=20, day_of_week='1-5'),  # 9:20 AM Mon-Fri
        'options': {'queue': 'reports'},
    },

    # EOD: fill OHLC data for all due checkpoints
    'update-hindsight-checkpoints': {
        'task': 'apps.analytics.tasks.update_hindsight_checkpoints',
        'schedule': crontab(hour=15, minute=50, day_of_week='1-5'),  # 3:50 PM Mon-Fri
        'options': {'queue': 'reports'},
    },

    # Early morning digest: summarize yesterday's hindsight updates on Telegram
    'send-hindsight-morning-digest': {
        'task': 'apps.analytics.tasks.send_hindsight_morning_digest',
        'schedule': crontab(hour=8, minute=30, day_of_week='1-5'),  # 8:30 AM Mon-Fri
        'options': {'queue': 'monitoring'},
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


def _build_custom_schedule(task_state):
    """
    Build a Celery schedule object from CeleryTaskState custom configuration.

    Args:
        task_state: CeleryTaskState instance with use_custom_schedule=True

    Returns:
        A crontab, float (interval seconds), or the original schedule if custom is not applicable.
    """
    days = task_state.days_of_week
    if days:
        # Convert [0,1,2,3,4] (Mon=0) to celery crontab format (Mon=1, Sun=0)
        celery_days = ','.join(str(d + 1) if d < 6 else '0' for d in sorted(days))
    else:
        celery_days = '1-5'  # Default to weekdays

    if task_state.schedule_type == 'crontab':
        return crontab(
            hour=task_state.schedule_hour,
            minute=task_state.schedule_minute,
            day_of_week=celery_days,
        )
    elif task_state.schedule_type == 'interval':
        # Convert interval to a time-bounded crontab to prevent 24/7 execution.
        # Uses recurring_start_hour/end_hour fields for time bounds.
        # Sub-minute intervals are rounded up to 1 minute (crontab minimum).
        start_h = task_state.recurring_start_hour
        end_h = task_state.recurring_end_hour
        interval_mins = max(1, task_state.interval_seconds // 60)
        return crontab(
            hour=f'{start_h}-{end_h}',
            minute=f'*/{interval_mins}' if interval_mins > 1 else '*',
            day_of_week=celery_days,
        )
    elif task_state.schedule_type == 'recurring':
        # Build crontab(s) that run every N minutes within a precise time window.
        # A single crontab uses cartesian product of hours x minutes, so when
        # the start/end minutes differ across hours (e.g. 9:40-10:15) we must
        # return multiple crontabs—one per hour with its own minute set.
        from collections import defaultdict

        start_h = task_state.recurring_start_hour
        start_m = getattr(task_state, 'recurring_start_minute', 0) or 0
        end_h = task_state.recurring_end_hour
        end_m = getattr(task_state, 'recurring_end_minute', 59) or 59
        interval = max(1, task_state.recurring_interval_minutes)

        # Compute all exact fire times as (hour, minute) pairs
        fire_times = []
        current_total = start_h * 60 + start_m
        end_total = end_h * 60 + end_m

        while current_total <= end_total:
            h = current_total // 60
            m = current_total % 60
            fire_times.append((h, m))
            current_total += interval

        if not fire_times:
            fire_times = [(start_h, start_m)]

        # Group fire times by hour
        hour_minutes = defaultdict(list)
        for h, m in fire_times:
            hour_minutes[h].append(m)

        # Check if all hours share the same minute set (single crontab is fine)
        minute_sets = [tuple(sorted(mins)) for mins in hour_minutes.values()]
        if len(set(minute_sets)) == 1:
            hours = sorted(hour_minutes.keys())
            minutes = sorted(hour_minutes[hours[0]])
            return crontab(
                hour=','.join(str(h) for h in hours),
                minute=','.join(str(m) for m in minutes),
                day_of_week=celery_days,
            )
        else:
            # Different hours need different minute sets — return a dict
            # keyed by suffix so load_beat_schedule can create multiple entries
            result = {}
            for h in sorted(hour_minutes.keys()):
                mins = sorted(hour_minutes[h])
                result[f'-{h}h'] = crontab(
                    hour=str(h),
                    minute=','.join(str(m) for m in mins),
                    day_of_week=celery_days,
                )
            return result

    return None


def load_beat_schedule():
    """
    Load beat schedule dynamically from database.

    Combines static tasks (data tasks) with dynamic strategy tasks.
    Only includes tasks that are explicitly enabled in CeleryTaskState.
    Tasks are disabled by default - users must enable them via UI.

    When a task has use_custom_schedule=True in CeleryTaskState, the custom
    schedule configuration (hour, minute, interval, days) overrides the
    static defaults from get_static_schedule().

    This is used by Celery Beat to determine which tasks to run.
    """
    all_tasks = get_all_tasks_for_display()

    # Filter out disabled tasks
    # Note: Tasks are disabled by default. Only enabled tasks will run.
    try:
        from apps.core.models import CeleryTaskState

        # Initialize any missing tasks in the database (as disabled)
        CeleryTaskState.initialize_static_tasks(all_tasks, force=False)

        enabled_keys = CeleryTaskState.get_enabled_task_keys()

        # Build a lookup of all task states for custom schedule application
        task_states = {s.task_key: s for s in CeleryTaskState.objects.all()}

        # Filter schedule to only include enabled tasks
        # and apply custom schedules where configured
        filtered_schedule = {}
        for key, config in all_tasks.items():
            # Check if this is a dynamic task (managed by TradingScheduleConfig)
            is_dynamic = any(d in key.lower() for d in [
                'premarket', 'market_open', 'trade_start',
                'trade_monitor', 'trade_stop', 'day_close', 'analyze_day'
            ])

            if is_dynamic:
                # Dynamic tasks are controlled by TradingScheduleConfig.is_enabled
                # which is already checked in get_dynamic_beat_schedule()
                filtered_schedule[key] = config
            elif key in enabled_keys:
                # Static task is enabled - check for custom schedule
                task_state = task_states.get(key)
                if task_state and task_state.use_custom_schedule:
                    custom_schedule = _build_custom_schedule(task_state)
                    if isinstance(custom_schedule, dict):
                        # Recurring window spanning hours with different minute sets
                        # — create multiple schedule entries (e.g. key-9h, key-10h)
                        for suffix, sched in custom_schedule.items():
                            entry_config = config.copy()
                            entry_config['schedule'] = sched
                            filtered_schedule[f"{key}{suffix}"] = entry_config
                        continue
                    elif custom_schedule is not None:
                        config = config.copy()
                        config['schedule'] = custom_schedule
                filtered_schedule[key] = config
            # If not in enabled_keys, task is disabled and excluded from schedule

        import logging
        logger = logging.getLogger(__name__)
        custom_count = sum(
            1 for k in filtered_schedule
            if task_states.get(k) and task_states[k].use_custom_schedule
        )
        logger.info(
            f"Loaded beat schedule: {len(filtered_schedule)} tasks enabled "
            f"out of {len(all_tasks)} total ({custom_count} with custom schedules)"
        )

        return filtered_schedule

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not filter disabled tasks: {e}. Loading all tasks.")
        return all_tasks


# Set initial beat schedule to static defaults.
# The DBReloadScheduler below will reload from DB once Django is ready.
app.conf.beat_schedule = get_static_schedule()


# Custom scheduler that reloads schedule from DB after Django is ready
from celery.beat import PersistentScheduler

class DBReloadScheduler(PersistentScheduler):
    """PersistentScheduler that reloads schedule from DB on setup."""

    def setup_schedule(self):
        import logging
        _logger = logging.getLogger(__name__)
        try:
            import django
            django.setup()
            schedule = load_beat_schedule()
            app.conf.beat_schedule = schedule
            _logger.info(f"Beat schedule reloaded from DB: {len(schedule)} tasks")
        except Exception as exc:
            _logger.warning(f"Could not reload beat schedule from DB: {exc}")
        super().setup_schedule()


# Register DBReloadScheduler as the default beat scheduler
# so it works regardless of how celery beat is started
app.conf.beat_scheduler = 'mcube_ai.celery:DBReloadScheduler'


# Task routing - distribute tasks across queues for better performance
app.conf.task_routes = {
    'apps.core.tasks.*': {'queue': 'risk'},
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
