# mCube-ai Trading Algorithms Code Cleanup Plan

> **Status**: Ready for execution
> **Created**: 2026-01-31
> **Purpose**: Eliminate ~4,500 lines of duplicated code and make trading algorithms readable

---

## Quick Start for Claude

When asked to execute this plan, follow these steps:

1. Read this document completely
2. Execute phases in order (Phase 1 → 2 → 3 → 4 → 5 → 6)
3. Test after each phase before proceeding
4. Keep backward compatibility with wrapper functions

---

## Executive Summary

This plan eliminates **~4,500 lines of duplicated code** across four trading algorithms and transforms them into a clean, readable architecture. After refactoring:

- Each algorithm file will contain **only its unique logic** (~150-250 lines vs 700-1100+ currently)
- Common workflow is abstracted into a base class
- Shared utilities are extracted into reusable modules

---

## Current State

### Files to Refactor

| File | Location | Current Lines |
|------|----------|---------------|
| `kotak_strangle.py` | `apps/strategies/strategies/` | 715 |
| `kotak_broken_iron_condor.py` | `apps/strategies/strategies/` | 1,134 |
| `icici_futures.py` | `apps/strategies/strategies/` | 904 |
| `strangle_delta_algorithm.py` | `apps/strategies/services/` | 417 |

### Identified Duplications

| Duplication | Location in Files | Lines | Match % |
|-------------|-------------------|-------|---------|
| `run_entry_filters()` | strangle:133-215, iron_condor:251-327 | ~160 | 100% |
| `calculate_strikes()` | strangle:45-130, iron_condor:39-108 | ~140 | 95% |
| `get_current_nifty_price()` | strangle:645-671, iron_condor:1007-1031 | ~54 | 100% |
| `get_option_premiums()` | strangle:674-714, iron_condor:1061-1099 | ~80 | 100% |
| Entry workflow (9 steps) | All 3 main files | ~1,800 | 80% |
| Logging patterns (`"=" * 100`, `"-" * 80`) | All files | ~400 | 95% |
| Return dict structures | All files | ~300 | 100% |
| Error handling patterns | All files | ~500 | 95% |

---

## Target Architecture

### New Directory Structure

```
apps/strategies/
├── core/                              # NEW: Base infrastructure
│   ├── __init__.py
│   ├── base_strategy.py               # Abstract base class (~150 lines)
│   ├── entry_workflow.py              # Shared 9-step workflow (~300 lines)
│   └── result_types.py                # EntryResult, StrategyConfig (~50 lines)
│
├── shared/                            # NEW: Shared utilities
│   ├── __init__.py
│   ├── market_data.py                 # get_nifty_price, get_vix, get_premiums (~100 lines)
│   ├── strike_calculator.py           # calculate_strangle_strikes (~80 lines)
│   ├── entry_filters.py               # run_entry_filters consolidated (~100 lines)
│   └── logging_utils.py               # StrategyLogger class (~60 lines)
│
├── strategies/                        # REFACTORED: Strategy-specific only
│   ├── kotak_strangle.py              # ~150 lines (was 715)
│   ├── kotak_broken_iron_condor.py    # ~200 lines (was 1,134)
│   └── icici_futures.py               # ~250 lines (was 904)
│
└── services/
    └── strangle_delta_algorithm.py    # ~300 lines (was 417)
```

---

## Phase 1: Create Core Infrastructure

### 1.1 Create Directory
```bash
mkdir -p apps/strategies/core
touch apps/strategies/core/__init__.py
```

### 1.2 Create `apps/strategies/core/result_types.py`

```python
"""
Result types and configuration dataclasses for trading strategies.
"""

from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal
from typing import Dict, Any, Optional


@dataclass
class StrategyConfig:
    """Configuration for a trading strategy"""
    name: str
    strategy_type: str  # 'OPTIONS' or 'FUTURES'
    direction: str      # 'NEUTRAL', 'LONG', 'SHORT'

    # Entry timing
    entry_start_time: time
    entry_end_time: time

    # Expiry rules
    min_days_to_expiry: int

    # Margin rules
    margin_usage_pct: Decimal  # e.g., 0.50 for 50%

    # Strategy-specific settings
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntryResult:
    """Standardized result from entry evaluation"""
    success: bool
    message: str
    suggestion: Optional[Any] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'success': self.success,
            'message': self.message,
            'suggestion': self.suggestion,
            'details': self.details or {}
        }
```

### 1.3 Create `apps/strategies/core/base_strategy.py`

