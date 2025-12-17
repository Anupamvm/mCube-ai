# Operations Guide

This document covers daily operations, monitoring, background tasks, and troubleshooting.

---

## Starting the System

You need 5 terminals (or processes) running:

### Terminal 1: Django Server

```bash
cd /path/to/mCube-ai
source venv/bin/activate
python manage.py runserver
```

Access: http://localhost:8000/

### Terminal 2: Redis

```bash
redis-server
```

Verify: `redis-cli ping` should return `PONG`

### Terminal 3: Celery Worker

```bash
cd /path/to/mCube-ai
source venv/bin/activate
celery -A mcube_ai worker --loglevel=info
```

### Terminal 4: Celery Beat (Scheduler)

```bash
cd /path/to/mCube-ai
source venv/bin/activate
celery -A mcube_ai beat --loglevel=info
```

**Warning:** Never run multiple Beat instances - it duplicates tasks!

### Terminal 5: Telegram Bot

```bash
cd /path/to/mCube-ai
source venv/bin/activate
python manage.py run_telegram_bot
```

---

## Stopping the System

Press `Ctrl+C` in each terminal, or kill all at once:

```bash
pkill -f runserver
pkill -f celery
pkill -f redis-server
pkill -f run_telegram_bot
```

---

## Telegram Bot Commands

### System Status

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/status` | System overview |
| `/accounts` | Account balances |
| `/positions` | Active positions |
| `/pnl` | Today's P&L |

### Trading Control

| Command | Description |
|---------|-------------|
| `/pause` | Pause all trading |
| `/resume` | Resume trading |
| `/close <id>` | Close specific position |
| `/closeall` | Emergency close all positions |

### Risk Management

| Command | Description |
|---------|-------------|
| `/risk` | View risk limits and utilization |
| `/help` | List all available commands |
| `/logs` | Recent system events |
| `/pnl_week` | This week's P&L |
| `/position <id>` | Specific position details |

---

## Background Tasks (Celery)

### Task Categories

| Category | Tasks | Frequency |
|----------|-------|-----------|
| **Position Monitoring** | monitor_positions, update_pnl | Every 10-30 sec |
| **Risk Management** | check_risk_limits, circuit_breakers | Every 30-60 sec |
| **Market Data** | update_market_data | Every 5 min |
| **Strategy** | evaluate_entry, evaluate_exit | Scheduled times |
| **Reports** | daily_pnl_report, weekly_summary | EOD/EOW |
| **Trendlyne** | fetch_data, import_data | Daily 8:30 AM |

### Task Schedule

**Position Monitoring:**
- `monitor_all_positions` - Every 10 seconds
- `update_position_pnl` - Every 15 seconds
- `check_exit_conditions` - Every 30 seconds

**Risk Management:**
- `check_risk_limits_all_accounts` - Every 1 minute
- `monitor_circuit_breakers` - Every 30 seconds

**Market Data (9 AM - 3:30 PM, Mon-Fri):**
- `update_live_market_data` - Every 5 minutes
- `update_pre_market_data` - 8:30 AM
- `update_post_market_data` - 3:30 PM
- `fetch_trendlyne_data` - 8:30 AM daily

**Strategy Evaluation:**
- `evaluate_kotak_strangle_entry` - 10:00 AM (Mon, Tue)
- `evaluate_kotak_strangle_exit` - 3:15 PM (Thu, Fri)
- `screen_futures_opportunities` - Every 30 min (9 AM - 2:30 PM)
- `monitor_strangle_delta` - Every 5 min (9 AM - 3:30 PM)

**Reports:**
- `generate_daily_pnl_report` - 4:00 PM (Mon-Fri)
- `send_weekly_summary` - 6:00 PM (Friday)

### Managing Celery

```bash
# Check active tasks
celery -A mcube_ai inspect active

# List registered tasks
celery -A mcube_ai inspect registered

# View scheduled tasks
celery -A mcube_ai inspect scheduled

# Worker stats
celery -A mcube_ai inspect stats

# Clear task queue
celery -A mcube_ai purge
```

### Flower (Web Monitoring)

```bash
pip install flower
celery -A mcube_ai flower
```

Open: http://localhost:5555

---

## Monitoring

### System Health Check

Visit http://localhost:8000/system/test/ to see:
- Database connectivity
- Broker integration status
- Trendlyne data freshness
- Redis/Celery status
- 40+ system tests

### Log Files

**Location:** `logs/mcube_ai.log`

```bash
# Real-time logs
tail -f logs/mcube_ai.log

# Errors only
grep ERROR logs/mcube_ai.log

# Today's logs
grep "$(date +%Y-%m-%d)" logs/mcube_ai.log

# Position-related logs
grep "position" logs/mcube_ai.log

# Order-related logs
grep "order" logs/mcube_ai.log
```

### Django Shell

```python
python manage.py shell

