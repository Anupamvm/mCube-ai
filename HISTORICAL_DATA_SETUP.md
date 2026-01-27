# Historical Data API - Setup Complete ✓

This document summarizes the newly created Historical Data API for fetching and storing OHLC data from Breeze API.

## What Was Created

### 1. Database Model
**File:** `apps/brokers/models.py` (line 462+)

**Model:** `HistoricalPrice`
- Stores OHLC data (Open, High, Low, Close, Volume, Open Interest)
- Supports stocks, futures, and options
- Automatically replaces old data on fetch (no duplicates)
- Indexed for fast queries

**Key Methods:**
- `replace_data()` - Delete old data and save fresh data
- `get_latest_data()` - Retrieve stored candles from database

### 2. API Endpoints
**File:** `apps/trading/api/historical_data_views.py`

#### Endpoint 1: Fetch and Save Historical Data
- **URL:** `/trading/api/get-breeze-historical-data/`
- **Methods:** POST, GET
- **Purpose:** Fetch data from Breeze API and save to database

#### Endpoint 2: Retrieve Stored Data
- **URL:** `/trading/api/get-stored-historical-data/`
- **Methods:** GET
- **Purpose:** Get previously fetched data from database

### 3. Documentation
**File:** `apps/trading/api/HISTORICAL_DATA_API_USAGE.md`
- Complete usage guide with examples
- All parameters documented
- Error handling guide
- Python and cURL examples

### 4. Test Suite
**File:** `scripts/test/test_historical_data_api.py`
- Comprehensive test script
- Tests stocks, futures, and options data fetching
- Error handling validation
- Easy to run and debug

---

## Next Steps - Setup Instructions

### Step 1: Create Database Migration

```bash
cd /Users/anupammangudkar/Projects/mCube-ai
python manage.py makemigrations trading
```

Expected output:
```
Migrations for 'trading':
  apps/trading/migrations/XXXX_historicaldata.py
    - Create model HistoricalPrice
```

### Step 2: Apply Migration

```bash
python manage.py migrate trading
```

Expected output:
```
Running migrations:
  Applying trading.XXXX_historicaldata... OK
```

### Step 3: Verify Installation

Check that the table was created:
```bash
python manage.py shell
```

In the shell:
```python
from apps.brokers.models import HistoricalPrice
print("Model loaded successfully!")
HistoricalPrice.objects.count()  # Should return 0
```

### Step 4: Test the API

Run the test suite:
```bash
python scripts/test/test_historical_data_api.py
```

This will test:
- Stock data fetching (ITC - NSE)
- Futures data fetching (NIFTY FUT)
- Options data fetching (NIFTY CE)
- Retrieving stored data
- Error handling

---

## Quick Start Examples

### Example 1: Fetch Stock Data (Python)

```python
import requests

url = "http://localhost:8000/trading/api/get-breeze-historical-data/"
data = {
    "stock_code": "ITC",
    "exchange_code": "NSE",
    "from_date": "2025-01-01",
    "to_date": "2025-01-23",
    "interval": "1day"
}

response = requests.post(url, json=data)
result = response.json()

if result['success']:
    print(f"✓ Saved {result['data']['created_count']} candles")
else:
    print(f"✗ Error: {result['error']}")
```

### Example 2: Fetch Futures Data

```python
data = {
    "stock_code": "NIFTY",
    "exchange_code": "NFO",
    "product_type": "futures",
    "expiry_date": "2025-01-30",
    "from_date": "2025-01-20",
    "to_date": "2025-01-23",
    "interval": "5minute"
}

response = requests.post(url, json=data)
```

### Example 3: Fetch Options Data

```python
data = {
    "stock_code": "NIFTY",
    "exchange_code": "NFO",
    "product_type": "options",
    "expiry_date": "2025-01-30",
    "strike_price": 24500,
    "right": "call",
    "from_date": "2025-01-20",
    "to_date": "2025-01-23",
    "interval": "1minute"
}

response = requests.post(url, json=data)
```

### Example 4: Using cURL

```bash
curl -X POST http://localhost:8000/trading/api/get-breeze-historical-data/ \
  -H "Content-Type: application/json" \
  -d '{
    "stock_code": "ITC",
    "from_date": "2025-01-01",
    "to_date": "2025-01-23",
    "interval": "1day"
  }'
```

---

## API Parameters Reference

