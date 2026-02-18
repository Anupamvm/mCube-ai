# mCube-ai: Comprehensive Test Plan & Code Cleanup Plan

**Generated:** February 9, 2026
**Prepared by:** System Architect Analysis
**Codebase Size:** 80,000+ LOC | 13 Django Apps | 100+ Models | 30+ Celery Tasks

---

## Executive Summary

This document provides a meticulous plan for improving the mCube-ai trading system across three critical dimensions:

1. **Testing Strategy** - From <1% to 80%+ coverage
2. **Code Quality & Cleanup** - Eliminate 200+ hours of technical debt
3. **Algorithm Optimization** - Performance improvements without changing core logic

### Current State Assessment

| Dimension | Current | Target | Priority |
|-----------|---------|--------|----------|
| Test Coverage | <1% (15 tests) | 80%+ | CRITICAL |
| Code Duplication | 6+ major patterns | 0 patterns | HIGH |
| Type Hints | ~30% | 95%+ | MEDIUM |
| Documentation | Minimal | Complete | MEDIUM |
| Performance | N+1 queries, no caching | Optimized | HIGH |

---

# PART 1: COMPREHENSIVE TEST PLAN

## 1.1 Testing Infrastructure Setup (Week 1)

### 1.1.1 Create Test Configuration

```bash
# Files to create:
tests/
├── conftest.py              # Pytest configuration & fixtures
├── fixtures/
│   ├── accounts.py          # BrokerAccount fixtures
│   ├── positions.py         # Position fixtures
│   ├── suggestions.py       # TradeSuggestion fixtures
│   ├── contracts.py         # ContractData fixtures
│   └── market_data.py       # MarketData fixtures
├── mocks/
│   ├── breeze_mock.py       # ICICI Breeze API mock
│   ├── neo_mock.py          # Kotak Neo API mock
│   ├── telegram_mock.py     # Telegram Bot API mock
│   └── celery_mock.py       # Celery task mocking
└── factories/
    ├── account_factory.py   # Factory Boy account factories
    ├── position_factory.py  # Position factories
    └── trade_factory.py     # Trade suggestion factories
```

### 1.1.2 Install Test Dependencies

```txt
# Add to requirements.txt
pytest==7.4.3
pytest-django==4.7.0
pytest-celery==0.1.0
pytest-asyncio==0.21.0
pytest-mock==3.12.0
factory-boy==3.3.0
freezegun==1.2.2
responses==0.24.0
coverage==7.3.2
```

### 1.1.3 Configure pytest.ini

```ini
[pytest]
DJANGO_SETTINGS_MODULE = mcube_ai.settings
python_files = tests.py test_*.py *_test.py
addopts = --strict-markers -v --tb=short
markers =
    unit: Unit tests (no external dependencies)
    integration: Integration tests (may use DB)
    broker: Tests requiring broker API mocks
    celery: Celery task tests
    slow: Tests that take >10 seconds
```

### 1.1.4 Create conftest.py

```python
# tests/conftest.py
import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from unittest.mock import MagicMock, patch

@pytest.fixture
def user():
    User = get_user_model()
    return User.objects.create_user(
        username='testuser',
        password='testpass123',
        email='test@example.com'
    )

@pytest.fixture
def authenticated_client(user):
    client = Client()
    client.login(username='testuser', password='testpass123')
    return client

@pytest.fixture
def mock_breeze():
    """Mock ICICI Breeze API client"""
    with patch('apps.brokers.services.breeze_session.get_breeze_client') as mock:
        breeze = MagicMock()
        breeze.get_funds.return_value = {
            'Status': 200,
            'Success': {'cash_limit': 5000000, 'block_by_trade': 1000000}
        }
        mock.return_value = breeze
        yield breeze

@pytest.fixture
def mock_neo():
    """Mock Kotak Neo API client"""
    with patch('tools.neo.get_neo_api') as mock:
        neo = MagicMock()
        neo.get_available_margin.return_value = 4000000
        mock.return_value = neo
        yield neo

@pytest.fixture
def celery_eager(settings):
    """Run Celery tasks synchronously for testing"""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
```

---

## 1.2 Unit Test Plan by Module

### 1.2.1 TIER 1: Critical Path Tests (Week 2-3)

#### A. Broker Integration Tests

**File:** `tests/brokers/test_breeze_session.py`

