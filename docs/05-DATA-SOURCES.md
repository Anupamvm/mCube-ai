# Data Sources & LLM Integration

This document covers market data sources, Trendlyne integration, and LLM-based analysis.

---

## Overview

mCube uses multiple data sources for trading decisions:

| Source | Data Type | Update Frequency |
|--------|-----------|------------------|
| **Trendlyne** | Fundamentals, FNO, Analyst consensus | Daily |
| **Brokers** | Live quotes, positions, orders | Real-time |
| **LLM (Ollama)** | Trade validation, sentiment analysis | On-demand |
| **News APIs** | Market news, events | Continuous |

---

## Trendlyne Integration

### What Data is Collected

#### 1. F&O Data
- All active futures and options contracts
- Strike prices, expiry dates, lot sizes
- Open interest, volume, Greeks (IV, delta, gamma, theta, vega)

#### 2. Market Snapshot
- Broad market overview
- Index levels, top gainers/losers

#### 3. Analyst Consensus (21 categories)
- High Bullishness / Bearishness ratings
- Analyst upgrades/downgrades
- Beat/Missed estimates (EPS, Revenue, Net Income)
- Forward growth projections

#### 4. Stock Data (80+ fields per stock)
- **Basic**: Name, NSE code, price, market cap
- **Trendlyne Scores**: Durability, Valuation, Momentum
- **Financials**: Revenue, profit, margins
- **Valuation**: PE, PEG, P/B ratios
- **Technicals**: RSI, MACD, MFI, ATR, ADX, SMAs, EMAs
- **Support/Resistance**: Pivot points, R1/R2/R3, S1/S2/S3
- **Holdings**: Promoter, MF, FII percentages

### Setup

```bash
# Setup Trendlyne credentials
python manage.py setup_credentials --setup-trendlyne

# Enter your Trendlyne email and password when prompted
```

### Fetching Data

**API Endpoints:**

```bash
# Test login
curl http://localhost:8000/api/data/trendlyne/login/

# Fetch all data
curl -X POST http://localhost:8000/api/data/trendlyne/fetch/

# Check status
curl http://localhost:8000/api/data/trendlyne/status/
```

**Programmatic:**

```python
from apps.data.trendlyne import get_all_trendlyne_data

# Fetch all Trendlyne data
success = get_all_trendlyne_data()
```

### Querying Data

```python
from apps.data.models import TLStockData, ContractData

# Find high momentum stocks
high_momentum = TLStockData.objects.filter(
    trendlyne_momentum_score__gte=70
).order_by('-trendlyne_momentum_score')

for stock in high_momentum[:10]:
    print(f"{stock.stock_name}: Momentum={stock.trendlyne_momentum_score}")

# Find quality growth stocks
quality_growth = TLStockData.objects.filter(
    trendlyne_durability_score__gte=70,
    trendlyne_momentum_score__gte=60,
    peg_ttm_pe_to_growth__lt=1.5,
    roe_annual_pct__gte=15
)

# Query F&O data
nifty_options = ContractData.objects.filter(
    symbol='NIFTY',
    option_type__in=['CE', 'PE']
).order_by('strike_price')
```

### Data Directory Structure

```
apps/data/
├── tldata/                          # Main downloads
│   ├── contracts_YYYY_MM_DD.xlsx    # F&O contracts data
│   └── progress.json                # Download progress tracking
│
├── providers/                       # Data provider implementations
│   └── trendlyne.py                # Trendlyne scraper
│
├── tools/                           # Data utilities
│   └── security_master.py          # Instrument token lookup
│
├── analyzers/                       # Data analysis
│   └── oi_analyzer.py              # Open interest analysis
│
└── models.py                        # Data models (TLStockData, ContractData, etc.)
```

---

## LLM Integration (Ollama)

### Overview

The LLM system provides:
- **News Processing**: Sentiment analysis and summarization
- **Trade Validation**: AI-powered trade approval
- **RAG Queries**: Context-aware Q&A about stocks
- **Knowledge Base**: Semantic search across news

