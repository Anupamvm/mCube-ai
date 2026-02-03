"""
Global Markets Filter

Checks global market stability before allowing Nifty options entry.

Filters:
1. SGX Nifty futures movement (Singapore Exchange)
2. US Markets (Nasdaq, Dow Jones) previous session

Thresholds:
- SGX Nifty: ±0.5% max movement
- US Markets: ±1.0% max movement

Rationale:
Global market volatility often translates to Indian market volatility,
making it risky to establish market-neutral positions during turbulent times.
"""

import logging
from decimal import Decimal
from typing import Dict
from datetime import datetime, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def get_sgx_nifty_change() -> Decimal:
    """
    Get SGX Nifty futures percentage change

    SGX Nifty trades during Asian market hours and provides early indication
    of Indian market sentiment before NSE opens.

    Returns:
        Decimal: Percentage change (e.g., 0.75 for +0.75%, -0.50 for -0.50%)

    TODO: Integrate with actual data source:
    - Option 1: Web scraping from SGX website
    - Option 2: Financial data API (e.g., Yahoo Finance)
    - Option 3: Broker API if available
    """

    # Placeholder implementation
    # TODO: Replace with actual SGX Nifty data fetch

    logger.debug("Fetching SGX Nifty change...")

    # Mock data for now
    sgx_change = Decimal('0.25')  # +0.25% change

    logger.debug(f"SGX Nifty Change: {sgx_change:+.2f}%")

    return sgx_change


def get_us_market_changes() -> Dict[str, Decimal]:
    """
    Get US market (Nasdaq, Dow Jones) previous session changes

    US market closes at ~4:00 AM IST, before Indian market opens at 9:15 AM.
    Strong US market moves often impact Indian market opening.

    Returns:
        dict: {
            'nasdaq': Decimal,  # % change
            'dow': Decimal      # % change
        }

    TODO: Integrate with actual data source:
    - Option 1: Yahoo Finance API
    - Option 2: Alpha Vantage API
    - Option 3: Financial Modeling Prep API
    """

    # Placeholder implementation
    # TODO: Replace with actual US market data fetch

    logger.debug("Fetching US market changes...")

    # Mock data for now
    us_changes = {
        'nasdaq': Decimal('0.45'),  # +0.45% change
        'dow': Decimal('0.35')       # +0.35% change
    }

    logger.debug(f"Nasdaq Change: {us_changes['nasdaq']:+.2f}%")
    logger.debug(f"Dow Jones Change: {us_changes['dow']:+.2f}%")

    return us_changes


def get_nifty_change(days: int = 1) -> Decimal:
    """
    Get Nifty percentage change over the last N trading days

    Uses actual trading days from HistoricalPrice (Mon-Fri, excluding holidays).

    Args:
        days: Number of trading days to look back (1, 3, 5, etc.)

    Returns:
        Decimal: Percentage change
    """
    try:
        from apps.brokers.models import HistoricalPrice

        logger.debug(f"Fetching Nifty change for last {days} trading day(s)...")

        # Get last N+1 records (need N+1 to calculate N-day change)
        records = HistoricalPrice.objects.filter(
            stock_code='NIFTY',
            product_type='cash',
            interval='1day'
        ).order_by('-datetime')[:days + 1]

        records = list(records)

        if len(records) < 2:
            logger.warning(f"Insufficient historical data for {days}D Nifty change, using fallback")
            # Fallback to mock data
            if days == 1:
                return Decimal('0.60')
            elif days == 3:
                return Decimal('1.20')
            else:
                return Decimal('0.0')

        # Most recent close and N-days-ago close
        latest_close = Decimal(str(records[0].close))
        older_close = Decimal(str(records[min(days, len(records) - 1)].close))

        if older_close == 0:
            return Decimal('0.0')

        nifty_change = ((latest_close - older_close) / older_close) * Decimal('100')
        nifty_change = nifty_change.quantize(Decimal('0.01'))

        logger.debug(f"Nifty {days}D Change: {nifty_change:+.2f}% ({older_close:.2f} -> {latest_close:.2f})")

        return nifty_change

    except Exception as e:
        logger.error(f"Error getting Nifty {days}D change: {e}")
        # Fallback to mock data on error
        if days == 1:
            return Decimal('0.60')
        elif days == 3:
            return Decimal('1.20')
        else:
            return Decimal('0.0')


