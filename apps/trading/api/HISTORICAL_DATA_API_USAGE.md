# Historical Data API Usage Guide

## Overview

The Historical Data API allows you to fetch OHLC (Open, High, Low, Close) data from Breeze API and store it in the database. It supports stocks, futures, and options data.

## Endpoints

### 1. Fetch and Save Historical Data
**Endpoint:** `/trading/api/get-breeze-historical-data/`
**Methods:** POST, GET
**Authentication:** Required (login_required)

### 2. Retrieve Stored Historical Data
**Endpoint:** `/trading/api/get-stored-historical-data/`
**Methods:** GET
**Authentication:** Required (login_required)

---

## API Parameters

### Required Parameters (All Product Types)

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `stock_code` | string | Stock/instrument code | `"ITC"`, `"NIFTY"`, `"RELIND"` |
| `from_date` | string | Start date (YYYY-MM-DD) | `"2025-01-01"` |
| `to_date` | string | End date (YYYY-MM-DD) | `"2025-01-23"` |

### Optional Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `exchange_code` | string | `"NSE"` | Exchange code: `"NSE"`, `"NFO"`, `"BSE"` |
| `interval` | string | `"1day"` | Candle interval: `"1minute"`, `"5minute"`, `"30minute"`, `"1day"` |
| `product_type` | string | `"cash"` | Product type: `"cash"`, `"futures"`, `"options"`, `"btst"`, `"margin"` |

### F&O Specific Parameters (Required for futures/options)

| Parameter | Type | Required For | Description |
|-----------|------|--------------|-------------|
| `expiry_date` | string | futures, options | Expiry date (YYYY-MM-DD) |
| `strike_price` | float | options | Strike price (e.g., 24500) |
| `right` | string | options | Option type: `"call"`, `"put"`, `"others"` |

---

## Usage Examples

### Example 1: Fetch Stock Data (Cash)

**Request:**
```bash
curl -X POST http://localhost:8000/trading/api/get-breeze-historical-data/ \
  -H "Content-Type: application/json" \
  -d '{
    "stock_code": "ITC",
    "exchange_code": "NSE",
    "from_date": "2025-01-01",
    "to_date": "2025-01-23",
    "interval": "1day"
  }'
```

**Python (using requests):**
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
    print(f"Deleted {result['data']['deleted_count']} old records")
else:
    print(f"✗ Error: {result['error']}")
```

**Response:**
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
    "from_date": "2025-01-01",
    "to_date": "2025-01-23",
    "expiry_date": null,
    "strike_price": null,
    "right": null,
    "deleted_count": 95,
    "created_count": 100,
    "total_candles": 100,
    "candles": [
      {
        "datetime": "2025-01-01 09:21:00",
        "stock_code": "ITC",
        "open": "450.50",
        "high": "452.75",
        "low": "449.25",
        "close": "451.00",
        "volume": "125000",
        "open_interest": null
      }
    ],
    "date_range": {
      "first": "2025-01-01 09:21:00",
      "last": "2025-01-23 15:30:00"
    }
  }
}
```

---

### Example 2: Fetch Futures Data

**Request:**
```bash
curl -X POST http://localhost:8000/trading/api/get-breeze-historical-data/ \
  -H "Content-Type: application/json" \
  -d '{
    "stock_code": "NIFTY",
    "exchange_code": "NFO",
    "product_type": "futures",
    "expiry_date": "2025-01-30",
    "from_date": "2025-01-20",
    "to_date": "2025-01-23",
    "interval": "5minute"
  }'
```

**Python:**
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
result = response.json()
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully fetched and saved 450 candles for NIFTY FUT 2025-01-30",
  "data": {
    "instrument": "NIFTY FUT 2025-01-30",
    "stock_code": "NIFTY",
    "exchange_code": "NFO",
    "product_type": "futures",
    "interval": "5minute",
    "expiry_date": "2025-01-30",
    "deleted_count": 420,
    "created_count": 450,
    "total_candles": 450
  }
}
```

---

### Example 3: Fetch Options Data

**Request:**
```bash
curl -X POST http://localhost:8000/trading/api/get-breeze-historical-data/ \
  -H "Content-Type: application/json" \
  -d '{
    "stock_code": "NIFTY",
    "exchange_code": "NFO",
    "product_type": "options",
    "expiry_date": "2025-01-30",
    "strike_price": 24500,
    "right": "call",
    "from_date": "2025-01-20",
    "to_date": "2025-01-23",
    "interval": "1minute"
  }'
```

**Python:**
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
result = response.json()
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully fetched and saved 1250 candles for NIFTY 2025-01-30 24500.00 CALL",
  "data": {
    "instrument": "NIFTY 2025-01-30 24500.00 CALL",
    "stock_code": "NIFTY",
    "exchange_code": "NFO",
    "product_type": "options",
    "interval": "1minute",
    "expiry_date": "2025-01-30",
    "strike_price": 24500.0,
    "right": "call",
    "deleted_count": 1200,
    "created_count": 1250,
    "total_candles": 1250
  }
}
```

---

### Example 4: Retrieve Stored Data from Database

