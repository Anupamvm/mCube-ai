"""
Strategy models for mCube Trading System

This module contains models for strategy configuration and self-learning.
"""

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from apps.core.models import TimeStampedModel
from apps.core.constants import STRATEGY_CHOICES


class StrategyConfig(TimeStampedModel):
    """
    Strategy configuration model

    Stores configuration parameters for trading strategies.
    Each account can have multiple strategy configurations.

    Fields:
        account: Associated broker account
        strategy_type: Type of strategy
        is_active: Whether strategy is currently active
        initial_margin_usage_pct: Percentage of margin to use for first trade
        min_profit_pct_to_exit: Minimum profit % required for EOD exit
    """

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='strategies',
        help_text="Associated broker account"
    )

    strategy_type = models.CharField(
        max_length=50,
        choices=STRATEGY_CHOICES,
        help_text="Type of strategy"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this strategy is currently active"
    )

    # Position rules
    initial_margin_usage_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('50.00'),
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('100.00'))
        ],
        help_text="Use 50% margin for first trade (reserve 50%)"
    )

    min_profit_pct_to_exit = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('50.00'),
        help_text="Only exit EOD if profit >= this %"
    )

    # Kotak Strangle specific parameters
    base_delta_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.50'),
        help_text="Base delta % for strike selection (Strangle)"
    )

    min_days_to_expiry = models.IntegerField(
        default=1,
        help_text="Minimum days to expiry for options (skip if less)"
    )

    delta_rebalance_threshold = models.IntegerField(
        default=300,
        help_text="Alert when |net_delta| exceeds this (Strangle)"
    )

    # ICICI Futures specific parameters
    min_days_to_future_expiry = models.IntegerField(
        default=15,
        help_text="Minimum days to expiry for futures (skip if less)"
    )

    allow_averaging = models.BooleanField(
        default=True,
        help_text="Whether averaging is allowed (Futures)"
    )

    max_average_attempts = models.IntegerField(
        default=2,
        help_text="Maximum averaging attempts (Futures)"
    )

    average_down_threshold_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text="Average when position down by this % (Futures)"
    )

    default_stop_loss_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.50'),
        help_text="Default stop-loss % (Futures)"
    )

    default_target_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text="Default target % (Futures)"
    )

    min_llm_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('70.00'),
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('100.00'))
        ],
        help_text="Minimum LLM confidence % required (Futures)"
    )

    require_human_approval = models.BooleanField(
        default=True,
        help_text="Require manual approval before entry (Futures)"
    )

    # Additional parameters
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional strategy-specific parameters"
    )

    notes = models.TextField(
        blank=True,
        help_text="Any additional notes"
    )

    class Meta:
        db_table = 'strategy_configs'
        verbose_name = 'Strategy Configuration'
        verbose_name_plural = 'Strategy Configurations'
        unique_together = ['account', 'strategy_type']
        ordering = ['account', 'strategy_type']

    def __str__(self):
        return f"{self.get_strategy_type_display()} - {self.account.account_name}"


