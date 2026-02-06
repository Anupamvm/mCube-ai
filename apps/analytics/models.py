"""
Analytics and performance tracking models for mCube Trading System

Models:
- DailyPnL: Daily P&L summary per account
- Performance: Weekly/Monthly/Yearly performance metrics
- LearningSession: Learning system sessions
- TradePerformance: Individual trade analysis
- LearningPattern: Discovered trading patterns
- ParameterAdjustment: Suggested parameter changes
- PerformanceMetric: Granular metrics for learning
- FinancialYearSummary: Pre-computed FY analytics
- UserDecisionLog: ML-ready user action logging
- MarketContextSnapshot: Market state at decision time
- UserBehaviorProfile: Aggregated user patterns
- DailyEquityCurve: Daily capital tracking
- AccountReturns: Pre-computed period returns
- BenchmarkData: Nifty/BankNifty daily data
- PortfolioBeta: Alpha/Beta calculations
- MLFeatureStore: Pre-computed ML features
"""

from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
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

    # Outcome tracking (for algorithm learning)
    final_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Final realized P&L when position closed"
    )
    max_profit_during_trade = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum unrealized profit during trade"
    )
    max_drawdown_during_trade = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum unrealized loss during trade"
    )
    exit_reason = models.CharField(
        max_length=30,
        choices=[
            ('STOP_LOSS_HIT', 'Stop Loss Hit'),
            ('TARGET_HIT', 'Target Hit'),
            ('TIME_EXIT', 'Time Exit'),
            ('MANUAL', 'Manual Close'),
            ('UNKNOWN', 'Unknown'),
        ],
        default='UNKNOWN',
        help_text="Reason for exit"
    )
    was_averaged = models.BooleanField(
        default=False,
        help_text="Whether averaging was used on this position"
    )
    averaging_helped = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether averaging improved the outcome"
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


