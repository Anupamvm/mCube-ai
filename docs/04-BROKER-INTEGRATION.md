# Broker Integration

This document covers how to set up and use the ICICI Breeze and Kotak Neo broker APIs.

---

## Overview

mCube integrates with two brokers:

| Broker | Account | Strategy | API |
|--------|---------|----------|-----|
| **Kotak Neo** | Rs 6 Cr | Options (Strangle) | REST + WebSocket |
| **ICICI Breeze** | Rs 1.2 Cr | Futures | REST |

---

## Getting API Credentials

### ICICI Breeze API

1. Go to https://api.icicidirect.com
2. Sign in with your ICICI Direct account
3. Navigate to API Console
4. Create a new application to get:
   - **API Key**: Your application's unique identifier
   - **API Secret**: Secret for authentication

### Kotak Neo API (v2)

1. Go to https://api.kotakneo.com
2. Sign in with your Kotak Securities account
3. Navigate to API Management
4. Create a new API app to get:
   - **Consumer Key**: Application ID (no Consumer Secret needed in v2)
5. Register for TOTP at https://www.kotakneo.com/platform/kotak-neo-trade-api/totp-registration/
   - This is separate from any app-level TOTP you may already have
6. Keep ready your trading credentials:
   - **UCC**: Unique Client Code (from Kotak account)
   - **Mobile Number**: Account login mobile
   - **TOTP Secret**: From TOTP registration (used for automated login)
   - **MPIN**: Trading PIN for 2FA validation

---

## Setting Up Credentials

### Method 1: Management Commands (Recommended)

```bash
# Setup ICICI Breeze
python manage.py setup_credentials --setup-breeze

# Setup Kotak Neo
python manage.py setup_credentials --setup-kotakneo

# Setup Trendlyne (for market data)
python manage.py setup_credentials --setup-trendlyne

# Verify setup
python manage.py setup_credentials --list
python manage.py setup_credentials --status
```

### Method 2: Django Shell

```python
python manage.py shell

from apps.core.models import CredentialStore

# Add Breeze credentials
CredentialStore.objects.create(
    service='breeze',
    name='breeze_prod',
    api_key='YOUR_BREEZE_API_KEY',
    api_secret='YOUR_BREEZE_API_SECRET',
    session_token='YOUR_SESSION_TOKEN'  # Optional
)

# Add Kotak Neo v2 credentials
CredentialStore.objects.create(
    service='kotakneo',
    name='kotakneo_prod',
    api_key='YOUR_CONSUMER_KEY',
    # api_secret not needed in v2
    username='9999999999',       # Mobile number
    neo_password='YOUR_MPIN',    # MPIN for 2FA validation
    ucc='YOUR_UCC',              # Unique Client Code
    totp_secret='YOUR_TOTP_SECRET',  # For automated TOTP generation
    mobile_number='9999999999',  # Mobile number (also stored separately)
    pan='ABCDE1234F'             # Optional
)
```

### Method 3: Django Admin

1. Visit http://localhost:8000/admin/
2. Go to Core > Credential stores
3. Add credentials for each service

---

## Testing Connections

```bash
# Test ICICI Breeze
python manage.py setup_credentials --test-breeze

# Test Kotak Neo
python manage.py setup_credentials --test-kotakneo
```

Or in Django shell:

```python
python manage.py shell

# Test Breeze
from apps.brokers.integrations.breeze import get_breeze_client
breeze = get_breeze_client()
print(breeze.get_funds())

# Test Kotak Neo
from tools.neo import NeoAPI
neo = NeoAPI()
neo.login()
print(neo.get_available_margin())
neo.logout()
```

---

## Using the Broker APIs

### Factory Pattern (Recommended)

```python
from apps.brokers.interfaces import BrokerFactory

# Get broker instance
broker = BrokerFactory.get_broker('breeze')  # or 'kotakneo'

# Login
broker.login()

# Operations
margin = broker.get_available_margin()
positions = broker.get_positions()

# Logout
broker.logout()
```

### Direct ICICI Breeze Usage

```python
from apps.brokers.integrations.breeze import (
    get_breeze_client,
    BreezeAPIClient,
    get_nfo_margin
)

# Get raw Breeze client
breeze = get_breeze_client()

# Get margin
funds = breeze.get_funds()
margin = get_nfo_margin()

# Get positions
positions = breeze.get_portfolio_positions()

# Using BreezeAPIClient for order placement
client = BreezeAPIClient()

# Place futures order
order_result = client.place_futures_order(
    symbol='NIFTY',
    direction='buy',
    quantity=1,  # in lots
    order_type='market'
)

# Place strangle order
strangle_result = client.place_strangle_order(
    symbol='NIFTY',
    call_strike=24500,
    put_strike=24000,
    quantity=1,
    expiry='27-NOV-2025'
)
```

