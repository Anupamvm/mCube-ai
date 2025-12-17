"""
Broker models for mCube Trading System

This module contains models for broker data including limits, positions,
option chain quotes, and historical prices.
"""

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator

from apps.core.models import TimeStampedModel
from apps.core.constants import (
    BROKER_CHOICES,
    ORDER_TYPE_CHOICES,
    ORDER_STATUS_CHOICES,
    DIRECTION_CHOICES,
    ORDER_STATUS_PENDING,
)


class BrokerLimit(TimeStampedModel):
    """
    Broker account limits and margin data

    Stores current margin, funds, and limits fetched from broker APIs.
    Updated periodically via API sync tasks.

    Fields for ICICI Breeze:
        - bank_account, total_bank_balance, allocated_equity, allocated_fno
        - block_by_trade_fno, unallocated_balance, margin_available, margin_used

    Fields for Kotak Neo:
        - category, net_balance, collateral_value, margin_used, margin_used_percent
        - margin_warning_pct, exposure_margin_pct, span_margin_pct, board_lot_limit
    """

    broker = models.CharField(
        max_length=20,
        choices=BROKER_CHOICES,
        help_text="Broker name (KOTAK or ICICI)"
    )

    fetched_at = models.DateTimeField(
        help_text="When this data was fetched from broker API"
    )

    # ICICI Breeze specific fields
    bank_account = models.CharField(
        max_length=50,
        blank=True,
        help_text="Bank account number (Breeze)"
    )

    total_bank_balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total bank balance (Breeze)"
    )

    allocated_equity = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Allocated for equity trading (Breeze)"
    )

    allocated_fno = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Allocated for F&O trading (Breeze)"
    )

    block_by_trade_fno = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Margin blocked by F&O trades (Breeze)"
    )

    unallocated_balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Unallocated balance (Breeze)"
    )

    # Kotak Neo specific fields
    category = models.CharField(
        max_length=100,
        blank=True,
        help_text="Account category (Neo)"
    )

    net_balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Net account balance (Neo)"
    )

    collateral_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total collateral value (Neo)"
    )

    margin_used_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Percentage of margin used (Neo)"
    )

    margin_warning_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Margin warning percentage (Neo)"
    )

    exposure_margin_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Exposure margin percentage (Neo)"
    )

    span_margin_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="SPAN margin percentage (Neo)"
    )

    board_lot_limit = models.IntegerField(
        default=0,
        help_text="Board lot limit (Neo)"
    )

    # Common fields for both brokers
    margin_available = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Available margin for trading"
    )

    margin_used = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Margin currently used"
    )

    class Meta:
        db_table = 'broker_limits'
        verbose_name = 'Broker Limit'
        verbose_name_plural = 'Broker Limits'
        ordering = ['-fetched_at']
        indexes = [
            models.Index(fields=['broker', '-fetched_at']),
        ]

    def __str__(self):
        return f"{self.get_broker_display()} - {self.fetched_at}"


class BrokerPosition(TimeStampedModel):
    """
    Current positions from broker

    Represents a trading position fetched from broker API.
    Includes buy/sell quantities, P&L, and other position metrics.
    """

    broker = models.CharField(
        max_length=20,
        choices=BROKER_CHOICES,
        help_text="Broker name (KOTAK or ICICI)"
    )

    fetched_at = models.DateTimeField(
        help_text="When this position was fetched from broker API"
    )

    symbol = models.CharField(
        max_length=100,
        help_text="Trading symbol (e.g., NIFTY25DEC2025025000CE)"
    )

    exchange_segment = models.CharField(
        max_length=50,
        blank=True,
        help_text="Exchange segment (e.g., nse_fo, bse_fo)"
    )

    product = models.CharField(
        max_length=50,
        blank=True,
        help_text="Product type (e.g., MIS, NRML, CNC)"
    )

    buy_qty = models.IntegerField(
        default=0,
        help_text="Total buy quantity"
    )

    sell_qty = models.IntegerField(
        default=0,
        help_text="Total sell quantity"
    )

    net_quantity = models.IntegerField(
        default=0,
        help_text="Net quantity (buy_qty - sell_qty)"
    )

    buy_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total buy amount"
    )

    sell_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total sell amount"
    )

    ltp = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Last traded price"
    )

    average_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Average entry price"
    )

    realized_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Realized profit/loss"
    )

    unrealized_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Unrealized profit/loss (MTM)"
    )

    class Meta:
        db_table = 'broker_positions'
        verbose_name = 'Broker Position'
        verbose_name_plural = 'Broker Positions'
        ordering = ['-fetched_at', 'symbol']
        indexes = [
            models.Index(fields=['broker', '-fetched_at']),
            models.Index(fields=['symbol', '-fetched_at']),
        ]

    def __str__(self):
        return f"{self.get_broker_display()} - {self.symbol} ({self.net_quantity})"


