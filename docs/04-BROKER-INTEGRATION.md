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

### Kotak Neo API

1. Go to https://api.kotakneo.com
2. Sign in with your Kotak Securities account
3. Navigate to API Management
4. Create a new API app to get:
   - **Consumer Key**: Application ID
   - **Consumer Secret**: Application secret
5. Keep ready your trading:
   - **Mobile Number**: Account login mobile
   - **Password**: Account login password
   - **MPIN**: Trading PIN for order placement

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

# Add Kotak Neo credentials
CredentialStore.objects.create(
    service='kotakneo',
    name='kotakneo_prod',
    api_key='YOUR_CONSUMER_KEY',
    api_secret='YOUR_CONSUMER_SECRET',
    username='9999999999',  # Mobile number
    password='YOUR_PASSWORD',
    neo_password='YOUR_MPIN',
    pan='ABCDE1234F'  # Optional
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

### Direct Kotak Neo Usage

```python
from tools.neo import NeoAPI

# Initialize
api = NeoAPI()

# Login
api.login()

# Get margin
margin = api.get_available_margin()

# Get positions
positions = api.get_positions()

# Search for symbol
results = api.search_scrip(symbol='NIFTY', exchange='NSE')

# Place order
order_id = api.place_order(
    symbol='NIFTY25NOV20000CE',
    action='B',           # 'B' for BUY, 'S' for SELL
    quantity=1,
    order_type='MARKET',  # 'MARKET' or 'LIMIT'
    price=0,
    exchange='NFO',
    product='NRML'
)

# Logout
api.logout()
```

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
    order_type='MARKET'
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

# Kotak Neo
api = NeoAPI()
api.login()
quote = api.get_quote('RELIANCE')
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
        ('kotakneo', 'Kotak Neo'),
        ('trendlyne', 'Trendlyne'),
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
    neo_password = models.CharField()  # MPIN
    pan = models.CharField()
    sid = models.CharField()  # Session ID
```

### Field Mapping

| Purpose | ICICI Breeze | Kotak Neo |
|---------|--------------|-----------|
| App ID | `api_key` | `api_key` |
| App Secret | `api_secret` | `api_secret` |
| Session | `session_token` | `sid` |
| Login ID | - | `username` (mobile) |
| Password | - | `password` |
| Trading PIN | - | `neo_password` (MPIN) |

---

## Error Handling

```python
try:
    api = NeoAPI()
    api.login()

    if not api.check_margin_sufficient(50000):
        raise ValueError("Insufficient margin")

    order_id = api.place_order('RELIANCE-EQ', 'B', 1, 'MARKET')

except Exception as e:
    print(f"Trading error: {e}")
    # Log error, send alert

finally:
    api.logout()
```

---

## Session Management

### Session Expiry

- Session tokens expire after inactivity
- APIs automatically prompt for re-login
- Store new session token after successful login

### Refresh Session

```bash
# Re-setup credentials with new session
python manage.py setup_credentials --setup-breeze
```

Or programmatically:

```python
cred = CredentialStore.objects.filter(service='breeze').first()
cred.session_token = new_token
cred.save()
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
| Connection timeout | Check internet, retry with backoff |

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

## File Reference

| File | Purpose |
|------|---------|
| `apps/core/models.py` | CredentialStore model |
| `apps/brokers/interfaces.py` | BrokerInterface & factory |
| `apps/brokers/integrations/breeze.py` | Breeze integration |
| `tools/neo.py` | NeoAPI implementation |
| `apps/core/management/commands/setup_credentials.py` | CLI commands |

---

## API Documentation Links

- **ICICI Breeze**: https://api.icicidirect.com/docs
- **Kotak Neo**: https://api.kotakneo.com/docs

---

*See [03-TRADING-STRATEGIES.md](03-TRADING-STRATEGIES.md) for how brokers are used in trading strategies.*