```python
"""
Abstract base class for all trading strategies.
Provides common workflow with hooks for strategy-specific customization.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Optional
import logging

from apps.accounts.models import BrokerAccount
from apps.strategies.core.result_types import StrategyConfig, EntryResult


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Usage:
        class KotakStrangle(BaseStrategy):
            def get_config(self) -> StrategyConfig:
                return StrategyConfig(...)

            def calculate_entry_parameters(self, market_data):
                # Strategy-specific calculation
    """

    def __init__(self, account: BrokerAccount):
        self.account = account
        self.config = self.get_config()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # =========================================================================
    # ABSTRACT METHODS - Must be implemented by each strategy
    # =========================================================================

    @abstractmethod
    def get_config(self) -> StrategyConfig:
        """Return strategy configuration"""
        pass

    @abstractmethod
    def calculate_entry_parameters(self, market_data: Dict) -> Dict:
        """
        Calculate strategy-specific entry parameters.

        For Options: Returns strikes, premiums
        For Futures: Returns entry price, direction, symbol
        """
        pass

    @abstractmethod
    def build_position_details(self, entry_params: Dict, sizing: Dict) -> Dict:
        """Build the position details dict for trade suggestion"""
        pass

    @abstractmethod
    def build_algorithm_reasoning(self,
                                  entry_params: Dict,
                                  filters_result: Dict,
                                  sizing: Dict) -> Dict:
        """Build the algorithm reasoning dict for trade suggestion"""
        pass

    # =========================================================================
    # OPTIONAL OVERRIDES - Strategies can customize these
    # =========================================================================

    def get_entry_filters(self) -> List[callable]:
        """Return list of entry filter functions. Override to customize."""
        from apps.strategies.shared.entry_filters import get_default_filters
        return get_default_filters()

    def validate_premiums(self, entry_params: Dict) -> Tuple[bool, str]:
        """Validate premiums are acceptable. Override for custom validation."""
        return True, "Premiums acceptable"

    def get_expiry_selector(self):
        """Return the appropriate expiry selector."""
        if self.config.strategy_type == 'OPTIONS':
            from apps.core.services.expiry_selector import select_expiry_for_options
            return select_expiry_for_options
        else:
            from apps.core.services.expiry_selector import select_expiry_for_futures
            return select_expiry_for_futures

    # =========================================================================
    # CONCRETE METHODS - Shared workflow
    # =========================================================================

    def execute_entry(self) -> EntryResult:
        """
        Execute the complete entry workflow.

        9-step workflow:
        1. Morning position check
        2. Entry timing validation
        3. Run entry filters
        4. Expiry selection
        5. Calculate entry parameters (strategy-specific)
        6. Validate premiums/prices
        7. Position sizing
        8. Risk limit checks
        9. Create trade suggestion
        """
        from apps.strategies.core.entry_workflow import EntryWorkflow
        return EntryWorkflow(self).execute()

    def log_header(self, title: str):
        """Log a section header"""
        self.logger.info("=" * 100)
        self.logger.info(title)
        self.logger.info("=" * 100)

    def log_step(self, step_num: int, title: str):
        """Log a workflow step"""
        self.logger.info(f"STEP {step_num}: {title}")
        self.logger.info("-" * 80)
```

### 1.4 Create `apps/strategies/core/entry_workflow.py`

