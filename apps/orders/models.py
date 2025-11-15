"""
Order models for mCube Trading System

This module contains models for order management and execution tracking.
"""

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator

from apps.core.models import TimeStampedModel
from apps.core.constants import (
    ORDER_TYPE_CHOICES,
    ORDER_STATUS_CHOICES,
    DIRECTION_CHOICES,
    ORDER_STATUS_PENDING,
)


class Order(TimeStampedModel):
    """
    Order model

    Tracks all orders placed with the broker.

    Fields:
        account: Associated broker account
        position: Associated position (if any)
        order_type: MARKET, LIMIT, SL, SLM
        direction: LONG or SHORT
        instrument: Instrument symbol
        quantity: Order quantity
        price: Order price (for LIMIT orders)
        trigger_price: Trigger price (for SL orders)
        status: Order status
        broker_order_id: Order ID from broker
        message: Status message from broker
    """

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='orders',
        help_text="Associated broker account"
    )

    position = models.ForeignKey(
        'positions.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        help_text="Associated position (if any)"
    )

    # Order details
    order_type = models.CharField(
        max_length=20,
        choices=ORDER_TYPE_CHOICES,
        help_text="Order type (MARKET, LIMIT, SL, SLM)"
    )

    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        help_text="Order direction (LONG or SHORT)"
    )

    instrument = models.CharField(
        max_length=100,
        help_text="Instrument symbol"
    )

    exchange = models.CharField(
        max_length=20,
        default='NSE',
        help_text="Exchange (NSE, BSE, NFO)"
    )

    # Quantity and pricing
    quantity = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Order quantity"
    )

    price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Order price (for LIMIT orders)"
    )

    trigger_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Trigger price (for SL orders)"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        default=ORDER_STATUS_PENDING,
        choices=ORDER_STATUS_CHOICES,
        db_index=True,
        help_text="Order status"
    )

    broker_order_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Order ID from broker"
    )

    message = models.TextField(
        blank=True,
        help_text="Status message from broker"
    )

    # Execution tracking
    filled_quantity = models.IntegerField(
        default=0,
        help_text="Quantity filled"
    )

    average_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average execution price"
    )

    # Timestamps
    placed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When order was placed with broker"
    )

    filled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When order was fully filled"
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When order was cancelled"
    )

    # Purpose tracking
    purpose = models.CharField(
        max_length=50,
        blank=True,
        help_text="Purpose (ENTRY, EXIT, AVERAGING, ADJUSTMENT)"
    )

    notes = models.TextField(
        blank=True,
        help_text="Any additional notes"
    )

    class Meta:
        db_table = 'orders'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['broker_order_id']),
        ]

    def __str__(self):
        return (
            f"{self.get_order_type_display()} {self.direction} "
            f"{self.instrument} x{self.quantity} - {self.get_status_display()}"
        )

    def is_pending(self) -> bool:
        """Check if order is pending"""
        return self.status == 'PENDING'

    def is_filled(self) -> bool:
        """Check if order is fully filled"""
        return self.status == 'FILLED'

    def is_partially_filled(self) -> bool:
        """Check if order is partially filled"""
        return self.status == 'PARTIAL'

    def mark_placed(self, broker_order_id: str):
        """
        Mark order as placed with broker

        Args:
            broker_order_id: Order ID from broker
        """
        from django.utils import timezone

        self.broker_order_id = broker_order_id
        self.status = 'PLACED'
        self.placed_at = timezone.now()
        self.save()

    def mark_filled(self, average_price: Decimal, filled_quantity: int = None):
        """
        Mark order as filled

        Args:
            average_price: Average execution price
            filled_quantity: Quantity filled (defaults to order quantity)
        """
        from django.utils import timezone

        self.average_price = average_price
        self.filled_quantity = filled_quantity or self.quantity
        self.status = 'FILLED'
        self.filled_at = timezone.now()
        self.save()

    def mark_cancelled(self, reason: str = ""):
        """
        Mark order as cancelled

        Args:
            reason: Cancellation reason
        """
        from django.utils import timezone

        self.status = 'CANCELLED'
        self.cancelled_at = timezone.now()
        if reason:
            self.message = reason
        self.save()

    def mark_rejected(self, reason: str):
        """
        Mark order as rejected

        Args:
            reason: Rejection reason
        """
        self.status = 'REJECTED'
        self.message = reason
        self.save()


class Execution(TimeStampedModel):
    """
    Order execution model

    Tracks individual executions/fills for an order.
    An order can have multiple executions if partially filled.

    Fields:
        order: Associated order
        execution_id: Unique execution ID from broker
        quantity: Quantity filled in this execution
        price: Execution price
        timestamp: Execution timestamp
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='executions',
        help_text="Associated order"
    )

    execution_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique execution ID from broker"
    )

    quantity = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Quantity filled in this execution"
    )

    price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Execution price"
    )

    exchange_timestamp = models.DateTimeField(
        help_text="Execution timestamp from exchange"
    )

    # Additional details
    exchange = models.CharField(
        max_length=20,
        blank=True,
        help_text="Exchange where executed"
    )

    transaction_type = models.CharField(
        max_length=10,
        help_text="BUY or SELL"
    )

    class Meta:
        db_table = 'executions'
        verbose_name = 'Execution'
        verbose_name_plural = 'Executions'
        ordering = ['-exchange_timestamp']
        indexes = [
            models.Index(fields=['order', 'exchange_timestamp']),
        ]

    def __str__(self):
        return (
            f"Execution {self.execution_id} - "
            f"{self.quantity} @ {self.price}"
        )
