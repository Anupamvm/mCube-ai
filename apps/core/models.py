"""
Core models for mCube Trading System

This module contains abstract base models that are inherited by other apps.
Also contains trading configuration and runtime state models.
"""

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import datetime as dt
import pytz

IST = pytz.timezone('Asia/Kolkata')


class TimeStampedModel(models.Model):
    """
    Abstract base model with automatic timestamp fields

    All models in the system should inherit from this class to ensure
    consistent tracking of creation and modification times.

    Fields:
        created_at: Automatically set when the record is created
        updated_at: Automatically updated whenever the record is modified

    Meta:
        abstract: True (this model won't create a database table)
        ordering: Records ordered by creation time (newest first)
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the record was created"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the record was last updated"
    )

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.__class__.__name__} - {self.created_at}"


class CredentialStore(models.Model):
    """
    Secure storage for API credentials and authentication tokens

    Stores credentials for various external services like brokers, data providers, etc.
    """

    SERVICE_CHOICES = [
        ('breeze', 'ICICI Breeze'),
        ('trendlyne', 'Trendlyne'),
        ('kotakneo', 'Kotak Neo'),
        ('telegram', 'Telegram Bot'),
        ('gnewsio', 'GNews.io'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=100, default="default")
    service = models.CharField(max_length=50, choices=SERVICE_CHOICES)

    # API credentials
    api_key = models.CharField(max_length=256, null=True, blank=True)
    api_secret = models.CharField(max_length=256, null=True, blank=True)
    session_token = models.CharField(max_length=512, null=True, blank=True)

    # Username/password credentials
    username = models.CharField(max_length=150, null=True, blank=True)
    password = models.CharField(max_length=150, null=True, blank=True)

    # Additional fields for specific services
    pan = models.CharField(max_length=20, null=True, blank=True)  # PAN number
    neo_password = models.CharField(max_length=100, null=True, blank=True)  # Kotak Neo password
    sid = models.CharField(max_length=256, null=True, blank=True)  # Session ID

    # Kotak Neo persisted session fields (for session reuse without re-login)
    neo_edit_token = models.TextField(null=True, blank=True)
    neo_edit_sid = models.CharField(max_length=256, null=True, blank=True)
    neo_server_id = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_session_update = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'credential_store'
        unique_together = ['service', 'name']

    def __str__(self):
        return f"{self.get_service_display()} - {self.name}"


class TradingSchedule(models.Model):
    """
    Daily trading schedule configuration

    Allows customizing trading times for each day.
    Tasks will use these times to schedule intraday operations.
    """

    date = models.DateField(unique=True, help_text="Trading date")

    # Market timings
    open_time = models.TimeField(
        default=dt.time(9, 15, 10),
        help_text="Market open / setup task time"
    )
    take_trade_time = models.TimeField(
        default=dt.time(9, 30, 0),
        help_text="Start taking trades"
    )
    last_trade_time = models.TimeField(
        default=dt.time(10, 15, 0),
        help_text="Last time to enter new trades"
    )
    close_pos_time = models.TimeField(
        default=dt.time(15, 25, 30),
        help_text="Start closing positions"
    )
    mkt_close_time = models.TimeField(
        default=dt.time(15, 32, 0),
        help_text="Market close time"
    )
    close_day_time = models.TimeField(
        default=dt.time(15, 45, 0),
        help_text="End-of-day analysis time"
    )

    enabled = models.BooleanField(
        default=True,
        help_text="Enable trading for this day"
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        help_text="Notes about this trading day"
    )

    class Meta:
        db_table = 'trading_schedule'
        ordering = ['-date']

    def __str__(self):
        return f"TradingSchedule({self.date}) - {'Enabled' if self.enabled else 'Disabled'}"

    def as_datetimes(self, tz=None):
        """
        Convert time fields to timezone-aware datetimes

        Args:
            tz: pytz timezone (defaults to IST)

        Returns:
            dict with datetime objects for each time field
        """
        if tz is None:
            tz = IST

        def at(t):
            return tz.localize(dt.datetime.combine(self.date, t))

        return {
            't_open': at(self.open_time),
            't_take_trade': at(self.take_trade_time),
            't_last_trade': at(self.last_trade_time),
            't_close_pos': at(self.close_pos_time),
            't_mkt_close': at(self.mkt_close_time),
            't_close_day': at(self.close_day_time),
        }


class NseFlag(models.Model):
    """
    Runtime configuration flags and state variables

    Key-value store for trading parameters, market conditions, and system state.
    Used by background tasks to make decisions and store intermediate values.

    Common flags:
    - isDayTradable: Whether it's safe to trade today
    - nseVix: VIX value and status
    - openPositions: Current open position count
    - dailyDelta: Daily volatility target
    - currentPos: Current P&L
    """

    flag = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Flag name (key)"
    )
    value = models.CharField(
        max_length=200,
        blank=True,
        help_text="Flag value (stored as string)"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this flag represents"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nse_flag'
        ordering = ['flag']

    def __str__(self):
        return f"{self.flag} = {self.value}"

    # ========== Helper Methods ==========

    @staticmethod
    def get(name: str, default: str = "") -> str:
        """Get flag value, return default if not found"""
        try:
            return NseFlag.objects.get(flag=name).value
        except NseFlag.DoesNotExist:
            return default

    @staticmethod
    def set(name: str, value: str, description: str = ""):
        """Set flag value, create if doesn't exist"""
        obj, created = NseFlag.objects.update_or_create(
            flag=name,
            defaults={'value': str(value), 'description': description}
        )
        return obj

    @staticmethod
    def get_bool(name: str, default: bool = False) -> bool:
        """Get flag as boolean"""
        raw = NseFlag.get(name, str(default))
        return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def get_float(name: str, default: float = 0.0) -> float:
        """Get flag as float"""
        try:
            return float(NseFlag.get(name, str(default)))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_int(name: str, default: int = 0) -> int:
        """Get flag as integer"""
        try:
            return int(NseFlag.get(name, str(default)))
        except (ValueError, TypeError):
            return default