```python
"""
Entry workflow engine - executes the standard 9-step entry workflow.
This class encapsulates common workflow logic shared across all strategies.
"""

from decimal import Decimal
from datetime import date
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.positions.services.position_manager import morning_check
from apps.accounts.services.margin_manager import calculate_usable_margin
from apps.risk.services.risk_manager import check_risk_limits
from apps.trading.services import TradeSuggestionService
from apps.strategies.core.result_types import EntryResult

if TYPE_CHECKING:
    from apps.strategies.core.base_strategy import BaseStrategy


class EntryWorkflow:
    """Executes the standard 9-step entry workflow."""

    def __init__(self, strategy: 'BaseStrategy'):
        self.strategy = strategy
        self.account = strategy.account
        self.config = strategy.config
        self.logger = strategy.logger

    def execute(self) -> EntryResult:
        """Execute the complete entry workflow"""

        self._log_header()

        # Step 1: Morning Position Check
        result = self._step_1_morning_check()
        if not result['allow_new_entry']:
            return EntryResult(False, result['message'], details=result)

        # Step 2: Entry Timing Validation
        timing_ok, timing_msg = self._step_2_timing_validation()
        if not timing_ok:
            return EntryResult(False, timing_msg)

        # Step 3: Run Entry Filters
        filters_passed, filter_details = self._step_3_entry_filters()
        if not filters_passed:
            return EntryResult(False, "Entry filters failed", details=filter_details)

        # Step 4: Expiry Selection
        expiry_result = self._step_4_expiry_selection()
        if not expiry_result['success']:
            return EntryResult(False, expiry_result['message'])

        # Step 5: Calculate Entry Parameters (STRATEGY-SPECIFIC)
        market_data = self._gather_market_data()
        market_data['expiry'] = expiry_result['expiry']
        market_data['days_to_expiry'] = expiry_result['days_to_expiry']

        try:
            entry_params = self.strategy.calculate_entry_parameters(market_data)
        except Exception as e:
            return EntryResult(False, f"Entry parameter calculation failed: {str(e)}")

        # Step 6: Validate Premiums/Prices
        valid, validation_msg = self.strategy.validate_premiums(entry_params)
        if not valid:
            return EntryResult(False, validation_msg)

        # Step 7: Position Sizing
        sizing = self._step_7_position_sizing(entry_params)
        if not sizing['success']:
            return EntryResult(False, sizing['message'])

        # Step 8: Risk Limit Checks
        risk_ok, risk_details = self._step_8_risk_checks()
        if not risk_ok:
            return EntryResult(False, "Risk limits breached", details=risk_details)

        # Step 9: Create Trade Suggestion
        return self._step_9_create_suggestion(entry_params, filter_details, sizing)

    def _log_header(self):
        self.strategy.log_header(f"{self.config.name.upper()} - ENTRY EVALUATION")
        self.logger.info(f"Account: {self.account.broker} - {self.account.account_name}")
        self.logger.info(f"Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("")

    def _step_1_morning_check(self) -> dict:
        self.strategy.log_step(1, "Morning Position Check (ONE POSITION RULE)")
        result = morning_check(self.account)

        if result['allow_new_entry']:
            self.logger.info(f"✅ {result['message']}")
        else:
            self.logger.warning(f"❌ {result['message']}")

        self.logger.info("")
        return result

    def _step_2_timing_validation(self) -> tuple:
        self.strategy.log_step(2, "Entry Timing Validation")

        current_time = timezone.now().time()
        start = self.config.entry_start_time
        end = self.config.entry_end_time

        if start <= current_time <= end:
            self.logger.info(f"✅ Entry timing valid ({current_time.strftime('%H:%M')})")
            self.logger.info("")
            return True, ""
        else:
            msg = f"Entry window closed (allowed: {start.strftime('%H:%M')}-{end.strftime('%H:%M')}, current: {current_time.strftime('%H:%M')})"
            self.logger.warning(f"❌ {msg}")
            return False, msg

    def _step_3_entry_filters(self) -> tuple:
        self.strategy.log_step(3, "Entry Filters Execution")

        from apps.strategies.shared.entry_filters import run_filters

        filters = self.strategy.get_entry_filters()
        return run_filters(filters, self.logger)

    def _step_4_expiry_selection(self) -> dict:
        self.strategy.log_step(4, f"Expiry Selection ({self.config.min_days_to_expiry}-day minimum rule)")

        try:
            expiry_selector = self.strategy.get_expiry_selector()

            if self.config.strategy_type == 'OPTIONS':
                selected_expiry, expiry_details = expiry_selector(
                    instrument='NIFTY',
                    min_days=self.config.min_days_to_expiry
                )
            else:
                selected_expiry, expiry_details = expiry_selector(
                    symbol=getattr(self.strategy, 'symbol', 'NIFTY'),
                    min_days=self.config.min_days_to_expiry
                )

            days_to_expiry = (selected_expiry - date.today()).days

            self.logger.info(f"✅ Selected Expiry: {selected_expiry} ({days_to_expiry} days)")
            self.logger.info(f"   Details: {expiry_details}")
            self.logger.info("")

            return {
                'success': True,
                'expiry': selected_expiry,
                'days_to_expiry': days_to_expiry,
                'details': expiry_details
            }
        except Exception as e:
            self.logger.error(f"❌ Expiry selection failed: {str(e)}", exc_info=True)
            return {'success': False, 'message': f"Expiry selection failed: {str(e)}"}

    def _gather_market_data(self) -> dict:
        """Gather current market data for strategy calculations"""
        from apps.strategies.shared.market_data import get_nifty_price, get_vix

        return {
            'spot_price': get_nifty_price(),
            'vix': get_vix(),
        }

    def _step_7_position_sizing(self, entry_params: dict) -> dict:
        self.strategy.log_step(7, "Position Sizing (50% margin usage rule)")

        try:
            usable_margin = calculate_usable_margin(self.account)

            # Nifty lot size = 50 for options
            lot_size = 50 if self.config.strategy_type == 'OPTIONS' else 1
            margin_per_lot = Decimal('80000')  # TODO: Fetch from broker

            max_lots = int(usable_margin / margin_per_lot)

            if max_lots < 1:
                msg = f"Insufficient margin (usable: ₹{usable_margin:,.0f}, required: ₹{margin_per_lot:,.0f})"
                self.logger.warning(f"❌ {msg}")
                return {'success': False, 'message': msg}

            lots = 1  # Conservative approach
            quantity = lots * lot_size
            margin_used = margin_per_lot * lots

            self.logger.info(f"Usable Margin (50%): ₹{usable_margin:,.0f}")
            self.logger.info(f"Lots: {lots}, Quantity: {quantity}")
            self.logger.info(f"Margin Used: ₹{margin_used:,.0f}")
            self.logger.info(f"✅ Position sizing complete")
            self.logger.info("")

            return {
                'success': True,
                'usable_margin': usable_margin,
                'lot_size': lot_size,
                'lots': lots,
                'quantity': quantity,
                'margin_used': margin_used
            }
        except Exception as e:
            self.logger.error(f"❌ Position sizing failed: {str(e)}", exc_info=True)
            return {'success': False, 'message': f"Position sizing failed: {str(e)}"}

    def _step_8_risk_checks(self) -> tuple:
        self.strategy.log_step(8, "Risk Limit Validation")

        try:
            risk_check = check_risk_limits(self.account)

            if risk_check['action_required'] != 'NONE':
                self.logger.warning(f"❌ Risk limits breached: {risk_check['message']}")
                return False, risk_check

            self.logger.info(f"✅ All risk limits satisfied")
            self.logger.info("")
            return True, risk_check
        except Exception as e:
            self.logger.error(f"❌ Risk check failed: {str(e)}", exc_info=True)
            return False, {'error': str(e)}

    def _step_9_create_suggestion(self, entry_params: dict, filter_details: dict, sizing: dict) -> EntryResult:
        self.strategy.log_step(9, "Trade Suggestion Creation")

        try:
            # Build strategy-specific details
            position_details = self.strategy.build_position_details(entry_params, sizing)
            algorithm_reasoning = self.strategy.build_algorithm_reasoning(
                entry_params, filter_details, sizing
            )

            # Create trade suggestion
            suggestion = TradeSuggestionService.create_suggestion(
                user=self.account.user,
                strategy=self.config.name.lower().replace(' ', '_'),
                suggestion_type=self.config.strategy_type,
                instrument=position_details.get('instrument', 'NIFTY'),
                direction=self.config.direction,
                algorithm_reasoning=algorithm_reasoning,
                position_details=position_details
            )

            self.logger.info(f"✅ Trade suggestion created: {suggestion.id}")
            self.logger.info(f"   Status: {suggestion.get_status_display()}")
            self.logger.info("")
            self.logger.info("=" * 100)

            return EntryResult(
                success=True,
                message=f'Trade suggestion #{suggestion.id} created',
                suggestion=suggestion,
                details={
                    'suggestion_id': suggestion.id,
                    'status': suggestion.get_status_display(),
                }
            )
        except Exception as e:
            self.logger.error(f"❌ Trade suggestion creation failed: {str(e)}", exc_info=True)
            return EntryResult(False, f"Trade suggestion creation failed: {str(e)}")
```

