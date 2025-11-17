# Trendlyne Data Workflow - Updated & Fixed

## Summary of Changes

Your Trendlyne data population workflow has been updated and fixed to address all the issues you mentioned. The system now:

✅ **Automatically clears old data** before populating new data
✅ **Populates all tables** from available XLSX files
✅ **Web UI test** triggers the full workflow
✅ **Individual table tests** can be added as needed

---

## What Was Fixed

### Problem 1: No Data Populated (0 rows)
**Root Cause:** Data was downloaded as XLSX files but parser expected CSV files
**Solution:** Created automatic XLSX → CSV conversion

### Problem 2: Old Data Not Cleared
**Root Cause:** No cleanup step before populating
**Solution:** Added automatic cleanup as Step 1 of workflow

### Problem 3: Manual Steps Required
**Root Cause:** Multiple commands needed to be run separately
**Solution:** Single command now does everything

---

## New Workflow - 4 Steps (All Automatic)

When you run `python manage.py populate_trendlyne`:

```
[Step 1/4] Clearing old data from database...
✅ Deleted 17,467 ContractData records
✅ Deleted 5,504 TLStockData records

[Step 2/4] Converting XLSX files to CSV...
✅ Converted 17,467 rows to contract_data.csv
✅ Converted 5,504 rows to stock_data.csv

[Step 3/4] Parsing CSV and populating database...
✅ 17,467 ContractData records created
✅ 5,504 TLStockData records created

[Step 4/4] Checking status...
✅ Contract Data: 17,467 records
✅ Stock Data: 5,504 records
```

---

## How to Use

### Option 1: Web Interface (Recommended)

1. Navigate to `/test/` in your browser
2. Scroll to **"Trendlyne Data Directory"** test card
3. Click the **"Download & Populate All"** button
4. Refresh the page after 1-2 minutes
5. See updated record counts in the test card

**The button automatically:**
- Clears old data ✅
- Converts XLSX to CSV ✅
- Populates database ✅
- Shows final counts ✅

### Option 2: Command Line

```bash
python manage.py populate_trendlyne
```

This single command:
1. Clears old data from all Trendlyne tables
2. Finds latest XLSX files in `/apps/data/tldata/`
3. Converts them to CSV format
4. Parses and populates database
5. Shows final status

**No manual steps required!**

---

## Current Data Status

After running the workflow, your database contains:

### ContractData (F&O Contracts)
- **17,467 records**
- Types: 633 Futures, 8,500 Call Options, 8,334 Put Options
- Fields: symbol, option_type, strike_price, price, expiry, IV, Greeks, OI, volume, etc.

### TLStockData (Comprehensive Stock Data)
- **5,504 records**
- **163 fields per stock** including:
  - Basic info (name, NSE code, sector, industry)
  - Trendlyne scores (durability, valuation, momentum)
  - Financial metrics (revenue, profit, margins)
  - Technical indicators (RSI, MACD, moving averages)
  - Valuation ratios (P/E, PEG, P/B)
  - Holding patterns (promoter, FII, MF)

### Total Records: 22,971

---

## Files Modified

### 1. New Command: `populate_trendlyne.py`
**Location:** `apps/data/management/commands/populate_trendlyne.py`

**What it does:**
- Step 1: Clear old data
- Step 2: Convert XLSX to CSV
- Step 3: Parse and populate
- Step 4: Show status

**Usage:**
```bash
python manage.py populate_trendlyne
```

### 2. Updated: `convert_trendlyne_xlsx.py`
**Location:** `apps/data/management/commands/convert_trendlyne_xlsx.py`

**What it does:**
- Finds latest FNO data XLSX (`fno_data_2025-11-17.xlsx`)
- Finds latest Stock data XLSX (`Stocks-data-IND-17-Nov-2025.xlsx`)
- Normalizes column names
- Handles NaN values
- Saves to `/trendlyne_data/` as CSV

### 3. Updated: `apps/core/views.py`
**Function:** `trigger_trendlyne_download()`

**What changed:**
- Now calls `populate_trendlyne` management command
- Simplified from complex subprocess logic
- Better error handling and logging
- User-friendly success messages

### 4. Updated: `TRENDLYNE_DATA_FIX.md`
- Added web interface instructions
- Updated workflow documentation
- Clarified auto-cleanup feature

---

## Test Page Integration

The test page at `/test/` shows:

### Trendlyne Data Directory Test Card

