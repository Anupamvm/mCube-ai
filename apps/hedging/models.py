"""
Models for the Covered Call Protection ("Cover Position") feature.

A HedgePosition is a hedge campaign layered on top of an existing futures
position (which may or may not have a corresponding `positions.Position`
row — the Open Trades page already works purely off live broker data, so
these models are keyed off (broker, underlying_symbol, futures_expiry_date)
rather than requiring one).

`strategy_type` on HedgePosition and the generic `leg_type`/`direction`
fields on HedgeLeg are intentionally broader than "covered call" so that
Protective Put, Collar, Covered Strangle and Wheel can reuse this schema
later without a migration rework. Only COVERED_CALL logic is implemented
today.
"""
from django.contrib.auth.models import User
from django.db import models

from apps.core.constants import DIRECTION_CHOICES
from apps.core.models import TimeStampedModel

BROKER_BREEZE = 'breeze'
BROKER_NEO = 'neo'

HEDGE_BROKER_CHOICES = [
    (BROKER_BREEZE, 'ICICI Breeze'),
    (BROKER_NEO, 'Kotak Neo'),
]

STRATEGY_COVERED_CALL = 'COVERED_CALL'
# Reserved for future phases — schema supports them, logic does not exist yet.
STRATEGY_PROTECTIVE_PUT = 'PROTECTIVE_PUT'
STRATEGY_COLLAR = 'COLLAR'
STRATEGY_COVERED_STRANGLE = 'COVERED_STRANGLE'
STRATEGY_WHEEL = 'WHEEL'

STRATEGY_TYPE_CHOICES = [
    (STRATEGY_COVERED_CALL, 'Covered Call'),
    (STRATEGY_PROTECTIVE_PUT, 'Protective Put'),
    (STRATEGY_COLLAR, 'Collar'),
    (STRATEGY_COVERED_STRANGLE, 'Covered Strangle'),
    (STRATEGY_WHEEL, 'Wheel'),
]

HEDGE_STATUS_ACTIVE = 'ACTIVE'
HEDGE_STATUS_ROLLED = 'ROLLED'
HEDGE_STATUS_CLOSED = 'CLOSED'
HEDGE_STATUS_EXPIRED = 'EXPIRED'
HEDGE_STATUS_CANCELLED = 'CANCELLED'

HEDGE_STATUS_CHOICES = [
    (HEDGE_STATUS_ACTIVE, 'Active'),
    (HEDGE_STATUS_ROLLED, 'Rolled'),
    (HEDGE_STATUS_CLOSED, 'Closed'),
    (HEDGE_STATUS_EXPIRED, 'Expired'),
    (HEDGE_STATUS_CANCELLED, 'Cancelled'),
]


