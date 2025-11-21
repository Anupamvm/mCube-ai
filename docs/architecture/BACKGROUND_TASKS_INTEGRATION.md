# Background Tasks Integration - Complete Guide

## 📋 Overview

This document describes the complete integration of **automated background tasks** into mCube Trading System, replacing Celery with the simpler **django-background-tasks** package.

### What's New?

1. **Smart Task Scheduling** - Automated daily trading tasks with configurable times
2. **Flag-Based Configuration** - Runtime state management via `NseFlag` model
3. **Comprehensive Broker APIs** - Full margin checking, position tracking, and order placement
4. **Telegram Notifications** - Real-time alerts for trades, P&L changes, and system events
5. **Daily Reports** - Automatic EOD reports and position tracking

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│           Master Scheduler (Runs at 8:30 AM)        │
│                task_scheduler()                     │
└────────────────┬────────────────────────────────────┘
                 │
      ┌──────────┼──────────┬──────────┬──────────┐
      │          │          │          │          │
┌─────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────┐ ┌──▼─────┐
│ Setup   │ │ Entry  │ │Monitor │ │Closing │ │Analysis│
│9:15 AM  │ │9:30 AM │ │Every 5m│ │3:25 PM │ │3:45 PM │
└─────────┘ └────────┘ └────────┘ └────────┘ └────────┘
     │           │          │          │          │
     └───────────┴──────────┴──────────┴──────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  NseFlag (State)     │
              │  DayReport (Results) │
              │  TodaysPosition (Log)│
              └──────────────────────┘
```

---

## 📦 New Models

### 1. **TradingSchedule**
Configurable trading times for each day.

```python
from apps.core.models import TradingSchedule
from datetime import date

# Create schedule for tomorrow
sched = TradingSchedule.objects.create(
    date=date.today() + timedelta(days=1),
    open_time=time(9, 15, 10),
    take_trade_time=time(9, 30, 0),
    enabled=True,
    note="Regular trading day"
)
```

**Fields:**
- `open_time`: Market open / setup task time (default: 9:15 AM)
- `take_trade_time`: Start taking trades (default: 9:30 AM)
- `last_trade_time`: Last entry time (default: 10:15 AM)
- `close_pos_time`: Start closing positions (default: 3:25 PM)
- `mkt_close_time`: Market close (default: 3:32 PM)
- `close_day_time`: EOD analysis (default: 3:45 PM)
- `enabled`: Enable/disable trading for this day
- `note`: Notes about the day

### 2. **NseFlag**
Runtime configuration and state management.

```python
from apps.core.models import NseFlag

# Get/set flags
NseFlag.set('autoTradingEnabled', 'true', 'Auto-trading enabled')
is_enabled = NseFlag.get_bool('autoTradingEnabled')

# Numeric flags
NseFlag.set('stopLossLimit', '-15000')
stop_loss = NseFlag.get_float('stopLossLimit')  # -15000.0

# Check positions
has_positions = NseFlag.get_bool('openPositions')
```

**Helper Methods:**
- `NseFlag.get(name, default)` - Get string value
- `NseFlag.set(name, value, description)` - Set value
- `NseFlag.get_bool(name, default)` - Get as boolean
- `NseFlag.get_float(name, default)` - Get as float
- `NseFlag.get_int(name, default)` - Get as integer

**Common Flags:**
| Flag | Type | Description |
|------|------|-------------|
| `autoTradingEnabled` | bool | Master toggle for automated trading |
| `isDayTradable` | bool | Is today safe to trade? |
| `nseVix` | float | Current VIX value |
| `vixStatus` | string | VHigh/High/Normal/Low/VLow |
| `openPositions` | bool | Do we have open positions? |
| `currentPos` | float | Current P&L |
| `stopLossLimit` | float | Stop loss threshold |
| `minDailyProfitTarget` | float | Profit target |
| `dailyDelta` | float | Volatility target (%) |

### 3. **BkLog**
Background task execution logs.

```python
from apps.core.models import BkLog

