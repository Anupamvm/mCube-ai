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
    │  │           Django Backend (12 Apps)               │    │
    │  │    core | accounts | positions | orders |        │    │
    │  │    strategies | risk | data | llm | analytics |  │    │
    │  │    alerts | brokers | trading                    │    │
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
| Tasks | Celery 5.3 + background_task | Background automation |
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
├── apps/               # Django applications (12 apps)
│   ├── core/          # Shared utilities, credentials
│   ├── accounts/      # Broker accounts
│   ├── positions/     # Position tracking
│   ├── orders/        # Order management
│   ├── strategies/    # Trading strategies
│   ├── risk/          # Risk management
│   ├── data/          # Market data, Trendlyne
│   ├── llm/           # LLM validation
│   ├── analytics/     # P&L tracking
│   ├── alerts/        # Telegram bot
│   ├── brokers/       # Broker integrations
│   └── trading/       # Trading workflows
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

### accounts
BrokerAccount model with capital allocation and risk limits. APICredential for broker auth.

### positions
Position tracking with entry/exit, P&L calculation, MonitorLog for position checks.

### orders
Order placement and execution tracking.

### strategies
Kotak strangle and ICICI futures strategy implementations.

### risk
RiskLimit model, circuit breakers, real-time monitoring.

### data
Trendlyne integration, market data, security master, news articles.

### llm
Ollama/vLLM client, trade validation, RAG queries, news sentiment analysis.

### analytics
Daily/weekly P&L tracking, performance analysis.

### alerts
Telegram bot integration with 14 commands.

### brokers
Broker API integrations (Kotak Neo, ICICI Breeze), order placement services.

### trading
Trading workflows, trade suggestions, approval system.

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
status = CharField()              # ACTIVE, CLOSED, PENDING

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
```

---

## Background Tasks

Tasks run via **Celery** and **Django background_task**:

| Category | Frequency |
|----------|-----------|
| Position Monitoring | Every 10-30 sec |
| Risk Management | Every 30-60 sec |
| Market Data | Every 5 min |
| Strategy Evaluation | Scheduled times |
| Reports | EOD/EOW |

---

## Data Flow

```
1. Market Data Sync (Celery/Trendlyne)
       ↓
2. Strategy Evaluation
       ↓
3. LLM Validation (futures only)
       ↓
4. Human Approval (Telegram)
       ↓
5. Order Placement (Broker API)
       ↓
6. Position Monitoring
       ↓
7. Exit Execution
       ↓
8. P&L Recording
```

---

## URL Routes

| Path | App | Purpose |
|------|-----|---------|
| `/` | core | Home page |
| `/admin/` | django | Admin interface |
| `/system/` | core | System test page |
| `/accounts/` | accounts | Account management |
| `/brokers/` | brokers | Broker dashboard |
| `/positions/` | positions | Position management |
| `/orders/` | orders | Order management |
| `/strategies/` | strategies | Strategy config |
| `/risk/` | risk | Risk limits |
| `/data/` | data | Market data |
| `/llm/` | llm | LLM interface |
| `/analytics/` | analytics | Analytics dashboard |
| `/alerts/` | alerts | Alert config |
| `/trading/` | trading | Trading interface |

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
