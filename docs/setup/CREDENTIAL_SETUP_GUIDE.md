# Credential Setup Guide for mCube Trading System

This guide explains how to set up and manage API credentials for both ICICI Breeze and Kotak Neo APIs.

## Architecture Overview

### Database Model: `CredentialStore` (apps/core/models.py)

The system uses Django's `CredentialStore` model to securely store credentials:

```python
class CredentialStore(models.Model):
    SERVICE_CHOICES = [
        ('breeze', 'ICICI Breeze'),
        ('trendlyne', 'Trendlyne'),
        ('kotakneo', 'Kotak Neo'),
    ]

    name = models.CharField(max_length=100, default="default")
    service = models.CharField(max_length=50, choices=SERVICE_CHOICES)

    # API credentials
    api_key = models.CharField(max_length=256, null=True, blank=True)
    api_secret = models.CharField(max_length=256, null=True, blank=True)
    session_token = models.CharField(max_length=512, null=True, blank=True)

    # Username/password credentials
    username = models.CharField(max_length=150, null=True, blank=True)
    password = models.CharField(max_length=150, null=True, blank=True)

    # Additional fields
    pan = models.CharField(max_length=20, null=True, blank=True)
    neo_password = models.CharField(max_length=100, null=True, blank=True)
    sid = models.CharField(max_length=256, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_session_update = models.DateTimeField(null=True, blank=True)
```

## Management Commands

### 1. List All Credentials
```bash
python manage.py setup_credentials --list
```

Shows all stored credentials (with sensitive data masked).

### 2. Setup ICICI Breeze
```bash
python manage.py setup_credentials --setup-breeze
```

