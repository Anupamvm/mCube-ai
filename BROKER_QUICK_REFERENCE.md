# Broker API - Quick Reference Card

One-page cheat sheet for using ICICI Breeze and Kotak Neo APIs.

## Setup (5 minutes)

```bash
# 1. Setup credentials
python manage.py setup_credentials --setup-breeze
python manage.py setup_credentials --setup-kotakneo

# 2. Test connections
python manage.py setup_credentials --test-breeze
python manage.py setup_credentials --test-kotakneo

# 3. Verify
python manage.py setup_credentials --list
```

## Basic Usage

### Using Factory Pattern (Recommended)
```python
from apps.brokers.interfaces import BrokerFactory

broker = BrokerFactory.get_broker('breeze')  # or 'kotakneo'
broker.login()
margin = broker.get_available_margin()
broker.logout()
```

### Direct Import
```python
from tools.breeze import BreezeAPI
from tools.neo import NeoAPI

api = BreezeAPI()
api.login()
# ... use api ...
api.logout()
```

---

## Common Operations

### Login & Logout
```python
api = BreezeAPI()
success = api.login()        # Returns bool
api.logout()
```

### Get Margin
```python
margin = api.get_available_margin()      # Returns float
status = api.check_margin_sufficient(50000)  # Returns bool
```

### Get Positions
```python
positions = api.get_positions()          # Returns List[Dict]
has_pos = api.has_open_positions()       # Returns bool
pnl = api.get_position_pnl()            # Returns float
```

### Place Order
```python
# Market Order
order_id = api.place_order(
    symbol='RELIANCE',
    action='B',              # 'B' (BUY) or 'S' (SELL)
    quantity=1,
    order_type='MKT'        # 'MKT' or 'L' (LIMIT)
)

# Limit Order
order_id = api.place_order(
    symbol='RELIANCE',
    action='B',
    quantity=1,
    order_type='L',
    price=2500
)
```

### Get Quote
```python
quote = api.get_quote('RELIANCE')
ltp = quote['ltp']
```

### Get/Cancel Orders
```python
orders = api.get_orders()
success = api.cancel_order('ORDER_ID')
```

### Market Status
```python
is_open = api.is_market_open()           # Returns bool
```

---

## Broker-Specific Details

### ICICI Breeze

| Method | Signature |
|--------|-----------|
| `login()` | No params |
| `place_order()` | symbol, action, qty, type='MARKET', price=0 |
| `get_quote()` | symbol, exchange='NSE' |

**Extras:**
```python
api.get_option_chain('NIFTY', '27-NOV-2024')
api.get_historical_data('RELIANCE', interval='1day')
api.get_current_expiry()  # Returns 'DD-MMM-YYYY'
```

### Kotak Neo

| Method | Signature |
|--------|-----------|
| `login()` | No params (needs neo_password in DB) |
| `place_order()` | symbol, action, qty, type='MARKET', price=0 |
| `search_scrip()` | symbol, exchange='NSE' |

**Extras:**
```python
api.subscribe([token1, token2])      # Live feed
api.unsubscribe([token1, token2])    # Stop live feed
api.limits(segment='ALL', exchange='ALL', product='ALL')
api.holdings()  # Portfolio holdings
```

---

## Error Handling

```python
try:
    api = BreezeAPI()
    api.login()

    if not api.check_margin_sufficient(50000):
        print("Insufficient margin")
        return

    order_id = api.place_order('RELIANCE', 'B', 1, 'MKT')

except Exception as e:
    print(f"Error: {e}")
finally:
    api.logout()
```

---

## Credential Management

### Add Credentials
```bash
python manage.py setup_credentials --setup-breeze
python manage.py setup_credentials --setup-kotakneo
```

### View Credentials
```bash
python manage.py setup_credentials --list
python manage.py setup_credentials --status
```

### Delete Credentials
```bash
python manage.py setup_credentials --delete breeze
```

### Programmatically
```python
from apps.core.models import CredentialStore

# Create
CredentialStore.objects.create(
    service='breeze',
    name='default',
    api_key='KEY',
    api_secret='SECRET'
)

# Read
cred = CredentialStore.objects.filter(service='breeze').first()

# Update
cred.api_key = 'NEW_KEY'
cred.save()

# Delete
cred.delete()
```

