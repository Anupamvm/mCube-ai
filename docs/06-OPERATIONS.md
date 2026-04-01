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

### Slash Commands (10 commands)

| Command | Description |
|---------|-------------|
| `/start` | Interactive main menu with live header + 12-button grid |
| `/pnl` | P&L summary |
| `/positions` | Open positions |
| `/orders` | Order book view |
| `/margin` | Margin & limits view |
| `/trade` | Manual trade wizard |
| `/history` | Trade history |
| `/analytics` | Performance analytics |
| `/login` | Broker login |
| `/core` | Core trading settings |

> Trading control, risk management, task management, and other operations are handled via inline menu buttons from `/start`, not slash commands.

---

## Management Commands

Django management commands for system administration and testing.

### Core Commands

| Command | Description |
|---------|-------------|
| `python manage.py enable_trading` | Enable/disable trading system |
| `python manage.py trading_status` | View current trading system status |
| `python manage.py install_scheduler` | Install and start background task scheduler |
| `python manage.py stop_scheduler` | Stop all scheduled background tasks |
| `python manage.py setup_credentials` | Setup broker API credentials |

### Broker Commands

| Command | Description |
|---------|-------------|
| `python manage.py breeze_auto_login` | Automated ICICI Breeze login |

### Testing Commands

| Command | Description |
|---------|-------------|
| `python manage.py test_services` | Test all system services (brokers, data, etc.) |
| `python manage.py test_telegram` | Test Telegram bot connectivity |
| `python manage.py test_llm` | Test LLM (Ollama) connectivity |
| `python manage.py test_vllm` | Test vLLM service |

### Data Commands

| Command | Description |
|---------|-------------|
| `python manage.py trendlyne_data_manager` | Manage Trendlyne data imports |
| `python manage.py populate_trendlyne` | Populate Trendlyne data from files |
| `python manage.py import_trendlyne_data` | Import Trendlyne CSV data |
| `python manage.py convert_trendlyne_xlsx` | Convert Trendlyne XLSX to CSV |
| `python manage.py scrape_trendlyne` | Scrape data from Trendlyne website |
| `python manage.py update_market_data` | Update market data cache |
| `python manage.py generate_signals` | Generate trading signals |
| `python manage.py fetch_news` | Fetch latest market news |
| `python manage.py validate_trade` | Validate a trade setup |

### Strategy Commands

| Command | Description |
|---------|-------------|
| `python manage.py setup_trading_schedule` | Configure trading schedule |
| `python manage.py update_schedule_configs` | Update schedule configurations |

### Analytics Commands

| Command | Description |
|---------|-------------|
| `python manage.py run_learning` | Run ML learning pipeline |

### User Commands

| Command | Description |
|---------|-------------|
| `python manage.py setup_users` | Setup user accounts |
| `python manage.py manage_models` | Manage ML models |
| `python manage.py run_telegram_bot` | Start the Telegram bot |

### Usage Examples

```bash
# Check system status
python manage.py trading_status

# Setup credentials interactively
python manage.py setup_credentials --setup-breeze
python manage.py setup_credentials --setup-kotakneo
python manage.py setup_credentials --list

# Test services
python manage.py test_services

# Import Trendlyne data
python manage.py trendlyne_data_manager --import-latest
python manage.py populate_trendlyne --file trendlyne_data/fno_data_2026-01-23.xlsx
```

---

## Background Tasks (Celery)

mCube automates the entire trading day through background tasks managed by Celery Beat. Every task runs at a specific time, in a specific order, to prepare, execute, monitor, and close your trades.

### How a Trading Day Works

Think of your trading day as four phases. Every phase has specific tasks that fire automatically:

### Phase 1: Pre-Market Preparation (7:00 – 9:14 AM)

The system wakes up and gathers everything it needs before the market opens.

