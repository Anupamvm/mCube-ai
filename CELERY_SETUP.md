# Celery Setup Guide for mCube Trading System

This guide explains how to set up and run Celery for automated task execution in the mCube Trading System.

## Overview

The mCube Trading System uses Celery for automated background tasks including:
- **Position monitoring** (every 10-30 seconds)
- **Strategy evaluation** (scheduled times)
- **Risk limit checks** (every 1 minute)
- **Market data updates** (every 5 minutes)
- **Daily/weekly reports** (EOD/EOW)

## Prerequisites

### 1. Install Redis

Redis is required as the message broker for Celery.

**macOS (using Homebrew):**
```bash
brew install redis
brew services start redis
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

**Verify Redis is running:**
```bash
redis-cli ping
# Should return: PONG
```

### 2. Install Python Dependencies

Install Celery and Redis Python client:
```bash
pip install -r requirements.txt
```

This will install:
- `celery==5.3.4` - Distributed task queue
- `redis==5.0.1` - Redis client for broker/backend

## Configuration

### Celery Settings (Already Configured)

The following files are already configured:

1. **mcube_ai/celery.py** - Main Celery application and Beat schedule
2. **mcube_ai/settings.py** - Celery configuration (Redis URLs, timezone, etc.)
3. **mcube_ai/__init__.py** - Imports Celery app (commented out by default)

### Enable Celery App Import (Optional)

To enable automatic Celery app loading, uncomment lines in `mcube_ai/__init__.py`:

```python
from __future__ import absolute_import, unicode_literals
from .celery import app as celery_app
__all__ = ('celery_app',)
```

## Running Celery

### 1. Start Celery Worker

The worker processes tasks from the queue.

**Development (single worker):**
```bash
celery -A mcube_ai worker --loglevel=info
```

**Production (with concurrency):**
```bash
celery -A mcube_ai worker --loglevel=info --concurrency=4
```

**With specific queues:**
```bash
# Default queue only
celery -A mcube_ai worker -Q celery --loglevel=info

# Specific queues
celery -A mcube_ai worker -Q data,strategies,monitoring --loglevel=info
```

### 2. Start Celery Beat Scheduler

Celery Beat schedules periodic tasks (required for automated trading).

```bash
celery -A mcube_ai beat --loglevel=info
```

### 3. Run Worker + Beat Together (Development Only)

For development, you can run worker and beat together:

```bash
celery -A mcube_ai worker --beat --loglevel=info
```

**⚠️ WARNING:** Never run multiple beat instances - it will duplicate scheduled tasks!

## Task Queues

Tasks are distributed across 5 queues for better performance:

| Queue | Purpose | Tasks |
|-------|---------|-------|
| `data` | Market data updates | fetch_trendlyne_data, update_live_market_data |
| `strategies` | Strategy evaluation | evaluate_kotak_strangle_entry, screen_futures |
| `monitoring` | Position monitoring | monitor_positions, update_pnl, check_exits |
| `risk` | Risk management | check_risk_limits, monitor_circuit_breakers |
| `reports` | Analytics & reports | generate_daily_pnl_report, send_weekly_summary |

## Scheduled Tasks

### Position Monitoring (High Frequency)
- `monitor_all_positions` - Every 10 seconds
- `update_position_pnl` - Every 15 seconds
- `check_exit_conditions` - Every 30 seconds

### Risk Management
- `check_risk_limits_all_accounts` - Every 1 minute
- `monitor_circuit_breakers` - Every 30 seconds

### Market Data
- `update_live_market_data` - Every 5 minutes (9 AM - 3:30 PM, Mon-Fri)
- `update_pre_market_data` - 8:30 AM (Mon-Fri)
- `update_post_market_data` - 3:30 PM (Mon-Fri)
- `fetch_trendlyne_data` - 8:30 AM daily
- `import_trendlyne_data` - 9:00 AM daily

### Strategy Evaluation
- `evaluate_kotak_strangle_entry` - 10:00 AM (Mon, Tue)
- `evaluate_kotak_strangle_exit` - 3:15 PM (Thu, Fri)
- `screen_futures_opportunities` - Every 30 minutes (9 AM - 2:30 PM)
- `check_futures_averaging` - Every 10 minutes (9 AM - 3:30 PM)
- `monitor_strangle_delta` - Every 5 minutes (9 AM - 3:30 PM)

### Reports & Analytics
- `generate_daily_pnl_report` - 4:00 PM (Mon-Fri)
- `update_learning_patterns` - 5:00 PM (Mon-Fri)
- `send_weekly_summary` - 6:00 PM (Friday)

## Testing Celery

### Test Basic Setup

1. **Check Celery worker:**
```bash
celery -A mcube_ai inspect active
```

2. **List registered tasks:**
```bash
celery -A mcube_ai inspect registered
```

3. **Test a simple task:**
```bash
python manage.py shell
>>> from mcube_ai.celery import debug_task
>>> result = debug_task.delay()
>>> result.get()
```

### Test Specific Tasks

```bash
python manage.py shell

# Test position monitoring
>>> from apps.positions.tasks import monitor_all_positions
>>> result = monitor_all_positions.delay()
>>> result.get()

# Test risk limits check
>>> from apps.risk.tasks import check_risk_limits_all_accounts
>>> result = check_risk_limits_all_accounts.delay()
>>> result.get()

