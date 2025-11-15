"""
Analytics and performance tracking models for mCube Trading System
"""

from decimal import Decimal
from django.db import models
from apps.core.models import TimeStampedModel


class DailyPnL(TimeStampedModel):
    """Daily P&L summary"""

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='daily_pnls'
    )

    date = models.DateField(db_index=True)

    # P&L breakdown
    realized_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    unrealized_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    # Trading activity
    trades_count = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)

    # Capital metrics
    starting_capital = models.DecimalField(max_digits=15, decimal_places=2)
    ending_capital = models.DecimalField(max_digits=15, decimal_places=2)
    max_capital_deployed = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    # Risk metrics
    max_drawdown = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0.00'))
    risk_limits_breached = models.IntegerField(default=0)

    # Notes
    summary = models.TextField(blank=True)

    class Meta:
        db_table = 'daily_pnl'
        unique_together = ['account', 'date']
        ordering = ['-date']
        indexes = [models.Index(fields=['account', '-date'])]

    def __str__(self):
        return f"{self.account.account_name} - {self.date} - Rs.{self.total_pnl:,.2f}"

    def calculate_win_rate(self) -> Decimal:
        """Calculate win rate percentage"""
        total = self.winning_trades + self.losing_trades
        if total == 0:
            return Decimal('0.00')
        return (Decimal(self.winning_trades) / Decimal(total)) * 100


class Performance(TimeStampedModel):
    """Performance metrics (weekly/monthly)"""

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='performances'
    )

    period_type = models.CharField(
        max_length=20,
        choices=[('WEEKLY', 'Weekly'), ('MONTHLY', 'Monthly'), ('YEARLY', 'Yearly')]
    )
    period_start = models.DateField()
    period_end = models.DateField()

    # P&L metrics
    total_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_trades = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)

    # Performance ratios
    win_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    profit_factor = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0.00'))
    sharpe_ratio = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    # Capital metrics
    avg_capital_deployed = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    max_drawdown = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0.00'))

    # Strategy breakdown
    strategy_performance = models.JSONField(default=dict, help_text="P&L by strategy")

    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'performance'
        ordering = ['-period_end']
        indexes = [models.Index(fields=['account', 'period_type', '-period_end'])]

    def __str__(self):
        return f"{self.account.account_name} - {self.period_type} - {self.period_start} to {self.period_end}"


class LearningSession(TimeStampedModel):
    """Track learning system sessions"""

    STATUS_CHOICES = [
        ('RUNNING', 'Running'),
        ('STOPPED', 'Stopped'),
        ('PAUSED', 'Paused'),
        ('COMPLETED', 'Completed'),
    ]

    name = models.CharField(max_length=100, help_text="Session name/description")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='STOPPED')

    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    # Learning configuration
    min_trades_required = models.IntegerField(default=10, help_text="Minimum trades to start learning")
    confidence_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('70.00'),
        help_text="Minimum confidence % to suggest changes"
    )

    # Learning progress
    trades_analyzed = models.IntegerField(default=0)
    patterns_discovered = models.IntegerField(default=0)
    parameters_adjusted = models.IntegerField(default=0)

    # Performance tracking
    pre_learning_win_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    post_learning_win_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    improvement_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.00'),
        help_text="Overall improvement percentage"
    )

    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'learning_sessions'
        ordering = ['-created_at']

    def __str__(self):
        return f"Learning Session: {self.name} ({self.status})"

    def is_active(self):
        """Check if learning session is currently active"""
        return self.status == 'RUNNING'


class TradePerformance(TimeStampedModel):
    """Detailed analysis of individual trade performance"""

    position = models.OneToOneField(
        'positions.Position',
        on_delete=models.CASCADE,
        related_name='performance_analysis'
    )

    # Entry analysis
    entry_conditions = models.JSONField(
        default=dict,
        help_text="Market conditions at entry: VIX, trends, indicators, etc."
    )
    entry_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Quality score of entry (0-100)"
    )

    # Exit analysis
    exit_conditions = models.JSONField(default=dict, blank=True)
    exit_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Quality score of exit (0-100)"
    )

    # Performance metrics
    max_favorable_excursion = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Maximum profit during trade"
    )
    max_adverse_excursion = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Maximum loss during trade"
    )

    # Timing analysis
    hold_duration_minutes = models.IntegerField(default=0)
    entry_time_quality = models.CharField(
        max_length=20,
        choices=[
            ('EXCELLENT', 'Excellent'),
            ('GOOD', 'Good'),
            ('AVERAGE', 'Average'),
            ('POOR', 'Poor'),
        ],
        default='AVERAGE'
    )

    # Learning insights
    what_worked = models.TextField(blank=True, help_text="What went well")
    what_failed = models.TextField(blank=True, help_text="What didn't work")
    lessons_learned = models.TextField(blank=True, help_text="Key takeaways")

    # Pattern matching
    similar_patterns_count = models.IntegerField(
        default=0,
        help_text="Number of similar historical trades"
    )
    pattern_success_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Success rate of this pattern"
    )

    class Meta:
        db_table = 'trade_performance'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['entry_score']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"Performance: {self.position.symbol} - Score: {self.entry_score}"


