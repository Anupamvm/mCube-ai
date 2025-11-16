# Comprehensive Trendlyne Data Parser

## Overview
The comprehensive Trendlyne data parser (`parse_all_trendlyne_data.py`) is the single source of truth for parsing and populating ALL Trendlyne database models. It replaces fragmented parsing logic and ensures consistent data clearing and population.

## Features

### ✅ Complete Model Coverage
Parses and populates:
- **ContractData**: All F&O contracts (17,329 records)
- **TLStockData**: Market snapshot stocks (5,500 records)
- **OptionChain**: Option chain data for ALL stocks (16,695 records across 214 stocks)
- **ContractStockData**: Stock-level F&O summary (placeholder - requires additional data file)

### ✅ Automatic Old Data Clearing
Before inserting new data, the parser:
1. Counts existing records in each model
2. Deletes all old records (`Model.objects.all().delete()`)
3. Logs how many records were cleared
4. Inserts fresh data from XLSX files

### ✅ Progress Tracking
- Reports progress every 500-1000 records
- Shows final record counts
- Provides breakdown statistics

### ✅ Comprehensive Option Data
OptionChain now includes ALL 214 stocks with F&O options, including:
- NIFTY (1,115 options)
- BANKNIFTY (452 options)
- MIDCPNIFTY (172 options)
- Individual stocks: ASIANPAINT, RELIANCE, SBIN, TCS, COALINDIA, etc.
- All 214 stocks with CE and PE options

## Data Sources

### Primary XLSX Files
Located in `apps/data/tldata/`:

1. **F&O Data**: `fno_data_2025-11-16.xlsx`
   - Contains 17,329 F&O contracts
   - Source for ContractData and OptionChain
   - Columns: SYMBOL, OPTION TYPE, STRIKE PRICE, EXPIRY, PRICE, OI, VOLUME, IV, DELTA, GAMMA, THETA, VEGA, etc.

2. **Market Snapshot**: `market_snapshot_2025-11-16.xlsx`
   - Contains 5,500 stock records
   - Source for TLStockData
   - Columns: Stock Name, NSEcode, BSEcode, ISIN, Industry Name, Current Price, Market Capitalization, Trendlyne Scores

## Usage

### From Command Line
```bash
python parse_all_trendlyne_data.py
```

### From Django Admin
1. Navigate to `/test/` (System Test page)
2. Find "Trendlyne Data Directory" section
3. Click "Download & Populate All" button
4. Wait 2-3 minutes for completion
5. Refresh page to see updated statistics

### From Code
```python
from parse_all_trendlyne_data import main
main()
```

## Output Example

```
======================================================================
COMPREHENSIVE TRENDLYNE DATA PARSER
======================================================================

📊 Parsing Contract Data (F&O)...
Found 17329 rows in apps/data/tldata/fno_data_2025-11-16.xlsx
Cleared 0 existing ContractData records
  ... created 1000 contract records
  ... created 17000 contract records
✅ Created 17329 ContractData records

📊 Parsing Market Snapshot (TLStockData)...
Found 5500 rows in apps/data/tldata/market_snapshot_2025-11-16.xlsx
Cleared 5500 existing TLStockData records
  ... created 5000 records
✅ Created 5500 TLStockData records

📊 Parsing Option Chain Data from Contracts...
Found 17329 rows in apps/data/tldata/fno_data_2025-11-16.xlsx
Cleared 16695 existing OptionChain records
  ... created 16000 option chain records
✅ Created 16695 OptionChain records for ALL stocks

Top 20 stocks by option count:
  NIFTY: 1115 options
  BANKNIFTY: 452 options
  MIDCPNIFTY: 172 options
  ASIANPAINT: 154 options
  RELIANCE: 143 options
  ...

======================================================================
SUMMARY
======================================================================

Database Record Counts:
  ContractData: 17,329
  ContractStockData: 0
  TLStockData: 5,500
  OptionChain: 16,695
  Event: 10
  NewsArticle: 8
  InvestorCall: 1
  KnowledgeBase: 2

✅ TOTAL: 39,545 records across all models
======================================================================
```

## Parser Functions

### 1. `parse_contract_data()`
**Purpose**: Parse all F&O contracts from XLSX file