| Test Case | Description | Priority |
|-----------|-------------|----------|
| `test_breeze_client_authentication_success` | Valid token returns authenticated client | CRITICAL |
| `test_breeze_client_expired_token_triggers_refresh` | Expired token triggers auto-login | CRITICAL |
| `test_breeze_client_invalid_credentials` | Wrong password raises BreezeAuthenticationError | CRITICAL |
| `test_breeze_lock_prevents_concurrent_login` | Cross-process lock works | HIGH |
| `test_breeze_margin_fetch_success` | get_margin() returns correct values | HIGH |
| `test_breeze_margin_fetch_api_error` | API error returns fallback | MEDIUM |
| `test_breeze_session_timeout_retry` | Timeout triggers retry with backoff | HIGH |

**File:** `tests/brokers/test_neo_integration.py`

| Test Case | Description | Priority |
|-----------|-------------|----------|
| `test_neo_login_success` | Valid session returns client | CRITICAL |
| `test_neo_order_placement_success` | Order returns order_id | CRITICAL |
| `test_neo_order_rejection_handling` | Invalid order returns error message | HIGH |
| `test_neo_position_fetch_accuracy` | Positions match expected format | HIGH |
| `test_neo_session_caching` | Multiple calls return same instance | MEDIUM |

#### B. Order Placement Tests

**File:** `tests/trading/test_order_execution.py`

| Test Case | Description | Priority |
|-----------|-------------|----------|
| `test_place_futures_order_single_lot` | 1 lot order places correctly | CRITICAL |
| `test_place_futures_order_batching` | 25 lots splits into 3 batches | CRITICAL |
| `test_place_futures_order_cancellation` | User cancel stops remaining batches | HIGH |
| `test_place_options_order_parallel` | CALL+PUT placed in parallel | HIGH |
| `test_order_idempotency_prevention` | Duplicate order within 60s rejected | CRITICAL |
| `test_order_timeout_handling` | Network timeout returns partial result | HIGH |
| `test_order_margin_validation` | Insufficient margin returns error | CRITICAL |

#### C. Position Management Tests

**File:** `tests/positions/test_position_manager.py`

| Test Case | Description | Priority |
|-----------|-------------|----------|
| `test_one_position_rule_enforced` | Second position blocked if active | CRITICAL |
| `test_position_pnl_calculation_long` | Long P&L = (current - entry) * qty | CRITICAL |
| `test_position_pnl_calculation_short` | Short P&L = (entry - current) * qty | CRITICAL |
| `test_averaging_trigger_at_1pct_loss` | Averaging triggered at -1% | HIGH |
| `test_averaging_max_3_attempts` | 4th averaging blocked | HIGH |
| `test_stop_loss_hit_detection` | SL triggers exit signal | CRITICAL |
| `test_target_hit_detection` | Target triggers exit signal | CRITICAL |
| `test_eod_exit_with_50pct_profit` | EOD exit only if profit >= 50% | HIGH |

#### D. Celery Task Tests

**File:** `tests/tasks/test_strategy_tasks.py`

| Test Case | Description | Priority |
|-----------|-------------|----------|
| `test_task_enabled_guard_blocks_disabled` | Disabled task returns skip result | CRITICAL |
| `test_task_enabled_guard_allows_bypass` | _bypass_guard=True runs task | HIGH |
| `test_execute_futures_algorithm_chord` | Chord completes with all batches | CRITICAL |
| `test_task_timeout_returns_partial` | SoftTimeLimitExceeded returns timed_out=True | HIGH |
| `test_setup_trading_day_idempotency` | Running twice same day is safe | CRITICAL |
| `test_task_retries_on_transient_error` | Network error triggers retry | HIGH |

---

### 1.2.2 TIER 2: Algorithm & Scoring Tests (Week 4)

**File:** `tests/strategies/test_futures_analysis.py`

| Test Case | Description | Priority |
|-----------|-------------|----------|
| `test_vix_adjusted_delta_high_vix` | VIX > 20 adjusts delta correctly | HIGH |
| `test_vix_adjusted_delta_low_vix` | VIX < 15 uses standard delta | HIGH |
| `test_composite_score_calculation` | All 12 components weighted correctly | CRITICAL |
| `test_oi_score_long_buildup` | OI increase + price up = bullish | HIGH |
| `test_sector_score_positive_signals` | Strong sector boosts score | MEDIUM |
| `test_support_resistance_detection` | S/R levels identified correctly | MEDIUM |
| `test_psychological_level_detection` | Round numbers flagged | MEDIUM |
| `test_minimum_score_threshold` | Score < 65 not recommended | HIGH |

**File:** `tests/strategies/test_strangle_algorithm.py`

