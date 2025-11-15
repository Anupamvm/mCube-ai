"""
Position models for mCube Trading System

This module contains models for tracking trading positions and their monitoring.

CRITICAL: Enforces ONE POSITION PER ACCOUNT rule
"""

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator

from apps.core.models import TimeStampedModel
from apps.core.constants import (
    DIRECTION_CHOICES,
    POSITION_STATUS_CHOICES,
    POSITION_STATUS_ACTIVE,
    POSITION_STATUS_CLOSED,
)


class Position(TimeStampedModel):
    """
    Position model

    Tracks all trading positions (options strangles and futures).

    CRITICAL: ONE POSITION PER ACCOUNT enforced at application level
    Before ANY new position entry, must check has_active_position()

    Fields:
        account: Associated broker account
        strategy_type: Type of strategy (STRANGLE, FUTURES)
        instrument: Instrument name (NIFTY, RELIANCE, etc.)
        direction: LONG, SHORT, or NEUTRAL (for strangles)
        quantity: Lot quantity
        entry_price: Entry price
        current_price: Current market price
        stop_loss: Stop-loss price
        target: Target price
        expiry_date: Contract expiry date
        margin_used: Margin blocked for this position
        entry_value: Total entry value
        status: ACTIVE or CLOSED
        realized_pnl: P&L after closing (if closed)
        unrealized_pnl: Current P&L (if active)
    """

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='positions',
        help_text="Associated broker account"
    )

    strategy_type = models.CharField(
        max_length=50,
        help_text="Type of strategy (WEEKLY_NIFTY_STRANGLE, LLM_VALIDATED_FUTURES)"
    )

    instrument = models.CharField(
        max_length=100,
        help_text="Instrument name (NIFTY, BANKNIFTY, RELIANCE, etc.)"
    )

    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        help_text="Position direction (LONG, SHORT, NEUTRAL)"
    )

    # Position sizing
    quantity = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Lot quantity"
    )

    lot_size = models.IntegerField(
        default=1,
        help_text="Lot size for the instrument"
    )

    # Pricing
    entry_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Entry price"
    )

    current_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Current market price"
    )

    stop_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Stop-loss price"
    )

    target = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Target price"
    )

    # Strangle-specific fields
    call_strike = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Call strike (for strangles)"
    )

    put_strike = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Put strike (for strangles)"
    )

    call_premium = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Call premium collected"
    )

    put_premium = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Put premium collected"
    )

    premium_collected = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total premium collected (call + put)"
    )

    current_delta = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Current net delta (for options)"
    )

    # Expiry and margin
    expiry_date = models.DateField(
        help_text="Contract expiry date"
    )

    margin_used = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Margin blocked for this position"
    )

    entry_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Total entry value (quantity * price * lot_size)"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        default=POSITION_STATUS_ACTIVE,
        choices=POSITION_STATUS_CHOICES,
        db_index=True,
        help_text="Position status (ACTIVE or CLOSED)"
    )

    entry_time = models.DateTimeField(
        auto_now_add=True,
        help_text="When position was entered"
    )

    exit_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When position was exited"
    )

    exit_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Exit price"
    )

    exit_reason = models.CharField(
        max_length=100,
        blank=True,
        help_text="Reason for exit (TARGET, STOP_LOSS, EOD, MANUAL, etc.)"
    )

    # P&L tracking
    realized_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Realized P&L (after closing)"
    )

    unrealized_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Unrealized P&L (while active)"
    )

    # Averaging (futures only)
    averaging_count = models.IntegerField(
        default=0,
        help_text="Number of times position was averaged"
    )

    original_entry_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original entry price before averaging"
    )

    # Partial booking
    partial_booked = models.BooleanField(
        default=False,
        help_text="Whether partial profit was booked"
    )

    partial_quantity = models.IntegerField(
        default=0,
        help_text="Quantity booked in partial exit"
    )

    # Additional metadata
    notes = models.TextField(
        blank=True,
        help_text="Any additional notes about this position"
    )

    class Meta:
        db_table = 'positions'
        verbose_name = 'Position'
        verbose_name_plural = 'Positions'
        ordering = ['-entry_time']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['status', 'expiry_date']),
        ]

    def __str__(self):
        return (
            f"{self.instrument} {self.direction} - "
            f"{self.get_status_display()} - "
            f"{self.account.account_name}"
        )

    @classmethod
    def has_active_position(cls, account) -> bool:
        """
        Check if active position exists - ONE POSITION RULE

        CRITICAL: This must be called before ANY new position entry

        Args:
            account: BrokerAccount instance

        Returns:
            bool: True if active position exists

        Example:
            >>> if Position.has_active_position(account):
            ...     raise ValueError("Cannot enter new position - ONE POSITION RULE")
        """
        return cls.objects.filter(
            account=account,
            status=POSITION_STATUS_ACTIVE
        ).exists()

    @classmethod
    def get_active_position(cls, account):
        """
        Get active position for account

        Args:
            account: BrokerAccount instance

        Returns:
            Position or None: Active position if exists
        """
        return cls.objects.filter(
            account=account,
            status=POSITION_STATUS_ACTIVE
        ).first()

    def update_current_price(self, price: Decimal):
        """
        Update current price and recalculate unrealized P&L

        Args:
            price: Current market price
        """
        self.current_price = price
        self.unrealized_pnl = self.calculate_unrealized_pnl()
        self.save(update_fields=['current_price', 'unrealized_pnl', 'updated_at'])

    def calculate_unrealized_pnl(self) -> Decimal:
        """
        Calculate unrealized P&L for active position

        Returns:
            Decimal: Unrealized P&L
        """
        if self.status != POSITION_STATUS_ACTIVE:
            return Decimal('0.00')

        if self.direction == 'LONG':
            pnl_per_unit = self.current_price - self.entry_price
        elif self.direction == 'SHORT':
            pnl_per_unit = self.entry_price - self.current_price
        else:  # NEUTRAL (strangle)
            # For strangles, P&L is premium collected minus current value
            pnl_per_unit = self.premium_collected - self.current_price

        total_pnl = pnl_per_unit * self.quantity * self.lot_size
        return total_pnl

    def close_position(self, exit_price: Decimal, exit_reason: str = "MANUAL"):
        """
        Close the position and calculate realized P&L

        Args:
            exit_price: Exit price
            exit_reason: Reason for exit
        """
        from django.utils import timezone

        self.exit_price = exit_price
        self.exit_time = timezone.now()
        self.exit_reason = exit_reason
        self.status = POSITION_STATUS_CLOSED

        # Calculate realized P&L
        if self.direction == 'LONG':
            pnl_per_unit = exit_price - self.entry_price
        elif self.direction == 'SHORT':
            pnl_per_unit = self.entry_price - exit_price
        else:  # NEUTRAL (strangle)
            pnl_per_unit = self.premium_collected - exit_price

        self.realized_pnl = pnl_per_unit * self.quantity * self.lot_size
        self.unrealized_pnl = Decimal('0.00')

        self.save()

    def is_stop_loss_hit(self) -> bool:
        """
        Check if stop-loss is hit

        Returns:
            bool: True if stop-loss hit
        """
        if self.status != POSITION_STATUS_ACTIVE:
            return False

        if self.direction == 'LONG':
            return self.current_price <= self.stop_loss
        elif self.direction == 'SHORT':
            return self.current_price >= self.stop_loss
        else:  # NEUTRAL (strangle)
            # For strangles, stop-loss is hit when current price >= stop_loss
            return self.current_price >= self.stop_loss

    def is_target_hit(self) -> bool:
        """
        Check if target is hit

        Returns:
            bool: True if target hit
        """
        if self.status != POSITION_STATUS_ACTIVE:
            return False

        if self.direction == 'LONG':
            return self.current_price >= self.target
        elif self.direction == 'SHORT':
            return self.current_price <= self.target
        else:  # NEUTRAL (strangle)
            # For strangles, target is hit when current price <= target
            return self.current_price <= self.target