class LearningPattern(TimeStampedModel):
    """Discovered patterns that lead to profitable/unprofitable trades"""

    PATTERN_TYPE_CHOICES = [
        ('ENTRY_TIMING', 'Entry Timing'),
        ('STRIKE_SELECTION', 'Strike Selection'),
        ('MARKET_CONDITION', 'Market Condition'),
        ('DELTA_BEHAVIOR', 'Delta Behavior'),
        ('EXIT_TIMING', 'Exit Timing'),
        ('VIX_PATTERN', 'VIX Pattern'),
        ('SECTOR_CORRELATION', 'Sector Correlation'),
        ('OTHER', 'Other'),
    ]

    session = models.ForeignKey(
        LearningSession,
        on_delete=models.CASCADE,
        related_name='patterns'
    )

    pattern_type = models.CharField(max_length=30, choices=PATTERN_TYPE_CHOICES)
    name = models.CharField(max_length=200, help_text="Pattern name/description")
    description = models.TextField(help_text="Detailed pattern description")

    # Pattern characteristics
    conditions = models.JSONField(
        help_text="JSON of conditions that define this pattern"
    )

    # Statistical significance
    occurrences = models.IntegerField(default=0, help_text="Times pattern observed")
    profitable_occurrences = models.IntegerField(default=0)
    unprofitable_occurrences = models.IntegerField(default=0)

    success_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Success rate percentage"
    )

    avg_profit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Average profit when pattern occurs"
    )

    avg_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Average loss when pattern occurs"
    )

    # Confidence and recommendation
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Statistical confidence in this pattern (0-100)"
    )

    is_actionable = models.BooleanField(
        default=False,
        help_text="Whether this pattern should influence trading decisions"
    )

    recommendation = models.TextField(
        blank=True,
        help_text="Trading recommendation based on this pattern"
    )

    # Validation
    last_validated = models.DateTimeField(null=True, blank=True)
    validation_status = models.CharField(
        max_length=20,
        choices=[
            ('ACTIVE', 'Active'),
            ('TESTING', 'Testing'),
            ('INVALIDATED', 'Invalidated'),
        ],
        default='TESTING'
    )

    class Meta:
        db_table = 'learning_patterns'
        ordering = ['-confidence_score', '-success_rate']
        indexes = [
            models.Index(fields=['pattern_type', '-confidence_score']),
            models.Index(fields=['is_actionable', '-success_rate']),
        ]

    def __str__(self):
        return f"{self.name} ({self.success_rate}% success, {self.confidence_score}% confidence)"


class ParameterAdjustment(TimeStampedModel):
    """Suggested parameter adjustments based on learning"""

    STATUS_CHOICES = [
        ('SUGGESTED', 'Suggested'),
        ('APPROVED', 'Approved'),
        ('APPLIED', 'Applied'),
        ('REJECTED', 'Rejected'),
        ('TESTING', 'Testing'),
    ]

    session = models.ForeignKey(
        LearningSession,
        on_delete=models.CASCADE,
        related_name='adjustments'
    )

    # What parameter to adjust
    parameter_name = models.CharField(max_length=100, help_text="Parameter name (e.g., 'base_delta_pct')")
    parameter_category = models.CharField(
        max_length=50,
        help_text="Category: strategy, risk, entry, exit, etc."
    )

    # Current and suggested values
    current_value = models.CharField(max_length=100)
    suggested_value = models.CharField(max_length=100)

    # Reasoning
    reason = models.TextField(help_text="Why this adjustment is suggested")
    supporting_data = models.JSONField(
        help_text="Data supporting this adjustment (patterns, statistics)"
    )

    # Impact analysis
    expected_improvement_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Expected improvement in win rate or P&L"
    )

    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Confidence in this suggestion (0-100)"
    )

    risk_level = models.CharField(
        max_length=20,
        choices=[
            ('LOW', 'Low Risk'),
            ('MEDIUM', 'Medium Risk'),
            ('HIGH', 'High Risk'),
        ],
        default='MEDIUM'
    )

    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUGGESTED')
    reviewed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parameter_reviews'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    # Testing results
    applied_at = models.DateTimeField(null=True, blank=True)
    test_start_date = models.DateField(null=True, blank=True)
    test_end_date = models.DateField(null=True, blank=True)
    actual_improvement_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Actual improvement observed during testing"
    )

    class Meta:
        db_table = 'parameter_adjustments'
        ordering = ['-confidence', '-expected_improvement_pct']
        indexes = [
            models.Index(fields=['status', '-confidence']),
            models.Index(fields=['parameter_category']),
        ]

    def __str__(self):
        return f"{self.parameter_name}: {self.current_value} → {self.suggested_value} ({self.status})"


class PerformanceMetric(TimeStampedModel):
    """Granular performance metrics for learning system"""

    METRIC_TYPE_CHOICES = [
        ('WIN_RATE', 'Win Rate'),
        ('PROFIT_FACTOR', 'Profit Factor'),
        ('AVG_PROFIT', 'Average Profit'),
        ('AVG_LOSS', 'Average Loss'),
        ('MAX_DRAWDOWN', 'Max Drawdown'),
        ('SHARPE_RATIO', 'Sharpe Ratio'),
        ('ENTRY_ACCURACY', 'Entry Accuracy'),
        ('EXIT_EFFICIENCY', 'Exit Efficiency'),
        ('RISK_REWARD', 'Risk/Reward Ratio'),
    ]

    session = models.ForeignKey(
        LearningSession,
        on_delete=models.CASCADE,
        related_name='metrics',
        null=True,
        blank=True
    )

    metric_type = models.CharField(max_length=30, choices=METRIC_TYPE_CHOICES)
    metric_value = models.DecimalField(max_digits=15, decimal_places=4)

    # Context
    strategy = models.CharField(max_length=50, blank=True)
    time_period = models.CharField(max_length=50, blank=True, help_text="e.g., 'last_7_days'")

    # Metadata
    calculation_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'performance_metrics'
        ordering = ['-calculation_date']
        indexes = [
            models.Index(fields=['metric_type', '-calculation_date']),
            models.Index(fields=['session', 'metric_type']),
        ]

    def __str__(self):
        return f"{self.metric_type}: {self.metric_value}"
