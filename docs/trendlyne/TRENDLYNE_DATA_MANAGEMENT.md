# Trendlyne Data Management System

Complete guide to downloading, parsing, and populating Trendlyne data in mCube Trading System.

## Overview

The Trendlyne data management system provides a complete workflow:

```
┌─────────────────────────────────────────────────────────┐
│  1. DOWNLOAD DATA                                       │
│  ↓ Downloads raw CSV files from Trendlyne              │
│  2. SAVE TO TEMPORARY STORAGE                          │
│  ↓ Stores in /trendlyne_data directory                 │
│  3. PARSE & POPULATE DATABASE                          │
│  ↓ Converts CSVs to model instances                    │
│  4. CLEAR TEMPORARY FILES                              │
│  ↓ Removes raw files after successful import           │
└─────────────────────────────────────────────────────────┘
```

---

## Database Tables

The following tables will be populated:

### 1. **ContractData**
F&O contracts (futures & options) with Greeks and metrics
- Symbols, strikes, expiry dates
- Price, volume, open interest data
- Greeks (delta, gamma, vega, theta, rho)

### 2. **ContractStockData**
F&O aggregated metrics by stock
- Total open interest
- Put/Call ratios
- Volume metrics
- Rollover data

### 3. **TLStockData**
Comprehensive stock data (80+ fields)
- Fundamental metrics
- Technical indicators
- Trendlyne scores (durability, valuation, momentum)
- Institutional holdings

### 4. **OptionChain**
Real-time option chain data
- Underlying, expiry, strikes
- Prices, Greeks
- Open interest, volume

### 5. **Event**
Economic/market events calendar
- Event date, time, importance
- Actual, forecast, previous values
- Impact categories

### 6. **NewsArticle**
Market and financial news
- Title, content, source
- Publication date
- URL

### 7. **InvestorCall**
Company investor calls and earnings
- Company, date, title
- Call summary

### 8. **KnowledgeBase**
Educational articles and tutorials
- Title, content, category
- Self-curated knowledge base

---

## Management Command

### Complete Workflow (Recommended)

```bash
# Full cycle: Download -> Parse -> Populate -> Clean
python manage.py trendlyne_data_manager --full-cycle
```

This command:
1. ✅ Clears previous files (if any)
2. ✅ Downloads new data from Trendlyne
3. ✅ Parses CSV files
4. ✅ Populates database tables
5. ✅ Deletes temporary files
6. ✅ Shows summary

### Individual Steps

**Download Data Only**
```bash
python manage.py trendlyne_data_manager --download-all
```
Saves raw CSV files to `/trendlyne_data` directory

**Parse & Populate**
```bash
python manage.py trendlyne_data_manager --parse-all
```
Converts CSV files to database records

**Clear Temporary Files**
```bash
python manage.py trendlyne_data_manager --clear-files
```
Removes downloaded CSV files

**Clear Database**
```bash
python manage.py trendlyne_data_manager --clear-database
```
Deletes all data from database tables

**Check Status**
```bash
python manage.py trendlyne_data_manager --status
```
Shows file and database statistics

---

## File Structure

### Download Directory
```
/trendlyne_data/
├── contract_data.csv           # F&O contracts
├── contract_stock_data.csv     # F&O by stock
├── stock_data.csv              # Stock fundamentals
├── option_chains.csv           # Option chain data
├── events.csv                  # Economic events
├── news.csv                    # News articles
├── investor_calls.csv          # Investor calls
└── knowledge_base.csv          # Knowledge base
```

### File Format

All files are CSV with headers. Example:

**contract_data.csv:**
```
symbol,option_type,strike_price,price,spot,expiry,last_updated,...
NIFTY,CE,18000,150.50,17950,27-NOV-2024,10:15 AM,...
NIFTY,PE,18000,148.75,17950,27-NOV-2024,10:15 AM,...
```

**stock_data.csv:**
```
stock_name,nsecode,current_price,industry_name,trendlyne_durability_score
Reliance,RELIANCE,2500.50,Energy,80.5
TCS,TCS,3650.25,IT,75.8
```