class FinancialYearSummary(TimeStampedModel):
    """
    Pre-computed financial year analytics for performance reporting.

    Stores aggregated trading performance metrics for each financial year
    (April 1 to March 31) with optional filters by strategy and trade type.
    """

    STRATEGY_CHOICES = [
        ('', 'All Strategies'),
        ('kotak_strangle', 'Kotak Strangle'),
        ('kotak_broken_iron_condor', 'Kotak Broken Iron Condor'),
        ('icici_futures', 'ICICI Futures'),
    ]

    TRADE_TYPE_CHOICES = [
        ('', 'All Types'),
        ('OPTIONS', 'Options'),
        ('FUTURES', 'Futures'),
    ]

    # User and Account
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='fy_summaries'
    )
    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='fy_summaries',
        help_text="Specific account or NULL for all accounts"
    )

    # Financial Year Period (April 1 to March 31)
    fy_start = models.DateField(
        help_text="FY start date (April 1)"
    )
    fy_end = models.DateField(
        help_text="FY end date (March 31)"
    )
    fy_label = models.CharField(
        max_length=20,
        help_text="Display label like 'FY2024-25'"
    )

    # Filters
    strategy = models.CharField(
        max_length=30,
        choices=STRATEGY_CHOICES,
        blank=True,
        default='',
        help_text="Filter by strategy or empty for all"
    )
    trade_type = models.CharField(
        max_length=10,
        choices=TRADE_TYPE_CHOICES,
        blank=True,
        default='',
        help_text="Filter by trade type or empty for all"
    )

    # Trade Counts
    total_trades = models.IntegerField(
        default=0,
        help_text="Total number of closed trades"
    )
    winning_trades = models.IntegerField(
        default=0,
        help_text="Number of profitable trades"
    )
    losing_trades = models.IntegerField(
        default=0,
        help_text="Number of losing trades"
    )
    breakeven_trades = models.IntegerField(
        default=0,
        help_text="Number of breakeven trades"
    )

    # P&L Metrics
    gross_profit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sum of all profits"
    )
    gross_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sum of all losses (positive number)"
    )
    net_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Net profit/loss"
    )
    total_charges = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total brokerage and other charges"
    )

    # Performance Ratios
    win_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Win rate percentage"
    )
    profit_factor = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Gross profit / Gross loss"
    )
    average_win = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Average profit per winning trade"
    )
    average_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Average loss per losing trade"
    )

    # Extremes
    largest_win = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Largest single winning trade"
    )
    largest_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Largest single losing trade"
    )

    # Drawdown
    max_drawdown = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Maximum drawdown in absolute terms"
    )
    max_drawdown_pct = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Maximum drawdown as percentage"
    )

    # Monthly Breakdown (JSON for flexibility)
    monthly_pnl = models.JSONField(
        default=dict,
        blank=True,
        help_text="Monthly P&L breakdown: {'Apr': 1000, 'May': -500, ...}"
    )

    # Best/Worst periods
    best_month = models.CharField(
        max_length=20,
        blank=True,
        help_text="Best performing month"
    )
    best_month_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    worst_month = models.CharField(
        max_length=20,
        blank=True,
        help_text="Worst performing month"
    )
    worst_month_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Average metrics
    avg_trade_duration_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average trade duration in hours"
    )
    avg_margin_used = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average margin deployed per trade"
    )
    avg_return_on_margin = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average ROM percentage"
    )

    # Metadata
    last_computed_at = models.DateTimeField(
        auto_now=True,
        help_text="When summary was last computed"
    )
    trades_included_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last trade included in this summary"
    )

    class Meta:
        db_table = 'financial_year_summary'
        verbose_name = 'Financial Year Summary'
        verbose_name_plural = 'Financial Year Summaries'
        ordering = ['-fy_start']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'account', 'fy_start', 'strategy', 'trade_type'],
                name='unique_fy_summary'
            )
        ]
        indexes = [
            models.Index(fields=['user', 'fy_start']),
            models.Index(fields=['account', 'fy_start']),
            models.Index(fields=['fy_label']),
        ]

    def __str__(self):
        parts = [self.fy_label]
        if self.account:
            parts.append(self.account.account_name)
        if self.strategy:
            parts.append(self.strategy)
        if self.trade_type:
            parts.append(self.trade_type)
        return ' - '.join(parts)

    @classmethod
    def get_fy_dates(cls, fy_year):
        """
        Get FY start and end dates for a given FY year.

        Args:
            fy_year: Start year of FY (e.g., 2024 for FY2024-25)

        Returns:
            Tuple: (fy_start, fy_end, fy_label)
        """
        from datetime import date
        fy_start = date(fy_year, 4, 1)  # April 1
        fy_end = date(fy_year + 1, 3, 31)  # March 31
        fy_label = f"FY{fy_year}-{str(fy_year + 1)[-2:]}"
        return fy_start, fy_end, fy_label

    @classmethod
    def get_current_fy_year(cls):
        """
        Get the current financial year's start year.

        Returns:
            int: FY start year (e.g., 2024 if current date is in FY2024-25)
        """
        from datetime import date
        today = date.today()
        if today.month >= 4:  # April onwards is current FY
            return today.year
        else:  # Jan-Mar belongs to previous FY
            return today.year - 1

    def get_monthly_chart_data(self):
        """
        Get monthly P&L formatted for chart display.

        Returns:
            Dict with labels and data arrays
        """
        months = ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
                  'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar']

        data = []
        for month in months:
            value = self.monthly_pnl.get(month, 0)
            data.append(float(value))

        return {
            'labels': months,
            'data': data,
            'colors': ['green' if v >= 0 else 'red' for v in data]
        }

    def get_summary_dict(self):
        """
        Get summary data as dictionary for API/template use.

        Returns:
            Dict with all summary metrics
        """
        return {
            'fy_label': self.fy_label,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'breakeven_trades': self.breakeven_trades,
            'net_pnl': float(self.net_pnl),
            'gross_profit': float(self.gross_profit),
            'gross_loss': float(self.gross_loss),
            'total_charges': float(self.total_charges),
            'win_rate': float(self.win_rate),
            'profit_factor': float(self.profit_factor),
            'average_win': float(self.average_win),
            'average_loss': float(self.average_loss),
            'largest_win': float(self.largest_win),
            'largest_loss': float(self.largest_loss),
            'max_drawdown': float(self.max_drawdown),
            'max_drawdown_pct': float(self.max_drawdown_pct),
            'monthly_pnl': self.monthly_pnl,
            'best_month': self.best_month,
            'best_month_pnl': float(self.best_month_pnl) if self.best_month_pnl else None,
            'worst_month': self.worst_month,
            'worst_month_pnl': float(self.worst_month_pnl) if self.worst_month_pnl else None,
        }