class MonitorLog(TimeStampedModel):
    """
    Position monitoring log

    Tracks position monitoring events and alerts.

    Fields:
        position: Associated position
        check_type: Type of check (PRICE, SL, TARGET, DELTA, etc.)
        result: Result of the check
        message: Detailed message
        action_taken: Any action taken
    """

    position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name='monitor_logs',
        help_text="Associated position"
    )

    check_type = models.CharField(
        max_length=50,
        help_text="Type of check (PRICE_UPDATE, SL_CHECK, TARGET_CHECK, DELTA_CHECK)"
    )

    result = models.CharField(
        max_length=20,
        help_text="Result (OK, WARNING, ALERT, ACTION_REQUIRED)"
    )

    message = models.TextField(
        help_text="Detailed message about the check"
    )

    action_taken = models.CharField(
        max_length=100,
        blank=True,
        help_text="Any action taken (ALERT_SENT, POSITION_CLOSED, etc.)"
    )

    # Snapshot data
    price_at_check = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price at time of check"
    )

    pnl_at_check = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="P&L at time of check"
    )

    class Meta:
        db_table = 'monitor_logs'
        verbose_name = 'Monitor Log'
        verbose_name_plural = 'Monitor Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['position', 'check_type']),
        ]

    def __str__(self):
        return f"{self.check_type} - {self.result} - {self.position}"
