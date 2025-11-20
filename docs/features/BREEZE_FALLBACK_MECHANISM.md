# Breeze API Fallback Mechanism for Instrument Lookup

## Overview

The system now includes an **automatic fallback mechanism** that fetches instrument details from Breeze API when SecurityMaster lookup fails. This ensures orders can always be placed even if the SecurityMaster file is missing or outdated.

## How It Works

### Primary Flow (SecurityMaster)
1. User triggers order placement (e.g., from Manual Triggers page)
2. System attempts to lookup instrument in SecurityMaster file
3. If found → Uses SecurityMaster data (✅ Preferred)
4. Order placed with accurate stock codes and lot sizes

### Fallback Flow (Breeze API)
1. SecurityMaster lookup fails (file missing OR instrument not found)
2. System logs warning and automatically triggers Breeze API fallback
3. Calls `breeze.get_quotes()` to fetch live instrument data
4. Extracts lot size and other details from Breeze response
5. Order placed using Breeze-fetched data

### Order of Operations

```
Order Placement Request
        ↓
Check Cache (6 hours)
        ↓
    [Cache Hit?]
      ↙     ↘
    Yes      No
     ↓        ↓
  Return   SecurityMaster File Exists?
  Cached      ↙           ↘
  Data      Yes            No
             ↓              ↓
      Read SecurityMaster   Breeze Fallback
             ↓              ↓
      [Found?]          get_quotes()
        ↙   ↘              ↓
      Yes    No      Extract lot_size
       ↓      ↓            ↓
    Return  Breeze    Cache & Return
     Data   Fallback
             ↓
        Cache & Return
```

## Key Functions

### `fetch_instrument_from_breeze()`
**Location:** `apps/brokers/utils/security_master.py`

Fetches instrument details directly from Breeze API.

**Signature:**
```python
def fetch_instrument_from_breeze(
    symbol: str,
    expiry_date: str,
    instrument_type: str = 'futures',
    strike_price: Optional[float] = None,
    option_type: Optional[str] = None
) -> Optional[Dict]
```

**Parameters:**
- **futures:** `fetch_instrument_from_breeze('SBIN', '30-Dec-2025', 'futures')`
- **options:** `fetch_instrument_from_breeze('NIFTY', '27-Nov-2025', 'options', 24500, 'CE')`

**Returns:**
```python
{
    'token': '',
    'short_name': 'SBIN',  # Uses symbol as fallback
    'lot_size': 750,       # From Breeze quote
    'exchange_code': 'SBIN',
    'company_name': 'STATE BANK OF INDIA',
    'expiry_date': '30-Dec-2025',
    'tick_size': 0.05,
    'base_price': 900.0,   # Current LTP
    'source': 'breeze_api'  # Identifies data source
}
```

### Updated `get_futures_instrument()`

Now includes `use_breeze_fallback` parameter (default: `True`).

**Example:**
```python
from apps.brokers.utils.security_master import get_futures_instrument

# Auto-fallback enabled (default)
instrument = get_futures_instrument('SBIN', '30-Dec-2025')

# Disable fallback (SecurityMaster only)
instrument = get_futures_instrument('SBIN', '30-Dec-2025', use_breeze_fallback=False)
```

## Scenarios

### Scenario 1: SecurityMaster Available & Instrument Found ✅
```
Input: get_futures_instrument('SBIN', '30-Dec-2025')

Flow:
1. SecurityMaster file exists
2. Instrument found in SecurityMaster
3. Returns SecurityMaster data

Result:
{
    'token': '50066',
    'short_name': 'STABAN',
    'lot_size': 750,
    'source': 'security_master'  ← From SecurityMaster
}
```

### Scenario 2: SecurityMaster Missing ⚠️ → Breeze Fallback
```
Input: get_futures_instrument('SBIN', '30-Dec-2025')

Flow:
1. SecurityMaster file NOT found
2. Logs warning: "SecurityMaster file not found"
3. Auto-triggers Breeze fallback
4. Calls breeze.get_quotes(stock_code='SBIN', ...)
5. Extracts lot_size from response

Result:
{
    'token': '',
    'short_name': 'SBIN',
    'lot_size': 750,  ← From Breeze API
    'source': 'breeze_api'  ← Fallback source
}
```