class OptionChainQuote(TimeStampedModel):
    """
    Option chain quotes from Breeze API

    Stores real-time option chain data including strikes, premiums,
    open interest, and other option metrics.
    """

    exchange_code = models.CharField(
        max_length=10,
        help_text="Exchange code (e.g., NFO, NSE)"
    )

    product_type = models.CharField(
        max_length=20,
        help_text="Product type (options, futures)"
    )

    stock_code = models.CharField(
        max_length=50,
        help_text="Stock/index code (e.g., NIFTY, BANKNIFTY)"
    )

    expiry_date = models.DateField(
        help_text="Option expiry date"
    )

    right = models.CharField(
        max_length=10,
        help_text="Option right (call or put)"
    )

    strike_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Strike price"
    )

    ltp = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Last traded price"
    )

    best_bid_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Best bid price"
    )

    best_offer_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Best offer price"
    )

    open = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Opening price"
    )

    high = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="High price"
    )

    low = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Low price"
    )

    previous_close = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Previous close price"
    )

    open_interest = models.BigIntegerField(
        default=0,
        help_text="Open interest"
    )

    total_quantity_traded = models.BigIntegerField(
        default=0,
        help_text="Total quantity traded"
    )

    spot_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Underlying spot price at time of fetch"
    )

    class Meta:
        db_table = 'option_chain_quotes'
        verbose_name = 'Option Chain Quote'
        verbose_name_plural = 'Option Chain Quotes'
        ordering = ['-created_at', 'expiry_date', 'strike_price']
        indexes = [
            models.Index(fields=['stock_code', 'expiry_date', '-created_at']),
            models.Index(fields=['strike_price', 'right']),
        ]

    def __str__(self):
        return f"{self.stock_code} {self.expiry_date} {self.strike_price} {self.right.upper()}"