---

## Usage Examples

### Example 1: Daily Data Update

```bash
# Run daily to get fresh data
python manage.py trendlyne_data_manager --full-cycle
```

### Example 2: Manual Two-Step Process

```bash
# Step 1: Download data (can be paused)
python manage.py trendlyne_data_manager --download-all

# ... Do other work ...

# Step 2: Parse and populate when ready
python manage.py trendlyne_data_manager --parse-all
```

### Example 3: Refresh Specific Data

```bash
# Clear old data and download new
python manage.py trendlyne_data_manager --clear-database
python manage.py trendlyne_data_manager --full-cycle
```

### Example 4: Monitor Data Status

```bash
# Check before/after operations
python manage.py trendlyne_data_manager --status

# Sample output:
# 📁 Downloaded Files:
#   ✅ contract_data.csv (2.5 MB)
#   ✅ stock_data.csv (1.2 MB)
#
# 💾 Database Records:
#   ✅ Contract Data: 5432 records
#   ✅ Stock Data: 1200 records
```

---

## Python Usage

### Direct Import

```python
from apps.data.management.commands.trendlyne_data_manager import Command

# Run full cycle programmatically
cmd = Command()
cmd.full_cycle()
```

### Using Django Management

```python
from django.core.management import call_command

# Run full cycle
call_command('trendlyne_data_manager', '--full-cycle')

# Check status
call_command('trendlyne_data_manager', '--status')
```

---

## Data Querying

### Query ContractData

```python
from apps.data.models import ContractData

# Get all NIFTY options
nifty_options = ContractData.objects.filter(symbol='NIFTY', option_type__in=['CE', 'PE'])

# Get specific expiry
nov_expiry = ContractData.objects.filter(expiry='27-NOV-2024')

# Filter by Greeks
high_delta = ContractData.objects.filter(delta__gt=0.7)

# Get latest data
latest = ContractData.objects.latest('created_at')
```

### Query StockData

```python
from apps.data.models import TLStockData

# Get all stocks
all_stocks = TLStockData.objects.all()

# Filter by Trendlyne score
quality_stocks = TLStockData.objects.filter(
    trendlyne_durability_score__gte=70,
    trendlyne_valuation_score__gte=60
)

# Get by sector
it_stocks = TLStockData.objects.filter(sector_name='IT Services')
```

### Query Events

```python
from apps.data.models import Event
from datetime import date, timedelta

# Get today's events
today = date.today()
events_today = Event.objects.filter(event_date=today)

# Get high importance events
important = Event.objects.filter(importance='HIGH')

# Get events for next 7 days
future_events = Event.objects.filter(
    event_date__range=[today, today + timedelta(days=7)]
)
```

---

## Data Volume Expectations

| Table | Expected Records | File Size |
|-------|-----------------|-----------|
| ContractData | 5,000-10,000 | 2-5 MB |
| ContractStockData | 1,000-2,000 | 0.5-1 MB |
| TLStockData | 2,000-3,000 | 1-3 MB |
| OptionChain | 3,000-5,000 | 1-2 MB |
| Event | 100-200 | 50-100 KB |
| NewsArticle | 500-1,000 | 1-2 MB |
| InvestorCall | 100-200 | 50-100 KB |
| KnowledgeBase | 50-100 | 20-50 KB |

**Total Estimated Size:** 5-15 MB

---

## Troubleshooting

### Issue: "Trendlyne credentials not found"

**Solution:** Add Trendlyne credentials first
```bash
python manage.py setup_credentials --setup-trendlyne
```

### Issue: "Chrome driver error"

**Solution:** Install ChromeDriver
```bash
pip install chromedriver-autoinstaller
```

### Issue: "Download timeout"

**Solution:** Increase timeout or run in headless mode
```python
# Edit trendlyne_downloader.py to adjust timeouts
# Or disable headless mode for debugging
```

### Issue: "CSV parsing error"

