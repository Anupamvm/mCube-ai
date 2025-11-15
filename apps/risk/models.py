"""
Risk management models for mCube Trading System

This module contains models for risk limits and circuit breakers.
"""

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator

from apps.core.models import TimeStampedModel
from apps.core.constants import RISK_LEVEL_CHOICES


class RiskLimit(TimeStampedModel):
    """
    Risk limit tracking model

    Tracks risk limits and current utilization for accounts.

    Fields:
        account: Associated broker account
        limit_type: Type of limit (DAILY, WEEKLY, MONTHLY, POSITION)
        limit_value: Maximum limit value
        current_value: Current utilization
        is_breached: Whether limit is breached
    """

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='risk_limits',
        help_text="Associated broker account"
    )

    limit_type = models.CharField(
        max_length=50,
        help_text="Type of limit (DAILY_LOSS, WEEKLY_LOSS, POSITION_SIZE, etc.)"
    )

    limit_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Maximum limit value"
    )

    current_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Current utilization"
    )

    is_breached = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this limit is currently breached"
    )

    breach_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the limit was breached"
    )

    # Tracking period
    period_start = models.DateField(
        help_text="Start of tracking period"
    )

    period_end = models.DateField(
        null=True,
        blank=True,
        help_text="End of tracking period"
    )

    # Alerts
    warning_threshold_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('80.00'),
        help_text="Send warning when utilization reaches this % of limit"
    )

    warning_sent = models.BooleanField(
        default=False,
        help_text="Whether warning alert was sent"
    )

    notes = models.TextField(
        blank=True,
        help_text="Any additional notes"
    )

    class Meta:
        db_table = 'risk_limits'
        verbose_name = 'Risk Limit'
        verbose_name_plural = 'Risk Limits'
        unique_together = ['account', 'limit_type', 'period_start']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'is_breached']),
        ]

    def __str__(self):
        return (
            f"{self.limit_type} - {self.account.account_name} - "
            f"{self.current_value}/{self.limit_value}"
        )

    def get_utilization_pct(self) -> Decimal:
        """
        Calculate utilization percentage

        Returns:
            Decimal: Utilization percentage
        """
        if self.limit_value == 0:
            return Decimal('0.00')

        return (self.current_value / self.limit_value) * 100

    def check_breach(self) -> bool:
        """
        Check if limit is breached

        Returns:
            bool: True if breached
        """
        return self.current_value >= self.limit_value

    def check_warning(self) -> bool:
        """
        Check if warning threshold is reached

        Returns:
            bool: True if warning threshold reached
        """
        utilization = self.get_utilization_pct()
        return utilization >= self.warning_threshold_pct

    def update_value(self, new_value: Decimal):
        """
        Update current value and check for breach

        Args:
            new_value: New current value
        """
        self.current_value = new_value

        # Check for breach
        if self.check_breach() and not self.is_breached:
            from django.utils import timezone
            self.is_breached = True
            self.breach_timestamp = timezone.now()

        # Check for warning
        if self.check_warning() and not self.warning_sent:
            self.warning_sent = True

        self.save()

    def reset(self):
        """Reset the limit for new period"""
        from datetime import date

        self.current_value = Decimal('0.00')
        self.is_breached = False
        self.warning_sent = False
        self.breach_timestamp = None
        self.period_start = date.today()
        self.save()


class CircuitBreaker(TimeStampedModel):
    """
    Circuit breaker model

    Tracks circuit breaker events and account shutdowns.

    A circuit breaker is triggered when critical risk limits are breached,
    resulting in automatic account deactivation and position closure.

    Fields:
        account: Associated broker account
        trigger_type: What triggered the circuit breaker
        trigger_value: Value that triggered it
        threshold_value: Threshold that was breached
        risk_level: Risk level (HIGH, CRITICAL)
        is_active: Whether circuit breaker is currently active
        positions_closed: How many positions were auto-closed
    """

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='circuit_breakers',
        help_text="Associated broker account"
    )

    trigger_type = models.CharField(
        max_length=50,
        help_text="What triggered the circuit breaker (DAILY_LOSS, WEEKLY_LOSS, DRAWDOWN)"
    )

    trigger_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Value that triggered the circuit breaker"
    )

    threshold_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Threshold value that was breached"
    )

    risk_level = models.CharField(
        max_length=20,
        choices=RISK_LEVEL_CHOICES,
        default='CRITICAL',
        help_text="Risk level"
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether circuit breaker is currently active"
    )

    # Actions taken
    account_deactivated = models.BooleanField(
        default=False,
        help_text="Whether account was deactivated"
    )

    positions_closed = models.IntegerField(
        default=0,
        help_text="Number of positions auto-closed"
    )

    orders_cancelled = models.IntegerField(
        default=0,
        help_text="Number of pending orders cancelled"
    )

    # Recovery
    reset_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When circuit breaker was reset"
    )

    reset_by = models.CharField(
        max_length=100,
        blank=True,
        help_text="Who reset the circuit breaker"
    )

    # Cooldown period
    cooldown_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Account cannot trade until this time"
    )

    # Details
    description = models.TextField(
        help_text="Detailed description of what happened"
    )

    actions_log = models.JSONField(
        default=list,
        help_text="Log of all actions taken"
    )

    class Meta:
        db_table = 'circuit_breakers'
        verbose_name = 'Circuit Breaker'
        verbose_name_plural = 'Circuit Breakers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'is_active']),
        ]

    def __str__(self):
        return (
            f"Circuit Breaker - {self.account.account_name} - "
            f"{self.trigger_type} - {'ACTIVE' if self.is_active else 'RESET'}"
        )

    def add_action(self, action: str):
        """
        Add an action to the log

        Args:
            action: Description of action taken
        """
        from django.utils import timezone

        self.actions_log.append({
            'timestamp': timezone.now().isoformat(),
            'action': action
        })
        self.save(update_fields=['actions_log', 'updated_at'])

    def reset_breaker(self, reset_by: str = "SYSTEM"):
        """
        Reset the circuit breaker

        Args:
            reset_by: Who is resetting (SYSTEM, ADMIN, etc.)
        """
        from django.utils import timezone

        self.is_active = False
        self.reset_at = timezone.now()
        self.reset_by = reset_by
        self.add_action(f"Circuit breaker reset by {reset_by}")
        self.save()
