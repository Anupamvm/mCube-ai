# Core App Documentation

**Location**: `apps/core/`

The core app is the foundation of mCube. It provides shared utilities, credential management, constants, and background task scheduling used by all other apps.

---

## What This App Does

1. **Credential Storage** - Securely stores API keys and passwords for all services
2. **Constants & Configuration** - Central place for all trading parameters
3. **Utilities** - Date/time helpers, formatting, validation, error handling
4. **Background Tasks** - Schedules and runs automated trading tasks
5. **Trading State** - Manages pause/resume trading functionality

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | Database models for credentials, settings, logs |
| `constants.py` | All trading parameters and configuration values |
| `views.py` | HTTP endpoints for dashboard and testing |
| `urls.py` | URL routing |
| `admin.py` | Django admin interface |
| `background_tasks.py` | Scheduled task definitions |
| `trading_state.py` | Pause/resume trading state |
| `notifications.py` | Telegram/SMS notification sending |
| `middleware.py` | Error handling middleware |
| `utils/` | Utility functions (dates, formatting, validation) |
| `services/` | Business logic services |

---

## Key Models

### CredentialStore

Stores API credentials for all external services.

```python
# Core Fields
service = CharField()           # breeze, kotakneo, trendlyne, telegram
name = CharField()              # Human-readable name
api_key = CharField()           # API key
api_secret = CharField()        # API secret
session_token = CharField()     # Session token (for Breeze)
username = CharField()          # Username/mobile (for Neo)
password = CharField()          # Password
neo_password = CharField()      # MPIN for Kotak Neo
pan = CharField()               # PAN card
sid = CharField()               # Session ID

# Kotak Neo v2 Fields (added Feb 2026)
ucc = CharField()               # Unique Client Code
totp_secret = CharField()       # TOTP secret for automated login
mobile_number = CharField()     # Mobile number
neo_base_url = URLField()       # API base URL (from totp_validate response, REQUIRED for all v2 API calls)
neo_data_center = CharField()   # Data center (from totp_validate response)
neo_edit_token = TextField()    # Edit token for session
neo_edit_sid = CharField()      # Edit SID
neo_server_id = CharField()     # Server ID

# Auto-Login Tracking (one attempt per day per broker)
auto_login_status = CharField() # none|in_progress|success|failed
auto_login_date = DateField()   # Date of last auto-login attempt
```

**Usage**:
```python
from apps.core.models import CredentialStore

# Get Breeze credentials
cred = CredentialStore.objects.get(service='breeze')
api_key = cred.api_key
```

### TradingSchedule

Configures daily trading times.

```python
# Fields
market_open = TimeField()       # Default: 09:15
entry_window_start = TimeField()  # Default: 09:30
entry_window_end = TimeField()    # Default: 11:30
exit_check_time = TimeField()     # Default: 15:15
market_close = TimeField()        # Default: 15:30
```

### NseFlag

Key-value store for runtime flags and state.

```python
# Fields
name = CharField()              # Flag name (e.g., 'isDayTradable')
value = CharField()             # Flag value
description = TextField()       # What this flag means
```

**Common Flags**:
- `isDayTradable` - Whether trading is allowed today
- `currentVIX` - Current India VIX value
- `openPositions` - Count of open positions

### BkLog

Background task logging with detailed metrics.

```python
# Fields
task_name = CharField()         # Name of the task
task_category = CharField()     # Category (position, risk, strategy)
status = CharField()            # STARTED, SUCCESS, FAILURE
message = TextField()           # Log message
execution_time_ms = IntegerField()  # How long it took
error_message = TextField()     # Error details if failed
context_data = JSONField()      # Additional context
```

### SystemSettings

Central configuration for all task timings (editable via admin).

```python
# Fields (sample)
trendlyne_fetch_time = TimeField()    # When to fetch Trendlyne data
position_monitor_interval = IntegerField()  # Seconds between checks
risk_check_interval = IntegerField()  # Seconds between risk checks
```

---

## Constants (constants.py)

This file contains all trading parameters. Key sections:

### Account Configuration

```python
KOTAK_CONFIG = {
    'capital': 60000000,      # Rs 6 Crore
    'strategy': 'STRANGLE',
    'max_margin_usage': 0.50,  # 50% rule
}

ICICI_CONFIG = {
    'capital': 12000000,      # Rs 1.2 Crore
    'strategy': 'FUTURES',
    'max_margin_usage': 0.50,
}
```

