"""
Consolidated entry filters for all strategies.

This module provides the standard entry filters and a runner function
that executes them and collects results. Consolidates duplicated code
from kotak_strangle.py and kotak_broken_iron_condor.py.
"""

from typing import List, Tuple, Callable, Dict
import logging


def get_default_filters() -> List[Callable]:
    """
    Return the default set of entry filters.

    Default filters:
    1. Global Market Stability (SGX Nifty, US markets)
    2. Economic Event Calendar (next 5 days)
    3. Market Regime (VIX, Bollinger Bands)

    Returns:
        List of filter callables
    """
    from apps.strategies.filters.global_markets import check_global_market_stability
    from apps.strategies.filters.event_calendar import check_economic_events
    from apps.strategies.filters.volatility import check_market_regime

    return [
        check_global_market_stability,
        lambda: check_economic_events(days_ahead=5),
        check_market_regime,
    ]


def run_filters(filters: List[Callable], log: logging.Logger = None) -> Tuple[bool, Dict]:
    """
    Execute all entry filters.

    Filter Logic: ALL must pass (conservative approach).
    If ANY filter fails, the trade is blocked.

    Args:
        filters: List of filter functions to execute
        log: Logger instance (optional)

    Returns:
        Tuple of (all_passed, details_dict)

    Details dict structure:
        {
            'filters_passed': ['message1', 'message2'],
            'filters_failed': ['message1'],
            'total_passed': int,
            'total_failed': int
        }
    """
    log = log or logging.getLogger(__name__)

    log.info("=" * 80)
    log.info("ENTRY FILTER EXECUTION")
    log.info("=" * 80)

    filters_passed = []
    filters_failed = []

    # Standard filter names for logging
    filter_names = ['Global Markets', 'Economic Events', 'Market Regime']

    for i, filter_func in enumerate(filters):
        name = filter_names[i] if i < len(filter_names) else f"Filter {i+1}"

        try:
            result = filter_func()

            if result['passed']:
                msg = f"[OK] {name}: {result['message']}"
                filters_passed.append(msg)
            else:
                msg = f"[FAILED] {name}: {result['message']}"
                filters_failed.append(msg)

        except Exception as e:
            msg = f"[ERROR] {name}: {str(e)}"
            filters_failed.append(msg)
            log.error(f"Filter error: {e}", exc_info=True)

    # Log results
    log.info("")
    log.info("FILTER RESULTS:")
    log.info("-" * 80)

    for msg in filters_passed:
        log.info(msg)
    for msg in filters_failed:
        log.warning(msg)

    log.info("-" * 80)

    all_passed = len(filters_failed) == 0

    if all_passed:
        log.info(f"[OK] ALL FILTERS PASSED ({len(filters_passed)}/{len(filters_passed)})")
        log.info("[OK] Entry evaluation can proceed")
    else:
        log.warning(f"[FAILED] FILTERS FAILED ({len(filters_failed)}/{len(filters_passed) + len(filters_failed)})")
        log.warning("[BLOCKED] Trade entry BLOCKED")

    log.info("=" * 80)
    log.info("")

    return all_passed, {
        'filters_passed': filters_passed,
        'filters_failed': filters_failed,
        'total_passed': len(filters_passed),
        'total_failed': len(filters_failed)
    }