class NiftyOptionChain(TimeStampedModel):
    """
    Nifty Option Chain data fetched from Breeze API

    Stores comprehensive option chain data for NIFTY index including all expiries.
    Data is cleared before each fresh fetch to avoid cluttering.
    """

    expiry_date = models.DateField(
        help_text="Option expiry date"
    )

    strike_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Strike price"
    )

    option_type = models.CharField(
        max_length=10,
        choices=[('CE', 'Call'), ('PE', 'Put')],
        help_text="Option type (CE or PE)"
    )

    # Call Option Data
    call_ltp = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Call LTP"
    )

    call_bid = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Call best bid price"
    )

    call_ask = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Call best ask price"
    )

    call_oi = models.BigIntegerField(
        default=0,
        help_text="Call open interest"
    )

    call_volume = models.BigIntegerField(
        default=0,
        help_text="Call volume"
    )

    # Put Option Data
    put_ltp = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Put LTP"
    )

    put_bid = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Put best bid price"
    )

    put_ask = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Put best ask price"
    )

    put_oi = models.BigIntegerField(
        default=0,
        help_text="Put open interest"
    )

    put_volume = models.BigIntegerField(
        default=0,
        help_text="Put volume"
    )

    # Greeks - Call Option
    call_delta = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Call Delta (0 to 1)"
    )

    call_gamma = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Call Gamma"
    )

    call_theta = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Call Theta"
    )

    call_vega = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Call Vega"
    )

    call_iv = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Call Implied Volatility %"
    )

    # Greeks - Put Option
    put_delta = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Put Delta (-1 to 0)"
    )

    put_gamma = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Put Gamma"
    )

    put_theta = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Put Theta"
    )

    put_vega = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Put Vega"
    )

    put_iv = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Put Implied Volatility %"
    )

    # OI Change
    call_oi_change = models.BigIntegerField(
        default=0,
        help_text="Call OI change from previous day"
    )

    put_oi_change = models.BigIntegerField(
        default=0,
        help_text="Put OI change from previous day"
    )

    # PCR (Put-Call Ratio)
    pcr_oi = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="PCR based on OI (Put OI / Call OI)"
    )

    pcr_volume = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="PCR based on volume (Put Vol / Call Vol)"
    )

    # Helper fields for strangle strategy
    is_atm = models.BooleanField(
        default=False,
        help_text="True if this is ATM strike"
    )

    distance_from_spot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distance from spot price (strike - spot)"
    )

    # Common fields
    spot_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Nifty spot price at time of fetch"
    )

    class Meta:
        db_table = 'nifty_option_chain'
        verbose_name = 'Nifty Option Chain'
        verbose_name_plural = 'Nifty Option Chains'
        ordering = ['-created_at', 'expiry_date', 'strike_price']
        indexes = [
            models.Index(fields=['expiry_date', 'strike_price']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"NIFTY {self.expiry_date} {self.strike_price} {self.option_type}"


class HistoricalPrice(TimeStampedModel):
    """
    Historical OHLCV data from Breeze API

    Stores historical price data for stocks, futures, and options.
    Used for backtesting and technical analysis.
    """

    datetime = models.DateTimeField(
        db_index=True,
        help_text="Candle timestamp"
    )

    stock_code = models.CharField(
        max_length=50,
        help_text="Stock/index code (e.g., NIFTY, ICICIBANK)"
    )

    exchange_code = models.CharField(
        max_length=10,
        help_text="Exchange code (NSE, NFO, BSE)"
    )

    product_type = models.CharField(
        max_length=20,
        help_text="Product type (cash, futures, options)"
    )

    # Optional fields for derivatives
    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Expiry date (for futures/options)"
    )

    right = models.CharField(
        max_length=10,
        blank=True,
        help_text="Option right (call/put, empty for futures/cash)"
    )

    strike_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Strike price (for options)"
    )

    # OHLCV data
    open = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Open price"
    )

    high = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="High price"
    )

    low = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Low price"
    )

    close = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Close price"
    )

    volume = models.BigIntegerField(
        default=0,
        help_text="Volume traded"
    )

    open_interest = models.BigIntegerField(
        default=0,
        help_text="Open interest (for derivatives)"
    )

    class Meta:
        db_table = 'historical_prices'
        verbose_name = 'Historical Price'
        verbose_name_plural = 'Historical Prices'
        ordering = ['-datetime']
        indexes = [
            models.Index(fields=['stock_code', 'product_type', '-datetime']),
            models.Index(fields=['datetime']),
        ]
        unique_together = [
            ['datetime', 'stock_code', 'exchange_code', 'product_type',
             'expiry_date', 'right', 'strike_price']
        ]

    def __str__(self):
        base = f"{self.stock_code} {self.datetime.date()}"
        if self.product_type == 'options' and self.strike_price:
            return f"{base} {self.strike_price} {self.right.upper()}"
        elif self.product_type == 'futures' and self.expiry_date:
            return f"{base} FUT {self.expiry_date}"
        return base


# =============================================================================
# Order Models (merged from orders app)
# =============================================================================

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
