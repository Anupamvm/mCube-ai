# Trendlyne Data Population - Issue Fixed

## Problem Summary

**Issue:** Trendlyne data was being downloaded (21 CSV files in forecaster directory, multiple XLSX files in tldata directory) but 0 rows were being populated into the database tables.

**Root Cause:**
1. Data was being downloaded as **XLSX files** (fno_data_*.xlsx, Stocks-data-IND-*.xlsx)
2. The `trendlyne_data_manager` command expected **CSV files** in `/trendlyne_data/` directory
3. No automatic conversion from XLSX to CSV was in place
4. Downloaded XLSX files were in `/apps/data/tldata/` but parser looked in `/trendlyne_data/`

## Solution Implemented

### 1. Installed Required Dependency
```bash
pip install openpyxl
```
This library is required to read Excel (.xlsx) files with pandas.

### 2. Created XLSX to CSV Conversion Command
**New File:** `apps/data/management/commands/convert_trendlyne_xlsx.py`

This command:
- Finds the latest FNO data XLSX file (`fno_data_2025-11-17.xlsx`)
- Finds the latest Stock data XLSX file (`Stocks-data-IND-17-Nov-2025.xlsx`)
- Converts them to CSV format with normalized column names
- Handles NaN values properly
- Saves to `/trendlyne_data/` directory

**Usage:**
```bash
python manage.py convert_trendlyne_xlsx
```

### 3. Created Complete Workflow Command
**New File:** `apps/data/management/commands/populate_trendlyne.py`

This command runs the complete workflow:
1. Convert XLSX files to CSV
2. Parse CSV files and populate database
3. Show status

**Usage (Recommended):**
```bash
python manage.py populate_trendlyne
```

## Current Data Status

After running the fix:

✅ **Contract Data:** 17,467 records
✅ **Stock Data:** 5,504 records

### Database Tables Populated

1. **contract_data** (ContractData model)
   - 17,467 F&O contracts
   - Fields: symbol, option_type, strike_price, price, spot, expiry, IV, Greeks, OI, volume, etc.
   - Includes FUTURES, CALL OPTIONS, and PUT OPTIONS

2. **tl_stock_data** (TLStockData model)
   - 5,504 stocks
   - 163 fields including:
     - Basic info (name, NSE code, sector, industry)
     - Trendlyne scores (durability, valuation, momentum)
     - Financial metrics (revenue, profit, margins)
     - Technical indicators (RSI, MACD, moving averages)
     - Valuation ratios (P/E, PEG, P/B)
     - Holding patterns (promoter, FII, MF)
     - Support/resistance levels

## How to Use Going Forward

### Quick Start - One Command
```bash
# After downloading new data from Trendlyne web interface:
python manage.py populate_trendlyne
```

This will:
1. ✅ **Clear old data** from database tables
2. ✅ Convert XLSX to CSV
3. ✅ Parse CSV and populate database
4. ✅ Show final status

**No need to manually clear data!** The command handles everything automatically.

### Web Interface (Recommended)

1. Navigate to `/test/` in your browser
2. Find "Trendlyne Data Directory" test card
3. Click **"Download & Populate All"** button
4. Refresh page after 1-2 minutes to see updated data

The web interface automatically:
- Clears old data
- Converts XLSX to CSV
- Populates database
- Shows final counts

### Individual Commands (Advanced)

**Convert XLSX only:**
```bash
python manage.py convert_trendlyne_xlsx
```

**Parse CSV only:**
```bash
python manage.py trendlyne_data_manager --parse-all
```

**Check status:**
```bash
python manage.py trendlyne_data_manager --status
```

**Clear database only:**
```bash
python manage.py trendlyne_data_manager --clear-database
```

**Clear files only:**
```bash
python manage.py trendlyne_data_manager --clear-files
```

## Using the Data in Your Code

```python
from apps.data.models import ContractData, TLStockData

# Get all NIFTY contracts
nifty_contracts = ContractData.objects.filter(symbol='NIFTY')

# Get all call options expiring this week
calls = ContractData.objects.filter(
    option_type='CE',
    expiry='2025-11-20'
)

# Get stocks with high momentum
high_momentum = TLStockData.objects.filter(
    trendlyne_momentum_score__gte=70
).order_by('-trendlyne_momentum_score')

# Get stocks in specific sector
it_stocks = TLStockData.objects.filter(
    sector_name='Information Technology'
)

# Get F&O data for a specific stock
reliance_contracts = ContractData.objects.filter(symbol='RELIANCE')
```

## Data Freshness

Current data:
- **F&O Data:** 17-Nov-2025 (fno_data_2025-11-17.xlsx)
- **Stock Data:** 17-Nov-2025 (Stocks-data-IND-17-Nov-2025.xlsx)
- **Forecaster Data:** 21 CSV files with analyst consensus (525 total rows)

To refresh with latest data:
1. Download new XLSX files from Trendlyne web interface
2. Run `python manage.py populate_trendlyne`

## File Locations

### Downloaded XLSX Files
```
/apps/data/tldata/
├── fno_data_2025-11-17.xlsx (3.2 MB)
├── Stocks-data-IND-17-Nov-2025.xlsx (4.4 MB)
└── forecaster/ (21 CSV files)
```

### Converted CSV Files
```
/trendlyne_data/
├── contract_data.csv (4.27 MB)
└── stock_data.csv (5.24 MB)
```

## What's Not Populated Yet

These tables are empty because source files don't exist yet:
- ⚠️ Contract Stock Data (contract_stock_data.csv)
- ⚠️ Option Chains (option_chains.csv)
- ⚠️ Events (events.csv)
- ⚠️ News Articles (news.csv)
- ⚠️ Investor Calls (investor_calls.csv)
- ⚠️ Knowledge Base (knowledge_base.csv)

These will be populated when you download the corresponding data from Trendlyne.

## Troubleshooting

### Issue: "No module named 'openpyxl'"
**Solution:**
```bash
pip install openpyxl
```

### Issue: "File not found" errors
**Solution:** Make sure you have downloaded the latest XLSX files from Trendlyne web interface to `/apps/data/tldata/`

### Issue: "0 records" in database
**Solution:** Run the complete workflow:
```bash
python manage.py populate_trendlyne
```

### Issue: Old data being used
**Solution:**
1. Clear old data: `python manage.py trendlyne_data_manager --clear-database`
2. Populate fresh data: `python manage.py populate_trendlyne`

## Next Steps

1. ✅ Data is now populated in database
2. ✅ You can query ContractData and TLStockData models
3. ✅ Run `python manage.py populate_trendlyne` after each new download

---

**Fixed on:** 2025-11-17
**Records Populated:** 22,971 (17,467 contracts + 5,504 stocks)
