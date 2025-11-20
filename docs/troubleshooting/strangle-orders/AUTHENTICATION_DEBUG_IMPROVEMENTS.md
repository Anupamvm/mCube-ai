# Authentication & Session Debugging Improvements

**Date:** November 20, 2025
**Issue:** Invalid JWT token error during order placement
**Status:** 🔍 DEBUGGING

---

## Error Observed

```
INFO: Kotak Neo order response: {
    'code': '900901',
    'message': 'Invalid Credentials',
    'description': 'Invalid JWT token. Make sure you have provided the correct security credentials'
}
```

---

## Root Cause Analysis

### Problem Chain

1. **Session Reuse** - Using single session for all orders ✅
2. **Token Issue** - Session token (JWT) is invalid ❌
3. **Authentication Flow** - `tools.neo.NeoAPI` → `neo_api_client` → JWT

### Why JWT is Invalid

Most likely causes:
1. **Stale OTP** - `session_token` in database is old
2. **Expired Session** - JWT token expired between login and order
3. **Wrong Credentials** - PAN/Password incorrect
4. **2FA Failure** - OTP verification failed silently

---

## Improvements Made

### 1. Better Error Handling

**File:** `apps/brokers/integrations/kotak_neo.py`
**Lines:** 446-461

**Before:**
```python
error_msg = response.get('errMsg', 'Unknown error')
```

**After:**
```python
# Handle different error response formats
if response:
    error_msg = response.get('errMsg') or response.get('message') or response.get('description', 'Unknown error')
    error_code = response.get('stCode') or response.get('code', '')
    full_error = f"[{error_code}] {error_msg}" if error_code else error_msg
else:
    full_error = 'No response from API'
```

**Benefits:**
- ✅ Catches `'message'` field (not just `'errMsg'`)
- ✅ Includes error code for debugging
- ✅ Shows full error context

### 2. Enhanced Authentication Logging

**File:** `apps/brokers/integrations/kotak_neo.py`
**Lines:** 105-115

**Added:**
```python
login_result = neo_wrapper.login()
logger.info(f"Neo login result: {login_result}, session_active: {neo_wrapper.session_active}")

if login_result and neo_wrapper.session_active:
    logger.info("✅ Neo API authentication successful")
    logger.info(f"Returning Neo client: {neo_wrapper.neo}")
    return neo_wrapper.neo
else:
    logger.error(f"❌ Neo API login failed: result={login_result}, session_active={neo_wrapper.session_active}")
    raise ValueError("Neo API login failed")
```

**What It Shows:**
- Whether `login()` returned True/False
- Whether `session_active` flag is set
- The actual client object being returned

### 3. Session Reuse for Lot Size Lookup

**File:** `apps/brokers/integrations/kotak_neo.py`
**Lines:** 481, 626

**Change:**
```python
# Before: Creates new session
def get_lot_size_from_neo(trading_symbol: str) -> int:
    client = _get_authenticated_client()  # New session

# After: Reuses existing session
def get_lot_size_from_neo(trading_symbol: str, client=None) -> int:
    if client is None:
        client = _get_authenticated_client()
    # ...

# Usage in batch function:
client = _get_authenticated_client()
lot_size = get_lot_size_from_neo(call_symbol, client=client)  # Reuse
```

**Benefits:**
- ✅ Only one authentication per batch
- ✅ Consistent session across lot size lookup and orders
- ✅ Reduces potential for token mismatch

---

## Expected Logs (Next Test)

### Successful Authentication:
```
INFO: Using NeoAPI wrapper from tools.neo for authentication
INFO: Neo login result: True, session_active: True
INFO: ✅ Neo API authentication successful
INFO: Returning Neo client: <neo_api_client.neo_api.NeoAPI object at 0x...>
INFO: ✅ Single Neo API session established for all orders
INFO: Using lot size: 75 for NIFTY25NOV27050CE
INFO: Batch 1/9: Placing 20 lots (1500 qty)
INFO: ⚡ Placing CALL and PUT orders in parallel...
INFO: Kotak Neo order response: {'stat': 'Ok', 'nOrdNo': '...'}
```

### Failed Authentication:
```
INFO: Using NeoAPI wrapper from tools.neo for authentication
INFO: Neo login result: False, session_active: False
ERROR: ❌ Neo API login failed: result=False, session_active=False
ERROR: Failed to establish Neo session: Neo API login failed
```

### Invalid Token After Login:
```
INFO: Neo login result: True, session_active: True
INFO: ✅ Neo API authentication successful
INFO: ✅ Single Neo API session established for all orders
INFO: Placing Neo order: ...
INFO: Kotak Neo order response: {'code': '900901', 'message': 'Invalid Credentials', ...}
ERROR: ❌ Order placement failed: [900901] Invalid Credentials
```

---

## Debugging Steps

### 1. Check Database Credentials

```sql
SELECT username, api_key, session_token, updated_at
FROM core_credentialstore
WHERE service='kotakneo';
```

