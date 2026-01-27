# App Documentation Index

This directory contains detailed documentation for each Django app in the mCube trading system.

---

## Quick Navigation

| App | Purpose | Key Files |
|-----|---------|-----------|
| [Core](core.md) | Foundation utilities, credentials, scheduling | `models.py`, `utils/` |
| [Accounts](accounts.md) | Broker account management, margin tracking | `models.py`, `margin_manager.py` |
| [Positions](positions.md) | Position lifecycle, exit management | `models.py`, `exit_manager.py` |
| [Strategies](strategies.md) | Trading algorithms (3 strategies) | `kotak_strangle.py`, `icici_futures.py` |
| [Brokers](brokers.md) | Kotak Neo & ICICI Breeze integration | `kotak_neo.py`, `icici_breeze.py` |
| [Trading](trading.md) | Trade suggestions, approval workflow | `models.py`, `futures_analyzer.py` |
| [Data](data.md) | Market data, 6 analyzers, signals | `models.py`, `data_analyzers.py` |
| [Alerts](alerts.md) | Telegram bot (14 commands), notifications | `telegram_bot.py` |
| [Risk](risk.md) | Circuit breakers, loss limits | `risk_manager.py` |
| [Analytics](analytics.md) | P&L tracking, learning engine | `learning_engine.py` |
| [LLM](llm.md) | AI validation, RAG system | `trade_validator.py`, `rag_system.py` |

---

## Reading Order for New Developers

### Day 1: Understand the Foundation
1. **[Core](core.md)** - Credentials, scheduling, utilities
2. **[Accounts](accounts.md)** - Account structure and margin

### Day 2: Understand Positions
3. **[Positions](positions.md)** - Position lifecycle (CRITICAL)
4. **[Brokers](brokers.md)** - How orders are placed

### Day 3: Understand Data
5. **[Data](data.md)** - Where data comes from
6. **[LLM](llm.md)** - AI validation

### Day 4: Understand Strategies
7. **[Strategies](strategies.md)** - The three trading algorithms
8. **[Trading](trading.md)** - Trade workflow

### Day 5: Understand Safety
9. **[Risk](risk.md)** - Circuit breakers
10. **[Alerts](alerts.md)** - Telegram notifications
11. **[Analytics](analytics.md)** - Performance tracking

---

## Common Patterns Across Apps

### Model Patterns

```python
# All models have these common fields
class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
```

### Service Patterns

```python
# Services are organized in services/ directory
# Each service is a class or collection of functions

# Class-based service
class SomeManager:
    def __init__(self, account):
        self.account = account

    def do_something(self):
        pass

# Function-based service
def some_action(account, param):
    pass
```

### Task Patterns

```python
# Celery tasks in tasks.py
@shared_task
def scheduled_task():
    """Runs on schedule (see celery.py)"""
    pass

@shared_task
def triggered_task(param):
    """Runs when triggered"""
    pass
```

---

## File Size Reference

Large files that need focused study:

| File | Lines | Notes |
|------|-------|-------|
| `strategies/services/kotak_strangle.py` | 800+ | Main strangle algorithm |
| `strategies/services/icici_futures.py` | 600+ | Futures algorithm |
| `data/services/trendlyne_fetcher.py` | 800+ | Data fetching |
| `data/data_analyzers.py` | 620+ | 6 analyzer classes |
| `alerts/services/telegram_bot.py` | 1000+ | 14 bot commands |
| `positions/models.py` | 480+ | Position model |
| `data/models.py` | 730+ | 10 data models |

---

## Tips for Studying

1. **Start with models.py** in each app - understand the data structures
2. **Read services/** - understand the business logic
3. **Check tasks.py** - understand scheduled operations
4. **Review admin.py** - see what's exposed in admin interface
5. **Test in Django shell** - query models to see real data

```bash
# Enter Django shell
python manage.py shell

# Example queries
from apps.positions.models import Position
Position.objects.filter(status='ACTIVE').count()
```

---

## Back to Main Documentation

- [Main README](../README.md) - System overview
- [Algorithms Guide](../ALGORITHMS.md) - Deep dive into trading algorithms

---

*Each app documentation includes code examples and "How to Study" sections.*
