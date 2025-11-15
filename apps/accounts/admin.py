from django.contrib import admin
from .models import BrokerAccount, APICredential


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


@admin.register(APICredential)
class APICredentialAdmin(admin.ModelAdmin):
    list_display = ['account', 'is_valid', 'last_authenticated', 'expires_at']
    list_filter = ['is_valid']
    search_fields = ['account__account_name']
    readonly_fields = ['created_at', 'updated_at', 'last_authenticated']
    
    fieldsets = (
        ('Account', {
            'fields': ('account',)
        }),
        ('API Credentials', {
            'fields': ('consumer_key', 'consumer_secret', 'access_token', 'refresh_token')
        }),
        ('Additional Fields', {
            'fields': ('mobile_number', 'password')
        }),
        ('Status', {
            'fields': ('is_valid', 'last_authenticated', 'expires_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
