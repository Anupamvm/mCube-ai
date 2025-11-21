# Broker Integration - Complete Implementation Summary

This document summarizes the complete broker API integration system for mCube Trading Platform, supporting both ICICI Breeze and Kotak Neo APIs.

## Overview

The system provides:
- **Unified credential management** through Django's CredentialStore model
- **Standardized broker interfaces** for consistent API usage across brokers
- **Complete wrapper classes** for both ICICI Breeze and Kotak Neo
- **Management commands** for easy credential setup and testing
- **Factory pattern** for switching between brokers
- **Migration tools** from old mCube3 project

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│         Trading Strategy / Application Code                │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│  BrokerFactory (apps/brokers/interfaces.py)               │
│  - Single entry point for all broker access               │
│  - Automatic broker registration                          │
└──────────────┬───────────────────────────────┬─────────────┘
               │                               │
        ┌──────▼──────┐            ┌──────────▼─────┐
        │  BreezeAPI  │            │   NeoAPI       │
        │ (tools/     │            │ (tools/        │
        │  breeze.py) │            │  neo.py)       │
        └──────┬──────┘            └──────┬─────────┘
               │                          │
        ┌──────▼──────────────────────────▼───────┐
        │ Broker API Implementations               │
        │ - Margin Management                     │
        │ - Order Placement                       │
        │ - Position Tracking                     │
        │ - Quote Fetching                        │
        └──────┬────────────────────────┬─────────┘
               │                        │
        ┌──────▼──┐          ┌──────────▼────┐
        │  Breeze │          │ Kotak Neo API │
        │ RESTful │          │  WebSocket    │
        │   API   │          │  + REST       │
        └─────────┘          └───────────────┘
```

---

## Files & Directory Structure

### Core Files

```
mCube-ai/
├── CREDENTIAL_SETUP_GUIDE.md          # Detailed credential setup guide
├── QUICKSTART_BROKERS.md              # Quick start examples
├── BROKER_INTEGRATION_SUMMARY.md      # This file
│
├── apps/
│   ├── core/
│   │   ├── models.py                  # CredentialStore model
│   │   └── management/commands/
│   │       └── setup_credentials.py   # Credential management command
│   │
│   └── brokers/
│       └── interfaces.py              # BrokerInterface abstract class
│
├── tools/
│   ├── breeze.py                      # BreezeAPI wrapper (implements BrokerInterface)
│   └── neo.py                         # NeoAPI wrapper (implements BrokerInterface)
│
└── scripts/
    ├── initialize_credentials.py      # Interactive credential initialization
    └── migrate_old_credentials.py     # Migrate from old mCube3 project
```

---

## Key Components

### 1. CredentialStore Model (`apps/core/models.py`)

Stores and manages API credentials securely.

**Fields:**
- `service`: Choice of 'breeze', 'kotakneo', 'trendlyne'
- `name`: Credential set name (e.g., 'default', 'prod')
- `api_key`: API Key or Consumer Key
- `api_secret`: API Secret or Consumer Secret
- `username`: Mobile number or email
- `password`: Login password
- `neo_password`: MPIN (Kotak Neo only)
- `pan`: PAN number (optional)
- `session_token`: Broker session token
- `sid`: Session ID (optional)

### 2. BrokerInterface (`apps/brokers/interfaces.py`)

Abstract base class defining the contract for all broker implementations.

**Key Methods:**
```python
# Authentication
login() -> bool
logout() -> bool

# Margin Management
get_margin() -> MarginData
get_available_margin() -> float
check_margin_sufficient(required: float) -> bool

# Positions
get_positions() -> List[Position]
has_open_positions() -> bool
get_position_pnl() -> float

# Orders
place_order(symbol, action, quantity, order_type, price) -> str
get_orders() -> List[Order]
cancel_order(order_id: str) -> bool

# Quotes & Data
get_quote(symbol) -> Quote
search_symbol(symbol) -> List[Dict]

