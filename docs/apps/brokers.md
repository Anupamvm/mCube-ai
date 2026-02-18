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
6. **Trade History Import** - Upload CSV/Excel Gain/Loss reports for P&L tracking

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | Order, Execution, HistoricalPrice models |
| `interfaces.py` | Abstract broker interface |
| `base.py` | Base classes for broker abstraction |
| `integrations/breeze.py` | ICICI Breeze integration (~1,962 lines) |
| `integrations/kotak_neo.py` | Kotak Neo integration (~2,822 lines) |
| `integrations/breeze_module/` | Modular Breeze components |
| `integrations/neo/` | Modular Neo components |
| `services/breeze_session.py` | Breeze session manager (singleton, auto-login with Selenium + Telegram OTP) |
| `services/breeze_auto_login.py` | Breeze auto-login with lock mechanism (~1,003 lines) |
| `services/csv_importers.py` | CSV/Excel importers for trade history (Kotak + Breeze) |
| `services/order_sync.py` | Order synchronization |
| `utils/auth_manager.py` | Credential management + auto-login tracking helpers |
| `utils/security_master.py` | Instrument master lookup |
| `forms.py` | CSVUploadForm (CSV/Excel file validation) |
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

## Kotak Neo Integration (v2 — TOTP + MPIN Auth)

**File**: `integrations/kotak_neo.py` + `tools/neo.py`

### Authentication (v2)

The Kotak Neo API was upgraded from v1 to v2 in Feb 2026:
- **Old (v1):** `login(pan, password)` + `session_2fa(OTP)` — required consumer_secret
- **New (v2):** `totp_login(mobile, ucc, totp)` + `totp_validate(mpin)` — no OTP needed, fully automated

```python
from tools.neo import NeoAPI

# Initialize (zero network calls on init — no consumer_secret needed)
api = NeoAPI()

# Login — tries session restore first, then fresh TOTP+MPIN login
# Session persistence: saves base_url + data_center from totp_validate response
# base_url is REQUIRED for all non-auth API calls
api.login()

# Auto-login is limited to one attempt per day to prevent account blocking
# 3 retries with 10-second delay between attempts
```

### v2 API Response Changes

```python
# Quotes: v2 returns list directly (not {'data': [...]})
# Uses pSymbol as instrument_token
# instrument_tokens format: [{"exchange_segment": "nse_fo", "instrument_token": "2885"}]

# search_scrip: v2 returns list directly (wrapper handles both formats)
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

Centralized authentication handling + auto-login safety tracking.

```python
from apps.brokers.utils.auth_manager import (
    can_attempt_auto_login,      # Check if daily attempt allowed
    mark_auto_login_started,     # Mark attempt in-progress
    mark_auto_login_success,     # Mark successful login
    mark_auto_login_failed,      # Mark failed login
    reset_auto_login_status,     # Manual reset
    save_neo_session,            # Persist Neo v2 session (base_url, data_center, tokens)
    restore_neo_session,         # Restore saved session
)
```

### Breeze Session Manager (`services/breeze_session.py`)

Singleton session manager with auto-login and lock mechanism.

```python
from apps.brokers.services.breeze_session import BreezeSessionManager

manager = BreezeSessionManager()  # Singleton (_instance pattern)
client = manager.get_client()     # Returns authenticated BreezeConnect

# Lock mechanism prevents concurrent logins:
# - breeze_auto_login_lock flag in NseFlag (300s expiry)
# - validate_existing_token() creates BreezeConnect directly (no recursion)
# - caller_holds_lock param prevents deadlock
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

## Trade History Import (CSV/Excel Upload)

**URL**: `/brokers/csv-upload/`

Upload broker Gain/Loss reports to track contract-level P&L across financial years. Supports both CSV and Excel (.xlsx) files.

### Supported File Types

| File Type | Broker | Source |
|-----------|--------|--------|
| `kotak_fno` | Kotak Neo | Gain/Loss report (all sections: Equity, MF, ETF, Derivatives) |
| `breeze_fno` | ICICI Breeze | FNO Portfolio CSV |

### How It Works

1. User uploads CSV or Excel file via drag-and-drop UI
2. **Excel files** are automatically converted to CSV on the fly using `openpyxl` (`convert_excel_to_csv_file()`)
3. The appropriate importer (`KotakFNOImporter` or `BreezeFNOImporter`) parses the file
4. **Incremental upload**: Records are matched by `(broker, trading_symbol, fy)` unique constraint
   - **New** contracts are created
   - **Changed** contracts are updated (latest report wins)
   - **Unchanged** contracts are skipped (no DB write)
   - Re-uploading the same file produces zero duplicates

### Key Files

| File | Purpose |
|------|---------|
| `services/csv_importers.py` | `KotakFNOImporter`, `BreezeFNOImporter`, `convert_excel_to_csv_file()` |
| `forms.py` | `CSVUploadForm` — validates .csv/.xlsx/.xls, max 10MB |
| `views.py` (lines 1388-1523) | `csv_upload_dashboard`, `api_upload_csv`, `api_delete_import_batch`, `api_import_logs`, `api_imported_pnl_summary` |
| `templates/brokers/csv_upload_dashboard.html` | Upload UI with drag-and-drop, results, import history |

### Models

**`CSVImportLog`** — Audit trail for each import (batch_id, file_type, status, record counts, errors)

**`BrokerContractPnL`** — Per-contract P&L with full charge breakdown:
- Identity: `broker`, `trading_symbol`, `symbol`, `segment`, `security_type`, `fy`
- Financial: `quantity`, `buy_amount`, `sell_amount`, `gross_pnl`, `net_pnl`
- Charges: `gst`, `brokerage`, `stt`, `misc_charges`, `total_charges`
- Contract: `expiry_date`, `strike_price`, `option_type`
- Unique constraint: `(broker, trading_symbol, fy)`

### Kotak CSV/Excel Format

```
Row 1-4: Client info (Name, Code, Period, Type)
Row 5:   Empty
Row 6:   Column headers (Script Name, Security Type, ISIN, Qty, Buy/Sell Amt, P&L, Charges...)
Row 7:   Sub-headers
Row 8+:  Section markers (Equity, Mutual Funds, ETF, Derivatives) followed by data rows
         Disclaimer at end
```

Contract name formats:
- **Futures**: `BANKNIFTY 25NOV25 XX 0` (SYMBOL DDMMMYY XX 0)
- **Options**: `NIFTY 02DEC25 CE 26850` (SYMBOL DDMMMYY CE/PE STRIKE)

FY extracted from filename: `Gain_Loss_A0YPQ_20250401_20260331.csv` → FY `2025-26`

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
   - Kotak API rate-limits after multiple failed login attempts; wait ~90s between retries

4. **Session Expiry**: Tokens expire, need daily re-login
   - Neo v2: Session restored via saved `base_url` + `data_center`; fails early if `base_url` missing
   - Breeze: Singleton session manager with Selenium + Telegram OTP auto-login

5. **Auto-Login Safety**: One attempt per day per broker
   - Tracked via `CredentialStore.auto_login_status` + `auto_login_date`
   - Prevents account blocking from repeated failed attempts

---

*For questions, check the code comments or ask the team.*