---

## Field Mapping

### CredentialStore → Breeze
| Field | CredentialStore | Breeze Method |
|-------|-----------------|---------------|
| API Key | `api_key` | `BreezeConnect(api_key=...)` |
| API Secret | `api_secret` | `generate_session(api_secret=...)` |
| Session Token | `session_token` | `generate_session(session_token=...)` |

### CredentialStore → Kotak Neo
| Field | CredentialStore | Neo Method |
|-------|-----------------|-----------|
| Consumer Key | `api_key` | `NeoAPI(consumer_key=...)` |
| Consumer Secret | `api_secret` | `NeoAPI(consumer_secret=...)` |
| Mobile Number | `username` | `login(mobilenumber=...)` |
| Password | `password` | `login(password=...)` |
| MPIN | `neo_password` | `session_2fa(OTP=...)` |

---

## Common Patterns

### Check Before Trading
```python
def can_trade(api, symbol, required_margin):
    return (api.login() and
            api.is_market_open() and
            api.check_margin_sufficient(required_margin))
```

### Safe Order Placement
```python
def place_order_safe(api, symbol, qty):
    if not api.check_margin_sufficient(50000):
        return None
    return api.place_order(symbol, 'B', qty)
```

### Position Tracking
```python
def track_positions(api):
    positions = api.get_positions()
    total_pnl = api.get_position_pnl()
    return {
        'count': len(positions),
        'pnl': total_pnl
    }
```

### Switch Brokers
```python
def trade_with_broker(broker_name, symbol, qty):
    broker = BrokerFactory.get_broker(broker_name)
    broker.login()
    order_id = broker.place_order(symbol, 'B', qty)
    broker.logout()
    return order_id
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Credentials not found" | `python manage.py setup_credentials --setup-breeze` |
| Login fails | Verify API key/secret, test: `python manage.py setup_credentials --test-breeze` |
| Session expired | Clear session token: `cred.session_token = None; cred.save()` |
| No margin | Check positions and P&L with `get_positions()` |
| Invalid symbol | Use exact instrument name (e.g., NIFTY25NOV20000CE for Neo) |

---

## Performance Tips

1. **Reuse connections**
   ```python
   broker = BrokerFactory.get_broker('breeze')
   broker.login()
   # Multiple calls...
   broker.logout()
   ```

2. **Cache frequently accessed data**
   ```python
   from django.core.cache import cache
   margin = cache.get_or_set('margin', api.get_available_margin, 300)
   ```

3. **Handle timeouts**
   ```python
   try:
       quote = api.get_quote('RELIANCE')
   except TimeoutError:
       # Retry or use cached value
   ```

---

## Testing

```bash
# Test Breeze
python manage.py setup_credentials --test-breeze

# Test Kotak Neo
python manage.py setup_credentials --test-kotakneo

# Django shell
python manage.py shell
>>> from tools.breeze import BreezeAPI
>>> api = BreezeAPI()
>>> api.login()
True
>>> api.get_available_margin()
500000.0
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `apps/core/models.py` | CredentialStore model |
| `apps/brokers/interfaces.py` | BrokerInterface & factory |
| `tools/breeze.py` | BreezeAPI implementation |
| `tools/neo.py` | NeoAPI implementation |
| `apps/core/management/commands/setup_credentials.py` | CLI commands |

---

## Useful Links

- **Breeze API Docs**: https://api.icicidirect.com/docs
- **Kotak Neo Docs**: https://api.kotakneo.com/docs
- **Full Setup Guide**: [CREDENTIAL_SETUP_GUIDE.md](CREDENTIAL_SETUP_GUIDE.md)
- **Quick Start**: [QUICKSTART_BROKERS.md](QUICKSTART_BROKERS.md)
- **Complete Summary**: [BROKER_INTEGRATION_SUMMARY.md](BROKER_INTEGRATION_SUMMARY.md)

---

## Status Check
```bash
python manage.py setup_credentials --status
```

Expected:
```
BREEZE          ✅ Set
KOTAKNEO        ✅ Set
TRENDLYNE       ⚠️  Not set
```

---

**Last Updated**: 2024-11-16 | **Version**: 1.0