**Required Information:**
- **API Key**: From ICICI Breeze console (https://api.icicidirect.com)
- **API Secret**: From ICICI Breeze console
- **Session Token** (optional): Can be provided later or prompted on first use

**Example Setup:**
```
Credential name (default: default): breeze_prod
Enter API Key: YOUR_BREEZE_API_KEY
Enter API Secret: YOUR_BREEZE_API_SECRET
Enter Session Token (optional): your_session_token
```

### 3. Setup Kotak Neo
```bash
python manage.py setup_credentials --setup-kotakneo
```

**Required Information:**
- **Consumer Key**: From Kotak Neo API console
- **Consumer Secret**: From Kotak Neo API console
- **Mobile Number**: Your trading account mobile number
- **Password**: Your trading account password
- **MPIN**: Your trading MPIN (for order placement)
- **PAN** (optional): Your PAN number

**Example Setup:**
```
Credential name (default: default): kotakneo_prod
Enter Consumer Key: YOUR_CONSUMER_KEY
Enter Consumer Secret: YOUR_CONSUMER_SECRET
Enter Mobile Number: 9999999999
Enter Password: ••••••••
Enter MPIN: ••••
Enter PAN (optional): ABCDE1234F
```

### 4. Setup Trendlyne
```bash
python manage.py setup_credentials --setup-trendlyne
```

**Required Information:**
- **Email/Username**: Your Trendlyne account email
- **Password**: Your Trendlyne account password

### 5. Check Status
```bash
python manage.py setup_credentials --status
```

Shows which credentials are configured and ready to use.

### 6. Delete Credentials
```bash
python manage.py setup_credentials --delete <service>
```

Example: `python manage.py setup_credentials --delete kotakneo`

### 7. Test Breeze Connection
```bash
python manage.py setup_credentials --test-breeze
```

Validates the Breeze credentials by:
- Attempting login
- Fetching available margin
- Checking open positions

### 8. Test Kotak Neo Connection
```bash
python manage.py setup_credentials --test-kotakneo
```

Validates the Kotak Neo credentials by:
- Attempting login
- Fetching available margin
- Checking open positions

## Using Credentials in Code

### Option 1: Direct Access from Database

```python
from apps.core.models import CredentialStore

# Get Breeze credentials
breeze_creds = CredentialStore.objects.filter(service='breeze').first()
api_key = breeze_creds.api_key
api_secret = breeze_creds.api_secret

# Get Kotak Neo credentials
neo_creds = CredentialStore.objects.filter(service='kotakneo').first()
consumer_key = neo_creds.api_key
consumer_secret = neo_creds.api_secret
mobile_number = neo_creds.username
password = neo_creds.password
mpin = neo_creds.neo_password
```

### Option 2: Using API Wrappers (Recommended)

#### ICICI Breeze
```python
from tools.breeze import BreezeAPI

# Initialize API (loads credentials automatically)
api = BreezeAPI()

# Login
api.login()

# Get margin
margin = api.get_available_margin()  # Returns float

# Check positions
positions = api.get_positions()  # Returns list of dicts

# Place order
order_id = api.place_order(
    symbol='RELIANCE',
    action='B',          # 'B' for BUY, 'S' for SELL
    quantity=1,
    order_type='MKT',    # 'MKT' or 'L' (LIMIT)
    price=0,
    exchange='NFO',      # 'NSE' or 'NFO'
    product='NRML'       # 'NRML', 'MIS', 'CNC'
)

# Logout
api.logout()
```

#### Kotak Neo
```python
from tools.neo import NeoAPI

# Initialize API (loads credentials automatically)
api = NeoAPI()

# Login
api.login()

# Get margin
margin = api.get_available_margin()  # Returns float

# Check positions
positions = api.get_positions()  # Returns list of dicts

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

## API Field Mapping

### ICICI Breeze

| Field | CredentialStore | Description |
|-------|-----------------|-------------|
| API Key | `api_key` | Application key from Breeze console |
| API Secret | `api_secret` | Secret key from Breeze console |
| Session Token | `session_token` | Trading session token (obtained after login) |

### Kotak Neo

| Field | CredentialStore | Description |
|-------|-----------------|-------------|
| Consumer Key | `api_key` | Application ID from Neo console |
| Consumer Secret | `api_secret` | Application secret from Neo console |
| Mobile Number | `username` | Mobile number for login |
| Password | `password` | Login password |
| MPIN | `neo_password` | Trading MPIN for order placement |
| PAN | `pan` | Permanent Account Number (optional) |
| Session ID | `sid` | Session ID (optional, managed by API) |

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

## Database Setup

### Initial Migration
```bash
# Create database tables (if not already done)
python manage.py migrate
```

### Pre-populate Credentials (Django Shell)
```bash
python manage.py shell
```

```python
from apps.core.models import CredentialStore

# Add Breeze credentials
breeze = CredentialStore.objects.create(
    service='breeze',
    name='breeze_prod',
    api_key='YOUR_BREEZE_API_KEY',
    api_secret='YOUR_BREEZE_API_SECRET',
    session_token='YOUR_SESSION_TOKEN'  # Optional
)

# Add Kotak Neo credentials
neo = CredentialStore.objects.create(
    service='kotakneo',
    name='kotakneo_prod',
    api_key='YOUR_CONSUMER_KEY',
    api_secret='YOUR_CONSUMER_SECRET',
    username='9999999999',  # Mobile number
    password='YOUR_PASSWORD',
    neo_password='YOUR_MPIN',
    pan='ABCDE1234F'  # Optional
)

# Add Trendlyne credentials
trendlyne = CredentialStore.objects.create(
    service='trendlyne',
    name='trendlyne_default',
    username='your_email@example.com',
    password='YOUR_PASSWORD'
)

print("Credentials created successfully!")
```

## Security Best Practices

1. **Never commit credentials to Git**
   - Use `.gitignore` to exclude `.env` files
   - Always use environment variables or secure databases

2. **Database Security**
   - Use Django's `django-encrypted-model-fields` for sensitive data
   - Implement role-based access control

3. **Session Management**
   - Session tokens expire after inactivity
   - Implement automatic refresh mechanism
   - Store tokens only in secure, encrypted databases

4. **API Key Rotation**
   - Rotate API keys periodically
   - Never expose keys in logs or error messages
   - Use separate credentials for development and production

## Troubleshooting

### "Credentials not found" Error
```bash
# Check if credentials are in database
python manage.py setup_credentials --list

# If empty, setup credentials
python manage.py setup_credentials --setup-breeze
python manage.py setup_credentials --setup-kotakneo
```

### "Session expired" Error
- Session tokens have a validity period
- The API wrappers automatically prompt for re-login
- Update session token: `python manage.py setup_credentials --setup-breeze`

### Login Failed on Test
```bash
# Debug: Check credentials
python manage.py setup_credentials --list

# Verify credentials are correct
# Re-setup if needed
python manage.py setup_credentials --setup-kotakneo
```

## Integration with Trading Strategies

```python
from apps.core.models import CredentialStore
from tools.breeze import BreezeAPI
from tools.neo import NeoAPI

class TradingStrategy:
    def __init__(self, broker='breeze'):
        if broker == 'breeze':
            self.api = BreezeAPI()
        elif broker == 'kotakneo':
            self.api = NeoAPI()

        # Login automatically
        self.api.login()

    def check_margin(self, required: float) -> bool:
        return self.api.check_margin_sufficient(required)

    def get_positions(self):
        return self.api.get_positions()

    def place_trade(self, symbol, quantity, action):
        return self.api.place_order(
            symbol=symbol,
            quantity=quantity,
            action=action,
            order_type='MKT'
        )
```

## Related Files

- **Model Definition**: `/apps/core/models.py` → `CredentialStore` class
- **Management Command**: `/apps/core/management/commands/setup_credentials.py`
- **Breeze Wrapper**: `/tools/breeze.py` → `BreezeAPI` class
- **Kotak Neo Wrapper**: `/tools/neo.py` → `NeoAPI` class
- **Trendlyne Tool**: `/apps/data/tools/trendlyne.py`