class HedgePosition(TimeStampedModel):
    """
    One hedge campaign (e.g. a covered call) layered against an existing
    futures position. Never requires a `positions.Position` row to exist.
    """

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='hedge_positions',
        help_text="Broker account this hedge is placed under",
    )

    position = models.ForeignKey(
        'positions.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hedges',
        help_text="Optional cross-reference to a Position row, if one exists. "
                   "Never required — the futures leg is identified by "
                   "(broker, underlying_symbol, futures_expiry_date) instead.",
    )

    broker = models.CharField(
        max_length=10,
        choices=HEDGE_BROKER_CHOICES,
        db_index=True,
        help_text="Broker the FUTURES position (and therefore the hedge orders) executes on",
    )

    underlying_symbol = models.CharField(max_length=100, db_index=True)
    futures_expiry_date = models.DateField(db_index=True)

    strategy_type = models.CharField(
        max_length=30,
        choices=STRATEGY_TYPE_CHOICES,
        default=STRATEGY_COVERED_CALL,
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=HEDGE_STATUS_CHOICES,
        default=HEDGE_STATUS_ACTIVE,
        db_index=True,
    )

    futures_direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        default='LONG',
        help_text="Direction of the underlying futures position being hedged. "
                   "Always LONG for a covered call; kept generic for future strategies.",
    )

    futures_lots_covered = models.PositiveIntegerField(
        help_text="Futures lots this campaign was sized against at creation time. "
                   "Active HedgeLeg quantity can never exceed this.",
    )
    futures_lot_size = models.PositiveIntegerField(
        help_text="Lot size of the futures contract, snapshotted at hedge-open time.",
    )
    futures_avg_price = models.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Weighted-average futures price at the time this hedge was opened.",
    )

    net_premium_collected = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text="Running total: sold premium minus buy-back cost, across all legs/rolls.",
    )
    effective_breakeven = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Cached display value, always recomputable from futures_avg_price "
                   "and net_premium_collected via payoff_engine.calculate_effective_breakeven.",
    )

    recommendation_snapshot = models.JSONField(
        default=dict, blank=True,
        help_text="Recommendation-engine input/output at time of the most recent order "
                   "action, kept for audit/backtest purposes.",
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hedge_positions',
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'hedge_positions'
        indexes = [
            models.Index(
                fields=['broker', 'underlying_symbol', 'futures_expiry_date', 'status'],
                name='hedge_pos_lookup_idx',
            ),
        ]
        ordering = ['-created_at']
        verbose_name = 'Hedge Position'
        verbose_name_plural = 'Hedge Positions'

    def __str__(self):
        return f"{self.underlying_symbol} {self.strategy_type} ({self.broker}) - {self.status}"

    @property
    def uncovered_lots(self):
        """Futures lots not currently covered by an OPEN/PENDING short leg."""
        covered = self.legs.filter(
            direction=HedgeLeg.DIRECTION_SELL,
            status__in=[HedgeLeg.STATUS_PENDING, HedgeLeg.STATUS_PLACED,
                        HedgeLeg.STATUS_PARTIALLY_FILLED, HedgeLeg.STATUS_FILLED],
        ).exclude(leg_role=HedgeLeg.ROLE_ROLL_CLOSE).aggregate(
            total=models.Sum('lots')
        )['total'] or 0
        bought_back = self.legs.filter(
            direction=HedgeLeg.DIRECTION_BUY,
            status=HedgeLeg.STATUS_FILLED,
        ).aggregate(total=models.Sum('lots'))['total'] or 0
        return max(self.futures_lots_covered - (covered - bought_back), 0)


class HedgeLeg(TimeStampedModel):
    """
    One option order/fill under a HedgePosition. A roll creates two new
    HedgeLeg rows (buy-back + new sell) rather than mutating an existing
    one, so the full history of every fill is preserved.
    """

    LEG_TYPE_CALL = 'CALL'
    LEG_TYPE_PUT = 'PUT'
    LEG_TYPE_FUTURE = 'FUTURE'
    LEG_TYPE_CHOICES = [
        (LEG_TYPE_CALL, 'Call'),
        (LEG_TYPE_PUT, 'Put'),
        (LEG_TYPE_FUTURE, 'Future'),
    ]

    DIRECTION_SELL = 'SELL'
    DIRECTION_BUY = 'BUY'
    LEG_DIRECTION_CHOICES = [
        (DIRECTION_SELL, 'Sell'),
        (DIRECTION_BUY, 'Buy'),
    ]

    ROLE_OPEN = 'OPEN'
    ROLE_ROLL_CLOSE = 'ROLL_CLOSE'
    ROLE_ROLL_OPEN = 'ROLL_OPEN'
    ROLE_MANUAL_CLOSE = 'MANUAL_CLOSE'
    LEG_ROLE_CHOICES = [
        (ROLE_OPEN, 'Initial Open'),
        (ROLE_ROLL_CLOSE, 'Roll Buy-Back'),
        (ROLE_ROLL_OPEN, 'Roll New Sell'),
        (ROLE_MANUAL_CLOSE, 'Manual Buy-Back / Expiry Close'),
    ]

    OPTION_TYPE_CE = 'CE'
    OPTION_TYPE_PE = 'PE'
    OPTION_TYPE_CHOICES = [
        (OPTION_TYPE_CE, 'Call'),
        (OPTION_TYPE_PE, 'Put'),
    ]

    ORDER_TYPE_MARKET = 'MARKET'
    ORDER_TYPE_LIMIT = 'LIMIT'
    ORDER_TYPE_SL = 'SL'
    LEG_ORDER_TYPE_CHOICES = [
        (ORDER_TYPE_MARKET, 'Market'),
        (ORDER_TYPE_LIMIT, 'Limit'),
        (ORDER_TYPE_SL, 'Stop-Loss'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_PLACED = 'PLACED'
    STATUS_PARTIALLY_FILLED = 'PARTIALLY_FILLED'
    STATUS_FILLED = 'FILLED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_FAILED = 'FAILED'
    STATUS_EXPIRED_WORTHLESS = 'EXPIRED_WORTHLESS'
    LEG_STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PLACED, 'Placed'),
        (STATUS_PARTIALLY_FILLED, 'Partially Filled'),
        (STATUS_FILLED, 'Filled'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_EXPIRED_WORTHLESS, 'Expired Worthless'),
    ]

    hedge_position = models.ForeignKey(
        HedgePosition, on_delete=models.CASCADE, related_name='legs',
    )

    leg_type = models.CharField(max_length=10, choices=LEG_TYPE_CHOICES, default=LEG_TYPE_CALL)
    direction = models.CharField(max_length=4, choices=LEG_DIRECTION_CHOICES)
    leg_role = models.CharField(max_length=15, choices=LEG_ROLE_CHOICES, default=ROLE_OPEN)

    option_trading_symbol = models.CharField(
        max_length=100,
        help_text="The broker-native symbol actually sent to the order API "
                   "(post Neo/Breeze translation).",
    )
    breeze_source_symbol = models.CharField(
        max_length=100, blank=True,
        help_text="The Breeze chain symbol this leg was priced off, kept even when "
                   "executed on Neo, for audit trail purposes.",
    )

    strike_price = models.DecimalField(max_digits=10, decimal_places=2)
    option_type = models.CharField(max_length=2, choices=OPTION_TYPE_CHOICES, default=OPTION_TYPE_CE)
    expiry_date = models.DateField(
        help_text="The OPTION's own expiry — may be nearer than futures_expiry_date "
                   "(e.g. a weekly call against a monthly future) but never after it.",
    )

    lots = models.PositiveIntegerField()
    lot_size = models.PositiveIntegerField(help_text="Snapshot at order time.")

    order_type = models.CharField(max_length=10, choices=LEG_ORDER_TYPE_CHOICES, default=ORDER_TYPE_MARKET)
    limit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    trigger_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    premium_per_share = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=LEG_STATUS_CHOICES, default=STATUS_PENDING, db_index=True)

    order = models.ForeignKey(
        'brokers.Order', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hedge_legs',
        help_text="Generic broker Order row tracking status/fills for this leg.",
    )

    rolled_from = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rolled_to_set',
        help_text="Set on a ROLL_OPEN leg, pointing back to the leg it replaced.",
    )

    greeks_at_entry = models.JSONField(default=dict, blank=True)
    greeks_at_exit = models.JSONField(default=dict, blank=True)

    placed_at = models.DateTimeField(null=True, blank=True)
    filled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'hedge_legs'
        ordering = ['-created_at']
        verbose_name = 'Hedge Leg'
        verbose_name_plural = 'Hedge Legs'

    def __str__(self):
        return f"{self.direction} {self.lots}x {self.strike_price}{self.option_type} ({self.status})"