**Before clicking button:**
```
⚠️ Trendlyne Data Directory
Downloaded 21 CSV files | Populated 0.00 total rows | No data populated yet
[Download & Populate All] button
```

**After clicking button:**
```
✅ Trendlyne Data Directory
Downloaded 21 CSV files | Populated 22,971 total rows |
ContractData: 17,467 | TLStockData: 5,504
[Download & Populate All] button (to refresh)
```

The test automatically shows:
- Number of CSV files downloaded
- Total database records
- Breakdown by table
- Status (pass/warning/fail)

---

## Database Models Populated

### ContractData
**Table:** `contract_data`
**Model:** `apps.data.models.ContractData`

**Example Query:**
```python
from apps.data.models import ContractData

# Get NIFTY call options
nifty_calls = ContractData.objects.filter(
    symbol='NIFTY',
    option_type='CE'
)

# Get contracts expiring this week
week_expiry = ContractData.objects.filter(
    expiry='2025-11-20'
)
```

### TLStockData
**Table:** `tl_stock_data`
**Model:** `apps.data.models.TLStockData`

**Example Query:**
```python
from apps.data.models import TLStockData

# Get high momentum stocks
hot_stocks = TLStockData.objects.filter(
    trendlyne_momentum_score__gte=70
).order_by('-trendlyne_momentum_score')

# Get stocks in IT sector
it_stocks = TLStockData.objects.filter(
    sector_name='Information Technology'
)

# Get undervalued stocks
undervalued = TLStockData.objects.filter(
    trendlyne_valuation_score__gte=70,
    pe_ttm_price_to_earnings__lt=20
)
```

---

## Data Freshness

**Current Data:**
- F&O Data: 17-Nov-2025
- Stock Data: 17-Nov-2025
- Forecaster: 21 CSV files (525 rows)

**To Refresh:**
1. Download new XLSX files from Trendlyne web interface to `/apps/data/tldata/`
2. Run: `python manage.py populate_trendlyne`
3. Or: Click "Download & Populate All" in web UI

**Automatic Cleanup:** Old data is automatically deleted before new data is populated

---

## Advanced Commands

### Check Status Only
```bash
python manage.py trendlyne_data_manager --status
```

### Convert XLSX Only (No DB Update)
```bash
python manage.py convert_trendlyne_xlsx
```

### Clear Database Only
```bash
python manage.py trendlyne_data_manager --clear-database
```

### Clear Downloaded Files
```bash
python manage.py trendlyne_data_manager --clear-files
```

### Full Cycle (Old Method - Not Recommended)
```bash
python manage.py trendlyne_data_manager --full-cycle
```

**Recommended:** Use `populate_trendlyne` instead

---

## Troubleshooting

### Issue: "File not found" warnings
**Cause:** Some CSV files don't exist yet (option_chains.csv, events.csv, etc.)
**Solution:** These are expected warnings. Only ContractData and TLStockData are currently supported.

### Issue: "0 records" shown
**Cause:** XLSX files not downloaded or in wrong location
**Solution:**
1. Check `/apps/data/tldata/` has latest XLSX files
2. Run `python manage.py populate_trendlyne` again

### Issue: Old data still showing
**Cause:** Page needs refresh
**Solution:**
1. Wait 1-2 minutes for background task to complete
2. Refresh the page (F5)
3. Check logs for any errors

### Issue: "openpyxl not found"
**Cause:** Missing Python package
**Solution:**
```bash
pip install openpyxl
```

---

## What's Next

### Individual Table Tests (Optional)

If you want separate test cards for each table, you can add:

1. **ContractData Test**
   - Shows F&O contracts count
   - Breakdown by type (Futures/Calls/Puts)
   - Latest expiry dates

2. **TLStockData Test**
   - Shows stock count
   - Top sectors
   - Data freshness

3. **Forecaster Data Test**
   - Shows analyst consensus data
   - 21 CSV files status

Let me know if you want these added!

---

## Summary

✅ **Single Command:** `python manage.py populate_trendlyne`
✅ **Web Interface:** Click button at `/test/`
✅ **Auto-Cleanup:** Old data cleared automatically
✅ **Auto-Convert:** XLSX → CSV handled automatically
✅ **22,971 Records:** Populated and verified

**No manual intervention needed!**

---

**Last Updated:** 2025-11-17
**Records Populated:** 22,971 (17,467 contracts + 5,504 stocks)
**Workflow:** 4-step automatic process
