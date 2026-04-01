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
| `models.py` | CredentialStore, TradingCoreConfig, NseFlag, BkLog, TaskExecutionLog, CeleryTaskState, DayReport, TodaysPosition, SystemSettings, TaskPreset |
| `tasks.py` | Core Celery tasks: health_check_brokers, monitor_opening_volatility, review_overnight_positions, send_morning_briefing |
| `constants.py` | All trading parameters and configuration values |
| `task_config.py` | TASK_DEFAULT_CONFIG — display names, categories, defaults for all tasks |
| `views.py` | HTTP endpoints for dashboard and testing |
| `urls.py` | URL routing |
| `admin.py` | Django admin interface |
| `utils/decorators.py` | task_enabled_guard, handle_exceptions, require_broker_auth, validate_input, etc. |
| `utils/task_logger.py` | TaskLogger — step-by-step BkLog writer for Celery tasks |
| `utils/date_utils.py` | Expiry dates, trading day checks, IST helpers |
| `utils/` | Other utilities (formatting, validation, error handling) |
| `services/trading_context.py` | TradingContext — unified context for tasks and views |
| `services/expiry_selector.py` | Expiry date selection with business rules |

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

Configures daily trading times per date.

```python
# Fields
date = DateField(unique=True)           # Trading date
open_time = TimeField()                 # Default: 09:15:10 — market open / setup task
take_trade_time = TimeField()           # Default: 09:30 — start taking trades
last_trade_time = TimeField()           # Default: 10:15 — last time for new entries
close_pos_time = TimeField()            # Default: 15:25:30 — start closing positions
mkt_close_time = TimeField()            # Default: 15:32 — market close time
close_day_time = TimeField()            # Default: 15:45 — end-of-day analysis
enabled = BooleanField()                # Enable trading for this day
note = CharField()                      # Notes about this trading day

# Method
schedule.as_datetimes(tz=IST)           # Convert all times to timezone-aware datetimes
```

### NseFlag

Key-value store for runtime flags and state.

```python
# Fields
flag = CharField(unique=True)   # Flag name (e.g., 'isDayTradable')
value = CharField()             # Flag value (stored as string)
description = TextField()       # What this flag means
updated_at = DateTimeField()    # Auto-updated on save

# Helper methods (static)
NseFlag.get(name, default='')           # Get flag value as string
NseFlag.set(name, value, description)   # Set or create flag
NseFlag.get_bool(name, default=False)   # Get as boolean
NseFlag.get_float(name, default=0.0)    # Get as float
NseFlag.get_int(name, default=0)        # Get as integer
```

**Common Flags**:
- `isDayTradable` - Whether trading is allowed today
- `nseVix` - VIX value and status
- `openPositions` - Current open position count
- `dailyDelta` - Daily volatility target
- `position_hold_<id>` - Hold flag for exit suggestion dedup (JSON: reason, price, held_at)

### TaskExecutionLog

One row per Celery task run — lightweight audit trail. Written automatically by `task_enabled_guard` for every guarded task.

```python
# Fields
task_key = CharField(db_index=True)       # Beat schedule key, e.g. 'monitor-and-manage-positions'
started_at = DateTimeField(auto_now_add)  # When task started
completed_at = DateTimeField(nullable)    # When task finished
status = CharField()                      # SUCCESS | FAILURE | SKIPPED
duration_ms = IntegerField(nullable)      # Wall-clock duration in milliseconds
result_summary = JSONField()              # Condensed return value from the task function
error_message = TextField()               # Exception message on FAILURE; empty otherwise
```

### BkLog

Step-by-step background task logging with detailed metrics. Used by `TaskLogger` for granular execution tracking.

```python
# Fields
timestamp = DateTimeField()     # Auto-set on creation
level = CharField()             # debug, info, warning, error, critical
action = CharField()            # Action/function name
message = TextField()           # Log message
background_task = CharField()   # Background task name
task_category = CharField()     # data, strategy, transaction, position, risk, analytics, other
task_id = CharField()           # Celery task ID for correlation
execution_time_ms = IntegerField()  # Execution time in milliseconds
context_data = JSONField()      # Additional context (symbols, counts, metrics)
error_details = TextField()     # Full error traceback if error occurred
success = BooleanField()        # Whether the task completed successfully
```

### DayReport

Daily trading report — end-of-day summary per trading day.

```python
# Fields
date = DateField(unique=True)
day_of_week = CharField()
num_legs = IntegerField()       # Number of option legs traded
pnl = DecimalField()            # Profit and Loss for the day
is_closed = BooleanField()      # Whether all positions were closed
expiry_date = DateField()       # F&O expiry date traded
notes = TextField()
```

### TodaysPosition

Individual F&O position details for the day, copied from broker position data.

