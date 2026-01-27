# Data App Documentation

**Location**: `apps/data/`

The data app handles market data collection, storage, and analysis. It's the data foundation for all trading decisions.

---

## What This App Does

1. **Trendlyne Integration** - Fetches comprehensive stock data
2. **Data Analysis** - 6 analyzer classes for market signals
3. **Signal Generation** - Trading signals from multiple indicators
4. **Trade Validation** - Validates trades before execution
5. **News Processing** - Fetches and stores market news

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | 10 data models (729 lines) |
| `services/trendlyne_fetcher.py` | Trendlyne data fetcher (797 lines) |
| `data_analyzers.py` | 6 analyzer classes (622 lines) |
| `validators.py` | Trade validation (397 lines) |
| `signals.py` | Signal generation |
| `providers/trendlyne.py` | Web scraping implementation |
| `services/gnews_client.py` | News API client |
| `importers.py` | CSV data import |
| `broker_integration.py` | Breeze API integration |

---

## Key Models

### TLStockData

Comprehensive stock data from Trendlyne (80+ fields).

```python
# Basic Info
stock_name = CharField()
nsecode = CharField()              # NSE symbol (unique)
current_price = DecimalField()
market_cap = DecimalField()
industry_name = CharField()
sector_name = CharField()

# Trendlyne Scores
trendlyne_durability_score = DecimalField()    # Financial health
trendlyne_valuation_score = DecimalField()     # Value assessment
trendlyne_momentum_score = DecimalField()      # Price momentum
dvm_classification_text = CharField()          # Overall rating

# Technical Indicators
rsi = DecimalField()               # Relative Strength Index
macd = DecimalField()              # Moving Average Convergence
atr = DecimalField()               # Average True Range
adx = DecimalField()               # Average Directional Index

# Moving Averages
sma_5 = DecimalField()
sma_20 = DecimalField()
sma_50 = DecimalField()
sma_200 = DecimalField()
ema_12 = DecimalField()
ema_20 = DecimalField()

# Support/Resistance
pivot_point = DecimalField()
support_1 = DecimalField()
support_2 = DecimalField()
resistance_1 = DecimalField()
resistance_2 = DecimalField()

# Holdings
promoter_holding_pct = DecimalField()
fii_holding_pct = DecimalField()
mf_holding_pct = DecimalField()

# Volume
avg_day_volume = BigIntegerField()
avg_week_volume = BigIntegerField()
delivery_pct = DecimalField()
```

### ContractData

F&O contract data (futures and options).

```python
# Identifiers
symbol = CharField()               # NIFTY, RELIANCE, etc.
option_type = CharField()          # CE, PE, or FUT
strike_price = DecimalField()
expiry = DateField()

# Price
price = DecimalField()
spot = DecimalField()
day_change = DecimalField()
pct_day_change = DecimalField()

# Open Interest
oi = BigIntegerField()
oi_change = BigIntegerField()
pct_oi_change = DecimalField()

# Volume
traded_contracts = BigIntegerField()
shares_traded = BigIntegerField()

# Greeks (Options)
iv = DecimalField()                # Implied Volatility
delta = DecimalField()
gamma = DecimalField()
theta = DecimalField()
vega = DecimalField()

# Futures
basis = DecimalField()             # Futures - Spot
cost_of_carry = DecimalField()
lot_size = IntegerField()
```

### NewsArticle

News with sentiment analysis.

```python
title = CharField()
source = CharField()
url = URLField()
published_at = DateTimeField()
summary = TextField()
content = TextField()

# Sentiment
sentiment_score = DecimalField()   # -1 to +1
sentiment_label = CharField()      # POSITIVE, NEUTRAL, NEGATIVE
sentiment_confidence = DecimalField()

# LLM Processing
llm_summary = TextField()
key_insights = JSONField()
market_impact = CharField()        # HIGH, MEDIUM, LOW

# Embeddings (for RAG)
embedding_stored = BooleanField()
embedding_id = CharField()         # ChromaDB ID
```