### Scenario 3: Instrument Not in SecurityMaster ⚠️ → Breeze Fallback
```
Input: get_futures_instrument('NEWSTOCK', '30-Dec-2025')

Flow:
1. SecurityMaster file exists
2. Instrument NOT found in SecurityMaster (new listing?)
3. Logs warning: "Instrument not found in SecurityMaster"
4. Auto-triggers Breeze fallback
5. Fetches from Breeze API

Result:
{
    'short_name': 'NEWSTOCK',
    'lot_size': 500,  ← From Breeze
    'source': 'breeze_api'
}
```

### Scenario 4: Both Sources Fail ❌
```
Input: get_futures_instrument('INVALID', '30-Dec-2025')

Flow:
1. SecurityMaster file missing/not found
2. Breeze API also fails (invalid symbol)
3. Logs error with troubleshooting hints

Result: None

Error Logs:
❌ Failed to get instrument from both SecurityMaster and Breeze API
Please either:
  1. Download SecurityMaster: https://...
  2. Ensure Breeze API is authenticated
```

## UI Display

### Success with SecurityMaster (Green Background)
```
✅ Order Placed Successfully!
Order ID: 202511201234567

Order Details:
Symbol: SBIN
Stock Code: STABAN
Quantity: 7500 (10 lots × 750)

📋 Instrument Info (📋 SecurityMaster):
┌────────────────────────────────┐
│ Token: 50066                   │
│ Stock Code: STABAN             │
│ Lot Size: 750                  │
│ Company: STATE BANK OF INDIA   │
└────────────────────────────────┘
```

### Success with Breeze Fallback (Yellow Background)
```
✅ Order Placed Successfully!
Order ID: 202511201234568

Order Details:
Symbol: SBIN
Stock Code: SBIN
Quantity: 7500 (10 lots × 750)

📋 Instrument Info (📡 Breeze API):
┌───────────────────────────────────────┐
│ ⚠️ Fetched from Breeze API            │
│    (SecurityMaster unavailable)       │
│                                       │
│ Token:                                │
│ Stock Code: SBIN                      │
│ Lot Size: 750                         │
│ Company: STATE BANK OF INDIA          │
└───────────────────────────────────────┘
```

## Advantages

### 1. **Resilience**
- Orders never fail due to missing SecurityMaster file
- System auto-recovers from SecurityMaster issues
- Reduces dependency on daily file downloads

### 2. **New Listings**
- Automatically handles newly listed instruments
- No waiting for SecurityMaster updates
- Breeze has live data for all tradable instruments

### 3. **Zero Configuration**
- Fallback enabled by default
- Works automatically without code changes
- Transparent to end users

### 4. **Caching**
- Both SecurityMaster and Breeze results cached (6 hours)
- Reduces API calls
- Fast subsequent lookups

### 5. **Transparency**
- UI shows data source (SecurityMaster vs Breeze)
- Different background colors for easy identification
- Logs indicate which source was used

## Logging

### SecurityMaster Success
```
INFO Reading SecurityMaster for SBIN futures expiring 30-Dec-2025
INFO ✅ Found in SecurityMaster: SBIN futures - Token=50066, StockCode=STABAN, LotSize=750
```

### Breeze Fallback Triggered
```
WARNING SecurityMaster file not found at /path/to/file
INFO ⚠️  SecurityMaster lookup failed, fetching from Breeze API as fallback...
INFO Fetching instrument from Breeze API: SBIN 30-Dec-2025 futures
DEBUG Breeze API quote params: {'stock_code': 'SBIN', ...}
INFO ✅ Fetched from Breeze: SBIN -> lot_size=750
INFO ✅ Fetched from Breeze API fallback: SBIN futures - LotSize=750
```