class StrategyLearning(TimeStampedModel):
    """
    Self-learning system to track pattern performance

    This model stores trading patterns and their performance metrics
    to enable the system to learn from past trades.

    Fields:
        strategy_type: Type of strategy
        pattern_name: Unique pattern identifier
        pattern_description: Description of the pattern
        entry_conditions: Entry conditions JSON
        market_conditions: Market conditions JSON
        times_occurred: How many times this pattern occurred
        times_profitable: How many times it was profitable
        win_rate: Win rate percentage
        profit_factor: Profit factor (gross profit / gross loss)
        avg_profit_pct: Average profit percentage
        avg_loss_pct: Average loss percentage
    """

    strategy_type = models.CharField(
        max_length=50,
        help_text="Type of strategy"
    )

    pattern_name = models.CharField(
        max_length=100,
        help_text="Unique pattern identifier"
    )

    pattern_description = models.TextField(
        help_text="Description of what this pattern represents"
    )

    # Pattern definition
    entry_conditions = models.JSONField(
        default=dict,
        help_text="Entry conditions that define this pattern"
    )

    market_conditions = models.JSONField(
        default=dict,
        help_text="Market conditions when pattern occurs"
    )

    # Performance metrics
    times_occurred = models.IntegerField(
        default=0,
        help_text="Number of times this pattern occurred"
    )

    times_profitable = models.IntegerField(
        default=0,
        help_text="Number of times pattern resulted in profit"
    )

    avg_profit_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Average profit percentage"
    )

    avg_loss_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Average loss percentage"
    )

    win_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Win rate percentage"
    )

    profit_factor = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Profit factor (gross profit / gross loss)"
    )

    # Aggregate P&L
    total_profit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total profit from this pattern"
    )

    total_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total loss from this pattern"
    )

    # Learning insights
    insights = models.TextField(
        blank=True,
        help_text="LLM-generated insights about this pattern"
    )

    recommendations = models.TextField(
        blank=True,
        help_text="Recommendations for trading this pattern"
    )

    # Status
    is_reliable = models.BooleanField(
        default=False,
        help_text="Whether this pattern is statistically reliable (>30 occurrences)"
    )

    last_occurrence = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this pattern occurred"
    )

    class Meta:
        db_table = 'strategy_learning'
        verbose_name = 'Strategy Learning'
        verbose_name_plural = 'Strategy Learning Records'
        unique_together = ['strategy_type', 'pattern_name']
        ordering = ['-win_rate', '-profit_factor']

    def __str__(self):
        return f"{self.pattern_name} ({self.strategy_type}) - WR: {self.win_rate}%"

    def update_metrics(self, is_profitable: bool, pnl_pct: Decimal):
        """
        Update pattern metrics with new trade result

        Args:
            is_profitable: Whether the trade was profitable
            pnl_pct: P&L percentage
        """
        self.times_occurred += 1

        if is_profitable:
            self.times_profitable += 1
            self.total_profit += abs(pnl_pct)
            # Update average profit
            old_avg = self.avg_profit_pct
            self.avg_profit_pct = (
                (old_avg * (self.times_profitable - 1) + pnl_pct) /
                self.times_profitable
            )
        else:
            self.total_loss += abs(pnl_pct)
            # Update average loss
            old_avg = self.avg_loss_pct
            times_loss = self.times_occurred - self.times_profitable
            self.avg_loss_pct = (
                (old_avg * (times_loss - 1) + abs(pnl_pct)) /
                times_loss
            ) if times_loss > 0 else Decimal('0.0000')

        # Calculate win rate
        self.win_rate = (
            Decimal(self.times_profitable) / Decimal(self.times_occurred) * 100
        )

        # Calculate profit factor
        if self.total_loss > 0:
            self.profit_factor = self.total_profit / self.total_loss
        else:
            self.profit_factor = self.total_profit if self.total_profit > 0 else Decimal('0.0000')

        # Mark as reliable if >= 30 occurrences
        self.is_reliable = self.times_occurred >= 30

        from django.utils import timezone
        self.last_occurrence = timezone.now()

        self.save()


class TradingScheduleConfig(TimeStampedModel):
    """
    Configurable schedule for trading tasks

    Allows UI-based configuration of task timings without code changes
    """

    TASK_CHOICES = [
        ('PREMARKET', 'Pre-Market Data Fetch'),
        ('MARKET_OPEN', 'Market Opening Validation'),
        ('TRADE_START', 'Trade Start Evaluation'),
        ('TRADE_MONITOR', 'Trade Monitoring'),
        ('TRADE_STOP', 'Trade Stop/Exit'),
        ('DAY_CLOSE', 'Day Close Reconciliation'),
        ('ANALYZE_DAY', 'Day Analysis & Learning'),
    ]

    task_name = models.CharField(max_length=50, choices=TASK_CHOICES, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Timing configuration
    scheduled_time = models.TimeField(help_text="Time to run this task (IST)")
    is_enabled = models.BooleanField(default=True)

    # For recurring tasks (like monitoring)
    is_recurring = models.BooleanField(default=False)
    interval_minutes = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Interval in minutes for recurring tasks"
    )
    start_time = models.TimeField(null=True, blank=True, help_text="Start time for recurring task")
    end_time = models.TimeField(null=True, blank=True, help_text="End time for recurring task")

    # Days of week to run (JSON list of integers 0-6, Monday-Sunday)
    days_of_week = models.JSONField(
        default=list,
        help_text="Days to run: [0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri]"
    )

    # Task parameters (strategy-specific)
    task_parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Task-specific parameters as JSON"
    )

    # Execution tracking
    last_executed_at = models.DateTimeField(null=True, blank=True)
    execution_count = models.IntegerField(default=0)
    last_status = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = 'trading_schedule_config'
        ordering = ['scheduled_time']
        verbose_name = 'Trading Schedule Configuration'
        verbose_name_plural = 'Trading Schedule Configurations'

    def __str__(self):
        status = "✅" if self.is_enabled else "❌"
        return f"{status} {self.get_task_name_display()} @ {self.scheduled_time.strftime('%H:%M')}"


