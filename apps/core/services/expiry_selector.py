"""
Expiry Selection Service

This service handles expiry date selection for options and futures.

CRITICAL EXPIRY RULES:
✅ OPTIONS: Don't trade options with < 1 day to expiry (gamma risk)
✅ FUTURES: Don't trade futures with < 15 days to expiry (liquidity risk)
✅ Skip to next expiry if current expiry is too close
"""

import logging
from datetime import date
from typing import Dict, Tuple

from apps.core.utils import (
    get_current_weekly_expiry,
    get_next_weekly_expiry,
    get_current_month_expiry,
    get_next_month_expiry,
    get_days_to_expiry,
)

logger = logging.getLogger(__name__)


def select_expiry_for_options(
    instrument: str = 'NIFTY',
    min_days: int = 1
) -> Tuple[date, Dict[str, any]]:
    """
    Select appropriate expiry for options trading

    CRITICAL: Don't trade options with < 1 day to expiry

    Gamma risk explodes near expiry. Skip to next weekly expiry if current
    expiry is less than minimum days away.

    Args:
        instrument: Instrument name (NIFTY, BANKNIFTY, FINNIFTY)
        min_days: Minimum days to expiry required (default: 1)

    Returns:
        Tuple[date, dict]: (selected_expiry, details_dict)

    Example:
        >>> expiry, details = select_expiry_for_options('NIFTY')
        >>> print(f"Selected expiry: {expiry} ({details['days_remaining']} days)")
        Selected expiry: 2024-11-21 (4 days)
    """

    current_expiry = get_current_weekly_expiry(instrument)
    days_to_current = get_days_to_expiry(current_expiry)

    # Check if current expiry meets minimum days requirement
    if days_to_current >= min_days:
        logger.info(
            f"✅ Using CURRENT expiry for {instrument}: "
            f"{current_expiry} ({days_to_current} days remaining)"
        )

        return current_expiry, {
            'selected_expiry': current_expiry,
            'days_remaining': days_to_current,
            'expiry_type': 'CURRENT_WEEK',
            'reason': f'Current expiry acceptable ({days_to_current} days >= {min_days} days)',
            'skipped': False
        }

    # Current expiry too close, skip to next week
    next_expiry = get_next_weekly_expiry(instrument)
    days_to_next = get_days_to_expiry(next_expiry)

    logger.warning(
        f"⚠️ Current expiry too close for {instrument}: "
        f"{current_expiry} (only {days_to_current} days)"
    )
    logger.info(
        f"✅ Skipping to NEXT WEEK expiry: "
        f"{next_expiry} ({days_to_next} days remaining)"
    )

    return next_expiry, {
        'selected_expiry': next_expiry,
        'days_remaining': days_to_next,
        'expiry_type': 'NEXT_WEEK',
        'reason': f'Skipped current expiry (only {days_to_current} days < {min_days} days minimum)',
        'skipped': True,
        'current_expiry': current_expiry,
        'days_to_current': days_to_current
    }


def select_expiry_for_futures(
    symbol: str,
    min_days: int = 15
) -> Tuple[date, Dict[str, any]]:
    """
    Select appropriate expiry for futures trading

    CRITICAL: Don't trade futures with < 15 days to expiry

    Near-month futures lose liquidity and spread widens. Skip to next monthly
    expiry if current expiry is less than minimum days away.

    Args:
        symbol: Stock/Index symbol (NIFTY, RELIANCE, etc.)
        min_days: Minimum days to expiry required (default: 15)

    Returns:
        Tuple[date, dict]: (selected_expiry, details_dict)

    Example:
        >>> expiry, details = select_expiry_for_futures('RELIANCE')
        >>> print(f"Selected expiry: {expiry} ({details['days_remaining']} days)")
        Selected expiry: 2024-12-26 (41 days)
    """

    current_expiry = get_current_month_expiry(symbol)
    days_to_current = get_days_to_expiry(current_expiry)

    # Check if current expiry meets minimum days requirement
    if days_to_current >= min_days:
        logger.info(
            f"✅ Using CURRENT month expiry for {symbol}: "
            f"{current_expiry} ({days_to_current} days remaining)"
        )

        return current_expiry, {
            'selected_expiry': current_expiry,
            'days_remaining': days_to_current,
            'expiry_type': 'CURRENT_MONTH',
            'reason': f'Current expiry acceptable ({days_to_current} days >= {min_days} days)',
            'skipped': False
        }

    # Current expiry too close, skip to next month
    next_expiry = get_next_month_expiry(symbol)
    days_to_next = get_days_to_expiry(next_expiry)

    logger.warning(
        f"⚠️ Current month expiry too close for {symbol}: "
        f"{current_expiry} (only {days_to_current} days)"
    )
    logger.info(
        f"✅ Skipping to NEXT MONTH expiry: "
        f"{next_expiry} ({days_to_next} days remaining)"
    )

    return next_expiry, {
        'selected_expiry': next_expiry,
        'days_remaining': days_to_next,
        'expiry_type': 'NEXT_MONTH',
        'reason': f'Skipped current expiry (only {days_to_current} days < {min_days} days minimum)',
        'skipped': True,
        'current_expiry': current_expiry,
        'days_to_current': days_to_current
    }


