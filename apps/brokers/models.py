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

    # Data interval
    interval = models.CharField(
        max_length=10,
        default='1day',
        help_text="Candle interval (1minute, 5minute, 30minute, 1day)"
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
            models.Index(fields=['stock_code', 'exchange_code', 'product_type', 'interval', '-datetime']),
            models.Index(fields=['stock_code', 'expiry_date', 'strike_price']),
            models.Index(fields=['datetime']),
        ]
        unique_together = [
            ['datetime', 'stock_code', 'exchange_code', 'product_type', 'interval',
             'expiry_date', 'right', 'strike_price']
        ]

    def __str__(self):
        base = f"{self.stock_code} {self.datetime.date()}"
        if self.product_type == 'options' and self.strike_price:
            return f"{base} {self.strike_price} {self.right.upper()}"
        elif self.product_type == 'futures' and self.expiry_date:
            return f"{base} FUT {self.expiry_date}"
        return base

    @classmethod
    def replace_data(cls, stock_code, exchange_code, product_type, interval,
                     data_points, expiry_date=None, strike_price=None, right=''):
        """
        Delete existing data for the instrument and save fresh data.

        Args:
            stock_code: Stock code (e.g., 'RELIND', 'ITC')
            exchange_code: Exchange code (e.g., 'NSE', 'NFO')
            product_type: 'cash', 'futures', 'options', 'btst', 'margin'
            interval: '1minute', '5minute', '30minute', '1day'
            data_points: List of dicts from Breeze API Success response
            expiry_date: For F&O instruments (datetime.date object)
            strike_price: For options (Decimal)
            right: 'call', 'put', 'others' for options

        Returns:
            Tuple: (deleted_count, created_count)

        Example:
            HistoricalPrice.replace_data(
                stock_code='ITC',
                exchange_code='NSE',
                product_type='cash',
                interval='1minute',
                data_points=response['Success']
            )
        """
        from decimal import Decimal
        from datetime import datetime
        import pytz

        # IST timezone for Breeze API data
        ist = pytz.timezone('Asia/Kolkata')

        # Build filter for existing data
        filter_params = {
            'stock_code': stock_code,
            'exchange_code': exchange_code,
            'product_type': product_type,
            'interval': interval,
        }

        # Add F&O specific filters
        if product_type in ['futures', 'options']:
            filter_params['expiry_date'] = expiry_date

        if product_type == 'options':
            filter_params['strike_price'] = strike_price
            filter_params['right'] = right

        # Delete existing data for this instrument
        deleted_count = cls.objects.filter(**filter_params).delete()[0]

        # Create new records
        new_records = []
        for point in data_points:
            # Parse datetime string from API and make timezone-aware (IST)
            dt = datetime.strptime(point['datetime'], '%Y-%m-%d %H:%M:%S')
            # Breeze API returns IST times, make them timezone-aware
            dt = ist.localize(dt)

            record = cls(
                stock_code=stock_code,
                exchange_code=exchange_code,
                product_type=product_type,
                interval=interval,
                expiry_date=expiry_date,
                strike_price=Decimal(strike_price) if strike_price else None,
                right=right,
                datetime=dt,
                open=Decimal(point['open']),
                high=Decimal(point['high']),
                low=Decimal(point['low']),
                close=Decimal(point['close']),
                volume=int(point['volume']),
                open_interest=int(point['open_interest']) if point.get('open_interest') else 0,
            )
            new_records.append(record)

        # Bulk create for efficiency
        created = cls.objects.bulk_create(new_records, ignore_conflicts=True)

        return (deleted_count, len(created))

    @classmethod
    def get_latest_data(cls, stock_code, exchange_code, product_type, interval,
                        expiry_date=None, strike_price=None, right='', limit=100):
        """
        Retrieve latest historical data for an instrument.

        Args:
            stock_code: Stock code
            exchange_code: Exchange code
            product_type: Product type
            interval: Candle interval
            expiry_date: For F&O
            strike_price: For options
            right: For options
            limit: Number of latest candles to retrieve

        Returns:
            QuerySet of HistoricalPrice ordered by datetime descending
        """
        filter_params = {
            'stock_code': stock_code,
            'exchange_code': exchange_code,
            'product_type': product_type,
            'interval': interval,
        }

        if product_type in ['futures', 'options']:
            filter_params['expiry_date'] = expiry_date

        if product_type == 'options':
            filter_params['strike_price'] = strike_price
            filter_params['right'] = right

        return cls.objects.filter(**filter_params).order_by('-datetime')[:limit]


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
            models.Index(fields=['account', 'status'], name='orders_account_ca00e7_idx'),
            models.Index(fields=['broker_order_id'], name='orders_broker__a04e54_idx'),
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
            models.Index(fields=['order', 'exchange_timestamp'], name='executions_order_i_5ef1c4_idx'),
        ]

    def __str__(self):
        return (
            f"Execution {self.execution_id} - "
            f"{self.quantity} @ {self.price}"
        )


