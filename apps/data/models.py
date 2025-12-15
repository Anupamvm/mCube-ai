"""
Market data models for mCube Trading System
"""

from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import TimeStampedModel

User = get_user_model()


class MarketData(TimeStampedModel):
    """Market data snapshot"""

    symbol = models.CharField(max_length=50, db_index=True)
    exchange = models.CharField(max_length=20, default='NSE')
    timestamp = models.DateTimeField(db_index=True)

    open = models.DecimalField(max_digits=15, decimal_places=2)
    high = models.DecimalField(max_digits=15, decimal_places=2)
    low = models.DecimalField(max_digits=15, decimal_places=2)
    close = models.DecimalField(max_digits=15, decimal_places=2)
    volume = models.BigIntegerField(default=0)
    open_interest = models.BigIntegerField(default=0, null=True, blank=True)

    class Meta:
        db_table = 'market_data'
        unique_together = ['symbol', 'timestamp']
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['symbol', '-timestamp'])]

    def __str__(self):
        return f"{self.symbol} @ {self.timestamp}"


class OptionChain(TimeStampedModel):
    """Option chain data"""

    underlying = models.CharField(max_length=50)
    expiry_date = models.DateField()
    strike = models.DecimalField(max_digits=15, decimal_places=2)
    option_type = models.CharField(max_length=2, choices=[('CE', 'Call'), ('PE', 'Put')])

    ltp = models.DecimalField(max_digits=15, decimal_places=2)
    bid = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    ask = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    volume = models.BigIntegerField(default=0)
    oi = models.BigIntegerField(default=0)
    oi_change = models.BigIntegerField(default=0)

    iv = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    delta = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    gamma = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    theta = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    vega = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    spot_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Spot price at the time of data fetch")
    snapshot_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'option_chain'
        ordering = ['underlying', 'expiry_date', 'strike']
        indexes = [
            models.Index(fields=['underlying', 'expiry_date', 'option_type']),
        ]

    def __str__(self):
        return f"{self.underlying} {self.strike}{self.option_type} {self.expiry_date}"