```python
# Fields
date = DateField()
symbol = CharField()
instrument_name = CharField()
instrument_token = BigIntegerField()
exchange = CharField()          # NFO
segment = CharField()           # FNO
expiry_date = CharField()
option_type = CharField()       # CE/PE/FUT
strike_price = IntegerField()
# Buy/Sell quantities, amounts, averages
# Net position, realized P&L
# Margin details (span, exposure, premium)
```

### SystemSettings

Central configuration for all task timings (editable via admin). Singleton pattern.

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

**Full lifecycle managed by the decorator:**
1. **Enable check**: Queries `CeleryTaskState.is_task_enabled()`. Disabled = returns `{'status': 'skipped'}`
2. **Telegram start notification**: Sends "Running..." message (skips silent/high-frequency tasks)
3. **Timing**: Measures wall-clock execution time
4. **Completion notification**: Edits the start message with result + BkLog steps (expandable blockquote)
5. **TaskExecutionLog write**: One row per execution (SUCCESS/FAILURE/SKIPPED)
6. **Celery Retry handling**: `celery.exceptions.Retry` is re-raised silently, not logged as FAILURE

**Silent tasks** (no Telegram notifications): `monitor-and-manage-positions`, `check-risk-limits-all-accounts`, `monitor-circuit-breakers`, `check-confirmation-timeouts`

### Other Decorators (`utils/decorators.py`)

| Decorator | Purpose |
|-----------|---------|
| `handle_exceptions` | Standardized JSON error responses for views |
| `require_broker_auth(broker_type)` | Ensure broker session before view execution |
| `validate_input(schema)` | Request input validation against a schema |
| `log_execution_time` | Performance logging for views |
| `require_post_method` | Restrict view to POST only |
| `cache_result(timeout)` | Cache view results for specified timeout |

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
from apps.core.services.trading_context import TradingContext, get_trading_context

# Direct instantiation or convenience function:
ctx = TradingContext(task_name='my_task', task_logger=logger)
# or
ctx = get_trading_context(task_name='my_task')

# Check trading eligibility (checks weekends, holidays, TradingDaySetup)
if not ctx.is_trading_allowed(check_futures=True):
    return ctx.skip_result()

# Access config
config = ctx.config  # TradingCoreConfig singleton (lazy-loaded)
lots = ctx.get_lots_for_trade('FUTURES', available_margin=5000000, margin_per_lot=50000)
needs_confirm = ctx.requires_confirmation('EXIT')
is_paper = ctx.is_simulated()

# Account retrieval
kotak_account = ctx.get_kotak_account()
icici_account = ctx.get_icici_account()

# Position queries
active = ctx.get_active_positions(account=kotak_account)
has_pos = ctx.has_active_position(kotak_account)

# Result builders
ctx.skip_result()    # {'success': True, 'skipped': True, 'reason': ...}
ctx.error_result(e)  # {'success': False, 'error': ...}
ctx.success_result(positions=5)  # {'success': True, 'positions': 5}
```

### TradingCoreConfig (in `models.py` ~line 1148) — Singleton

Centralized trading control. Access: `TradingCoreConfig.get_instance()`

```python
# Trading Enable/Disable
enable_futures_trading = BooleanField()

# Strategy Selection
options_strategy = CharField()       # STRANGLE | BROKEN_IRON_CONDOR | AUTO | NONE
vix_high_threshold = DecimalField()  # Default 18.0
vix_low_threshold = DecimalField()   # Default 14.0

# Position Sizing Modes
position_sizing_mode = CharField()   # TEST | MANUAL | AUTO | SIMULATED
manual_options_lots = IntegerField() # 1-50, default 1
manual_futures_lots = IntegerField() # 1-20, default 1
margin_utilization_pct = DecimalField()  # 10-90%, default 50%
simulated_options_lots = IntegerField()  # 1-500, default 100
simulated_futures_lots = IntegerField()  # 1-100, default 30

# Notification Levels
notification_level = CharField()     # FULL_CONTROL | SUPERVISED | AUTONOMOUS
confirmation_timeout_minutes = IntegerField()  # 1-30, default 5

# Risk Parameters
max_loss_per_trade = DecimalField()
options_profit_target = DecimalField()
movement_threshold = DecimalField()  # 0.1-3.0%, default 0.5%

# Carry Forward Rules
options_carry_forward_threshold = DecimalField()  # Default 5000

