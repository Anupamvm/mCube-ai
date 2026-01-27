# mCube AI Trading System - Documentation

**AI-Powered Multi-Strategy F&O Trading System for Indian Markets**

---

## What is mCube?

mCube is an automated trading system that manages two broker accounts with different trading strategies:

| Account | Broker | Capital | Strategy | Target Return |
|---------|--------|---------|----------|---------------|
| **Kotak** | Kotak Neo | Rs 6 Crores | Weekly Nifty Short Strangle / Broken Iron Condor | Rs 6-8L/month |
| **ICICI** | ICICI Breeze | Rs 1.2 Crores | LLM-Validated Futures Trading | Rs 4-6L/month |

**Combined Target**: Rs 12-15L monthly (1.7-2.1% monthly, 20-25% annually)

---

## Core Philosophy

### Critical Rule: ONE POSITION PER ACCOUNT

The most important rule in mCube: **Only ONE active position per broker account at any time.**

This rule:
- Prevents over-exposure
- Simplifies risk management
- Makes P&L tracking clear
- Is enforced at the code level (not just documentation)

### 50% Margin Rule

For any new position, use only 50% of available margin. The remaining 50% is reserved for:
- Averaging opportunities (when position goes against you)
- Emergency adjustments
- Margin calls

---

## System Architecture

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
    │  │    brokers | trading                             │    │
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
| LLM | Ollama (DeepSeek) | Trade validation |
| Vector DB | ChromaDB | RAG system |
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
├── apps/               # Django applications (11 apps)
│   ├── core/          # Shared utilities, credentials, scheduling
│   ├── accounts/      # Broker accounts, margin management
│   ├── positions/     # Position tracking, P&L, exit logic
│   ├── strategies/    # Trading algorithms (Strangle, Futures)
│   ├── risk/          # Risk limits, circuit breakers
│   ├── data/          # Market data, Trendlyne integration
│   ├── llm/           # LLM validation, RAG, news processing
│   ├── analytics/     # P&L tracking, learning patterns
│   ├── alerts/        # Telegram bot
│   ├── brokers/       # Broker API integrations, orders
│   └── trading/       # Trading workflows, UI
│
├── tools/             # Standalone broker utilities
│   └── neo.py        # Kotak Neo API wrapper
│
├── templates/         # HTML templates
├── static/            # CSS, JS assets
├── logs/              # Application logs
└── docs/              # This documentation
```

---

## The 11 Django Apps

| App | Purpose | Key Responsibilities |
|-----|---------|---------------------|
| **core** | Foundation | Credentials, constants, utilities, background tasks |
| **accounts** | Account Management | BrokerAccount model, margin calculations |
| **positions** | Position Lifecycle | Entry, monitoring, exit, averaging, P&L |
| **strategies** | Trading Logic | Strangle, Iron Condor, Futures algorithms |
| **risk** | Risk Management | Limits, circuit breakers, auto-shutdown |
| **data** | Market Data | Trendlyne, analyzers, validators, signals |
| **llm** | AI Integration | Trade validation, news processing, RAG |
| **analytics** | Performance | P&L reports, pattern discovery, learning |
| **alerts** | Notifications | Telegram bot with 14 commands |
| **brokers** | Broker APIs | Kotak Neo, ICICI Breeze integrations |
| **trading** | Trading UI | Suggestions, approval, execution |

For detailed documentation of each app, see the [apps/](apps/) directory.

---

## Trading Strategies

### 1. Weekly Nifty Short Strangle (Kotak)

**Concept**: Sell both a call and put option at out-of-the-money strikes, collecting premium.

- **When**: Monday/Tuesday entry, Thursday/Friday exit
- **Strikes**: Calculated using VIX-adjusted delta formula
- **Profit**: If NIFTY stays within the strike range, keep all premium
- **Risk**: Unlimited if market moves significantly

### 2. Broken Iron Condor (Kotak)

**Concept**: Short strangle plus an insurance put to cap downside risk.

- **3 Legs**: Sell Call + Sell Put + Buy Put (insurance)
- **Benefit**: Defined maximum loss (2x expected profit)
- **When**: High VIX environments or uncertain markets

### 3. LLM-Validated Futures (ICICI)

**Concept**: Directional futures trading with AI validation.

- **Screening**: 9-factor composite scoring (OI, sector, technical)
- **Validation**: LLM with 70% minimum confidence
- **Averaging**: Up to 3 averaging attempts if position goes against

See [03-TRADING-STRATEGIES.md](03-TRADING-STRATEGIES.md) for full algorithm details.

---

## Quick Reference

### Core Trading Rules

```
1. ONE POSITION PER ACCOUNT AT ANY TIME
2. 50% MARGIN FOR FIRST TRADE
3. OPTIONS: Skip if < 1 day to expiry
4. FUTURES: Skip if < 15 days to expiry
5. EXIT EOD only if >= 50% target achieved
```

### Essential Commands

```bash
# Start Django
python manage.py runserver