class Event(TimeStampedModel):
    """Economic/market event calendar"""

    IMPORTANCE_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    ]

    event_date = models.DateField(db_index=True)
    event_time = models.TimeField(null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    importance = models.CharField(max_length=20, choices=IMPORTANCE_CHOICES)
    country = models.CharField(max_length=50, default='IN')
    category = models.CharField(max_length=50, blank=True)

    actual = models.CharField(max_length=50, blank=True)
    forecast = models.CharField(max_length=50, blank=True)
    previous = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = 'events'
        ordering = ['event_date', 'event_time']
        indexes = [models.Index(fields=['event_date', 'importance'])]

    def __str__(self):
        return f"{self.title} ({self.event_date}) - {self.importance}"


class ContractData(TimeStampedModel):
    """
    Futures & Options contract data from Trendlyne

    Stores comprehensive F&O metrics including price, volume, open interest, and Greeks
    """

    symbol = models.CharField(max_length=50)
    option_type = models.CharField(max_length=10)  # CE/PE/FUT
    strike_price = models.FloatField(null=True, blank=True)
    price = models.FloatField(null=True, blank=True)
    spot = models.FloatField(null=True, blank=True)
    expiry = models.CharField(max_length=50)
    last_updated = models.CharField(max_length=50, null=True, blank=True)
    build_up = models.CharField(max_length=100, blank=True)
    lot_size = models.IntegerField(null=True, blank=True)

    # Price metrics
    day_change = models.FloatField(null=True, blank=True)
    pct_day_change = models.FloatField(null=True, blank=True)
    open_price = models.FloatField(null=True, blank=True)
    high_price = models.FloatField(null=True, blank=True)
    low_price = models.FloatField(null=True, blank=True)
    prev_close_price = models.FloatField(null=True, blank=True)

    # Open Interest metrics
    oi = models.BigIntegerField(null=True, blank=True)
    pct_oi_change = models.FloatField(null=True, blank=True)
    oi_change = models.BigIntegerField(null=True, blank=True)
    prev_day_oi = models.BigIntegerField(null=True, blank=True)

    # Volume metrics
    traded_contracts = models.BigIntegerField(null=True, blank=True)
    traded_contracts_change_pct = models.FloatField(null=True, blank=True)
    shares_traded = models.BigIntegerField(null=True, blank=True)
    pct_volume_shares_change = models.FloatField(null=True, blank=True)
    prev_day_vol = models.BigIntegerField(null=True, blank=True)

    # Futures metrics
    basis = models.FloatField(null=True, blank=True)
    cost_of_carry = models.FloatField(null=True, blank=True)

    # Options Greeks
    iv = models.FloatField(null=True, blank=True)
    prev_day_iv = models.FloatField(null=True, blank=True)
    pct_iv_change = models.FloatField(null=True, blank=True)
    delta = models.FloatField(null=True, blank=True)
    vega = models.FloatField(null=True, blank=True)
    gamma = models.FloatField(null=True, blank=True)
    theta = models.FloatField(null=True, blank=True)
    rho = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'contract_data'
        ordering = ['symbol', 'expiry', 'strike_price']
        indexes = [
            models.Index(fields=['symbol', 'expiry', 'option_type']),
        ]

    def __str__(self):
        return f"{self.symbol} - {self.option_type} - {self.strike_price} ({self.expiry})"


class ContractStockData(TimeStampedModel):
    """
    Stock-level F&O summary data from Trendlyne

    Aggregated metrics for stocks with F&O contracts
    """

    stock_name = models.CharField(max_length=100)
    nse_code = models.CharField(max_length=20, unique=True)
    bse_code = models.CharField(max_length=20, blank=True)
    isin = models.CharField(max_length=20, blank=True)
    current_price = models.FloatField()
    industry_name = models.CharField(max_length=100)
    annualized_volatility = models.FloatField()

    # F&O Open Interest
    fno_total_oi = models.BigIntegerField()
    fno_prev_day_total_oi = models.BigIntegerField()
    fno_total_put_oi = models.BigIntegerField()
    fno_total_call_oi = models.BigIntegerField()
    fno_prev_day_put_oi = models.BigIntegerField()
    fno_prev_day_call_oi = models.BigIntegerField()

    # F&O Volume
    fno_total_put_vol = models.BigIntegerField()
    fno_total_call_vol = models.BigIntegerField()
    fno_prev_day_put_vol = models.BigIntegerField()
    fno_prev_day_call_vol = models.BigIntegerField()

    # F&O Ratios & Changes
    fno_mwpl = models.BigIntegerField()
    fno_pcr_vol = models.FloatField()
    fno_pcr_vol_prev = models.FloatField()
    fno_pcr_vol_change_pct = models.FloatField()
    fno_pcr_oi = models.FloatField()
    fno_pcr_oi_prev = models.FloatField()
    fno_pcr_oi_change_pct = models.FloatField()
    fno_mwpl_pct = models.FloatField()
    fno_mwpl_prev_pct = models.FloatField()
    fno_total_oi_change_pct = models.FloatField()
    fno_put_oi_change_pct = models.FloatField()
    fno_call_oi_change_pct = models.FloatField()
    fno_put_vol_change_pct = models.FloatField()
    fno_call_vol_change_pct = models.FloatField()

    # Rollover metrics
    fno_rollover_cost = models.FloatField()
    fno_rollover_cost_pct = models.FloatField()
    fno_rollover_pct = models.FloatField()

    class Meta:
        db_table = 'contract_stock_data'
        ordering = ['stock_name']

    def __str__(self):
        return f"{self.stock_name} ({self.nse_code})"


class TLStockData(TimeStampedModel):
    """
    Comprehensive stock data from Trendlyne

    Contains 80+ fields including fundamental metrics, technical indicators,
    valuation ratios, and institutional holding data
    """

    # Basic Information
    stock_name = models.CharField(max_length=100, null=True, blank=True)
    nsecode = models.CharField(max_length=20, null=True, blank=True, unique=True)
    bsecode = models.CharField(max_length=20, null=True, blank=True)
    isin = models.CharField(max_length=20, null=True, blank=True)
    industry_name = models.CharField(max_length=100, null=True, blank=True)
    sector_name = models.CharField(max_length=100, null=True, blank=True)
    current_price = models.FloatField(null=True, blank=True)
    market_capitalization = models.BigIntegerField(null=True, blank=True)

    # Trendlyne Scoring (Daily/Weekly/Monthly)
    trendlyne_durability_score = models.FloatField(null=True, blank=True)
    trendlyne_valuation_score = models.FloatField(null=True, blank=True)
    trendlyne_momentum_score = models.FloatField(null=True, blank=True)
    dvm_classification_text = models.CharField(max_length=100, null=True, blank=True)
    prev_day_trendlyne_durability_score = models.FloatField(null=True, blank=True)
    prev_day_trendlyne_valuation_score = models.FloatField(null=True, blank=True)
    prev_day_trendlyne_momentum_score = models.FloatField(null=True, blank=True)
    prev_week_trendlyne_durability_score = models.FloatField(null=True, blank=True)
    prev_week_trendlyne_valuation_score = models.FloatField(null=True, blank=True)
    prev_week_trendlyne_momentum_score = models.FloatField(null=True, blank=True)
    prev_month_trendlyne_durability_score = models.FloatField(null=True, blank=True)
    prev_month_trendlyne_valuation_score = models.FloatField(null=True, blank=True)
    prev_month_trendlyne_momentum_score = models.FloatField(null=True, blank=True)
    normalized_momentum_score = models.FloatField(null=True, blank=True)

    # Financial Metrics - Quarterly
    operating_revenue_qtr = models.BigIntegerField(null=True, blank=True)
    net_profit_qtr = models.BigIntegerField(null=True, blank=True)
    revenue_qoq_growth_pct = models.FloatField(null=True, blank=True)
    revenue_growth_qtr_yoy_pct = models.FloatField(null=True, blank=True)
    net_profit_qtr_growth_yoy_pct = models.FloatField(null=True, blank=True)
    net_profit_qoq_growth_pct = models.FloatField(null=True, blank=True)
    operating_profit_margin_qtr_pct = models.FloatField(null=True, blank=True)
    operating_profit_margin_qtr_1yr_ago_pct = models.FloatField(null=True, blank=True)

    # Sector comparisons
    sector_revenue_growth_qtr_yoy_pct = models.FloatField(null=True, blank=True)
    sector_net_profit_growth_qtr_yoy_pct = models.FloatField(null=True, blank=True)
    sector_revenue_growth_qtr_qoq_pct = models.FloatField(null=True, blank=True)
    sector_net_profit_growth_qtr_qoq_pct = models.FloatField(null=True, blank=True)

    # Financial Metrics - TTM & Annual
    operating_revenue_ttm = models.BigIntegerField(null=True, blank=True)
    net_profit_ttm = models.BigIntegerField(null=True, blank=True)
    operating_revenue_annual = models.BigIntegerField(null=True, blank=True)
    net_profit_annual = models.BigIntegerField(null=True, blank=True)
    revenue_growth_annual_yoy_pct = models.FloatField(null=True, blank=True)
    net_profit_annual_yoy_growth_pct = models.FloatField(null=True, blank=True)
    sector_revenue_growth_annual_yoy_pct = models.FloatField(null=True, blank=True)

    # Cash Flow
    cash_from_financing_annual_activity = models.BigIntegerField(null=True, blank=True)
    cash_from_investing_activity_annual = models.BigIntegerField(null=True, blank=True)
    cash_from_operating_activity_annual = models.BigIntegerField(null=True, blank=True)
    net_cash_flow_annual = models.BigIntegerField(null=True, blank=True)

    # Latest Results
    latest_financial_result = models.CharField(max_length=100, null=True, blank=True)
    result_announced_date = models.CharField(max_length=100, null=True, blank=True)

    # Valuation Metrics - P/E Ratio
    pe_ttm_price_to_earnings = models.FloatField(null=True, blank=True)
    forecaster_estimates_1y_forward_pe = models.FloatField(null=True, blank=True)
    pe_3yr_average = models.FloatField(null=True, blank=True)
    pe_5yr_average = models.FloatField(null=True, blank=True)
    pctdays_traded_below_current_pe_price_to_earnings = models.FloatField(null=True, blank=True)
    sector_pe_ttm = models.FloatField(null=True, blank=True)
    industry_pe_ttm = models.FloatField(null=True, blank=True)

    # Valuation Metrics - PEG Ratio
    peg_ttm_pe_to_growth = models.FloatField(null=True, blank=True)
    forecaster_estimates_1y_forward_peg = models.FloatField(null=True, blank=True)
    sector_peg_ttm = models.FloatField(null=True, blank=True)
    industry_peg_ttm = models.FloatField(null=True, blank=True)

    # Valuation Metrics - Price to Book
    price_to_book_value = models.FloatField(null=True, blank=True)
    pctdays_traded_below_current_price_to_book_value = models.FloatField(null=True, blank=True)
    sector_price_to_book_ttm = models.FloatField(null=True, blank=True)
    industry_price_to_book_ttm = models.FloatField(null=True, blank=True)

    # EPS Metrics
    basic_eps_ttm = models.FloatField(null=True, blank=True)
    eps_ttm_growth_pct = models.FloatField(null=True, blank=True)

    # Returns & Quality
    roe_annual_pct = models.FloatField(null=True, blank=True)
    sector_return_on_equity_roe = models.FloatField(null=True, blank=True)
    industry_return_on_equity_roe = models.FloatField(null=True, blank=True)
    roa_annual_pct = models.FloatField(null=True, blank=True)
    sector_return_on_assets = models.FloatField(null=True, blank=True)
    industry_return_on_assets = models.FloatField(null=True, blank=True)
    piotroski_score = models.FloatField(null=True, blank=True)

    # Technical Indicators
    day_mfi = models.FloatField(null=True, blank=True)
    day_rsi = models.FloatField(null=True, blank=True)
    day_macd = models.FloatField(null=True, blank=True)
    day_macd_signal_line = models.FloatField(null=True, blank=True)
    day_atr = models.FloatField(null=True, blank=True)
    day_adx = models.FloatField(null=True, blank=True)
    day_roc21 = models.FloatField(null=True, blank=True)
    day_roc125 = models.FloatField(null=True, blank=True)

    # Moving Averages - SMA
    day5_sma = models.FloatField(null=True, blank=True)
    day30_sma = models.FloatField(null=True, blank=True)
    day50_sma = models.FloatField(null=True, blank=True)
    day100_sma = models.FloatField(null=True, blank=True)
    day200_sma = models.FloatField(null=True, blank=True)

    # Moving Averages - EMA
    day12_ema = models.FloatField(null=True, blank=True)
    day20_ema = models.FloatField(null=True, blank=True)
    day50_ema = models.FloatField(null=True, blank=True)
    day100_ema = models.FloatField(null=True, blank=True)

    # Beta
    beta_1month = models.FloatField(null=True, blank=True)
    beta_3month = models.FloatField(null=True, blank=True)
    beta_1year = models.FloatField(null=True, blank=True)
    beta_3year = models.FloatField(null=True, blank=True)

    # Support & Resistance
    pivot_point = models.FloatField(null=True, blank=True)
    first_resistance_r1 = models.FloatField(null=True, blank=True)
    first_resistance_r1_to_price_diff_pct = models.FloatField(null=True, blank=True)
    second_resistance_r2 = models.FloatField(null=True, blank=True)
    second_resistance_r2_to_price_diff_pct = models.FloatField(null=True, blank=True)
    third_resistance_r3 = models.FloatField(null=True, blank=True)
    third_resistance_r3_to_price_diff_pct = models.FloatField(null=True, blank=True)
    first_support_s1 = models.FloatField(null=True, blank=True)
    first_support_s1_to_price_diff_pct = models.FloatField(null=True, blank=True)
    second_support_s2 = models.FloatField(null=True, blank=True)
    second_support_s2_to_price_diff_pct = models.FloatField(null=True, blank=True)
    third_support_s3 = models.FloatField(null=True, blank=True)
    third_support_s3_to_price_diff_pct = models.FloatField(null=True, blank=True)

    # Price Ranges & Changes
    day_low = models.FloatField(null=True, blank=True)
    day_high = models.FloatField(null=True, blank=True)
    day_change_pct = models.FloatField(null=True, blank=True)
    week_low = models.FloatField(null=True, blank=True)
    week_high = models.FloatField(null=True, blank=True)
    week_change_pct = models.FloatField(null=True, blank=True)
    month_low = models.FloatField(null=True, blank=True)
    month_high = models.FloatField(null=True, blank=True)
    month_change_pct = models.FloatField(null=True, blank=True)
    qtr_low = models.FloatField(null=True, blank=True)
    qtr_high = models.FloatField(null=True, blank=True)
    qtr_change_pct = models.FloatField(null=True, blank=True)
    one_year_low = models.FloatField(null=True, blank=True)
    one_year_high = models.FloatField(null=True, blank=True)
    one_year_change_pct = models.FloatField(null=True, blank=True)
    three_year_low = models.FloatField(null=True, blank=True)
    three_year_high = models.FloatField(null=True, blank=True)
    three_year_changep = models.FloatField(null=True, blank=True)
    five_year_low = models.FloatField(null=True, blank=True)
    five_year_high = models.FloatField(null=True, blank=True)
    five_year_changep = models.FloatField(null=True, blank=True)
    ten_year_low = models.FloatField(null=True, blank=True)
    ten_year_high = models.FloatField(null=True, blank=True)
    ten_year_changep = models.FloatField(null=True, blank=True)

    # Volume Data
    day_volume = models.BigIntegerField(null=True, blank=True)
    week_volume_avg = models.BigIntegerField(null=True, blank=True)
    month_volume_avg = models.BigIntegerField(null=True, blank=True)
    three_month_volume_avg = models.BigIntegerField(null=True, blank=True)
    six_month_volume_avg = models.BigIntegerField(null=True, blank=True)
    year_volume_avg = models.BigIntegerField(null=True, blank=True)
    consolidated_eod_volume = models.BigIntegerField(null=True, blank=True)
    consolidated_prev_eod_volume = models.BigIntegerField(null=True, blank=True)
    consolidated_5day_avg_eod_volume = models.BigIntegerField(null=True, blank=True)
    consolidated_30day_avg_eod_volume = models.BigIntegerField(null=True, blank=True)
    consolidated_6m_avg_eod_volume = models.BigIntegerField(null=True, blank=True)
    day_volume_multiple_of_week = models.FloatField(null=True, blank=True)
    vol_day_times_vol_week_str = models.CharField(max_length=100, null=True, blank=True)
    consolidated_day_volume = models.BigIntegerField(null=True, blank=True)
    vwap_day = models.FloatField(null=True, blank=True)

    # Delivery Data
    delivery_volume_pct_eod = models.FloatField(null=True, blank=True)
    delivery_volume_pct_prev_eod = models.FloatField(null=True, blank=True)
    delivery_volume_avg_week = models.FloatField(null=True, blank=True)
    delivery_volume_avg_month = models.FloatField(null=True, blank=True)
    delivery_volume_avg_6month = models.FloatField(null=True, blank=True)
    delivery_volume_eod = models.BigIntegerField(null=True, blank=True)
    delivery_volume_avg_week_qty = models.BigIntegerField(null=True, blank=True)

    # Holding Patterns - Promoter
    promoter_holding_latest_pct = models.FloatField(null=True, blank=True)
    promoter_holding_change_qoq_pct = models.FloatField(null=True, blank=True)
    promoter_holding_change_4qtr_pct = models.FloatField(null=True, blank=True)
    promoter_holding_change_8qtr_pct = models.FloatField(null=True, blank=True)
    promoter_pledge_pct_qtr = models.FloatField(null=True, blank=True)
    promoter_pledge_change_qoq_pct = models.FloatField(null=True, blank=True)

    # Holding Patterns - Mutual Funds
    mf_holding_current_qtr_pct = models.FloatField(null=True, blank=True)
    mf_holding_change_qoq_pct = models.FloatField(null=True, blank=True)
    mf_holding_change_1month_pct = models.FloatField(null=True, blank=True)
    mf_holding_change_2month_pct = models.FloatField(null=True, blank=True)
    mf_holding_change_3month_pct = models.FloatField(null=True, blank=True)
    mf_holding_change_4qtr_pct = models.FloatField(null=True, blank=True)
    mf_holding_change_8qtr_pct = models.FloatField(null=True, blank=True)

    # Holding Patterns - FII
    fii_holding_current_qtr_pct = models.FloatField(null=True, blank=True)
    fii_holding_change_qoq_pct = models.FloatField(null=True, blank=True)
    fii_holding_change_4qtr_pct = models.FloatField(null=True, blank=True)
    fii_holding_change_8qtr_pct = models.FloatField(null=True, blank=True)

    # Holding Patterns - Institutional
    institutional_holding_current_qtr_pct = models.FloatField(null=True, blank=True)
    institutional_holding_change_qoq_pct = models.FloatField(null=True, blank=True)
    institutional_holding_change_4qtr_pct = models.FloatField(null=True, blank=True)
    institutional_holding_change_8qtr_pct = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'tl_stock_data'
        ordering = ['stock_name']
        indexes = [
            models.Index(fields=['nsecode']),
            models.Index(fields=['sector_name']),
            models.Index(fields=['industry_name']),
        ]

    def __str__(self):
        return f"{self.stock_name} ({self.nsecode})"


class NewsArticle(TimeStampedModel):
    """
    News articles and market updates for analysis

    Stores news from various sources with metadata and embeddings
    for semantic search and LLM analysis
    """

    # Article metadata
    title = models.CharField(max_length=500)
    source = models.CharField(max_length=100, help_text="News source (MoneyControl, ET, etc.)")
    author = models.CharField(max_length=200, blank=True)
    published_at = models.DateTimeField(db_index=True)
    url = models.URLField(max_length=1000, unique=True)

    # Content
    summary = models.TextField(help_text="Article summary/excerpt")
    content = models.TextField(help_text="Full article content")

    # Categorization
    category = models.CharField(max_length=50, blank=True, help_text="Market, Economy, Corporate, etc.")
    tags = models.JSONField(default=list, help_text="Article tags/keywords")
    symbols_mentioned = models.JSONField(default=list, help_text="Stock symbols mentioned")
    sectors_mentioned = models.JSONField(default=list, help_text="Sectors mentioned")

    # Sentiment Analysis
    sentiment_score = models.FloatField(null=True, blank=True, help_text="Sentiment score (-1 to 1)")
    sentiment_label = models.CharField(
        max_length=20,
        choices=[('POSITIVE', 'Positive'), ('NEUTRAL', 'Neutral'), ('NEGATIVE', 'Negative')],
        null=True,
        blank=True
    )
    sentiment_confidence = models.FloatField(null=True, blank=True, help_text="Confidence (0-1)")

    # LLM Processing
    llm_summary = models.TextField(blank=True, help_text="LLM-generated summary")
    key_insights = models.JSONField(default=list, help_text="Key insights extracted")
    market_impact = models.CharField(
        max_length=20,
        choices=[('HIGH', 'High'), ('MEDIUM', 'Medium'), ('LOW', 'Low')],
        null=True,
        blank=True
    )

    # Vector embedding for semantic search
    embedding_stored = models.BooleanField(default=False, help_text="Embedding stored in ChromaDB")
    embedding_id = models.CharField(max_length=100, blank=True, help_text="ChromaDB document ID")

    # Processing status
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'news_articles'
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['-published_at']),
            models.Index(fields=['source', '-published_at']),
            models.Index(fields=['category', '-published_at']),
        ]

    def __str__(self):
        return f"{self.title[:50]}... ({self.source})"