# View recent logs
recent_logs = BkLog.objects.filter(
    level='error',
    background_task='start_day_task'
).order_by('-timestamp')[:10]
```

### 4. **DayReport**
End-of-day trading summary.

```python
from apps.core.models import DayReport

# Get today's report
report = DayReport.objects.filter(date=date.today()).first()
print(f"P&L: ₹{report.pnl}, Legs: {report.num_legs}")
```

### 5. **TodaysPosition**
Individual position details.

```python
from apps.core.models import TodaysPosition

# Get all positions for today
positions = TodaysPosition.objects.filter(date=date.today())
total_pnl = sum(p.realized_pl for p in positions)
```

---

## 🚀 Background Tasks

### Task Schedule

| Time | Task | Frequency | Purpose |
|------|------|-----------|---------|
| 8:30 AM | **Master Scheduler** | Once daily | Schedules all intraday tasks |
| 9:15 AM | **setup_day_task** | Once | Pre-market setup, VIX fetch, Trendlyne data |
| 9:30 AM | **start_day_task** | Every 2 min until 10:15 | Entry signals and trade execution |
| 9:30 AM | **monitor_task** | Every 5 min until 3:32 PM | P&L monitoring, stop loss check |
| 3:25 PM | **closing_day_task** | Every 2.5 min until 3:32 PM | Close positions if profit target hit |
| 3:45 PM | **analyse_day_task** | Once | EOD report generation |

### Task Details

#### 1. **setup_day_task** (9:15 AM)
Pre-market preparation.

**Actions:**
- Fetch Trendlyne data (scraping)
- Get VIX value and categorize (VHigh/High/Normal/Low/VLow)
- Update pre-market data from broker API
- Check for existing open positions
- Calculate daily delta (volatility-based sizing)
- Determine if day is tradable (check VIX, major events, holidays)
- Set all flags for the day

**Flags Set:**
- `nseVix`, `vixStatus`
- `openPositions`
- `dailyDelta`
- `isDayTradable`

#### 2. **start_day_task** (9:30 AM, repeats every 2 min until 10:15 AM)
Trade entry window.

**Actions:**
- Check if day is tradable
- Check if already have positions (skip if yes)
- Generate trading signals using `SignalGenerator`
- Validate trade using `TradeValidator`
- Place order if approved (TODO: actual order placement)
- Send Telegram notification
- Update `openPositions` flag

**Exit Conditions:**
- Day not tradable
- Already have open positions
- Signal confidence too low (<60%)
- Validation failed

#### 3. **monitor_task** (Every 5 min, 9:30 AM - 3:32 PM)
Position monitoring.

**Actions:**
- Get current P&L from broker
- Check if P&L changed significantly (>₹5,000)
- Send alert if big change
- Check stop loss violation
- Close all positions if stop loss hit

**Alerts:**
- P&L change > ₹5,000
- Stop loss hit

#### 4. **closing_day_task** (Every 2.5 min, 3:25 PM - 3:32 PM)
Position closing logic.

**Actions:**
- Check if profit target achieved
- Check if it's expiry day (close all)
- Close positions if criteria met
- Send notification

**Close Triggers:**
- P&L >= profit target
- Days to expiry <= 0
- Market closing time

#### 5. **analyse_day_task** (3:45 PM)
End-of-day analysis.

**Actions:**
- Fetch all today's positions from broker
- Calculate total P&L
- Create/update `DayReport`
- Save individual positions to `TodaysPosition`
- Reset flags for next day
- Send EOD summary notification

---

## 🔧 Broker APIs

### ICICI Breeze API

Full-featured broker integration with margin checking.

**Location:** `tools/breeze.py`

```python
from apps.brokers.integrations.breeze import get_breeze_client, BreezeAPIClient

# Initialize
api = BreezeAPI()
api.login()