---

## Phase 2: Create Shared Utilities

### 2.1 Create Directory
```bash
mkdir -p apps/strategies/shared
touch apps/strategies/shared/__init__.py
```

### 2.2 Create `apps/strategies/shared/market_data.py`

Extract from existing files - consolidate all market data fetching:

```python
"""
Shared market data fetching functions.
Used by all strategies to get current prices, VIX, premiums, etc.
"""

from decimal import Decimal
from datetime import datetime, timedelta
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


def get_nifty_price() -> Decimal:
    """Get current Nifty spot price"""
    try:
        from apps.brokers.models import HistoricalPrice

        latest_price = HistoricalPrice.objects.filter(
            symbol='NIFTY 50',
            timestamp__gte=datetime.now() - timedelta(days=1)
        ).order_by('-timestamp').first()

        if latest_price:
            return Decimal(str(latest_price.close))

        logger.warning("Using fallback Nifty price")
        return Decimal('24000.00')

    except Exception as e:
        logger.error(f"Error getting Nifty price: {e}")
        return Decimal('24000.00')


def get_vix() -> Decimal:
    """Get current India VIX value"""
    try:
        from apps.brokers.models import HistoricalPrice

        latest_vix = HistoricalPrice.objects.filter(
            symbol='INDIA VIX',
            timestamp__gte=datetime.now() - timedelta(days=1)
        ).order_by('-timestamp').first()

        if latest_vix:
            return Decimal(str(latest_vix.close))

        logger.warning("Using fallback VIX value")
        return Decimal('14.50')

    except Exception as e:
        logger.error(f"Error getting VIX: {e}")
        return Decimal('14.50')


def get_option_premiums(call_strike: int, put_strike: int, expiry_date) -> Tuple[Decimal, Decimal]:
    """Get option premiums for given strikes"""
    try:
        from apps.data.models import OptionChain

        call_option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=call_strike,
            option_type='CE',
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        put_option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=put_strike,
            option_type='PE',
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        call_premium = call_option.ltp if call_option else Decimal('100.0')
        put_premium = put_option.ltp if put_option else Decimal('100.0')

        logger.info(f"Premiums: {call_strike}CE = ₹{call_premium}, {put_strike}PE = ₹{put_premium}")

        return call_premium, put_premium

    except Exception as e:
        logger.error(f"Error getting option premiums: {e}")
        return Decimal('100.0'), Decimal('100.0')


def get_put_premium(strike: int, expiry_date) -> Decimal:
    """Get put option premium for a single strike"""
    try:
        from apps.data.models import OptionChain

        put_option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=strike,
            option_type='PE',
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        if put_option:
            return Decimal(str(put_option.ltp))

        logger.warning(f"Using estimated premium for {strike}PE")
        return Decimal('50.0')

    except Exception as e:
        logger.error(f"Error getting put premium: {e}")
        return Decimal('50.0')
```

### 2.3 Create `apps/strategies/shared/strike_calculator.py`

Extract from `kotak_strangle.py:45-130`:

```python
"""
Strike calculation logic for options strategies.
Shared by kotak_strangle and kotak_broken_iron_condor.
"""

from decimal import Decimal
from typing import Dict
import logging

logger = logging.getLogger(__name__)


def calculate_strangle_strikes(
    spot_price: Decimal,
    days_to_expiry: int,
    vix: Decimal,
    base_delta: Decimal = Decimal('0.5'),
    strike_interval: int = 100
) -> Dict:
    """
    Calculate OTM call and put strikes for short strangle.

    Formula:
        strike_distance = spot * (adjusted_delta / 100) * days_to_expiry

    VIX-based adjustment:
        - Normal VIX (< 15): 1.0x
        - Elevated VIX (15-18): 1.10x
        - High VIX (> 18): 1.20x

    Args:
        spot_price: Current Nifty spot price
        days_to_expiry: Days remaining to expiry
        vix: India VIX value
        base_delta: Base delta percentage (default 0.5%)
        strike_interval: Strike price interval (default 100 for Nifty)

    Returns:
        dict with call_strike, put_strike, strike_distance, etc.
    """

    # VIX-based adjustment
    if vix > 18:
        adjustment = Decimal('1.20')
        reason = f"High VIX ({vix:.1f}) - increasing strike distance for safety (+20%)"
    elif vix > 15:
        adjustment = Decimal('1.10')
        reason = f"Elevated VIX ({vix:.1f}) - slight increase in strike distance (+10%)"
    else:
        adjustment = Decimal('1.0')
        reason = f"Normal VIX ({vix:.1f}) - standard strike distance"

    adjusted_delta = base_delta * adjustment

    logger.info(f"Strike Selection Parameters:")
    logger.info(f"  Spot Price: ₹{spot_price:,.2f}")
    logger.info(f"  Days to Expiry: {days_to_expiry}")
    logger.info(f"  VIX: {vix:.2f}")
    logger.info(f"  Adjusted Delta: {adjusted_delta:.3f}% ({reason})")

    # Calculate strike distance
    strike_distance = spot_price * (adjusted_delta / Decimal('100')) * Decimal(str(days_to_expiry))

    # Calculate and round strikes
    call_strike_raw = spot_price + strike_distance
    put_strike_raw = spot_price - strike_distance

    call_strike = round(float(call_strike_raw) / strike_interval) * strike_interval
    put_strike = round(float(put_strike_raw) / strike_interval) * strike_interval

    logger.info(f"Strike Calculation:")
    logger.info(f"  Strike Distance: {strike_distance:.2f} points")
    logger.info(f"  Call Strike (OTM): {call_strike:,.0f}")
    logger.info(f"  Put Strike (OTM): {put_strike:,.0f}")

    return {
        'call_strike': int(call_strike),
        'put_strike': int(put_strike),
        'strike_distance': strike_distance,
        'adjusted_delta': adjusted_delta,
        'adjustment_reason': reason
    }
```

### 2.4 Create `apps/strategies/shared/entry_filters.py`

Extract from `kotak_strangle.py:133-215`:

```python
"""
Consolidated entry filters for all strategies.
"""

from typing import List, Tuple, Callable
import logging

from apps.strategies.filters.global_markets import check_global_market_stability
from apps.strategies.filters.event_calendar import check_economic_events
from apps.strategies.filters.volatility import check_market_regime


def get_default_filters() -> List[Callable]:
    """Return the default set of entry filters"""
    return [
        check_global_market_stability,
        lambda: check_economic_events(days_ahead=5),
        check_market_regime,
    ]


def run_filters(filters: List[Callable], log: logging.Logger = None) -> Tuple[bool, dict]:
    """
    Execute all entry filters.

    Args:
        filters: List of filter functions to execute
        log: Logger instance

    Returns:
        Tuple of (all_passed, details_dict)
    """
    log = log or logging.getLogger(__name__)

    log.info("=" * 80)
    log.info("ENTRY FILTER EXECUTION")
    log.info("=" * 80)

    passed = []
    failed = []

    filter_names = ['Global Markets', 'Economic Events', 'Market Regime']

    for i, filter_func in enumerate(filters):
        name = filter_names[i] if i < len(filter_names) else f"Filter {i+1}"

        try:
            result = filter_func()

            if result['passed']:
                passed.append(f"✅ {name}: {result['message']}")
            else:
                failed.append(f"❌ {name}: {result['message']}")

        except Exception as e:
            failed.append(f"❌ {name}: {str(e)}")
            log.error(f"Filter error: {e}", exc_info=True)

    # Log results
    log.info("")
    log.info("FILTER RESULTS:")
    log.info("-" * 80)

    for msg in passed:
        log.info(msg)
    for msg in failed:
        log.warning(msg)

    log.info("-" * 80)

    all_passed = len(failed) == 0

    if all_passed:
        log.info(f"✅ ALL FILTERS PASSED ({len(passed)}/{len(passed)})")
    else:
        log.warning(f"❌ FILTERS FAILED ({len(failed)}/{len(passed) + len(failed)})")

    log.info("=" * 80)
    log.info("")

    return all_passed, {
        'filters_passed': passed,
        'filters_failed': failed,
        'total_passed': len(passed),
        'total_failed': len(failed)
    }
```

---

## Phase 3: Refactor Kotak Strangle

### 3.1 Create New Class-Based Implementation

Replace the 715-line file with ~150 lines:

```python
"""
Kotak Strangle Strategy

Strategy: Sell OTM Nifty weekly call and put options to collect premium.
Account: Kotak Securities (Rs.6 Crores)
Target: Rs.6-8 Lakhs monthly (1.0-1.3% return)

Key Rules:
- ONE POSITION PER ACCOUNT
- 50% margin usage for first trade
- 1-day minimum to expiry
- Exit Thursday 3:15 PM (if >=50% profit) or Friday EOD
"""

from decimal import Decimal
from datetime import time
from typing import Dict

from apps.strategies.core.base_strategy import BaseStrategy
from apps.strategies.core.result_types import StrategyConfig, EntryResult
from apps.strategies.shared.strike_calculator import calculate_strangle_strikes
from apps.strategies.shared.market_data import get_nifty_price, get_vix, get_option_premiums
from apps.trading.risk_calculator import OptionsRiskCalculator, SupportResistanceCalculator


class KotakStrangleStrategy(BaseStrategy):
    """
    Short Strangle strategy for Kotak account.

    Unique Logic:
    - VIX-adjusted strike selection
    - Delta monitoring (alert if |net_delta| > 300)
    - Exit Thursday 3:15 PM (if >=50% profit) or Friday EOD
    """

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="Kotak Strangle Strategy",
            strategy_type='OPTIONS',
            direction='NEUTRAL',
            entry_start_time=time(9, 0),
            entry_end_time=time(11, 30),
            min_days_to_expiry=1,
            margin_usage_pct=Decimal('0.50'),
            extra={
                'delta_alert_threshold': 300,
                'profit_target_pct': Decimal('0.50'),
            }
        )

    def calculate_entry_parameters(self, market_data: Dict) -> Dict:
        """Calculate strikes and premiums for strangle"""

        spot_price = market_data.get('spot_price') or get_nifty_price()
        vix = market_data.get('vix') or get_vix()

        # Calculate strikes using shared utility
        strikes = calculate_strangle_strikes(
            spot_price=spot_price,
            days_to_expiry=market_data['days_to_expiry'],
            vix=vix
        )

        # Get option premiums
        call_premium, put_premium = get_option_premiums(
            strikes['call_strike'],
            strikes['put_strike'],
            market_data['expiry']
        )

        return {
            'spot_price': spot_price,
            'vix': vix,
            'strikes': strikes,
            'call_premium': call_premium,
            'put_premium': put_premium,
            'total_premium': call_premium + put_premium,
            'expiry': market_data['expiry'],
            'days_to_expiry': market_data['days_to_expiry']
        }

    def build_position_details(self, entry_params: Dict, sizing: Dict) -> Dict:
        """Build position details for trade suggestion"""
        strikes = entry_params['strikes']
        quantity = sizing['quantity']
        premium_collected = entry_params['total_premium'] * quantity

        return {
            'instrument': 'NIFTY',
            'strategy': 'Short Strangle',
            'call_strike': strikes['call_strike'],
            'put_strike': strikes['put_strike'],
            'quantity': quantity,
            'lot_size': sizing['lot_size'],
            'premium_collected': str(premium_collected),
            'margin_required': str(sizing['margin_used']),
            'expiry_date': str(entry_params['expiry']),
        }

    def build_algorithm_reasoning(self, entry_params: Dict, filters_result: Dict, sizing: Dict) -> Dict:
        """Build algorithm reasoning for trade suggestion"""
        strikes = entry_params['strikes']

        return {
            'title': 'Kotak Strangle Strategy',
            'summary': 'Short Strangle position to collect premium',
            'calculations': {
                'spot_price': str(entry_params['spot_price']),
                'vix': str(entry_params['vix']),
                'days_to_expiry': entry_params['days_to_expiry'],
                'strike_distance': str(strikes['strike_distance']),
                'adjusted_delta': str(strikes['adjusted_delta']),
                'adjustment_reason': strikes['adjustment_reason'],
                'call_premium': str(entry_params['call_premium']),
                'put_premium': str(entry_params['put_premium']),
            },
            'filters': filters_result,
            'position_sizing': {
                'lots': sizing['lots'],
                'quantity': sizing['quantity'],
                'margin_used': str(sizing['margin_used']),
            }
        }


# ============================================================================
# BACKWARD COMPATIBILITY WRAPPER
# ============================================================================

def execute_kotak_strangle_entry(account) -> Dict:
    """
    Backward compatible wrapper for existing code.

    Usage remains the same:
        result = execute_kotak_strangle_entry(account)
    """
    strategy = KotakStrangleStrategy(account)
    result = strategy.execute_entry()
    return result.to_dict()
```

---

## Phase 4: Refactor Kotak Broken Iron Condor

Similar pattern - keep only unique logic (insurance calculation):

