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
        default=True,
        help_text="Enable all market data fetching tasks"
    )
    enable_strategy_tasks = models.BooleanField(
        default=True,
        help_text="Enable strategy execution tasks"
    )
    enable_position_monitoring = models.BooleanField(
        default=True,
        help_text="Enable position monitoring tasks"
    )
    enable_risk_monitoring = models.BooleanField(
        default=True,
        help_text="Enable risk management tasks"
    )
    enable_reporting_tasks = models.BooleanField(
        default=True,
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
