"""
Dynamic Task Scheduler Service

Reads TradingScheduleConfig from database and dynamically
creates Celery Beat schedule. This allows UI-based configuration
of task timings without code changes.
"""

import logging
from datetime import datetime, time
from celery.schedules import crontab
from django.utils import timezone

from apps.strategies.models import TradingScheduleConfig

logger = logging.getLogger(__name__)


class DynamicScheduler:
    """
    Dynamic scheduler that builds Celery Beat schedule from database config
    """

    # Map task names to Celery task paths
    TASK_MAP = {
        'PREMARKET': 'apps.strategies.tasks_strangle.premarket_data_fetch',
        'MARKET_OPEN': 'apps.strategies.tasks_strangle.market_opening_validation',
        'TRADE_START': 'apps.strategies.tasks_strangle.trade_start_evaluation',
        'TRADE_MONITOR': 'apps.strategies.tasks_strangle.trade_monitoring',
        'TRADE_STOP': 'apps.strategies.tasks_strangle.trade_stop_evaluation',
        'DAY_CLOSE': 'apps.strategies.tasks_strangle.day_close_reconciliation',
        'ANALYZE_DAY': 'apps.strategies.tasks_strangle.analyze_day',
    }

    @classmethod
    def get_beat_schedule(cls):
        """
        Build Celery Beat schedule from database config

        Returns:
            dict: Celery Beat schedule dictionary
        """
        schedule = {}

        try:
            # Get all enabled schedule configs
            configs = TradingScheduleConfig.objects.filter(is_enabled=True)

            for config in configs:
                task_path = cls.TASK_MAP.get(config.task_name)
                if not task_path:
                    logger.warning(f"No task mapping for {config.task_name}")
                    continue

                if config.is_recurring:
                    # Recurring task (like monitoring)
                    schedule_key = f"{config.task_name.lower()}_recurring"
                    schedule[schedule_key] = cls._build_recurring_schedule(config, task_path)
                else:
                    # One-time daily task
                    schedule_key = f"{config.task_name.lower()}_daily"
                    schedule[schedule_key] = cls._build_daily_schedule(config, task_path)

            logger.info(f"Built dynamic schedule with {len(schedule)} tasks")

        except Exception as e:
            logger.error(f"Failed to build dynamic schedule: {e}", exc_info=True)
            # Return empty schedule on error
            schedule = {}

        return schedule

    @classmethod
    def _build_daily_schedule(cls, config: TradingScheduleConfig, task_path: str):
        """
        Build schedule for one-time daily task

        Args:
            config: TradingScheduleConfig instance
            task_path: Celery task path

        Returns:
            dict: Schedule configuration
        """
        scheduled_time = config.scheduled_time
        days_of_week = config.days_of_week or [0, 1, 2, 3, 4]  # Mon-Fri default

        # Convert days list to crontab format (e.g., "1-5" or "1,2,3")
        if days_of_week:
            if len(days_of_week) == 1:
                day_of_week = str(days_of_week[0])
            elif cls._is_consecutive(days_of_week):
                day_of_week = f"{min(days_of_week)}-{max(days_of_week)}"
            else:
                day_of_week = ','.join(map(str, days_of_week))
        else:
            day_of_week = '*'  # Every day

        # Build kwargs if any
        kwargs = config.task_parameters or {}

        return {
            'task': task_path,
            'schedule': crontab(
                hour=scheduled_time.hour,
                minute=scheduled_time.minute,
                day_of_week=day_of_week
            ),
            'kwargs': kwargs,
            'options': {'queue': 'strategies'},
        }

    @classmethod
    def _build_recurring_schedule(cls, config: TradingScheduleConfig, task_path: str):
        """
        Build schedule for recurring task (every N minutes)

        Args:
            config: TradingScheduleConfig instance
            task_path: Celery task path

        Returns:
            dict: Schedule configuration
        """
        interval_minutes = config.interval_minutes or 5
        start_time = config.start_time or time(9, 0)
        end_time = config.end_time or time(15, 30)
        days_of_week = config.days_of_week or [0, 1, 2, 3, 4]  # Mon-Fri default

        # Convert days list to crontab format
        if days_of_week:
            if len(days_of_week) == 1:
                day_of_week = str(days_of_week[0])
            elif cls._is_consecutive(days_of_week):
                day_of_week = f"{min(days_of_week)}-{max(days_of_week)}"
            else:
                day_of_week = ','.join(map(str, days_of_week))
        else:
            day_of_week = '*'

        # Build hour range (e.g., "9-15")
        if start_time.hour == end_time.hour:
            hour = str(start_time.hour)
        else:
            hour = f"{start_time.hour}-{end_time.hour}"

        # Build kwargs if any
        kwargs = config.task_parameters or {}

        return {
            'task': task_path,
            'schedule': crontab(
                hour=hour,
                minute=f'*/{interval_minutes}',
                day_of_week=day_of_week
            ),
            'kwargs': kwargs,
            'options': {'queue': 'monitoring'},
        }

    @classmethod
    def _is_consecutive(cls, numbers):
        """Check if list of numbers is consecutive"""
        if not numbers:
            return False
        numbers = sorted(numbers)
        return all(b - a == 1 for a, b in zip(numbers[:-1], numbers[1:]))

    @classmethod
    def create_default_schedule(cls):
        """
        Create default schedule configuration in database

        Call this once during setup to create initial schedule configs
        """
        defaults = [
            {
                'task_name': 'PREMARKET',
                'display_name': 'Pre-Market Data Fetch',
                'description': 'Fetch SGX Nifty, US markets, Trendlyne data, VIX before market opens',
                'scheduled_time': time(9, 0),
                'is_enabled': True,
                'is_recurring': False,
                'days_of_week': [0, 1, 2, 3, 4],  # Mon-Fri
                'task_parameters': {}
            },
            {
                'task_name': 'MARKET_OPEN',
                'display_name': 'Market Opening Validation',
                'description': 'Capture market opening state at 9:15 AM',
                'scheduled_time': time(9, 15),
                'is_enabled': True,
                'is_recurring': False,
                'days_of_week': [0, 1, 2, 3, 4],
                'task_parameters': {}
            },
            {
                'task_name': 'TRADE_START',
                'display_name': 'Trade Start Evaluation',
                'description': 'Evaluate strangle entries (9:40 AM - 10:15 AM window)',
                'scheduled_time': time(9, 40),
                'is_enabled': True,
                'is_recurring': True,
                'interval_minutes': 5,  # Check every 5 min during entry window
                'start_time': time(9, 40),
                'end_time': time(10, 15),
                'days_of_week': [0, 1, 2, 3, 4],  # All market days (Mon-Fri)
                'task_parameters': {}
            },
            {
                'task_name': 'TRADE_MONITOR',
                'display_name': 'Trade Monitoring (Delta, P&L)',
                'description': 'Monitor active positions (delta, P&L, targets) - Configurable via UI',
                'scheduled_time': time(9, 0),  # Start time
                'is_enabled': True,
                'is_recurring': True,
                'interval_minutes': 15,  # Changed from 5 to 15 minutes
                'start_time': time(9, 0),
                'end_time': time(15, 30),
                'days_of_week': [0, 1, 2, 3, 4],
                'task_parameters': {'delta_threshold': 300}  # Configurable delta alert threshold
            },
            {
                'task_name': 'TRADE_STOP',
                'display_name': 'Trade Stop/Exit',
                'description': 'Evaluate exit conditions daily if profit >= configured threshold (e.g., ₹10k)',
                'scheduled_time': time(15, 15),
                'is_enabled': True,
                'is_recurring': False,
                'days_of_week': [0, 1, 2, 3, 4],  # All market days (Mon-Fri)
                'task_parameters': {'profit_threshold': 10000}  # Configurable profit target
            },
            {
                'task_name': 'DAY_CLOSE',
                'display_name': 'Day Close Reconciliation',
                'description': 'End-of-day position updates and reconciliation',
                'scheduled_time': time(15, 30),
                'is_enabled': True,
                'is_recurring': False,
                'days_of_week': [0, 1, 2, 3, 4],
                'task_parameters': {}
            },
            {
                'task_name': 'ANALYZE_DAY',
                'display_name': 'Day Analysis & Learning',
                'description': 'Comprehensive day analysis for continuous improvement',
                'scheduled_time': time(15, 40),
                'is_enabled': True,
                'is_recurring': False,
                'days_of_week': [0, 1, 2, 3, 4],
                'task_parameters': {}
            },
        ]

        created_count = 0
        for default in defaults:
            _, created = TradingScheduleConfig.objects.get_or_create(
                task_name=default['task_name'],
                defaults=default
            )
            if created:
                created_count += 1
                logger.info(f"Created schedule config: {default['display_name']}")

        logger.info(f"Created {created_count} default schedule configurations")
        return created_count


def get_dynamic_beat_schedule():
    """
    Wrapper function to get dynamic beat schedule

    This is called by celery.py to build the beat schedule
    """
    return DynamicScheduler.get_beat_schedule()