class InvestorCall(TimeStampedModel):
    """
    Investor conference calls and earnings transcripts

    Stores transcripts with LLM analysis for decision making
    """

    # Call metadata
    company = models.CharField(max_length=100)
    symbol = models.CharField(max_length=50, db_index=True)
    call_type = models.CharField(
        max_length=50,
        choices=[
            ('EARNINGS', 'Earnings Call'),
            ('ANALYST', 'Analyst Meet'),
            ('INVESTOR', 'Investor Day'),
            ('CONFERENCE', 'Conference Call'),
        ]
    )
    call_date = models.DateField(db_index=True)
    quarter = models.CharField(max_length=10, blank=True, help_text="Q1 FY24, etc.")

    # Content
    transcript = models.TextField(help_text="Full call transcript")
    participants = models.JSONField(default=list, help_text="List of participants")

    # LLM Analysis
    executive_summary = models.TextField(blank=True, help_text="LLM-generated summary")
    key_highlights = models.JSONField(default=list, help_text="Key points")
    financial_metrics = models.JSONField(default=dict, help_text="Extracted financial data")
    management_tone = models.CharField(
        max_length=20,
        choices=[('POSITIVE', 'Positive'), ('NEUTRAL', 'Neutral'), ('NEGATIVE', 'Negative')],
        null=True,
        blank=True
    )
    outlook = models.TextField(blank=True, help_text="Future outlook/guidance")
    concerns_raised = models.JSONField(default=list, help_text="Concerns/risks mentioned")

    # Trading impact
    trading_signal = models.CharField(
        max_length=20,
        choices=[('BULLISH', 'Bullish'), ('NEUTRAL', 'Neutral'), ('BEARISH', 'Bearish')],
        null=True,
        blank=True
    )
    confidence_score = models.FloatField(null=True, blank=True, help_text="Signal confidence (0-1)")

    # Vector embedding
    embedding_stored = models.BooleanField(default=False)
    embedding_id = models.CharField(max_length=100, blank=True)

    # Processing
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'investor_calls'
        ordering = ['-call_date']
        indexes = [
            models.Index(fields=['symbol', '-call_date']),
            models.Index(fields=['call_type', '-call_date']),
        ]

    def __str__(self):
        return f"{self.company} - {self.call_type} ({self.call_date})"


