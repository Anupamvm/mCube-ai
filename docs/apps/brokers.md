# Brokers App Documentation

**Location**: `apps/brokers/`

The brokers app handles all communication with broker APIs (Kotak Neo and ICICI Breeze). It's responsible for fetching data, placing orders, and syncing positions.

---

## What This App Does

1. **Authentication** - Login to broker accounts
2. **Data Fetching** - Get prices, margins, positions
3. **Order Placement** - Place market/limit orders
4. **Position Sync** - Sync positions from broker
5. **Batch Operations** - Handle large orders in batches

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | Order, Execution, HistoricalPrice models |
| `interfaces.py` | Abstract broker interface |
| `base.py` | Base classes for broker abstraction |
| `integrations/breeze.py` | ICICI Breeze integration (1458 lines) |
| `integrations/kotak_neo.py` | Kotak Neo integration (1924 lines) |
| `integrations/breeze_module/` | Modular Breeze components |
| `integrations/neo/` | Modular Neo components |
| `services/order_sync.py` | Order synchronization |
| `utils/` | Auth manager, security master |
| `admin.py` | Django admin interface |

---

## Two Brokers

| Broker | Account | API | Purpose |
|--------|---------|-----|---------|
| **Kotak Neo** | Rs 6 Cr | REST + WebSocket | Options (Strangle) |
| **ICICI Breeze** | Rs 1.2 Cr | REST | Futures |

---

## Key Models

### Order

Tracks all orders placed through the system.

```python
# Fields
account = ForeignKey(BrokerAccount)
position = ForeignKey(Position, nullable)
order_type = CharField()           # MARKET, LIMIT, SL, SLM
direction = CharField()            # LONG, SHORT
instrument = CharField()           # Trading symbol
quantity = IntegerField()
price = DecimalField()             # For LIMIT orders
trigger_price = DecimalField()     # For SL orders
status = CharField()               # PENDING, PLACED, FILLED, CANCELLED, REJECTED
broker_order_id = CharField()      # ID from broker
filled_quantity = IntegerField()
average_price = DecimalField()
placed_at = DateTimeField()
filled_at = DateTimeField()
cancelled_at = DateTimeField()
purpose = CharField()              # ENTRY, EXIT, AVERAGING
```

### Execution

Individual fills for an order (partial fills).

```python
# Fields
order = ForeignKey(Order)
execution_id = CharField()
quantity = IntegerField()
price = DecimalField()
exchange_timestamp = DateTimeField()
```

### HistoricalPrice

OHLCV data for backtesting and analysis.

```python
# Fields
stock_code = CharField()
datetime = DateTimeField()
open = DecimalField()
high = DecimalField()
low = DecimalField()
close = DecimalField()
volume = BigIntegerField()
```

---

## ICICI Breeze Integration

**File**: `integrations/breeze.py`

### Authentication

```python
from apps.brokers.integrations.breeze import get_breeze_client

# Get authenticated client
breeze = get_breeze_client()

# The function:
# 1. Loads credentials from CredentialStore
# 2. Initializes BreezeConnect client
# 3. Generates session using stored token
# 4. Returns ready-to-use client
```

### Key Functions

```python
from apps.brokers.integrations.breeze import (
    get_breeze_client,                    # Get authenticated client
    fetch_and_save_breeze_data,           # Fetch funds and positions
    get_nfo_margin,                       # Get F&O margin
    get_nifty_quote,                      # Get NIFTY50 price
    get_india_vix,                        # Get VIX (cached 5 min)
    get_next_nifty_expiry,                # Get expiry date
    place_futures_order_with_security_master,  # Place futures order
    place_option_order_with_security_master,   # Place option order
    place_strangle_order,                 # Place both call and put
)
```

### Placing a Futures Order

```python
from apps.brokers.integrations.breeze import place_futures_order_with_security_master

result = place_futures_order_with_security_master(
    symbol='RELIANCE',
    expiry_date='30-JAN-2026',
    action='buy',           # 'buy' or 'sell'
    lots=1,
    order_type='market',    # 'market' or 'limit'
    price=0                 # For limit orders
)

# Result:
# {
#     'success': True,
#     'order_id': 'BRZ123456',
#     'message': 'Order placed successfully',
#     'details': {...}
# }
```

### Placing a Strangle Order

```python
from apps.brokers.integrations.breeze import place_strangle_order

result = place_strangle_order(
    symbol='NIFTY',
    call_strike=24500,
    put_strike=24000,
    quantity=2,              # In lots
    expiry='27-NOV-2025'
)

# Places both SELL CALL and SELL PUT orders
```

### Getting Data

```python
# Get current price
quote = get_nifty_quote()
# Returns: {'ltp': 24150.50, 'high': 24200, 'low': 24100, ...}

# Get VIX (cached for 5 minutes)
vix = get_india_vix()
# Returns: 12.35

# Get margin
margin = get_nfo_margin()
# Returns: {'available': 2500000, 'used': 150000, ...}
```

---

## Kotak Neo Integration

**File**: `integrations/kotak_neo.py`

### Authentication

```python
from apps.brokers.integrations.kotak_neo import get_kotak_neo_client

# Get authenticated client (handles 2FA automatically)
client = get_kotak_neo_client()
```

### Key Functions

```python
from apps.brokers.integrations.kotak_neo import (
    get_kotak_neo_client,               # Get authenticated client
    fetch_and_save_kotakneo_data,       # Fetch limits and positions
    place_option_order,                 # Place option order
    get_lot_size_from_neo,              # Get lot size
    get_ltp_from_neo,                   # Get current price
    place_strangle_orders_in_batches,   # Batch strangle placement
    close_position_in_batches,          # Batch position closing
)
```