### Strategy Parameters

```python
STRANGLE_CONFIG = {
    'base_delta': 0.5,        # 0.5% base delta
    'profit_target': 0.70,    # 70% of premium
    'stop_loss': 1.00,        # 100% of premium (exit at double)
}

FUTURES_CONFIG = {
    'min_days_to_expiry': 15,
    'risk_reward_ratio': 2.0,  # 1:2 risk-reward
    'max_averaging_attempts': 3,
}
```

### Market Timings

```python
ENTRY_WINDOW_START = time(9, 0)   # 9:00 AM
ENTRY_WINDOW_END = time(11, 30)   # 11:30 AM
EXIT_CHECK_TIME = time(15, 15)    # 3:15 PM
MARKET_CLOSE = time(15, 30)       # 3:30 PM
```

---

## Utility Functions

### Date Utilities (`utils/date_utils.py`)

```python
from apps.core.utils.date_utils import (
    get_current_weekly_expiry,    # Get this week's expiry
    get_next_weekly_expiry,       # Get next week's expiry
    get_days_to_expiry,           # Days remaining to expiry
    is_trading_day,               # Is today a trading day?
    is_market_hours,              # Is market currently open?
    get_current_ist_time,         # Current time in IST
)

# Example
expiry = get_current_weekly_expiry('NIFTY')  # Returns date
days = get_days_to_expiry(expiry)            # Returns int
```

### Formatting Utilities (`utils/formatting.py`)

```python
from apps.core.utils.formatting import (
    format_indian_currency,       # Rs 1,00,000
    format_percentage,            # 12.50%
    format_pnl,                   # +Rs 5,000 or -Rs 3,000
)

# Example
print(format_indian_currency(150000))  # Rs 1,50,000
print(format_pnl(5000))                # +Rs 5,000
```

### Validators (`utils/validators.py`)

```python
from apps.core.utils.validators import (
    validate_position_entry,      # Check if entry is valid
    validate_margin_usage,        # Check margin availability
    is_valid_strike,              # Check if strike is valid
)

# Example
is_valid, errors = validate_position_entry(account, 'STRANGLE', expiry, margin)
```

### Error Handlers (`utils/error_handlers.py`)

```python
from apps.core.utils.error_handlers import (
    handle_api_errors,            # Decorator for API error handling
    handle_broker_errors,         # Decorator for broker errors
    retry_on_failure,             # Retry decorator with backoff
)

# Example
@handle_api_errors
def my_api_view(request):
    # Your code here - errors are automatically handled
    pass

@retry_on_failure(max_attempts=3, delay_seconds=2)
def fetch_data():
    # Will retry up to 3 times with exponential backoff
    pass
```

### Task Logger (`utils/task_logger.py`)

```python
from apps.core.utils.task_logger import TaskLogger

# Example usage in a background task
logger = TaskLogger(task_name='monitor_positions', task_category='position')
logger.start("Starting position monitoring")
logger.info('check_price', "Checking price for NIFTY")
logger.success("Monitoring complete", context={'positions': 5})
# or
logger.failure("Error occurred", error=exception)
```

### Task Guard Decorator (`utils/decorators.py`)

```python
from apps.core.utils.decorators import task_enabled_guard

@task_enabled_guard('fetch-trendlyne-data-daily')
def fetch_trendlyne_data(self):
    # Only runs if task is enabled in CeleryTaskState
    pass

# Supports list of task keys (runs if ANY key is enabled)
@task_enabled_guard(['batch-options-averaging', 'batch-options-averaging-10am'])
def batch_averaging(self):
    pass

# Manual "Run Now" bypasses the guard
# run_task_now() passes _bypass_guard=True kwarg
```

### Task Config (`task_config.py`)

`TASK_DEFAULT_CONFIG` defines display names, categories, and defaults for all tasks.

**6 Task Categories:**
- `data` (Market Data)
- `strategies` (Strategy Execution)
- `transactions` (Transactions) — start-options-trade, batch-options-averaging, close-trading-day, etc.
- `monitoring` (Position Monitoring)
- `risk` (Risk Management)
- `reports` (Analytics & Reports)

---

## Services