class HedgeAuditLog(TimeStampedModel):
    """
    Action-level audit trail, mirroring apps.trading.models.TradeSuggestionLog.
    Every PLACED / ROLL_COMPLETED row must carry a non-null `user` — this is
    the auditable proof that no hedge action ever fires unattended.
    """

    ACTION_CREATED = 'CREATED'
    ACTION_PREVIEWED = 'PREVIEWED'
    ACTION_PLACED = 'PLACED'
    ACTION_FILLED = 'FILLED'
    ACTION_ROLL_INITIATED = 'ROLL_INITIATED'
    ACTION_ROLL_COMPLETED = 'ROLL_COMPLETED'
    ACTION_MANUAL_CLOSE = 'MANUAL_CLOSE'
    ACTION_EXPIRED_WORTHLESS = 'EXPIRED_WORTHLESS'
    ACTION_CANCELLED = 'CANCELLED'
    ACTION_VALIDATION_BLOCKED = 'VALIDATION_BLOCKED'

    ACTION_CHOICES = [
        (ACTION_CREATED, 'Hedge Created'),
        (ACTION_PREVIEWED, 'Previewed'),
        (ACTION_PLACED, 'Order Placed'),
        (ACTION_FILLED, 'Order Filled'),
        (ACTION_ROLL_INITIATED, 'Roll Initiated'),
        (ACTION_ROLL_COMPLETED, 'Roll Completed'),
        (ACTION_MANUAL_CLOSE, 'Manual Close'),
        (ACTION_EXPIRED_WORTHLESS, 'Expired Worthless'),
        (ACTION_CANCELLED, 'Cancelled'),
        (ACTION_VALIDATION_BLOCKED, 'Blocked by Validation'),
    ]

    hedge_position = models.ForeignKey(
        HedgePosition, on_delete=models.CASCADE, related_name='audit_logs',
    )
    leg = models.ForeignKey(
        HedgeLeg, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=25, choices=ACTION_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    snapshot = models.JSONField(
        default=dict, blank=True,
        help_text="Request payload + validator result for this specific action.",
    )

    class Meta:
        db_table = 'hedge_audit_logs'
        ordering = ['-created_at']
        verbose_name = 'Hedge Audit Log'
        verbose_name_plural = 'Hedge Audit Logs'

    def __str__(self):
        return f"{self.hedge_position} - {self.action}"