# Start Redis
redis-server

# Start Celery worker
celery -A mcube_ai worker -l info

# Start Celery beat scheduler
celery -A mcube_ai beat -l info

# Start Telegram bot
python manage.py run_telegram_bot

# View logs
tail -f logs/mcube_ai.log
```

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | List all commands |
| `/status` | System overview |
| `/positions` | All active positions |
| `/position <id>` | Specific position details |
| `/accounts` | Account balances |
| `/risk` | Risk limits status |
| `/pnl` | Today's P&L |
| `/pnl_week` | This week's P&L |
| `/close <id>` | Close specific position |
| `/closeall` | Emergency close all |
| `/pause` | Pause trading |
| `/resume` | Resume trading |
| `/logs` | Recent system events |

---

## Documentation Reading Guide

### For First-Time Setup

1. **[01-GETTING-STARTED.md](01-GETTING-STARTED.md)** - Installation and first run

### For Understanding the System

2. **[02-ARCHITECTURE.md](02-ARCHITECTURE.md)** - High-level architecture
3. **[03-TRADING-STRATEGIES.md](03-TRADING-STRATEGIES.md)** - Trading algorithms

### For Broker & Data Integration

4. **[04-BROKER-INTEGRATION.md](04-BROKER-INTEGRATION.md)** - Connecting to brokers
5. **[05-DATA-SOURCES.md](05-DATA-SOURCES.md)** - Market data and LLM

### For Daily Operations

6. **[06-OPERATIONS.md](06-OPERATIONS.md)** - Running and monitoring

### For Deep Dives (Junior Developers Start Here)

7. **[apps/](apps/)** - Detailed documentation for each Django app
8. **[ALGORITHMS.md](ALGORITHMS.md)** - Algorithm study guide

---

## Access Points

| URL | Purpose |
|-----|---------|
| http://localhost:8000/ | Home page |
| http://localhost:8000/admin/ | Django Admin |
| http://localhost:8000/system/test/ | System Health Check |
| http://localhost:8000/brokers/ | Broker dashboard |
| http://localhost:8000/trading/ | Trading interface |
| http://localhost:8000/positions/ | Positions management |
| http://localhost:8000/analytics/ | Analytics dashboard |
| http://localhost:8000/llm/ | LLM interface |

---

## For Junior Developers

If you're new to the codebase, follow this learning path:

1. **Read this README** - Understand the system overview
2. **Read [apps/core.md](apps/core.md)** - Understand the foundation
3. **Read [apps/accounts.md](apps/accounts.md)** - Understand account structure
4. **Read [apps/positions.md](apps/positions.md)** - Understand position lifecycle
5. **Read [apps/strategies.md](apps/strategies.md)** - Understand the algorithms
6. **Read [ALGORITHMS.md](ALGORITHMS.md)** - Deep dive into algorithm logic
7. **Run the system locally** - Follow 01-GETTING-STARTED.md
8. **Study the code** - Start with `apps/core/models.py`

---

## Master Design Document

For complete system design with all formulas and implementation details:
- **[design/mcube-ai.design.md](design/mcube-ai.design.md)**

---

*Last Updated: January 2026*