class BkLog(models.Model):
    """
    Background task execution logs

    Stores logs from all background tasks for monitoring and debugging.
    Enhanced with additional metadata and context for better debugging.
    """

    LEVEL_CHOICES = [
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]

    TASK_CATEGORY_CHOICES = [
        ('data', 'Market Data'),
        ('strategy', 'Strategy Execution'),
        ('transaction', 'Transactions'),
        ('position', 'Position Monitoring'),
        ('risk', 'Risk Management'),
        ('analytics', 'Analytics & Reports'),
        ('other', 'Other'),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='info')
    action = models.CharField(max_length=100, help_text="Action/function name")
    message = models.TextField(help_text="Log message")
    background_task = models.CharField(
        max_length=100,
        blank=True,
        help_text="Background task name"
    )

    # Enhanced fields for better tracking
    task_category = models.CharField(
        max_length=20,
        choices=TASK_CATEGORY_CHOICES,
        default='other',
        help_text="Category of the task",
        db_index=True
    )

    task_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Celery task ID for correlation",
        db_index=True
    )

    execution_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Execution time in milliseconds"
    )

    context_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context data (symbols, counts, metrics, etc.)"
    )

    error_details = models.TextField(
        blank=True,
        help_text="Full error traceback if error occurred"
    )

    success = models.BooleanField(
        default=True,
        help_text="Whether the task completed successfully"
    )

    class Meta:
        db_table = 'bk_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp', 'level']),
            models.Index(fields=['background_task']),
            models.Index(fields=['task_category', '-timestamp']),
            models.Index(fields=['success', '-timestamp']),
            models.Index(fields=['task_id']),
        ]

    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"[{self.timestamp}] {status} {self.level.upper()}: {self.action}"

    @classmethod
    def log(cls, level, action, message, background_task='', task_category='other',
            task_id='', execution_time_ms=None, context_data=None, error_details='', success=True):
        """
        Convenience method to create log entries

        Example:
            BkLog.log('info', 'fetch_data', 'Started fetching market data',
                     background_task='fetch_trendlyne_data', task_category='data')
        """
        return cls.objects.create(
            level=level,
            action=action,
            message=message,
            background_task=background_task,
            task_category=task_category,
            task_id=task_id,
            execution_time_ms=execution_time_ms,
            context_data=context_data or {},
            error_details=error_details,
            success=success
        )


class DayReport(models.Model):
    """
    Daily trading report

    Stores end-of-day summary for each trading day.
    """

    date = models.DateField(
        unique=True,
        db_index=True,
        help_text="Trading date (DD-MM-YY format stored as DateField)"
    )
    day_of_week = models.CharField(
        max_length=20,
        blank=True,
        help_text="Day of the week"
    )

    # Trading summary
    num_legs = models.IntegerField(
        default=0,
        help_text="Number of option legs traded"
    )
    pnl = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Profit and Loss for the day"
    )
    is_closed = models.BooleanField(
        default=False,
        help_text="Whether all positions were closed"
    )

    # Contract info
    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="F&O expiry date traded"
    )

    # Metadata
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'day_report'
        ordering = ['-date']

    def __str__(self):
        return f"Report {self.date} ({self.day_of_week}): PnL ₹{self.pnl}"