def validate_expiry_for_strategy(
    expiry_date: date,
    strategy_type: str
) -> Tuple[bool, str]:
    """
    Validate if expiry date is suitable for given strategy

    Args:
        expiry_date: Proposed expiry date
        strategy_type: WEEKLY_NIFTY_STRANGLE or LLM_VALIDATED_FUTURES

    Returns:
        Tuple[bool, str]: (is_valid, message)
    """

    days_remaining = get_days_to_expiry(expiry_date)

    if strategy_type == 'WEEKLY_NIFTY_STRANGLE':
        # Options: Minimum 1 day
        min_required = 1
        if days_remaining < min_required:
            message = (
                f"❌ Expiry too close for options: {expiry_date} "
                f"(only {days_remaining} days < {min_required} minimum)"
            )
            logger.warning(message)
            return False, message

        message = f"✅ Expiry valid for options: {expiry_date} ({days_remaining} days)"
        return True, message

    elif strategy_type == 'LLM_VALIDATED_FUTURES':
        # Futures: Minimum 15 days
        min_required = 15
        if days_remaining < min_required:
            message = (
                f"❌ Expiry too close for futures: {expiry_date} "
                f"(only {days_remaining} days < {min_required} minimum)"
            )
            logger.warning(message)
            return False, message

        message = f"✅ Expiry valid for futures: {expiry_date} ({days_remaining} days)"
        return True, message

    else:
        message = f"⚠️ Unknown strategy type: {strategy_type}"
        logger.warning(message)
        return False, message


def get_expiry_details(expiry_date: date) -> Dict[str, any]:
    """
    Get comprehensive details about an expiry date

    Args:
        expiry_date: Expiry date to analyze

    Returns:
        dict: Detailed information about the expiry
    """

    from datetime import datetime

    days_remaining = get_days_to_expiry(expiry_date)
    today = date.today()

    # Categorize time to expiry
    if days_remaining == 0:
        time_category = 'EXPIRY_TODAY'
        risk_level = 'CRITICAL'
    elif days_remaining == 1:
        time_category = 'EXPIRY_TOMORROW'
        risk_level = 'HIGH'
    elif days_remaining <= 7:
        time_category = 'THIS_WEEK'
        risk_level = 'MEDIUM'
    elif days_remaining <= 15:
        time_category = 'NEXT_2_WEEKS'
        risk_level = 'LOW'
    else:
        time_category = 'MORE_THAN_2_WEEKS'
        risk_level = 'VERY_LOW'

    # Determine if suitable for options/futures
    suitable_for_options = days_remaining >= 1
    suitable_for_futures = days_remaining >= 15

    return {
        'expiry_date': expiry_date,
        'days_remaining': days_remaining,
        'time_category': time_category,
        'risk_level': risk_level,
        'suitable_for_options': suitable_for_options,
        'suitable_for_futures': suitable_for_futures,
        'is_expiry_week': days_remaining <= 7,
        'is_expiry_day': days_remaining == 0,
    }


def should_roll_position(
    current_expiry: date,
    position_type: str = 'OPTIONS'
) -> Tuple[bool, str]:
    """
    Determine if position should be rolled to next expiry

    Args:
        current_expiry: Current position expiry
        position_type: 'OPTIONS' or 'FUTURES'

    Returns:
        Tuple[bool, str]: (should_roll, reason)
    """

    days_remaining = get_days_to_expiry(current_expiry)

    if position_type == 'OPTIONS':
        # Roll options if < 2 days remaining
        if days_remaining < 2:
            reason = (
                f"Should roll options position. "
                f"Only {days_remaining} days to expiry. "
                f"High gamma risk."
            )
            return True, reason

    elif position_type == 'FUTURES':
        # Roll futures if < 7 days remaining
        if days_remaining < 7:
            reason = (
                f"Should roll futures position. "
                f"Only {days_remaining} days to expiry. "
                f"Liquidity concerns."
            )
            return True, reason

    reason = f"No need to roll. {days_remaining} days remaining."
    return False, reason
