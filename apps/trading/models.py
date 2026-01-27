"""
Trading Models - Trade Suggestions and Approvals

Stores trade suggestions from algorithms with complete reasoning
and tracks approval status and decisions
"""

from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import json
from django.utils import timezone


class TradeSuggestion(models.Model):
    """
    Stores algorithm-generated trade suggestions with complete reasoning.
    Requires manual or auto approval before execution.
    """

    STRATEGY_CHOICES = [
        ('kotak_strangle', 'Kotak Strangle (Options)'),
        ('kotak_broken_iron_condor', 'Kotak Broken Iron Condor (Options)'),
        ('icici_futures', 'ICICI Futures'),
    ]

    SUGGESTION_TYPE_CHOICES = [
        ('OPTIONS', 'Options'),
        ('FUTURES', 'Futures'),
    ]

    STATUS_CHOICES = [
        ('SUGGESTED', 'Suggested'),           # Initial state - algorithm generated suggestion
        ('TAKEN', 'Taken'),                   # User accepted and executed the trade
        ('REJECTED', 'Rejected'),             # User rejected the suggestion
        ('ACTIVE', 'Active'),                 # Trade is currently running
        ('CLOSED', 'Closed'),                 # Trade is closed (neutral state)
        ('SUCCESSFUL', 'Successful'),         # Trade closed with profit
        ('LOSS', 'Loss'),                     # Trade closed with loss
        ('BREAKEVEN', 'Breakeven'),           # Trade closed at breakeven
        ('EXPIRED', 'Expired'),               # Suggestion expired without action
        ('CANCELLED', 'Cancelled'),           # Cancelled before execution
    ]

    # Core Information
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trade_suggestions')
    strategy = models.CharField(max_length=30, choices=STRATEGY_CHOICES)
    suggestion_type = models.CharField(max_length=10, choices=SUGGESTION_TYPE_CHOICES)

    # Trade Details
    instrument = models.CharField(max_length=50)  # NIFTY, RELIANCE, etc.
    direction = models.CharField(max_length=10, choices=[('LONG', 'Long'), ('SHORT', 'Short'), ('NEUTRAL', 'Neutral')])

    # Market Data at Suggestion Time
    spot_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vix = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    days_to_expiry = models.IntegerField(null=True, blank=True)

    # Strike Details (for Options)
    call_strike = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    put_strike = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    call_premium = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    put_premium = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_premium = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Position Sizing
    recommended_lots = models.IntegerField(null=True, blank=True)
    margin_required = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    margin_available = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    margin_per_lot = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    margin_utilization = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)  # Percentage

    # Risk Metrics
    max_profit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    max_loss = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    breakeven_upper = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    breakeven_lower = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    risk_reward_ratio = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # Algorithm Reasoning (complete calculation details)
    algorithm_reasoning = models.JSONField(
        default=dict,
        help_text="Complete algorithm analysis including all calculations, filters, and scores"
    )

    # Position Details
    position_details = models.JSONField(
        default=dict,
        help_text="Recommended position parameters (quantity, SL, target, margin, etc.)"
    )

    # Status Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUGGESTED')

    # Execution Tracking
    taken_timestamp = models.DateTimeField(null=True, blank=True, help_text="When user took the trade")
    closed_timestamp = models.DateTimeField(null=True, blank=True, help_text="When trade was closed")
    rejected_timestamp = models.DateTimeField(null=True, blank=True, help_text="When suggestion was rejected")

    # P&L Tracking (for closed trades)
    entry_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    exit_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    realized_pnl = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    return_on_margin = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="ROM %")

    # User Notes
    user_notes = models.TextField(blank=True, help_text="User's notes on why taken/rejected/closed")

    # Auto-Trade Configuration
    is_auto_trade = models.BooleanField(
        default=False,
        help_text="Whether this was auto-approved based on configuration"
    )

    # Execution Reference
    executed_position = models.OneToOneField(
        'positions.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trade_suggestion'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Trade Suggestions'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['strategy', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.get_strategy_display()} - {self.instrument} {self.direction} ({self.status})"

    @property
    def is_pending(self):
        """Check if suggestion is still pending action"""
        return self.status == 'SUGGESTED'

    @property
    def is_active(self):
        """Check if trade is currently active"""
        return self.status in ['TAKEN', 'ACTIVE']

    @property
    def is_closed(self):
        """Check if trade is closed"""
        return self.status in ['CLOSED', 'SUCCESSFUL', 'LOSS', 'BREAKEVEN']

    @property
    def is_actionable(self):
        """Check if suggestion can still be acted upon"""
        from django.utils import timezone
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return self.status == 'SUGGESTED'

    def mark_taken(self, user_notes=''):
        """Mark suggestion as taken by user"""
        from django.utils import timezone
        self.status = 'TAKEN'
        self.taken_timestamp = timezone.now()
        if user_notes:
            self.user_notes = user_notes
        self.save()

    def mark_rejected(self, user_notes=''):
        """Mark suggestion as rejected by user"""
        from django.utils import timezone
        self.status = 'REJECTED'
        self.rejected_timestamp = timezone.now()
        if user_notes:
            self.user_notes = user_notes
        self.save()

    def mark_active(self):
        """Mark trade as active (running)"""
        self.status = 'ACTIVE'
        self.save()

    def mark_closed(self, pnl=None, exit_value=None, outcome='CLOSED', user_notes=''):
        """Mark trade as closed with P&L"""
        from django.utils import timezone
        self.status = outcome  # CLOSED, SUCCESSFUL, LOSS, or BREAKEVEN
        self.closed_timestamp = timezone.now()
        if pnl is not None:
            self.realized_pnl = pnl
            # Calculate ROM if margin_required exists
            if self.margin_required and self.margin_required > 0:
                self.return_on_margin = (pnl / self.margin_required) * 100
        if exit_value is not None:
            self.exit_value = exit_value
        if user_notes:
            self.user_notes = user_notes
        self.save()

    def get_status_color(self):
        """Get color for status badge"""
        colors = {
            'SUGGESTED': 'blue',
            'TAKEN': 'purple',
            'ACTIVE': 'orange',
            'CLOSED': 'gray',
            'SUCCESSFUL': 'green',
            'LOSS': 'red',
            'BREAKEVEN': 'yellow',
            'REJECTED': 'gray',
            'EXPIRED': 'gray',
            'CANCELLED': 'gray',
        }
        return colors.get(self.status, 'gray')


class AutoTradeConfig(models.Model):
    """
    Auto-trade configuration per user/strategy combination.
    Controls when suggestions are automatically approved.
    """

    STRATEGY_CHOICES = [
        ('kotak_strangle', 'Kotak Strangle'),
        ('kotak_broken_iron_condor', 'Kotak Broken Iron Condor'),
        ('icici_futures', 'ICICI Futures'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auto_trade_configs')
    strategy = models.CharField(max_length=30, choices=STRATEGY_CHOICES)

    # Auto-Trade Settings
    is_enabled = models.BooleanField(default=False)
    auto_approve_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('95.00'),
        help_text="For options: LLM confidence %. For futures: Composite score"
    )

    # Risk Controls
    max_daily_positions = models.IntegerField(default=1)
    max_daily_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('25000.00'),
        help_text="Maximum loss allowed per day"
    )

    # Approval Rules
    require_human_on_weekend = models.BooleanField(default=True)
    require_human_on_high_vix = models.BooleanField(default=True)
    vix_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'strategy')
        verbose_name_plural = 'Auto-Trade Configurations'

    def __str__(self):
        return f"{self.user.username} - {self.get_strategy_display()}"

    @property
    def status_display(self):
        """Display current status"""
        return "ENABLED" if self.is_enabled else "DISABLED"