| Test Case | Description | Priority |
|-----------|-------------|----------|
| `test_strangle_strike_selection` | Delta-neutral strikes selected | HIGH |
| `test_strangle_position_sizing` | Lots based on margin utilization | HIGH |
| `test_breach_risk_calculation` | Breach probability computed | MEDIUM |
| `test_expiry_selection_weekly` | Selects correct weekly expiry | HIGH |

---

### 1.2.3 TIER 3: Service Layer Tests (Week 5)

**File:** `tests/trading/test_trade_confirmation.py`

| Test Case | Description | Priority |
|-----------|-------------|----------|
| `test_telegram_confirmation_message_format` | Message contains all required fields | HIGH |
| `test_confirmation_timeout_handling` | Expired confirmation rejected | HIGH |
| `test_user_modified_lots_applied` | Custom lot count used | MEDIUM |
| `test_execution_progress_callback` | Progress updates sent correctly | MEDIUM |

**File:** `tests/core/test_trading_context.py`

| Test Case | Description | Priority |
|-----------|-------------|----------|
| `test_trading_context_holiday_detection` | Holiday returns trading_allowed=False | HIGH |
| `test_trading_context_weekend_detection` | Weekend returns trading_allowed=False | HIGH |
| `test_get_kotak_account_returns_active` | Returns active Kotak account | MEDIUM |
| `test_get_icici_account_returns_active` | Returns active ICICI account | MEDIUM |

---

### 1.2.4 TIER 4: Integration Tests (Week 6)

**File:** `tests/integration/test_end_to_end_futures.py`

```python
@pytest.mark.integration
class TestFuturesWorkflow:
    """End-to-end futures trading workflow tests"""

    def test_full_futures_trade_lifecycle(self, mock_breeze, mock_telegram):
        """
        1. Algorithm generates suggestion
        2. Telegram confirmation sent
        3. User approves
        4. Order placed in batches
        5. Position tracked
        6. Exit on target
        7. P&L recorded
        """
        pass

    def test_futures_trade_with_averaging(self, mock_breeze):
        """Position averages down twice then exits"""
        pass

    def test_futures_trade_stop_loss_hit(self, mock_breeze):
        """Position exits immediately on SL"""
        pass
```

---

## 1.3 Test Coverage Targets

| Module | Current | Target (Week 8) | Priority |
|--------|---------|-----------------|----------|
| `apps/brokers/services/` | 0% | 85% | CRITICAL |
| `apps/trading/services/` | 0% | 80% | CRITICAL |
| `apps/positions/services/` | 0% | 80% | CRITICAL |
| `apps/strategies/tasks.py` | 0% | 75% | CRITICAL |
| `apps/core/utils/decorators.py` | 0% | 90% | HIGH |
| `apps/trading/models.py` | 40% | 85% | HIGH |
| `apps/analytics/services/` | 0% | 60% | MEDIUM |
| `apps/llm/services/` | 10% | 50% | MEDIUM |
| `apps/alerts/services/` | 0% | 40% | LOW |

---

# PART 2: CODE CLEANUP PLAN

## 2.1 Immediate Actions (Week 1)

### 2.1.1 Extract Duplicate `json_serial` Function

**Current State:** 5 identical copies across codebase (verified Feb 17, 2026)

**Files Affected:**
- `apps/trading/views.py` (lines 499, 971, 2058, 2449) — **4 copies**
- `apps/trading/services/analysis_service.py` (line 29) — **1 copy**

**Action:**
```python
# Create: apps/core/utils/json_helpers.py
from decimal import Decimal
from datetime import datetime, date

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

# Usage:
from apps.core.utils.json_helpers import json_serial
json.dumps(data, default=json_serial)
```

**Effort:** 2 hours

### 2.1.2 Replace Bare `except:` Statements

**Current State:** 38 bare `except:` occurrences across 19 files (verified Feb 17, 2026)

**Top offender files:**
- `apps/data/providers/trendlyne.py` (5 occurrences — worst)
- `apps/core/views.py` (4 occurrences)
- `apps/alerts/services/telegram_bot.py` (3 occurrences)
- `apps/strategies/strategies/icici_futures.py` (3 occurrences)
- `apps/strategies/tasks_strangle.py` (2 occurrences)
- `apps/brokers/integrations/kotak_neo.py` (1 occurrence)

**Action:**
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

**Effort:** 4 hours

### 2.1.3 Standardize JSON Response Format

**Current State:** 3 different patterns (success/status/mixed)

