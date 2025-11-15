# Trendlyne Integration Guide

## Overview

The Trendlyne integration provides automated web scraping capabilities to collect comprehensive stock market data including:

- **Analyst Consensus Data**: Bullishness/Bearishness ratings, analyst upgrades
- **Earnings Surprises**: Beat/Missed estimates for EPS, Revenue, Net Income
- **Forward Growth Projections**: EPS, Revenue, and Capex growth forecasts
- **F&O Data**: Futures & Options contracts with Greeks and open interest
- **Market Snapshots**: Daily market overview data
- **Technical & Fundamental Metrics**: 80+ fields per stock including Trendlyne scores, valuation ratios, technical indicators, and institutional holdings

## Data Models

### 1. CredentialStore (apps/core/models.py)
Securely stores Trendlyne login credentials.

**Fields**:
- `service`: Service type (e.g., 'trendlyne')
- `name`: Credential set name (default: "default")
- `username`: Trendlyne email/username
- `password`: Trendlyne password

### 2. TLStockData (apps/data/models.py)
Main model with 80+ comprehensive stock data fields.

**Key field categories**:
- **Basic Info**: stock_name, nsecode, current_price, market_cap
- **Trendlyne Scores**: durability_score, valuation_score, momentum_score (daily/weekly/monthly)
- **Financials**: revenue, profit, margins (quarterly, TTM, annual)
- **Valuation**: PE, PEG, P/B ratios with sector/industry comparisons
- **Technical Indicators**: RSI, MACD, MFI, ATR, ADX, SMAs, EMAs, Beta
- **Support/Resistance**: Pivot points, R1/R2/R3, S1/S2/S3
- **Volume & Delivery**: Daily/weekly/monthly averages, delivery percentages
- **Holdings**: Promoter, MF, FII, and institutional holding patterns

### 3. ContractData (apps/data/models.py)
F&O contract-level data with pricing, volume, OI, and Greeks.

**Key fields**:
- Symbol, option_type, strike_price, expiry
- Price metrics: LTP, open, high, low, day_change
- OI metrics: oi, oi_change, pct_oi_change
- Volume metrics: traded_contracts, shares_traded
- Greeks: IV, delta, gamma, theta, vega, rho

### 4. ContractStockData (apps/data/models.py)
Stock-level F&O aggregated metrics.

**Key fields**:
- PCR ratios: fno_pcr_oi, fno_pcr_vol
- Total OI: calls vs puts
- Rollover metrics
- Volatility: annualized_volatility

## Setup Instructions

### 1. Install Dependencies

```bash
cd /path/to/mCube-ai
pip install -r requirements.txt
```

Required packages:
- Django >= 4.2.7
- selenium >= 4.15.2
- beautifulsoup4 >= 4.12.2
- html5lib >= 1.1
- pandas >= 2.2.0
- chromedriver-autoinstaller >= 0.6.4

### 2. Run Migrations

```bash
python manage.py migrate
```

### 3. Configure Trendlyne Credentials

**Option A: Via Django Admin**

1. Start the development server:
   ```bash
   python manage.py createsuperuser  # If you haven't already
   python manage.py runserver
   ```

2. Navigate to: `http://localhost:8000/admin/core/credentialstore/`

3. Click "Add Credential Store" and fill in:
   - **Service**: trendlyne
   - **Name**: default (or custom name)
   - **Username**: Your Trendlyne email
   - **Password**: Your Trendlyne password

**Option B: Via Django Shell**

```python
python manage.py shell

from apps.core.models import CredentialStore

CredentialStore.objects.create(
    service='trendlyne',
    name='default',
    username='your_email@example.com',
    password='your_password'
)
```

### 4. Set Environment Variable (Optional)

Add to your `.env` file:
```
TRENDLYNE_API_KEY=your_api_key_if_applicable
```

## API Endpoints

### 1. Test Login
```http
GET /api/data/trendlyne/login/
```

**Response**:
```json
{
    "status": "success",
    "message": "Trendlyne login successful"
}
```

### 2. Fetch All Data
```http
POST /api/data/trendlyne/fetch/
```