# Market Status
is_market_open() -> bool

# Live Feed
subscribe_live_feed(symbols) -> bool
unsubscribe_live_feed(symbols) -> bool
```

### 3. BreezeAPI (`tools/breeze.py`)

ICICI Breeze broker implementation.

**Features:**
- ✅ Login/logout with session management
- ✅ Margin and funds retrieval
- ✅ Portfolio positions tracking
- ✅ Order placement (market and limit)
- ✅ Order cancellation and history
- ✅ Quote fetching
- ✅ Option chain retrieval
- ✅ Historical data (OHLCV)
- ✅ Market status checking

### 4. NeoAPI (`tools/neo.py`)

Kotak Neo broker implementation.

**Features:**
- ✅ Login/logout with 2FA support
- ✅ Margin and limits retrieval
- ✅ Portfolio positions tracking
- ✅ Order placement
- ✅ Order modification and cancellation
- ✅ Quote fetching
- ✅ Symbol search
- ✅ Limits and portfolio holdings
- ✅ Live feed subscription (WebSocket)
- ✅ Order feed subscription

### 5. BrokerFactory (`apps/brokers/interfaces.py`)

Factory pattern for creating broker instances.

```python
from apps.brokers.interfaces import BrokerFactory

# Get any broker by name
broker = BrokerFactory.get_broker('breeze')
# broker = BrokerFactory.get_broker('kotakneo')

# Both have same interface
broker.login()
margin = broker.get_available_margin()
broker.logout()
```

---

## Management Commands

### Setup Credentials

```bash
# Interactive setup for Breeze
python manage.py setup_credentials --setup-breeze

# Interactive setup for Kotak Neo
python manage.py setup_credentials --setup-kotakneo

# Interactive setup for Trendlyne
python manage.py setup_credentials --setup-trendlyne
```

### List & Manage

```bash
# List all stored credentials
python manage.py setup_credentials --list

# Check status of all credentials
python manage.py setup_credentials --status

# Delete credentials for a service
python manage.py setup_credentials --delete breeze
```

### Testing

```bash
# Test Breeze connection
python manage.py setup_credentials --test-breeze

# Test Kotak Neo connection
python manage.py setup_credentials --test-kotakneo
```

---

## Usage Examples

### Example 1: Switch Between Brokers (Factory Pattern)

```python
from apps.brokers.interfaces import BrokerFactory

def trade_with_best_margin(symbol, quantity, required_margin):
    """Find broker with best margin and place trade"""

    brokers = ['breeze', 'kotakneo']

    best_broker = None
    best_margin = 0

    for broker_name in brokers:
        try:
            broker = BrokerFactory.get_broker(broker_name)
            broker.login()

            margin = broker.get_available_margin()
            if margin >= required_margin and margin > best_margin:
                best_margin = margin
                best_broker = broker

        except Exception as e:
            print(f"Error with {broker_name}: {e}")

    if best_broker:
        order_id = best_broker.place_order(
            symbol=symbol,
            action='B',
            quantity=quantity,
            order_type='MKT'
        )
        best_broker.logout()
        return order_id

    return None
```

### Example 2: Multi-Broker Position Tracking

```python
from apps.brokers.interfaces import BrokerFactory

def track_positions():
    """Track positions across all brokers"""

    for broker_name in ['breeze', 'kotakneo']:
        try:
            broker = BrokerFactory.get_broker(broker_name)
            broker.login()

            positions = broker.get_positions()
            pnl = broker.get_position_pnl()

            print(f"\n{broker_name.upper()}:")
            print(f"  Open Positions: {len(positions)}")
            print(f"  Total P&L: ₹{pnl:,.2f}")

            for pos in positions:
                print(f"    - {pos['symbol']}: ₹{pos.get('pnl', 0):,.2f}")

            broker.logout()

        except Exception as e:
            print(f"Error accessing {broker_name}: {e}")
```

### Example 3: Conditional Trading Based on Broker

```python
from apps.brokers.interfaces import BrokerFactory

