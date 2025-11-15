from django.contrib import admin
from .models import (
    CredentialStore,
    TradingSchedule,
    NseFlag,
    BkLog,
    DayReport,
    TodaysPosition
)


@admin.register(CredentialStore)
class CredentialStoreAdmin(admin.ModelAdmin):
    list_display = ['service', 'name', 'username', 'created_at', 'last_session_update']
    list_filter = ['service']
    search_fields = ['service', 'name', 'username']
    readonly_fields = ['created_at', 'last_session_update']

    fieldsets = (
        ('Service Information', {
            'fields': ('service', 'name')
        }),
        ('API Credentials', {
            'fields': ('api_key', 'api_secret', 'session_token'),
            'classes': ('collapse',)
        }),
        ('Username/Password Credentials', {
            'fields': ('username', 'password'),
        }),
        ('Additional Fields', {
            'fields': ('pan', 'neo_password', 'sid'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_session_update'),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Make password fields use password input widget
        if 'password' in form.base_fields:
            form.base_fields['password'].widget.attrs['type'] = 'password'
        if 'neo_password' in form.base_fields:
            form.base_fields['neo_password'].widget.attrs['type'] = 'password'
        if 'api_secret' in form.base_fields:
            form.base_fields['api_secret'].widget.attrs['type'] = 'password'
        return form


@admin.register(TradingSchedule)
class TradingScheduleAdmin(admin.ModelAdmin):
    list_display = ['date', 'enabled', 'open_time', 'take_trade_time', 'close_pos_time', 'note']
    list_filter = ['enabled', 'date']
    search_fields = ['date', 'note']
    date_hierarchy = 'date'

    fieldsets = (
        ('Date & Status', {
            'fields': ('date', 'enabled', 'note')
        }),
        ('Trading Times', {
            'fields': (
                'open_time',
                'take_trade_time',
                'last_trade_time',
                'close_pos_time',
                'mkt_close_time',
                'close_day_time'
            )
        }),
    )


@admin.register(NseFlag)
class NseFlagAdmin(admin.ModelAdmin):
    list_display = ['flag', 'value', 'updated_at']
    list_filter = ['updated_at']
    search_fields = ['flag', 'value', 'description']
    readonly_fields = ['updated_at']

    fieldsets = (
        ('Flag', {
            'fields': ('flag', 'value', 'description')
        }),
        ('Metadata', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(BkLog)
class BkLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'level', 'background_task', 'action', 'short_message']
    list_filter = ['level', 'background_task', 'timestamp']
    search_fields = ['action', 'message']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'

    def short_message(self, obj):
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    short_message.short_description = 'Message'


@admin.register(DayReport)
class DayReportAdmin(admin.ModelAdmin):
    list_display = ['date', 'day_of_week', 'pnl', 'num_legs', 'is_closed', 'expiry_date']
    list_filter = ['is_closed', 'day_of_week', 'date']
    search_fields = ['date', 'notes']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'date'

    fieldsets = (
        ('Date Information', {
            'fields': ('date', 'day_of_week', 'expiry_date')
        }),
        ('Trading Results', {
            'fields': ('num_legs', 'pnl', 'is_closed')
        }),
        ('Additional Info', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TodaysPosition)
class TodaysPositionAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'symbol', 'option_type', 'strike_price',
        'net_trd_qty_lot', 'realized_pl', 'last_price'
    ]
    list_filter = ['date', 'symbol', 'option_type', 'exchange']
    search_fields = ['symbol', 'instrument_name']
    readonly_fields = ['created_at']
    date_hierarchy = 'date'

    fieldsets = (
        ('Position Details', {
            'fields': ('date', 'symbol', 'instrument_name', 'instrument_token')
        }),
        ('Contract Details', {
            'fields': ('exchange', 'segment', 'expiry_date', 'option_type', 'strike_price')
        }),
        ('Buy Side', {
            'fields': (
                'buy_traded_qty_lot', 'buy_traded_val', 'buy_trd_avg',
                'buy_open_qty_lot', 'buy_open_val'
            ),
            'classes': ('collapse',)
        }),
        ('Sell Side', {
            'fields': (
                'sell_traded_qty_lot', 'sell_traded_val', 'sell_trd_avg',
                'sell_open_qty_lot', 'sell_open_val'
            ),
            'classes': ('collapse',)
        }),
        ('Net Position', {
            'fields': (
                'net_trd_qty_lot', 'net_trd_value', 'actual_net_trd_value',
                'realized_pl', 'last_price', 'average_stock_price'
            )
        }),
        ('Margins', {
            'fields': (
                'span_margin', 'span_margin_total',
                'exposure_margin', 'exposure_margin_total', 'premium'
            ),
            'classes': ('collapse',)
        }),
    )