**Action:** Standardize on:
```python
# Success response
return JsonResponse({
    'success': True,
    'data': {...}
}, status=200)

# Error response
return JsonResponse({
    'success': False,
    'error': 'Error message',
    'code': 'ERROR_CODE'
}, status=400)  # Always include status code
```

**Effort:** 6 hours

---

## 2.2 Short-term Refactoring (Weeks 2-4)

### 2.2.1 Split Monster Files

#### A. Telegram Bot — ~~DONE~~ (SUPERSEDED)

**Status:** Already split into 4-file mixin architecture (~7,573 LOC total):
```
apps/alerts/services/
├── telegram_bot.py           # Main handler + callback router (~3,880 LOC)
├── telegram_bot_menus.py     # MenuMixin - menu rendering (~1,312 LOC)
├── telegram_bot_data.py      # DataMixin - @sync_to_async fetchers (~1,486 LOC)
└── telegram_bot_trade.py     # TradeMixin - manual trade wizard (~895 LOC)
```

**Effort:** Already complete — no further work needed

#### B. Core Views (5,740 lines → 4 files)

**Current:** `apps/core/views.py` - 80+ functions

**Target Structure:**
```
apps/core/views/
├── __init__.py              # Imports from submodules
├── dashboard_views.py       # home_page, documentation_dashboard (~300 lines)
├── task_control_views.py    # celery_task_control, toggle functions (~1,500 lines)
├── system_views.py          # system_test, health checks (~800 lines)
└── error_views.py           # error_400 through error_500 (~200 lines)
```

**Effort:** 12 hours

#### C. Trading Views (3,191 lines → service extraction)

**Action:** Extract business logic to services:
```
apps/trading/services/
├── futures_suggestion_service.py  # Extract from trigger_futures_algorithm
├── strangle_suggestion_service.py # Extract from trigger_nifty_strangle
└── verification_service.py        # Extract from verify_future_trade
```

**Effort:** 16 hours

### 2.2.2 Consolidate Duplicate Analyzers

**Current State:**
- `apps/trading/futures_analyzer.py` (3,340 lines)
- `apps/strategies/analyzers/enhanced_futures_analyzer.py` (2,117 lines)
- Significant overlap in functionality

**Action:**
1. Audit both files for unique functionality
2. Create single `apps/strategies/analyzers/futures_analyzer.py`
3. Deprecate duplicates with imports for backwards compatibility

**Effort:** 8 hours

### 2.2.3 Extract Celery Process Management

**Current:** `ensure_celery_running()` in views.py (230 lines)

**Action:**
```python
# Create: apps/core/services/celery_manager.py
class CeleryManager:
    """Manages Celery worker and beat processes"""

    def __init__(self):
        self.python_path = self._find_python_path()

    def ensure_running(self) -> dict:
        """Start/restart Celery processes if needed"""
        pass

    def stop_all(self) -> dict:
        """Stop all Celery processes"""
        pass

    def get_status(self) -> dict:
        """Get current process status"""
        pass

    def _find_python_path(self) -> str:
        """Locate Python executable in venv"""
        pass

    def _check_redis_health(self) -> bool:
        """Verify Redis is accessible"""
        pass
```

**Effort:** 6 hours

---

## 2.3 Medium-term Improvements (Weeks 5-8)

### 2.3.1 Add Comprehensive Type Hints

**Target Files (in priority order):**
1. `apps/trading/services/*.py` - All trading services
2. `apps/positions/services/*.py` - Position management
3. `apps/strategies/tasks.py` - Task functions
4. `apps/core/utils/decorators.py` - Decorators

**Standard Pattern:**
```python
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal

def calculate_position_size(
    available_margin: Decimal,
    margin_per_lot: Decimal,
    max_utilization: float = 0.8
) -> Tuple[int, Decimal]:
    """
    Calculate optimal position size based on margin.

    Args:
        available_margin: Total available F&O margin
        margin_per_lot: Margin required per lot
        max_utilization: Maximum margin utilization percentage

    Returns:
        Tuple of (lots, total_margin_used)
    """
    pass
```

**Effort:** 16 hours

### 2.3.2 Implement Structured Logging

**Current:** Inconsistent log formats, no correlation IDs

**Action:**
```python
# Create: apps/core/utils/logging.py
import structlog
import uuid

def get_task_logger(task_name: str, task_id: str = None):
    """Get structured logger for Celery task"""
    return structlog.get_logger().bind(
        task_name=task_name,
        task_id=task_id or str(uuid.uuid4()),
        component='celery'
    )

# Usage in task:
logger = get_task_logger('execute_futures_algorithm', self.request.id)
logger.info('starting_analysis', contracts=50, batch_size=3)
```