### Direct Kotak Neo Usage (v2)

```python
from tools.neo import NeoAPI

# Initialize (no network calls on init)
api = NeoAPI()

# Login — uses TOTP + MPIN (no OTP needed)
# Auth flow: totp_login(mobile, ucc, totp) → totp_validate(mpin)
# Session persisted via base_url + data_center in CredentialStore
api.login()

# Get margin
margin = api.get_available_margin()

# Get positions
positions = api.get_positions()

# Search for symbol (v2 returns list directly, not {'data': [...]})
results = api.search_scrip(symbol='NIFTY', exchange='NSE')

# Get quotes (v2 returns list directly, uses pSymbol as instrument_token)
# instrument_tokens format: [{"exchange_segment": "nse_fo", "instrument_token": "2885"}]
quote = api.get_quote('NIFTY')

# Place order (with automatic retry — March 2026)
order_id = api.place_order(
    symbol='NIFTY25NOV20000CE',
    action='B',           # 'B' for BUY, 'S' for SELL
    quantity=1,
    order_type='MKT',     # 'MKT' or 'L' (LIMIT)
    price=0,
    exchange='NFO',
    product='NRML',
    is_exit=False,        # Set True for exit orders (URGENT alert on failure)
    max_retries=3,        # Retries with exponential backoff (1s, 2s, 4s)
)

# Logout
api.logout()
```

> **Note:** Neo v2 auto-login is limited to **one attempt per day** per broker to prevent
> account blocking. Session is restored from saved `base_url` + `data_center` when possible.
> If `base_url` is missing, a fresh login is forced.

**Order Retry & Safety (March 2026):**
- `place_order()` retries up to 3 times with exponential backoff (1s, 2s, 4s)
- **Auth errors**: Session cleared, re-login attempted, order retried
- **Transient errors** (timeout, 500, connection): Retried with backoff
- **Deterministic errors** (insufficient margin, invalid symbol): No retry
- **`is_exit=True`**: If all retries exhausted, sends URGENT Telegram alert with exact order details for manual execution
- **HTTP timeouts**: All REST calls use `timeout=(5, 30)` — 5s connect, 30s read (prevents worker starvation)

---

## Common Operations

### Check Margin

```python
# ICICI Breeze
from apps.brokers.integrations.breeze import get_nfo_margin
margin_data = get_nfo_margin()
available = margin_data.get('cash_limit', 0)

# Kotak Neo
from tools.neo import NeoAPI
api = NeoAPI()
api.login()
margin = api.get_available_margin()
```

### Get Positions

```python
# ICICI Breeze
breeze = get_breeze_client()
positions = breeze.get_portfolio_positions()

# Kotak Neo
api = NeoAPI()
api.login()
positions = api.get_positions()
```

### Place Market Order

```python
# ICICI Breeze
client = BreezeAPIClient()
order_id = client.place_futures_order(
    symbol='RELIANCE',
    direction='buy',
    quantity=1,
    order_type='market'
)

# Kotak Neo
api = NeoAPI()
api.login()
order_id = api.place_order(
    symbol='RELIANCE-EQ',
    action='B',
    quantity=1,
    order_type='MKT'
)
```

### Get Quote

```python
# ICICI Breeze
breeze = get_breeze_client()
quote = breeze.get_quotes(
    stock_code='RELIANCE',
    exchange_code='NSE'
)

# Kotak Neo (instrument_token is a numeric ID, not symbol name)
api = NeoAPI()
api.login()
quote = api.get_quote(instrument_token='2885', exchange='NSE')
ltp = quote['ltp']
```

### Get Option Chain

```python
# ICICI Breeze
breeze = get_breeze_client()
chain = breeze.get_option_chain_quotes(
    stock_code='NIFTY',
    exchange_code='NFO',
    expiry_date='27-Nov-2025'
)
```

---

## Credential Storage Model