class TodaysPosition(models.Model):
    """
    Individual position details for the day

    Stores detailed information about each F&O position taken during the day.
    Copied from broker's position data structure.
    """

    date = models.DateField(db_index=True, help_text="Position date")

    # Instrument details
    symbol = models.CharField(max_length=50)
    instrument_name = models.CharField(max_length=100)
    instrument_token = models.BigIntegerField()
    exchange = models.CharField(max_length=10, default='NFO')
    segment = models.CharField(max_length=10, default='FNO')

    # Contract details
    expiry_date = models.CharField(max_length=10)
    option_type = models.CharField(max_length=10)  # CE/PE/FUT
    strike_price = models.IntegerField(default=0)

    # Price & quantity
    last_price = models.FloatField()
    average_stock_price = models.FloatField()

    # Buy side
    buy_traded_qty_lot = models.IntegerField(default=0)
    buy_traded_val = models.FloatField(default=0)
    buy_trd_avg = models.FloatField(default=0)
    buy_open_qty_lot = models.IntegerField(default=0)
    buy_open_val = models.FloatField(default=0)

    # Sell side
    sell_traded_qty_lot = models.IntegerField(default=0)
    sell_traded_val = models.FloatField(default=0)
    sell_trd_avg = models.FloatField(default=0)
    sell_open_qty_lot = models.IntegerField(default=0)
    sell_open_val = models.FloatField(default=0)

    # Net position
    net_trd_qty_lot = models.IntegerField(default=0)
    net_trd_value = models.FloatField(default=0)
    actual_net_trd_value = models.FloatField(default=0)
    realized_pl = models.FloatField(default=0, help_text="Realized P&L")

    # Market data
    net_change = models.FloatField(default=0)
    percent_change = models.FloatField(default=0)

    # Margin details
    span_margin = models.FloatField(default=0)
    span_margin_total = models.FloatField(default=0)
    exposure_margin = models.FloatField(default=0)
    exposure_margin_total = models.FloatField(default=0)
    premium = models.FloatField(default=0)

    # Other fields
    market_lot = models.IntegerField(default=1)
    multiplier = models.IntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'todays_position'
        ordering = ['-date', 'symbol']
        indexes = [
            models.Index(fields=['-date', 'symbol']),
        ]

    def __str__(self):
        return f"{self.date} - {self.symbol} {self.option_type} {self.strike_price}: PnL ₹{self.realized_pl}"