class BrokerTradeHistory(TimeStampedModel):
    """
    Historical trade records from broker APIs with deduplication.

    Stores executed trades synced from Kotak Neo and ICICI Breeze APIs.
    Used for reconciliation, reporting, and FY performance analysis.
    """

    BROKER_CHOICES = [
        ('KOTAK', 'Kotak Neo'),
        ('ICICI', 'ICICI Breeze'),
    ]

    TRADE_TYPE_CHOICES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ]

    SEGMENT_CHOICES = [
        ('NFO', 'NSE F&O'),
        ('NSE', 'NSE Cash'),
        ('BSE', 'BSE Cash'),
        ('BFO', 'BSE F&O'),
    ]

    PRODUCT_TYPE_CHOICES = [
        ('NRML', 'Normal'),
        ('MIS', 'Intraday'),
        ('CNC', 'Delivery'),
    ]

    # Broker Reference
    broker = models.CharField(
        max_length=10,
        choices=BROKER_CHOICES,
        help_text="Broker name"
    )
    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='trade_history',
        help_text="Associated broker account"
    )

    # Unique Identifiers from Broker
    trade_id = models.CharField(
        max_length=100,
        help_text="Trade ID from broker"
    )
    order_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Order ID from broker"
    )

    # Trade Details
    symbol = models.CharField(
        max_length=50,
        help_text="Base symbol (e.g., NIFTY, RELIANCE)"
    )
    trading_symbol = models.CharField(
        max_length=100,
        help_text="Full trading symbol (e.g., NIFTY25JAN23500CE)"
    )
    segment = models.CharField(
        max_length=10,
        choices=SEGMENT_CHOICES,
        default='NFO',
        help_text="Exchange segment"
    )

    # Transaction Details
    trade_type = models.CharField(
        max_length=10,
        choices=TRADE_TYPE_CHOICES,
        help_text="Buy or Sell"
    )
    product_type = models.CharField(
        max_length=10,
        choices=PRODUCT_TYPE_CHOICES,
        default='NRML',
        help_text="Product type"
    )

    # Quantity and Price
    quantity = models.IntegerField(
        help_text="Trade quantity"
    )
    price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Trade price"
    )
    trade_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total trade value (quantity * price)"
    )

    # Timing
    trade_date = models.DateField(
        help_text="Trade execution date"
    )
    trade_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Trade execution time"
    )
    trade_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Combined trade datetime"
    )

    # Options/Futures specific
    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Expiry date for F&O"
    )
    strike_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Strike price for options"
    )
    option_type = models.CharField(
        max_length=5,
        blank=True,
        help_text="CE or PE for options"
    )

    # Charges
    brokerage = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Brokerage charges"
    )
    stt = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Securities Transaction Tax"
    )
    exchange_charges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Exchange transaction charges"
    )
    gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="GST on brokerage"
    )
    stamp_duty = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Stamp duty"
    )
    total_charges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total of all charges"
    )

    # Raw data from API
    raw_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw response data from broker API"
    )

    # Reconciliation
    is_reconciled = models.BooleanField(
        default=False,
        help_text="Whether matched with TakenTrade"
    )
    taken_trade = models.ForeignKey(
        'trading.TakenTrade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='broker_trades',
        help_text="Linked TakenTrade if reconciled"
    )

    class Meta:
        db_table = 'broker_trade_history'
        verbose_name = 'Broker Trade History'
        verbose_name_plural = 'Broker Trade Histories'
        ordering = ['-trade_date', '-trade_time']
        constraints = [
            models.UniqueConstraint(
                fields=['broker', 'trade_id', 'trade_date'],
                name='unique_broker_trade'
            )
        ]
        indexes = [
            models.Index(fields=['account', 'trade_date']),
            models.Index(fields=['broker', 'trade_date']),
            models.Index(fields=['symbol', 'trade_date']),
            models.Index(fields=['is_reconciled']),
        ]

    def __str__(self):
        return f"{self.broker} {self.trade_type} {self.trading_symbol} x{self.quantity} @ {self.price}"

    def save(self, *args, **kwargs):
        # Auto-calculate trade value if not set
        if self.trade_value is None and self.quantity and self.price:
            self.trade_value = self.quantity * self.price

        # Auto-calculate total charges
        self.total_charges = (
            self.brokerage +
            self.stt +
            self.exchange_charges +
            self.gst +
            self.stamp_duty
        )
        super().save(*args, **kwargs)

    @classmethod
    def sync_from_api(cls, account, trade_data, broker):
        """
        Create or update trade history from API data.
        Uses get_or_create pattern for deduplication.

        Args:
            account: BrokerAccount instance
            trade_data: Dict with trade details from broker API
            broker: 'KOTAK' or 'ICICI'

        Returns:
            Tuple: (BrokerTradeHistory instance, created: bool)
        """
        trade_id = trade_data.get('trade_id') or trade_data.get('tradeId')
        trade_date = trade_data.get('trade_date')

        if isinstance(trade_date, str):
            from datetime import datetime
            trade_date = datetime.strptime(trade_date, '%Y-%m-%d').date()

        defaults = {
            'account': account,
            'order_id': trade_data.get('order_id', ''),
            'symbol': trade_data.get('symbol', ''),
            'trading_symbol': trade_data.get('trading_symbol', ''),
            'segment': trade_data.get('segment', 'NFO'),
            'trade_type': trade_data.get('trade_type', 'BUY'),
            'product_type': trade_data.get('product_type', 'NRML'),
            'quantity': trade_data.get('quantity', 0),
            'price': Decimal(str(trade_data.get('price', 0))),
            'trade_value': Decimal(str(trade_data.get('trade_value', 0))) if trade_data.get('trade_value') else None,
            'trade_time': trade_data.get('trade_time'),
            'trade_datetime': trade_data.get('trade_datetime'),
            'expiry_date': trade_data.get('expiry_date'),
            'strike_price': Decimal(str(trade_data.get('strike_price'))) if trade_data.get('strike_price') else None,
            'option_type': trade_data.get('option_type', ''),
            'brokerage': Decimal(str(trade_data.get('brokerage', 0))),
            'stt': Decimal(str(trade_data.get('stt', 0))),
            'exchange_charges': Decimal(str(trade_data.get('exchange_charges', 0))),
            'gst': Decimal(str(trade_data.get('gst', 0))),
            'stamp_duty': Decimal(str(trade_data.get('stamp_duty', 0))),
            'raw_data': trade_data,
        }

        return cls.objects.get_or_create(
            broker=broker,
            trade_id=trade_id,
            trade_date=trade_date,
            defaults=defaults
        )