# Test daily P&L report
>>> from apps.analytics.tasks import generate_daily_pnl_report
>>> result = generate_daily_pnl_report.delay()
>>> result.get()
```

## Monitoring Celery

### Flower (Web-based monitoring)

Install Flower:
```bash
pip install flower
```

Start Flower:
```bash
celery -A mcube_ai flower
```

Open browser: http://localhost:5555

### View Logs

Logs are written to:
- **Console:** Standard output
- **File:** `logs/mcube_ai.log`

### Check Task Status

```bash
# Active tasks
celery -A mcube_ai inspect active

# Scheduled tasks
celery -A mcube_ai inspect scheduled

# Reserved tasks
celery -A mcube_ai inspect reserved

# Worker stats
celery -A mcube_ai inspect stats
```

## Production Deployment

### Using Systemd (Linux)

Create service files for worker and beat:

**Worker service (`/etc/systemd/system/celery-worker.service`):**
```ini
[Unit]
Description=Celery Worker for mCube Trading System
After=network.target redis.service

[Service]
Type=forking
User=mcube
Group=mcube
WorkingDirectory=/path/to/mCube-ai
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/celery -A mcube_ai worker --loglevel=info --concurrency=4 --pidfile=/var/run/celery/worker.pid
PIDFile=/var/run/celery/worker.pid
Restart=always

[Install]
WantedBy=multi-user.target
```

**Beat service (`/etc/systemd/system/celery-beat.service`):**
```ini
[Unit]
Description=Celery Beat Scheduler for mCube Trading System
After=network.target redis.service

[Service]
Type=simple
User=mcube
Group=mcube
WorkingDirectory=/path/to/mCube-ai
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/celery -A mcube_ai beat --loglevel=info --pidfile=/var/run/celery/beat.pid
PIDFile=/var/run/celery/beat.pid
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable celery-worker celery-beat
sudo systemctl start celery-worker celery-beat
```

### Using Supervisor (Alternative)

Install supervisor:
```bash
pip install supervisor
```

Create config (`/etc/supervisor/conf.d/celery.conf`):
```ini
[program:celery-worker]
command=/path/to/venv/bin/celery -A mcube_ai worker --loglevel=info
directory=/path/to/mCube-ai
user=mcube
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/celery/worker.log

[program:celery-beat]
command=/path/to/venv/bin/celery -A mcube_ai beat --loglevel=info
directory=/path/to/mCube-ai
user=mcube
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/celery/beat.log
```

## Troubleshooting

### Common Issues

**1. ModuleNotFoundError: No module named 'celery'**
```bash
pip install celery==5.3.4 redis==5.0.1
```

**2. Connection Error: Redis not running**
```bash
# Check Redis status
redis-cli ping

# Start Redis
redis-server  # macOS/Linux
brew services start redis  # macOS with Homebrew
sudo systemctl start redis  # Linux
```

**3. Tasks not executing**
- Verify worker is running: `celery -A mcube_ai inspect active`
- Check Beat scheduler is running
- Verify task is registered: `celery -A mcube_ai inspect registered`
- Check logs for errors

**4. Timezone issues**
- Ensure `CELERY_TIMEZONE = 'Asia/Kolkata'` in settings.py
- Verify `CELERY_ENABLE_UTC = False` for IST

**5. Tasks running multiple times**
- Check only ONE beat instance is running
- Stop all beat processes: `pkill -f "celery.*beat"`
- Restart beat: `celery -A mcube_ai beat --loglevel=info`

### Debug Mode

Run worker with debug logging:
```bash
celery -A mcube_ai worker --loglevel=debug
```

Run Beat with debug logging:
```bash
celery -A mcube_ai beat --loglevel=debug
```

## Task Files Created

The following task files have been created:

1. **apps/positions/tasks.py** - Position monitoring tasks (3 tasks)
2. **apps/risk/tasks.py** - Risk management tasks (3 tasks)
3. **apps/strategies/tasks.py** - Strategy evaluation tasks (5 tasks)
4. **apps/analytics/tasks.py** - Analytics and reporting tasks (3 Celery + 5 background tasks)
5. **apps/data/tasks.py** - Market data tasks (7 tasks - already existed)

Total: **21 Celery scheduled tasks** across all apps

## Next Steps

1. **Install Redis and dependencies:**
   ```bash
   brew install redis  # macOS
   pip install -r requirements.txt
   ```

2. **Start Redis:**
   ```bash
   redis-server
   ```

3. **Test Celery configuration:**
   ```bash
   celery -A mcube_ai inspect registered
   ```

4. **Start worker and beat (separate terminals):**
   ```bash
   # Terminal 1: Worker
   celery -A mcube_ai worker --loglevel=info

   # Terminal 2: Beat
   celery -A mcube_ai beat --loglevel=info
   ```

5. **Monitor tasks:**
   - Check worker logs for task execution
   - Verify Telegram notifications are sent
   - Monitor position P&L updates

## Important Notes

⚠️ **Before running in production:**
- Set Telegram bot token and chat ID in settings.py
- Configure broker API credentials
- Set Trendlyne API key
- Review and adjust task schedules if needed
- Set up proper logging and monitoring
- Configure systemd/supervisor for auto-restart

✅ **Celery is fully configured and ready to use!**

For more information, see:
- Celery documentation: https://docs.celeryproject.org/
- Django Celery integration: https://docs.celeryproject.org/en/stable/django/