class KnowledgeBase(TimeStampedModel):
    """
    Processed knowledge chunks for RAG system

    Stores processed information chunks with embeddings for
    efficient semantic search and retrieval
    """

    # Source information
    source_type = models.CharField(
        max_length=50,
        choices=[
            ('NEWS', 'News Article'),
            ('CALL', 'Investor Call'),
            ('REPORT', 'Research Report'),
            ('MANUAL', 'Manual Entry'),
        ]
    )
    source_id = models.IntegerField(help_text="ID of source record")
    source_url = models.URLField(max_length=1000, blank=True)

    # Content
    title = models.CharField(max_length=500)
    content_chunk = models.TextField(help_text="Processed text chunk")
    chunk_index = models.IntegerField(default=0, help_text="Chunk position in document")

    # Metadata
    metadata = models.JSONField(default=dict, help_text="Additional context")
    symbols = models.JSONField(default=list, help_text="Related symbols")
    sectors = models.JSONField(default=list, help_text="Related sectors")
    topics = models.JSONField(default=list, help_text="Topics covered")

    # Vector embedding
    embedding_id = models.CharField(max_length=100, unique=True, help_text="ChromaDB ID")
    embedding_stored = models.BooleanField(default=True)

    # Relevance tracking
    times_retrieved = models.IntegerField(default=0)
    last_retrieved_at = models.DateTimeField(null=True, blank=True)
    relevance_score = models.FloatField(default=0.0, help_text="Average relevance in retrievals")

    class Meta:
        db_table = 'knowledge_base'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['embedding_id']),
        ]

    def __str__(self):
        return f"{self.title[:50]}... ({self.source_type})"