def place_trade_safely(symbol, broker_name='breeze'):
    """Place trade with safety checks"""

    broker = BrokerFactory.get_broker(broker_name)

    try:
        if not broker.login():
            print("❌ Login failed")
            return None

        # Check market
        if not broker.is_market_open():
            print("❌ Market is closed")
            broker.logout()
            return None

        # Check margin
        if not broker.check_margin_sufficient(50000):
            print("❌ Insufficient margin")
            broker.logout()
            return None

        # Check positions
        if broker.has_open_positions():
            print("⚠️  Already have open positions")

        # Get quote
        quote = broker.get_quote(symbol)
        if not quote:
            print(f"❌ Could not fetch quote for {symbol}")
            broker.logout()
            return None

        print(f"✅ Placing order for {symbol}")
        order_id = broker.place_order(
            symbol=symbol,
            action='B',
            quantity=1,
            order_type='MKT'
        )

        broker.logout()
        return order_id

    except Exception as e:
        print(f"❌ Error: {e}")
        broker.logout()
        return None
```

---

## Migration from Old mCube3

### Automated Migration

```bash
python scripts/migrate_old_credentials.py
```

This script:
1. Connects to old mCube3 database
2. Reads CredentialStore entries
3. Maps old schema to new schema
4. Creates/updates credentials in new system
5. Verifies migration

### Manual Migration

```bash
python manage.py shell
```

```python
from apps.core.models import CredentialStore

# Import from old project
import sqlite3
old_db = sqlite3.connect('/path/to/old/db.sqlite3')
cursor = old_db.cursor()

cursor.execute("SELECT * FROM tools_credentialstore")
for row in cursor.fetchall():
    # Create in new system
    CredentialStore.objects.create(...)
```

---

## Database Setup

### First Time Setup

```bash
# Create tables
python manage.py migrate

# Verify
python manage.py shell
>>> from apps.core.models import CredentialStore
>>> print(CredentialStore.objects.count())
0
```

### Backup & Restore

```bash
# Backup
python manage.py dumpdata core.CredentialStore > credentials.json

# Restore
python manage.py loaddata credentials.json
```

---

## Security Considerations

### Best Practices

1. **Environment Variables**: Never hardcode credentials
   ```python
   import os
   api_key = os.environ.get('BREEZE_API_KEY')
   ```

2. **Database Encryption**: Encrypt sensitive fields
   ```python
   # Use django-encrypted-model-fields
   api_secret = EncryptedCharField(max_length=256)
   ```

3. **Access Control**: Restrict credential access
   - Only authorized users can view
   - Log all credential access attempts
   - Implement role-based access

4. **Token Rotation**: Regularly rotate session tokens
   ```python
   # Clear expired tokens
   cred.session_token = None
   cred.save()
   ```

5. **Credential Rotation**: Periodically rotate API keys
   - Generate new keys in broker console
   - Update in database
   - Revoke old keys

---

## Troubleshooting Guide

### Common Issues

| Issue | Solution |
|-------|----------|
| "Credentials not found" | Run `python manage.py setup_credentials --setup-breeze` |
| "Login failed" | Verify API keys and test connection |
| "Session expired" | Clear session token and re-login |
| "Insufficient margin" | Check available margin and close positions if needed |
| "Invalid symbol" | Use full instrument names (e.g., NIFTY25NOV20000CE) |

### Debug Commands

```bash
# Check all credentials
python manage.py setup_credentials --list

# Test connection
python manage.py setup_credentials --test-breeze

# Django shell debugging
python manage.py shell
>>> from apps.core.models import CredentialStore
>>> cred = CredentialStore.objects.filter(service='breeze').first()
>>> print(cred.api_key)
```

---

## Testing

### Unit Tests

```python
# tests/test_brokers.py

from apps.brokers.interfaces import BrokerFactory
from apps.brokers.integrations.breeze import get_breeze_client, BreezeAPIClient