# =============================================================================
# ML-READY USER ACTION LOGGING MODELS (Phase 1)
# =============================================================================

class UserDecisionLog(TimeStampedModel):
    """
    Core ML training data - logs every user decision on trade suggestions.
    Captures decision context, timing, and eventual outcome for ML training.
    """

    DECISION_TYPE_CHOICES = [
        ('APPROVE', 'Approved'),
        ('REJECT', 'Rejected'),
        ('MODIFY', 'Modified'),
        ('IGNORE', 'Ignored'),
        ('AUTO_APPROVE', 'Auto-Approved'),
    ]

    OUTCOME_CHOICES = [
        ('PROFIT', 'Profit'),
        ('LOSS', 'Loss'),
        ('BREAKEVEN', 'Breakeven'),
        ('N/A', 'Not Applicable'),
        ('PENDING', 'Pending'),
    ]

    # Core References
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='decision_logs'
    )
    suggestion = models.ForeignKey(
        'trading.TradeSuggestion',
        on_delete=models.CASCADE,
        related_name='decision_logs'
    )

    # Decision Details
    decision_type = models.CharField(
        max_length=15,
        choices=DECISION_TYPE_CHOICES
    )
    decision_timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text="When the decision was made"
    )

    # Behavioral Metrics
    time_to_decision_seconds = models.IntegerField(
        null=True,
        blank=True,
        help_text="Time from suggestion creation to decision"
    )
    suggestion_viewed_count = models.IntegerField(
        default=1,
        help_text="How many times user viewed before deciding"
    )

    # Market Context at Decision Time
    market_context = models.JSONField(
        default=dict,
        help_text="Market state: spot, vix, oi, trend, pcr, etc."
    )
    market_snapshot = models.ForeignKey(
        'MarketContextSnapshot',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decision_logs'
    )

    # Algorithm Metrics
    algorithm_confidence = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Algorithm's confidence score (0-100)"
    )
    algorithm_signal_strength = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Signal strength from algorithm"
    )

    # Original vs Modified Parameters
    original_parameters = models.JSONField(
        default=dict,
        help_text="Original parameters from suggestion"
    )
    modified_parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="User-modified parameters (for MODIFY decisions)"
    )

    # Outcome Tracking (filled after trade closes)
    final_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Final P&L if trade was taken"
    )
    final_outcome = models.CharField(
        max_length=15,
        choices=OUTCOME_CHOICES,
        default='PENDING'
    )
    outcome_linked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When outcome was linked back"
    )

    # User Notes
    decision_notes = models.TextField(
        blank=True,
        help_text="User's reason for the decision"
    )

    class Meta:
        db_table = 'user_decision_log'
        ordering = ['-decision_timestamp']
        indexes = [
            models.Index(fields=['user', '-decision_timestamp']),
            models.Index(fields=['decision_type', '-decision_timestamp']),
            models.Index(fields=['final_outcome']),
            models.Index(fields=['suggestion', 'decision_type']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.decision_type} - {self.suggestion}"


class MarketContextSnapshot(TimeStampedModel):
    """
    Captures complete market state at a specific point in time.
    Used for ML feature engineering and decision context.
    """

    TREND_CHOICES = [
        ('STRONG_UP', 'Strong Uptrend'),
        ('UP', 'Uptrend'),
        ('SIDEWAYS', 'Sideways'),
        ('DOWN', 'Downtrend'),
        ('STRONG_DOWN', 'Strong Downtrend'),
    ]

    # Timestamp
    snapshot_timestamp = models.DateTimeField(
        db_index=True,
        help_text="Exact time of snapshot"
    )

    # Index Prices
    nifty_spot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    banknifty_spot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    india_vix = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Day Change
    nifty_day_change_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    nifty_trend = models.CharField(
        max_length=15,
        choices=TREND_CHOICES,
        blank=True
    )

    # Open Interest Data
    total_call_oi = models.BigIntegerField(null=True, blank=True)
    total_put_oi = models.BigIntegerField(null=True, blank=True)
    pcr_oi = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Put/Call ratio by OI"
    )
    max_pain = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Technical Indicators
    rsi_14 = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    macd_signal = models.CharField(
        max_length=10,
        choices=[('BUY', 'Buy'), ('SELL', 'Sell'), ('NEUTRAL', 'Neutral')],
        blank=True
    )

    # Raw data for complete snapshot
    raw_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Complete raw market data snapshot"
    )

    class Meta:
        db_table = 'market_context_snapshot'
        ordering = ['-snapshot_timestamp']
        indexes = [
            models.Index(fields=['-snapshot_timestamp']),
            models.Index(fields=['nifty_trend', '-snapshot_timestamp']),
        ]

    def __str__(self):
        vix = self.india_vix or 'N/A'
        return f"Market @ {self.snapshot_timestamp.strftime('%Y-%m-%d %H:%M')} - VIX: {vix}"


