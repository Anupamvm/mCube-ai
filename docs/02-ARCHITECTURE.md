# System Architecture

This document explains how mCube is built and how all components work together.

---

## High-Level Overview

```
                     mCube AI Trading System
    ┌─────────────────────────────────────────────────────────┐
    │                 Django Application                       │
    │  ┌─────────────────────────────────────────────────┐    │
    │  │    Frontend (Templates + Bootstrap 5 + HTMX)    │    │
    │  └─────────────────────────────────────────────────┘    │
    │  ┌─────────────────────────────────────────────────┐    │
    │  │           Django Backend (11 Apps)               │    │
    │  │    core | accounts | positions | strategies |    │    │
    │  │    risk | data | llm | analytics | alerts |      │    │
    │  │    brokers | trading | algo_test                  │    │
    │  └─────────────────────────────────────────────────┘    │
    │  ┌─────────────────────────────────────────────────┐    │
    │  │    Celery Workers + Django Background Tasks      │    │
    │  └─────────────────────────────────────────────────┘    │
    │  ┌─────────────────────────────────────────────────┐    │
    │  │    SQLite (data) | Redis (cache/queue)          │    │
    │  └─────────────────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────┘
                               │
    ┌─────────────────────────────────────────────────────────┐
    │  Kotak Neo | ICICI Breeze | Trendlyne | Telegram | LLM  │
    └─────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Framework | Django 4.2 | Web application |
| Database | SQLite | Persistent storage |
| Cache/Queue | Redis | Celery message broker |
| Tasks | Celery 5.3 (Redis broker) | Background automation |
| Frontend | Bootstrap 5 + HTMX | UI |
| LLM | Ollama | Trade validation |
| Alerts | Telegram Bot | Notifications |

---

## Project Structure

```
mCube-ai/
├── mcube_ai/           # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── celery.py
│
├── apps/               # Django applications (11 installed apps)
│   ├── core/          # Shared utilities, credentials, TradingCoreConfig, TradingContext
│   ├── accounts/      # Broker accounts
│   ├── positions/     # Position tracking
│   ├── strategies/    # Trading strategies, dynamic scheduler
│   ├── risk/          # Risk management
│   ├── data/          # Market data, Trendlyne, GNews
│   ├── llm/           # LLM validation, analyst reports
│   ├── analytics/     # P&L tracking
│   ├── alerts/        # Telegram bot (4-file mixin architecture, ~7.5K LOC)
│   ├── brokers/       # Broker integrations, orders, session management
│   ├── trading/       # Trading workflows, trade confirmation service
│   └── algo_test/     # Algorithm testing
│
├── templates/          # HTML templates
├── static/             # CSS, JS assets
├── logs/               # Application logs
└── docs/               # Documentation
```

---

## Django Applications

### core
Shared utilities, CredentialStore model, trading state management, system test page.
**Key services:**
- `TradingCoreConfig` — Singleton model for centralized trading control (position sizing modes: TEST/MANUAL/AUTO/SIMULATED, notification levels: FULL_CONTROL/SUPERVISED/AUTONOMOUS)
- `TradingContext` (`apps/core/services/trading_context.py`) — Unified context for Celery tasks & web views (account retrieval, trading day validation, config access)
- `CeleryTaskState` — Enable/disable + custom schedule per task, 6 categories (data, strategies, transactions, monitoring, risk, reports)
- `@task_enabled_guard` decorator — Runtime safety check for all scheduled tasks

### accounts
BrokerAccount model with capital allocation and risk limits.

### positions
Position tracking with entry/exit, P&L calculation, MonitorLog for position checks.
- `PositionMonitorDashboard` — Anti-spam single Telegram message per day, edited in place
- S/R Exit Engine with 3-stage warnings (NEAR_SL → STRUCTURAL_PRESSURE → TRIGGER)
- `position_manager.py` — ONE POSITION RULE with Redis lock + circuit breaker gate
- `close_position(place_broker_order=True)` — Broker-first close for autonomous exits

### strategies
Kotak strangle and ICICI futures strategy implementations.
- `DynamicScheduler` for `TradingScheduleConfig`-based task scheduling
- Enhanced futures analyzer with 13-component parallel analysis (315pts → 100 scale)
- **New services:**
  - `adaptive_sl_target.py` — 3-tier SL/target engine (S/R → ATR×regime → volatility%)
  - `market_regime.py` — Market regime detection (TRENDING/RANGING/VOLATILE/BREAKOUT/NORMAL)
  - `contract_prefilter.py` — Lightweight DB-only contract pre-filter
  - `trade_validation.py` — Post-score R:R and regime validation gate
  - `llm_context_builder.py` — Enriched LLM context with regime + scoring summary

### risk
RiskLimit model, circuit breakers, real-time monitoring.
- Redis circuit breaker flag — immediate O(1) check blocks all new orders
- Intraday unrealized drawdown monitoring (10% warning, 15% critical)
- Portfolio-level aggregate drawdown across all accounts

### data
Trendlyne integration, market data, security master, news articles.
- GNews API with 8-hour cache (`CACHE_TTL = 28800`)
- Three-layer caching: GNews API → NewsArticle DB → In-memory (30 min)

### llm
Ollama/vLLM client, trade validation, RAG queries, news sentiment analysis.
- Analyst report analyzer with 8-hour DB cache

### analytics
Daily/weekly P&L tracking, performance analysis.

### alerts
Telegram bot — full app control via 4-file mixin architecture (~7,573 LOC):
- `telegram_bot.py` — Main handler + callback router (~3,880 LOC)
- `telegram_bot_menus.py` — MenuMixin (30 methods)
- `telegram_bot_data.py` — DataMixin (37+ `@sync_to_async` methods)
- `telegram_bot_trade.py` — TradeMixin (25 methods, 10-step manual trade wizard)
- 9 slash commands, 12-button main menu, 21 callback routing prefixes
- **Unified notification framework** (`notify()` API):
  - `notification_service.py` — Single entry point for all notifications, replaces raw `send_telegram_notification()` calls
  - `notification_templates.py` — 12 event types with auto-defaults (status, priority, buttons, dedup_key)
  - `aggregation_buffer.py` — Redis-backed grouping of similar alerts within 30-60s window
  - `escalation_tracker.py` — Auto-upgrades priority after 3/5/10 repeated occurrences
  - `notification_formatter.py` — HTML formatter with Telegram `<blockquote expandable>` for collapsible details

### brokers
Broker API integrations (Kotak Neo v2, ICICI Breeze), order placement, Order and Execution models.
- Neo v2: TOTP + MPIN auth (no OTP), session persistence via `base_url`
- Breeze: Singleton session manager with auto-login (Selenium + Telegram OTP)
- Auto-login safety: one attempt per day per broker

### trading
Trading workflows, trade suggestions, approval system.
- `TradeConfirmationService` — Telegram confirmation flow (futures, options, exit)
- Two-step futures approval: selection screen → detail view → execute with batching
- Order batching: orders > 10 lots split, 10-second delay, stop execution button
- Hybrid Telegram format: compact headline with score/R:R/regime + labeled sections
- Web UI: color-coded score badges, R:R display, regime badges, quality grades
- `TradeSuggestion` model: `composite_score`, `regime`, `is_pending` properties

---

## Key Models

### BrokerAccount (apps/accounts/models.py)
```python
broker = CharField()              # KOTAK or ICICI
account_number = CharField()
account_name = CharField()
allocated_capital = DecimalField()
is_active = BooleanField()
is_paper_trading = BooleanField()
max_daily_loss = DecimalField()
max_weekly_loss = DecimalField()