**Effort:** 8 hours

### 2.3.3 Database Query Optimization

**Issue 1: N+1 Queries in Position Views**
```python
# Before:
for pos in Position.objects.filter(status='ACTIVE'):
    account_name = pos.account.account_name  # N queries!

# After:
for pos in Position.objects.filter(status='ACTIVE').select_related('account'):
    account_name = pos.account.account_name  # 1 query
```

**Issue 2: Missing Indexes**
```python
# Add to Position model:
class Meta:
    indexes = [
        models.Index(fields=['account', '-created_at']),
        models.Index(fields=['status', '-entry_time']),
    ]

# Add to TradeSuggestion model:
class Meta:
    indexes = [
        models.Index(fields=['user', 'status', '-created_at']),
        models.Index(fields=['strategy', '-created_at']),
    ]
```

**Effort:** 8 hours

---

## 2.4 Code Quality Metrics to Track

| Metric | Current | Target | Tool |
|--------|---------|--------|------|
| Cyclomatic Complexity | >20 (many functions) | <10 average | radon |
| Lines per Function | >500 (max) | <50 (max) | pylint |
| Duplicate Code | 6%+ | <2% | flake8-duplicate |
| Type Coverage | ~30% | 95%+ | mypy |
| Docstring Coverage | ~40% | 90%+ | interrogate |

---

# PART 3: ALGORITHM OPTIMIZATION RECOMMENDATIONS

*Note: These optimizations preserve the core trading logic while improving efficiency and reliability.*

## 3.1 Futures Screening Algorithm

### 3.1.1 Current Flow Analysis

```
50 contracts → 12-component parallel analysis → Score ranking → TOP 3 to Telegram
```

### 3.1.2 Optimization Opportunities

#### A. Pre-Screening Filter (Reduce Load)

**Current:** Analyze all 50 contracts with full 12-component analysis

**Recommendation:** Two-stage filtering
```python
# Stage 1: Quick filter (10ms per contract)
def quick_filter(contract: ContractData) -> bool:
    """Eliminate obviously unsuitable contracts"""
    # Check minimum volume
    if contract.traded_contracts < 500:
        return False
    # Check price movement (looking for volatility)
    if abs(contract.day_change_pct) < 0.5:
        return False
    # Check OI for liquidity
    if contract.open_interest < 10000:
        return False
    return True

# Stage 2: Full analysis on remaining contracts (typically 20-30)
candidates = [c for c in contracts if quick_filter(c)]
```

**Impact:** 40-50% reduction in analysis time

#### B. Caching Market Data

**Current:** Each analysis fetches fresh market data

**Recommendation:**
```python
# Cache option chain for 5 minutes
from django.core.cache import cache

def get_option_chain_cached(symbol: str, expiry: str) -> dict:
    cache_key = f"option_chain:{symbol}:{expiry}"
    data = cache.get(cache_key)
    if data is None:
        data = breeze.get_option_chain_quotes(symbol, expiry)
        cache.set(cache_key, data, timeout=300)  # 5 min
    return data
```

**Impact:** Reduce API calls by 70% during batch analysis

#### C. Parallel Analysis Optimization

**Current:** `batch_size=3` with chord pattern

**Recommendation:**
```python
# Increase batch size with smarter timeout handling
@shared_task(
    bind=True,
    soft_time_limit=360,  # 6 min soft limit
    time_limit=420,       # 7 min hard limit
    rate_limit='20/m'     # Rate limit to prevent API throttling
)
def analyze_futures_batch(self, contracts, batch_size=5):  # Increase from 3
    pass
```

**Impact:** 40% faster total analysis time

### 3.1.3 Scoring Component Weights

**Current weights (implied from code):**
- Technical Analysis: 25%
- OI Analysis: 20%
- Support/Resistance: 15%
- Sector Strength: 10%
- News Sentiment: 10%
- Psychological Levels: 5%
- Historical Patterns: 15%

**Recommendation:** Make weights configurable via `TradingCoreConfig`:
```python
# Add to TradingCoreConfig model
scoring_weights = models.JSONField(
    default=dict,
    help_text="Algorithm component weights (must sum to 100)"
)
```

---

## 3.2 Options Strangle Algorithm

### 3.2.1 Delta Selection Optimization

**Current:** Fixed delta targets with VIX adjustment