### Complete Failure
```
ERROR ❌ Failed to get instrument from both SecurityMaster and Breeze API for SBIN 30-Dec-2025
ERROR Please either:
ERROR   1. Download SecurityMaster: https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip
ERROR   2. Ensure Breeze API is authenticated and accessible
```

## Configuration

### Disable Fallback (Not Recommended)
```python
# In apps/trading/api_views.py
instrument = get_futures_instrument(
    symbol,
    expiry_date,
    use_breeze_fallback=False  # Disable fallback
)
```

### Custom Cache Timeout
```python
# In apps/brokers/utils/security_master.py
CACHE_TIMEOUT = 3 * 60 * 60  # 3 hours instead of 6
```

## Testing

### Test SecurityMaster Path
```python
from apps.brokers.utils.security_master import get_futures_instrument

# Should use SecurityMaster
instrument = get_futures_instrument('SBIN', '30-Dec-2025')
assert instrument['source'] == 'security_master'
print(f"Stock Code: {instrument['short_name']}")  # STABAN
```

### Test Breeze Fallback
```python
from apps.brokers.utils.security_master import get_futures_instrument

# Force fallback by using non-existent path
instrument = get_futures_instrument(
    'SBIN',
    '30-Dec-2025',
    security_master_path='/nonexistent/path'
)
assert instrument['source'] == 'breeze_api'
print(f"Lot Size: {instrument['lot_size']}")  # From Breeze
```

### Test Direct Breeze Fetch
```python
from apps.brokers.utils.security_master import fetch_instrument_from_breeze

instrument = fetch_instrument_from_breeze('SBIN', '30-Dec-2025', 'futures')
print(instrument)
```

## Best Practices

### 1. **Still Download SecurityMaster**
- Fallback is for resilience, not replacement
- SecurityMaster has more accurate stock codes
- Download daily: `15 8 * * * cd ~/Downloads && curl -O https://...`

### 2. **Monitor Logs**
- Check which source is being used
- Investigate if fallback used frequently
- Ensure Breeze API connectivity

### 3. **Cache Awareness**
- 6-hour cache means stale data possible
- Clear cache after SecurityMaster download: `clear_security_master_cache()`
- Consider shorter cache for critical applications

### 4. **Error Handling**
- Always check if `instrument is None`
- Display helpful error messages to users
- Log both SecurityMaster and Breeze failures

## Troubleshooting

### Issue: "Resource not found" from Breeze
**Cause:** Symbol/expiry not valid or market not open

**Solution:**
1. Verify symbol is correct (case-sensitive)
2. Check expiry date format: DD-MMM-YYYY
3. Ensure market is open (9:15 AM - 3:30 PM IST)
4. Verify contract exists on NSE

### Issue: Fallback always used
**Cause:** SecurityMaster file path incorrect

**Solution:**
```bash
# Check file exists
ls -l /Users/anupammangudkar/Downloads/SecurityMaster/FONSEScripMaster.txt

# If missing, download
cd ~/Downloads
curl -O https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip
unzip -o SecurityMaster.zip -d SecurityMaster/
```

### Issue: Wrong lot sizes
**Cause:** Stale cache or outdated SecurityMaster

**Solution:**
```python
from apps.brokers.utils.security_master import clear_security_master_cache

# Clear cache
clear_security_master_cache()

# Download fresh SecurityMaster
# Then retry order
```

## Related Documentation

- [SecurityMaster Integration](SECURITY_MASTER_INTEGRATION.md) - Main integration guide
- [SecurityMaster Quick Start](../../SECURITY_MASTER_QUICK_START.md) - Setup guide
- [SecurityMaster Usage](../../SECURITY_MASTER_USAGE.md) - Detailed usage

## Summary

The Breeze API fallback mechanism ensures:
- ✅ Orders never fail due to missing SecurityMaster
- ✅ Auto-recovery from file/lookup failures
- ✅ Support for new listings
- ✅ Full transparency via logs and UI
- ✅ Zero configuration required

**Flow:** SecurityMaster (preferred) → Breeze API (fallback) → Error (both failed)