**Solution:** Verify file format
```bash
# Check file exists
ls -la /trendlyne_data/

# Verify CSV format
head -5 /trendlyne_data/contract_data.csv
```

### Issue: "Database constraint error"

**Solution:** Clear database first
```bash
python manage.py trendlyne_data_manager --clear-database
python manage.py trendlyne_data_manager --full-cycle
```

---

## Best Practices

### 1. Regular Updates
```bash
# Daily cron job (add to crontab)
0 16 * * * cd /path/to/project && python manage.py trendlyne_data_manager --full-cycle
```

### 2. Monitor File Size
```bash
# Check download directory size
du -sh /trendlyne_data/

# Clean up if needed
python manage.py trendlyne_data_manager --clear-files
```

### 3. Backup Database Before Updates
```bash
# Backup
python manage.py dumpdata data > data_backup.json

# If needed, restore
python manage.py loaddata data_backup.json
```

### 4. Verify Data After Import
```bash
# Check database status
python manage.py trendlyne_data_manager --status

# Count records
python manage.py shell << 'EOF'
from apps.data.models import ContractData, TLStockData
print(f"Contracts: {ContractData.objects.count()}")
print(f"Stocks: {TLStockData.objects.count()}")
EOF
```

---

## Performance Tips

### 1. Index Queries
```python
# Use select_related for foreign keys
contracts = ContractData.objects.select_related('...')

# Use only for specific fields
limited = ContractData.objects.only('symbol', 'price')
```

### 2. Batch Operations
```python
# Create in batches for faster import
objects = [... create model instances ...]
ContractData.objects.bulk_create(objects, batch_size=1000)
```

### 3. Archive Old Data
```python
from datetime import datetime, timedelta

# Archive data older than 30 days
thirty_days_ago = datetime.now() - timedelta(days=30)
old_data = ContractData.objects.filter(created_at__lt=thirty_days_ago)
old_data.delete()
```

---

## Scheduling

### Using APScheduler

```python
# In your scheduler setup
from apscheduler.schedulers.background import BackgroundScheduler
from django.core.management import call_command

def update_trendlyne_data():
    call_command('trendlyne_data_manager', '--full-cycle')

scheduler = BackgroundScheduler()
scheduler.add_job(update_trendlyne_data, 'cron', hour=16, minute=0)
scheduler.start()
```

### Using Celery

```python
# tasks.py
from celery import shared_task
from django.core.management import call_command

@shared_task
def update_trendlyne_data():
    call_command('trendlyne_data_manager', '--full-cycle')
    return "Trendlyne data updated"

# Schedule in celery beat
from celery.schedules import crontab

app.conf.beat_schedule = {
    'update-trendlyne': {
        'task': 'apps.data.tasks.update_trendlyne_data',
        'schedule': crontab(hour=16, minute=0),  # 4 PM daily
    },
}
```

---

## File Locations

- **Management Command**: `apps/data/management/commands/trendlyne_data_manager.py`
- **Downloader Module**: `apps/data/tools/trendlyne_downloader.py`
- **Data Models**: `apps/data/models.py`
- **Download Directory**: `BASE_DIR/trendlyne_data/`

---

## Next Steps

1. **Setup Trendlyne Credentials**
   ```bash
   python manage.py setup_credentials --setup-trendlyne
   ```

2. **Test Connection**
   ```bash
   python manage.py setup_credentials --test-trendlyne
   ```

3. **Run Initial Data Import**
   ```bash
   python manage.py trendlyne_data_manager --full-cycle
   ```

4. **Verify Data**
   ```bash
   python manage.py trendlyne_data_manager --status
   ```

5. **Query and Use Data**
   ```python
   from apps.data.models import ContractData
   contracts = ContractData.objects.all()
   ```

---

## Support

For issues or questions:
1. Check status: `python manage.py trendlyne_data_manager --status`
2. Review logs in Django logs
3. Verify Trendlyne credentials
4. Check internet connectivity
5. Ensure Chrome/ChromeDriver is installed

---

**Version:** 1.0
**Last Updated:** 2024-11-16
**Status:** ✅ Production Ready