**Process**:
1. Reads `fno_data_2025-11-16.xlsx`
2. Clears existing ContractData records
3. Parses all 17,329 rows
4. Creates ContractData objects with:
   - Symbol, option type, strike price, expiry
   - Price metrics (open, high, low, close, day change)
   - OI metrics (OI, OI change, % OI change)
   - Volume metrics (traded contracts, shares traded)
   - Greeks (IV, Delta, Gamma, Theta, Vega, Rho)

**Fields Populated**: All 30+ fields in ContractData model

### 2. `parse_market_snapshot()`
**Purpose**: Parse market snapshot stock data

**Process**:
1. Reads `market_snapshot_2025-11-16.xlsx`
2. Clears existing TLStockData records
3. Uses `update_or_create()` to handle duplicates
4. Creates TLStockData objects with:
   - Stock name, NSE/BSE codes, ISIN
   - Industry and sector classification
   - Current price and market cap
   - Trendlyne scores (Durability, Valuation, Momentum)

**Deduplication**: Uses NSEcode as unique key

### 3. `parse_option_chain_from_contracts()`
**Purpose**: Parse option chain data for ALL stocks

**Process**:
1. Reads same F&O file (`fno_data_2025-11-16.xlsx`)
2. Clears existing OptionChain records
3. Filters for options only (skips FUTURE contracts)
4. For each CE/PE option across ALL 214 stocks:
   - Parses underlying, expiry date, strike price
   - Captures option type (CE or PE)
   - Stores LTP, bid, ask, volume, OI
   - Records Greeks (IV, Delta, Gamma, Theta, Vega)

**Coverage**: 16,695 options across 214 different stocks

**Breakdown Statistics**: Shows top 20 stocks by option count

### 4. `parse_contract_stock_data()`
**Purpose**: Parse stock-level F&O summary

**Status**: Placeholder - requires stock-level summary file not available in current downloads

## Helper Functions

### `safe_float(value, default=0)`
Safely converts values to float, handling:
- NaN values → returns default
- Invalid values → returns default
- Valid numbers → returns float

### `safe_int(value, default=0)`
Safely converts values to int, handling:
- NaN values → returns default
- Invalid values → returns default
- Valid numbers → returns int

## Database Models Updated

### ContractData
- **Purpose**: Store all F&O contract data
- **Records**: 17,329
- **Key Fields**: symbol, option_type, strike_price, expiry, price, OI, volume, Greeks
- **Clearing**: Yes, before insert

### TLStockData
- **Purpose**: Store market snapshot data
- **Records**: 5,500
- **Key Fields**: nsecode (unique), stock_name, current_price, market_cap, Trendlyne scores
- **Clearing**: Yes, before insert

### OptionChain
- **Purpose**: Store option chain data for ALL stocks
- **Records**: 16,695
- **Key Fields**: underlying, expiry_date, strike, option_type (CE/PE), LTP, OI, IV, Greeks
- **Clearing**: Yes, before insert
- **Stocks Covered**: 214 (all F&O stocks)

### ContractStockData
- **Purpose**: Store stock-level F&O summary
- **Records**: 0 (requires additional data file)
- **Status**: Placeholder

## Integration with Trigger Function

The `trigger_trendlyne_download()` view function (`apps/core/views.py:257`) now uses this comprehensive parser:

```python
def trigger_trendlyne_download(request):
    """
    Trigger Trendlyne FULL CYCLE: Download → Parse → Populate Database
    """
    def full_download_and_populate_task():
        # Step 1: Download all data from Trendlyne
        results = get_all_trendlyne_data()

        # Step 2: Parse and populate using comprehensive parser
        result = subprocess.run(
            ['python', 'parse_all_trendlyne_data.py'],
            cwd='/Users/anupammangudkar/Projects/mCube-ai/mCube-ai',
            capture_output=True,
            text=True,
            timeout=300
        )

        # Step 3: Get summary statistics
        stats = {
            'ContractData': ContractData.objects.count(),
            'TLStockData': TLStockData.objects.count(),
            'OptionChain': OptionChain.objects.count(),
            # ... etc
        }
```

## Comparison with Old Parser

| Feature | Old (`parse_trendlyne_xlsx.py`) | New (`parse_all_trendlyne_data.py`) |
|---------|----------------------------------|-------------------------------------|
| ContractData | ✅ 17,329 records | ✅ 17,329 records |
| TLStockData | ✅ 5,500 records | ✅ 5,500 records |
| OptionChain | ❌ Not included | ✅ 16,695 records (ALL stocks) |
| Old Data Clearing | ✅ Yes | ✅ Yes |
| Progress Reporting | ✅ Yes | ✅ Enhanced with breakdowns |
| Comprehensive Stats | ❌ Limited | ✅ Full model summary |