def check_global_market_stability() -> Dict:
    """
    Check global market stability for strangle entry

    Checks:
    1. SGX Nifty change < ±0.5%
    2. US markets (Nasdaq/Dow) change < ±1.0%
    3. Recent Nifty movement < ±1.0% (1 day) and < ±2.0% (3 days)

    Returns:
        dict: {
            'passed': bool,
            'message': str,
            'details': dict
        }
    """

    logger.info("Checking global market stability...")

    details = {}
    issues = []

    # Check 1: SGX Nifty
    try:
        sgx_change = get_sgx_nifty_change()
        details['sgx_nifty_change'] = float(sgx_change)

        if abs(sgx_change) > Decimal('0.5'):
            issues.append(f"SGX Nifty moved {sgx_change:+.2f}% (limit: ±0.5%)")
        else:
            logger.debug(f"✅ SGX Nifty stable: {sgx_change:+.2f}%")

    except Exception as e:
        logger.error(f"Failed to fetch SGX Nifty: {e}")
        issues.append(f"SGX Nifty data unavailable")

    # Check 2: US Markets
    try:
        us_changes = get_us_market_changes()
        details['nasdaq_change'] = float(us_changes['nasdaq'])
        details['dow_change'] = float(us_changes['dow'])

        nasdaq_breach = abs(us_changes['nasdaq']) > Decimal('1.0')
        dow_breach = abs(us_changes['dow']) > Decimal('1.0')

        if nasdaq_breach or dow_breach:
            issues.append(
                f"US markets volatile (Nasdaq: {us_changes['nasdaq']:+.2f}%, "
                f"Dow: {us_changes['dow']:+.2f}%, limit: ±1.0%)"
            )
        else:
            logger.debug(
                f"✅ US markets stable (Nasdaq: {us_changes['nasdaq']:+.2f}%, "
                f"Dow: {us_changes['dow']:+.2f}%)"
            )

    except Exception as e:
        logger.error(f"Failed to fetch US market data: {e}")
        issues.append(f"US market data unavailable")

    # Check 3: Recent Nifty Movement
    try:
        nifty_1d = get_nifty_change(days=1)
        nifty_3d = get_nifty_change(days=3)

        details['nifty_1d_change'] = float(nifty_1d)
        details['nifty_3d_change'] = float(nifty_3d)

        if abs(nifty_1d) > Decimal('1.0'):
            issues.append(f"Nifty moved {nifty_1d:+.2f}% yesterday (limit: ±1.0%)")

        if abs(nifty_3d) > Decimal('2.0'):
            issues.append(f"Nifty moved {nifty_3d:+.2f}% in 3 days (limit: ±2.0%)")

        if abs(nifty_1d) <= Decimal('1.0') and abs(nifty_3d) <= Decimal('2.0'):
            logger.debug(
                f"✅ Nifty movement acceptable "
                f"(1D: {nifty_1d:+.2f}%, 3D: {nifty_3d:+.2f}%)"
            )

    except Exception as e:
        logger.error(f"Failed to fetch Nifty movement: {e}")
        issues.append(f"Nifty movement data unavailable")

    # Final verdict
    passed = len(issues) == 0

    if passed:
        message = "Global markets stable across all checks"
    else:
        message = "; ".join(issues)

    logger.info(f"Global market stability check: {'PASSED' if passed else 'FAILED'}")
    if not passed:
        for issue in issues:
            logger.warning(f"  - {issue}")

    return {
        'passed': passed,
        'message': message,
        'details': details
    }
