# Getting Started with mCube

This guide covers everything you need to set up and run mCube for the first time.

---

## Prerequisites

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| Python | 3.10+ | `python --version` |
| Redis | Latest | `redis-cli ping` |

---

## Quick Install

```bash
# Navigate to project
cd /path/to/mCube-ai

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Run installation script
./install.sh
```

The script handles dependencies, database setup, and creates an admin user.

---

## Manual Install

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
pip install -e ./kotak-neo-api

# 3. Create directories
mkdir -p logs llm_models

# 4. Setup database
python manage.py migrate

# 5. Create admin user
python manage.py createsuperuser
```

---

## Configure Credentials

### Broker APIs

```bash
# ICICI Breeze
python manage.py setup_credentials --setup-breeze

# Kotak Neo
python manage.py setup_credentials --setup-kotakneo

# Verify
python manage.py setup_credentials --list
```

### Telegram Bot

Edit `mcube_ai/settings.py`:
```python
TELEGRAM_BOT_TOKEN = 'your_token'
TELEGRAM_CHAT_ID = 'your_chat_id'
```

---

## Start the System

**Terminal 1: Django**
```bash
python manage.py runserver
```

**Terminal 2: Redis**
```bash
redis-server
```

**Terminal 3: Celery Worker**
```bash
celery -A mcube_ai worker -l info
```

**Terminal 4: Celery Beat**
```bash
celery -A mcube_ai beat -l info
```

**Terminal 5: Telegram Bot**
```bash
python manage.py run_telegram_bot
```

---

## Verify Installation

1. **Django Admin**: http://localhost:8000/admin/
2. **System Health**: http://localhost:8000/system/test/
3. **Telegram**: Send `/status` to your bot

---

## Create Broker Accounts

In Django Admin, create:

**Kotak Account:**
- Broker: KOTAK
- Capital: 60000000 (Rs 6 Cr)
- Max Daily Loss: 200000

**ICICI Account:**
- Broker: ICICI
- Capital: 12000000 (Rs 1.2 Cr)
- Max Daily Loss: 150000

---

## Common Issues

| Issue | Solution |
|-------|----------|
| ModuleNotFoundError | `pip install -r requirements.txt` |
| Redis connection refused | Start `redis-server` |
| Database errors | `python manage.py migrate` |

---

## Next Steps

1. [02-ARCHITECTURE.md](02-ARCHITECTURE.md) - Understand the system
2. [03-TRADING-STRATEGIES.md](03-TRADING-STRATEGIES.md) - Learn trading logic
3. [06-OPERATIONS.md](06-OPERATIONS.md) - Daily operations