# =============================================================================
# CSV Import Models
# =============================================================================

class CSVImportLog(TimeStampedModel):
    """
    Track CSV imports for audit and rollback purposes.
    """

    FILE_TYPE_CHOICES = [
        ('KOTAK_FNO', 'Kotak F&O Gain/Loss'),
        ('BREEZE_FNO', 'Breeze FNO Portfolio'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SUCCESS', 'Success'),
        ('PARTIAL', 'Partial Success'),
        ('FAILED', 'Failed'),
    ]

    import_batch_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique batch ID for grouping imports"
    )

    file_type = models.CharField(
        max_length=20,
        choices=FILE_TYPE_CHOICES,
        help_text="Type of CSV file imported"
    )

    original_filename = models.CharField(
        max_length=255,
        help_text="Original filename uploaded"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        help_text="Import status"
    )

    records_created = models.IntegerField(
        default=0,
        help_text="Number of records created"
    )

    records_updated = models.IntegerField(
        default=0,
        help_text="Number of records updated"
    )

    records_skipped = models.IntegerField(
        default=0,
        help_text="Number of records skipped"
    )

    errors = models.JSONField(
        default=list,
        blank=True,
        help_text="List of error messages"
    )

    imported_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who performed the import"
    )

    class Meta:
        db_table = 'csv_import_logs'
        verbose_name = 'CSV Import Log'
        verbose_name_plural = 'CSV Import Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.file_type} - {self.import_batch_id} ({self.status})"