### Placing an Option Order

```python
from apps.brokers.integrations.kotak_neo import place_option_order

result = place_option_order(
    trading_symbol='NIFTY25NOV24500CE',
    transaction_type='S',      # 'B' for BUY, 'S' for SELL
    quantity=50,               # In shares (1 lot = 50)
    product='NRML',
    order_type='MKT',
)

# Result:
# {
#     'success': True,
#     'order_id': 'NEO123456',
#     'message': 'Order placed'
# }
```

### Batch Order Placement

For large positions, orders are placed in batches to avoid API limits.

```python
from apps.brokers.integrations.kotak_neo import place_strangle_orders_in_batches

result = place_strangle_orders_in_batches(
    call_symbol='NIFTY25NOV24500CE',
    put_symbol='NIFTY25NOV24000PE',
    total_lots=167,
    batch_size=20,          # Neo API limit
    delay_seconds=20,       # Delay between batches
)

# Places 9 batches: 8 × 20 lots + 1 × 7 lots
# With 20-second delays between batches
```

### Closing Positions in Batches

```python
from apps.brokers.integrations.kotak_neo import close_position_in_batches

result = close_position_in_batches(
    trading_symbol='NIFTY25DECFUT',
    total_quantity=3350,
    transaction_type='S',    # SELL to close LONG
    batch_size=20,
    delay_seconds=20,
)
```

---

## Symbol Mapping

Breeze and Neo use different symbol formats. The app handles this automatically.

```
Breeze Format: stock_code='NIFTY', expiry_date='30-JAN-2026'
Neo Format:    'NIFTY26JANFUT' or 'NIFTY25NOV24500CE'
```

```python
from apps.brokers.integrations.kotak_neo import (
    map_neo_symbol_to_breeze,
    map_breeze_symbol_to_neo,
)

# Neo to Breeze
breeze_format = map_neo_symbol_to_breeze('NIFTY26JANFUT')
# Returns: {'stock_code': 'NIFTY', 'expiry_date': '30-JAN-2026'}

# Breeze to Neo (uses scrip master lookup)
neo_symbol = map_breeze_symbol_to_neo('NIFTY', 24500, 'CE', '27-NOV-2025')
# Returns: 'NIFTY25NOV24500CE'
```

---

## Modular Structure

Both brokers have been split into modules for maintainability:

### Breeze Module (`integrations/breeze_module/`)

| File | Purpose |
|------|---------|
| `client.py` | Session management |
| `orders.py` | Order placement |
| `option_chain.py` | Option chain fetching |
| `quotes.py` | Price quotes |
| `margin.py` | Margin information |
| `historical.py` | Historical data |

### Neo Module (`integrations/neo/`)

| File | Purpose |
|------|---------|
| `client.py` | Session management |
| `orders.py` | Order placement |
| `batch_orders.py` | Batch operations |
| `quotes.py` | Price quotes |
| `symbol_mapper.py` | Symbol conversion |

---

## Utilities

### Security Master (`utils/security_master.py`)

Looks up correct instrument codes for orders.

```python
from apps.brokers.utils.security_master import get_futures_instrument

instrument = get_futures_instrument('RELIANCE', '30-JAN-2026')
# Returns instrument details from Breeze SecurityMaster
```

### Auth Manager (`utils/auth_manager.py`)

Centralized authentication handling.

```python
from apps.brokers.utils.auth_manager import AuthManager

auth = AuthManager()
auth.login_breeze()
auth.login_neo()
```

---

## Order Types

| Type | Description |
|------|-------------|
| `MARKET` | Execute at current market price |
| `LIMIT` | Execute at specified price or better |
| `SL` | Stop-Loss order (trigger + limit) |
| `SLM` | Stop-Loss Market (trigger only) |

## Product Types

| Product | Description |
|---------|-------------|
| `NRML` | Regular (carry overnight) |
| `MIS` | Margin Intraday Scheme |
| `CNC` | Cash and Carry (delivery) |

---

## Error Handling

All broker functions include error handling:

```python
try:
    result = place_futures_order_with_security_master(...)
except BreezeAuthenticationError:
    # Session expired, need re-login
except BreezeAPIError as e:
    # API error with details
    print(f"Error: {e.message}, Status: {e.status_code}")
```

---

## How to Study This App

1. **Start with `interfaces.py`** - Understand the abstract interface
2. **Read `integrations/breeze.py`** - Most documented broker
3. **Study `integrations/kotak_neo.py`** - Complex but important
4. **Check `utils/security_master.py`** - Symbol lookup
5. **Review batch functions** - Understand large order handling

---

## Common Tasks for Developers

### Add New Order Function

1. Add to appropriate broker file
2. Follow existing patterns for error handling
3. Add to `__all__` exports

### Debug Order Issues

1. Check `Order` model for order status
2. Check `BkLog` for error details
3. Verify symbol format matches broker

### Test Broker Connection

```bash
python manage.py setup_credentials --test-breeze
python manage.py setup_credentials --test-kotakneo
```

---

## Key Notes

1. **Lot Size**: Orders use quantity in shares, not lots
   - Convert: `quantity = lots × lot_size`

2. **Expiry Format**: Different for each broker
   - Breeze: `'30-JAN-2026'`
   - Neo: Embedded in symbol `'NIFTY26JAN...'`

3. **Rate Limits**: Use batch functions for large orders

4. **Session Expiry**: Tokens expire, need daily re-login

---

*For questions, check the code comments or ask the team.*