class MarketOpeningState(TimeStampedModel):
    """
    Market opening state captured at 9:15 AM

    Tracks how market opens and subsequent movement for decision making
    """

    trading_date = models.DateField(db_index=True, unique=True)

    # Previous day close
    prev_close = models.DecimalField(max_digits=15, decimal_places=2)

    # Opening prices (9:15 AM)
    nifty_open = models.DecimalField(max_digits=15, decimal_places=2)
    nifty_9_15_price = models.DecimalField(max_digits=15, decimal_places=2)

    # Gap analysis
    gap_points = models.DecimalField(max_digits=15, decimal_places=2)
    gap_percent = models.DecimalField(max_digits=10, decimal_places=4)
    gap_type = models.CharField(
        max_length=20,
        choices=[
            ('GAP_UP', 'Gap Up'),
            ('GAP_DOWN', 'Gap Down'),
            ('FLAT', 'Flat Open')
        ]
    )

    # Market sentiment at opening
    opening_sentiment = models.CharField(
        max_length=20,
        choices=[
            ('BULLISH', 'Bullish'),
            ('NEUTRAL', 'Neutral'),
            ('BEARISH', 'Bearish'),
            ('VOLATILE', 'Volatile')
        ],
        null=True,
        blank=True
    )

    # VIX at opening
    vix_9_15 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    # Volume analysis
    opening_volume = models.BigIntegerField(null=True, blank=True)
    volume_vs_avg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # 9:15 to 9:30 movement tracking
    nifty_9_30_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    movement_9_15_to_9_30_points = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    movement_9_15_to_9_30_percent = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    # Is movement substantial (>0.5%)?
    is_substantial_movement = models.BooleanField(default=False)

    # Market state flags
    is_trading_day = models.BooleanField(default=True)
    is_expiry_day = models.BooleanField(default=False)
    is_event_day = models.BooleanField(default=False)

    # SGX Nifty correlation
    sgx_nifty_change = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    sgx_correlation_accurate = models.BooleanField(null=True, blank=True)

    # US market influence
    us_nasdaq_change = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    us_dow_change = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    # Metadata
    captured_at = models.DateTimeField(auto_now_add=True)
    updated_at_9_30 = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'market_opening_state'
        ordering = ['-trading_date']
        indexes = [
            models.Index(fields=['-trading_date']),
            models.Index(fields=['is_substantial_movement']),
        ]

    def __str__(self):
        return f"Market Opening {self.trading_date} ({self.gap_type}, {self.gap_percent:+.2f}%)"


class SGXNiftyData(TimeStampedModel):
    """
    SGX Nifty futures data (Singapore Exchange)

    Captures pre-market Nifty sentiment from Singapore market
    """

    trading_date = models.DateField(db_index=True, unique=True)

    # SGX Nifty prices (before Indian market opens)
    sgx_open = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    sgx_high = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    sgx_low = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    sgx_close = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    sgx_last_traded = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # SGX Nifty changes
    sgx_change_points = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    sgx_change_percent = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    # Indian Nifty previous close (for comparison)
    nifty_prev_close = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # Implied gap from SGX
    implied_gap_points = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    implied_gap_percent = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    # Fetch metadata
    fetched_at = models.DateTimeField(auto_now_add=True)
    data_source = models.CharField(max_length=100, default='Yahoo Finance')

    class Meta:
        db_table = 'sgx_nifty_data'
        ordering = ['-trading_date']
        indexes = [models.Index(fields=['-trading_date'])]

    def __str__(self):
        return f"SGX Nifty {self.trading_date} ({self.sgx_change_percent:+.2f}%)"