# Check positions
from apps.positions.models import Position
Position.objects.filter(status='ACTIVE').count()

# Check accounts
from apps.accounts.models import BrokerAccount
for acc in BrokerAccount.objects.all():
    print(f"{acc.account_name}: Capital={acc.allocated_capital}, Available={acc.get_available_capital()}")

# Check trading state
from apps.core.trading_state import is_trading_paused
is_trading_paused()

# Check today's P&L
for acc in BrokerAccount.objects.filter(is_active=True):
    print(f"{acc.broker}: {acc.get_today_pnl()}")
```

---

## Daily Routine

### Morning (8:30 AM - 9:15 AM)

1. **Start all services** (Django, Redis, Celery, Telegram)
2. **Check system health** at `/system/test/`
3. **Verify Trendlyne data** was fetched at 8:30 AM
4. **Check broker connectivity** via Telegram `/status`
5. **Review overnight news** affecting positions

### Market Hours (9:15 AM - 3:30 PM)

1. **Monitor positions** via Telegram `/positions`
2. **Watch for alerts** (stop-loss, target, delta)
3. **Approve trades** when prompted via Telegram
4. **Check risk limits** with `/risk` command

### Evening (3:30 PM - 5:00 PM)

1. **Review daily P&L** via `/pnl`
2. **Check daily report** (sent at 4:00 PM)
3. **Review logs** for any errors
4. **Plan for next day**

### Weekly

1. **Friday 6 PM:** Review weekly summary
2. **Check pattern learning** updates
3. **Review strategy performance**
4. **Adjust parameters if needed**

---

## Troubleshooting

### Service Issues

| Issue | Check | Solution |
|-------|-------|----------|
| Django not starting | `python manage.py check` | Fix syntax/import errors |
| Redis not running | `redis-cli ping` | `redis-server` |
| Celery worker down | `celery inspect active` | Restart worker |
| Celery beat issues | Check for duplicate beats | Kill all, restart one |
| Telegram not responding | Check bot token | Verify settings.py |

### Common Errors

**"ModuleNotFoundError"**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**"Redis connection refused"**
```bash
redis-server  # Start Redis
```

**"Database errors"**
```bash
python manage.py migrate
```

**"Unable to configure handler 'file'"**
```bash
mkdir -p logs
```

**"Tasks not executing"**
1. Check worker is running
2. Check Beat is running (only one!)
3. Verify task is registered
4. Check logs for errors

### Broker Issues

| Issue | Solution |
|-------|----------|
| Login failed | Verify credentials: `python manage.py setup_credentials --list` |
| Session expired | Re-setup credentials |
| Order rejected | Check margin, verify instrument name |
| No positions showing | Sync positions from broker |

### Position Issues

| Issue | Solution |
|-------|----------|
| Position not updating | Check Celery worker is running |
| Wrong P&L | Verify current price feed |
| Exit not triggered | Check exit conditions in logs |
| Stuck in PENDING | Check order status with broker |

---

## Production Deployment

### Using Systemd (Linux)

**Worker service** (`/etc/systemd/system/celery-worker.service`):

```ini
[Unit]
Description=Celery Worker
After=network.target redis.service

[Service]
Type=forking
User=mcube
WorkingDirectory=/path/to/mCube-ai
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/celery -A mcube_ai worker --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

**Beat service** (`/etc/systemd/system/celery-beat.service`):

```ini
[Unit]
Description=Celery Beat
After=network.target redis.service

[Service]
Type=simple
User=mcube
WorkingDirectory=/path/to/mCube-ai
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/celery -A mcube_ai beat --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable services:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable celery-worker celery-beat
sudo systemctl start celery-worker celery-beat
```

---

## Emergency Procedures

### Pause All Trading

**Via Telegram:**
```
/pause
```

**Via Django shell:**
```python
from apps.core.trading_state import pause_trading
pause_trading()
```

### Close All Positions

**Via Telegram:**
```
/closeall
```

**Via Django shell:**
```python
from apps.positions.services import close_all_positions
close_all_positions(reason="Emergency close")
```

### Deactivate Account

```python
from apps.accounts.models import BrokerAccount
acc = BrokerAccount.objects.get(broker='KOTAK')
acc.is_active = False
acc.save()
```

### Stop All Tasks

```bash
pkill -f celery
```

---

## Quick Commands Reference

```bash
# Start everything
redis-server &
python manage.py runserver &
celery -A mcube_ai worker --loglevel=info &
celery -A mcube_ai beat --loglevel=info &
python manage.py run_telegram_bot &

# Check status
celery -A mcube_ai inspect active
curl http://localhost:8000/system/test/

# View logs
tail -f logs/mcube_ai.log

# Django shell
python manage.py shell

# Stop everything
pkill -f "runserver|celery|redis|telegram"
```

---

*For system architecture, see [02-ARCHITECTURE.md](02-ARCHITECTURE.md).*
