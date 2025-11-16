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
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Manually Approved'),
        ('AUTO_APPROVED', 'Auto Approved'),
        ('REJECTED', 'Rejected'),
        ('EXECUTED', 'Executed'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
    ]

    # Core Information
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trade_suggestions')
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES)
    suggestion_type = models.CharField(max_length=10, choices=SUGGESTION_TYPE_CHOICES)

    # Trade Details
    instrument = models.CharField(max_length=50)  # NIFTY, RELIANCE, etc.
    direction = models.CharField(max_length=10, choices=[('LONG', 'Long'), ('SHORT', 'Short'), ('NEUTRAL', 'Neutral')])

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

    # Approval Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_suggestions'
    )
    approval_timestamp = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)

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
        """Check if suggestion is still pending approval"""
        return self.status == 'PENDING'

    @property
    def is_approved(self):
        """Check if suggestion has been approved"""
        return self.status in ['APPROVED', 'AUTO_APPROVED', 'EXECUTED']

    @property
    def is_actionable(self):
        """Check if suggestion can still be acted upon"""
        from django.utils import timezone
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return self.status in ['PENDING', 'APPROVED', 'AUTO_APPROVED']


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