def test_breeze_login():
    api = BreezeAPI()
    assert api.login() == True

def test_broker_factory():
    broker = BrokerFactory.get_broker('breeze')
    assert broker is not None

def test_margin_check():
    api = BreezeAPI()
    api.login()
    margin = api.get_available_margin()
    assert isinstance(margin, float)
    api.logout()
```

### Integration Tests

```bash
python manage.py test apps.core tests.test_brokers
```

---

## Performance Optimization

### Caching

```python
from django.core.cache import cache

def get_margin_cached(broker_name, timeout=300):
    cache_key = f"margin_{broker_name}"
    margin = cache.get(cache_key)

    if margin is None:
        broker = BrokerFactory.get_broker(broker_name)
        broker.login()
        margin = broker.get_available_margin()
        broker.logout()
        cache.set(cache_key, margin, timeout)

    return margin
```

### Connection Pooling

```python
# Reuse broker connections
class BrokerPool:
    _brokers = {}

    @classmethod
    def get_broker(cls, name):
        if name not in cls._brokers:
            broker = BrokerFactory.get_broker(name)
            broker.login()
            cls._brokers[name] = broker
        return cls._brokers[name]

    @classmethod
    def close_all(cls):
        for broker in cls._brokers.values():
            broker.logout()
```

---

## Monitoring & Logging

```python
import logging

logger = logging.getLogger('brokers')

def safe_place_order(symbol, action, quantity):
    try:
        broker = BrokerFactory.get_broker('breeze')
        broker.login()
        order_id = broker.place_order(symbol, action, quantity)
        logger.info(f"Order placed: {order_id}")
        return order_id
    except Exception as e:
        logger.error(f"Order failed: {e}", exc_info=True)
        return None
    finally:
        broker.logout()
```

---

## Next Steps

1. **Complete Documentation**: Read detailed guides
   - [CREDENTIAL_SETUP_GUIDE.md](CREDENTIAL_SETUP_GUIDE.md)
   - [QUICKSTART_BROKERS.md](QUICKSTART_BROKERS.md)

2. **Setup Credentials**: Run management commands
   ```bash
   python manage.py setup_credentials --setup-breeze
   python manage.py setup_credentials --setup-kotakneo
   ```

3. **Test Connections**: Verify both brokers work
   ```bash
   python manage.py setup_credentials --test-breeze
   python manage.py setup_credentials --test-kotakneo
   ```

4. **Implement Trading Strategy**: Use the APIs in your strategies

5. **Monitor & Log**: Implement proper logging and monitoring

6. **Handle Errors**: Implement comprehensive error handling

---

## API Comparison

| Feature | Breeze | Neo |
|---------|--------|-----|
| Login Method | API Key + Secret | Consumer Key/Secret + 2FA |
| Session Management | Session Token | Edit Token + 2FA |
| WebSocket Support | ❌ | ✅ |
| Order Types | MARKET, LIMIT | MARKET, LIMIT |
| Exchanges | NSE, BSE, NFO | NSE, BSE, NSEFO, BSEFO |
| Historical Data | ✅ | ❌ |
| Option Chain | ✅ | ❌ |
| Live Quotes | REST only | WebSocket + REST |

---

## Support & Resources

- **Official Docs**:
  - Breeze: https://api.icicidirect.com/docs
  - Kotak Neo: https://api.kotakneo.com/docs

- **Issues**: Report bugs to project repository

- **Questions**: Check FAQ in CREDENTIAL_SETUP_GUIDE.md

---

## Version History

- **v1.0** (2024-11-16): Initial release
  - ICICI Breeze integration
  - Kotak Neo integration
  - BrokerFactory pattern
  - Management commands
  - Migration tools

---

## License & Disclaimer

This code is provided as-is for trading purposes. Always test with small amounts and implement proper risk management. The authors are not responsible for trading losses.

---

**Last Updated**: 2024-11-16
**Maintainer**: mCube Trading Team
