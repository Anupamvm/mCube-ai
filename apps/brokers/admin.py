"""
Admin configuration for brokers app
"""

from django.contrib import admin
from apps.brokers.models import (
    BrokerLimit, BrokerPosition, OptionChainQuote, HistoricalPrice,
    Order, Execution
)


@admin.register(BrokerLimit)
class BrokerLimitAdmin(admin.ModelAdmin):
    """Admin interface for BrokerLimit model"""

    list_display = [
        'broker',
        'margin_available',
        'margin_used',
        'fetched_at',
        'created_at',
    ]

    list_filter = [
        'broker',
        'fetched_at',
    ]

    search_fields = [
        'broker',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
    ]

    ordering = ['-fetched_at']


@admin.register(BrokerPosition)
class BrokerPositionAdmin(admin.ModelAdmin):
    """Admin interface for BrokerPosition model"""

    list_display = [
        'broker',
        'symbol',
        'net_quantity',
        'ltp',
        'average_price',
        'unrealized_pnl',
        'realized_pnl',
        'fetched_at',
    ]

    list_filter = [
        'broker',
        'exchange_segment',
        'product',
        'fetched_at',
    ]

    search_fields = [
        'symbol',
        'broker',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
    ]

    ordering = ['-fetched_at', 'symbol']


@admin.register(OptionChainQuote)
class OptionChainQuoteAdmin(admin.ModelAdmin):
    """Admin interface for OptionChainQuote model"""

    list_display = [
        'stock_code',
        'expiry_date',
        'strike_price',
        'right',
        'ltp',
        'open_interest',
        'created_at',
    ]

    list_filter = [
        'stock_code',
        'product_type',
        'right',
        'expiry_date',
    ]

    search_fields = [
        'stock_code',
        'strike_price',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
    ]

    ordering = ['-created_at', 'expiry_date', 'strike_price']


@admin.register(HistoricalPrice)
class HistoricalPriceAdmin(admin.ModelAdmin):
    """Admin interface for HistoricalPrice model"""

    list_display = [
        'stock_code',
        'product_type',
        'datetime',
        'open',
        'high',
        'low',
        'close',
        'volume',
    ]

    list_filter = [
        'stock_code',
        'exchange_code',
        'product_type',
        'datetime',
    ]

    search_fields = [
        'stock_code',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
    ]

    ordering = ['-datetime']

    date_hierarchy = 'datetime'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin interface for Order model"""

    list_display = [
        'instrument',
        'order_type',
        'direction',
        'quantity',
        'status',
        'broker_order_id',
        'created_at',
    ]

    list_filter = [
        'status',
        'order_type',
        'direction',
        'exchange',
    ]

    search_fields = [
        'instrument',
        'broker_order_id',
        'account__account_name',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'placed_at',
        'filled_at',
        'cancelled_at',
    ]

    date_hierarchy = 'created_at'


@admin.register(Execution)
class ExecutionAdmin(admin.ModelAdmin):
    """Admin interface for Execution model"""

    list_display = [
        'execution_id',
        'order',
        'quantity',
        'price',
        'exchange_timestamp',
    ]

    list_filter = [
        'exchange',
        'transaction_type',
    ]

    search_fields = [
        'execution_id',
        'order__instrument',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
    ]

    date_hierarchy = 'exchange_timestamp'