---

## Data Fetching

### Trendlyne Fetcher

```python
from apps.data.services.trendlyne_fetcher import TrendlyneDataFetcher

fetcher = TrendlyneDataFetcher()

# Fetch all data
result = fetcher.fetch_fno_data()

# Workflow:
# 1. Initialize browser (Selenium)
# 2. Login to Trendlyne
# 3. Download F&O contracts data
# 4. Download Market Snapshot (stock data)
# 5. Parse and save to database
# 6. Cleanup old files (> 7 days)
```

### Real-time Logging

The fetcher supports SSE (Server-Sent Events) for real-time progress:

```python
from apps.data.services.trendlyne_fetcher import TrendlyneLogCallback

callback = TrendlyneLogCallback()
fetcher = TrendlyneDataFetcher(log_callback=callback)

# In your view, stream logs:
for log in callback.get_logs():
    yield f"data: {log}\n\n"
```

---

## Analyzers

Six analyzer classes for different aspects of market analysis.

### TrendlyneScoreAnalyzer

Analyzes Trendlyne proprietary scores.

```python
from apps.data.data_analyzers import TrendlyneScoreAnalyzer

analyzer = TrendlyneScoreAnalyzer()

# Get scores
scores = analyzer.get_stock_scores('RELIANCE')
# Returns:
# {
#     'durability': 75,
#     'valuation': 60,
#     'momentum': 80,
#     'average': 71.67,
#     'rating': 'STRONG_BUY'
# }

# Validate entry criteria
is_valid, reason = analyzer.validate_entry(
    symbol='RELIANCE',
    min_durability=50,
    min_valuation=40,
    min_momentum=50
)
```

### OpenInterestAnalyzer

Analyzes OI patterns.

```python
from apps.data.data_analyzers import OpenInterestAnalyzer

analyzer = OpenInterestAnalyzer()

# Get put-call ratio
pcr = analyzer.get_pcr_ratio('NIFTY')
# Returns:
# {
#     'pcr_oi': 1.25,          # Bullish (> 1.0)
#     'pcr_vol': 0.95,
#     'interpretation': 'BULLISH'
# }

# Analyze OI buildup
buildup = analyzer.analyze_oi_buildup('RELIANCE', '2026-01-30')
# Returns:
# {
#     'buildup_type': 'LONG_BUILDUP',  # Price up + OI up
#     'sentiment': 'BULLISH',
#     'price_change_pct': 2.5,
#     'oi_change_pct': 15.3
# }
```

**Buildup Types**:
| Price | OI | Interpretation |
|-------|-----|----------------|
| Up | Up | LONG_BUILDUP (Bullish) |
| Down | Up | SHORT_BUILDUP (Bearish) |
| Up | Down | SHORT_COVERING (Bullish) |
| Down | Down | LONG_UNWINDING (Bearish) |

### VolumeAnalyzer

Analyzes volume patterns.

```python
from apps.data.data_analyzers import VolumeAnalyzer

analyzer = VolumeAnalyzer()
result = analyzer.analyze_volume('RELIANCE')
# Returns volume surge detection, confirmation signals
```

### DMAAnalyzer

Daily Moving Averages analysis.

```python
from apps.data.data_analyzers import DMAAnalyzer

analyzer = DMAAnalyzer()
result = analyzer.analyze_dma('RELIANCE')
# Returns:
# {
#     'trend': 'BULLISH',
#     'price_above_20': True,
#     'price_above_50': True,
#     'price_above_200': True,
#     'golden_cross': True,      # 20 > 50
# }
```

### TechnicalIndicatorAnalyzer

Technical indicators analysis.

```python
from apps.data.data_analyzers import TechnicalIndicatorAnalyzer

analyzer = TechnicalIndicatorAnalyzer()
result = analyzer.analyze_indicators('RELIANCE')
# Returns RSI, MACD, ATR, ADX analysis
```

### HoldingPatternAnalyzer