class DeepDiveAnalysis(TimeStampedModel):
    """
    Store Level 2 Deep-Dive Analysis Reports

    Stores comprehensive analysis reports generated for futures trading decisions.
    Includes tracking of user decisions and trade outcomes for performance analysis.
    """

    # Basic Info
    symbol = models.CharField(max_length=50, db_index=True)
    expiry = models.DateField()
    level1_score = models.IntegerField(help_text="Level 1 composite score")
    level1_direction = models.CharField(max_length=20, default='NEUTRAL')

    # Report data (JSON)
    report = models.JSONField(help_text="Complete deep-dive analysis report")

    # User and decision tracking
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deep_dive_analyses')
    decision = models.CharField(
        max_length=20,
        choices=[
            ('EXECUTED', 'Executed Trade'),
            ('MODIFIED', 'Modified Parameters'),
            ('REJECTED', 'Rejected'),
            ('PENDING', 'Pending Decision')
        ],
        default='PENDING'
    )
    decision_notes = models.TextField(blank=True, help_text="User notes on decision")
    decision_timestamp = models.DateTimeField(null=True, blank=True)

    # Trade tracking (if executed)
    trade_executed = models.BooleanField(default=False)
    entry_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    exit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    lot_size = models.IntegerField(null=True, blank=True)
    pnl = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="P&L in rupees")
    pnl_pct = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="P&L percentage")

    # Performance metadata
    conviction_score = models.IntegerField(null=True, blank=True, help_text="Conviction score from report")
    risk_grade = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = 'deep_dive_analysis'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['symbol', 'expiry']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['decision']),
            models.Index(fields=['trade_executed']),
        ]

    def __str__(self):
        return f"{self.symbol} {self.expiry} - {self.decision} (Score: {self.level1_score})"

    def calculate_pnl(self):
        """Calculate P&L if entry and exit prices are set"""
        if self.entry_price and self.exit_price and self.lot_size:
            pnl_per_unit = self.exit_price - self.entry_price
            self.pnl = pnl_per_unit * self.lot_size
            self.pnl_pct = (pnl_per_unit / self.entry_price) * 100
            self.save()

    def mark_executed(self, entry_price, lot_size):
        """Mark trade as executed"""
        self.trade_executed = True
        self.decision = 'EXECUTED'
        self.entry_price = entry_price
        self.lot_size = lot_size
        self.save()

    def close_trade(self, exit_price):
        """Close trade and calculate P&L"""
        self.exit_price = exit_price
        self.calculate_pnl()
        self.save()