class DailyTradingAnalysis(TimeStampedModel):
    """
    Daily trading analysis and learning (3:40 PM task)

    Captures comprehensive day analysis for continuous improvement
    """

    trading_date = models.DateField(db_index=True, unique=True)

    # Market summary
    nifty_open = models.DecimalField(max_digits=15, decimal_places=2)
    nifty_high = models.DecimalField(max_digits=15, decimal_places=2)
    nifty_low = models.DecimalField(max_digits=15, decimal_places=2)
    nifty_close = models.DecimalField(max_digits=15, decimal_places=2)
    nifty_change_percent = models.DecimalField(max_digits=10, decimal_places=4)

    vix_open = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    vix_close = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    vix_change_percent = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    # Trading activity
    total_trades_entered = models.IntegerField(default=0)
    total_trades_exited = models.IntegerField(default=0)
    total_trades_open = models.IntegerField(default=0)

    # Performance metrics
    total_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    realized_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    unrealized_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))

    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)
    win_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))

    # Capital efficiency
    capital_deployed = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    return_on_capital = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0'))

    # Filter effectiveness
    filters_run = models.JSONField(default=dict, help_text="Which filters were run")
    filters_passed = models.JSONField(default=dict, help_text="Which filters passed")
    filters_failed = models.JSONField(default=dict, help_text="Which filters failed")
    filter_accuracy = models.JSONField(default=dict, help_text="Filter accuracy analysis")

    # Entry analysis
    entry_timing_analysis = models.JSONField(default=dict, help_text="Entry timing effectiveness")
    strike_selection_analysis = models.JSONField(default=dict, help_text="Strike selection performance")
    position_sizing_analysis = models.JSONField(default=dict, help_text="Position sizing effectiveness")

    # Exit analysis
    exit_timing_analysis = models.JSONField(default=dict, help_text="Exit timing effectiveness")
    exit_reasons = models.JSONField(default=dict, help_text="Exit reasons breakdown")

    # Pattern recognition
    market_regime = models.CharField(
        max_length=50,
        choices=[
            ('TRENDING_UP', 'Trending Up'),
            ('TRENDING_DOWN', 'Trending Down'),
            ('RANGE_BOUND', 'Range Bound'),
            ('VOLATILE', 'Volatile'),
            ('QUIET', 'Quiet'),
        ],
        null=True,
        blank=True
    )

    successful_patterns = models.JSONField(default=list, help_text="Patterns that led to success")
    failed_patterns = models.JSONField(default=list, help_text="Patterns that led to failure")

    # Learning insights
    key_learnings = models.JSONField(default=list, help_text="Key insights from the day")
    recommendations = models.JSONField(default=list, help_text="Recommendations for future")
    parameter_adjustments = models.JSONField(default=dict, help_text="Suggested parameter changes")

    # Confidence scores
    overall_strategy_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    # SGX correlation accuracy
    sgx_prediction_accuracy = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="How accurate was SGX in predicting Indian market"
    )

    # Analysis metadata
    analysis_completed_at = models.DateTimeField(null=True, blank=True)
    analysis_version = models.CharField(max_length=20, default='1.0')

    # Telegram notification sent
    notification_sent = models.BooleanField(default=False)

    class Meta:
        db_table = 'daily_trading_analysis'
        ordering = ['-trading_date']
        indexes = [
            models.Index(fields=['-trading_date']),
            models.Index(fields=['market_regime']),
            models.Index(fields=['win_rate']),
        ]

    def __str__(self):
        return f"Analysis {self.trading_date} (P&L: ₹{self.total_pnl:,.0f}, WR: {self.win_rate}%)"


class TradingInsight(TimeStampedModel):
    """
    Individual trading insights for learning

    Stores specific learnings and patterns discovered
    """

    INSIGHT_TYPE_CHOICES = [
        ('FILTER', 'Filter Effectiveness'),
        ('ENTRY', 'Entry Timing'),
        ('EXIT', 'Exit Timing'),
        ('STRIKE', 'Strike Selection'),
        ('SIZING', 'Position Sizing'),
        ('PATTERN', 'Market Pattern'),
        ('CORRELATION', 'Market Correlation'),
        ('OTHER', 'Other'),
    ]

    insight_type = models.CharField(max_length=50, choices=INSIGHT_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField()

    # Associated trading date
    trading_date = models.DateField(db_index=True)

    # Insight details
    insight_data = models.JSONField(default=dict, help_text="Detailed insight data")

    # Confidence and validation
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Confidence in this insight (0-100)"
    )

    times_validated = models.IntegerField(default=0, help_text="How many times validated")
    times_contradicted = models.IntegerField(default=0, help_text="How many times contradicted")

    # Impact
    estimated_impact = models.CharField(
        max_length=20,
        choices=[('HIGH', 'High'), ('MEDIUM', 'Medium'), ('LOW', 'Low')],
        default='MEDIUM'
    )

    # Action taken
    action_recommended = models.TextField(blank=True)
    action_taken = models.BooleanField(default=False)
    action_taken_at = models.DateTimeField(null=True, blank=True)

    # Status
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'trading_insights'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-trading_date']),
            models.Index(fields=['insight_type']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.get_insight_type_display()}: {self.title}"


# Import Nifty Strangle Strategy models
from .models_strangle import NiftyMarketData, StrangleAlgorithmState