# Methods
get_available_capital()           # Returns capital not deployed
get_total_pnl()                   # Returns total P&L
```

### Position (apps/positions/models.py)
```python
account = ForeignKey(BrokerAccount)
strategy_type = CharField()       # STRANGLE, FUTURES
instrument = CharField()
direction = CharField()           # LONG, SHORT, NEUTRAL
quantity = IntegerField()
lot_size = IntegerField()
entry_price = DecimalField()
current_price = DecimalField()
stop_loss = DecimalField()
target = DecimalField()
status = CharField()              # SUGGESTED, APPROVED, OPEN, CLOSED, REJECTED, EXPIRED
                                  # (ACTIVE is an alias for OPEN)

# Strangle-specific
call_strike = DecimalField()
put_strike = DecimalField()
call_premium = DecimalField()
put_premium = DecimalField()
premium_collected = DecimalField()
current_delta = DecimalField()

# P&L
realized_pnl = DecimalField()
unrealized_pnl = DecimalField()
margin_used = DecimalField()

# Averaging
averaging_count = IntegerField()
original_entry_price = DecimalField()
```

### Order (apps/brokers/models.py)
```python
account = ForeignKey(BrokerAccount)
position = ForeignKey(Position)       # Optional
order_type = CharField()              # MARKET, LIMIT, SL, SLM
direction = CharField()               # LONG, SHORT
instrument = CharField()
quantity = IntegerField()
price = DecimalField()                # For LIMIT orders
status = CharField()                  # PENDING, PLACED, FILLED, CANCELLED
broker_order_id = CharField()
filled_quantity = IntegerField()
average_price = DecimalField()