| Time | Task | What Happens |
|------|------|--------------|
| **6:45 AM** | `health-check-brokers` | Checks Kotak Neo, ICICI Breeze, and **Redis** connectivity. Redis check uses write-readback test. Results stored in Redis (2h TTL). Any failure sends CRITICAL Telegram alert. |
| **7:00 AM** | `morning-data-sync` | Downloads overnight global market data (SGX Nifty, US indices, Asia), refreshes news, and updates index data. Gives the system a full picture of what happened while Indian markets were closed. |
| **8:50 AM** | `update-pre-market-data` | Fetches pre-open session data — opening indications, pre-open prices, gap-up/gap-down signals. Updates Trendlyne data for delivery percentages and institutional flows. |
| **8:55 AM** | `setup-trading-day` | The system's "morning checklist": verifies broker connectivity (Kotak Neo + ICICI Breeze), checks account margins, validates no stale positions from yesterday, determines if today is tradeable (no holidays, no major events), loads active strategy configs. |
| **8:55 AM** | `review-overnight-positions` | Scans news for negative sentiment on carried positions. |
| **9:00 AM** | `send-morning-briefing` | Consolidated morning Telegram message with overnight summary, pre-market data, and trading plan. |
| **9:00–9:20 AM** | `monitor-opening-volatility` | Every 5 min. Measures VIX and Nifty gap, writes `market_stable_for_trading` flag. |

### Phase 2: Market Open & Strategy Execution (9:15 – 9:55 AM)

Market opens. The system validates the opening, then executes your algorithms.

| Time | Task | What Happens |
|------|------|--------------|
| **9:15 AM** | `start-trading-day` | Validates the opening — checks if open is within expected range, no flash crash, broker sessions live. Activates live data feed and monitoring. |
| **9:15 AM** | `update-live-market-data` | Starts updating live prices every 5 minutes throughout market hours (until 3:30 PM). Feeds data to position monitor and P&L calculations. |
| **9:30 AM** | `screen-futures-opportunities` | **Pre-market futures scan.** Scans the top 50 F&O stocks by volume and runs the 13-factor scoring model on each. This is a *read-only* scan — no orders are placed. Results are cached for the active algorithm at 9:40 AM. **Idempotency guard**: Redis key prevents Beat double-fire on same day. |
| **9:30 AM** | `evaluate-options-strategy` | **Options decision point.** Analyzes VIX, overnight cues, Nifty opening range, news sentiment. Decides: (a) trade today? (b) Strangle or Broken Iron Condor? (c) Strike distances? Sends evaluation to Telegram. |
| **9:40 AM** | `start-options-trade` | **Options execution.** If evaluation passed and you approved via Telegram, places option sell orders (CE + PE, or CE + PE + PE hedge). Creates Position record with stop-loss/target levels. |
| **9:40 AM** | `execute-futures-algorithm` | **Futures execution.** Uses 13-component scoring (315pts → 100 scale) with params: `this_month_volume=1000`, `next_month_volume=800`, `min_score=65`, `top_contracts=50`, `batch_size=2`. Re-validates with live prices, picks TOP candidates above score 65, sends to Telegram with full analysis. On your approval, executes with batched ordering. **Idempotency guard**: Redis key prevents Beat double-fire (manual triggers bypass). |

### Phase 3: Averaging & Active Monitoring (9:40 AM – 3:59 PM)

Your positions are now live. The system monitors everything and manages averaging.

| Time | Task | What Happens |
|------|------|--------------|
| **9:40–9:55** | `batch-options-averaging` | Every 5 min, checks if options position needs averaging. If premium moved against us and conditions met, proposes averaging trade via Telegram. |
| **10:00–10:30** | `batch-options-averaging-10am` | Extended averaging window, same logic as above. |
| **Every 10 min** | `check-futures-averaging` | 9:00 AM to 3:59 PM. Checks if any futures position dropped 1% from entry. Evaluates averaging (max 3 attempts): 20% → 50% → 50% of remaining balance. |
| **Every 15 min** | `monitor-all-strangle-deltas` | 9:00 AM to 3:59 PM. Delta drift monitoring for all strangle positions. |
| **Every minute** | `monitor-and-manage-positions` | **System heartbeat.** Runs every 1 minute (9:00 AM–3:59 PM). Updates real-time P&L for all positions (batched `bulk_create` for MonitorLog), runs SR exit engine with structural pressure checks + catastrophic gap override, updates position monitor dashboard, manages hold flags, checks stop-loss/target, monitors delta for options. Autonomous exits use broker-first close. First broker sync failure sends WARNING alert immediately. |
| **Every minute** | `check-confirmation-timeouts` | Watches for pending Telegram confirmations that exceeded timeout. Triggers revalidation — market conditions may have changed. |
| **Every minute** | `check-risk-limits-all-accounts` | Monitors all accounts against risk limits: daily loss, weekly loss, max drawdown. Includes intraday unrealized drawdown check (10% warning / 15% critical thresholds) and portfolio-level aggregate drawdown across all accounts. Breaches pause trading and send critical alerts. |
| **Every minute** | `monitor-circuit-breakers` | Monitors active circuit breakers: checks cooldown expiry, sends periodic reminders for long-running breakers (>24h), uses Redis-based dedup for notifications. |