```python
"""
Kotak Broken Iron Condor Strategy

Strategy: Short Strangle with protective put (insurance)
Account: Kotak Securities
Risk Profile: Defined risk on downside
"""

from decimal import Decimal
from datetime import time
from typing import Dict

from apps.strategies.core.base_strategy import BaseStrategy
from apps.strategies.core.result_types import StrategyConfig, EntryResult
from apps.strategies.shared.strike_calculator import calculate_strangle_strikes
from apps.strategies.shared.market_data import get_nifty_price, get_vix, get_option_premiums, get_put_premium


DEFAULT_RISK_MULTIPLIER = Decimal('2.0')


class KotakBrokenIronCondorStrategy(BaseStrategy):
    """
    Broken Iron Condor strategy - strangle with protective put.

    Unique Logic:
    - Insurance put calculation based on risk multiplier
    - 3-leg position (sell CE, sell PE, buy PE insurance)
    - Defined max loss on downside
    """

    def __init__(self, account, risk_multiplier: Decimal = DEFAULT_RISK_MULTIPLIER):
        super().__init__(account)
        self.risk_multiplier = risk_multiplier

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="Kotak Broken Iron Condor Strategy",
            strategy_type='OPTIONS',
            direction='NEUTRAL',
            entry_start_time=time(9, 0),
            entry_end_time=time(11, 30),
            min_days_to_expiry=1,
            margin_usage_pct=Decimal('0.50'),
            extra={
                'risk_multiplier': self.risk_multiplier,
            }
        )

    def calculate_entry_parameters(self, market_data: Dict) -> Dict:
        """Calculate strikes, premiums, and insurance for iron condor"""

        spot_price = market_data.get('spot_price') or get_nifty_price()
        vix = market_data.get('vix') or get_vix()

        # Calculate strangle strikes (same as strangle)
        strikes = calculate_strangle_strikes(
            spot_price=spot_price,
            days_to_expiry=market_data['days_to_expiry'],
            vix=vix
        )

        # Get option premiums
        call_premium, put_premium = get_option_premiums(
            strikes['call_strike'],
            strikes['put_strike'],
            market_data['expiry']
        )

        total_premium = call_premium + put_premium

        # Calculate insurance strike (UNIQUE TO THIS STRATEGY)
        insurance = self._calculate_insurance(
            put_strike=strikes['put_strike'],
            max_profit=total_premium * 50,  # Assuming 1 lot = 50 qty
            quantity=50
        )

        # Get insurance premium
        insurance_premium = get_put_premium(
            insurance['insurance_strike'],
            market_data['expiry']
        )

        return {
            'spot_price': spot_price,
            'vix': vix,
            'strikes': strikes,
            'call_premium': call_premium,
            'put_premium': put_premium,
            'total_strangle_premium': total_premium,
            'insurance': insurance,
            'insurance_premium': insurance_premium,
            'net_premium': total_premium - insurance_premium,
            'expiry': market_data['expiry'],
            'days_to_expiry': market_data['days_to_expiry']
        }

    def _calculate_insurance(self, put_strike: int, max_profit: Decimal, quantity: int) -> Dict:
        """
        Calculate insurance put strike based on risk budget.

        Insurance Logic:
            Risk Budget = Max Profit × Risk Multiplier
            Insurance Strike = Put Strike - (Risk Budget / Quantity)
        """
        risk_budget = max_profit * self.risk_multiplier
        max_loss_per_share = risk_budget / Decimal(str(quantity))

        insurance_strike_raw = Decimal(str(put_strike)) - max_loss_per_share
        insurance_strike = round(float(insurance_strike_raw) / 100) * 100

        # Ensure insurance is at least 100 points below sold put
        if insurance_strike >= put_strike:
            insurance_strike = put_strike - 100

        spread_width = put_strike - insurance_strike
        max_loss_on_put_side = Decimal(str(spread_width)) * Decimal(str(quantity))

        return {
            'insurance_strike': int(insurance_strike),
            'risk_budget': risk_budget,
            'spread_width': spread_width,
            'max_loss_on_put_side': max_loss_on_put_side,
            'risk_multiplier': self.risk_multiplier
        }

    def build_position_details(self, entry_params: Dict, sizing: Dict) -> Dict:
        """Build 3-leg position details"""
        strikes = entry_params['strikes']
        insurance = entry_params['insurance']
        quantity = sizing['quantity']

        return {
            'instrument': 'NIFTY',
            'strategy': 'Broken Iron Condor',
            'legs': [
                {'action': 'SELL', 'type': 'CE', 'strike': strikes['call_strike'], 'qty': quantity},
                {'action': 'SELL', 'type': 'PE', 'strike': strikes['put_strike'], 'qty': quantity},
                {'action': 'BUY', 'type': 'PE', 'strike': insurance['insurance_strike'], 'qty': quantity},
            ],
            'call_strike': strikes['call_strike'],
            'put_strike': strikes['put_strike'],
            'insurance_strike': insurance['insurance_strike'],
            'quantity': quantity,
            'net_premium': str(entry_params['net_premium'] * quantity),
            'max_loss_on_put_side': str(insurance['max_loss_on_put_side']),
            'margin_required': str(sizing['margin_used']),
            'expiry_date': str(entry_params['expiry']),
        }

    def build_algorithm_reasoning(self, entry_params: Dict, filters_result: Dict, sizing: Dict) -> Dict:
        """Build algorithm reasoning including insurance details"""
        strikes = entry_params['strikes']
        insurance = entry_params['insurance']

        return {
            'title': 'Kotak Broken Iron Condor Strategy',
            'summary': 'Short Strangle with protective put for defined downside risk',
            'calculations': {
                'spot_price': str(entry_params['spot_price']),
                'vix': str(entry_params['vix']),
                'days_to_expiry': entry_params['days_to_expiry'],
                'call_premium': str(entry_params['call_premium']),
                'put_premium': str(entry_params['put_premium']),
                'insurance_premium': str(entry_params['insurance_premium']),
                'net_premium': str(entry_params['net_premium']),
            },
            'insurance': {
                'insurance_strike': insurance['insurance_strike'],
                'risk_multiplier': str(insurance['risk_multiplier']),
                'max_loss_on_put_side': str(insurance['max_loss_on_put_side']),
                'spread_width': insurance['spread_width'],
            },
            'filters': filters_result,
            'position_sizing': {
                'lots': sizing['lots'],
                'quantity': sizing['quantity'],
                'margin_used': str(sizing['margin_used']),
            }
        }


# Keep additional unique functions
def get_insurance_strike_options(put_strike, max_profit, quantity, spot_price):
    """Generate multiple insurance options for user selection"""
    # ... (keep existing implementation)


def update_insurance_selection(suggestion_id, risk_multiplier):
    """Update insurance strike from UI selection"""
    # ... (keep existing implementation)


# BACKWARD COMPATIBILITY
def execute_kotak_broken_iron_condor_entry(account, risk_multiplier=DEFAULT_RISK_MULTIPLIER):
    """Backward compatible wrapper"""
    strategy = KotakBrokenIronCondorStrategy(account, risk_multiplier)
    return strategy.execute_entry().to_dict()
```