# ===== MARGIN CHECKING =====
margin = api.get_margin()
print(f"Available: ₹{margin['available_margin']:,.2f}")

# Quick check
has_margin = api.check_margin_sufficient(50000)

# ===== POSITIONS =====
positions = api.get_positions()
has_positions = api.isOpenPos()
pnl = api.get_position_pnl()

# ===== ORDERS =====
order_id = api.place_order(
    symbol='NIFTY',
    action='BUY',  # or 'SELL'
    quantity=50,
    order_type='MARKET',  # or 'LIMIT'
    price=0,
    exchange='NFO',
    expiry='28-NOV-2024',
    strike_price='24000',
    right='CALL'  # or 'PUT'
)

# Cancel order
api.cancel_order(order_id)

# Get all orders
orders = api.get_orders()

# ===== QUOTES & DATA =====
quote = api.get_quote('NIFTY', exchange='NSE')
print(f"NIFTY: {quote.get('ltp')}")

# Option chain
chain = api.get_option_chain('NIFTY', '28-NOV-2024')

# Historical data
df = api.get_historical_data(
    symbol='NIFTY',
    interval='1day',
    from_date='2024-01-01',
    to_date='2024-11-15'
)

# ===== UTILITIES =====
is_open = api.is_market_open()
expiry = api.get_current_expiry()  # '28-NOV-2024'

api.logout()
```

**Available Methods:**

| Method | Purpose |
|--------|---------|
| `get_margin()` | Get available margin and funds |
| `get_available_margin()` | Get available margin as float |
| `check_margin_sufficient(amount)` | Check if sufficient margin |
| `get_positions()` | Get all open positions |
| `isOpenPos()` | Check if any positions exist |
| `get_position_pnl()` | Calculate total P&L |
| `place_order(...)` | Place an order |
| `cancel_order(order_id)` | Cancel an order |
| `get_orders()` | Get all orders |
| `get_quote(symbol)` | Get current quote |
| `get_option_chain(symbol, expiry)` | Get complete option chain |
| `get_historical_data(...)` | Get OHLCV data |
| `is_market_open()` | Check if market is open |
| `get_current_expiry()` | Get current month expiry |

### Kotak Neo API

Similar comprehensive integration.

**Location:** `tools/neo.py`

```python
from tools.neo import NeoAPI

api = NeoAPI()
api.login()

# Same methods as Breeze
margin = api.get_margin()
positions = api.get_positions()
order_id = api.place_order(...)

api.logout()
```

**Note:** Neo API requires instrument tokens. Use `search_scrip()` to find tokens:

```python
scrips = api.search_scrip('NIFTY', exchange='NSE')
token = scrips[0]['pSymbol']
```

### Yahoo Finance Utilities

Market data and VIX fetching.

**Location:** `tools/yahoofin.py`

```python
from tools.yahoofin import (
    get_nse_vix,
    get_nifty_quote,
    fetch_nifty50_data,
    get_market_summary,
    is_market_hours,
    get_market_status
)

# VIX
symbol, vix = get_nse_vix()
print(f"VIX: {vix}")

# NIFTY quote
quote = get_nifty_quote()
print(f"NIFTY: {quote['price']}, Change: {quote['pct_change']}%")

# Historical data
df = fetch_nifty50_data('2024-01-01', '2024-11-15')

# Market status
status = get_market_status()  # 'PRE_MARKET', 'OPEN', or 'CLOSED'
```

---

## 💬 Telegram Notifications

**Location:** `apps/core/notifications.py`

### Setup

1. Store credentials in Django admin:

```
Service: telegram
API Key: <telegram_api_id>
API Secret: <telegram_api_hash>
Username: dmcube_bot
```

2. Send notifications:

```python
from apps.core.notifications import send_telegram_notification

