# Quick Start Guide - Broker API Integration

Complete guide to setting up and using both ICICI Breeze and Kotak Neo APIs in mCube.

## Table of Contents
1. [Initial Setup](#initial-setup)
2. [ICICI Breeze Setup](#icici-breeze-setup)
3. [Kotak Neo Setup](#kotak-neo-setup)
4. [Using the APIs](#using-the-apis)
5. [Common Operations](#common-operations)
6. [Testing](#testing)
7. [Troubleshooting](#troubleshooting)

---

## Initial Setup

### Step 1: Database Preparation
```bash
# Create/apply migrations
python manage.py migrate

# Verify database is ready
python manage.py shell
>>> from apps.core.models import CredentialStore
>>> print(CredentialStore.objects.count())
0  # Should be empty initially
```

---

## ICICI Breeze Setup

### Step 1: Get API Credentials

1. Visit https://api.icicidirect.com
2. Sign in with your ICICI Direct account
3. Go to "API Console" or "Developer" section
4. Create a new application
5. Note down:
   - **API Key** (Application ID)
   - **API Secret** (Secret Key)
6. Keep these credentials safe!

### Step 2: Store Credentials in Database

**Method 1: Interactive Setup (Recommended)**
```bash
python manage.py setup_credentials --setup-breeze
```

Follow the prompts:
```
Credential name (default: default): breeze_prod
Enter API Key: your_api_key_here
Enter API Secret: your_api_secret_here
Enter Session Token (optional):
```

**Method 2: Django Shell**
```bash
python manage.py shell
```

```python
from apps.core.models import CredentialStore

CredentialStore.objects.create(
    service='breeze',
    name='default',
    api_key='YOUR_BREEZE_API_KEY',
    api_secret='YOUR_BREEZE_API_SECRET',
    session_token=None  # Will be set on first login
)
```

### Step 3: Verify Setup
```bash
python manage.py setup_credentials --test-breeze
```

Expected output:
```
=== Testing Breeze Connection ===

Attempting login...
✅ Login successful
✅ Available Margin: ₹50,00,000.00
✅ Open Positions: 0
```

### Step 4: Start Using
```python
from tools.breeze import BreezeAPI

api = BreezeAPI()
api.login()

# Get margin
margin = api.get_available_margin()
print(f"Available margin: ₹{margin:,.2f}")

# Get positions
positions = api.get_positions()
print(f"Open positions: {len(positions)}")

# Place order
order_id = api.place_order(
    symbol='RELIANCE',
    action='BUY',
    quantity=1,
    order_type='MARKET'
)

api.logout()
```

---

## Kotak Neo Setup

### Step 1: Get API Credentials

1. Visit https://api.kotakneo.com
2. Sign in with your Kotak Securities account
3. Go to "API Management"
4. Create a new API application
5. Note down:
   - **Consumer Key** (Application ID)
   - **Consumer Secret** (Application Secret)
6. Keep ready for login:
   - **Mobile Number**: Account login mobile
   - **Password**: Account login password
   - **MPIN**: Trading MPIN (for order placement)

### Step 2: Store Credentials in Database

**Method 1: Interactive Setup (Recommended)**
```bash
python manage.py setup_credentials --setup-kotakneo
```

Follow the prompts:
```
Credential name (default: default): kotakneo_prod
Enter Consumer Key: YOUR_CONSUMER_KEY
Enter Consumer Secret: YOUR_CONSUMER_SECRET
Enter Mobile Number: 9999999999
Enter Password: ••••••••
Enter MPIN: ••••
Enter PAN (optional): ABCDE1234F
```

**Method 2: Django Shell**
```bash
python manage.py shell
```

```python
from apps.core.models import CredentialStore

CredentialStore.objects.create(
    service='kotakneo',
    name='default',
    api_key='YOUR_CONSUMER_KEY',
    api_secret='YOUR_CONSUMER_SECRET',
    username='9999999999',  # Mobile number
    password='YOUR_PASSWORD',
    neo_password='YOUR_MPIN',
    pan='ABCDE1234F'  # Optional
)
```

### Step 3: Verify Setup
```bash
python manage.py setup_credentials --test-kotakneo
```

Expected output:
```
=== Testing Kotak Neo Connection ===

Attempting login...
✅ Login successful
✅ Available Margin: ₹50,00,000.00
✅ Open Positions: 0
```

### Step 4: Start Using
```python
from tools.neo import NeoAPI

api = NeoAPI()
api.login()

# Get margin
margin = api.get_available_margin()
print(f"Available margin: ₹{margin:,.2f}")

# Search for symbol
results = api.search_scrip('NIFTY', exchange='NSE')

# Place order
order_id = api.place_order(
    symbol='NIFTY25NOV20000CE',
    action='B',           # 'B' for BUY, 'S' for SELL
    quantity=1,
    order_type='MARKET'
)

api.logout()
```

---

## Using the APIs

### Broker Factory Pattern (Recommended)

Switch between brokers easily:

```python
from apps.brokers.interfaces import BrokerFactory

# Get any broker by name
broker = BrokerFactory.get_broker('breeze')
# broker = BrokerFactory.get_broker('kotakneo')

# Same interface for both!
broker.login()
margin = broker.get_available_margin()
positions = broker.get_positions()
order_id = broker.place_order(symbol='RELIANCE', action='B', quantity=1)
broker.logout()
```

### Direct Import (Traditional)

```python
from tools.breeze import BreezeAPI
# or
from tools.neo import NeoAPI

api = BreezeAPI()
api.login()
# ... use api ...
api.logout()
```

---

## Common Operations

### 1. Get Available Margin
```python
api = BreezeAPI()  # or NeoAPI()
api.login()

margin = api.get_available_margin()
print(f"Available: ₹{margin:,.2f}")

# Check if sufficient for trade
required_margin = 50000
if api.check_margin_sufficient(required_margin):
    print("✅ Sufficient margin for trade")
else:
    print("❌ Insufficient margin")

api.logout()
```

### 2. Get Current Positions
```python
api = BreezeAPI()
api.login()

positions = api.get_positions()

if positions:
    print(f"Open positions: {len(positions)}")
    for pos in positions:
        print(f"  - {pos['symbol']}: {pos['quantity']} units")
else:
    print("No open positions")

api.logout()
```

### 3. Get Position P&L
```python
api = BreezeAPI()
api.login()

total_pnl = api.get_position_pnl()
print(f"Total P&L: ₹{total_pnl:,.2f}")

api.logout()
```

### 4. Place Order
```python
api = BreezeAPI()
api.login()

# Market order
order_id = api.place_order(
    symbol='RELIANCE',
    action='BUY',
    quantity=1,
    order_type='MARKET'
)

# Limit order
order_id = api.place_order(
    symbol='RELIANCE',
    action='BUY',
    quantity=1,
    order_type='LIMIT',
    price=2500
)

api.logout()
```

### 5. Get Quote
```python
api = BreezeAPI()
api.login()

quote = api.get_quote('RELIANCE', exchange='NSE')
if quote:
    print(f"LTP: {quote.get('ltp')}")
    print(f"High: {quote.get('high')}")
    print(f"Low: {quote.get('low')}")

api.logout()
```

### 6. Get All Orders
```python
api = BreezeAPI()
api.login()

orders = api.get_orders()
for order in orders:
    print(f"Order {order['id']}: {order['symbol']} - {order['status']}")

api.logout()
```

### 7. Cancel Order
```python
api = BreezeAPI()
api.login()

order_id = '12345'
success = api.cancel_order(order_id)

if success:
    print(f"✅ Order {order_id} cancelled")
else:
    print(f"❌ Failed to cancel order")

api.logout()
```

### 8. Check Market Status
```python
api = BreezeAPI()

if api.is_market_open():
    print("✅ Market is open")
else:
    print("❌ Market is closed")
```

---

## Testing

### List All Credentials
```bash
python manage.py setup_credentials --list
```

Output:
```
=== Stored Credentials ===

Service: ICICI Breeze
  Name: default
  API Key: 12345678...
  Username: Not set
  Session Token: Not set
  Created: 2024-11-16 12:00:00

Service: Kotak Neo
  Name: default
  API Key: 98765432...
  Username: 9999999999
  Session Token: Not set
  Created: 2024-11-16 12:05:00
```

### Test Breeze Connection
```bash
python manage.py setup_credentials --test-breeze
```

### Test Kotak Neo Connection
```bash
python manage.py setup_credentials --test-kotakneo
```

### Check All Credentials Status
```bash
python manage.py setup_credentials --status
```

Output:
```
=== Credentials Status ===

BREEZE          ✅ Set  (No token)
KOTAKNEO        ✅ Set  (No token)
TRENDLYNE       ⚠️  Not set
```

---

## Troubleshooting

### Error: "Credentials not found in database"

**Solution:**
```bash
# Setup credentials
python manage.py setup_credentials --setup-breeze

# Verify setup
python manage.py setup_credentials --list
```

### Error: "Login failed"

**For Breeze:**
- Verify API Key and API Secret are correct
- Check if session token is expired (remove it and re-login)
- Test credentials: `python manage.py setup_credentials --test-breeze`

**For Kotak Neo:**
- Verify Consumer Key and Consumer Secret
- Verify mobile number and password are correct
- Verify MPIN is correct (must be numeric, usually 4-6 digits)
- Check if account is active

### Error: "Session Token Expired"

```python
from apps.core.models import CredentialStore

# Clear token
cred = CredentialStore.objects.filter(service='breeze').first()
cred.session_token = None
cred.save()

# Re-login
from tools.breeze import BreezeAPI
api = BreezeAPI()
api.login()  # Will obtain new token
```

### Error: "Insufficient Margin"

```python
api = BreezeAPI()
api.login()

# Check available margin
margin = api.get_available_margin()
print(f"Available: ₹{margin:,.2f}")

# Check existing positions
positions = api.get_positions()
for pos in positions:
    print(f"{pos['symbol']}: {pos.get('pnl', 0)}")

api.logout()
```

### Error: "Invalid Symbol"

Kotak Neo requires full instrument names for derivatives:
```python
# Correct
api.place_order(symbol='NIFTY25NOV20000CE', ...)

# Incorrect
api.place_order(symbol='NIFTY', ...)
```

Breeze uses shorter codes. Check the broker's documentation.

---

## Next Steps

1. **Read Full Guide**: See [CREDENTIAL_SETUP_GUIDE.md](CREDENTIAL_SETUP_GUIDE.md)
2. **Implement Strategy**: Use APIs in your trading strategies
3. **Handle Errors**: Implement proper error handling and logging
4. **Monitor Sessions**: Track session tokens and refresh them periodically
5. **Test in Paper Trading**: Always test with small amounts first

---

## Related Files

- **Setup Guide**: `CREDENTIAL_SETUP_GUIDE.md`
- **API Interfaces**: `apps/brokers/interfaces.py`
- **Breeze Wrapper**: `tools/breeze.py`
- **Kotak Neo Wrapper**: `tools/neo.py`
- **Models**: `apps/core/models.py`
- **Management Command**: `apps/core/management/commands/setup_credentials.py`
- **Initialization Scripts**: `scripts/initialize_credentials.py`, `scripts/migrate_old_credentials.py`