# Methods
mark_placed(broker_order_id)
mark_filled(average_price)
mark_cancelled(reason)
```

### CredentialStore (apps/core/models.py)
```python
service = CharField()             # breeze, kotakneo, trendlyne, telegram
name = CharField()
api_key = CharField()
api_secret = CharField()
session_token = CharField()
username = CharField()
password = CharField()
neo_password = CharField()        # Kotak MPIN
pan = CharField()
sid = CharField()                 # Session ID
# Kotak Neo v2 fields
ucc = CharField()                 # Unique Client Code
totp_secret = CharField()         # TOTP secret for automated login
mobile_number = CharField()       # Mobile number
neo_base_url = URLField()         # API base URL (required for v2 API calls)
neo_data_center = CharField()     # Data center
# Auto-login tracking
auto_login_status = CharField()   # none|in_progress|success|failed
auto_login_date = DateField()     # Date of last attempt
```

---

## Background Tasks

Tasks run via **Celery** with Redis as broker:

| Category | Frequency |
|----------|-----------|
| Position Monitoring | Every 1 min |
| Risk Management | Every 30-60 sec |
| Market Data | Every 5 min |
| Strategy Evaluation | Scheduled times |
| Reports | EOD/EOW |

---

## Data Flow

```
1. Market Data Sync (Celery/Trendlyne)
       ↓
2. Market Regime Detection (NIFTY ADX + ATR + VIX)
       ↓
3. Contract Pre-filter (ADX, Volume, RSI)
       ↓
4. Strategy Evaluation (13-factor scoring, 315pts → 100)
       ↓
5. Trade Validation Gate (R:R >= 1.5 preferred, reject < 1.0, regime checks)
       ↓
6. LLM Validation (enriched context with regime + scoring)
       ↓
7. Human Approval (Telegram — hybrid format)
       ↓
8. Order Placement (Broker API)
       ↓
9. Position Monitoring (adaptive SL/target, hold flag)
       ↓
10. Exit Execution (smart re-alert on held positions)
       ↓
11. P&L Recording
```

---

## URL Routes

| Path | App | Purpose |
|------|-----|---------|
| `/` | core | Home page |
| `/admin/` | django | Admin interface |
| `/system/` | core | System test page |
| `/accounts/` | accounts | Account management |
| `/brokers/` | brokers | Broker dashboard, orders |
| `/positions/` | positions | Position management |
| `/strategies/` | strategies | Strategy config |
| `/risk/` | risk | Risk limits |
| `/data/` | data | Market data |
| `/llm/` | llm | LLM interface |
| `/analytics/` | analytics | Analytics dashboard |
| `/alerts/` | alerts | Alert config |
| `/trading/` | trading | Trading interface |

### Trading API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/trading/api/calculate-position/` | POST | Calculate position sizing |
| `/trading/api/calculate-pnl/` | POST | Calculate P&L scenarios |
| `/trading/api/place-futures-order/` | POST | Place futures order |
| `/trading/api/order-status/<id>/` | GET | Check order status |
| `/trading/api/get-margins/` | GET | Get margin data |
| `/trading/api/suggestions/` | GET | List trade suggestions |
| `/trading/api/suggestions/<id>/` | GET | Get suggestion details |
| `/trading/api/get-positions/` | GET | Get active positions |
| `/trading/api/close-position/` | POST | Close a position |
| `/trading/api/get-option-premiums/` | GET | Get option chain premiums |
| `/trading/api/get-lot-size/` | GET | Get lot size for instrument |
| `/trading/api/get-contract-details/` | GET | Get contract details |
| `/trading/api/get-breeze-historical-data/` | POST | Fetch historical OHLC data |
| `/trading/api/get-stored-historical-data/` | GET | Retrieve stored historical data |
| `/trading/api/prepare-historical-data/` | POST | Prepare data for analysis |
| `/trading/api/get-related-instruments/` | GET | Get related instruments |
| `/trading/api/verify-historical-data/` | POST | Verify historical data |

### Trading Trigger Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/trading/trigger/futures/` | POST | Trigger futures algorithm |
| `/trading/trigger/strangle/` | POST | Trigger strangle algorithm |
| `/trading/trigger/iron-condor/` | POST | Trigger iron condor |
| `/trading/trigger/verify/` | POST | Verify trade setup |
| `/trading/trigger/start-trendlyne-fetch/` | POST | Start Trendlyne data fetch |
| `/trading/trigger/fetch-news/` | POST | Fetch market news |
| `/trading/trigger/update-breeze-session/` | POST | Refresh Breeze session |
| `/trading/trigger/update-neo-session/` | POST | Refresh Neo session |

---

## Security

- All credentials in CredentialStore model
- Environment variables for sensitive config
- Admin-only access to sensitive views
- Login required for most views

---

## For Complete Details

See the master design document:
- **[design/mcube-ai.design.md](design/mcube-ai.design.md)** (1,800+ lines)

---

*See [03-TRADING-STRATEGIES.md](03-TRADING-STRATEGIES.md) for trading logic.*