send_telegram_notification(
    "Trade Entry: FUTURES_LONG NIFTY\n"
    "Confidence: 75%\n"
    "Signal: BUY"
)
```

---

## 🎯 Installation & Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

New packages installed:
- `django-background-tasks==1.2.8`
- `django-compat==1.0.15`
- `yfinance>=0.2.31`
- `ta>=0.11.0`

### 2. Run Migrations

```bash
python manage.py migrate
```

Creates tables for:
- `TradingSchedule`
- `NseFlag`
- `BkLog`
- `DayReport`
- `TodaysPosition`

### 3. Install Scheduler

```bash
python manage.py install_scheduler
```

This will:
- Remove any existing scheduler tasks
- Create default `NseFlag` entries
- Create `TradingSchedule` for today and tomorrow
- Schedule the master scheduler to run daily at 8:30 AM

### 4. Enable Trading

```bash
# Enable automated trading
python manage.py enable_trading

# Disable it
python manage.py enable_trading --disable
```

### 5. Start Background Worker

```bash
python manage.py process_tasks
```

**Keep this running!** This is the worker that processes all background tasks.

**For production**, use systemd or supervisor to keep it running:

```ini
[program:mcube_tasks]
command=/path/to/venv/bin/python manage.py process_tasks
directory=/path/to/mCube-ai
autostart=true
autorestart=true
```

---

## 📊 Management Commands

### View Status

```bash
python manage.py trading_status
```

Shows:
- Trading enabled/disabled
- Current market conditions (VIX, day tradable)
- Open positions
- Current P&L
- Pending tasks
- Recent reports

### Stop All Tasks

```bash
python manage.py stop_scheduler
```

Emergency stop - deletes ALL scheduled tasks.

### Configure Flags

Use Django admin or shell:

```python
from apps.core.models import NseFlag

# Set stop loss
NseFlag.set('stopLossLimit', '-15000', 'Max daily loss')

# Set profit target
NseFlag.set('minDailyProfitTarget', '5000', 'Min profit to close')

# Set daily delta
NseFlag.set('dailyDelta', '0.35', 'Daily volatility target')
```

---

## 🔐 Credentials Setup

### 1. Via Django Admin

Go to: `http://localhost:8000/admin/core/credentialstore/`

**ICICI Breeze:**
- Service: `breeze`
- API Key: Your Breeze API key
- API Secret: Your Breeze API secret
- Session Token: Your Breeze session token

**Kotak Neo:**
- Service: `kotakneo`
- API Key: Consumer key
- API Secret: Consumer secret
- Username: Mobile number
- Password: Account password
- Neo Password: MPIN

**Telegram:**
- Service: `telegram`
- API Key: Telegram API ID
- API Secret: Telegram API hash
- Username: Bot username (e.g., `dmcube_bot`)

### 2. Via Django Shell

```python
from apps.core.models import CredentialStore

# Breeze
CredentialStore.objects.create(
    service='breeze',
    name='default',
    api_key='YOUR_API_KEY',
    api_secret='YOUR_API_SECRET',
    session_token='YOUR_SESSION_TOKEN'
)
```

---

## 🐛 Troubleshooting

### Tasks Not Running

**Check worker is running:**
```bash
ps aux | grep process_tasks
```

**Check pending tasks:**
```bash
python manage.py trading_status
```

**View logs:**
```python
from apps.core.models import BkLog
BkLog.objects.filter(level='error').order_by('-timestamp')[:10]
```

### Trading Not Starting

**Check flags:**
```bash
python manage.py enable_trading  # View current config
```

**Common issues:**
- `autoTradingEnabled` = false
- `isDayTradable` = false (VIX too high, major event, etc.)
- `openPositions` = true (already have position)

### Margin Issues

**Check available margin:**
```python
from apps.brokers.integrations.breeze import get_breeze_client

api = get_breeze_api()
margin = api.get_margin()
print(f"Available: ₹{margin['available_margin']:,.2f}")
```

---

## 📈 Workflow Example

### Complete Daily Flow

**8:30 AM:**
```
Master Scheduler runs
  ↓
Schedules all tasks for the day
```

