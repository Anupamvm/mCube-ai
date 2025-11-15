"""
Validation utility functions for mCube Trading System

This module provides validation functions for:
- Strike prices
- Market hours
- Position entries
- Trading parameters
"""

import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Tuple

from apps.core.constants import (
    NIFTY_STRIKE_INTERVAL,
    BANKNIFTY_STRIKE_INTERVAL,
    FINNIFTY_STRIKE_INTERVAL,
    INSTRUMENT_NIFTY,
    INSTRUMENT_BANKNIFTY,
    INSTRUMENT_FINNIFTY,
)

from .date_utils import is_market_hours, is_trading_day, get_days_to_expiry

logger = logging.getLogger(__name__)


def is_valid_strike(strike: int, instrument: str = 'NIFTY') -> bool:
    """
    Validate if strike price follows the correct interval for the instrument

    Args:
        strike: Strike price to validate
        instrument: Instrument name (NIFTY, BANKNIFTY, FINNIFTY)

    Returns:
        bool: True if strike is valid

    Example:
        >>> is_valid_strike(24000, 'NIFTY')  # 50 interval
        True
        >>> is_valid_strike(24025, 'NIFTY')
        False
        >>> is_valid_strike(51000, 'BANKNIFTY')  # 100 interval
        True
    """
    interval_map = {
        INSTRUMENT_NIFTY: NIFTY_STRIKE_INTERVAL,
        INSTRUMENT_BANKNIFTY: BANKNIFTY_STRIKE_INTERVAL,
        INSTRUMENT_FINNIFTY: FINNIFTY_STRIKE_INTERVAL,
    }

    interval = interval_map.get(instrument, 50)
    is_valid = (strike % interval) == 0

    if not is_valid:
        logger.warning(
            f"Invalid strike {strike} for {instrument}. "
            f"Must be multiple of {interval}"
        )

    return is_valid


def is_within_market_hours(check_time: datetime = None) -> bool:
    """
    Validate if given time is within market hours

    Wrapper around is_market_hours from date_utils for consistency

    Args:
        check_time: Time to check (defaults to now)

    Returns:
        bool: True if within market hours
    """
    return is_market_hours(check_time)


def validate_position_entry(
    account,
    strategy_type: str,
    expiry_date: date,
    margin_required: Decimal
) -> Tuple[bool, List[str]]:
    """
    Validate if position entry is allowed based on business rules

    This validates:
    1. ONE POSITION RULE - No existing active position
    2. Expiry date is not too close
    3. Sufficient margin available
    4. Market hours check
    5. Trading day check

    Args:
        account: BrokerAccount instance
        strategy_type: Type of strategy
        expiry_date: Contract expiry date
        margin_required: Margin required for position

    Returns:
        Tuple[bool, List[str]]: (is_valid, list of error messages)

    Example:
        >>> is_valid, errors = validate_position_entry(account, 'STRANGLE', expiry, margin)
        >>> if not is_valid:
        ...     print(errors)
        ['Active position already exists', 'Insufficient margin']
    """
    errors = []

    # RULE 1: Check for existing active position (ONE POSITION RULE)
    # Import here to avoid circular imports
    from apps.positions.models import Position

    if Position.has_active_position(account):
        errors.append(
            "Active position already exists. ONE POSITION RULE enforced. "
            "Close existing position before entering new trade."
        )

    # RULE 2: Check expiry date
    days_to_expiry = get_days_to_expiry(expiry_date)

    if 'STRANGLE' in strategy_type or 'OPTIONS' in strategy_type:
        # Options: Minimum 1 day to expiry
        if days_to_expiry < 1:
            errors.append(
                f"Expiry too close ({days_to_expiry} days). "
                "Options require minimum 1 day to expiry."
            )
    else:
        # Futures: Minimum 15 days to expiry
        if days_to_expiry < 15:
            errors.append(
                f"Expiry too close ({days_to_expiry} days). "
                "Futures require minimum 15 days to expiry."
            )

    # RULE 3: Check margin availability
    available_margin = account.get_available_capital()

    if margin_required > available_margin:
        errors.append(
            f"Insufficient margin. Required: Rs.{margin_required:,.0f}, "
            f"Available: Rs.{available_margin:,.0f}"
        )

    # RULE 4: Check if market is open
    if not is_market_hours():
        errors.append(
            "Market is closed. Positions can only be entered during market hours."
        )

    # RULE 5: Check if it's a trading day
    if not is_trading_day():
        errors.append(
            "Today is not a trading day. Positions can only be entered on trading days."
        )

    is_valid = len(errors) == 0

    if not is_valid:
        logger.warning(f"Position entry validation failed: {errors}")
    else:
        logger.info("Position entry validation passed")

    return is_valid, errors