**Recommendation:** Dynamic delta based on market regime:
```python
def get_optimal_delta(vix: float, days_to_expiry: int) -> float:
    """
    Calculate optimal delta based on market conditions.

    - High VIX (>20): Use wider deltas (0.15-0.20) for safety
    - Low VIX (<15): Can use tighter deltas (0.20-0.25) for premium
    - Near expiry (<3 days): Tighten deltas for theta decay
    """
    base_delta = 0.20

    # VIX adjustment
    if vix > 25:
        base_delta = 0.12
    elif vix > 20:
        base_delta = 0.15
    elif vix < 12:
        base_delta = 0.25

    # Expiry adjustment
    if days_to_expiry <= 2:
        base_delta *= 1.2  # Tighter near expiry

    return min(max(base_delta, 0.10), 0.30)  # Clamp to 0.10-0.30
```

### 3.2.2 Breach Risk Enhancement

**Current:** Simple distance-based breach probability

**Recommendation:** Incorporate historical volatility:
```python
def calculate_breach_risk(
    spot_price: float,
    strike: float,
    days_to_expiry: int,
    historical_volatility: float  # Add this parameter
) -> float:
    """
    Calculate probability of breach using historical volatility.

    Uses simplified Black-Scholes-like estimation.
    """
    import math
    from scipy import stats

    # Annualize volatility
    daily_vol = historical_volatility / math.sqrt(252)
    period_vol = daily_vol * math.sqrt(days_to_expiry)

    # Calculate z-score for breach
    distance = abs(spot_price - strike) / spot_price
    z_score = distance / period_vol

    # Probability of breach
    breach_prob = 1 - stats.norm.cdf(z_score)

    return round(breach_prob * 100, 2)
```

---

## 3.3 Position Management Optimization

### 3.3.1 Averaging Decision Enhancement

**Current:** Fixed 1% loss trigger, fixed lot sizes

**Recommendation:** Adaptive averaging based on conviction:
```python
def should_average(
    position: Position,
    current_price: Decimal,
    algorithm_score: float  # Original suggestion score
) -> dict:
    """
    Adaptive averaging decision based on original conviction.

    High-conviction trades (score > 80): Average more aggressively
    Medium-conviction (65-80): Standard averaging
    Low-conviction (< 65): Smaller averaging or skip
    """
    loss_pct = calculate_loss_percentage(position, current_price)

    # Adjust trigger based on conviction
    if algorithm_score > 80:
        loss_trigger = Decimal('-0.8')   # 0.8% for high conviction
        lot_multiplier = 1.5             # Larger averaging
    elif algorithm_score > 70:
        loss_trigger = Decimal('-1.0')   # 1.0% standard
        lot_multiplier = 1.0
    else:
        loss_trigger = Decimal('-1.2')   # 1.2% for low conviction
        lot_multiplier = 0.5             # Smaller averaging

    return {
        'should_average': loss_pct <= loss_trigger,
        'lot_multiplier': lot_multiplier,
        'conviction_level': algorithm_score
    }
```

### 3.3.2 Exit Strategy Enhancement

**Current:** Fixed SL/target percentages

**Recommendation:** Trailing stop-loss for winners:
```python
def calculate_dynamic_stop_loss(
    position: Position,
    current_price: Decimal,
    highest_price: Decimal  # Track highest since entry
) -> Decimal:
    """
    Implement trailing stop-loss for profitable positions.

    - If unrealized P&L > 2%: Trail at 1% from high
    - If unrealized P&L > 5%: Trail at 1.5% from high
    - If unrealized P&L > 10%: Trail at 2% from high
    """
    profit_pct = calculate_profit_percentage(position, current_price)

    if profit_pct >= Decimal('10'):
        trail_pct = Decimal('0.02')
    elif profit_pct >= Decimal('5'):
        trail_pct = Decimal('0.015')
    elif profit_pct >= Decimal('2'):
        trail_pct = Decimal('0.01')
    else:
        return position.stop_loss  # Keep original

    if position.direction == 'LONG':
        trailing_sl = highest_price * (1 - trail_pct)
        return max(position.stop_loss, trailing_sl)
    else:
        trailing_sl = highest_price * (1 + trail_pct)  # Inverted for short
        return min(position.stop_loss, trailing_sl)
```

---

## 3.4 Performance Monitoring Recommendations

### 3.4.1 Algorithm Performance Tracking

