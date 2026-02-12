# Next Session Quick Start Guide

**Last Updated:** February 9, 2026
**Full Plan:** See `IMPROVEMENT_PLAN.md` (1047 lines, 8-week roadmap)

---

## Quick Status

| Area | Status | Next Action |
|------|--------|-------------|
| Test Coverage | <1% | Create test infrastructure |
| Code Duplication | 6+ patterns | Extract `json_serial` first |
| Security | OK | `api_positions` already has decorators |
| Monster Files | 3 files >3K lines | Plan to split, not started |

---

## Week 1 Priority Tasks (Immediate)

### Task 1: Extract `json_serial` to Utility (2h)
**Problem:** 3+ identical copies in `apps/trading/views.py` (lines 499, 971, 2058)

**Action:**
```bash
# 1. Create the utility file
touch apps/core/utils/json_helpers.py
```

**Code to add:**
```python
# apps/core/utils/json_helpers.py
from decimal import Decimal
from datetime import datetime, date

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")
```

**Then update imports in:**
- `apps/trading/views.py` (3 locations)
- `apps/trading/services/suggestion_service.py`
- `apps/trading/services/analysis_service.py`

---

### Task 2: Fix Bare `except:` Statements (4h)

**Files to fix (priority order):**
1. `apps/brokers/integrations/kotak_neo.py` - broker API calls
2. `apps/strategies/tasks_strangle.py` - trading logic
3. `apps/data/providers/trendlyne.py` - data fetching

**Pattern:**
```python
# Before:
try:
    result = api_call()
except:
    pass

# After:
try:
    result = api_call()
except Exception as e:
    logger.warning(f"API call failed: {e}", exc_info=True)
    result = default_value
```

**To find all occurrences:**
```bash
grep -rn "except:" --include="*.py" apps/ | grep -v "except:$" | head -20
```

---

### Task 3: Create Test Infrastructure (8h)

**Files to create:**
```
tests/
├── conftest.py           # Fixtures (see IMPROVEMENT_PLAN.md section 1.1.4)
├── fixtures/
│   └── __init__.py
├── mocks/
│   └── __init__.py
└── unit/
    └── __init__.py
```

**Add to requirements.txt:**
```txt
pytest-asyncio==0.21.0
pytest-mock==3.12.0
factory-boy==3.3.0
freezegun==1.2.2
responses==0.24.0
coverage==7.3.2
```

---

## Key Files Reference

| File | Lines | Purpose |
|------|-------|---------|
| `IMPROVEMENT_PLAN.md` | 1047 | Full 8-week plan |
| `apps/trading/views.py` | 3191 | Has 533-line function to extract |
| `apps/alerts/services/telegram_bot.py` | 3181 | Needs split into 3 files |
| `apps/core/views.py` | 5740 | Needs split into 4 modules |
| `apps/core/task_config.py` | - | Task display names & categories |

---

## What NOT to Do

1. **Don't change algorithm logic** - optimization only, no new trading rules
2. **Don't add @login_required to api_positions** - already has it (lines 673-674)
3. **Don't start beat without DBReloadScheduler** - see MEMORY.md
4. **Don't run tests yet** - infrastructure needs setup first

---

## Commands Reference

```bash
# Run tests (after setup)
pytest tests/ -v

# Find duplicate code
grep -rn "def json_serial" --include="*.py" apps/

# Find bare except
grep -rn "except:" --include="*.py" apps/ | wc -l

# Check celery status
ps aux | grep celery
```

---

---

## Broker Integration Gaps (Added Feb 9)

Critical gaps identified in broker services:
- **No retry logic** - transient failures crash immediately
- **No circuit breaker** - keeps hammering API when down
- **No rate limiting** - can trigger 429 throttling
- **Inconsistent timeouts** - some calls can hang forever

See `IMPROVEMENT_PLAN.md` Appendix C for details.

**Dependencies to add:**
```txt
tenacity>=8.0.0  # Retry with backoff
pybreaker>=1.0.0  # Circuit breaker
ratelimit>=2.2.1  # Rate limiting
```

---

## Session Continuation Prompt

If starting fresh, use this prompt:
> "Continue implementing the IMPROVEMENT_PLAN.md. Start with Week 1 Task 1: Extract json_serial to apps/core/utils/json_helpers.py. Read the plan first."