### TradingContext (`services/trading_context.py`) — NEW (Feb 2026)

Unified context service for Celery tasks & web views. Ensures both use the SAME APIs.

```python
from apps.core.services.trading_context import get_trading_context

ctx = get_trading_context(task_name='my_task')

# Check trading eligibility
if not ctx.is_trading_allowed():
    return ctx.skip_result()

# Access config
config = ctx.config  # TradingCoreConfig singleton
lots = config.get_lots_for_trade(margin_per_lot=50000)
needs_confirm = config.requires_confirmation('futures_entry')
is_paper = config.is_simulated()

# Account retrieval
kotak_account = ctx.get_kotak_account()
```

### TradingCoreConfig (in `models.py`) — NEW (Feb 2026)

Singleton model for centralized trading control.

```python
# Position Sizing Modes
# TEST (1 Lot Each) | MANUAL (Fixed Lots) | AUTO (Margin-Based) | SIMULATED (Paper Trade)

# Notification Levels
# FULL_CONTROL (Confirm Everything) | SUPERVISED (Confirm Major) | AUTONOMOUS (Notifications Only)

# Helper Methods
config = TradingCoreConfig.get_instance()
config.get_lots_for_trade(margin_per_lot)  # Calculate lots based on mode
config.requires_confirmation(action_type)  # Check if action needs approval
config.is_simulated()                       # Check if paper trading
```

### Expiry Selector (`services/expiry_selector.py`)

Handles expiry date selection with business rules.

```python
from apps.core.services.expiry_selector import (
    select_expiry_for_options,    # Get expiry for options (min 1 day)
    select_expiry_for_futures,    # Get expiry for futures (min 15 days)
    should_roll_position,         # Check if position needs rolling
)

# Example
expiry, details = select_expiry_for_options('NIFTY')
# Returns: (date, {'days_remaining': 5, 'risk_level': 'LOW'})
```

---

## Background Tasks

### Task Schedule

| Task | Frequency | Purpose |
|------|-----------|---------|
| `setup_day_task` | 9:15 AM | Pre-market setup |
| `start_day_task` | 9:30 AM | Trade entry evaluation |
| `monitor_task` | Every 10 sec | Position monitoring |
| `closing_day_task` | 3:25 PM | Position closure |
| `analyse_day_task` | 3:45 PM | End-of-day analysis |

### Trading State

```python
from apps.core.trading_state import (
    is_trading_paused,            # Check if trading is paused
    pause_trading,                # Pause all trading
    resume_trading,               # Resume trading
)

# Example
if is_trading_paused():
    return "Trading is paused, skipping..."

pause_trading(reason="Manual pause via Telegram")
```

---

## Admin Interface

Access at `/admin/core/` to manage:

- **Credential Stores** - API keys and passwords
- **Trading Schedules** - Daily timing configuration
- **NSE Flags** - Runtime state flags
- **BK Logs** - Background task logs (read-only)
- **System Settings** - Task timing configuration

---

## How to Study This App

1. **Start with `models.py`** - Understand the data structures
2. **Read `constants.py`** - Learn all configuration parameters
3. **Explore `utils/`** - See available helper functions
4. **Check `background_tasks.py`** - Understand the task schedule
5. **Review `trading_state.py`** - Learn pause/resume logic

---

## Common Tasks for Developers

### Add a New Credential Service

1. Add to `CredentialStore.SERVICE_CHOICES` in `models.py`
2. Create a management command or use admin to add credentials
3. Access via `CredentialStore.objects.get(service='new_service')`

### Add a New Configuration Parameter

1. Add to `constants.py` with a descriptive name
2. Import where needed: `from apps.core.constants import NEW_PARAM`
3. Document in the constants file

### Add a New Background Task

1. Define in `background_tasks.py`
2. Use `TaskLogger` for logging
3. Add to Celery beat schedule in `mcube_ai/celery.py`

### Add a New Utility Function

1. Add to appropriate file in `utils/`
2. Export from `utils/__init__.py`
3. Add docstring with usage example

---

## Dependencies

This app is imported by all other apps. It should not import from other apps to avoid circular dependencies.

**Imports from external**:
- Django core modules
- Python standard library

**Does not import**:
- Other mCube apps (keeps core independent)

---

*For questions, check the code comments or ask the team.*