**Add to `FuturesSuggestion` model:**
```python
# Track algorithm accuracy
class AlgorithmPerformance(models.Model):
    """Track algorithm prediction accuracy"""
    date = models.DateField(unique=True)
    suggestions_count = models.IntegerField(default=0)
    taken_count = models.IntegerField(default=0)
    profitable_count = models.IntegerField(default=0)
    average_score = models.DecimalField(max_digits=5, decimal_places=2)
    score_vs_outcome_correlation = models.DecimalField(max_digits=5, decimal_places=4)

    @property
    def hit_rate(self) -> float:
        if self.taken_count == 0:
            return 0.0
        return self.profitable_count / self.taken_count * 100
```

### 3.4.2 Component Contribution Analysis

**Track which scoring components predict success:**
```python
def analyze_component_effectiveness():
    """
    Analyze which algorithm components correlate with profitable trades.
    Run weekly to identify component weights that need adjustment.
    """
    from apps.analytics.models import TradePerformance
    from scipy.stats import pearsonr

    profitable = TradePerformance.objects.filter(is_profitable=True)
    unprofitable = TradePerformance.objects.filter(is_profitable=False)

    components = ['oi_score', 'sector_score', 'technical_score',
                  'sr_score', 'news_score', 'psych_score']

    results = {}
    for component in components:
        # Calculate correlation with profitability
        all_scores = list(profitable.values_list(component, flat=True)) + \
                    list(unprofitable.values_list(component, flat=True))
        outcomes = [1] * profitable.count() + [0] * unprofitable.count()

        correlation, p_value = pearsonr(all_scores, outcomes)
        results[component] = {
            'correlation': correlation,
            'p_value': p_value,
            'recommendation': 'increase' if correlation > 0.3 else
                            'decrease' if correlation < 0 else 'maintain'
        }

    return results
```

---

# PART 4: IMPLEMENTATION TIMELINE

## Phase 1: Foundation (Weeks 1-2)

| Task | Owner | Effort | Dependencies |
|------|-------|--------|--------------|
| Setup test infrastructure | Dev | 8h | None |
| Create conftest.py and fixtures | Dev | 8h | Test infrastructure |
| Extract json_serial to utility | Dev | 2h | None |
| Fix bare except statements | Dev | 4h | None |
| Standardize JSON responses | Dev | 6h | None |
| Add missing @login_required | Dev | 2h | None |

## Phase 2: Critical Tests (Weeks 3-4)

| Task | Owner | Effort | Dependencies |
|------|-------|--------|--------------|
| Broker integration tests | Dev | 16h | Fixtures |
| Order placement tests | Dev | 12h | Mock brokers |
| Position management tests | Dev | 12h | Fixtures |
| Celery task tests | Dev | 12h | celery_eager fixture |

## Phase 3: Refactoring (Weeks 5-6)

| Task | Owner | Effort | Dependencies |
|------|-------|--------|--------------|
| Split telegram_bot.py | Dev | 8h | Tests for bot |
| Split core/views.py | Dev | 12h | Tests for views |
| Extract trading services | Dev | 16h | Tests for trading |
| Consolidate analyzers | Dev | 8h | Tests for analyzers |

## Phase 4: Optimization (Weeks 7-8)

| Task | Owner | Effort | Dependencies |
|------|-------|--------|--------------|
| Add type hints | Dev | 16h | Refactoring complete |
| Implement structured logging | Dev | 8h | None |
| Database query optimization | Dev | 8h | None |
| Add missing indexes | Dev | 4h | None |
| Algorithm optimizations | Dev | 16h | Tests in place |

---

# PART 5: SUCCESS METRICS

## Code Quality

| Metric | Before | After (Target) |
|--------|--------|----------------|
| Test Coverage | <1% | 80%+ |
| Pylint Score | ~6/10 | 9/10 |
| Type Coverage | 30% | 95% |
| Cyclomatic Complexity (avg) | 15+ | <10 |
| Duplicate Code | 6%+ | <2% |

## Performance

| Metric | Before | After (Target) |
|--------|--------|----------------|
| Futures Analysis Time | 5-8 min | 3-4 min |
| DB Queries per Request (avg) | 50+ | <10 |
| API Response Time (avg) | 500ms | <200ms |
| Celery Task Success Rate | ~95% | 99%+ |

## Reliability

| Metric | Before | After (Target) |
|--------|--------|----------------|
| Broker API Failures/Day | 5-10 | <2 |
| Duplicate Order Risk | HIGH | NONE |
| Task Timeout Rate | 10%+ | <1% |
| Unhandled Exceptions/Day | 20+ | <5 |

---

# Appendix A: File-by-File Action Items