class BrokerContractPnL(TimeStampedModel):
    """
    Aggregated contract-level P&L from CSV imports.

    Unlike BrokerTradeHistory (individual trades), this stores
    aggregated P&L per contract from broker statements.
    """

    BROKER_CHOICES = [
        ('KOTAK', 'Kotak Neo'),
        ('ICICI', 'ICICI Breeze'),
    ]

    SEGMENT_CHOICES = [
        ('FUTURES', 'Futures'),
        ('OPTIONS', 'Options'),
        ('EQUITY', 'Equity'),
        ('MUTUAL_FUND', 'Mutual Fund'),
        ('ETF', 'ETF'),
    ]

    SECURITY_TYPE_CHOICES = [
        ('FUTSTK', 'Stock Futures'),
        ('FUTIDX', 'Index Futures'),
        ('OPTSTK', 'Stock Options'),
        ('OPTIDX', 'Index Options'),
        ('EQUITY_STOCK', 'Equity Stock'),
        ('MUTUAL_FUND', 'Mutual Fund'),
        ('ETF', 'ETF'),
    ]

    # Broker and import tracking
    broker = models.CharField(
        max_length=10,
        choices=BROKER_CHOICES,
        help_text="Broker name"
    )

    import_batch_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Links to CSVImportLog batch"
    )

    # Contract identification
    symbol = models.CharField(
        max_length=50,
        help_text="Base symbol (e.g., NIFTY, BANKNIFTY, HDFCBANK)"
    )

    trading_symbol = models.CharField(
        max_length=200,
        help_text="Full contract name from CSV"
    )

    segment = models.CharField(
        max_length=15,
        choices=SEGMENT_CHOICES,
        help_text="FUTURES, OPTIONS, EQUITY, MUTUAL_FUND, or ETF"
    )

    security_type = models.CharField(
        max_length=15,
        choices=SECURITY_TYPE_CHOICES,
        blank=True,
        help_text="Detailed security type from Kotak CSV"
    )

    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Contract expiry date"
    )

    # Financial Year when P&L was realized (from CSV import filename)
    fy = models.CharField(
        max_length=10,
        blank=True,
        db_index=True,
        help_text="Financial year of P&L realization (e.g., '2024-25')"
    )

    strike_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Strike price for options"
    )

    option_type = models.CharField(
        max_length=5,
        blank=True,
        help_text="CE or PE for options"
    )

    # Quantity and amounts
    quantity = models.IntegerField(
        default=0,
        help_text="Total traded quantity"
    )

    buy_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total buy value"
    )

    sell_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total sell value"
    )

    # P&L figures
    gross_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Gross P&L before charges"
    )

    net_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Net P&L after all charges"
    )

    # Charges breakdown (Kotak CSV)
    gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="GST charges"
    )

    brokerage = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Brokerage charges"
    )

    stt = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Securities Transaction Tax"
    )

    misc_charges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Other miscellaneous charges"
    )

    total_charges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total of all charges"
    )

    # Breeze specific fields
    realized_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Realized P&L (Breeze)"
    )

    unrealized_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Unrealized P&L (Breeze)"
    )

    # Raw data storage
    raw_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Original CSV row as JSON"
    )

    class Meta:
        db_table = 'broker_contract_pnl'
        verbose_name = 'Broker Contract PnL'
        verbose_name_plural = 'Broker Contract PnL'
        ordering = ['-created_at', 'symbol']
        indexes = [
            models.Index(fields=['broker', 'import_batch_id']),
            models.Index(fields=['symbol', 'expiry_date']),
            models.Index(fields=['segment']),
            models.Index(fields=['broker', 'trading_symbol']),  # For fast lookups
            models.Index(fields=['fy']),  # For FY filtering
            models.Index(fields=['broker', 'fy']),  # For broker+FY filtering
        ]
        constraints = [
            # Unique per broker + trading_symbol + fy - allows same contract in different FYs
            # Same contract from same FY updates existing record
            models.UniqueConstraint(
                fields=['broker', 'trading_symbol', 'fy'],
                name='unique_contract_per_broker_fy'
            )
        ]

    def __str__(self):
        return f"{self.broker} - {self.trading_symbol} ({self.segment})"

    def save(self, *args, **kwargs):
        # Auto-calculate total charges if not set
        if self.total_charges == Decimal('0.00'):
            self.total_charges = self.gst + self.brokerage + self.stt + self.misc_charges
        super().save(*args, **kwargs)