def validate_margin_usage(
    used_margin: Decimal,
    total_margin: Decimal,
    max_usage_pct: Decimal = Decimal('0.50')
) -> Tuple[bool, str]:
    """
    Validate if margin usage is within limits

    Args:
        used_margin: Amount of margin being used
        total_margin: Total available margin
        max_usage_pct: Maximum allowed usage (default 50%)

    Returns:
        Tuple[bool, str]: (is_valid, error message if any)

    Example:
        >>> is_valid, msg = validate_margin_usage(
        ...     Decimal('3000000'),
        ...     Decimal('6000000'),
        ...     Decimal('0.50')
        ... )
        >>> is_valid
        True
    """
    usage_pct = used_margin / total_margin if total_margin > 0 else Decimal('1.0')

    if usage_pct > max_usage_pct:
        error_msg = (
            f"Margin usage {usage_pct * 100:.1f}% exceeds maximum "
            f"{max_usage_pct * 100:.0f}%. "
            f"Used: Rs.{used_margin:,.0f}, Available: Rs.{total_margin:,.0f}"
        )
        logger.warning(error_msg)
        return False, error_msg

    logger.debug(f"Margin usage validation passed: {usage_pct * 100:.1f}%")
    return True, ""


def validate_risk_reward_ratio(
    entry_price: Decimal,
    target_price: Decimal,
    stop_loss_price: Decimal,
    direction: str,
    min_rr: Decimal = Decimal('2.0')
) -> Tuple[bool, str]:
    """
    Validate if risk-reward ratio meets minimum requirement

    Args:
        entry_price: Entry price
        target_price: Target price
        stop_loss_price: Stop-loss price
        direction: LONG or SHORT
        min_rr: Minimum risk-reward ratio (default 2.0 for 1:2)

    Returns:
        Tuple[bool, str]: (is_valid, message)

    Example:
        >>> is_valid, msg = validate_risk_reward_ratio(
        ...     Decimal('100'),
        ...     Decimal('102'),
        ...     Decimal('99.50'),
        ...     'LONG',
        ...     Decimal('2.0')
        ... )
        >>> is_valid
        True
    """
    if direction == 'LONG':
        potential_profit = target_price - entry_price
        potential_loss = entry_price - stop_loss_price
    else:  # SHORT
        potential_profit = entry_price - target_price
        potential_loss = stop_loss_price - entry_price

    if potential_loss <= 0:
        return False, "Invalid stop-loss: must result in a loss if hit"

    rr_ratio = potential_profit / potential_loss

    if rr_ratio < min_rr:
        error_msg = (
            f"Risk-Reward ratio {rr_ratio:.2f} is below minimum {min_rr:.1f}. "
            f"Potential Profit: {potential_profit:.2f}, "
            f"Potential Loss: {potential_loss:.2f}"
        )
        logger.warning(error_msg)
        return False, error_msg

    logger.info(f"Risk-Reward ratio validation passed: {rr_ratio:.2f}")
    return True, f"Risk-Reward ratio: {rr_ratio:.2f}"


def validate_quantity(
    quantity: int,
    lot_size: int = 1
) -> Tuple[bool, str]:
    """
    Validate if quantity is in valid lot multiples

    Args:
        quantity: Quantity to validate
        lot_size: Lot size for the instrument

    Returns:
        Tuple[bool, str]: (is_valid, error message if any)

    Example:
        >>> is_valid, msg = validate_quantity(50, 50)  # NIFTY lot size
        True
        >>> is_valid, msg = validate_quantity(75, 50)
        False
    """
    if quantity <= 0:
        return False, "Quantity must be positive"

    if (quantity % lot_size) != 0:
        error_msg = (
            f"Quantity {quantity} is not a valid multiple of lot size {lot_size}"
        )
        logger.warning(error_msg)
        return False, error_msg

    return True, ""
