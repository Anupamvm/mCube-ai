from django.contrib import admin
from .models import Order, Execution


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['instrument', 'order_type', 'direction', 'quantity', 'status', 'broker_order_id', 'created_at']
    list_filter = ['status', 'order_type', 'direction', 'exchange']
    search_fields = ['instrument', 'broker_order_id', 'account__account_name']
    readonly_fields = ['created_at', 'updated_at', 'placed_at', 'filled_at', 'cancelled_at']
    date_hierarchy = 'created_at'


@admin.register(Execution)
class ExecutionAdmin(admin.ModelAdmin):
    list_display = ['execution_id', 'order', 'quantity', 'price', 'exchange_timestamp']
    list_filter = ['exchange', 'transaction_type']
    search_fields = ['execution_id', 'order__instrument']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'exchange_timestamp'