### Setup

```bash
# 1. Install Ollama
brew install ollama  # macOS

# 2. Start Ollama server
ollama serve

# 3. Download a model (recommended: DeepSeek 6.7B)
python manage.py manage_models --quick-setup

# 4. Configure environment
echo "OLLAMA_HOST=http://localhost:11434" >> .env
echo "OLLAMA_MODEL=deepseek-coder-6.7b" >> .env

# 5. Test
python manage.py test_llm
```

### Recommended Models

| Model | Size | RAM | Use Case |
|-------|------|-----|----------|
| **DeepSeek 6.7B** | 3.8GB | 8GB | General use (recommended) |
| Mistral 7B | 4.1GB | 8GB | Fast responses |
| DeepSeek 33B | 19GB | 24GB | Complex analysis |

### Trade Validation

```python
from apps.llm.services.trade_validator import validate_trade

result = validate_trade(
    symbol="RELIANCE",
    direction="LONG",
    strategy_type="OPTIONS"
)

if result['approved'] and result['confidence'] >= 0.7:
    print(f"Trade approved with {result['confidence']:.0%} confidence")
    print(f"Reasoning: {result['reasoning']}")
else:
    print(f"Trade rejected: {result['reasoning']}")
```

### News Processing

```python
from apps.llm.services.news_processor import process_news_article

success, article = process_news_article(
    title="Reliance Q3 Results Beat Estimates",
    content="Full article content...",
    source="Economic Times",
    symbols=["RELIANCE"]
)

print(f"Sentiment: {article.sentiment_label}")
print(f"Summary: {article.llm_summary}")
print(f"Key Insights: {article.llm_insights}")
```

### RAG Queries

```python
from apps.llm.services.rag_system import ask_question, get_symbol_analysis

# Ask any question
success, answer, sources = ask_question(
    "What is the sentiment on RELIANCE?",
    n_results=5
)
print(answer)

# Get symbol analysis
success, analysis = get_symbol_analysis("RELIANCE")
print(analysis)
```

### Management Commands

```bash
# Model management
python manage.py manage_models --list-recommended
python manage.py manage_models --quick-setup
python manage.py manage_models --list-local

# Testing
python manage.py test_llm
python manage.py test_llm --quick
python manage.py test_llm --component rag

# News processing
python manage.py fetch_news --demo --limit 10
python manage.py fetch_news --demo --symbols RELIANCE,TCS
```

---

## Security Master

The Security Master provides instrument token lookup for broker APIs.

### Usage

```python
from apps.data.tools.security_master import get_security_master

sm = get_security_master()

# Get token for Nifty futures
token = sm.get_token(
    symbol='NIFTY',
    exchange='NFO',
    instrument_type='FUTIDX',
    expiry='28-NOV-2025'
)

# Get token for option
token = sm.get_token(
    symbol='NIFTY',
    exchange='NFO',
    instrument_type='OPTIDX',
    expiry='28-NOV-2025',
    strike=24000,
    option_type='CE'
)
```

---

## Data Models

### TLStockData

```python
class TLStockData(models.Model):
    # Basic Info
    stock_name = models.CharField()
    nsecode = models.CharField()
    current_price = models.DecimalField()
    market_cap = models.DecimalField()

    # Trendlyne Scores (0-100)
    trendlyne_durability_score = models.IntegerField()
    trendlyne_valuation_score = models.IntegerField()
    trendlyne_momentum_score = models.IntegerField()

    # Technical Indicators
    rsi_14 = models.DecimalField()
    macd = models.DecimalField()
    beta = models.DecimalField()

    # Support/Resistance
    pivot_point = models.DecimalField()
    resistance_1 = models.DecimalField()
    support_1 = models.DecimalField()

    # Holdings
    promoter_holding_latest_pct = models.DecimalField()
    fii_holding_pct = models.DecimalField()
    mf_holding_pct = models.DecimalField()
```

### ContractData