### Phase 4: Day Close & Reporting (3:15 – 5:00 PM)

Market is closing. Positions are evaluated, data is finalized, reports are generated.

| Time | Task | What Happens |
|------|------|--------------|
| **3:15 PM** | `alert-open-positions-pre-close` | Summary of all open positions before `close-trading-day` runs. |
| **3:25 PM** | `close-trading-day` | Evaluates all open positions for exit. Applies 50% target rule: positions at ≥50% of target are closed; others may hold overnight. Disables new entries. |
| **3:35 PM** | `update-post-market-data` | Downloads final closing prices, volume, settlement values. Updates all position records with accurate closing P&L. |
| **3:45 PM** | `reconcile-positions-eod` | Post-market broker sync and comparison. Reconciles internal position records against broker data. |
| **4:00 PM** | `generate-daily-pnl-report` | Generates comprehensive P&L report: realized + unrealized, per-position breakdown, strategy-level performance. Sends summary to Telegram. |
| **4:15 PM** | `sync-benchmark-data` | Downloads benchmark index data (Nifty 50, Bank Nifty) for performance comparison charts. |
| **4:30 PM** | `daily-data-aggregation` | Rolls up all trading data into daily summaries: win rate, average P&L, category performance, strategy metrics. |
| **5:00 PM** | `update-equity-curves` | Recalculates portfolio equity curves and NAV for each account. Updates performance tracking charts. |

### Task Categories (6 Categories)

| Category | Color | Tasks | Schedule |
|----------|-------|-------|----------|
| **Market Data** | 🔵 Blue | Morning Sync, Pre-Market, Live Market, Post-Market | Fixed times + recurring during market hours |
| **Strategies** | 🟣 Purple | Setup Day, Start Day, Evaluate Options, Futures Screening | Fixed times (pre-market & market open) |
| **Transactions** | 🟡 Yellow | Options Trade, Options Averaging (2), Futures Algo, Futures Averaging, Close Day | Fixed times + recurring windows |
| **Monitoring** | 🟠 Orange | Position Monitor, Confirmation Timeouts | Every minute during market hours |
| **Risk** | 🔴 Red | Risk Limits, Circuit Breakers | Every minute during market hours |
| **Reports** | 🟢 Green | Daily P&L, Benchmark Sync, Data Aggregation, Equity Curves | Fixed times (4:00–5:00 PM) |

### Algorithm Task Groups

Tasks are organized into algorithm groups. When you toggle an algorithm, these tasks move together:

**Futures Algorithm** — Directional futures trades with 13-factor scoring:
- *Own tasks:* `screen-futures-opportunities` (9:30 AM), `execute-futures-algorithm` (9:40 AM), `check-futures-averaging` (every 10 min)
- *Shared tasks:* `setup-trading-day`, `start-trading-day`, `close-trading-day`
- *Monitoring:* `monitor-and-manage-positions`

**Options Algorithm** — Weekly Nifty Strangle / Broken Iron Condor:
- *Own tasks:* `evaluate-options-strategy` (9:30 AM), `start-options-trade` (9:40 AM), `batch-options-averaging` (9:40–9:55), `batch-options-averaging-10am` (10:00–10:30), `evaluate-kotak-strangle-exit` (callable, not auto-scheduled), `monitor-all-strangle-deltas` (every 15 min)
- *Shared tasks:* `setup-trading-day`, `start-trading-day`, `close-trading-day`
- *Monitoring:* `monitor-and-manage-positions`

> **Shared task rule:** Disabling one algorithm keeps shared tasks active if the other is still running. They only turn off when *both* algorithms are disabled.

