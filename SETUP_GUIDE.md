# mCube Trading System - Complete Setup Guide

Step-by-step guide to configure, run, and test the mCube Trading System from scratch.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Database Configuration](#database-configuration)
4. [Configuration Files](#configuration-files)
5. [Running the Application](#running-the-application)
6. [Testing Components](#testing-components)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **OS**: macOS, Linux, or Windows
- **Python**: 3.8 or higher
- **RAM**: 4GB minimum, 8GB recommended
- **Disk**: 2GB free space

### Required Software

Check if you have these installed:

```bash
# Check Python version (should be 3.8+)
python --version

# Check pip
pip --version

# Check Redis (optional for Celery)
redis-cli --version
```

### Install Missing Software

**Python** (if not installed):
```bash
# macOS
brew install python@3.9

# Linux (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install python3.9 python3-pip

# Windows
# Download from python.org
```

**Redis** (for Celery - optional for initial testing):
```bash
# macOS
brew install redis

# Linux (Ubuntu/Debian)
sudo apt-get install redis-server

# Windows
# Use WSL or download from https://redis.io
```

---

## Initial Setup

### Step 1: Navigate to Project Directory

```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate

# Windows:
# venv\Scripts\activate

# You should see (venv) in your terminal prompt
```

### Step 3: Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip

# Install all requirements
pip install -r requirements.txt

# Install Kotak Neo API (local package included in repo)
pip install -e ./kotak-neo-api

# This will install:
# - Django 4.2.7
# - Celery 5.3.4 + Redis
# - pandas, numpy, ta (for analysis)
# - python-telegram-bot (for alerts)
# - kotak-neo-api (local editable install)
# - All other dependencies
```

**Expected output:**
```
Successfully installed Django-4.2.7 celery-5.3.4 redis-5.0.1 pandas-2.2.0 ...
Successfully installed neo-api-client-1.2.0
```

### Step 4: Verify Installation

```bash
# Check Django installation
python -m django --version
# Should show: 4.2.7

# Check Celery installation
celery --version
# Should show: 5.3.4

# List installed packages
pip list
```

---

## Database Configuration

### Step 5: Create Database Tables

```bash
# Create migrations for all apps
python manage.py makemigrations

# Apply migrations (create database tables)
python manage.py migrate

# You should see:
# Running migrations:
#   Applying contenttypes.0001_initial... OK
#   Applying auth.0001_initial... OK
#   Applying accounts.0001_initial... OK
#   Applying positions.0001_initial... OK
#   ...
```

### Step 6: Create Superuser (Admin)

```bash
# Create admin user for Django admin interface
python manage.py createsuperuser

# Follow prompts:
# Username: admin
# Email: your_email@example.com
# Password: (your secure password)
# Password (again): (confirm password)
```

### Step 7: Verify Database

```bash
# Check if database file was created
ls -lh db.sqlite3

# Should show file size (e.g., 200KB)

# Test database access
python manage.py shell

# In Python shell:
>>> from apps.accounts.models import BrokerAccount
>>> BrokerAccount.objects.count()
0  # Expected (no accounts created yet)
>>> exit()
```

---

## Configuration Files

### Step 8: Configure Settings

Edit `mcube_ai/settings.py` with your actual credentials:

```python
# =============================================================================
# TELEGRAM BOT CONFIGURATION
# =============================================================================

# Get bot token from @BotFather on Telegram
TELEGRAM_BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'  # Replace with actual token
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID_HERE'      # Replace with your chat ID

# =============================================================================
# MARKET DATA CONFIGURATION
# =============================================================================

# Get API key from Trendlyne
TRENDLYNE_API_KEY = 'YOUR_TRENDLYNE_API_KEY'  # Replace with actual key
```

**How to get Telegram credentials:**

1. **Bot Token**:
   - Open Telegram, search for `@BotFather`
   - Send `/newbot` command
   - Follow prompts to create bot
   - Copy the token (format: `1234567890:ABCdefGHI...`)

2. **Chat ID**:
   - Search for `@userinfobot` on Telegram
   - Send any message
   - Copy your chat ID (a number like `123456789`)

**Alternative: Use Environment Variables (Recommended for Production)**

Create `.env` file in project root:
```bash
# Create .env file
nano .env
```

Add these lines:
```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHI...
TELEGRAM_CHAT_ID=123456789
TRENDLYNE_API_KEY=your_api_key_here
```

**Important**: Add `.env` to `.gitignore`:
```bash
echo ".env" >> .gitignore
```

### Step 9: Create Required Directories

```bash
# Create logs directory (if not exists)
mkdir -p logs

# Create LLM models directory (if not exists)
mkdir -p llm_models

# Verify directories
ls -la | grep -E "logs|llm_models"
```

---

## Running the Application

### Step 10: Start Django Development Server

```bash
# Start Django server
python manage.py runserver

# You should see:
# Starting development server at http://127.0.0.1:8000/
# Quit the server with CONTROL-C
```

Open browser and visit:
- **Main app**: http://127.0.0.1:8000/
- **Admin panel**: http://127.0.0.1:8000/admin/

Login to admin with credentials from Step 6.

**Keep this terminal running** and open new terminals for next steps.

### Step 11: Start Redis (Optional - for Celery)

**If you want to test background tasks:**

```bash
# Terminal 2: Start Redis server
redis-server

# You should see:
# Ready to accept connections
```

### Step 12: Start Celery Worker (Optional)

**If you want to test background tasks:**

```bash
# Terminal 3: Start Celery worker
celery -A mcube_ai worker --loglevel=info

# You should see:
# [tasks]
#   . apps.positions.tasks.monitor_all_positions
#   . apps.risk.tasks.check_risk_limits_all_accounts
#   ...
# celery@hostname ready.
```

### Step 13: Start Celery Beat (Optional)

**If you want to test scheduled tasks:**

```bash
# Terminal 4: Start Celery Beat scheduler
celery -A mcube_ai beat --loglevel=info

# You should see:
# Scheduler: Starting...
# beat: Starting...
```

### Step 14: Start Telegram Bot (Optional)

**If you want to test manual controls:**

```bash
# Terminal 5: Start Telegram bot
python manage.py run_telegram_bot

# You should see:
# Starting Telegram bot...
# Bot is polling for updates...
```

Now send `/start` to your bot on Telegram to test.

---

## Testing Components

### Test 1: Create Broker Accounts

**Via Django Admin:**

1. Visit http://127.0.0.1:8000/admin/
2. Login with your credentials
3. Click **Broker accounts** → **Add broker account**
4. Fill in details:
   ```
   Account Name: Kotak Primary
   Broker: KOTAK
   Account Number: TEST001
   Is Active: ✓
   Current Balance: 60000000 (₹6 Cr)
   Margin Available: 30000000 (₹3 Cr)
   Max Daily Loss: 30000
   Max Weekly Loss: 100000
   ```
5. Click **Save**

6. Create second account:
   ```
   Account Name: ICICI Futures
   Broker: ICICI
   Account Number: TEST002
   Is Active: ✓
   Current Balance: 12000000 (₹1.2 Cr)
   Margin Available: 6000000 (₹60 L)
   Max Daily Loss: 12000
   Max Weekly Loss: 40000
   ```
7. Click **Save**

**Via Django Shell:**

```bash
python manage.py shell
```

```python
from apps.accounts.models import BrokerAccount
from decimal import Decimal

# Create Kotak account
kotak = BrokerAccount.objects.create(
    account_name="Kotak Primary",
    broker="KOTAK",
    account_number="TEST001",
    is_active=True,
    current_balance=Decimal('60000000'),
    margin_available=Decimal('30000000'),
    max_daily_loss=Decimal('30000'),
    max_weekly_loss=Decimal('100000')
)
print(f"Created: {kotak}")

# Create ICICI account
icici = BrokerAccount.objects.create(
    account_name="ICICI Futures",
    broker="ICICI",
    account_number="TEST002",
    is_active=True,
    current_balance=Decimal('12000000'),
    margin_available=Decimal('6000000'),
    max_daily_loss=Decimal('12000'),
    max_weekly_loss=Decimal('40000')
)
print(f"Created: {icici}")

# Verify
print(f"Total accounts: {BrokerAccount.objects.count()}")

exit()
```

### Test 2: Test Telegram Bot Commands

**If bot is running**, send these commands in Telegram:

```
/start       # Should get welcome message
/help        # Should show all commands
/status      # Should show system status
/accounts    # Should show your 2 test accounts
/positions   # Should show "No active positions"
/risk        # Should show risk limits
/pnl         # Should show today's P&L (₹0)
```

### Test 3: Test Strategy Entry (Dry Run)

```bash
python manage.py shell
```

```python
from apps.accounts.models import BrokerAccount
from apps.strategies.strategies.kotak_strangle import execute_kotak_strangle_entry

# Get Kotak account
kotak = BrokerAccount.objects.get(account_name="Kotak Primary")

# Test entry workflow (will use placeholder data)
result = execute_kotak_strangle_entry(kotak)

# Check result
print(f"Success: {result['success']}")
print(f"Message: {result['message']}")

# Note: This will likely fail at some step due to placeholder data
# (e.g., fetching actual spot price, premiums from broker API)
# But it tests the workflow logic

exit()
```

### Test 4: Test Risk Limit Checking

```bash
python manage.py shell
```

```python
from apps.accounts.models import BrokerAccount
from apps.risk.services.risk_manager import check_risk_limits

# Get account
kotak = BrokerAccount.objects.get(account_name="Kotak Primary")

# Check risk limits
risk_check = check_risk_limits(kotak)

print(f"All clear: {risk_check['all_clear']}")
print(f"Breached limits: {len(risk_check['breached_limits'])}")
print(f"Warnings: {len(risk_check['warnings'])}")
print(f"Message: {risk_check['message']}")

exit()
```

### Test 5: Test Celery Task Manually

**If Celery worker is running:**

```bash
python manage.py shell
```

```python
from apps.positions.tasks import monitor_all_positions
from apps.risk.tasks import check_risk_limits_all_accounts

# Trigger task immediately (don't wait for schedule)
result1 = monitor_all_positions.delay()
print(f"Task ID: {result1.id}")
print(f"Task status: {result1.status}")

# Wait a moment and check result
import time
time.sleep(2)
print(f"Result: {result1.get()}")

# Test risk check task
result2 = check_risk_limits_all_accounts.delay()
time.sleep(2)
print(f"Risk check result: {result2.get()}")

exit()
```

### Test 6: Test Trading State (Pause/Resume)

```bash
python manage.py shell
```

```python
from apps.core.trading_state import is_trading_paused, pause_trading, resume_trading, get_trading_state

# Check current state
print(f"Trading paused: {is_trading_paused()}")

# Pause trading
pause_trading(reason="Testing pause functionality", paused_by="MANUAL_TEST")
print(f"Trading paused: {is_trading_paused()}")

# Get full state
state = get_trading_state()
print(f"State: {state}")

# Resume trading
resume_trading()
print(f"Trading paused: {is_trading_paused()}")

exit()
```

---

## Testing Checklist

Use this checklist to verify everything is working:

- [ ] **Python 3.8+** installed and accessible
- [ ] **Virtual environment** created and activated
- [ ] **Dependencies** installed from requirements.txt
- [ ] **Database migrations** applied successfully
- [ ] **Superuser** created for admin access
- [ ] **Django server** running at http://127.0.0.1:8000/
- [ ] **Admin panel** accessible and can login
- [ ] **Two broker accounts** created (Kotak + ICICI)
- [ ] **Redis** running (optional, for Celery)
- [ ] **Celery worker** running (optional)
- [ ] **Celery beat** running (optional)
- [ ] **Telegram bot** running and responding (optional)
- [ ] **Telegram commands** working (/start, /status, /accounts)
- [ ] **Risk limit checks** working
- [ ] **Trading state** (pause/resume) working
- [ ] **Logs directory** exists and logs are being written

---

## Troubleshooting

### Issue 1: "No module named 'celery'"

**Solution:**
```bash
# Make sure virtual environment is activated
source venv/bin/activate  # macOS/Linux

# Reinstall dependencies
pip install -r requirements.txt
```

### Issue 2: "Redis connection refused"

**Solution:**
```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# If not running, start Redis
redis-server

# Or use brew services (macOS)
brew services start redis
```

### Issue 3: "TELEGRAM_BOT_TOKEN not configured"

**Solution:**
```python
# Edit mcube_ai/settings.py
TELEGRAM_BOT_TOKEN = 'your_actual_token_here'
TELEGRAM_CHAT_ID = 'your_actual_chat_id_here'

# Or use .env file (better)
# Create .env and add:
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Issue 4: "Migration failed"

**Solution:**
```bash
# Delete database and start fresh
rm db.sqlite3

# Delete migration files (keep __init__.py)
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete

# Recreate migrations
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

### Issue 5: "Permission denied" for logs directory

**Solution:**
```bash
# Create logs directory with proper permissions
mkdir -p logs
chmod 755 logs

# Create a test log file
touch logs/mcube_ai.log
chmod 644 logs/mcube_ai.log
```

### Issue 6: Celery tasks not executing

**Solution:**
```bash
# Check if Celery worker is running
ps aux | grep celery

# Check if tasks are registered
celery -A mcube_ai inspect registered

# Check if Beat is running
ps aux | grep "celery.*beat"

# Restart everything
pkill -f celery  # Kill all celery processes
celery -A mcube_ai worker --loglevel=info &
celery -A mcube_ai beat --loglevel=info &
```

### Issue 7: Telegram bot not responding

**Solution:**
```bash
# Test bot token
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe

# Should return bot info
# If error, token is invalid

# Check if bot is running
ps aux | grep run_telegram_bot

# Restart bot
python manage.py run_telegram_bot
```

### Issue 8: "ImportError: No module named 'apps'"

**Solution:**
```bash
# Make sure you're in project root
pwd
# Should be: /Users/anupammangudkar/Projects/mCube-ai/mCube-ai

# Check PYTHONPATH
echo $PYTHONPATH

# If needed, add project to path
export PYTHONPATH="${PYTHONPATH}:/Users/anupammangudkar/Projects/mCube-ai/mCube-ai"
```

---

## Quick Start Commands

Once everything is set up, use these commands to start the system:

**Terminal 1 - Django:**
```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai
source venv/bin/activate
python manage.py runserver
```

**Terminal 2 - Redis:**
```bash
redis-server
```

**Terminal 3 - Celery Worker:**
```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai
source venv/bin/activate
celery -A mcube_ai worker --loglevel=info
```

**Terminal 4 - Celery Beat:**
```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai
source venv/bin/activate
celery -A mcube_ai beat --loglevel=info
```

**Terminal 5 - Telegram Bot:**
```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai
source venv/bin/activate
python manage.py run_telegram_bot
```

**Stop all:**
```bash
# Press Ctrl+C in each terminal
# Or kill all processes:
pkill -f runserver
pkill -f celery
pkill -f redis-server
pkill -f run_telegram_bot
```

---

## Next Steps

After completing setup:

1. **Configure Broker API Credentials**
   - Add Kotak Neo API credentials
   - Add ICICI Breeze API credentials
   - Test broker connectivity

2. **Test Strategies with Paper Trading**
   - Enable PAPER_TRADING mode in settings
   - Test Kotak Strangle strategy
   - Test ICICI Futures strategy

3. **Set Up Production Deployment**
   - Use PostgreSQL instead of SQLite
   - Set up proper logging with rotation
   - Configure systemd services
   - Set up monitoring with Flower

4. **Enable Real Trading**
   - Disable paper trading mode
   - Start with small capital
   - Monitor closely for first few trades

---

## Helpful Commands Reference

```bash
# Django
python manage.py runserver          # Start development server
python manage.py shell               # Open Django shell
python manage.py makemigrations      # Create migrations
python manage.py migrate             # Apply migrations
python manage.py createsuperuser     # Create admin user
python manage.py test                # Run tests

# Celery
celery -A mcube_ai worker --loglevel=info      # Start worker
celery -A mcube_ai beat --loglevel=info        # Start beat
celery -A mcube_ai inspect active              # Check active tasks
celery -A mcube_ai inspect registered          # List registered tasks
celery -A mcube_ai purge                       # Clear all tasks

# Telegram Bot
python manage.py run_telegram_bot              # Start bot

# Database
python manage.py dbshell                       # Open database shell
sqlite3 db.sqlite3                             # Access SQLite directly

# Logs
tail -f logs/mcube_ai.log                      # Watch logs
grep ERROR logs/mcube_ai.log                   # Find errors
grep "CELERY TASK" logs/mcube_ai.log           # Find task executions
```

---

## Support

For issues or questions:

1. Check logs: `tail -f logs/mcube_ai.log`
2. Check Telegram for alerts
3. Review documentation:
   - CELERY_SETUP.md - Celery configuration
   - TELEGRAM_BOT_GUIDE.md - Bot commands
   - LOGGING_AND_ERROR_HANDLING.md - Logging guide

---

**Setup Complete! Your mCube Trading System is ready for testing.**