# Helper Methods
config.is_autonomous()               # True only for AUTONOMOUS
config.is_simulated()                # True for SIMULATED mode
config.is_test_mode()                # True for TEST mode (1 lot)
config.is_auto_sizing()              # True for AUTO margin-based sizing
config.is_full_control()             # True for FULL_CONTROL
config.is_supervised()               # True for SUPERVISED
config.is_options_enabled()          # True if options_strategy != NONE
config.is_futures_enabled()          # True if enable_futures_trading
config.requires_confirmation('EXIT') # True for FULL_CONTROL & SUPERVISED
config.get_auto_strategy(current_vix) # Returns strategy based on VIX thresholds
config.get_lots_for_trade('OPTIONS', available_margin, margin_per_lot) # Sizing-mode-aware
config.get_notification_level_display_short()  # e.g. '🔒 Full Control'
config.get_position_sizing_display_short()     # e.g. '🧪 Test (1 lot)'
```

### CeleryTaskState (in `models.py`)

Enable/disable + custom schedule per Celery task. Tasks not in this table are considered DISABLED by default.

```python
task_key = CharField(unique=True)    # Task key from beat_schedule
task_path = CharField()              # Full task path (e.g. 'apps.data.tasks.fetch_trendlyne_data')
display_name = CharField()           # Human-readable name
description = TextField()            # Task description
is_enabled = BooleanField()          # Toggle task on/off (default: False)
last_toggled_at = DateTimeField()    # When last enabled/disabled
last_toggled_by = CharField()        # Who toggled it
schedule_type = CharField()          # crontab | interval | recurring
# + schedule configuration fields (crontab fields, interval_seconds, window times)
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

## Core Celery Tasks (`tasks.py`)

Infrastructure, market-open observation, and pre-market review tasks. None of these tasks place orders or modify positions — they are purely observational and informational.

### Task Schedule (Mon-Fri)

| Task | Time | Purpose |
|------|------|---------|
| `health_check_brokers` | 06:45 AM | Broker API + Redis connectivity check |
| `review_overnight_positions` | 08:55 AM | News impact on carried positions |
| `send_morning_briefing` | 09:00 AM | Single consolidated briefing message |
| `monitor_opening_volatility` | 09:00-09:20 (every 5 min) | VIX + gap flags for strategy gate |

### Redis Key Registry

Tasks write to Redis so downstream trading tasks can gate on results:

```python
BROKER_HEALTH_KEY = 'broker_health'           # TTL: 2h (06:45 → past 08:55)
MARKET_STABLE_KEY = 'market_stable_for_trading'  # TTL: 1h (09:00-10:00)
MARKET_VIX_KEY = 'market_open_vix'            # TTL: 1h
MARKET_GAP_KEY = 'market_open_gap_pct'        # TTL: 1h
```

**Thresholds**: VIX >= 20.0 or |gap%| >= 1.5% marks market as unstable.

### Task Details

- **`health_check_brokers`**: Tests Kotak Neo (get_margin), ICICI Breeze (client init), and Redis (write/read-back). Stores results in Redis. Sends CRITICAL alert on any failure.

- **`monitor_opening_volatility`**: Measures VIX + Nifty gap vs previous close. Writes `market_stable_for_trading` flag. Fail-open: missing flag = proceed normally.

- **`review_overnight_positions`**: Checks NewsArticle for negative sentiment on held instruments (24h window). Sends WARNING listing at-risk positions.

- **`send_morning_briefing`**: Consolidates broker health, VIX, gap, day setup status, open positions into one structured Telegram message using `NotificationPayload`.

---

## Admin Interface

Access at `/admin/core/` to manage:

- **Credential Stores** - API keys and passwords
- **Trading Core Config** - Strategy, sizing, notification level (singleton)
- **Trading Schedules** - Daily timing configuration
- **NSE Flags** - Runtime state flags
- **Celery Task States** - Enable/disable tasks, custom schedules
- **Task Execution Logs** - Per-run audit trail (read-only)
- **BK Logs** - Step-by-step task logs (read-only)
- **Day Reports** - Daily trading summaries
- **System Settings** - Task timing configuration
- **Task Presets** - Saved enabled/disabled state presets

---

## How to Study This App

1. **Start with `models.py`** - Understand TradingCoreConfig, CeleryTaskState, NseFlag, BkLog, TaskExecutionLog
2. **Read `tasks.py`** - Core Celery tasks (health check, morning briefing, volatility monitor)
3. **Check `utils/decorators.py`** - task_enabled_guard lifecycle and other decorators
4. **Explore `services/trading_context.py`** - Unified context for tasks and views
5. **Read `constants.py`** - Trading parameters and configuration values
6. **Explore `utils/`** - Date helpers, formatting, validation, task logger

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

1. Define in `tasks.py` using `@shared_task` and `@task_enabled_guard`
2. Use `TaskLogger` for step-by-step logging
3. Add to Celery beat schedule in `mcube_ai/celery.py`
4. Add task key to `task_config.py` TASK_DEFAULT_CONFIG

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
