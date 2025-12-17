# mCube AI Trading System - Documentation

**AI-Powered Multi-Strategy F&O Trading System for Indian Markets**

---

## What is mCube?

mCube is an automated trading system that manages two accounts with different strategies:

| Account | Capital | Strategy | Target Return |
|---------|---------|----------|---------------|
| **Kotak** | Rs 6 Crores | Weekly Nifty Short Strangle | Rs 6-8L/month |
| **ICICI** | Rs 1.2 Crores | LLM-Validated Futures Trading | Rs 4-6L/month |

**Combined Target**: Rs 12-15L monthly (1.7-2.1% monthly, 20-25% annually)

---

## Documentation Reading Guide

### For First-Time Setup (Start Here)

1. **[01-GETTING-STARTED.md](01-GETTING-STARTED.md)** - Installation, configuration, and first run

### For Understanding the System

2. **[02-ARCHITECTURE.md](02-ARCHITECTURE.md)** - How the system is built
3. **[03-TRADING-STRATEGIES.md](03-TRADING-STRATEGIES.md)** - The trading logic

### For Broker & Data Integration

4. **[04-BROKER-INTEGRATION.md](04-BROKER-INTEGRATION.md)** - Connecting to brokers
5. **[05-DATA-SOURCES.md](05-DATA-SOURCES.md)** - Market data and LLM

### For Daily Operations

6. **[06-OPERATIONS.md](06-OPERATIONS.md)** - Running and monitoring

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

### Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | Django 4.2 |
| Database | SQLite |
| Tasks | Celery + Redis + background_task |
| LLM | Ollama (local) |
| Alerts | Telegram Bot |

### Project Structure

```
mCube-ai/
├── apps/               # 12 Django applications
│   ├── core/          # Shared utilities, credentials
│   ├── accounts/      # Broker accounts
│   ├── positions/     # Position tracking
│   ├── orders/        # Order management
│   ├── strategies/    # Trading strategies
│   ├── risk/          # Risk management
│   ├── data/          # Market data, Trendlyne
│   ├── llm/           # LLM integration
│   ├── analytics/     # P&L tracking
│   ├── alerts/        # Telegram bot
│   ├── brokers/       # Broker integrations
│   └── trading/       # Trading workflows
├── templates/         # HTML templates
├── static/            # CSS, JS assets
├── logs/              # Application logs
└── docs/              # This documentation
```

---

## Essential Commands

```bash
# Start Django
python manage.py runserver

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

## Master Design Document

For complete system design with all formulas:
- **[design/mcube-ai.design.md](design/mcube-ai.design.md)**

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

*Last Updated: December 2024*
