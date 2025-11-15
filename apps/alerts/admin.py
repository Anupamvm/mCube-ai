from django.contrib import admin
from .models import Alert, AlertLog


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['title', 'priority', 'alert_type', 'telegram_sent', 'email_sent', 'sms_sent', 'created_at']
    list_filter = ['priority', 'alert_type', 'telegram_sent', 'email_sent', 'requires_action']
    search_fields = ['title', 'message']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(AlertLog)
class AlertLogAdmin(admin.ModelAdmin):
    list_display = ['alert', 'channel', 'status', 'retry_count', 'created_at']
    list_filter = ['channel', 'status']
    search_fields = ['alert__title']
    readonly_fields = ['created_at', 'updated_at']