| File | Lines | Priority | Actions |
|------|-------|----------|---------|
| `apps/alerts/services/telegram_bot.py` | 3,880 | ~~DONE~~ | ~~Split into 3 files~~ Already split into 4-file mixin pattern |
| `apps/core/views.py` | 6,025 | CRITICAL | Split into 4 files |
| `apps/trading/views.py` | 3,191 | CRITICAL | Extract 3 services |
| `apps/trading/futures_analyzer.py` | 3,340 | HIGH | Consolidate with enhanced_futures_analyzer |
| `apps/strategies/analyzers/enhanced_futures_analyzer.py` | 2,118 | HIGH | Merge with futures_analyzer |
| `apps/trading/services/analysis_service.py` | - | HIGH | Remove duplicate json_serial |
| `apps/brokers/services/breeze_auto_login.py` | 1,003 | MEDIUM | Add retry logic |
| `apps/brokers/integrations/breeze.py` | 1,962 | MEDIUM | Add rate limiting |
| `apps/brokers/integrations/kotak_neo.py` | 2,822 | MEDIUM | Add rate limiting |
| `apps/core/utils/decorators.py` | - | MEDIUM | Add type hints |

---

# Appendix B: Test File Locations

```
tests/
├── conftest.py
├── fixtures/
│   ├── accounts.py
│   ├── positions.py
│   ├── suggestions.py
│   └── market_data.py
├── mocks/
│   ├── breeze_mock.py
│   ├── neo_mock.py
│   └── telegram_mock.py
├── unit/
│   ├── brokers/
│   │   ├── test_breeze_session.py
│   │   └── test_neo_integration.py
│   ├── trading/
│   │   ├── test_order_execution.py
│   │   ├── test_trade_confirmation.py
│   │   └── test_position_sizing.py
│   ├── positions/
│   │   ├── test_position_manager.py
│   │   ├── test_averaging_manager.py
│   │   └── test_exit_manager.py
│   ├── strategies/
│   │   ├── test_futures_analysis.py
│   │   └── test_strangle_algorithm.py
│   └── tasks/
│       ├── test_strategy_tasks.py
│       └── test_data_tasks.py
├── integration/
│   ├── test_end_to_end_futures.py
│   └── test_end_to_end_options.py
└── performance/
    └── test_algorithm_speed.py
```

---

---

# Appendix C: Broker Integration Gaps (Critical)

**Analysis Date:** February 9, 2026

## High-Priority Broker Fixes

| Gap | Severity | Files Affected | Effort |
|-----|----------|----------------|--------|
| No retry logic with exponential backoff | CRITICAL | `breeze.py`, `neo/orders.py` | 4h |
| No circuit breaker pattern | CRITICAL | All broker services | 4h |
| No global rate limiting | HIGH | `breeze.py`, `neo/` | 3h |
| No order idempotency keys | HIGH | `breeze.py:1240`, `neo/orders.py:64` | 4h |
| Inconsistent timeout handling | HIGH | Multiple files | 2h |
| Neo orders not tracked in DB | MEDIUM | `neo/orders.py`, `batch_orders.py` | 4h |
| No option chain caching | MEDIUM | `breeze.py:917` | 2h |

## Recommended Broker Improvements

### 1. Implement Exponential Backoff
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30)
)
def place_order_with_retry(order_params):
    return breeze.place_order(**order_params)
```

### 2. Add Circuit Breaker
```python
from pybreaker import CircuitBreaker

breeze_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=300  # 5 minutes
)

@breeze_breaker
def safe_breeze_call():
    return breeze.get_funds()
```

### 3. Standardize Timeouts
```python
# Create: apps/core/constants.py
BREEZE_TIMEOUT = (10, 30)  # Connect 10s, read 30s
NEO_TIMEOUT = (10, 30)
DEFAULT_TIMEOUT = (10, 30)
```

### 4. Add Rate Limiting
```python
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=10, period=60)
def get_breeze_quotes(): ...
```

## Broker Robustness Scores

| Dimension | Current | Target |
|-----------|---------|--------|
| Session Management | 8/10 | 9/10 |
| Error Handling | 6/10 | 9/10 |
| Rate Limiting | 2/10 | 8/10 |
| Retry Logic | 3/10 | 9/10 |
| Circuit Breaking | 0/10 | 8/10 |
| Order Tracking | 7/10 | 9/10 |

---

**Document Version:** 1.1
**Last Updated:** February 9, 2026
**Estimated Total Effort:** 220+ hours
**Recommended Timeline:** 8 weeks with 1 developer