```python
class CredentialStore(models.Model):
    SERVICE_CHOICES = [
        ('breeze', 'ICICI Breeze'),
        ('trendlyne', 'Trendlyne'),
        ('kotakneo', 'Kotak Neo'),
        ('telegram', 'Telegram Bot'),
        ('gnewsio', 'GNews.io'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=100)
    service = models.CharField(choices=SERVICE_CHOICES)

    # API credentials
    api_key = models.CharField()
    api_secret = models.CharField()
    session_token = models.CharField()

    # Username/password credentials
    username = models.CharField()
    password = models.CharField()

    # Kotak Neo specific
    neo_password = models.CharField()        # MPIN (6-digit)
    pan = models.CharField()                 # Legacy v1 — no longer used
    sid = models.CharField()                 # Legacy v1 — no longer used

    # Kotak Neo v2 fields
    ucc = models.CharField()                 # Unique Client Code
    totp_secret = models.CharField()         # TOTP secret for automated login
    mobile_number = models.CharField()       # Mobile number
    neo_base_url = models.URLField()         # API base URL (from totp_validate response)
    neo_data_center = models.CharField()     # Data center (from totp_validate response)
    neo_edit_token = models.TextField()      # Edit token for session
    neo_edit_sid = models.CharField()        # Edit SID for session
    neo_server_id = models.CharField()       # Server ID for session

    # Auto-login tracking (one attempt per day per broker)
    auto_login_status = models.CharField()   # none|in_progress|success|failed
    auto_login_date = models.DateField()     # Date of last auto-login attempt

    created_at = models.DateTimeField(auto_now_add=True)
    last_session_update = models.DateTimeField()
```

### Field Mapping

| Purpose | ICICI Breeze | Kotak Neo v2 |
|---------|--------------|--------------|
| App ID | `api_key` | `api_key` (Consumer Key) |
| App Secret | `api_secret` | *(not needed in v2)* |
| Session | `session_token` | `neo_edit_token` + `neo_edit_sid` |
| Login ID | - | `mobile_number` |
| UCC | - | `ucc` |
| TOTP Secret | - | `totp_secret` |
| Trading PIN | - | `neo_password` (MPIN) |
| API Base URL | - | `neo_base_url` (required for all v2 API calls) |
| Data Center | - | `neo_data_center` |
| Auto-Login | - | `auto_login_status` + `auto_login_date` |

---

## Error Handling

```python
try:
    api = NeoAPI()
    api.login()

    if not api.check_margin_sufficient(50000):
        raise ValueError("Insufficient margin")

    # Entry order — retries on transient errors
    order_id = api.place_order('RELIANCE-EQ', 'B', 1, 'MKT')

    # Exit order — sends URGENT alert if all retries fail
    exit_id = api.place_order('RELIANCE-EQ', 'S', 1, 'MKT', is_exit=True)

except Exception as e:
    print(f"Trading error: {e}")
    # Log error, send alert

finally:
    api.logout()
```

---

## Session Management

### Session Expiry

- Session tokens expire after inactivity (typically daily)
- Breeze: Uses Selenium + Telegram OTP flow for auto-login
- Kotak Neo v2: Uses TOTP + MPIN (no OTP needed, fully automated)

### Auto-Login Safety (One Attempt Per Day)

To prevent account blocking from repeated failed login attempts:
- Each broker gets **one auto-login attempt per day**
- Tracked via `auto_login_status` (none → in_progress → success/failed)
- Reset daily via `auto_login_date` comparison
- Helpers in `apps/brokers/utils/auth_manager.py`:
  - `can_attempt_auto_login(service)` — check if attempt allowed
  - `mark_auto_login_started(service)` — mark in-progress
  - `mark_auto_login_success(service)` / `mark_auto_login_failed(service)`
  - `reset_auto_login_status(service)` — manual reset

### Breeze Session

```python
# Auto-login with Selenium + Telegram OTP
from apps.brokers.services.breeze_session import BreezeSessionManager

manager = BreezeSessionManager()  # Singleton
client = manager.get_client()     # Auto-refreshes if needed

# Lock mechanism prevents concurrent logins:
# - breeze_auto_login_lock in NseFlag (300s expiry)
# - validate_existing_token() creates BreezeConnect directly (no recursion)
```

### Kotak Neo v2 Session