### Core Trading Configuration (TradingCoreConfig)

The system uses `TradingCoreConfig` to control trading behavior:

**Position Sizing Modes:**
| Mode | Description |
|------|-------------|
| `TEST` | 1 lot each (safe testing) |
| `MANUAL` | Fixed lots specified by user |
| `AUTO` | System-calculated from broker margin |
| `SIMULATED` | Paper trading (no real orders) |

**Notification Levels:**
| Level | Description |
|-------|-------------|
| `FULL_CONTROL` | Confirm everything via Telegram |
| `SUPERVISED` | Confirm entries/exits only |
| `AUTONOMOUS` | Auto-execute, notifications only |

Access via: http://localhost:8000/system/celery/ → Core Trading Config tab

### Controlling Tasks

| Method | Where | What You Can Do |
|--------|-------|-----------------|
| **Celery Dashboard** | `/system/celery/` | Toggle tasks on/off, customize schedules, view logs, run manually, apply presets, see 24-hour timeline |
| **Telegram Bot** | `/start` → Tasks menu | Toggle tasks, run now, enable/disable categories |
| **API** | `POST /system/toggle-static-task/` | Programmatic toggle with JSON response |

> Click the kebab menu (⋮) on any task in the Celery dashboard to customize its schedule. Changes take effect immediately. Use "Reset All Schedules" to revert to defaults.

### Starting Celery (IMPORTANT)

**CRITICAL**: Always use the custom scheduler to ensure tasks respect enabled/disabled state:

```bash
# Start Celery worker
celery -A mcube_ai worker --loglevel=info

# Start Celery Beat with DB scheduler (REQUIRED)
python -m celery -A mcube_ai beat --scheduler=mcube_ai.celery:DBReloadScheduler --loglevel=info
```

**WARNING**: Never run multiple Beat instances simultaneously! This causes duplicate task execution — duplicate orders, duplicate Telegram messages, double position entries.

The Celery dashboard auto-starts Beat when you toggle tasks (recommended approach).

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
Position.objects.filter(status='OPEN').count()  # OPEN is the active status

# Check accounts
from apps.accounts.models import BrokerAccount
for acc in BrokerAccount.objects.all():
    print(f"{acc.account_name}: Capital={acc.allocated_capital}, Available={acc.get_available_capital()}")

# Check trading state
from apps.core.trading_state import is_trading_paused
is_trading_paused()

# Check today's P&L
for acc in BrokerAccount.objects.filter(is_active=True):
    print(f"{acc.broker}: {acc.get_todays_pnl()}")
```

---

## Daily Routine (What You Should Do)

### Morning (Before 9:15 AM)

1. **Start all services** (Django, Redis, Celery worker, Celery Beat, Telegram bot)
2. **Check system health** at `/system/test/` — verify all 40+ checks pass
3. **Review overnight news** — morning data sync at 7:00 AM gathers global cues
4. **Check broker connectivity** via Telegram `/status` — Kotak Neo + ICICI Breeze should be green
5. **Verify pre-market scan** — futures screening runs at 9:30 AM, check Telegram for scan results

### Market Hours (9:15 AM - 3:30 PM)

1. **Approve trades** — when algorithms send trade suggestions to Telegram, review and approve/reject
2. **Monitor positions** via Telegram `/positions` — the system updates P&L every minute automatically
3. **Watch for alerts** — stop-loss hits, averaging proposals, circuit breakers
4. **Check risk limits** with `/risk` — system monitors automatically, but periodic manual checks are wise

### Evening (3:25 PM - 5:00 PM)

1. **Review close-day actions** — `close-trading-day` runs at 3:25 PM, check what was closed vs held
2. **Check daily report** — sent to Telegram at 4:00 PM with full P&L breakdown
3. **Review logs** for any errors — `tail -f logs/mcube_ai.log`
4. **Equity curves update** at 5:00 PM — check portfolio performance on the dashboard

### Weekly

1. **Review strategy performance** — which algorithm performed better this week
2. **Adjust parameters** — scoring thresholds, strike distances, margin usage
3. **Check Trendlyne data freshness** — ensure fundamental data is up to date
4. **Review and clean up** any stale positions or pending confirmations

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
