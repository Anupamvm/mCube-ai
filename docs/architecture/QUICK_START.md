# Quick Start Checklist

Fast setup guide for the mCube Trading System. For detailed instructions, see [SETUP_GUIDE.md](SETUP_GUIDE.md).

---

## Prerequisites (5 minutes)

```bash
# Check Python version (need 3.8+)
python --version

# Install Redis (optional, for Celery)
brew install redis  # macOS
```

---

## Setup (10 minutes)

```bash
# 1. Navigate to project
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -e ./kotak-neo-api  # Kotak Neo API (local package)

# 4. Setup database
python manage.py migrate

# 5. Create admin user
python manage.py createsuperuser
# Username: admin
# Password: (your choice)

# 6. Create directories
mkdir -p logs llm_models
```

---

## Configure (5 minutes)

**Edit `mcube_ai/settings.py`:**

```python
# Line 189-190
TELEGRAM_BOT_TOKEN = 'YOUR_BOT_TOKEN'  # Get from @BotFather
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID'      # Get from @userinfobot
```

**Or use `.env` file (recommended):**

```bash
# Create .env
cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
EOF
```

---

## Run (5 separate terminals)

### Terminal 1: Django Server
```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai
source venv/bin/activate
python manage.py runserver
```
**Open**: http://127.0.0.1:8000/admin/

### Terminal 2: Redis (Optional)
```bash
redis-server
```

### Terminal 3: Celery Worker (Optional)
```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai
source venv/bin/activate
celery -A mcube_ai worker -l info
```

### Terminal 4: Celery Beat (Optional)
```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai
source venv/bin/activate
celery -A mcube_ai beat -l info
```

### Terminal 5: Telegram Bot (Optional)
```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai
source venv/bin/activate
python manage.py run_telegram_bot
```

---

## Test (5 minutes)

### 1. Create Test Accounts

Visit http://127.0.0.1:8000/admin/ and login.

**Create 2 accounts**:

**Kotak Account:**
- Account Name: `Kotak Primary`
- Broker: `KOTAK`
- Account Number: `TEST001`
- Is Active: ✓
- Current Balance: `60000000` (₹6 Cr)
- Margin Available: `30000000` (₹3 Cr)
- Max Daily Loss: `30000`
- Max Weekly Loss: `100000`

**ICICI Account:**
- Account Name: `ICICI Futures`
- Broker: `ICICI`
- Account Number: `TEST002`
- Is Active: ✓
- Current Balance: `12000000` (₹1.2 Cr)
- Margin Available: `6000000` (₹60 L)
- Max Daily Loss: `12000`
- Max Weekly Loss: `40000`

### 2. Test Telegram Bot

Send to your bot on Telegram:
```
/start      → Should get welcome message
/status     → Should show system status
/accounts   → Should show 2 test accounts
/positions  → Should show no active positions
/risk       → Should show risk limits
```

### 3. Test Django Shell

```bash
python manage.py shell
```

```python
# Check accounts created
from apps.accounts.models import BrokerAccount
print(f"Accounts: {BrokerAccount.objects.count()}")

# Test trading state
from apps.core.trading_state import is_trading_paused
print(f"Trading paused: {is_trading_paused()}")

exit()
```

---

## Verification Checklist

- [ ] Python 3.8+ installed
- [ ] Virtual environment activated (see `(venv)` in prompt)
- [ ] Dependencies installed (no errors)
- [ ] Database migrated (tables created)
- [ ] Admin user created
- [ ] Django server running at http://127.0.0.1:8000/
- [ ] Can login to admin panel
- [ ] 2 broker accounts created
- [ ] Telegram bot responding to `/start`
- [ ] All 5 terminals running (if using Celery)

---

## Common Issues

**Issue**: `ModuleNotFoundError: No module named 'celery'`
```bash
source venv/bin/activate  # Activate venv first!
pip install -r requirements.txt
```

**Issue**: `Redis connection refused`
```bash
redis-server  # Start Redis in separate terminal
```

**Issue**: Telegram bot not responding
- Check bot token is correct in settings.py
- Check bot is running: `ps aux | grep run_telegram_bot`

**Issue**: Database errors
```bash
rm db.sqlite3  # Delete database
python manage.py migrate  # Recreate
python manage.py createsuperuser  # Recreate admin
```

---

## Stop Everything

```bash
# In each terminal, press Ctrl+C

# Or kill all processes:
pkill -f runserver
pkill -f celery
pkill -f redis-server
pkill -f run_telegram_bot
```

---

## Next Steps

1. **Read Full Documentation**:
   - [SETUP_GUIDE.md](SETUP_GUIDE.md) - Detailed setup
   - [CELERY_SETUP.md](CELERY_SETUP.md) - Background tasks
   - [TELEGRAM_BOT_GUIDE.md](TELEGRAM_BOT_GUIDE.md) - Bot commands
   - [LOGGING_AND_ERROR_HANDLING.md](LOGGING_AND_ERROR_HANDLING.md) - Monitoring

2. **Configure Broker APIs**:
   - Add Kotak Neo credentials
   - Add ICICI Breeze credentials
   - Test connectivity

3. **Test with Paper Trading**:
   - Enable PAPER_TRADING mode
   - Test strategies
   - Verify logic

4. **Production Deployment**:
   - Use PostgreSQL
   - Set up systemd services
   - Configure monitoring

---

## Helpful Commands

```bash
# View logs
tail -f logs/mcube_ai.log

# Django shell
python manage.py shell

# Check Celery tasks
celery -A mcube_ai inspect registered

# Check active Celery tasks
celery -A mcube_ai inspect active

# Clear Celery queue
celery -A mcube_ai purge
```

---

**Total Time**: ~30 minutes for complete setup and testing

**For detailed explanations**, see [SETUP_GUIDE.md](SETUP_GUIDE.md)
