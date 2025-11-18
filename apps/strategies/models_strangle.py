"""
Nifty Strangle Strategy Models

Models for storing Nifty market data and strangle strategy execution state
"""

from django.db import models
from django.utils import timezone
from decimal import Decimal
from apps.core.models import TimeStampedModel
from apps.brokers.models import NiftyOptionChain  # Reuse existing model


class NiftyMarketData(TimeStampedModel):
    """
    Stores comprehensive Nifty market data for strangle strategy

    Includes:
    - Spot price and OHLC
    - Global markets data
    - Previous session data
    - Technical indicators (DMAs)
    - VIX data
    """

    # Timestamp
    data_timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    # Nifty Spot Data
    spot_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Current Nifty spot price")
    open_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Today's open")
    high_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Today's high")
    low_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Today's low")
    prev_close = models.DecimalField(max_digits=10, decimal_places=2, help_text="Previous day close")

    # Price Changes
    change_points = models.DecimalField(max_digits=10, decimal_places=2, help_text="Change in points")
    change_percent = models.DecimalField(max_digits=5, decimal_places=2, help_text="Change in percentage")

    # Global Markets (for sentiment analysis)
    sgx_nifty = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="SGX Nifty")
    dow_jones = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Dow Jones")
    nasdaq = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Nasdaq")
    sp500 = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="S&P 500")
    gift_nifty = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="GIFT Nifty")

    # Volatility
    india_vix = models.DecimalField(max_digits=6, decimal_places=2, help_text="India VIX")
    vix_change_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Technical Indicators (DMAs from Trendlyne)
    dma_5 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="5-day moving average")
    dma_10 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="10-day moving average")
    dma_20 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="20-day moving average")
    dma_50 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="50-day moving average")
    dma_200 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="200-day moving average")

    # Volume and Liquidity
    total_volume = models.BigIntegerField(null=True, blank=True, help_text="Total volume traded")
    total_turnover = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Total turnover in crores")

    # Market Sentiment
    advances = models.IntegerField(null=True, blank=True, help_text="Number of advancing stocks")
    declines = models.IntegerField(null=True, blank=True, help_text="Number of declining stocks")
    unchanged = models.IntegerField(null=True, blank=True, help_text="Number of unchanged stocks")

    # Data Freshness
    is_stale = models.BooleanField(default=False, help_text="True if data is > 5 minutes old")
    data_source = models.CharField(max_length=50, default='breeze', help_text="Source: breeze, trendlyne, manual")

    class Meta:
        db_table = 'strangle_market_data'
        ordering = ['-data_timestamp']
        indexes = [
            models.Index(fields=['-data_timestamp']),
            models.Index(fields=['is_stale']),
        ]

    def __str__(self):
        return f"Nifty @ {self.spot_price} on {self.data_timestamp.strftime('%Y-%m-%d %H:%M')}"

    def mark_as_stale(self):
        """Mark data as stale if it's > 5 minutes old"""
        from datetime import timedelta
        if timezone.now() - self.data_timestamp > timedelta(minutes=5):
            self.is_stale = True
            self.save(update_fields=['is_stale'])


class StrangleAlgorithmState(TimeStampedModel):
    """
    Stores the execution state of the strangle algorithm

    Tracks step-by-step progression through the algorithm
    """

    STATUS_CHOICES = [
        ('INITIALIZED', 'Initialized'),
        ('DATA_COLLECTION', 'Collecting Data'),
        ('MARKET_ANALYSIS', 'Analyzing Market'),
        ('STRIKE_SELECTION', 'Selecting Strikes'),
        ('DELTA_CALCULATION', 'Calculating Delta'),
        ('PREMIUM_EVALUATION', 'Evaluating Premiums'),
        ('RISK_ASSESSMENT', 'Assessing Risk'),
        ('POSITION_READY', 'Position Ready'),
        ('COMPLETED', 'Completed'),
        ('ERROR', 'Error'),
    ]

    # Link to market data
    market_data = models.ForeignKey(NiftyMarketData, on_delete=models.CASCADE, related_name='algorithm_states')

    # Algorithm State
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='INITIALIZED')
    current_step = models.IntegerField(default=1, help_text="Current step number (1-10)")
    total_steps = models.IntegerField(default=10, help_text="Total steps in algorithm")

    # Selected Strikes
    suggested_call_strike = models.IntegerField(null=True, blank=True, help_text="Suggested CE strike")
    suggested_put_strike = models.IntegerField(null=True, blank=True, help_text="Suggested PE strike")

    # Premium Data
    call_premium = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    put_premium = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_premium = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Delta Analysis
    call_delta = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    put_delta = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    net_delta = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="Net position delta")
    delta_target = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('300'), help_text="Target delta (usually 300)")

    # Risk Metrics
    max_loss = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Max potential loss")
    breakeven_upper = models.IntegerField(null=True, blank=True, help_text="Upper breakeven point")
    breakeven_lower = models.IntegerField(null=True, blank=True, help_text="Lower breakeven point")
    margin_required = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Algorithm Progress Logs
    step_1_data = models.JSONField(default=dict, blank=True, help_text="Step 1: Market data collection")
    step_2_data = models.JSONField(default=dict, blank=True, help_text="Step 2: Option chain analysis")
    step_3_data = models.JSONField(default=dict, blank=True, help_text="Step 3: ATM strike identification")
    step_4_data = models.JSONField(default=dict, blank=True, help_text="Step 4: Call strike selection")
    step_5_data = models.JSONField(default=dict, blank=True, help_text="Step 5: Put strike selection")
    step_6_data = models.JSONField(default=dict, blank=True, help_text="Step 6: Delta calculation")
    step_7_data = models.JSONField(default=dict, blank=True, help_text="Step 7: Premium evaluation")
    step_8_data = models.JSONField(default=dict, blank=True, help_text="Step 8: Risk assessment")
    step_9_data = models.JSONField(default=dict, blank=True, help_text="Step 9: Final validation")
    step_10_data = models.JSONField(default=dict, blank=True, help_text="Step 10: Position summary")

    # Execution metadata
    execution_time_ms = models.IntegerField(null=True, blank=True, help_text="Algorithm execution time")
    error_message = models.TextField(blank=True, help_text="Error details if status=ERROR")

    # Account for which this was triggered
    account = models.ForeignKey('accounts.BrokerAccount', on_delete=models.SET_NULL, null=True, blank=True, help_text="Broker account for this strangle")

    class Meta:
        db_table = 'strangle_algorithm_state'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Strangle State {self.id} - {self.status} (Step {self.current_step}/{self.total_steps})"

    def get_progress_percentage(self):
        """Calculate progress percentage"""
        return int((self.current_step / self.total_steps) * 100)