class UserBehaviorProfile(TimeStampedModel):
    """
    Aggregated user behavior patterns computed from decision logs.
    Used as ML features for personalization.
    """

    # One profile per user
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='behavior_profile'
    )

    # Decision Counts
    total_suggestions_received = models.IntegerField(default=0)
    suggestions_approved = models.IntegerField(default=0)
    suggestions_rejected = models.IntegerField(default=0)
    suggestions_modified = models.IntegerField(default=0)
    suggestions_ignored = models.IntegerField(default=0)

    # Rates
    approval_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Percentage of suggestions approved"
    )
    modification_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Percentage of suggestions modified"
    )

    # Timing
    avg_decision_time_seconds = models.IntegerField(
        default=0,
        help_text="Average time to make a decision"
    )
    median_decision_time_seconds = models.IntegerField(
        default=0,
        help_text="Median time to make a decision"
    )

    # Strategy-specific Approval Rates
    strategy_approval_rates = models.JSONField(
        default=dict,
        help_text="Approval rate by strategy: {'kotak_strangle': 75.0, ...}"
    )

    # Market Condition Preferences
    high_vix_approval_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Approval rate when VIX > 18"
    )
    low_vix_approval_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Approval rate when VIX <= 18"
    )

    # Performance Metrics
    approved_trades_win_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Win rate of trades user approved"
    )
    rejected_trades_would_have_won_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Rate at which rejected trades would have been profitable"
    )

    # Last Computed
    last_computed_at = models.DateTimeField(
        auto_now=True,
        help_text="When profile was last computed"
    )
    decisions_included = models.IntegerField(
        default=0,
        help_text="Number of decisions included in computation"
    )

    class Meta:
        db_table = 'user_behavior_profile'
        verbose_name = 'User Behavior Profile'
        verbose_name_plural = 'User Behavior Profiles'

    def __str__(self):
        return f"{self.user.username} - {self.approval_rate}% approval rate"


# =============================================================================
# RETURNS CALCULATION MODELS (Phase 2)
# =============================================================================

class DailyEquityCurve(TimeStampedModel):
    """
    Daily capital and equity tracking for each account.
    Used for equity curve visualization and drawdown calculations.
    """

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='equity_curves'
    )
    date = models.DateField(db_index=True)

    # Capital Metrics
    opening_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Capital at market open"
    )
    closing_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Capital at market close"
    )
    high_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Peak capital during the day"
    )
    low_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Lowest capital during the day"
    )

    # P&L Breakdown
    realized_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    unrealized_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Cumulative Metrics
    cumulative_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total P&L since inception"
    )
    cumulative_return_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.00'),
        help_text="Cumulative return percentage"
    )

    # Drawdown Tracking
    peak_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="All-time high capital (for drawdown calc)"
    )
    current_drawdown = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Current drawdown from peak"
    )
    drawdown_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.00'),
        help_text="Drawdown as percentage"
    )

    # Benchmark Comparison
    nifty_close = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    nifty_return_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Nifty's return on this day"
    )
    alpha = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Daily alpha vs Nifty"
    )

    # Trade Stats
    trades_taken = models.IntegerField(default=0)
    trades_closed = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)

    class Meta:
        db_table = 'daily_equity_curve'
        unique_together = ['account', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['account', '-date']),
            models.Index(fields=['-date']),
        ]

    def __str__(self):
        return f"{self.account.account_name} - {self.date} - Rs.{self.closing_capital:,.2f}"

    @property
    def daily_return_pct(self):
        """Calculate daily return percentage"""
        if self.opening_capital and self.opening_capital > 0:
            return ((self.closing_capital - self.opening_capital) / self.opening_capital) * 100
        return Decimal('0.00')


