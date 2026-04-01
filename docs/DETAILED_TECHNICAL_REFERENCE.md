# mCube AI Trading System - Detailed Technical Reference

**Complete Module-by-Module Documentation for Understanding and Modifying the Codebase**

**Version:** 4.0
**Last Updated:** March 2026
**Document Type:** Developer Reference Manual

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Deep Dive](#2-architecture-deep-dive)
3. [Module Classification](#3-module-classification)
4. [Core App (`apps/core`)](#4-core-app)
5. [Accounts App (`apps/accounts`)](#5-accounts-app)
6. [Positions App (`apps/positions`)](#6-positions-app)
7. [Strategies App (`apps/strategies`)](#7-strategies-app)
8. [Brokers App (`apps/brokers`)](#8-brokers-app)
9. [Data App (`apps/data`)](#9-data-app)
10. [LLM App (`apps/llm`)](#10-llm-app)
11. [Trading App (`apps/trading`)](#11-trading-app)
12. [Risk App (`apps/risk`)](#12-risk-app)
13. [Analytics App (`apps/analytics`)](#13-analytics-app)
14. [Alerts App (`apps/alerts`)](#14-alerts-app)
15. [Background Tasks (Celery)](#15-background-tasks-celery)
16. [Constants and Configuration](#16-constants-and-configuration)
17. [Common Modification Scenarios](#17-common-modification-scenarios)
18. [Data Flow Diagrams](#18-data-flow-diagrams)
19. [Debugging Guide](#19-debugging-guide)
20. [Testing Strategy](#20-testing-strategy)

---

## 1. System Overview

### 1.1 What is mCube?

mCube is an **AI-powered automated trading system** for Indian F&O (Futures & Options) markets. It manages two broker accounts with different trading strategies:

| Account | Broker | Capital | Strategy | Monthly Target |
|---------|--------|---------|----------|----------------|
| **Kotak** | Kotak Neo | ₹6 Crores | Weekly Nifty Short Strangle | ₹6-8 Lakhs |
| **ICICI** | ICICI Breeze | ₹1.2 Crores | LLM-Validated Futures | ₹4-6 Lakhs |

### 1.2 Core Business Rules (NEVER VIOLATE)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SACRED RULES - ENFORCED AT CODE LEVEL                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1️⃣  ONE POSITION PER ACCOUNT AT ANY TIME                               │
│      └─ Checked in: Position.has_open_position(account)                 │
│      └─ Location: apps/positions/models.py:362-368                      │
│      └─ Redis lock prevents race conditions (position_create_lock_{id}) │
│      └─ Circuit breaker gate: is_circuit_breaker_active() checked first │
│                                                                          │
│  2️⃣  50% MARGIN FOR FIRST TRADE                                         │
│      └─ Reserved for averaging and emergencies                          │
│      └─ Location: apps/accounts/services/margin_manager.py              │
│                                                                          │
│  3️⃣  OPTIONS: Skip if < 1 day to expiry                                 │
│      └─ Gamma risk too high near expiry                                 │
│      └─ Location: apps/core/services/expiry_selector.py                 │
│                                                                          │
│  4️⃣  FUTURES: Skip if < 15 days to expiry                               │
│      └─ Liquidity drops, spreads widen                                  │
│      └─ Location: apps/core/services/expiry_selector.py                 │
│                                                                          │
│  5️⃣  EXIT EOD only if >= 50% target achieved                            │
│      └─ Otherwise hold overnight                                        │
│      └─ Location: apps/positions/services/exit_manager.py:110-217       │
│                                                                          │
│  6️⃣  LLM Confidence >= 70% for futures trades                           │
│      └─ Location: apps/llm/services/trade_validator.py                  │
│                                                                          │
│  7️⃣  Maximum 2 averaging attempts for futures                           │
│      └─ Location: apps/positions/services/averaging_manager.py          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Technology Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                        TECHNOLOGY STACK                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Web Framework     │  Django 4.2.7                              │
│  Database          │  SQLite (db.sqlite3)                       │
│  Cache/Queue       │  Redis 5.0.1                               │
│  Task Queue        │  Celery 5.3.4                              │
│  Vector Database   │  ChromaDB 0.4.18                           │
│  LLM              │  Ollama + DeepSeek R1                       │
│  Frontend          │  Bootstrap 5 + HTMX                        │
│  Notifications     │  Telegram Bot (python-telegram-bot)        │
│                                                                 │
│  Brokers          │  Kotak Neo API, ICICI Breeze API            │
│  Data Sources     │  Trendlyne, GNews.io, Yahoo Finance         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture Deep Dive

### 2.1 Directory Structure

```
mCube-ai/
├── mcube_ai/                      # Django Project Configuration
│   ├── __init__.py
│   ├── settings.py                # Main settings (DB, Redis, Celery, LLM)
│   ├── celery.py                  # Celery configuration & beat schedule
│   ├── urls.py                    # Root URL routing
│   └── wsgi.py / asgi.py
│
├── apps/                          # 11 Installed Django Applications (+algo_test legacy)
│   ├── core/                      # Foundation: credentials, scheduling, TradingContext, TradingCoreConfig
│   ├── accounts/                  # Broker accounts & margin management
│   ├── positions/                 # Position lifecycle management
│   ├── strategies/                # Trading algorithms, dynamic scheduler
│   ├── brokers/                   # Broker API integrations (Neo v2, Breeze)
│   ├── data/                      # Market data, Trendlyne, GNews (3-layer caching)
│   ├── llm/                       # AI/LLM validation, analyst reports (8h cache)
│   ├── trading/                   # Trade suggestions, TradeConfirmationService
│   ├── risk/                      # Risk management & circuit breakers
│   ├── analytics/                 # Performance tracking & learning
│   ├── alerts/                    # Telegram bot (4-file mixin, ~7.5K LOC)
│   └── algo_test/                 # Algorithm testing
│
├── tools/                         # Standalone utilities
│   ├── neo.py                     # Kotak Neo API wrapper
│   └── yahoofin.py                # Yahoo Finance integration
│
├── templates/                     # HTML templates
├── static/                        # CSS/JS assets
├── scripts/                       # Startup/utility scripts
├── docs/                          # Documentation
└── logs/                          # Application logs
```

### 2.2 App Dependency Graph

```
                              ┌────────────┐
                              │    core    │ ◄─── ALL apps depend on core
                              └─────┬──────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
    ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
    │   accounts    │       │    brokers    │       │     data      │
    └───────┬───────┘       └───────┬───────┘       └───────┬───────┘
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    │
                                    ▼
                            ┌───────────────┐
                            │   strategies  │
                            └───────┬───────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
    ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
    │      llm      │       │   positions   │       │    trading    │
    └───────┬───────┘       └───────┬───────┘       └───────┬───────┘
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
    ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
    │     risk      │       │   analytics   │       │    alerts     │
    └───────────────┘       └───────────────┘       └───────────────┘
```

---

## 3. Module Classification

### 3.1 By Function

| Category | Apps | Purpose |
|----------|------|---------|
| **Foundation** | `core` | Base models, utilities, credentials, scheduling |
| **Trading Engine** | `strategies`, `positions`, `trading` | Algorithm execution, position management |
| **External Integration** | `brokers`, `data` | Broker APIs, market data sources |
| **AI/ML** | `llm`, `analytics` | Trade validation, pattern learning |
| **Safety** | `risk`, `alerts` | Risk limits, circuit breakers, notifications |
| **Administration** | `accounts` | Broker accounts, margin tracking |

### 3.2 By Complexity

| Complexity | Apps | Lines of Code | Notes |
|------------|------|---------------|-------|
| **High** | `strategies`, `brokers`, `llm` | 2000+ each | Core trading logic, complex integrations |
| **Medium** | `positions`, `trading`, `data`, `analytics` | 800-2000 | Business logic, data management |
| **Low** | `core`, `accounts`, `risk` | 300-800 | Support functions, configuration |
| **Medium-High** | `alerts` | ~7,500 | 4-file mixin Telegram bot + unified notification framework |

---

## 4. Core App (`apps/core`)

### 4.1 Purpose
Foundation layer providing shared utilities, credential storage, scheduling configuration, and abstract base models.

### 4.2 Models

#### `TimeStampedModel` (Abstract)
**Location:** `apps/core/models.py:17-50`
**Purpose:** Base class for all models with automatic timestamps

```python
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']
```

**Usage:** All models in the system inherit from this:
```python
class MyModel(TimeStampedModel):
    # Your fields here
    pass
```

---

#### `CredentialStore`
**Location:** `apps/core/models.py:52-111`
**Purpose:** Secure storage for API credentials + session state + auto-login tracking

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `service` | CharField | Service name (breeze, kotakneo, telegram, etc.) |
| `name` | CharField | Credential set name (default: "default") |
| `api_key` | CharField | API key (Consumer Key for Neo v2) |
| `api_secret` | CharField | API secret (not used for Neo v2) |
| `session_token` | CharField | Session token (refreshed daily) |
| `username` | CharField | Username for login |
| `password` | CharField | Password for login |
| `pan` | CharField | PAN number (for broker auth) |
| `neo_password` | CharField | MPIN for Kotak Neo 2FA |
| `ucc` | CharField | Unique Client Code (Neo v2) |
| `totp_secret` | CharField | TOTP secret for automated login (Neo v2) |
| `mobile_number` | CharField | Mobile number (Neo v2) |
| `neo_base_url` | URLField | API base URL from totp_validate (REQUIRED for v2 API calls) |
| `neo_data_center` | CharField | Data center from totp_validate |
| `neo_edit_token` | TextField | Edit token for session persistence |
| `neo_edit_sid` | CharField | Edit SID for session persistence |
| `neo_server_id` | CharField | Server ID for session persistence |
| `auto_login_status` | CharField | none\|in_progress\|success\|failed |
| `auto_login_date` | DateField | Date of last auto-login attempt |

**How to use:**
```python
from apps.core.models import CredentialStore

# Get Breeze credentials
creds = CredentialStore.objects.get(service='breeze', name='default')
api_key = creds.api_key
api_secret = creds.api_secret
```

**Where credentials come from:**
- Populated via admin interface, web UI (`kotakneo_login` view), or management commands
- Session tokens updated daily by auto-login tasks
- Neo v2 session: `base_url` + `data_center` saved from `totp_validate()` response

---

#### `TradingSchedule`
**Location:** `apps/core/models.py:96-172`
**Purpose:** Daily trading schedule configuration

**Key Time Fields:**
| Field | Default | Purpose |
|-------|---------|---------|
| `open_time` | 09:15:10 | Market open setup task |
| `take_trade_time` | 09:30:00 | Start taking trades |
| `last_trade_time` | 10:15:00 | No new trades after this |
| `close_pos_time` | 15:25:30 | Start closing positions |
| `mkt_close_time` | 15:32:00 | Market close |
| `close_day_time` | 15:45:00 | End-of-day analysis |

**How to modify:**
```python
from apps.core.models import TradingSchedule
from datetime import date, time

schedule, created = TradingSchedule.objects.get_or_create(
    date=date.today(),
    defaults={
        'take_trade_time': time(9, 40),  # Delayed start
        'enabled': True,
    }
)
```

---

#### `NseFlag`
**Location:** `apps/core/models.py:175-254`
**Purpose:** Runtime key-value store for trading parameters

**Common Flags:**
| Flag Name | Type | Description |
|-----------|------|-------------|
| `isDayTradable` | bool | Whether trading is enabled today |
| `nseVix` | float | Current VIX value |
| `openPositions` | int | Number of open positions |
| `dailyDelta` | float | Daily volatility target |

**How to use:**
```python
from apps.core.models import NseFlag

# Get a flag value
is_tradable = NseFlag.get_bool('isDayTradable', default=False)
vix = NseFlag.get_float('nseVix', default=15.0)

# Set a flag value
NseFlag.set('isDayTradable', 'true', description='Trading enabled')
```

---

#### `SystemSettings`
**Location:** `apps/core/models.py:497-736`
**Purpose:** System-wide settings (singleton pattern)

**Key Settings Groups:**
1. **Market Data Timing** - Pre-market, live, post-market update times
2. **Strategy Timing** - Futures screening intervals, averaging checks
3. **Position Monitoring** - Monitor interval, P&L update frequency
4. **Risk Management** - Risk check intervals, circuit breaker timing
5. **Reporting** - Daily P&L report time, weekly summary

**How to access:**
```python
from apps.core.models import SystemSettings

settings = SystemSettings.get_settings()  # Always use this method
monitor_interval = settings.monitor_positions_interval_seconds
```

---

#### `CeleryTaskState`
**Location:** `apps/core/models.py:744-1049`
**Purpose:** Enable/disable and configure individual Celery tasks

**Key Features:**
- Tasks are **disabled by default** - must be explicitly enabled
- Supports custom schedule configuration (crontab, interval, recurring window)
- Tracks who enabled/disabled and when

**How to use:**
```python
from apps.core.models import CeleryTaskState

# Check if a task is enabled
if CeleryTaskState.is_task_enabled('fetch-trendlyne-data-daily'):
    # Run the task
    pass

# Enable a task
CeleryTaskState.set_task_state(
    'fetch-trendlyne-data-daily',
    enabled=True,
    user='admin'
)
```

---

### 4.3 Services

#### `expiry_selector.py`
**Location:** `apps/core/services/expiry_selector.py`
**Purpose:** Calculate option and futures expiry dates

**Key Functions:**

```python
def get_current_weekly_expiry() -> date:
    """Get the current week's Thursday expiry."""

def get_next_weekly_expiry() -> date:
    """Get next week's Thursday expiry."""

def select_expiry_for_options(min_days=1) -> date:
    """
    Select appropriate expiry for options.
    Skips to next week if < min_days to current expiry.
    """

def select_expiry_for_futures(symbol, min_days=15) -> date:
    """
    Select appropriate expiry for futures.
    Skips to next month if < min_days to current expiry.
    """
```

**To modify expiry logic:**
1. Edit `apps/core/services/expiry_selector.py`
2. Change `min_days` parameter or add new holiday handling

---

### 4.4 Utilities

#### `date_utils.py`
**Location:** `apps/core/utils/date_utils.py` or `apps/core/utils.py`

**Key Functions:**
```python
def get_current_ist_time() -> datetime:
    """Get current time in IST timezone."""

def is_market_hours() -> bool:
    """Check if current time is within market hours (9:15-15:30)."""

def is_trading_day(date) -> bool:
    """Check if given date is a trading day (not weekend/holiday)."""
```

---

## 5. Accounts App (`apps/accounts`)

### 5.1 Purpose
Manages broker accounts, capital allocation, and margin calculations.

### 5.2 Models

#### `BrokerAccount`
**Location:** `apps/accounts/models.py`
**Purpose:** Represents a trading account with a broker

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `broker` | CharField | KOTAK or ICICI |
| `account_number` | CharField | Unique account identifier |
| `account_name` | CharField | Display name |
| `allocated_capital` | DecimalField | Total capital allocated |
| `is_active` | BooleanField | Whether account is active |
| `is_paper_trading` | BooleanField | Paper trading mode |
| `max_daily_loss` | DecimalField | Daily loss limit |
| `max_weekly_loss` | DecimalField | Weekly loss limit |

**Important Methods:**
```python
def get_available_capital(self) -> Decimal:
    """
    Calculate capital not deployed in positions.

    Returns:
        allocated_capital - (margin used by active positions)
    """
```

---

### 5.3 Services

#### `margin_manager.py`
**Location:** `apps/accounts/services/margin_manager.py`
**Purpose:** Calculate available margin and position sizing

**Key Functions:**

```python
def calculate_usable_margin(account: BrokerAccount) -> Decimal:
    """
    Calculate margin usable for first trade (50% of available).

    CRITICAL: Reserves 50% for:
    - Averaging opportunities
    - Emergency adjustments
    - Margin calls

    Returns:
        Decimal: Usable margin amount
    """
    available = account.get_available_capital()
    return available * Decimal('0.50')

def check_margin_availability(account: BrokerAccount, required: Decimal) -> bool:
    """Check if account has enough margin for a trade."""

def get_margin_utilization(account: BrokerAccount) -> Dict:
    """Get margin utilization stats (total, used, available, %)."""
```

**To change the 50% rule:**
1. Find `Decimal('0.50')` in `margin_manager.py`
2. Change to desired percentage
3. Update corresponding tests

---

## 6. Positions App (`apps/positions`)

### 6.1 Purpose
Tracks position lifecycle from suggestion through execution to closure.

### 6.2 Models

#### `Position`
**Location:** `apps/positions/models.py:30-465`
**Purpose:** Unified model for all positions (broker-synced, system-suggested, manual)

**Status Lifecycle:**
```
SUGGESTED → APPROVED → OPEN → CLOSED
           ↘        ↗
            REJECTED
            EXPIRED
```

**Key Fields by Category:**

**Core Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `account` | ForeignKey | Associated broker account |
| `instrument` | CharField | Trading symbol (NIFTY, RELIANCE) |
| `direction` | CharField | LONG, SHORT, or NEUTRAL |
| `quantity` | IntegerField | Number of lots |
| `lot_size` | IntegerField | Lot size for instrument |

**Status & Source:**
| Field | Type | Description |
|-------|------|-------------|
| `status` | CharField | SUGGESTED, APPROVED, OPEN, CLOSED, REJECTED, EXPIRED |
| `source` | CharField | BROKER (synced), SYSTEM (generated), MANUAL |
| `strategy_type` | CharField | LLM_VALIDATED_FUTURES, WEEKLY_STRANGLE, etc. |

**Pricing:**
| Field | Type | Description |
|-------|------|-------------|
| `entry_price` | DecimalField | Entry/suggested price |
| `current_price` | DecimalField | Current market price (LTP) |
| `exit_price` | DecimalField | Exit price (when closed) |
| `stop_loss` | DecimalField | Stop-loss price |
| `target` | DecimalField | Target price |

**P&L Tracking:**
| Field | Type | Description |
|-------|------|-------------|
| `unrealized_pnl` | DecimalField | Current unrealized P&L |
| `realized_pnl` | DecimalField | Realized P&L (after closing) |
| `entry_value` | DecimalField | Total entry value |
| `margin_used` | DecimalField | Margin blocked |

**Options-Specific:**
| Field | Type | Description |
|-------|------|-------------|
| `call_strike` | DecimalField | Call option strike |
| `put_strike` | DecimalField | Put option strike |
| `premium_collected` | DecimalField | Total premium collected (strangle) |
| `current_delta` | DecimalField | Current position delta |

**Averaging (Futures):**
| Field | Type | Description |
|-------|------|-------------|
| `averaging_count` | IntegerField | Number of averaging attempts |
| `original_entry_price` | DecimalField | Original entry before averaging |
| `partial_booked` | BooleanField | Whether partial profit taken |

**Critical Class Methods:**

```python
@classmethod
def has_open_position(cls, account) -> bool:
    """
    Check if account has any open position.

    THIS IS THE ONE POSITION RULE ENFORCEMENT.
    Called before every new entry evaluation.
    """
    return cls.objects.filter(
        account=account,
        status=POSITION_STATUS_OPEN
    ).exists()

@classmethod
def get_active_position(cls, account):
    """Get the active position for an account (should be 0 or 1)."""
    return cls.objects.filter(
        account=account,
        status=POSITION_STATUS_OPEN
    ).first()
```

**Instance Methods:**

```python
def calculate_pnl(self, price=None) -> Decimal:
    """Calculate P&L at given price (defaults to current_price)."""

def update_price(self, price: Decimal):
    """Update current price and recalculate unrealized P&L."""

def is_stop_loss_hit(self) -> bool:
    """Check if current price has breached stop-loss."""

def is_target_hit(self) -> bool:
    """Check if current price has achieved target."""

def close_position(self, exit_price: Decimal, exit_reason: str):
    """Close the position and calculate final P&L."""
```

---

#### `MonitorLog`
**Location:** `apps/positions/models.py:467-491`
**Purpose:** Tracks position monitoring events (alerts, checks)

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `position` | ForeignKey | Associated position |
| `check_type` | CharField | PNL_UPDATE, EXIT_SUGGESTION, STRUCTURAL_PRESSURE, AUTO_EXIT, NEAR_SL |
| `result` | CharField | OK, SUGGESTION_SENT, HELD_BY_USER, SKIPPED_DUPLICATE, EXECUTING, STAGE2_WARNING_SENT |
| `message` | TextField | Description with IST timestamp |
| `price_at_check` | DecimalField | Price at time of check |
| `pnl_at_check` | DecimalField | P&L at time of check |
| `action_taken` | CharField | SUGGESTION_SENT, HELD_BY_USER, DUPLICATE_SKIPPED, AUTO_EXIT |

**Performance:** PNL_UPDATE entries are batched via `bulk_create()` to reduce SQLite write contention.

#### `PositionMonitorDashboard`
**Purpose:** Anti-spam dashboard — one Telegram message per trading day, edited in place

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `trading_date` | DateField | One per trading day |
| `message_id` | IntegerField | Telegram message ID (for editing) |
| `snapshots` | JSONField | Last 3 snapshots [{price, pnl, pnl_pct, time}] |
| `sr_tracking` | JSONField | SR cache, gap flag, near_sl_warned, volatility_event_flag |
| `last_snapshot` | DateTimeField | Last update timestamp |

#### `PortfolioPnlTracker`
**Purpose:** Portfolio P&L snapshot history (used for daily reports)

---

### 6.3 Services

#### `exit_manager.py`
**Location:** `apps/positions/services/exit_manager.py`
**Purpose:** Handles all exit logic (stop-loss, target, EOD)

**Exit Priority:**
```
1. STOP-LOSS HIT → IMMEDIATE EXIT (mandatory)
2. TARGET HIT → IMMEDIATE EXIT (mandatory)
3. EOD EXIT → CONDITIONAL (only if profit >= 50%)
4. EXPIRY DAY → MANDATORY EXIT
```

**Key Functions:**

```python
def check_exit_conditions(position: Position) -> Dict:
    """
    Check all exit conditions for a position.

    Returns:
        {
            'should_exit': bool,
            'exit_reason': str,  # STOP_LOSS, TARGET, EOD, EXPIRY_DAY
            'exit_price': Decimal,
            'message': str,
            'is_mandatory': bool
        }
    """

def check_eod_exit(position: Position, current_time) -> Dict:
    """
    Check EOD exit with 50% minimum profit rule.

    - Kotak (Strangle): Thursday 3:15 PM exit if profit >= 50%
    - ICICI (Futures): Any day 3:15 PM exit if profit >= 50%
    - If profit < 50% → Hold overnight
    """

def calculate_exit_metrics(position: Position, exit_price: Decimal) -> Dict:
    """
    Calculate exit metrics (P&L, ROI, holding period, etc.)
    """
```

**To modify exit rules:**
1. Edit `apps/positions/services/exit_manager.py`
2. Change `min_profit_threshold = Decimal('50.0')` for different threshold
3. Modify time checks in `check_eod_exit()` for different exit times

---

#### `sr_exit_engine.py`
**Location:** `apps/positions/services/sr_exit_engine.py`
**Purpose:** Structural S/R-based stop-loss and target management

**Public API:**
```python
def apply_sl_and_target(position, dashboard, now=None) -> Dict:
    """
    Returns:
        {
            'sl_triggered': bool,
            'sl_reason': str,
            'structural_pressure': dict or None,  # Stage 2 warning
        }
    """
```

**3-Stage Warning System:**
1. **NEAR_SL** — Within 1% of stop-loss (once per day via `sr_tracking['near_sl_warned']`)
2. **STRUCTURAL_PRESSURE** — Condition A met, Condition B pending (5 min lead time)
3. **TRIGGER** — Both conditions met → exit fired

**Score-Gated Triggers** (LevelConfidenceScorer 0-100):
- ≥76 (institutional): Condition A alone triggers
- 56-75 (strong): A or B + 15-min confirmation
- <56 (moderate): Both A+B required
- Strict mode (expiry day before 14:00 IST): Always requires both A+B

**Enhancement Layer (6 files):**
- `sr_mtf_enricher.py` — 4-timeframe swing HL stacking
- `sr_level_strength.py` — LevelStrengthAnnotator + LevelConfidenceScorer
- `order_block_detector.py` — Order block zones
- `oi_wall_enricher.py` — Gamma walls, OI delta, strike pinning
- `sr_strategy_adapter.py` — FuturesStrategyAdapter, StrangleRangeGuard
- `sr_risk_interface.py` — AdaptiveSLPlacer, StructuralPressureMonitor

---

#### `position_manager.py`
**Location:** `apps/positions/services/position_manager.py`
**Purpose:** Position lifecycle (create, close, average) with ONE POSITION RULE

**Key Functions:**
```python
def morning_check(account) -> Dict:
    """Returns {action: 'MONITOR'/'EVALUATE_ENTRY', allow_new_entry: bool, position, message}"""

def create_position(account, strategy_type, instrument, ...) -> Tuple[bool, Position, str]:
    """Redis-locked, circuit-breaker-gated position creation"""

def close_position(position, exit_price, exit_reason, place_broker_order=False) -> Tuple[bool, str]:
    """Broker-first close when place_broker_order=True (prevents ghost positions)"""

def average_position(position, new_quantity, new_price, new_margin) -> Tuple[bool, str]:
    """Max 2 averaging attempts. Tightens SL to 0.5% from new average."""
```

---

#### `averaging_manager.py`
**Location:** `apps/positions/services/averaging_manager.py`
**Purpose:** Manages futures averaging logic

**Averaging Rules:**
- Maximum 2 averaging attempts (`max_average_attempts = 2`)
- Trigger: Position down by 1% from entry
- First average: Add 20% of original margin
- Second average: Add 50% of remaining margin
- After averaging: Tighten stop-loss to 0.5% from new average

**Key Functions:**

```python
def should_average_position(position: Position) -> Tuple[bool, str]:
    """
    Check if position should be averaged.

    Returns:
        (should_average: bool, reason: str)
    """

def calculate_averaging_quantity(position: Position) -> int:
    """Calculate how many lots to add for averaging."""

def execute_averaging(position: Position) -> bool:
    """Execute averaging and update position."""
```

---

#### `delta_monitor.py`
**Location:** `apps/positions/services/delta_monitor.py`
**Purpose:** Monitors delta for options positions

**Key Functions:**

```python
def calculate_net_delta(position: Position) -> Decimal:
    """Calculate net delta for strangle position."""

def check_delta_threshold(position: Position) -> Dict:
    """
    Check if delta exceeds threshold (300).

    Returns:
        {
            'alert_needed': bool,
            'current_delta': Decimal,
            'threshold': int,
            'recommendation': str
        }
    """

def generate_adjustment_recommendation(position: Position) -> str:
    """Generate recommendation for delta adjustment."""
```

---

#### `pnl_updater.py`
**Location:** `apps/positions/services/pnl_updater.py`
**Purpose:** Updates P&L for all open positions

```python
def update_all_positions_pnl():
    """
    Update current price and P&L for all open positions.
    Called periodically by Celery task.
    """
```

---

#### `position_sync.py`
**Location:** `apps/positions/services/position_sync.py`
**Purpose:** Syncs positions from broker APIs

```python
def sync_positions_from_broker(account: BrokerAccount):
    """
    Fetch positions from broker API and sync to database.
    Creates new Position records or updates existing ones.
    """
```

---

#### `sr_exit_engine.py` *(March 2026)*
**Location:** `apps/positions/services/sr_exit_engine.py`
**Purpose:** Support/Resistance-based exit engine with adaptive SL and structural pressure detection

**Public API:**
```python
def apply_sl_and_target(position, dashboard, now) -> dict:
    """
    Returns:
        {
            'sl_triggered': bool,
            'sl_reason': str,
            'structural_pressure': dict  # Stage 2 warning (Cond A met, Cond B pending)
        }
    Called BEFORE should_exit_position() in monitor task.
    """
```

**SR Enhancement Files (all additive):**
| File | Purpose |
|------|---------|
| `sr_mtf_enricher.py` | MTFSREnricher — 4-timeframe swing HL stacking |
| `sr_level_strength.py` | LevelStrengthAnnotator + LevelConfidenceScorer (0-100) |
| `order_block_detector.py` | OrderBlockDetector — base candle zones |
| `oi_wall_enricher.py` | OIWallEnricher — gamma walls, OI delta, strike pinning |
| `sr_strategy_adapter.py` | FuturesStrategyAdapter, StrangleRangeGuard, BrokenIronCondorGuard |
| `sr_risk_interface.py` | AdaptiveSLPlacer, StructuralPressureMonitor, PartialCloseAdvisor |

**Score-gated trigger rules (LevelConfidenceScorer 0-100):**
- >= 76 (institutional): Condition A alone triggers
- 56-75 (strong): A or B + 15-min confirmation
- < 56: both A+B required
- Strict mode (expiry day before 14:00 / low-liquidity): always requires both A+B

---

#### `monitor_dashboard.py` *(March 2026)*
**Location:** `apps/positions/services/monitor_dashboard.py`
**Purpose:** Anti-spam position monitoring dashboard

**Model:** `PositionMonitorDashboard` (one per trading day) — edits a single Telegram message instead of sending new ones. Shows day-start snapshot + last 3 position snapshots with IST timestamps.

---

## 7. Strategies App (`apps/strategies`)

### 7.1 Purpose
Implements trading algorithms (Strangle, Futures, Iron Condor).

### 7.2 Directory Structure

```
apps/strategies/
├── models.py                  # Strategy config, learning, market state
├── models_strangle.py         # Strangle-specific models
├── tasks.py                   # General strategy tasks
├── tasks_strangle.py          # Strangle-specific tasks
├── core/
│   ├── base_strategy.py       # Abstract base strategy class
│   ├── entry_workflow.py      # Entry detection & validation
│   └── result_types.py        # Type definitions
├── strategies/
│   ├── kotak_strangle.py      # Strangle strategy implementation
│   └── icici_futures.py       # Futures strategy implementation
├── filters/
│   ├── volatility.py          # VIX-based filters
│   ├── sector_filter.py       # Sector strength analysis
│   ├── event_calendar.py      # Economic event filtering
│   └── global_markets.py      # SGX Nifty, US markets impact
├── services/
│   ├── strangle_delta_algorithm.py
│   ├── technical_analysis.py
│   ├── support_resistance_calculator.py
│   ├── nifty_data_fetcher.py
│   ├── comprehensive_data_aggregator.py
│   ├── market_condition_validator.py
│   ├── entry_point_detector.py
│   ├── greeks_calculator.py
│   ├── historical_analysis.py
│   ├── psychological_levels.py
│   ├── adaptive_sl_target.py     # Adaptive SL/Target (March 2026)
│   ├── market_regime.py          # Market regime detection (March 2026)
│   ├── contract_prefilter.py     # Contract prefilter (March 2026)
│   ├── trade_validation.py       # Trade validation layer (March 2026)
│   └── llm_context_builder.py    # LLM context builder (March 2026)
└── shared/
    ├── strike_calculator.py   # Strike calculation utilities
    └── market_data.py         # Market data fetching utilities
```

### 7.3 Models

#### `StrategyConfig`
**Location:** `apps/strategies/models.py:15-158`
**Purpose:** Configuration parameters for each strategy

**Key Fields:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `account` | ForeignKey | - | Associated broker account |
| `strategy_type` | CharField | - | WEEKLY_NIFTY_STRANGLE or LLM_VALIDATED_FUTURES |
| `is_active` | BooleanField | True | Whether strategy is active |
| `initial_margin_usage_pct` | DecimalField | 50.00 | % of margin for first trade |
| `min_profit_pct_to_exit` | DecimalField | 50.00 | Minimum % to exit EOD |
| `base_delta_pct` | DecimalField | 0.50 | Strike distance (Strangle) |
| `min_days_to_expiry` | IntegerField | 1 | Min days for options |
| `min_days_to_future_expiry` | IntegerField | 15 | Min days for futures |
| `allow_averaging` | BooleanField | True | Enable averaging (Futures) |
| `max_average_attempts` | IntegerField | 2 | Max averaging count |
| `min_llm_confidence` | DecimalField | 70.00 | Min LLM confidence % |
| `require_human_approval` | BooleanField | True | Require manual approval |

---

#### `StrategyLearning`
**Location:** `apps/strategies/models.py:161-340`
**Purpose:** Self-learning pattern tracking

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `pattern_name` | CharField | Unique pattern identifier |
| `times_occurred` | IntegerField | Occurrence count |
| `times_profitable` | IntegerField | Profitable count |
| `win_rate` | DecimalField | Win rate % |
| `profit_factor` | DecimalField | Profit factor (profit/loss) |
| `avg_profit_pct` | DecimalField | Average profit % |
| `avg_loss_pct` | DecimalField | Average loss % |
| `is_reliable` | BooleanField | True if >= 30 occurrences |

**Update Method:**
```python
def update_metrics(self, is_profitable: bool, pnl_pct: Decimal):
    """Update pattern metrics after trade completion."""
```

---

#### `TradingDaySetup`
**Location:** `apps/strategies/models.py:713-860`
**Purpose:** Daily trading setup and status tracking

**Key Phases:**
1. **Setup Phase (8:55 AM)** - Pre-market evaluation
2. **Start Phase (9:15 AM)** - Market opening validation

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `trading_date` | DateField | Trading date |
| `is_tradable` | BooleanField | Final: Can we trade today? |
| `recommended_strategy` | CharField | NONE, STRANGLE, IRON_CONDOR, FUTURES_ONLY, ALL |
| `vix_level` | CharField | LOW, NORMAL, ELEVATED, HIGH |
| `gap_percent` | DecimalField | Gap up/down % |

---

### 7.4 Strategy Implementations

#### `kotak_strangle.py`
**Location:** `apps/strategies/strategies/kotak_strangle.py`
**Purpose:** Weekly Nifty Short Strangle implementation

**Class:** `KotakStrangleStrategy(BaseStrategy)`

**Key Methods:**

```python
def get_config(self) -> StrategyConfig:
    """Return strategy configuration."""

def calculate_entry_parameters(self, market_data: Dict) -> Dict:
    """
    Calculate strikes and premiums for strangle.

    Uses VIX-adjusted strike selection formula:
        strike_distance = spot × (adjusted_delta / 100) × days_to_expiry

    Where adjusted_delta:
        - VIX < 15: base_delta (0.5%)
        - VIX 15-18: base_delta × 1.10 (0.55%)
        - VIX > 18: base_delta × 1.20 (0.6%)
    """

def build_position_details(self, entry_params: Dict, sizing: Dict) -> Dict:
    """Build position details for trade suggestion."""

def build_algorithm_reasoning(self, entry_params: Dict, filters: Dict, sizing: Dict) -> Dict:
    """Build complete reasoning for trade suggestion."""
```

**To modify strike calculation:**
1. Edit `apps/strategies/shared/strike_calculator.py`
2. Modify `calculate_strangle_strikes()` function

---

### 7.5 Filters

**Location:** `apps/strategies/filters/`

Each filter returns:
```python
{
    'passed': bool,
    'reason': str,
    'data': dict  # Optional additional data
}
```

#### `volatility.py`
- VIX range check (acceptable: 12-25)
- Bollinger Band extreme detection

#### `sector_filter.py`
- Sector momentum across timeframes (3D, 7D, 21D)
- ALL timeframes must align for direction

#### `event_calendar.py`
- Economic event detection
- Major events: RBI policy, Budget, elections

#### `global_markets.py`
- SGX Nifty change (limit: ±0.5%)
- US markets (Nasdaq, Dow) change (limit: ±1.0%)

---

### 7.6 Services

#### `strangle_delta_algorithm.py`
**Purpose:** Delta calculation for strike selection

```python
def calculate_vix_adjusted_delta(spot, vix, days_to_expiry) -> Dict:
    """Calculate VIX-adjusted strike distance."""

def select_strikes(spot, call_delta, put_delta, expiry) -> Dict:
    """Select optimal strikes based on delta."""
```

#### `technical_analysis.py`
**Purpose:** Technical indicators (RSI, MACD, Bollinger Bands)

```python
def calculate_rsi(prices, period=14) -> float:
    """Calculate RSI indicator."""

def calculate_macd(prices) -> Dict:
    """Calculate MACD and signal line."""

def calculate_bollinger_bands(prices, period=20, std_dev=2) -> Dict:
    """Calculate upper, middle, lower bands."""
```

#### `support_resistance_calculator.py`
**Purpose:** Key price levels

```python
def calculate_support_resistance(price, historical_data) -> Dict:
    """Calculate support and resistance levels."""
```

#### Futures Algorithm — Enhanced (March 2026)

**13-component scoring system** (315pts raw -> normalized to 100 scale). The 13th component is **MTF Confluence** (multi-timeframe trend alignment), added in March 2026.

**New Services:**

| File | Purpose |
|------|---------|
| `adaptive_sl_target.py` | `compute_adaptive_sl_target()` — 3-tier: SR-based -> ATR-adaptive by regime -> Volatility-scaled % |
| `market_regime.py` | `MarketRegimeDetector.classify()` — TRENDING/RANGING/VOLATILE/BREAKOUT/NORMAL |
| `contract_prefilter.py` | `prefilter_contracts()` — ADX > 15, Volume > 20d avg, RSI not dead zone (~50 -> ~30-35 contracts) |
| `trade_validation.py` | `TradeValidationLayer.validate()` — R:R gate (reject < 1.0), regime-appropriate direction, SL distance 0.5%-5% |
| `llm_context_builder.py` | `build_trade_context()` — Enriched context: regime, score summary, risk profile, signals, warnings |

---

## 8. Brokers App (`apps/brokers`)

### 8.1 Purpose
Integrates with Kotak Neo and ICICI Breeze broker APIs.

### 8.2 Directory Structure

```
apps/brokers/
├── models.py                  # BrokerLimit, BrokerPosition, Order, etc.
├── integrations/
│   ├── kotak_neo.py           # Kotak Neo API wrapper
│   ├── breeze.py              # ICICI Breeze API wrapper
│   ├── neo/
│   │   ├── client.py          # WebSocket client
│   │   ├── orders.py          # Order execution
│   │   ├── quotes.py          # Real-time quotes
│   │   ├── data_fetcher.py    # Historical data
│   │   └── symbol_mapper.py   # Symbol conversion
│   └── breeze_module/
│       ├── client.py          # API session
│       ├── orders.py          # Order execution
│       ├── option_chain.py    # Options data
│       ├── quotes.py          # Price quotes
│       ├── margin.py          # Margin calculations
│       └── expiry.py          # Expiry management
├── services/
│   ├── order_sync.py          # Order status sync
│   ├── trade_sync.py          # Trade history sync
│   ├── breeze_session.py      # Session management
│   └── csv_importers.py       # CSV/Excel trade history import (Kotak + Breeze)
└── utils/
    ├── auth_manager.py        # Credential management
    ├── security_master.py     # Instrument master
    └── api_patterns.py        # Rate limiting, retries
```

### 8.3 Models

#### `BrokerLimit`
**Location:** `apps/brokers/models.py:22-169`
**Purpose:** Account margin and limits from broker

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `broker` | CharField | KOTAK or ICICI |
| `margin_available` | DecimalField | Available for trading |
| `margin_used` | DecimalField | Currently used |
| `collateral_value` | DecimalField | Total collateral (Neo) |
| `allocated_fno` | DecimalField | F&O allocation (Breeze) |

---

#### `BrokerPosition`
**Location:** `apps/brokers/models.py:172-275`
**Purpose:** Positions synced from broker API

---

#### `NiftyOptionChain`
**Location:** `apps/brokers/models.py:396-627`
**Purpose:** Nifty option chain with Greeks

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `expiry_date` | DateField | Option expiry |
| `strike_price` | DecimalField | Strike price |
| `call_ltp`, `put_ltp` | DecimalField | LTP |
| `call_delta`, `put_delta` | DecimalField | Delta |
| `call_iv`, `put_iv` | DecimalField | Implied Volatility |
| `call_oi`, `put_oi` | BigIntegerField | Open Interest |

---

#### `HistoricalPrice`
**Location:** `apps/brokers/models.py:630-862`
**Purpose:** Historical OHLCV data

**Key Class Methods:**
```python
@classmethod
def replace_data(cls, stock_code, exchange_code, product_type, interval, data_points, ...):
    """Delete existing and save fresh data."""

@classmethod
def get_latest_data(cls, stock_code, exchange_code, product_type, interval, limit=100):
    """Get latest historical data."""
```

---

#### `Order`
**Location:** `apps/brokers/models.py:869-1099`
**Purpose:** Track orders placed with broker

**Status Lifecycle:**
```
PENDING → PLACED → FILLED
                 → PARTIAL
                 → CANCELLED
                 → REJECTED
```

**Key Methods:**
```python
def mark_placed(self, broker_order_id: str):
    """Mark order as placed with broker."""

def mark_filled(self, average_price: Decimal, filled_quantity: int = None):
    """Mark order as filled."""

def mark_cancelled(self, reason: str = ""):
    """Mark order as cancelled."""
```

---

### 8.4 Integrations

#### Kotak Neo API
**Location:** `apps/brokers/integrations/kotak_neo.py` (facade), `tools/neo.py` (NeoAPI wrapper)

**Key Functions:**
```python
def authenticate() -> bool:
    """Authenticate with Kotak Neo API (TOTP + MPIN)."""

def place_order(symbol, action, quantity, order_type='MKT', price=0,
                exchange='NFO', product='NRML', is_exit=False, max_retries=3) -> Optional[str]:
    """Place order with automatic retry (March 2026).
    - Retries 3x with exponential backoff (1s, 2s, 4s) for transient errors
    - Auth errors: session cleared, re-login, retry
    - is_exit=True: URGENT Telegram alert on exhausted retries
    - Returns order_id or None
    """

def get_positions() -> List[Dict]:
    """Get all positions from Kotak Neo."""

def get_live_quote(symbol) -> Dict:
    """Get real-time quote for symbol."""

def get_option_chain(symbol, expiry) -> List[Dict]:
    """Get option chain data."""
```

**REST Client:** `kotak-neo-api/neo_api_client/rest.py` — all HTTP calls use `timeout=(5, 30)` (5s connect, 30s read) to prevent worker starvation.

#### ICICI Breeze API
**Location:** `apps/brokers/integrations/breeze.py`

**Key Functions:**
```python
def authenticate() -> bool:
    """Authenticate with ICICI Breeze API."""

def place_order(stock_code, exchange_code, action, quantity, price=None) -> Dict:
    """Place order with Breeze."""

def get_portfolio_positions() -> List[Dict]:
    """Get all positions."""

def get_quotes(stock_code, exchange_code) -> Dict:
    """Get real-time quotes."""

def get_historical_data(stock_code, interval, from_date, to_date) -> List[Dict]:
    """Get historical OHLCV data."""
```

---

## 9. Data App (`apps/data`)

### 9.1 Purpose
Fetches, stores, and analyzes market data from multiple sources.

### 9.2 Models

#### `MarketData`
**Purpose:** OHLCV data snapshots

#### `OptionChain`
**Purpose:** Options Greeks and premiums

#### `ContractData`
**Purpose:** Futures/Options contract data from Trendlyne

#### `NewsArticle`
**Purpose:** News articles with sentiment

#### `TrendlyneStockData`
**Purpose:** Stock metrics from Trendlyne
- Durability score
- Momentum score
- Technical indicators

---

### 9.3 Services

#### `trendlyne_fetcher.py`
**Location:** `apps/data/services/trendlyne_fetcher.py`
**Purpose:** Fetch data from Trendlyne API

**Key Functions:**
```python
def fetch_fno_stocks() -> List[Dict]:
    """Fetch all F&O stocks data."""

def fetch_stock_data(symbol) -> Dict:
    """Fetch detailed data for a stock."""

def fetch_option_chain(symbol, expiry) -> List[Dict]:
    """Fetch option chain from Trendlyne."""
```

#### `gnews_client.py`
**Location:** `apps/data/services/gnews_client.py`
**Purpose:** Fetch news from GNews.io API

---

### 9.4 Analyzers

**Location:** `apps/data/data_analyzers.py`

**6 Analyzer Classes:**

1. **`OpenInterestAnalyzer`** - OI buildups and breakdowns
   ```python
   def analyze_oi_change(symbol) -> Dict:
       """
       Interpret OI + Price movement:
       - Price UP + OI UP = LONG_BUILDUP (Bullish)
       - Price DOWN + OI UP = SHORT_BUILDUP (Bearish)
       - Price UP + OI DOWN = SHORT_COVERING (Bullish)
       - Price DOWN + OI DOWN = LONG_UNWINDING (Bearish)
       """
   ```

2. **`VolumeAnalyzer`** - Volume profile analysis

3. **`PriceActionAnalyzer`** - Support/resistance, trends

4. **`VolatilityAnalyzer`** - VIX, IV percentile, volatility regimes

5. **`TechnicalAnalyzer`** - RSI, MACD, Bollinger Bands, ATR

6. **`FundamentalAnalyzer`** - P/E, dividend, market cap

---

## 10. LLM App (`apps/llm`)

### 10.1 Purpose
AI-powered trade validation using local LLM (Ollama/DeepSeek).

### 10.2 Models

#### `LLMValidation`
**Location:** `apps/llm/models.py`
**Purpose:** Store validation records

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `symbol` | CharField | Stock symbol |
| `direction` | CharField | LONG or SHORT |
| `recommendation` | CharField | APPROVED, REJECTED, AVOID |
| `confidence_score` | DecimalField | 0-100 |
| `reasoning` | TextField | LLM reasoning |
| `outcome_correct` | BooleanField | Was prediction correct? |

---

### 10.3 Services

#### `ollama_client.py`
**Location:** `apps/llm/services/ollama_client.py`
**Purpose:** Interface to Ollama LLM

```python
def generate_response(prompt: str, model: str = None) -> str:
    """Send prompt to Ollama and get response."""

def validate_trade(symbol, direction, context) -> Dict:
    """
    Validate a trade with LLM.

    Returns:
        {
            'recommendation': str,  # APPROVED, REJECTED, AVOID
            'confidence': float,    # 0-100
            'reasoning': str,
            'risk_factors': list
        }
    """
```

#### `trade_validator.py`
**Location:** `apps/llm/services/trade_validator.py`
**Purpose:** Trade validation logic

**Key Function:**
```python
def validate_futures_trade(symbol, direction, market_data, news_context) -> Dict:
    """
    Validate futures trade with LLM.

    Minimum confidence: 70%

    Process:
    1. Gather context (market data, news, historical)
    2. Build validation prompt
    3. Get LLM response
    4. Parse and return decision
    """
```

**Validation Prompt Template:**
```
You are an expert stock analyst. Evaluate this trade:

Symbol: {symbol}
Direction: {direction}
Composite Score: {score}

TECHNICAL CONTEXT:
- OI Buildup: {oi_analysis}
- PCR: {pcr}
- RSI: {rsi}
- DMA Position: {dma_status}

NEWS CONTEXT:
{news_summaries}

Respond with:
DECISION: APPROVED/REJECTED
CONFIDENCE: 0-100
REASONING: ...
RISKS: ...
```

---

#### `rag_system.py`
**Location:** `apps/llm/services/rag_system.py`
**Purpose:** Retrieval-Augmented Generation for context

```python
def retrieve_context(query: str, top_k: int = 5) -> List[str]:
    """
    Search ChromaDB for relevant context.
    Returns top_k most similar documents.
    """

def add_document(text: str, metadata: Dict):
    """Add document to vector store."""
```

#### `vector_store.py`
**Location:** `apps/llm/services/vector_store.py`
**Purpose:** ChromaDB vector database operations

---

## 11. Trading App (`apps/trading`)

### 11.1 Purpose
Trade suggestion generation, approval workflow, and execution control.

### 11.2 Models

#### `TradeSuggestion`
**Location:** `apps/trading/models.py`
**Purpose:** Algorithm-generated trade suggestions

**Status Lifecycle:**
```
SUGGESTED → TAKEN → ACTIVE → CLOSED/SUCCESSFUL/LOSS
         ↘ REJECTED
         ↘ EXPIRED
```

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `symbol` | CharField | Trading symbol |
| `direction` | CharField | LONG, SHORT, NEUTRAL |
| `strategy` | CharField | Strategy name |
| `algorithm_reasoning` | JSONField | Complete calculation details |
| `position_details` | JSONField | Recommended position params |
| `status` | CharField | Suggestion status |

---

### 11.3 Services

#### `trade_suggestions.py`
**Location:** `apps/trading/services/trade_suggestions.py`
**Purpose:** Generate trade suggestions

```python
def generate_suggestion(strategy, market_data, account) -> TradeSuggestion:
    """Generate a new trade suggestion."""

def process_suggestion_approval(suggestion, user) -> Position:
    """Process approved suggestion and create position."""
```

#### `position_sizer.py`
**Location:** `apps/trading/services/position_sizer.py`
**Purpose:** Calculate position size based on margin and risk

```python
def calculate_position_size(account, margin_per_lot, max_lots=None) -> Dict:
    """
    Calculate position size using 50% margin rule.

    Returns:
        {
            'lots': int,
            'quantity': int,
            'margin_used': Decimal,
            'usable_margin': Decimal
        }
    """
```

#### `strangle_position_sizer.py`
**Purpose:** Strangle-specific position sizing with premium consideration

#### `iron_condor_position_sizer.py`
**Purpose:** Iron condor position sizing with hedge calculation

---

## 12. Risk App (`apps/risk`)

### 12.1 Purpose
Risk limits, circuit breakers, and auto-shutdown on breach.

### 12.2 Models

#### `RiskLimit`
**Purpose:** Risk limit configuration per account

**Key Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `account` | ForeignKey | Associated account |
| `limit_type` | CharField | DAILY_LOSS, WEEKLY_LOSS, POSITION_SIZE |
| `limit_value` | DecimalField | Limit amount |
| `current_value` | DecimalField | Current tracked value |
| `is_breached` | BooleanField | Whether limit breached |
| `warning_threshold_pct` | DecimalField | Warning at this % |

#### `CircuitBreaker`
**Purpose:** Auto-shutdown triggers

---

### 12.3 Services

#### `risk_manager.py`
**Location:** `apps/risk/services/risk_manager.py`
**Purpose:** Risk checking and enforcement

**Key Functions:**
```python
def check_risk_limits(account) -> Dict:
    """Comprehensive risk check: daily + weekly limits."""

def check_daily_loss_limit(account) -> Dict:
    """Check if daily loss limit breached. Returns {breached, warning, limit, current_loss}."""

def check_weekly_loss_limit(account) -> Dict:
    """Check if weekly loss limit breached. Returns {breached, warning, limit, current_loss}."""

def activate_circuit_breaker(account, trigger_type, trigger_value, threshold_value) -> Tuple[bool, CircuitBreaker]:
    """Activate circuit breaker: Redis flag → DB record → close positions → deactivate account.
    Manual mode: sends CRITICAL exit suggestion. Autonomous: broker-first close."""

def is_circuit_breaker_active(account_id: int) -> bool:
    """Fast Redis check for active circuit breaker (used by create_position before entry)."""

def enforce_risk_limits(account) -> Tuple[bool, str]:
    """Main enforcement: check limits, activate circuit breaker if breached."""

def get_risk_status(account) -> Dict:
    """Dashboard-style risk overview: limits, breaches, warnings, active circuit breakers."""
```

**Circuit Breaker Architecture (March 2026):**
- **Redis flag**: `circuit_breaker_active_{account_id}` set immediately (24h TTL) — blocks new orders before DB record is created
- **Hardened close-all**: Autonomous mode uses `close_position(place_broker_order=True)` with 3-retry + URGENT Telegram
- **`is_circuit_breaker_active()`**: O(1) Redis check called by `create_position()` before one-position rule

---

## 13. Analytics App (`apps/analytics`)

### 13.1 Purpose
Performance tracking, P&L analysis, and pattern learning.

### 13.2 Models

#### `DailyPnL`
**Purpose:** Daily P&L summary per account

#### `Performance`
**Purpose:** Period performance (weekly/monthly/yearly)

#### `LearningPattern`
**Purpose:** Discovered trading patterns

#### `ParameterAdjustment`
**Purpose:** Suggested parameter tweaks

---

### 13.3 Services

#### `learning_engine.py`
**Location:** `apps/analytics/services/learning_engine.py`
**Purpose:** Discover trading patterns and suggest improvements

```python
def analyze_completed_trades(start_date, end_date) -> List[Dict]:
    """Analyze completed trades for patterns."""

def discover_patterns(trades) -> List[LearningPattern]:
    """Discover new patterns from trade data."""

def suggest_parameter_adjustments() -> List[ParameterAdjustment]:
    """Suggest parameter tweaks based on patterns."""
```

#### `fy_analytics.py`
**Purpose:** Financial year performance summaries

---

## 14. Alerts App (`apps/alerts`)

### 14.1 Purpose
Full interactive trading control via Telegram bot + alert notifications.

### 14.2 Telegram Bot Architecture (4-file Mixin Pattern — ~7,573 LOC)

| File | LOC | Purpose |
|------|-----|---------|
| `services/telegram_bot.py` | ~3,880 | Main `TelegramBotHandler` + callback router |
| `services/telegram_bot_menus.py` | ~1,312 | `MenuMixin` — 30 menu rendering methods |
| `services/telegram_bot_data.py` | ~1,486 | `DataMixin` — 37+ `@sync_to_async` data fetchers |
| `services/telegram_bot_trade.py` | ~895 | `TradeMixin` — 10-step manual trade wizard |

**Class:** `TelegramBotHandler(MenuMixin, DataMixin, TradeMixin)`

**Commands (9):**
| Command | Description |
|---------|-------------|
| `/start` | Main menu with 12-button grid + live header (VIX, P&L, margin) |
| `/test` | Connectivity test |
| `/positions` | Broker picker → position management |
| `/core` | Core trading settings |
| `/trade` | Manual trade wizard |
| `/orders` | Order book view |
| `/margin` | Margin & limits |
| `/pnl` | Today's P&L |
| `/analytics` | Performance analytics |

**Callback Routing (21 prefixes):**
`menu_*`, `pnl_*`, `mkt_*`, `risk_*`, `sys_*`, `task_cat_*`, `task_all_*`, `algo_*`, `tt_*`, `tr_*`, `qa_*`, `trade_*`, `ord_*`, `sl_*`, `tgt_*`, `margin_*`, `hist_*`, `login_*`, `news_*`, `tsched_*`, `select_futures_*`/`confirm_futures_*`

**Key Design:** `button_callback()` calls `query.answer()` once at top; handlers only use `edit_message_text`.

### 14.3 Unified Notification Framework *(March 2026)*

All notifications now flow through a single `notify()` API, replacing 89+ raw `send_telegram_notification()` calls.

| File | Purpose |
|------|---------|
| `notification_service.py` | Unified `notify(event_type, **kwargs)` API — single entry point for all notifications |
| `notification_templates.py` | 12 event type templates with auto-defaults (status, priority, buttons, dedup_key) |
| `notification_payload.py` | `NotificationPayload` dataclass with `collapsible: bool = True` field |
| `notification_formatter.py` | `TelegramMessageFormatter` — HTML formatting with `<blockquote expandable>` (Telegram Bot API 7.0+) |
| `button_registry.py` | 6 button sets for inline keyboards (exit confirm, options confirm, futures confirm, ack, retry, view) |
| `aggregation_buffer.py` | Redis-backed alert grouping — groups similar alerts within 30-60s window |
| `escalation_tracker.py` | Priority auto-upgrade after 3/5/10 repeated occurrences |

**Message Format:** Always-visible header (emoji + title + instrument + time + metrics) with collapsible `<blockquote expandable>` detail sections. Footer shows mode and sizing. Short messages use `collapsible=False` with flat separator.

**Anti-spam features:**
- P&L change gate: won't re-alert unless P&L moves 2%+ (SL) or 1%+ (exit suggestion)
- Exit suggestion dedup: same reason within 5-min cooldown is skipped
- Aggregation buffer flushes via `flush_notification_buffer` Celery task

### 14.4 Alert Manager (Legacy)

#### `alert_manager.py`
**Purpose:** Route alerts to appropriate channels

```python
def send_alert(message, priority='INFO'):
    """
    Send alert based on priority.

    Priority levels:
    - INFO: Telegram only
    - WARNING: Telegram + log
    - CRITICAL: Telegram + SMS (if configured)
    """
```

---

## 15. Background Tasks (Celery)

### 15.1 Configuration
**Location:** `mcube_ai/celery.py`

**Key Components:**
- `get_static_schedule()` — Defines ~27 static tasks
- `load_beat_schedule()` — Reads DB, filters disabled tasks, applies custom schedules
- `_build_custom_schedule()` — Builds per-hour crontabs from `CeleryTaskState`
- `DBReloadScheduler` — Custom `PersistentScheduler` subclass that reloads from DB

**CRITICAL:** Always start beat with `--scheduler=mcube_ai.celery:DBReloadScheduler`

**Task Guard:** All tasks use `@task_enabled_guard` decorator for runtime enable/disable check.

**6 Task Categories:** data, strategies, transactions, monitoring, risk, reports

**Global Time Limits:** `task_time_limit=300` (5 min hard), `task_soft_time_limit=240` (4 min soft)
**Futures batch:** `soft_time_limit=540` (9 min), `time_limit=720` (12 min), `MAX_BATCH_SECONDS=480`

### 15.2 Daily Task Schedule

| Time | Task | Purpose |
|------|------|---------|
| 06:45 | `health_check_brokers` | Broker connectivity health check |
| 07:00 | `morning_data_sync` | Full market data update |
| 08:30 | `fetch_trendlyne_data` | Trendlyne data fetch |
| 08:50 | `update_pre_market_data` | Pre-market update |
| 08:55 | `setup_trading_day` | Trading day setup |
| 08:55 | `review_overnight_positions` | Review overnight position status |
| 09:00 | `send_morning_briefing` | Morning market briefing via Telegram |
| 09:00-09:20 | `monitor_opening_volatility` | Opening volatility monitor (every 5 min) |
| 09:15 | `start_trading_day` | Market open validation |
| 09:30 | `evaluate_options_strategy` | Check strangle entry |
| 09:40 | `start_options_trade` | Execute options trade |
| 09:40-10:30 | `batch_options_averaging` | Options averaging (every 1 min) |
| 09:40 | `execute_futures_algorithm` | Futures screening + scoring (batch_size=2) |
| 09:30 | `screen_futures_opportunities` | Pre-market futures scan |
| Every 10 min (9:40-14:30) | `check_futures_averaging` | Futures averaging |
| Every 15 min | `monitor_all_strangle_deltas` | Strangle delta monitoring (threshold: 300) |
| Every 1 min (9 AM-3:59 PM) | `monitor_and_manage_positions` | Position monitoring: sync, P&L, SR engine, exits |
| Every 1 min | `check_risk_limits_all_accounts` | Risk limits + intraday drawdown + portfolio aggregate |
| Every 1 min (9 AM-3:59 PM) | `monitor_circuit_breakers` | Circuit breaker status monitoring |
| Dynamic | `evaluate_kotak_strangle_exit` | Strangle profit check and exit (via dynamic scheduler) |
| 15:15 | `alert_open_positions_pre_close` | Pre-close open position summary |
| 15:25 | `close_trading_day` | Close positions with profit conditions |
| 15:35 | `update_post_market_data` | After-hours data |
| 15:45 | `reconcile_positions_eod` | EOD reconciliation: sync broker → compare DB |
| 16:00 | `generate_daily_pnl_report` | Daily P&L breakdown |
| 16:00 | `sync_benchmark_data` | Nifty/BankNifty benchmark sync |
| 16:30 | `daily_data_aggregation` | Sync trades, update DailyPnL |
| 17:00 | `update_equity_curves` | Equity curve snapshots |
| 17:00 | `update_learning_patterns` | Pattern learning update |
| 18:00 | `generate_daily_risk_report` | End-of-day risk report |
| Friday 18:00 | `weekly_summary` | Weekly performance summary |

### 15.3 Task Queues

```python
# In celery.py
task_routes = {
    'apps.data.tasks.*': {'queue': 'data'},
    'apps.strategies.tasks.*': {'queue': 'strategies'},
    'apps.positions.tasks.*': {'queue': 'monitoring'},
    'apps.alerts.tasks.*': {'queue': 'notifications'},
    'apps.analytics.tasks.*': {'queue': 'analytics'},
}
```

---

## 16. Constants and Configuration

### 16.1 Location
**File:** `apps/core/constants.py`

### 16.2 Key Constants

```python
# Brokers
BROKER_KOTAK = 'KOTAK'
BROKER_ICICI = 'ICICI'
BROKER_CHOICES = [(BROKER_KOTAK, 'Kotak Neo'), (BROKER_ICICI, 'ICICI Breeze')]

# Directions
DIRECTION_LONG = 'LONG'
DIRECTION_SHORT = 'SHORT'
DIRECTION_NEUTRAL = 'NEUTRAL'

# Position Status
POSITION_STATUS_SUGGESTED = 'SUGGESTED'
POSITION_STATUS_APPROVED = 'APPROVED'
POSITION_STATUS_OPEN = 'OPEN'
POSITION_STATUS_CLOSED = 'CLOSED'
POSITION_STATUS_REJECTED = 'REJECTED'
POSITION_STATUS_EXPIRED = 'EXPIRED'

# Strategy Types
STRATEGY_WEEKLY_STRANGLE = 'WEEKLY_NIFTY_STRANGLE'
STRATEGY_LLM_FUTURES = 'LLM_VALIDATED_FUTURES'
STRATEGY_IRON_CONDOR = 'BROKEN_IRON_CONDOR'

# Exit Times
KOTAK_EXIT_TIME = time(15, 15)  # 3:15 PM
MANDATORY_EXIT_TIME = time(15, 25)  # 3:25 PM

# Weekdays
WEEKDAY_THURSDAY = 3
WEEKDAY_FRIDAY = 4
```

---

## 17. Common Modification Scenarios

### 17.1 Change Strike Distance for Strangle

**File:** `apps/strategies/shared/strike_calculator.py`

```python
# Current:
base_delta = 0.5  # 0.5% base delta

# To make strikes wider:
base_delta = 0.7  # 0.7% base delta
```

### 17.2 Change LLM Confidence Threshold

**File:** `apps/strategies/models.py` (StrategyConfig model)

```python
# Current default:
min_llm_confidence = models.DecimalField(..., default=Decimal('70.00'))

# To change default to 80%:
min_llm_confidence = models.DecimalField(..., default=Decimal('80.00'))
```

Or change per-account in database.

### 17.3 Add New Entry Filter

1. Create new file: `apps/strategies/filters/your_filter.py`

```python
def check_your_condition(market_data: Dict) -> Dict:
    """
    Your filter description.

    Returns:
        {
            'passed': bool,
            'reason': str,
            'data': dict
        }
    """
    # Your logic here
    if condition_met:
        return {'passed': True, 'reason': 'Condition satisfied', 'data': {...}}
    return {'passed': False, 'reason': 'Condition not met', 'data': {...}}
```

2. Import in entry workflow: `apps/strategies/core/entry_workflow.py`

### 17.4 Change Exit Time

**File:** `apps/positions/services/exit_manager.py`

```python
# Current (line ~128):
if current_time.time() < time(15, 15):

# To exit at 3:00 PM:
if current_time.time() < time(15, 0):
```

### 17.5 Add New Telegram Command

**File:** `apps/alerts/services/telegram_bot.py`

```python
async def new_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /newcommand."""
    # Your logic here
    await update.message.reply_text("Response")

# Add to command list:
application.add_handler(CommandHandler("newcommand", new_command_handler))
```

---

## 18. Data Flow Diagrams

### 18.1 Trade Entry Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TRADE ENTRY FLOW                                │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Celery    │     │  Strategy   │     │   Filters   │     │   Position  │
│  Scheduler  │ ──► │  evaluate() │ ──► │   check()   │ ──► │   check()   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                              │                    │
                                              │ All pass?          │ has_open_position?
                                              ▼                    ▼
                                        ┌─────────────┐     ┌─────────────┐
                                        │   Market    │     │   Margin    │
                                        │    Data     │ ◄── │   check()   │
                                        └─────────────┘     └─────────────┘
                                              │
                                              ▼
                    ┌─────────────────────────────────────────────────────┐
                    │                   LLM VALIDATION                    │
                    │           (Futures only, confidence >= 70%)         │
                    └─────────────────────────────────────────────────────┘
                                              │
                                              ▼
                                        ┌─────────────┐
                                        │   Create    │
                                        │ Suggestion  │
                                        └─────────────┘
                                              │
                                              ▼
                    ┌─────────────────────────────────────────────────────┐
                    │                HUMAN APPROVAL (Telegram)            │
                    └─────────────────────────────────────────────────────┘
                                              │
                                              ▼
                                        ┌─────────────┐
                                        │   Execute   │
                                        │   Order     │
                                        └─────────────┘
                                              │
                                              ▼
                                        ┌─────────────┐
                                        │   Create    │
                                        │  Position   │
                                        └─────────────┘
```

### 18.2 Position Monitoring Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       POSITION MONITORING FLOW                          │
└─────────────────────────────────────────────────────────────────────────┘

   ┌─────────────┐
   │   Every     │
   │  10 seconds │
   └──────┬──────┘
          │
          ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │              FOR EACH OPEN POSITION                             │
   └─────────────────────────────────────────────────────────────────┘
          │
          ├──► Update current_price (from broker)
          │
          ├──► Calculate unrealized_pnl
          │
          └──► Check exit conditions
                    │
                    ├── Stop-loss hit? ──► EXIT IMMEDIATELY
                    │
                    ├── Target hit? ──► EXIT IMMEDIATELY
                    │
                    ├── EOD time? ──► Check 50% profit rule
                    │                        │
                    │                        ├── >= 50%? ──► EXIT
                    │                        └── < 50%? ──► HOLD
                    │
                    ├── Expiry day? ──► EXIT IMMEDIATELY
                    │
                    └── Delta threshold? ──► ALERT (Strangle only)
```

---

## 19. Debugging Guide

### 19.1 Log Files

```bash
# Main application log
tail -f logs/mcube_ai.log

# Celery worker log
tail -f logs/celery_worker.log

# Filter by component
grep "strangle" logs/mcube_ai.log
grep "exit_manager" logs/mcube_ai.log
grep "ERROR" logs/mcube_ai.log
```

### 19.2 Django Shell

```bash
python manage.py shell
```

```python
# Check open positions
from apps.positions.models import Position
Position.objects.filter(status='OPEN').values('instrument', 'direction', 'unrealized_pnl')

# Check account margin
from apps.accounts.models import BrokerAccount
acc = BrokerAccount.objects.get(broker='KOTAK')
print(f"Available: {acc.get_available_capital()}")

# Check task state
from apps.core.models import CeleryTaskState
CeleryTaskState.objects.filter(is_enabled=True).values('task_key', 'is_enabled')

# Check flags
from apps.core.models import NseFlag
NseFlag.objects.all().values('flag', 'value')
```

### 19.3 Common Issues

| Issue | Likely Cause | Fix |
|-------|--------------|-----|
| No trades executing | Task not enabled | Enable in CeleryTaskState |
| Position not created | ONE POSITION RULE | Check existing positions |
| LLM validation failing | Ollama not running | Start Ollama service |
| Broker auth failing | Session expired | Run breeze_auto_login |
| Exit not triggering | Time zone issue | Check IST conversion |

---

## 20. Testing Strategy

### 20.1 Unit Tests

```bash
# Run all tests
pytest

# Run specific app tests
pytest apps/positions/tests/

# Run with coverage
pytest --cov=apps --cov-report=html
```

### 20.2 Paper Trading Mode

```python
# In BrokerAccount model
is_paper_trading = True  # Orders won't actually execute
```

### 20.3 Test Specific Scenarios

```python
# Test ONE POSITION RULE
from apps.positions.models import Position
from apps.accounts.models import BrokerAccount

acc = BrokerAccount.objects.get(broker='KOTAK')
print(f"Has position: {Position.has_open_position(acc)}")

# Test exit conditions
from apps.positions.services.exit_manager import check_exit_conditions
pos = Position.objects.get(id=1)
result = check_exit_conditions(pos)
print(result)
```

---

## Appendix A: Quick Reference

### File Locations

| Need to change | File |
|----------------|------|
| Strike calculation | `apps/strategies/shared/strike_calculator.py` |
| Exit logic | `apps/positions/services/exit_manager.py` |
| Averaging rules | `apps/positions/services/averaging_manager.py` |
| Entry filters | `apps/strategies/filters/` |
| LLM validation | `apps/llm/services/trade_validator.py` |
| Risk limits | `apps/risk/services/risk_manager.py` |
| Telegram commands | `apps/alerts/services/telegram_bot.py` |
| Celery schedule | `mcube_ai/celery.py` |
| Constants | `apps/core/constants.py` |

### Django Commands

```bash
python manage.py runserver              # Start web server
python manage.py shell                   # Interactive shell
python manage.py breeze_auto_login       # Login to Breeze
python manage.py makemigrations          # Create migrations
python manage.py migrate                 # Apply migrations
```

### Celery Commands

```bash
celery -A mcube_ai worker -l info        # Start worker
celery -A mcube_ai beat -l info          # Start scheduler
celery -A mcube_ai inspect active        # Check active tasks
```

---

*Document maintained by mCube development team. Last updated February 2026.*