**What it does**:
- Logs in to Trendlyne
- Downloads F&O data as CSV
- Downloads market snapshot as CSV
- Scrapes 21 analyst consensus pages
- Saves all data to `apps/data/tldata/` and `apps/data/trendlynedata/`

**Response**:
```json
{
    "status": "success",
    "message": "All Trendlyne data fetched and saved to apps/data/tldata/"
}
```

### 3. Check Status
```http
GET /api/data/trendlyne/status/
```

**Response**:
```json
{
    "credentials_configured": true,
    "credential_name": "default",
    "last_updated": "2025-01-15T10:30:00Z",
    "data_directory_exists": true,
    "files_count": 23,
    "latest_files": [
        "fno_data_2025-01-15.csv",
        "market_snapshot_2025-01-15.csv",
        ...
    ]
}
```

## Data Collection Details

### What Gets Scraped

#### 1. F&O Data (`fno_data_YYYY-MM-DD.csv`)
- All active futures and options contracts
- Strike prices, expiry dates, lot sizes
- Open interest, volume, Greeks
- Downloaded from: `https://trendlyne.com/futures-options/contracts-excel-download/`

#### 2. Market Snapshot (`market_snapshot_YYYY-MM-DD.csv`)
- Broad market overview
- Index levels, top gainers/losers
- Downloaded from: `https://trendlyne.com/tools/data-downloader/market-snapshot-excel/`

#### 3. Forecaster Data (21 CSV files)

**Analyst Consensus**:
- `trendlyne_High_Bullishness.csv`
- `trendlyne_High_Bearishness.csv`
- `trendlyne_Highest_3Mth_Analyst_Upgrades.csv`

**Earnings Surprises** (Annual & Quarterly):
- Beat/Missed: EPS, Revenue, Net Income

**Forward Projections**:
- Highest Forward Annual EPS/Revenue/Capex Growth
- Highest Forward 12Mth Upside %
- Highest Dividend Yield

## Usage Examples

### Programmatic Access

```python
from apps.data.trendlyne import get_all_trendlyne_data
from apps.data.models import TLStockData, ContractData

# Fetch fresh data from Trendlyne
success = get_all_trendlyne_data()

if success:
    print("Data fetched successfully!")

    # Query TLStockData
    high_momentum_stocks = TLStockData.objects.filter(
        trendlyne_momentum_score__gte=70
    ).order_by('-trendlyne_momentum_score')

    for stock in high_momentum_stocks[:10]:
        print(f"{stock.stock_name}: Momentum={stock.trendlyne_momentum_score}")

    # Query FnO data
    nifty_options = ContractData.objects.filter(
        symbol='NIFTY',
        option_type__in=['CE', 'PE']
    ).order_by('strike_price')

    for option in nifty_options:
        print(f"{option.symbol} {option.strike_price} {option.option_type}: IV={option.iv}")
```

### Using Scraped CSV Files

```python
import pandas as pd
import os
from django.conf import settings

# Read FnO data
data_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata')
fno_df = pd.read_csv(os.path.join(data_dir, 'fno_data_2025-01-15.csv'))

# Read analyst consensus data
forecaster_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'trendlynedata')
bullish_df = pd.read_csv(os.path.join(forecaster_dir, 'trendlyne_High_Bullishness.csv'))

print("Top 10 Bullish Stocks:")
print(bullish_df.head(10))
```

### Creating a Trading Strategy with Trendlyne Scores

```python
from apps.data.models import TLStockData

# Find quality growth stocks
quality_growth = TLStockData.objects.filter(
    trendlyne_durability_score__gte=70,  # High quality
    trendlyne_momentum_score__gte=60,     # Good momentum
    peg_ttm_pe_to_growth__lt=1.5,         # Reasonable valuation
    roe_annual_pct__gte=15,                # Strong ROE
    promoter_holding_latest_pct__gte=50    # Promoter confidence
).order_by('-trendlyne_durability_score')

for stock in quality_growth:
    print(f"""
    {stock.stock_name} ({stock.nsecode})
    Durability: {stock.trendlyne_durability_score}
    Valuation: {stock.trendlyne_valuation_score}
    Momentum: {stock.trendlyne_momentum_score}
    PE: {stock.pe_ttm_price_to_earnings}
    PEG: {stock.peg_ttm_pe_to_growth}
    ROE: {stock.roe_annual_pct}%
    """)
```

