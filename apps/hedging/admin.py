from django.contrib import admin

from .models import HedgeAuditLog, HedgeLeg, HedgePosition


class HedgeLegInline(admin.TabularInline):
    model = HedgeLeg
    extra = 0
    readonly_fields = ('created_at', 'updated_at')
    fields = (
        'direction', 'leg_role', 'strike_price', 'option_type', 'expiry_date',
        'lots', 'lot_size', 'status', 'premium_per_share', 'charges', 'order',
    )


@admin.register(HedgePosition)
class HedgePositionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'underlying_symbol', 'broker', 'strategy_type', 'status',
        'futures_lots_covered', 'uncovered_lots', 'futures_avg_price',
        'effective_breakeven', 'net_premium_collected', 'created_by', 'created_at',
    )
    list_filter = ('broker', 'strategy_type', 'status')
    search_fields = ('underlying_symbol',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [HedgeLegInline]

    def uncovered_lots(self, obj):
        return obj.uncovered_lots


@admin.register(HedgeLeg)
class HedgeLegAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'hedge_position', 'direction', 'leg_role', 'strike_price',
        'option_type', 'expiry_date', 'lots', 'status', 'premium_per_share',
    )
    list_filter = ('direction', 'leg_role', 'option_type', 'status')
    search_fields = ('option_trading_symbol', 'breeze_source_symbol')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(HedgeAuditLog)
class HedgeAuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'hedge_position', 'leg', 'action', 'user', 'created_at')
    list_filter = ('action',)
    readonly_fields = ('created_at', 'updated_at')
