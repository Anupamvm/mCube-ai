"""
Broker models for mCube Trading System

This module contains models for broker data including limits, positions,
option chain quotes, and historical prices.
"""

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator

from apps.core.models import TimeStampedModel
from apps.core.constants import BROKER_CHOICES


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