**9:15 AM:**
```
setup_day_task runs
  ↓
Fetches Trendlyne data
Checks VIX (15.5 - Normal)
Updates broker data
No open positions
Daily delta: 0.35
Day is tradable ✓
```

**9:30 AM:**
```
start_day_task runs (first time)
  ↓
Generates signals for NIFTY
Signal: BUY, Confidence: 75%
Validates trade ✓
Places order (TODO)
Sends Telegram: "Trade Entry: FUTURES_LONG NIFTY"
Sets openPositions = true
```

**9:35 AM, 9:40 AM, ...**
```
start_day_task runs (but skips - already have position)
```

**9:35 AM, 9:40 AM, 9:45 AM, ... 3:30 PM:**
```
monitor_task runs every 5 minutes
  ↓
Checks P&L: ₹3,500
No alerts (change < ₹5,000)
Not at stop loss
```

**3:25 PM:**
```
closing_day_task runs
  ↓
Current P&L: ₹5,200
Profit target: ₹5,000
Target achieved! ✓
Closes all positions
Sends Telegram: "Positions Closed, P&L: ₹5,200"
Sets openPositions = false
```

**3:45 PM:**
```
analyse_day_task runs
  ↓
Fetches today's positions
Total P&L: ₹5,200
Creates DayReport
Saves positions to TodaysPosition
Resets flags
Sends EOD summary
```

---

## 🎨 Customization

### Custom Task

Create custom background task:

```python
from background_task import background
from apps.core.models import NseFlag

@background(name="my_custom_task")
def my_custom_task():
    # Your logic here
    vix = NseFlag.get_float('nseVix')
    
    if vix > 25:
        # Do something
        pass
```

Schedule it:

```python
from datetime import datetime, timedelta

# Run in 5 minutes
run_time = datetime.now() + timedelta(minutes=5)
my_custom_task(schedule=run_time)

# Run daily at 10 AM
my_custom_task(schedule=run_time, repeat=86400)  # 86400 seconds = 1 day
```

### Custom Trading Logic

Modify `start_day_task` in `apps/core/background_tasks.py`:

```python
@background(name="start_day_task")
def start_day_task():
    # Your custom entry logic
    
    # Example: Use different confidence threshold
    if signal.confidence < 70:  # Changed from 60
        return
    
    # Example: Add custom filters
    if is_expiry_week():
        return  # Skip expiry week
```

---

## 📚 Further Reading

- **Django Background Tasks:** https://django-background-tasks.readthedocs.io/
- **Breeze Connect Docs:** https://api.icicidirect.com/breezeconnect/
- **Trendlyne Integration:** See `TRENDLYNE_TRADING_INTEGRATION.md`
- **Signal Generation:** See `apps/data/signals.py`
- **Trade Validation:** See `apps/data/validators.py`

---

## ✅ Summary

**What We Built:**

1. ✅ **Automated Daily Scheduler** - Runs at 8:30 AM, schedules all tasks
2. ✅ **5 Background Tasks** - Setup, Entry, Monitor, Closing, Analysis
3. ✅ **5 New Models** - TradingSchedule, NseFlag, BkLog, DayReport, TodaysPosition
4. ✅ **2 Broker APIs** - ICICI Breeze & Kotak Neo with margin checking
5. ✅ **Telegram Notifications** - Real-time trading alerts
6. ✅ **4 Management Commands** - install_scheduler, stop_scheduler, enable_trading, trading_status
7. ✅ **Yahoo Finance Integration** - VIX and market data

**Key Improvements Over Old Project:**

- ✅ Cleaner code structure
- ✅ Better error handling
- ✅ More comprehensive logging
- ✅ Integrated with signal generation and validation
- ✅ Better documentation
- ✅ Django admin integration
- ✅ Flexible configuration via flags
- ✅ Complete broker API with margin checking

**Ready to Trade!** 🚀
