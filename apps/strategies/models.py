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