class AccountReturns(TimeStampedModel):
    """
    Pre-computed period returns for each account.
    Includes risk-adjusted metrics like Sharpe and Sortino ratios.
    """

    PERIOD_TYPE_CHOICES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('FY', 'Financial Year'),
        ('YTD', 'Year to Date'),
        ('ALL_TIME', 'All Time'),
    ]

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='account_returns'
    )

    # Period Definition
    period_type = models.CharField(
        max_length=15,
        choices=PERIOD_TYPE_CHOICES
    )
    period_start = models.DateField()
    period_end = models.DateField()
    period_label = models.CharField(
        max_length=30,
        blank=True,
        help_text="Display label like 'Jan 2025' or 'FY2024-25'"
    )

    # Capital
    starting_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2
    )
    ending_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2
    )
    avg_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Returns
    absolute_return = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Absolute P&L"
    )
    percentage_return = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Return percentage"
    )
    annualized_return = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Annualized return (CAGR)"
    )

    # Risk Metrics
    max_drawdown = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    max_drawdown_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.00')
    )
    volatility = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Standard deviation of returns"
    )

    # Risk-Adjusted Returns
    sharpe_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    sortino_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    calmar_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Annualized return / Max drawdown"
    )

    # Trade Statistics
    total_trades = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)
    win_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00')
    )
    profit_factor = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    avg_win = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    avg_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Costs
    total_brokerage = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_taxes = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_charges = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Strategy Breakdown
    strategy_returns = models.JSONField(
        default=dict,
        help_text="Returns by strategy: {'kotak_strangle': {...}, ...}"
    )

    class Meta:
        db_table = 'account_returns'
        ordering = ['-period_end']
        indexes = [
            models.Index(fields=['account', 'period_type', '-period_end']),
            models.Index(fields=['period_type', '-period_end']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'period_type', 'period_start', 'period_end'],
                name='unique_account_period'
            )
        ]

    def __str__(self):
        return f"{self.account.account_name} - {self.period_type} - {self.period_label}"


class BenchmarkData(TimeStampedModel):
    """
    Daily benchmark data (Nifty/BankNifty) for performance comparison.
    """

    BENCHMARK_CHOICES = [
        ('NIFTY50', 'Nifty 50'),
        ('BANKNIFTY', 'Bank Nifty'),
        ('NIFTYIT', 'Nifty IT'),
    ]

    benchmark = models.CharField(
        max_length=15,
        choices=BENCHMARK_CHOICES
    )
    date = models.DateField(db_index=True)

    # OHLC Data
    open = models.DecimalField(max_digits=12, decimal_places=2)
    high = models.DecimalField(max_digits=12, decimal_places=2)
    low = models.DecimalField(max_digits=12, decimal_places=2)
    close = models.DecimalField(max_digits=12, decimal_places=2)

    # Volume (if available)
    volume = models.BigIntegerField(null=True, blank=True)

    # Returns
    daily_return_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    cumulative_return_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Cumulative return from FY start"
    )

    class Meta:
        db_table = 'benchmark_data'
        unique_together = ['benchmark', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['benchmark', '-date']),
        ]

    def __str__(self):
        return f"{self.benchmark} - {self.date} - {self.close}"