---

## Phase 5: Refactor ICICI Futures

Keep screening logic, add LLM validation as custom filter:

```python
"""
ICICI Futures Strategy

Strategy: Directional futures trading with multi-factor screening + LLM validation
Account: ICICI Securities (Rs.1.2 Crores)
"""

from decimal import Decimal
from datetime import time
from typing import Dict, List

from apps.strategies.core.base_strategy import BaseStrategy
from apps.strategies.core.result_types import StrategyConfig, EntryResult
from apps.llm.services.trade_validator import validate_trade


class ICICIFuturesStrategy(BaseStrategy):
    """
    Directional futures strategy with multi-factor screening.

    Unique Logic:
    - Multi-factor stock screening (OI + sector + technical)
    - LLM validation gate (70% confidence)
    - Averaging allowed (max 2 attempts)
    """

    def __init__(self, account, screened_candidate: Dict = None):
        self.candidate = screened_candidate
        super().__init__(account)

    def get_config(self) -> StrategyConfig:
        direction = self.candidate['direction'] if self.candidate else 'LONG'

        return StrategyConfig(
            name="ICICI Futures Strategy",
            strategy_type='FUTURES',
            direction=direction,
            entry_start_time=time(9, 15),
            entry_end_time=time(15, 0),
            min_days_to_expiry=15,
            margin_usage_pct=Decimal('0.50'),
            extra={
                'llm_confidence_threshold': Decimal('0.70'),
                'min_composite_score': 65,
            }
        )

    def get_entry_filters(self) -> List[callable]:
        """Add LLM validation as additional filter"""
        base_filters = super().get_entry_filters()
        return base_filters + [self._llm_validation_filter]

    def _llm_validation_filter(self) -> Dict:
        """LLM validation as a filter step"""
        if not self.candidate:
            return {'passed': False, 'message': 'No candidate to validate'}

        result = validate_trade(
            symbol=self.candidate['symbol'],
            direction=self.candidate['direction'],
            strategy_type='FUTURES'
        )

        confidence = result.get('confidence', 0)
        passed = result.get('approved', False) and confidence >= 0.70

        return {
            'passed': passed,
            'message': f"LLM confidence: {confidence*100:.1f}%",
            'details': result
        }

    def calculate_entry_parameters(self, market_data: Dict) -> Dict:
        """Calculate entry parameters for futures trade"""
        if not self.candidate:
            raise ValueError("No screened candidate provided")

        # ... (unique futures logic)

    # ... (rest of implementation)


# Keep screening functions as standalone (not part of workflow)
def screen_futures_opportunities(min_volume_rank=50, min_score=65):
    """Screen for futures trading opportunities"""
    # ... (keep existing implementation - this is unique)


def analyze_oi_for_stock(symbol):
    """Analyze OI for a stock"""
    # ... (keep existing)


def analyze_technical_for_stock(symbol):
    """Analyze technical indicators"""
    # ... (keep existing)


def calculate_composite_score(oi_score, sector_score, technical_score):
    """Calculate composite score"""
    # ... (keep existing)


# BACKWARD COMPATIBILITY
def execute_icici_futures_entry(account, symbol, direction, oi_analysis, sector_analysis, technical_analysis, composite_score):
    """Backward compatible wrapper"""
    candidate = {
        'symbol': symbol,
        'direction': direction,
        'composite_score': composite_score,
        'oi_analysis': oi_analysis,
        'sector_analysis': sector_analysis,
        'technical_analysis': technical_analysis,
    }
    strategy = ICICIFuturesStrategy(account, candidate)
    return strategy.execute_entry().to_dict()
```

---

## Phase 6: Cleanup and Testing

### 6.1 Update Imports

Update all files that import from strategy files:
- `apps/strategies/tasks.py`
- `apps/trading/views/algorithm_views.py`

### 6.2 Run Tests

```bash
# Run all strategy tests
python manage.py test apps.strategies

# Test individual strategies
python manage.py shell
>>> from apps.strategies.strategies.kotak_strangle import KotakStrangleStrategy
>>> from apps.accounts.models import BrokerAccount
>>> account = BrokerAccount.objects.filter(broker='KOTAK').first()
>>> result = KotakStrangleStrategy(account).execute_entry()
>>> print(result.success, result.message)
```

### 6.3 Compare Outputs

Compare new vs old implementation outputs to ensure identical behavior.

---

## Summary

| Metric | Before | After |
|--------|--------|-------|
| Total lines (4 files) | 3,170 | ~900 |
| Duplicated code | ~4,500 lines | 0 |
| Lines to understand a strategy | 700-1100 | 150-250 |
| Files to modify for strike change | 2 | 1 |

**Key Outcome**: Each algorithm becomes a ~150-250 line class with only its unique logic.