## Verification

### Check OptionChain Coverage
```python
from apps.data.models import OptionChain
from django.db.models import Count

# Get all stocks with options
underlyings = OptionChain.objects.values('underlying').annotate(
    count=Count('id')
).order_by('-count')

print(f"Total stocks: {len(underlyings)}")
print(f"Total options: {OptionChain.objects.count():,}")

# Top 10 stocks
for item in underlyings[:10]:
    print(f"{item['underlying']}: {item['count']} options")
```

Expected output:
```
Total stocks: 214
Total options: 16,695
NIFTY: 1115 options
BANKNIFTY: 452 options
MIDCPNIFTY: 172 options
ASIANPAINT: 154 options
RELIANCE: 143 options
...
```

### Check All Models
```python
from apps.data.models import (
    ContractData, ContractStockData, TLStockData, OptionChain
)

print(f"ContractData: {ContractData.objects.count():,}")
print(f"TLStockData: {TLStockData.objects.count():,}")
print(f"OptionChain: {OptionChain.objects.count():,}")
print(f"ContractStockData: {ContractStockData.objects.count():,}")
```

Expected output:
```
ContractData: 17,329
TLStockData: 5,500
OptionChain: 16,695
ContractStockData: 0
```

## Error Handling

### File Not Found
If XLSX files are missing, parser gracefully handles with:
```
❌ File not found
```
Returns 0 records created.

### Database Constraints
All required numeric fields use `safe_float()` and `safe_int()` with default values to prevent constraint violations.

### Column Name Variations
Parser checks multiple possible column names:
```python
stock_name = row.get('Stock Name') or row.get('STOCK') or row.get('Stock') or ''
nsecode = row.get('NSEcode') or row.get('NSE CODE') or row.get('NSE') or ''
```

### Transaction Safety
All parsing uses `transaction.atomic()` to ensure data integrity:
```python
with transaction.atomic():
    for idx, row in df.iterrows():
        # Create records
```

## Performance

- **Parsing Time**: ~30-60 seconds for all models
- **ContractData**: ~15 seconds (17,329 records)
- **TLStockData**: ~8 seconds (5,500 records)
- **OptionChain**: ~20 seconds (16,695 records)

Progress updates every 500-1000 records ensure user visibility.

## Future Enhancements

1. **ContractStockData Population**: Requires stock-level summary file
2. **Incremental Updates**: Only update changed records
3. **Data Validation**: Verify data integrity after population
4. **Scheduling**: Celery periodic task for automatic daily updates
5. **Email Notifications**: Alert when parsing completes
6. **Error Recovery**: Retry failed records
7. **Data Export**: Export parsed data to CSV for analysis

## Troubleshooting

### OptionChain Shows Only NIFTY/BANKNIFTY
**Issue**: Old parser only filtered for major indices

**Solution**: Run comprehensive parser
```bash
python parse_all_trendlyne_data.py
```

### ContractData Empty After Download
**Issue**: Trigger function not calling comprehensive parser

**Solution**: Check `apps/core/views.py:290` uses subprocess to run `parse_all_trendlyne_data.py`

### Duplicate Records in TLStockData
**Issue**: Multiple rows with same NSEcode

**Solution**: Parser uses `update_or_create()` with NSEcode as unique key

## Logs Location

Parser logs to Django logger:
```python
logger.info("Parsing files and populating database models...")
logger.info(f"Full Trendlyne cycle completed: {total} total records")
```

Check Django logs for parser output.

## Related Files

- **Parser Script**: `/parse_all_trendlyne_data.py`
- **Trigger Function**: `/apps/core/views.py` (line 257)
- **Data Directory**: `/apps/data/tldata/`
- **Old Parser**: `/parse_trendlyne_xlsx.py` (deprecated)
- **Models**: `/apps/data/models.py`

## Summary

The comprehensive Trendlyne parser solves all data population issues:
- ✅ Populates ALL models (ContractData, TLStockData, OptionChain)
- ✅ Clears old data before updates
- ✅ Covers ALL 214 stocks with F&O options (not just NIFTY/BANKNIFTY)
- ✅ Provides detailed statistics and breakdowns
- ✅ Integrated with trigger button for easy use
- ✅ Handles 39,545 total records across all models

This is now the single source of truth for Trendlyne data parsing.