class SystemSettings(TimeStampedModel):
    """
    System-wide settings for background tasks and scheduled operations

    Configurable timing settings for all Celery-based background tasks.
    This allows UI-based configuration without code changes.
    """

    # Singleton pattern - only one settings record should exist
    singleton_id = models.IntegerField(default=1, unique=True)

    # =========================================================================
    # MARKET DATA TASK TIMINGS
    # =========================================================================

    # Trendlyne Data Tasks
    trendlyne_fetch_hour = models.IntegerField(
        default=8,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Hour to fetch Trendlyne data (0-23)"
    )
    trendlyne_fetch_minute = models.IntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="Minute to fetch Trendlyne data (0-59)"
    )

    trendlyne_import_hour = models.IntegerField(
        default=9,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Hour to import Trendlyne data (0-23)"
    )
    trendlyne_import_minute = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="Minute to import Trendlyne data (0-59)"
    )

    # Pre-market Data
    premarket_update_hour = models.IntegerField(
        default=8,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Hour to update pre-market data (0-23)"
    )
    premarket_update_minute = models.IntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="Minute to update pre-market data (0-59)"
    )

    # Live Market Data
    live_data_interval_minutes = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Interval in minutes to update live market data during market hours"
    )
    live_data_start_hour = models.IntegerField(
        default=9,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Start hour for live market data updates"
    )
    live_data_end_hour = models.IntegerField(
        default=15,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="End hour for live market data updates"
    )

    # Post-market Data
    postmarket_update_hour = models.IntegerField(
        default=15,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Hour to update post-market data (0-23)"
    )
    postmarket_update_minute = models.IntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="Minute to update post-market data (0-59)"
    )

    # =========================================================================
    # STRATEGY TASK TIMINGS
    # =========================================================================

    # Futures Screening
    futures_screening_interval_minutes = models.IntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(120)],
        help_text="Interval in minutes to screen for futures opportunities"
    )
    futures_screening_start_hour = models.IntegerField(
        default=9,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Start hour for futures screening"
    )
    futures_screening_end_hour = models.IntegerField(
        default=14,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="End hour for futures screening"
    )

    # Futures Averaging
    futures_averaging_interval_minutes = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Interval in minutes to check futures averaging"
    )

    # =========================================================================
    # POSITION MONITORING TASK TIMINGS
    # =========================================================================

    # Position Monitoring (in seconds for real-time monitoring)
    monitor_positions_interval_seconds = models.IntegerField(
        default=10,
        validators=[MinValueValidator(5), MaxValueValidator(300)],
        help_text="Interval in seconds to monitor all positions"
    )

    update_pnl_interval_seconds = models.IntegerField(
        default=15,
        validators=[MinValueValidator(5), MaxValueValidator(300)],
        help_text="Interval in seconds to update position P&L"
    )

    check_exit_interval_seconds = models.IntegerField(
        default=30,
        validators=[MinValueValidator(10), MaxValueValidator(300)],
        help_text="Interval in seconds to check exit conditions"
    )

    # =========================================================================
    # RISK MANAGEMENT TASK TIMINGS
    # =========================================================================

    # Risk Checks (in seconds for real-time monitoring)
    risk_check_interval_seconds = models.IntegerField(
        default=60,
        validators=[MinValueValidator(30), MaxValueValidator(600)],
        help_text="Interval in seconds to check risk limits"
    )

    circuit_breaker_interval_seconds = models.IntegerField(
        default=30,
        validators=[MinValueValidator(10), MaxValueValidator(300)],
        help_text="Interval in seconds to monitor circuit breakers"
    )

    # =========================================================================
    # REPORTING & ANALYTICS TASK TIMINGS
    # =========================================================================

    # Daily P&L Report
    daily_pnl_report_hour = models.IntegerField(
        default=16,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Hour to generate daily P&L report (0-23)"
    )
    daily_pnl_report_minute = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="Minute to generate daily P&L report (0-59)"
    )

    # Learning Patterns Update
    learning_patterns_hour = models.IntegerField(
        default=17,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Hour to update learning patterns (0-23)"
    )
    learning_patterns_minute = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="Minute to update learning patterns (0-59)"
    )

    # Weekly Summary
    weekly_summary_hour = models.IntegerField(
        default=18,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Hour to send weekly summary (0-23)"
    )
    weekly_summary_minute = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="Minute to send weekly summary (0-59)"
    )
    weekly_summary_day_of_week = models.IntegerField(
        default=4,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="Day of week for weekly summary (0=Monday, 6=Sunday)"
    )

    # =========================================================================
    # TASK ENABLE/DISABLE FLAGS
    # =========================================================================

    enable_market_data_tasks = models.BooleanField(
        default=False,
        help_text="Enable all market data fetching tasks"
    )
    enable_strategy_tasks = models.BooleanField(
        default=False,
        help_text="Enable strategy execution tasks"
    )
    enable_position_monitoring = models.BooleanField(
        default=False,
        help_text="Enable position monitoring tasks"
    )
    enable_risk_monitoring = models.BooleanField(
        default=False,
        help_text="Enable risk management tasks"
    )
    enable_reporting_tasks = models.BooleanField(
        default=False,
        help_text="Enable reporting and analytics tasks"
    )

    class Meta:
        db_table = 'system_settings'
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'

    def __str__(self):
        return f"System Settings (Updated: {self.updated_at.strftime('%Y-%m-%d %H:%M')})"

    @classmethod
    def get_settings(cls):
        """
        Get or create the singleton settings instance

        Returns:
            SystemSettings: The singleton settings object
        """
        settings, created = cls.objects.get_or_create(
            singleton_id=1,
            defaults={}
        )
        if created:
            settings.save()
        return settings

    def save(self, *args, **kwargs):
        """Override save to ensure singleton pattern"""
        self.singleton_id = 1
        super().save(*args, **kwargs)


