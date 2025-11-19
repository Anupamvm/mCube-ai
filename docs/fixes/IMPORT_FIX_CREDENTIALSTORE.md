# CredentialStore Import Fix

## Error
```
ImportError: cannot import name 'CredentialStore' from 'apps.brokers.models'
```

## Root Cause
Three issues with the Neo API credential access:

1. **Wrong import path**: Was importing from `apps.brokers.models` instead of `apps.core.models`
2. **Wrong service name**: Was using `'kotak_neo'` instead of `'kotakneo'`
3. **Wrong field name**: Was using `access_token` instead of `session_token`

## Correct Usage

### Import Path
```python
# WRONG
from apps.brokers.models import CredentialStore

# CORRECT
from apps.core.models import CredentialStore
```

### Service Name
```python
# WRONG
neo_creds = CredentialStore.objects.filter(service='kotak_neo').first()

# CORRECT
neo_creds = CredentialStore.objects.filter(service='kotakneo').first()
```

### Field Name
```python
# WRONG
if neo_creds and neo_creds.access_token:
    ...

# CORRECT
if neo_creds and neo_creds.session_token:
    ...
```

### Neo API Initialization
```python
# CORRECT - Use session_token from DB as access_token parameter to NeoAPI
neo = NeoAPI(
    access_token=neo_creds.session_token,
    environment='prod'
)
```

## Files Fixed

### `/apps/trading/services/strangle_position_sizer.py`

**Lines 55-67**: Fixed `get_neo_margin()` method
- Corrected import path
- Fixed service name from 'kotak_neo' to 'kotakneo'
- Fixed field from `access_token` to `session_token`
- Fixed NeoAPI initialization

**Lines 122-134**: Fixed `get_neo_margin_for_strangle()` method
- Same corrections as above

## CredentialStore Model Reference

**Location**: `apps/core/models.py`

**Service Choices**:
- `'breeze'` - ICICI Breeze
- `'trendlyne'` - Trendlyne
- `'kotakneo'` - Kotak Neo (note: one word, no underscore)
- `'telegram'` - Telegram Bot
- `'other'` - Other

**Fields**:
- `api_key` - API key
- `api_secret` - API secret
- `session_token` - Session/access token (this is what Neo stores)

## Testing

The position sizing calculation should now work without import errors. Next test will verify:
1. No import error
2. Placeholder margin used if Neo not configured
3. Actual margin fetched if Neo credentials available
4. Proper lot calculation (should show 1+ lots, not 0)