```python
class ContractData(models.Model):
    symbol = models.CharField()
    option_type = models.CharField()  # CE, PE, FUT
    strike_price = models.DecimalField()
    expiry = models.DateField()

    # Pricing
    ltp = models.DecimalField()
    day_change = models.DecimalField()

    # OI & Volume
    oi = models.IntegerField()
    oi_change = models.IntegerField()
    traded_contracts = models.IntegerField()

    # Greeks
    iv = models.DecimalField()
    delta = models.DecimalField()
    gamma = models.DecimalField()
    theta = models.DecimalField()
    vega = models.DecimalField()
```

### NewsArticle

```python
class NewsArticle(models.Model):
    title = models.CharField()
    content = models.TextField()
    source = models.CharField()
    published_at = models.DateTimeField()
    symbols = models.JSONField()  # List of stock symbols

    # LLM Analysis
    sentiment_score = models.DecimalField()  # -1 to 1
    sentiment_label = models.CharField()     # bullish, bearish, neutral
    llm_summary = models.TextField()
    llm_insights = models.JSONField()
    is_embedded = models.BooleanField()      # In vector store
```

---

## Automation

### Celery Tasks

```python
# Daily Trendlyne scrape (8:30 AM)
@shared_task
def fetch_trendlyne_data_daily():
    from apps.data.trendlyne import get_all_trendlyne_data
    return get_all_trendlyne_data()

# News processing (every 30 minutes)
@shared_task
def process_news_batch():
    from apps.llm.services.news_processor import process_pending_news
    return process_pending_news()
```

### Celery Beat Schedule

```python
CELERY_BEAT_SCHEDULE = {
    'fetch-trendlyne-daily': {
        'task': 'apps.data.tasks.fetch_trendlyne_data_daily',
        'schedule': crontab(hour=8, minute=30),
    },
    'process-news': {
        'task': 'apps.llm.tasks.process_news_batch',
        'schedule': crontab(minute='*/30'),
    },
}
```

---

## Troubleshooting

### Trendlyne Issues

| Issue | Solution |
|-------|----------|
| Login failed | Verify credentials: `python manage.py setup_credentials --list` |
| No CSV files | Check subscription is active, verify download directory |
| ChromeDriver error | `pip install chromedriver-autoinstaller --upgrade` |

### LLM Issues

| Issue | Solution |
|-------|----------|
| "LLM not available" | Check Ollama is running: `ollama serve` |
| Slow responses | Use smaller model, reduce context |
| Out of memory | Use Q4_K_M quantization, close other apps |

### Data Freshness

Check data freshness at http://localhost:8000/system/test/ which shows:
- Last Trendlyne update time
- FNO data age
- Market snapshot age

---

## Best Practices

### 1. Daily Data Refresh

Run Trendlyne scrape before market opens (8:30 AM):

```bash
python manage.py fetch_trendlyne
```

### 2. Use Trendlyne Scores for Filtering

```python
# Filter stocks using Trendlyne scores
candidates = TLStockData.objects.filter(
    trendlyne_durability_score__gte=60,
    trendlyne_momentum_score__gte=50,
    trendlyne_valuation_score__gte=40
)
```

### 3. Combine LLM with Quantitative

```python
# First filter quantitatively
candidates = get_high_score_stocks()

# Then validate with LLM
for stock in candidates:
    result = validate_trade(stock.nsecode, direction, strategy)
    if result['approved']:
        approved_trades.append(stock)
```

### 4. Cache Frequently Accessed Data

```python
from django.core.cache import cache

def get_nifty_support_resistance():
    key = 'nifty_sr_levels'
    levels = cache.get(key)
    if not levels:
        data = TLStockData.objects.get(nsecode='NIFTY')
        levels = {
            'pivot': data.pivot_point,
            'r1': data.resistance_1,
            's1': data.support_1
        }
        cache.set(key, levels, 300)  # 5 min cache
    return levels
```

---

*For trading strategy details, see [03-TRADING-STRATEGIES.md](03-TRADING-STRATEGIES.md).*