```python
from tools.neo import NeoAPI

api = NeoAPI()
api.login()  # Tries session restore first, then fresh login

# Session restoration:
# 1. Checks saved base_url + data_center in CredentialStore
# 2. If base_url missing → forces fresh login
# 3. Fresh login: totp_login() → totp_validate() → save session
# 4. Rate limiting: max 3 attempts with 10s delay between retries
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Credentials not found" | Run `python manage.py setup_credentials --setup-breeze` |
| Login fails | Verify API key/secret are correct |
| "Session expired" | Re-run credential setup or clear session_token |
| "Invalid symbol" | Use exact instrument name (e.g., NIFTY25NOV20000CE) |
| "Insufficient margin" | Check positions and available balance |
| Connection timeout | REST calls use `timeout=(5, 30)` — 5s connect, 30s read (set in `RESTClientObject.DEFAULT_TIMEOUT`). Check internet connectivity. |
| Exit order failed | If `is_exit=True`, system retries 3 times then sends URGENT Telegram. Check broker portal for manual close. |
| Auth error during order | Session auto-cleared, re-login attempted on next retry. If persistent, re-run credential setup. |

---

## Best Practices

### 1. Reuse Connections

```python
# Do this
broker = BrokerFactory.get_broker('breeze')
broker.login()
# Multiple operations...
broker.logout()

# Not this
for i in range(10):
    broker.login()
    broker.get_quote('NIFTY')
    broker.logout()  # Slow!
```

### 2. Check Before Trading

```python
def can_trade(api, required_margin):
    return (
        api.login() and
        api.is_market_open() and
        api.check_margin_sufficient(required_margin)
    )
```

### 3. Handle Rate Limits

```python
import time

def place_orders_batch(api, orders):
    for order in orders:
        try:
            api.place_order(**order)
        except RateLimitError:
            time.sleep(1)
            api.place_order(**order)
```

### 4. Never Commit Credentials

```bash
# .gitignore
.env
*.env
secrets.py
```

---

## Modular Broker Architecture

The broker integrations have been refactored into a modular structure for better maintainability:

### ICICI Breeze (`apps/brokers/integrations/breeze_module/`)

| Module | Purpose |
|--------|---------|
| `client.py` | Main BreezeAPIClient class |
| `quotes.py` | Quote fetching and LTP retrieval |
| `orders.py` | Order placement (futures, options, strangle) |
| `margin.py` | Margin calculation and availability |
| `historical.py` | Historical OHLC data fetching |
| `expiry.py` | Expiry date management |
| `option_chain.py` | Option chain data retrieval |
| `data_fetcher.py` | Generic data fetching utilities |
| `api_classes.py` | API response classes and enums |

### Kotak Neo (`apps/brokers/integrations/neo/`)

| Module | Purpose |
|--------|---------|
| `client.py` | Main NeoAPI client class |
| `quotes.py` | Quote and LTP retrieval |
| `orders.py` | Order placement and management |
| `batch_orders.py` | Batch order execution (strangle, iron condor) |
| `symbol_mapper.py` | Symbol mapping and instrument lookup |

### Usage

```python
# Import from main integration file (facade pattern)
from apps.brokers.integrations.breeze import get_breeze_client, BreezeAPIClient

# Or import specific modules for advanced usage
from apps.brokers.integrations.breeze_module.quotes import get_ltp
from apps.brokers.integrations.breeze_module.margin import get_nfo_margin
from apps.brokers.integrations.neo.batch_orders import execute_strangle_orders
```

---

## File Reference

| File | Purpose |
|------|---------|
| `apps/core/models.py` | CredentialStore model |
| `apps/brokers/models.py` | Order, Execution, BrokerLimit, BrokerPosition, HistoricalPrice models |
| `apps/brokers/interfaces.py` | BrokerInterface & factory |
| `apps/brokers/integrations/breeze.py` | Breeze integration (facade) |
| `apps/brokers/integrations/breeze_module/` | Modular Breeze implementation |
| `apps/brokers/integrations/kotak_neo.py` | Kotak Neo integration (facade) |
| `apps/brokers/integrations/neo/` | Modular Neo implementation |
| `apps/brokers/services/order_sync.py` | Order synchronization service |
| `apps/brokers/utils/auth_manager.py` | Auto-login tracking & Neo session save/restore |
| `tools/neo.py` | NeoAPI implementation |
| `apps/core/management/commands/setup_credentials.py` | CLI commands |

---

## API Documentation Links

- **ICICI Breeze**: https://api.icicidirect.com/docs
- **Kotak Neo**: https://api.kotakneo.com/docs

---

*See [03-TRADING-STRATEGIES.md](03-TRADING-STRATEGIES.md) for how brokers are used in trading strategies.*
