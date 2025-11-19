"""
Trading Models - Trade Suggestions and Approvals

Stores trade suggestions from algorithms with complete reasoning
and tracks approval status and decisions
"""

from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import json


class TradeSuggestion(models.Model):
    """
    Stores algorithm-generated trade suggestions with complete reasoning.
    Requires manual or auto approval before execution.
    """

    STRATEGY_CHOICES = [
        ('kotak_strangle', 'Kotak Strangle (Options)'),
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
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES)
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
        ('icici_futures', 'ICICI Futures'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auto_trade_configs')
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES)

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
