"""
Algorithm Testing Models

Stores test scenarios and results for algorithm analysis
"""

from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import json


class AlgoTestScenario(models.Model):
    """
    Stores saved algorithm test scenarios for later review/comparison
    """
    STRATEGY_CHOICES = [
        ('options', 'Options - Kotak Strangle'),
        ('futures', 'Futures - ICICI'),
        ('both', 'Both Strategies'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES)

    # Scenario inputs (stored as JSON for flexibility)
    inputs = models.JSONField(default=dict)

    # Calculated results
    results = models.JSONField(default=dict)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_template = models.BooleanField(default=False)  # Public template

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Algo Test Scenarios'

    def __str__(self):
        return f"{self.name} ({self.strategy})"


class OptionsTestLog(models.Model):
    """
    Log of options algorithm test execution
    """
    STATUS_CHOICES = [
        ('pass', 'Passed All Filters'),
        ('fail', 'Failed Filter'),
        ('error', 'Calculation Error'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    # Input parameters
    nifty_spot = models.DecimalField(max_digits=10, decimal_places=2)
    india_vix = models.DecimalField(max_digits=8, decimal_places=2)
    days_to_expiry = models.IntegerField()
    available_margin = models.DecimalField(max_digits=15, decimal_places=2)
    active_positions = models.IntegerField(default=0)

    # Calculated values
    adjusted_delta = models.DecimalField(max_digits=6, decimal_places=4)
    call_strike = models.IntegerField()
    put_strike = models.IntegerField()
    premium_collected = models.DecimalField(max_digits=10, decimal_places=2)

    # Filter results
    filter_results = models.JSONField(default=dict)

    # Final decision
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    decision = models.CharField(max_length=20)  # 'ENTRY', 'REJECT', 'ERROR'
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Options Test Logs'

    def __str__(self):
        return f"Options Test - NIFTY {self.nifty_spot} ({self.created_at.date()})"


class FuturesTestLog(models.Model):
    """
    Log of futures algorithm test execution
    """
    STATUS_CHOICES = [
        ('qualified', 'Qualified'),
        ('not_qualified', 'Not Qualified'),
        ('blocked', 'Blocked'),
        ('error', 'Error'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    # Stock and input parameters
    symbol = models.CharField(max_length=20)
    current_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Scoring results
    oi_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sector_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    technical_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    composite_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    # Factor details
    factor_details = models.JSONField(default=dict)

    # LLM validation
    llm_confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    llm_recommendation = models.CharField(max_length=50, blank=True)

    # Final decision
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    decision = models.CharField(max_length=20)  # 'LONG', 'SHORT', 'BLOCK'

    # Position details if entry
    position_size = models.IntegerField(default=0)
    margin_required = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Futures Test Logs'

    def __str__(self):
        return f"{self.symbol} Futures Test ({self.created_at.date()})"


class PositionMonitorSnapshot(models.Model):
    """
    Snapshot of position monitoring at a given time
    """
    from apps.positions.models import Position

    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='monitor_snapshots')

    # Current market data
    current_price = models.DecimalField(max_digits=10, decimal_places=2)
    current_time = models.DateTimeField()

    # P&L calculation
    unrealized_pnl = models.DecimalField(max_digits=15, decimal_places=2)
    unrealized_pnl_pct = models.DecimalField(max_digits=8, decimal_places=4)

    # Options-specific
    call_premium = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    put_premium = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    current_delta = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # Exit checks
    sl_hit = models.BooleanField(default=False)
    target_hit = models.BooleanField(default=False)

    # Recommended action
    action = models.CharField(max_length=50, default='HOLD')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Position Monitor Snapshots'

    def __str__(self):
        return f"{self.position} - {self.created_at}"
