from django.contrib import admin
from .models import BrokerAccount


@admin.register(BrokerAccount)
class BrokerAccountAdmin(admin.ModelAdmin):
    list_display = ['account_name', 'broker', 'allocated_capital', 'is_active', 'is_paper_trading']
    list_filter = ['broker', 'is_active', 'is_paper_trading']
    search_fields = ['account_name', 'account_number']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('broker', 'account_number', 'account_name')
        }),
        ('Capital & Risk', {
            'fields': ('allocated_capital', 'max_daily_loss', 'max_weekly_loss')
        }),
        ('Status', {
            'fields': ('is_active', 'is_paper_trading')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