class PortfolioBeta(TimeStampedModel):
    """
    Alpha/Beta calculations for portfolio vs benchmark.
    """

    PERIOD_TYPE_CHOICES = [
        ('30D', '30 Days'),
        ('60D', '60 Days'),
        ('90D', '90 Days'),
        ('180D', '180 Days'),
        ('1Y', '1 Year'),
        ('ALL', 'All Time'),
    ]

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        related_name='portfolio_betas'
    )
    benchmark = models.CharField(
        max_length=15,
        choices=BenchmarkData.BENCHMARK_CHOICES
    )
    period_type = models.CharField(
        max_length=10,
        choices=PERIOD_TYPE_CHOICES
    )
    calculation_date = models.DateField()

    # Beta/Alpha
    beta = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Portfolio beta vs benchmark"
    )
    alpha = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Portfolio alpha (excess return)"
    )

    # Correlation
    r_squared = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="R-squared of regression"
    )
    correlation = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )

    # Returns Used in Calculation
    portfolio_return = models.DecimalField(
        max_digits=10,
        decimal_places=4
    )
    benchmark_return = models.DecimalField(
        max_digits=10,
        decimal_places=4
    )
    excess_return = models.DecimalField(
        max_digits=10,
        decimal_places=4
    )

    # Risk-Free Rate Used
    risk_free_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal('0.065'),
        help_text="Risk-free rate used (default 6.5% T-bill)"
    )

    class Meta:
        db_table = 'portfolio_beta'
        ordering = ['-calculation_date']
        indexes = [
            models.Index(fields=['account', 'benchmark', '-calculation_date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'benchmark', 'period_type', 'calculation_date'],
                name='unique_beta_calculation'
            )
        ]

    def __str__(self):
        return f"{self.account.account_name} vs {self.benchmark} - β:{self.beta:.2f} α:{self.alpha:.2f}"


# =============================================================================
# ML FEATURE ENGINEERING MODEL (Phase 3)
# =============================================================================

class MLFeatureStore(TimeStampedModel):
    """
    Pre-computed ML features for each user decision.
    Stores feature vectors ready for ML training/inference.
    """

    # Link to Decision
    decision_log = models.OneToOneField(
        UserDecisionLog,
        on_delete=models.CASCADE,
        related_name='ml_features'
    )

    # Market Features
    spot_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    vix = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    vix_percentile_30d = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="VIX percentile over last 30 days"
    )

    # Time Features
    day_of_week = models.IntegerField(
        null=True,
        blank=True,
        help_text="0=Monday, 6=Sunday"
    )
    hour_of_day = models.IntegerField(null=True, blank=True)
    days_to_expiry = models.IntegerField(null=True, blank=True)
    is_expiry_week = models.BooleanField(default=False)
    is_monthly_expiry = models.BooleanField(default=False)

    # Trend Features
    spot_vs_sma20 = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="(Spot - SMA20) / SMA20 * 100"
    )
    spot_vs_sma50 = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    rsi_14 = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    macd_histogram = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )

    # OI Features
    pcr_oi = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True
    )
    pcr_volume = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True
    )
    max_pain_distance_pct = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Distance from max pain as percentage"
    )

    # Algorithm Features
    algo_confidence = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    algo_signal_strength = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    strategy_type = models.CharField(max_length=30, blank=True)

    # User Behavior Features
    user_historical_approval_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    user_avg_decision_time = models.IntegerField(null=True, blank=True)
    user_win_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Recent Performance Features
    last_5_trades_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    last_5_trades_win_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    current_streak = models.IntegerField(
        default=0,
        help_text="Positive for win streak, negative for loss streak"
    )
    current_day_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Labels (computed after outcome is known)
    label_1d_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="P&L after 1 day (if closed)"
    )
    label_1d_outcome = models.CharField(
        max_length=15,
        blank=True,
        help_text="1-day outcome: PROFIT/LOSS/OPEN"
    )
    label_final_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    label_final_outcome = models.CharField(
        max_length=15,
        blank=True,
        help_text="Final outcome: PROFIT/LOSS/BREAKEVEN"
    )

    # Complete Feature Vector (for ML)
    feature_vector = models.JSONField(
        default=list,
        help_text="Ordered list of features for ML model"
    )
    feature_version = models.CharField(
        max_length=10,
        default='v1',
        help_text="Feature engineering version"
    )

    # Computation Status
    is_complete = models.BooleanField(
        default=False,
        help_text="Whether all features are computed"
    )
    labels_computed = models.BooleanField(
        default=False,
        help_text="Whether outcome labels are computed"
    )
    computed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'ml_feature_store'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_complete', 'labels_computed']),
            models.Index(fields=['strategy_type']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        status = "Complete" if self.is_complete else "Partial"
        return f"Features for Decision #{self.decision_log_id} - {status}"