class CeleryTaskState(TimeStampedModel):
    """
    Tracks enabled/disabled state and schedule configuration for individual Celery tasks.

    Used to control static tasks defined in code (celery.py beat_schedule).
    Tasks not in this table are considered DISABLED by default.
    Users must explicitly enable tasks they want to run.

    Schedule configuration allows UI-based customization of task timing.
    """

    SCHEDULE_TYPE_CHOICES = [
        ('crontab', 'Fixed Time (Crontab)'),
        ('interval', 'Interval'),
        ('recurring', 'Recurring Window'),
    ]

    task_key = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Task key from beat_schedule (e.g., 'fetch-trendlyne-data-daily')"
    )
    task_path = models.CharField(
        max_length=200,
        blank=True,
        help_text="Full task path (e.g., 'apps.data.tasks.fetch_trendlyne_data')"
    )
    display_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Human-readable task name"
    )
    description = models.TextField(
        blank=True,
        help_text="Task description"
    )
    is_enabled = models.BooleanField(
        default=False,
        help_text="Whether this task should run (default: disabled)"
    )
    last_toggled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the task was last enabled/disabled"
    )
    last_toggled_by = models.CharField(
        max_length=100,
        blank=True,
        help_text="User who last toggled this task"
    )

    # =========================================================================
    # SCHEDULE CONFIGURATION
    # =========================================================================

    schedule_type = models.CharField(
        max_length=20,
        choices=SCHEDULE_TYPE_CHOICES,
        default='crontab',
        help_text="Type of schedule: crontab (fixed time), interval, or recurring window"
    )

    # Crontab fields (for fixed time tasks)
    schedule_hour = models.IntegerField(
        default=9,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Hour to run (0-23) for crontab tasks"
    )
    schedule_minute = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="Minute to run (0-59) for crontab tasks"
    )

    # Interval fields (for recurring tasks)
    interval_seconds = models.IntegerField(
        default=60,
        validators=[MinValueValidator(1), MaxValueValidator(86400)],
        help_text="Interval in seconds for interval tasks"
    )

    # Recurring window fields
    recurring_start_hour = models.IntegerField(
        default=9,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="Start hour for recurring window (0-23)"
    )
    recurring_start_minute = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="Start minute for recurring window (0-59)"
    )
    recurring_end_hour = models.IntegerField(
        default=15,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="End hour for recurring window (0-23)"
    )
    recurring_end_minute = models.IntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
        help_text="End minute for recurring window (0-59)"
    )
    recurring_interval_minutes = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Interval in minutes within the recurring window"
    )

    # Days of week (JSON array: 0=Monday, 6=Sunday)
    days_of_week = models.JSONField(
        default=list,
        blank=True,
        help_text="Days of week to run (0=Mon, 1=Tue, ..., 6=Sun). Empty = all weekdays."
    )

    # Task-specific parameters (JSON)
    task_params = models.JSONField(
        default=dict,
        blank=True,
        help_text="Task-specific parameters as JSON (e.g., {'top_contracts': 50})"
    )

    # Whether to use custom schedule (if False, use defaults from celery.py)
    use_custom_schedule = models.BooleanField(
        default=False,
        help_text="Use custom schedule instead of system defaults"
    )

    # Category for grouping
    category = models.CharField(
        max_length=50,
        blank=True,
        help_text="Task category for grouping (data, strategies, monitoring, risk, reports)"
    )

    class Meta:
        db_table = 'celery_task_state'
        ordering = ['task_key']
        verbose_name = 'Celery Task State'
        verbose_name_plural = 'Celery Task States'

    def __str__(self):
        status = "Enabled" if self.is_enabled else "Disabled"
        return f"{self.task_key} - {status}"

    @classmethod
    def is_task_enabled(cls, task_key: str) -> bool:
        """Check if a task is enabled (defaults to False if not in DB)"""
        try:
            state = cls.objects.get(task_key=task_key)
            return state.is_enabled
        except cls.DoesNotExist:
            return False  # Default to disabled - tasks must be explicitly enabled

    @classmethod
    def set_task_state(cls, task_key: str, enabled: bool, task_path: str = '',
                       display_name: str = '', user: str = '', **schedule_kwargs):
        """Set or create task state with optional schedule configuration"""
        from django.utils import timezone

        defaults = {
            'is_enabled': enabled,
            'last_toggled_at': timezone.now(),
            'last_toggled_by': user,
        }

        # Only update these if provided
        if task_path:
            defaults['task_path'] = task_path
        if display_name:
            defaults['display_name'] = display_name

        # Add schedule configuration if provided
        schedule_fields = [
            'schedule_type', 'schedule_hour', 'schedule_minute',
            'interval_seconds', 'recurring_start_hour', 'recurring_start_minute',
            'recurring_end_hour', 'recurring_end_minute', 'recurring_interval_minutes',
            'days_of_week', 'use_custom_schedule', 'category', 'description'
        ]
        for field in schedule_fields:
            if field in schedule_kwargs and schedule_kwargs[field] is not None:
                defaults[field] = schedule_kwargs[field]

        state, created = cls.objects.update_or_create(
            task_key=task_key,
            defaults=defaults
        )
        return state

    @classmethod
    def get_task_schedule(cls, task_key: str) -> dict:
        """Get schedule configuration for a task"""
        try:
            state = cls.objects.get(task_key=task_key)
            return {
                'schedule_type': state.schedule_type,
                'schedule_hour': state.schedule_hour,
                'schedule_minute': state.schedule_minute,
                'interval_seconds': state.interval_seconds,
                'recurring_start_hour': state.recurring_start_hour,
                'recurring_start_minute': state.recurring_start_minute,
                'recurring_end_hour': state.recurring_end_hour,
                'recurring_end_minute': state.recurring_end_minute,
                'recurring_interval_minutes': state.recurring_interval_minutes,
                'days_of_week': state.days_of_week or [0, 1, 2, 3, 4],  # Default weekdays
                'use_custom_schedule': state.use_custom_schedule,
                'category': state.category,
                'description': state.description,
            }
        except cls.DoesNotExist:
            return None

    @classmethod
    def update_schedule(cls, task_key: str, user: str = '', **schedule_kwargs):
        """Update schedule configuration for a task"""
        from django.utils import timezone

        try:
            state = cls.objects.get(task_key=task_key)

            # Update schedule fields
            schedule_fields = [
                'schedule_type', 'schedule_hour', 'schedule_minute',
                'interval_seconds', 'recurring_start_hour', 'recurring_start_minute',
                'recurring_end_hour', 'recurring_end_minute', 'recurring_interval_minutes',
                'days_of_week', 'use_custom_schedule', 'category', 'description'
            ]

            updated = False
            for field in schedule_fields:
                if field in schedule_kwargs and schedule_kwargs[field] is not None:
                    setattr(state, field, schedule_kwargs[field])
                    updated = True

            if updated:
                state.use_custom_schedule = True
                state.last_toggled_at = timezone.now()
                state.last_toggled_by = user
                state.save()

            return state
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_all_states(cls) -> dict:
        """Get all task states as a dict {task_key: is_enabled}"""
        return {s.task_key: s.is_enabled for s in cls.objects.all()}

    @classmethod
    def initialize_static_tasks(cls, schedule: dict, force: bool = False) -> dict:
        """
        Initialize all static tasks in the database.

        Args:
            schedule: The beat schedule dictionary from celery.py
            force: If True, reset all tasks to disabled. If False, only create missing tasks.

        Returns:
            dict with counts of created and updated tasks
        """
        from django.utils import timezone

        created = 0
        updated = 0

        for task_key, config in schedule.items():
            # Skip dynamic tasks (those managed by TradingScheduleConfig)
            if any(d in task_key.lower() for d in ['premarket', 'market_open', 'trade_start', 'trade_monitor', 'trade_stop', 'day_close', 'analyze_day']):
                continue

            task_path = config.get('task', '')
            display_name = task_key.replace('-', ' ').title()

            if force:
                # Reset to disabled
                _, was_created = cls.objects.update_or_create(
                    task_key=task_key,
                    defaults={
                        'is_enabled': False,
                        'task_path': task_path,
                        'display_name': display_name,
                        'last_toggled_at': timezone.now(),
                        'last_toggled_by': 'system',
                    }
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            else:
                # Only create if doesn't exist
                _, was_created = cls.objects.get_or_create(
                    task_key=task_key,
                    defaults={
                        'is_enabled': False,
                        'task_path': task_path,
                        'display_name': display_name,
                        'last_toggled_at': timezone.now(),
                        'last_toggled_by': 'system',
                    }
                )
                if was_created:
                    created += 1

        return {'created': created, 'updated': updated}

    @classmethod
    def get_enabled_task_keys(cls) -> set:
        """Get set of task keys that are enabled"""
        return set(cls.objects.filter(is_enabled=True).values_list('task_key', flat=True))


class TradingCoreConfig(TimeStampedModel):
    """
    Core trading configuration - singleton model for strategy selection and risk parameters.

    This is set before market opens and controls:
    - Which options strategy to use (Strangle vs Broken Iron Condor)
    - Position sizing mode (Test, Manual, Auto margin-based, Simulated)
    - Notification level (Full Control, Supervised, Autonomous)
    - Risk parameters and thresholds
    - Carry forward rules for overnight positions
    """

    STRATEGY_CHOICES = [
        ('STRANGLE', 'Short Strangle'),
        ('BROKEN_IRON_CONDOR', 'Broken Iron Condor'),
        ('AUTO', 'Auto (VIX-based decision)'),
        ('NONE', 'Disabled - No Options Trading'),
    ]

    POSITION_SIZING_CHOICES = [
        ('TEST', 'Test Mode (1 Lot Each)'),
        ('MANUAL', 'Manual (Fixed Lots)'),
        ('AUTO', 'Auto (Margin-Based)'),
        ('SIMULATED', 'Simulated (Paper Trade)'),
    ]

    NOTIFICATION_LEVEL_CHOICES = [
        ('FULL_CONTROL', 'Full Control - Confirm Everything'),
        ('SUPERVISED', 'Supervised - Confirm Major Actions'),
        ('AUTONOMOUS', 'Autonomous - Notifications Only'),
    ]

    # Singleton pattern - only one config record
    singleton_id = models.IntegerField(default=1, unique=True)

    # =========================================================================
    # TRADING ENABLE/DISABLE
    # =========================================================================

    enable_futures_trading = models.BooleanField(
        default=True,
        help_text="Enable futures trading algorithm"
    )

    # =========================================================================
    # STRATEGY SELECTION
    # =========================================================================

    options_strategy = models.CharField(
        max_length=50,
        choices=STRATEGY_CHOICES,
        default='AUTO',
        help_text="Options strategy: Strangle, Iron Condor, Auto, or None (disabled)"
    )

    # =========================================================================
    # POSITION SIZING MODE
    # =========================================================================

    position_sizing_mode = models.CharField(
        max_length=20,
        choices=POSITION_SIZING_CHOICES,
        default='TEST',
        help_text="How to determine position sizes"
    )

    # Manual mode - fixed lots
    manual_options_lots = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="Fixed lots for options (Manual mode)"
    )
    manual_futures_lots = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Fixed lots for futures (Manual mode)"
    )

    # Auto mode - margin utilization percentage
    margin_utilization_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50.00,
        validators=[MinValueValidator(10), MaxValueValidator(90)],
        help_text="% of available margin to use (Auto mode)"
    )

    # Simulated mode - paper trade with hypothetical positions
    simulated_options_lots = models.IntegerField(
        default=100,
        validators=[MinValueValidator(1), MaxValueValidator(500)],
        help_text="Hypothetical lots for options (Simulated mode)"
    )
    simulated_futures_lots = models.IntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Hypothetical lots for futures (Simulated mode)"
    )

    # Legacy fields for backward compatibility (deprecated)
    options_lots = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="DEPRECATED: Use manual_options_lots instead"
    )
    futures_lots = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="DEPRECATED: Use manual_futures_lots instead"
    )

    # =========================================================================
    # RISK PARAMETERS
    # =========================================================================

    max_loss_per_trade = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=10000,
        help_text="Maximum loss allowed per trade in INR"
    )
    options_profit_target = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=5000,
        help_text="Target profit for options positions in INR"
    )
    movement_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.5,
        validators=[MinValueValidator(0.1), MaxValueValidator(3.0)],
        help_text="Max % movement since market open to allow entry (e.g., 0.5%)"
    )

    # =========================================================================
    # NOTIFICATION & CONTROL LEVEL
    # =========================================================================

    notification_level = models.CharField(
        max_length=20,
        choices=NOTIFICATION_LEVEL_CHOICES,
        default='FULL_CONTROL',
        help_text="Level of user control: Full Control (confirm all), Supervised (confirm major), Autonomous (auto-execute)"
    )

    confirmation_timeout_minutes = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Minutes to wait for user confirmation before revalidating"
    )

    # Legacy fields for backward compatibility (deprecated)
    require_telegram_confirmation = models.BooleanField(
        default=True,
        help_text="DEPRECATED: Use notification_level instead"
    )
    auto_close_on_target = models.BooleanField(
        default=False,
        help_text="DEPRECATED: Use notification_level=AUTONOMOUS instead"
    )
    auto_close_on_stoploss = models.BooleanField(
        default=False,
        help_text="DEPRECATED: Use notification_level=AUTONOMOUS instead"
    )

    # =========================================================================
    # CARRY FORWARD RULES (for overnight options positions)
    # =========================================================================

    options_carry_forward_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=5000,
        help_text="Close same day if profit >= this amount, else carry forward"
    )

    # =========================================================================
    # VIX-BASED AUTO STRATEGY THRESHOLDS
    # =========================================================================

    vix_high_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=18.0,
        help_text="VIX above this = prefer Iron Condor (more protection)"
    )
    vix_low_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=14.0,
        help_text="VIX below this = prefer Strangle (more premium)"
    )

    class Meta:
        db_table = 'trading_core_config'
        verbose_name = 'Trading Core Configuration'
        verbose_name_plural = 'Trading Core Configuration'

    def __str__(self):
        return f"Trading Config: {self.get_options_strategy_display()} | {self.options_lots} lots"

    def save(self, *args, **kwargs):
        """Override save to ensure singleton pattern"""
        self.singleton_id = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_instance(cls):
        """
        Get or create the singleton config instance.

        Returns:
            TradingCoreConfig: The singleton config object
        """
        config, created = cls.objects.get_or_create(
            singleton_id=1,
            defaults={}
        )
        return config

    def get_auto_strategy(self, current_vix: float = None) -> str:
        """
        Determine strategy automatically based on VIX.

        Args:
            current_vix: Current VIX value. If None, returns STRANGLE as default.

        Returns:
            str: 'STRANGLE', 'BROKEN_IRON_CONDOR', or 'NONE'
        """
        # If explicitly set to NONE or a specific strategy, use it
        if self.options_strategy == 'NONE':
            return 'NONE'

        if self.options_strategy != 'AUTO':
            return self.options_strategy

        # Auto mode - decide based on VIX
        if current_vix is None:
            return 'STRANGLE'

        if current_vix >= float(self.vix_high_threshold):
            return 'BROKEN_IRON_CONDOR'
        else:
            return 'STRANGLE'

    def is_options_enabled(self) -> bool:
        """Check if options trading is enabled."""
        return self.options_strategy != 'NONE'

    def is_futures_enabled(self) -> bool:
        """Check if futures trading is enabled."""
        return self.enable_futures_trading

    # =========================================================================
    # POSITION SIZING HELPERS
    # =========================================================================

    def get_lots_for_trade(self, trade_type: str, available_margin=None, margin_per_lot=None) -> int:
        """
        Calculate lots based on position sizing mode.

        Args:
            trade_type: 'OPTIONS' or 'FUTURES'
            available_margin: Current available margin from broker API (Decimal)
            margin_per_lot: Margin required per lot for this instrument (Decimal)

        Returns:
            int: Number of lots to trade
        """
        from decimal import Decimal

        if self.position_sizing_mode == 'TEST':
            return 1

        if self.position_sizing_mode == 'SIMULATED':
            return self.simulated_options_lots if trade_type == 'OPTIONS' else self.simulated_futures_lots

        if self.position_sizing_mode == 'MANUAL':
            return self.manual_options_lots if trade_type == 'OPTIONS' else self.manual_futures_lots

        if self.position_sizing_mode == 'AUTO':
            if not available_margin or not margin_per_lot or margin_per_lot <= 0:
                return 1  # Fallback to 1 lot if margin data unavailable

            available_margin = Decimal(str(available_margin))
            margin_per_lot = Decimal(str(margin_per_lot))
            usable_margin = available_margin * (self.margin_utilization_pct / Decimal('100'))
            calculated_lots = int(usable_margin / margin_per_lot)
            return max(1, calculated_lots)  # At least 1 lot

        return 1

    def is_test_mode(self) -> bool:
        """Check if in test mode (1 lot trades)."""
        return self.position_sizing_mode == 'TEST'

    def is_simulated(self) -> bool:
        """Check if in simulated mode (paper trading - no real orders)."""
        return self.position_sizing_mode == 'SIMULATED'

    def is_auto_sizing(self) -> bool:
        """Check if using automatic margin-based sizing."""
        return self.position_sizing_mode == 'AUTO'

    # =========================================================================
    # NOTIFICATION LEVEL HELPERS
    # =========================================================================

    def requires_confirmation(self, action_type: str) -> bool:
        """
        Check if an action requires user confirmation based on notification level.

        Args:
            action_type: 'ENTRY', 'EXIT', 'AVERAGING', 'INFO'

        Returns:
            bool: True if confirmation required
        """
        if self.notification_level == 'FULL_CONTROL':
            return True  # Confirm everything

        if self.notification_level == 'SUPERVISED':
            # Only confirm major actions (entry and exit)
            return action_type in ['ENTRY', 'EXIT']

        if self.notification_level == 'AUTONOMOUS':
            return False  # No confirmations, just notify

        return True  # Default to safe behavior

    def is_full_control(self) -> bool:
        """Check if in full control mode (confirm everything)."""
        return self.notification_level == 'FULL_CONTROL'

    def is_supervised(self) -> bool:
        """Check if in supervised mode (confirm major actions only)."""
        return self.notification_level == 'SUPERVISED'

    def is_autonomous(self) -> bool:
        """Check if in autonomous mode (no confirmations)."""
        return self.notification_level == 'AUTONOMOUS'

    def get_notification_level_display_short(self) -> str:
        """Get short display name for notification level."""
        level_names = {
            'FULL_CONTROL': '🔒 Full Control',
            'SUPERVISED': '👁️ Supervised',
            'AUTONOMOUS': '🤖 Autonomous',
        }
        return level_names.get(self.notification_level, self.notification_level)

    def get_position_sizing_display_short(self) -> str:
        """Get short display name for position sizing mode."""
        mode_names = {
            'TEST': '🧪 Test (1 lot)',
            'MANUAL': '✋ Manual',
            'AUTO': '📊 Auto (Margin)',
            'SIMULATED': '📝 Simulated',
        }
        return mode_names.get(self.position_sizing_mode, self.position_sizing_mode)