class TradeSuggestionLog(models.Model):
    """
    Audit log for all trade suggestion activities.
    Tracks who approved/rejected and when.
    """

    ACTION_CHOICES = [
        ('CREATED', 'Suggestion Created'),
        ('APPROVED', 'Approved by User'),
        ('AUTO_APPROVED', 'Auto-Approved'),
        ('REJECTED', 'Rejected by User'),
        ('EXECUTED', 'Executed'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
    ]

    suggestion = models.ForeignKey(TradeSuggestion, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Trade Suggestion Logs'

    def __str__(self):
        return f"{self.suggestion} - {self.action}"


class OrderExecutionControl(models.Model):
    """
    Controls ongoing order execution with cancellation capability.
    Used to stop split/batch orders mid-execution when issues are detected.
    """

    suggestion = models.OneToOneField(
        TradeSuggestion,
        on_delete=models.CASCADE,
        related_name='execution_control'
    )

    # Cancellation Flag
    is_cancelled = models.BooleanField(
        default=False,
        help_text='Set to True to stop ongoing order execution'
    )
    cancel_reason = models.TextField(
        blank=True,
        help_text='Reason for cancellation (server stopped, error detected, user cancelled)'
    )

    # Progress Tracking
    batches_completed = models.IntegerField(
        default=0,
        help_text='Number of batches/orders completed so far'
    )
    total_batches = models.IntegerField(
        default=0,
        help_text='Total number of batches planned'
    )

    # Heartbeat
    last_heartbeat = models.DateTimeField(
        auto_now=True,
        help_text='Last time execution process checked in'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Order Execution Control'
        verbose_name_plural = 'Order Execution Controls'

    def __str__(self):
        status = 'CANCELLED' if self.is_cancelled else f'RUNNING ({self.batches_completed}/{self.total_batches})'
        return f"Execution #{self.suggestion_id} - {status}"

    def cancel(self, reason='User cancelled'):
        """Cancel ongoing execution"""
        self.is_cancelled = True
        self.cancel_reason = reason
        self.save()

    def should_continue(self):
        """Check if execution should continue"""
        return not self.is_cancelled

    def update_progress(self, batches_completed):
        """Update execution progress"""
        self.batches_completed = batches_completed
        self.last_heartbeat = timezone.now()
        self.save()


class PositionSize(models.Model):
    """
    Stores position sizing calculations for trades
    Includes margin requirements, lot sizing, and P&L projections
    """

    INSTRUMENT_TYPE_CHOICES = [
        ('FUTURES', 'Futures'),
        ('OPTIONS', 'Options'),
    ]

    DIRECTION_CHOICES = [
        ('LONG', 'Long'),
        ('SHORT', 'Short'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('EXECUTED', 'Executed'),
        ('EXPIRED', 'Expired'),
    ]

    # Core Information
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='position_sizes')
    instrument_type = models.CharField(max_length=10, choices=INSTRUMENT_TYPE_CHOICES)
    symbol = models.CharField(max_length=50)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)

    # Price Levels
    entry_price = models.DecimalField(max_digits=12, decimal_places=2)
    stop_loss = models.DecimalField(max_digits=12, decimal_places=2)
    target = models.DecimalField(max_digits=12, decimal_places=2)

    # Contract Details
    lot_size = models.IntegerField()
    strike = models.IntegerField(null=True, blank=True)  # For options
    option_type = models.CharField(max_length=2, blank=True)  # CE/PE

    # Margin Information
    available_margin = models.DecimalField(max_digits=15, decimal_places=2)
    margin_per_lot = models.DecimalField(max_digits=15, decimal_places=2)
    margin_source = models.CharField(max_length=10)  # breeze/neo

    # Position Sizing - Single Position
    recommended_lots = models.IntegerField()
    total_quantity = models.IntegerField()
    margin_required = models.DecimalField(max_digits=15, decimal_places=2)
    max_loss = models.DecimalField(max_digits=15, decimal_places=2)
    max_profit = models.DecimalField(max_digits=15, decimal_places=2)
    risk_reward_ratio = models.DecimalField(max_digits=6, decimal_places=2)

    # Averaging Down Scenario (for futures)
    averaging_data = models.JSONField(null=True, blank=True, help_text="Averaging down calculations")

    # Full calculation details
    calculation_details = models.JSONField(help_text="Complete position sizing calculation")

    # Status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Auto-expire after this time")

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Position Sizes'
        indexes = [
            models.Index(fields=['user', 'status', '-created_at']),
            models.Index(fields=['symbol', 'instrument_type']),
        ]

    def __str__(self):
        return f"{self.symbol} {self.instrument_type} - {self.recommended_lots} lots"

    def get_summary(self):
        """Get a summary dict of key metrics"""
        return {
            'symbol': self.symbol,
            'type': self.instrument_type,
            'direction': self.direction,
            'lots': self.recommended_lots,
            'quantity': self.total_quantity,
            'margin': float(self.margin_required),
            'max_loss': float(self.max_loss),
            'max_profit': float(self.max_profit),
            'risk_reward': float(self.risk_reward_ratio),
        }


class TakenTrade(models.Model):
    """
    Dedicated model for user-accepted trades with full lifecycle tracking.
    Links trade suggestions to actual positions and tracks P&L outcomes.
    """

    STATUS_CHOICES = [
        ('PENDING_EXECUTION', 'Pending Execution'),
        ('EXECUTED', 'Executed'),
        ('ACTIVE', 'Active'),
        ('CLOSED', 'Closed'),
        ('CANCELLED', 'Cancelled'),
        ('FAILED', 'Failed'),
    ]

    OUTCOME_CHOICES = [
        ('PROFIT', 'Profit'),
        ('LOSS', 'Loss'),
        ('BREAKEVEN', 'Breakeven'),
        ('PENDING', 'Pending'),
    ]

    STRATEGY_CHOICES = [
        ('kotak_strangle', 'Kotak Strangle'),
        ('kotak_broken_iron_condor', 'Kotak Broken Iron Condor'),
        ('icici_futures', 'ICICI Futures'),
    ]

    TRADE_TYPE_CHOICES = [
        ('OPTIONS', 'Options'),
        ('FUTURES', 'Futures'),
    ]

    DIRECTION_CHOICES = [
        ('LONG', 'Long'),
        ('SHORT', 'Short'),
        ('NEUTRAL', 'Neutral'),
    ]

    # Core References
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='taken_trades'
    )
    suggestion = models.OneToOneField(
        TradeSuggestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='taken_trade',
        help_text="Link to original trade suggestion"
    )
    position = models.OneToOneField(
        'positions.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='taken_trade',
        help_text="Link to executed position"
    )
    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='taken_trades'
    )

    # Trade Details
    strategy = models.CharField(max_length=30, choices=STRATEGY_CHOICES)
    trade_type = models.CharField(max_length=10, choices=TRADE_TYPE_CHOICES)
    instrument = models.CharField(max_length=50)  # NIFTY, RELIANCE, etc.
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)

    # Pricing
    entry_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Entry price or premium collected"
    )
    exit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Exit price or premium paid to close"
    )
    quantity = models.IntegerField(
        default=1,
        help_text="Number of lots"
    )
    lot_size = models.IntegerField(
        default=25,
        help_text="Lot size for the instrument"
    )

    # Options-specific fields
    call_strike = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    put_strike = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    call_order_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Broker order ID for call leg"
    )
    put_order_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Broker order ID for put leg"
    )
    expiry_date = models.DateField(null=True, blank=True)

    # Futures-specific fields
    broker_order_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Broker order ID for futures"
    )

    # Status & Timing
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING_EXECUTION'
    )
    outcome = models.CharField(
        max_length=15,
        choices=OUTCOME_CHOICES,
        default='PENDING'
    )
    taken_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When user accepted the trade"
    )
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When trade was executed with broker"
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When trade was closed"
    )

    # P&L Tracking
    realized_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    charges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total brokerage and other charges"
    )
    net_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="P&L after charges"
    )
    return_on_margin = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Return on margin percentage"
    )
    margin_used = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )

    # User Notes
    notes = models.TextField(
        blank=True,
        help_text="User notes about the trade"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-taken_at']
        verbose_name = 'Taken Trade'
        verbose_name_plural = 'Taken Trades'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'suggestion'],
                name='unique_user_suggestion',
                condition=models.Q(suggestion__isnull=False)
            )
        ]
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['account', 'status']),
            models.Index(fields=['strategy', 'outcome']),
            models.Index(fields=['taken_at']),
            models.Index(fields=['closed_at']),
        ]

    def __str__(self):
        return f"{self.instrument} {self.direction} - {self.status} ({self.outcome})"

    @property
    def is_pending(self):
        """Check if trade is pending execution"""
        return self.status == 'PENDING_EXECUTION'

    @property
    def is_active(self):
        """Check if trade is currently active"""
        return self.status in ['EXECUTED', 'ACTIVE']

    @property
    def is_closed(self):
        """Check if trade is closed"""
        return self.status == 'CLOSED'

    @property
    def total_quantity(self):
        """Total quantity in units"""
        return self.quantity * self.lot_size

    def mark_executed(self, position=None, executed_at=None):
        """Mark trade as executed"""
        self.status = 'EXECUTED'
        self.executed_at = executed_at or timezone.now()
        if position:
            self.position = position
        self.save()

    def mark_active(self):
        """Mark trade as actively being monitored"""
        self.status = 'ACTIVE'
        self.save()

    def mark_closed(self, exit_price=None, realized_pnl=None, charges=None):
        """Close the trade with final P&L"""
        self.status = 'CLOSED'
        self.closed_at = timezone.now()

        if exit_price is not None:
            self.exit_price = exit_price

        if realized_pnl is not None:
            self.realized_pnl = realized_pnl

        if charges is not None:
            self.charges = charges

        # Calculate net P&L
        if self.realized_pnl is not None:
            self.net_pnl = self.realized_pnl - (self.charges or Decimal('0.00'))

            # Determine outcome
            if self.net_pnl > Decimal('100'):  # Small buffer for breakeven
                self.outcome = 'PROFIT'
            elif self.net_pnl < Decimal('-100'):
                self.outcome = 'LOSS'
            else:
                self.outcome = 'BREAKEVEN'

            # Calculate ROM if margin available
            if self.margin_used and self.margin_used > 0:
                self.return_on_margin = (self.net_pnl / self.margin_used) * 100

        self.save()

    def mark_cancelled(self, reason=''):
        """Cancel the trade"""
        self.status = 'CANCELLED'
        self.outcome = 'PENDING'
        if reason:
            self.notes = f"{self.notes}\nCancelled: {reason}".strip()
        self.save()

    def mark_failed(self, reason=''):
        """Mark trade as failed"""
        self.status = 'FAILED'
        self.outcome = 'PENDING'
        if reason:
            self.notes = f"{self.notes}\nFailed: {reason}".strip()
        self.save()

    def sync_from_position(self):
        """Sync status and P&L from linked Position"""
        if not self.position:
            return False

        position = self.position

        # Update status based on position status
        if position.status == 'ACTIVE':
            self.status = 'ACTIVE'
        elif position.status == 'CLOSED':
            self.status = 'CLOSED'
            self.closed_at = position.closed_at

            # Sync P&L
            self.realized_pnl = position.realized_pnl
            self.exit_price = position.exit_price

            # Determine outcome
            if position.realized_pnl and position.realized_pnl > Decimal('100'):
                self.outcome = 'PROFIT'
            elif position.realized_pnl and position.realized_pnl < Decimal('-100'):
                self.outcome = 'LOSS'
            else:
                self.outcome = 'BREAKEVEN'

        self.save()
        return True

    def sync_suggestion_status(self):
        """Sync status back to linked TradeSuggestion"""
        if not self.suggestion:
            return False

        suggestion = self.suggestion

        if self.status == 'ACTIVE':
            suggestion.status = 'ACTIVE'
        elif self.status == 'CLOSED':
            if self.outcome == 'PROFIT':
                suggestion.status = 'SUCCESSFUL'
            elif self.outcome == 'LOSS':
                suggestion.status = 'LOSS'
            else:
                suggestion.status = 'BREAKEVEN'

            suggestion.realized_pnl = self.realized_pnl
            suggestion.exit_value = self.exit_price
            suggestion.closed_timestamp = self.closed_at

        suggestion.save()
        return True

    def get_status_color(self):
        """Get color for status badge in UI"""
        colors = {
            'PENDING_EXECUTION': 'yellow',
            'EXECUTED': 'blue',
            'ACTIVE': 'orange',
            'CLOSED': 'gray',
            'CANCELLED': 'gray',
            'FAILED': 'red',
        }
        return colors.get(self.status, 'gray')

    def get_outcome_color(self):
        """Get color for outcome badge in UI"""
        colors = {
            'PROFIT': 'green',
            'LOSS': 'red',
            'BREAKEVEN': 'yellow',
            'PENDING': 'gray',
        }
        return colors.get(self.outcome, 'gray')