**Request:**
```bash
curl -X GET "http://localhost:8000/trading/api/get-stored-historical-data/?stock_code=ITC&exchange_code=NSE&interval=1day&limit=50"
```

**Python:**
```python
params = {
    "stock_code": "ITC",
    "exchange_code": "NSE",
    "interval": "1day",
    "limit": 50
}

response = requests.get(
    "http://localhost:8000/trading/api/get-stored-historical-data/",
    params=params
)
result = response.json()

if result['success']:
    candles = result['data']['candles']
    print(f"Retrieved {len(candles)} candles")
    for candle in candles[:5]:
        print(f"{candle['datetime']}: O={candle['open']}, C={candle['close']}")
```

---

## Error Handling

### Common Error Responses

#### 1. Missing Required Parameter
```json
{
  "success": false,
  "error": "Missing required parameter: stock_code",
  "details": "Please provide the stock/instrument code (e.g., ITC, NIFTY)"
}
```

#### 2. Invalid Date Format
```json
{
  "success": false,
  "error": "Invalid date format",
  "details": "Dates must be in YYYY-MM-DD format (e.g., 2025-01-23)"
}
```

#### 3. Invalid Date Range
```json
{
  "success": false,
  "error": "Invalid date range",
  "details": "from_date must be before or equal to to_date"
}
```

#### 4. Missing F&O Parameters
```json
{
  "success": false,
  "error": "Missing required parameter for options: strike_price",
  "details": "Please provide strike_price (e.g., 24500)"
}
```

#### 5. Breeze Authentication Error
```json
{
  "success": false,
  "error": "Breeze authentication failed",
  "details": "Breeze session token not found. Please login to continue."
}
```

#### 6. No Data Available
```json
{
  "success": false,
  "error": "No data available for the specified parameters",
  "details": "The API returned no candles for this time period. This could mean:\n- Market was closed during this period\n- No trades occurred for this instrument\n- Invalid instrument/expiry combination"
}
```

#### 7. Date Range Too Large
```json
{
  "success": false,
  "error": "Date range too large for 1minute interval",
  "details": "Maximum 365 days allowed for minute intervals"
}
```

---

## Important Notes

### 1. Data Replacement Strategy
- The API **deletes all existing data** for the same instrument before saving fresh data
- This ensures you always have the latest data without duplicates
- The response includes both `deleted_count` and `created_count`

### 2. Date Range Limits
- For minute intervals (`1minute`, `5minute`, `30minute`): Maximum 365 days
- For daily interval (`1day`): No specific limit

### 3. Market Hours
- Historical data is only available during market hours: 9:15 AM - 3:30 PM IST
- Outside market hours, you may get empty responses or errors

### 4. Authentication
- All endpoints require user authentication
- Ensure your Breeze session token is valid
- Session tokens expire daily and need to be refreshed

### 5. Product Types
- `cash`: Regular stocks/indices (no expiry needed)
- `futures`: Futures contracts (requires expiry_date)
- `options`: Options contracts (requires expiry_date, strike_price, right)
- `btst`: Buy Today Sell Tomorrow (no expiry needed)
- `margin`: Margin trading (no expiry needed)

---

## Django Integration Example

```python
from apps.trading.api import get_breeze_historical_data, get_stored_historical_data
from django.test import RequestFactory
from django.contrib.auth.models import User

# Create a test request
factory = RequestFactory()
user = User.objects.get(username='your_username')

# Prepare data
data = {
    'stock_code': 'ITC',
    'from_date': '2025-01-01',
    'to_date': '2025-01-23',
    'interval': '1day'
}

# Create POST request
request = factory.post('/api/get-breeze-historical-data/', data=data, content_type='application/json')
request.user = user

# Call the view
response = get_breeze_historical_data(request)
result = response.json()

print(result)
```

---

## Testing with Postman

1. **Set Authentication:**
   - Add your session cookie or authentication token

2. **Create POST Request:**
   - URL: `http://localhost:8000/trading/api/get-breeze-historical-data/`
   - Method: POST
   - Headers: `Content-Type: application/json`
   - Body (raw JSON):
   ```json
   {
     "stock_code": "ITC",
     "from_date": "2025-01-01",
     "to_date": "2025-01-23",
     "interval": "1day"
   }
   ```

3. **Send Request and Check Response**

---

## Best Practices

1. **Always check the response:**
   ```python
   if result['success']:
       # Process data
       candles = result['data']['candles']
   else:
       # Handle error
       print(f"Error: {result['error']}")
   ```

2. **Use appropriate intervals:**
   - Use `1day` for long-term analysis
   - Use `5minute` or `30minute` for intraday analysis
   - Use `1minute` only for short time periods

3. **Handle authentication errors:**
   - Check if Breeze session is valid
   - Refresh token if needed

4. **Validate parameters before sending:**
   - Ensure dates are in correct format
   - Check that F&O parameters are provided when needed
   - Verify date range is reasonable

---

## Support

For issues or questions:
- Check the error message in the `error` and `details` fields
- Verify Breeze session is active
- Ensure market is open when fetching data
- Check logs at `/var/log/mcube/` for detailed error information
