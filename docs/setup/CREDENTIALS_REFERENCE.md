# mCube Trading System - Credentials Reference

This document provides a quick reference for all credentials configured in the system.

## Overview

The system uses **two credential storage mechanisms**:

1. **APICredential** model (legacy) - Linked to BrokerAccount
2. **CredentialStore** model (current) - Used by broker API wrappers

## Automatic Setup

When you run `./install.sh`, all credentials are **automatically configured**. You don't need to manually set them up after installation.

## Configured Credentials

### 1. Kotak Neo (Options Trading)

**Account Details:**
- Account Number: AAQHA1835B
- PAN: AAQHA1835B
- Allocated Capital: ₹6.0 Crores
- Strategy: Weekly Nifty Strangle

**API Credentials (CredentialStore):**
- Service: `kotakneo`
- Name: `default`
- Consumer Key: NkmJfGnAehLpdDm3wSPFR7iCMj4a
- Consumer Secret: H8Q60_oBa2PkSOBJXnk7zbOvGqUa
- Username (PAN): **AAQHA1835B** ← Used for login
- Password: Anupamvm2@
- MPIN: Anupamvm2@
- PAN: AAQHA1835B
- Session Token: 284321

**Important:** Kotak Neo uses PAN (AAQHA1835B) as the username for login, NOT mobile number.

### 2. ICICI Breeze (Futures Trading)

**Account Details:**
- Account Number: 52780531
- Allocated Capital: ₹1.2 Crores
- Strategy: LLM-validated Futures

**API Credentials (CredentialStore):**
- Service: `breeze`
- Name: `default`
- API Key: 6561_m2784f16J&R88P3429@66Y89^46
- API Secret: l6_(162788u1p629549_)499O158881c
- Session Token: 52780531

### 3. Trendlyne (Market Data)

**Credentials (CredentialStore):**
- Service: `trendlyne`
- Name: `default`
- Email: avmgp.in@gmail.com
- Password: Anupamvm1!

## Credential Management Commands

### Check Status
```bash
python manage.py setup_credentials --status
```

### List All Credentials
```bash
python manage.py setup_credentials --list
```

### Manual Setup (if needed)

**Setup Kotak Neo:**
```bash
python manage.py setup_credentials --setup-kotakneo
```

**Setup ICICI Breeze:**
```bash
python manage.py setup_credentials --setup-breeze
```

**Setup Trendlyne:**
```bash
python manage.py setup_credentials --setup-trendlyne
```

### Test Connections

**Test Kotak Neo:**
```bash
python manage.py setup_credentials --test-kotakneo
```

**Test ICICI Breeze:**
```bash
python manage.py setup_credentials --test-breeze
```

## Important Notes

1. **Kotak Neo Login**: Kotak Neo uses **PAN (AAQHA1835B)** as the username for login, NOT mobile number. This is automatically configured in `install.sh`.

2. **Session Tokens**: Session tokens may expire. When they do:
   - For Kotak Neo: The API will automatically re-authenticate using mobile + password + MPIN
   - For ICICI Breeze: You may need to refresh the session token manually

3. **Security**:
   - All credentials are stored in the database
   - Never commit credentials to git
   - The `install.sh` script contains credentials - keep it secure

4. **Paper Trading**: Both accounts start in paper trading mode (`is_paper_trading=True`)
   - This prevents real trades until you're ready
   - To enable live trading, update via Django admin

## Credential Flow

```
install.sh execution
    ↓
Creates BrokerAccount records
    ↓
Creates APICredential records (legacy)
    ↓
Creates CredentialStore records (current)
    ↓
Broker API wrappers use CredentialStore
```

## Troubleshooting

### "No credentials found" error
```bash
# Re-run the credential setup section of install.sh
python manage.py shell <<'EOF'
from apps.core.models import CredentialStore

# Recreate Kotak Neo
CredentialStore.objects.update_or_create(
    service='kotakneo',
    name='default',
    defaults={
        'api_key': 'NkmJfGnAehLpdDm3wSPFR7iCMj4a',
        'api_secret': 'H8Q60_oBa2PkSOBJXnk7zbOvGqUa',
        'username': '9890688965',
        'password': 'Anupamvm2@',
        'neo_password': 'Anupamvm2@',
        'pan': 'AAQHA1835B',
    }
)
print('✓ Kotak Neo credentials restored')
EOF
```

### "Login failed" or "PAN needed" error
Kotak Neo requires PAN (not mobile number) as username. The PAN is hardcoded in `install.sh` as **AAQHA1835B**. If you see this error, run:
```bash
python manage.py shell -c "from apps.core.models import CredentialStore; c = CredentialStore.objects.get(service='kotakneo'); c.username = 'AAQHA1835B'; c.save(); print('✓ Fixed - PAN set as username')"
```

## System Test

To verify all credentials are working:
```bash
python manage.py test_services
```

This will test:
- Margin management
- Position creation
- Risk limits
- Expiry selection
- All core business logic

---

Last Updated: 2025-11-17