## Automation

### Using Celery Beat (Scheduled Tasks)

```python
# In your celery.py or tasks.py

from celery import shared_task
from apps.data.trendlyne import get_all_trendlyne_data

@shared_task
def fetch_trendlyne_data_daily():
    """Fetch Trendlyne data every morning at 9:00 AM"""
    success = get_all_trendlyne_data()
    return {"success": success}

# In celery beat schedule:
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'fetch-trendlyne-daily': {
        'task': 'apps.data.tasks.fetch_trendlyne_data_daily',
        'schedule': crontab(hour=9, minute=0),  # 9:00 AM daily
    },
}
```

### Using Django Management Command

Create `apps/data/management/commands/fetch_trendlyne.py`:

```python
from django.core.management.base import BaseCommand
from apps.data.trendlyne import get_all_trendlyne_data

class Command(BaseCommand):
    help = 'Fetch all Trendlyne data'

    def handle(self, *args, **options):
        self.stdout.write('Starting Trendlyne data fetch...')
        success = get_all_trendlyne_data()

        if success:
            self.stdout.write(self.style.SUCCESS('Successfully fetched Trendlyne data'))
        else:
            self.stdout.write(self.style.ERROR('Failed to fetch Trendlyne data'))
```

Run with:
```bash
python manage.py fetch_trendlyne
```

## Troubleshooting

### Common Issues

**1. Login Failed**
- Verify credentials in Django admin
- Check if Trendlyne website changed login flow
- Ensure Chrome/Chromedriver is installed

**2. No CSV Files Downloaded**
- Check download directory permissions
- Verify Trendlyne subscription is active
- Check if download URLs changed

**3. ChromeDriver Issues**
```bash
# Manually install chromedriver
pip install chromedriver-autoinstaller --upgrade
```

**4. Import Errors**
```bash
# Reinstall dependencies
pip install --force-reinstall selenium beautifulsoup4 pandas
```

### Debugging

Enable verbose logging in `trendlyne.py`:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Add logger.debug() calls throughout your code
```

## Data Directory Structure

```
apps/data/
├── tldata/                     # Main download directory
│   ├── fno_data_YYYY-MM-DD.csv
│   └── market_snapshot_YYYY-MM-DD.csv
│
└── trendlynedata/              # Forecaster data
    ├── trendlyne_High_Bullishness.csv
    ├── trendlyne_High_Bearishness.csv
    ├── trendlyne_Beat_Annual_EPS_Estimates.csv
    ├── trendlyne_Missed_Quarter_Revenue_Estimates.csv
    └── ... (21 files total)
```

## Security Considerations

**1. Credentials Storage**
- Never commit credentials to version control
- Use environment variables for production
- Consider using Django's `django-encrypted-model-fields` for added security

**2. Rate Limiting**
- Trendlyne may have rate limits
- Add delays between requests if scraping multiple stocks
- Respect robots.txt

**3. Data Privacy**
- Ensure compliance with Trendlyne's Terms of Service
- Don't redistribute scraped data without permission

## Next Steps

1. **Import Historical Data**: Import the existing CSV files from old project
2. **Build Validators**: Create validation functions using Trendlyne scores (momentum, valuation, quality)
3. **LLM Integration**: Use TLStockData with LLM for stock analysis
4. **Strategy Development**: Build trading strategies using comprehensive metrics
5. **Dashboard**: Create frontend dashboard to visualize Trendlyne scores

## Support

For issues or questions:
1. Check Django logs: `python manage.py runserver --verbosity=3`
2. Verify database: `python manage.py dbshell`
3. Review scraped files in `apps/data/tldata/`
4. Test individual functions in Django shell

## License

This integration is for personal/educational use only. Ensure compliance with Trendlyne's Terms of Service.