**Verify:**
- `username` = PAN card number
- `password` = Neo trading password
- `session_token` = Current OTP/TOTP (refreshes every 30s)
- `api_key` = Consumer Key
- `api_secret` = Consumer Secret

### 2. Check OTP Freshness

Neo uses TOTP (Time-based OTP) that changes every 30 seconds.

**Problem:** If `session_token` in DB is >30s old, it's invalid.

**Solution:** Update with fresh TOTP before placing orders:
```python
# In Neo login, refresh from TOTP source
import pyotp
totp = pyotp.TOTP(secret_key)
fresh_otp = totp.now()
```

### 3. Test Authentication Separately

```python
python manage.py shell

from tools.neo import NeoAPI
neo = NeoAPI()
result = neo.login()
print(f"Login result: {result}")
print(f"Session active: {neo.session_active}")

# Try an API call
margin = neo.get_margin()
print(f"Margin call result: {margin}")
```

### 4. Check JWT Token

After login, the Neo client has an access token:
```python
# In tools/neo.py after login
if session_response and session_response.get('data'):
    access_token = session_response['data'].get('access_token')
    print(f"Access token received: {access_token[:50]}...")
```

---

## Likely Issues & Fixes

### Issue 1: Stale TOTP in Database

**Symptom:** Login returns `False` or 2FA fails

**Check:**
```python
from apps.core.models import CredentialStore
creds = CredentialStore.objects.filter(service='kotakneo').first()
print(f"Session token: {creds.session_token}")
print(f"Updated: {creds.updated_at}")

# Time difference
from datetime import datetime, timezone
age = datetime.now(timezone.utc) - creds.updated_at
print(f"Token age: {age.total_seconds()} seconds")
```

**Fix:** If age > 30s, token is stale. Need to refresh from TOTP generator.

### Issue 2: Wrong PAN/Password

**Symptom:** First login step fails

**Check:** Verify username field contains PAN (not mobile):
```python
creds = CredentialStore.objects.filter(service='kotakneo').first()
print(f"Username (PAN): {creds.username}")
print(f"Should be PAN format: AAAAA1234A")
```

**Fix:** Update database with correct PAN in username field.

### Issue 3: Environment Mismatch

**Symptom:** Login succeeds but API calls fail

**Check:** Ensure `environment='prod'` in tools/neo.py:
```python
self.neo = KotakNeoAPI(
    consumer_key=self.consumer_key,
    consumer_secret=self.consumer_secret,
    environment='prod'  # Must be 'prod' not 'uat'
)
```

### Issue 4: JWT Token Expires Quickly

**Symptom:** Login succeeds, first batch works, later batches fail

**Problem:** JWT token has short expiry (e.g., 5 minutes)

**Solution:** Refresh token before it expires:
```python
# Check token age before each batch
if time_since_login > 4 * 60:  # 4 minutes
    logger.info("Token nearing expiry, refreshing...")
    client = _get_authenticated_client()
```

---

## Current Status

### What We Fixed:
✅ Better error messages (shows actual error code/message)
✅ Enhanced authentication logging
✅ Session reuse across lot size lookup and orders
✅ Parallel order execution
✅ Single authentication per batch

### What We Need:
⏳ Fresh TOTP in database
⏳ Verify PAN/password are correct
⏳ Test during market hours
⏳ Check JWT token validity duration

---

## Next Steps

1. **Verify Credentials:**
   ```bash
   python manage.py shell
   from apps.core.models import CredentialStore
   creds = CredentialStore.objects.filter(service='kotakneo').first()
   print(f"PAN: {creds.username}")
   print(f"OTP age: {datetime.now(timezone.utc) - creds.updated_at}")
   ```

2. **Update TOTP if Stale:**
   - Get fresh TOTP from Neo mobile app or TOTP generator
   - Update in database:
   ```python
   creds.session_token = "123456"  # Fresh TOTP
   creds.save()
   ```

3. **Test Authentication:**
   ```bash
   python test_neo_order_api.py
   ```

4. **Retry Order Placement:**
   - With fresh credentials
   - Check logs for authentication status
   - Verify JWT token is valid

---

## Files Modified

1. **kotak_neo.py** (Lines 105-115)
   - Added detailed authentication logging
   - Shows login result and session status

2. **kotak_neo.py** (Lines 446-461)
   - Improved error handling
   - Parses multiple error formats
   - Shows error codes

3. **kotak_neo.py** (Lines 481, 626)
   - Added client parameter to get_lot_size_from_neo()
   - Reuses session across lookups and orders

---

## Summary

**Problem:** Invalid JWT token error
**Root Cause:** Most likely stale TOTP (>30s old) in database
**Fixes Applied:** Better logging, error handling, session reuse
**Next:** Update TOTP and re-test

**Status:** 🔍 AWAITING FRESH CREDENTIALS FOR TESTING