Institutional holding patterns.

```python
from apps.data.data_analyzers import HoldingPatternAnalyzer

analyzer = HoldingPatternAnalyzer()
result = analyzer.analyze_holdings('RELIANCE')
# Returns promoter, FII, MF holding trends
```

---

## Signal Generation

```python
from apps.data.signals import SignalGenerator, SignalStrength

generator = SignalGenerator()

signal = generator.generate_futures_signal('RELIANCE', '2026-01-30')

# Returns TradingSignal:
# {
#     'symbol': 'RELIANCE',
#     'signal': SignalStrength.STRONG_BUY,
#     'confidence': 85,
#     'reasons': ['Strong OI buildup', 'Above all DMAs', ...],
#     'recommended_action': 'LONG',
# }
```

**Signal Components (Weighted)**:
| Component | Weight |
|-----------|--------|
| Trendlyne Scores | 30% |
| OI Buildup | 25% |
| Volume | 20% |
| DMA Trend | 15% |
| Technical Indicators | 10% |

---

## Trade Validation

```python
from apps.data.validators import TradeValidator

validator = TradeValidator()

result = validator.validate_futures_long(
    symbol='RELIANCE',
    expiry='2026-01-30',
    min_durability=50,
    min_momentum=50
)

# Returns ValidationResult:
# {
#     'approved': True,
#     'confidence': 82,
#     'reasons': ['Good OI buildup', 'Above DMAs', ...],
#     'warnings': ['RSI near overbought'],
# }
```

---

## Data Freshness

The system checks data freshness (30-minute threshold):

```python
from apps.data.utils.data_freshness import (
    check_tlstock_data_freshness,
    ensure_fresh_data,
)

# Check if data is fresh
is_fresh = check_tlstock_data_freshness()

# Auto-update if stale
ensure_fresh_data()  # Triggers Trendlyne fetch if > 30 min old
```

---

## Celery Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `fetch_trendlyne_data` | 8:30 AM | Daily data fetch |
| `import_trendlyne_data` | 9:00 AM | CSV import |
| `generate_signals` | Every 30 min | Signal generation |
| `update_broker_data` | Every 5 min | Real-time updates |

---

## Management Commands

```bash
# Full data fetch
python manage.py trendlyne_data_manager

# Import from CSV
python manage.py import_trendlyne_data

# Validate a trade
python manage.py validate_trade RELIANCE --direction=LONG

# Generate signals
python manage.py generate_signals
```

---

## How to Study This App

1. **Start with `models.py`** - Understand data structures
2. **Read `data_analyzers.py`** - Learn the 6 analyzers
3. **Study `validators.py`** - Validation logic
4. **Check `signals.py`** - Signal generation
5. **Review `trendlyne_fetcher.py`** - Data collection

---

## Data Flow

```
Trendlyne Website
      ↓
TrendlyneProvider (Selenium scraping)
      ↓
TrendlyneDataFetcher (Orchestration)
      ↓
Parse Excel/CSV files
      ↓
Save to Database
├── TLStockData (80+ fields per stock)
├── ContractData (F&O contracts)
└── ContractStockData (F&O summary)
      ↓
Analyzers query data
├── TrendlyneScoreAnalyzer
├── OpenInterestAnalyzer
├── VolumeAnalyzer
├── DMAAnalyzer
├── TechnicalIndicatorAnalyzer
└── HoldingPatternAnalyzer
      ↓
SignalGenerator combines analysis
      ↓
TradeValidator validates entry
      ↓
Trading decision
```

---

## Key Notes

1. **Data Volume**: TLStockData has 80+ fields per stock
2. **Freshness**: Data older than 30 minutes triggers refresh
3. **Trendlyne Login**: Requires valid credentials in CredentialStore
4. **Browser**: Uses Selenium with ChromeDriver for scraping
5. **Caching**: VIX cached for 5 minutes, news for 1 hour

---

*For questions, check the code comments or ask the team.*