### Required Parameters (All Types)
- `stock_code` - Stock/instrument code (e.g., "ITC", "NIFTY")
- `from_date` - Start date (YYYY-MM-DD format)
- `to_date` - End date (YYYY-MM-DD format)

### Optional Parameters (Defaults)
- `exchange_code` - Default: "NSE" (also: "NFO", "BSE")
- `interval` - Default: "1day" (also: "1minute", "5minute", "30minute")
- `product_type` - Default: "cash" (also: "futures", "options", "btst", "margin")

### F&O Parameters (Required when product_type is futures/options)
- `expiry_date` - Expiry date (YYYY-MM-DD format)
- `strike_price` - Strike price (required for options only)
- `right` - "call", "put", or "others" (required for options only)

---

## Response Format

### Success Response
```json
{
  "success": true,
  "message": "Successfully fetched and saved 100 candles for ITC NSE",
  "data": {
    "instrument": "ITC NSE",
    "stock_code": "ITC",
    "exchange_code": "NSE",
    "product_type": "cash",
    "interval": "1day",
    "deleted_count": 95,
    "created_count": 100,
    "total_candles": 100,
    "candles": [...],
    "date_range": {
      "first": "2025-01-01 09:21:00",
      "last": "2025-01-23 15:30:00"
    }
  }
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error message",
  "details": "Additional context about the error"
}
```

---

## Important Notes

1. **Data Replacement:** The API deletes all existing data for the instrument before saving fresh data. This prevents duplicates.

2. **Market Hours:** Historical data is only available during market hours (9:15 AM - 3:30 PM IST).

3. **Authentication:** All endpoints require user authentication (login_required).

4. **Breeze Session:** Ensure your Breeze session token is valid. Tokens expire daily.

5. **Date Limits:** For minute intervals, maximum 365 days allowed.

---

## Troubleshooting

### Issue: "Breeze authentication failed"
**Solution:** Refresh your Breeze session token at `/brokers/breeze/login/`

### Issue: "No data available"
**Possible Reasons:**
- Market is closed
- Invalid instrument/expiry combination
- No trades occurred for the instrument

### Issue: Migration errors
**Solution:**
```bash
python manage.py migrate --fake trading zero
python manage.py migrate trading
```

### Issue: "Missing required parameter"
**Solution:** Check the API documentation for required parameters based on product_type

---

## File Locations

```
apps/trading/
├── models.py                              # HistoricalPrice model (line 462+)
├── api/
│   ├── historical_data_views.py          # API endpoints
│   ├── HISTORICAL_DATA_API_USAGE.md      # Detailed documentation
│   └── __init__.py                        # Exports (updated)
├── urls.py                                # URL routes (updated)

scripts/test/
└── test_historical_data_api.py           # Test suite

HISTORICAL_DATA_SETUP.md                   # This file
```

---

## API Integration in Your Code

### Django View Integration

```python
from apps.brokers.models import HistoricalPrice

# Get latest 100 daily candles for ITC
candles = HistoricalPrice.get_latest_data(
    stock_code='ITC',
    exchange_code='NSE',
    product_type='cash',
    interval='1day',
    limit=100
)

for candle in candles:
    print(f"{candle.datetime}: {candle.close}")
```

### Programmatic Data Fetching

```python
from apps.brokers.models import HistoricalPrice

# Fetch and save data
deleted, created = HistoricalPrice.replace_data(
    stock_code='ITC',
    exchange_code='NSE',
    product_type='cash',
    interval='1day',
    data_points=api_response['Success']
)

print(f"Replaced {deleted} old records with {created} new records")
```

---

## Support & Documentation

- **Full API Documentation:** `apps/trading/api/HISTORICAL_DATA_API_USAGE.md`
- **Test Script:** `scripts/test/test_historical_data_api.py`
- **Model Documentation:** See docstrings in `apps/brokers/models.py`

---

## Summary

✓ Database model created and ready
✓ Two API endpoints implemented
✓ Comprehensive error handling
✓ Full documentation provided
✓ Test suite included
✓ URL routes configured

**Next:** Run migrations and test the API!

```bash
# 1. Create and apply migrations
python manage.py makemigrations trading
python manage.py migrate trading

# 2. Test the API
python scripts/test/test_historical_data_api.py

# 3. Start using the API!
```

Enjoy your new Historical Data API! 🚀
