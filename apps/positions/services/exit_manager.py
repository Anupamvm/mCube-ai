"""
Exit Management Service

This service handles position exit logic including stop-loss, target, and EOD exits.

CRITICAL EXIT RULES:
✅ TARGET HIT → Exit immediately
✅ STOP-LOSS HIT → Exit immediately
✅ EOD (3:15 PM) → Exit ONLY if minimum profit threshold achieved (50%)
✅ If minimum profit NOT achieved → Hold position (accept overnight risk)
"""

import logging
from datetime import time
from decimal import Decimal
from typing import Dict, Tuple

from apps.positions.models import Position
from apps.core.utils import get_current_ist_time, is_market_hours
from apps.core.constants import (
    KOTAK_EXIT_TIME,
    MANDATORY_EXIT_TIME,
    WEEKDAY_THURSDAY,
    WEEKDAY_FRIDAY,
)

logger = logging.getLogger(__name__)


def check_exit_conditions(position: Position) -> Dict[str, any]:
    """
    Check all exit conditions for a position

    Exit Priority:
    1. Stop-loss hit → IMMEDIATE EXIT
    2. Target hit → IMMEDIATE EXIT
    3. EOD exit → CONDITIONAL (only if profit >= 50%)
    4. Expiry day → MANDATORY EXIT

    Args:
        position: Position instance

    Returns:
        dict: {
            'should_exit': bool,
            'exit_reason': str,
            'exit_price': Decimal,
            'message': str,
            'is_mandatory': bool  # True for SL/Target/Expiry, False for EOD
        }
    """

    current_time = get_current_ist_time()
    current_price = position.current_price

    # RULE 1: Check Stop-Loss
    if position.is_stop_loss_hit():
        message = (
            f"🚨 STOP-LOSS HIT: {position.instrument} "
            f"Current: ₹{current_price:,.2f}, SL: ₹{position.stop_loss:,.2f}. "
            f"IMMEDIATE EXIT REQUIRED."
        )
        logger.warning(message)

        return {
            'should_exit': True,
            'exit_reason': 'STOP_LOSS',
            'exit_price': current_price,
            'message': message,
            'is_mandatory': True
        }

    # RULE 2: Check Target
    if position.is_target_hit():
        message = (
            f"🎯 TARGET HIT: {position.instrument} "
            f"Current: ₹{current_price:,.2f}, Target: ₹{position.target:,.2f}. "
            f"IMMEDIATE EXIT REQUIRED."
        )
        logger.info(message)

        return {
            'should_exit': True,
            'exit_reason': 'TARGET',
            'exit_price': current_price,
            'message': message,
            'is_mandatory': True
        }

    # RULE 3: Check EOD Exit (with 50% minimum profit rule)
    eod_check = check_eod_exit(position, current_time)
    if eod_check['should_exit']:
        return eod_check

    # RULE 4: Check Expiry Day Exit
    expiry_check = check_expiry_exit(position, current_time)
    if expiry_check['should_exit']:
        return expiry_check

    # No exit condition met
    return {
        'should_exit': False,
        'exit_reason': None,
        'exit_price': None,
        'message': f"No exit condition met for {position.instrument}",
        'is_mandatory': False
    }


def check_eod_exit(position: Position, current_time) -> Dict[str, any]:
    """
    Check EOD exit conditions with 50% minimum profit rule

    EOD Exit Rules:
    - Kotak (Strangle): Thursday 3:15 PM exit if profit >= 50%
    - ICICI (Futures): Any day 3:15 PM exit if profit >= 50%
    - If profit < 50% → Hold overnight

    Args:
        position: Position instance
        current_time: Current IST time

    Returns:
        dict: Exit decision with reasoning
    """

    # Check if it's EOD time (3:15 PM)
    if current_time.time() < time(15, 15):
        return {'should_exit': False, 'exit_reason': None, 'exit_price': None,
                'message': 'Not EOD time yet', 'is_mandatory': False}

    # Calculate current profit percentage
    if position.direction == 'NEUTRAL':  # Strangle
        if position.premium_collected > 0:
            profit_pct = (position.unrealized_pnl / position.premium_collected) * 100
        else:
            profit_pct = Decimal('0')
    else:  # Futures
        if position.entry_value > 0:
            profit_pct = (position.unrealized_pnl / position.entry_value) * 100
        else:
            profit_pct = Decimal('0')

    # Get minimum profit threshold from strategy config
    min_profit_threshold = Decimal('50.0')  # 50% minimum

    # Check if it's Thursday (for Kotak strategy)
    is_thursday = current_time.weekday() == WEEKDAY_THURSDAY

    # Kotak Strangle: Thursday 3:15 PM
    if position.strategy_type == 'WEEKLY_NIFTY_STRANGLE' and is_thursday:
        if profit_pct >= min_profit_threshold:
            message = (
                f"📅 THURSDAY EOD EXIT: {position.instrument}, "
                f"Profit: {profit_pct:.2f}% (>= {min_profit_threshold}%). "
                f"Exiting as planned."
            )
            logger.info(message)

            return {
                'should_exit': True,
                'exit_reason': 'EOD_THURSDAY',
                'exit_price': position.current_price,
                'message': message,
                'is_mandatory': False
            }
        else:
            message = (
                f"⏳ THURSDAY EOD - HOLD: {position.instrument}, "
                f"Profit: {profit_pct:.2f}% (< {min_profit_threshold}%). "
                f"Holding overnight as profit threshold not met."
            )
            logger.info(message)

            return {
                'should_exit': False,
                'exit_reason': None,
                'exit_price': None,
                'message': message,
                'is_mandatory': False
            }

    # ICICI Futures: Any day 3:15 PM
    if position.strategy_type == 'LLM_VALIDATED_FUTURES':
        if profit_pct >= min_profit_threshold:
            message = (
                f"📅 EOD EXIT: {position.instrument}, "
                f"Profit: {profit_pct:.2f}% (>= {min_profit_threshold}%). "
                f"Exiting as planned."
            )
            logger.info(message)

            return {
                'should_exit': True,
                'exit_reason': 'EOD',
                'exit_price': position.current_price,
                'message': message,
                'is_mandatory': False
            }
        else:
            message = (
                f"⏳ EOD - HOLD: {position.instrument}, "
                f"Profit: {profit_pct:.2f}% (< {min_profit_threshold}%). "
                f"Holding overnight as profit threshold not met."
            )
            logger.info(message)

            return {
                'should_exit': False,
                'exit_reason': None,
                'exit_price': None,
                'message': message,
                'is_mandatory': False
            }

    return {'should_exit': False, 'exit_reason': None, 'exit_price': None,
            'message': 'No EOD exit condition', 'is_mandatory': False}


def check_expiry_exit(position: Position, current_time) -> Dict[str, any]:
    """
    Check if position must be exited due to expiry

    Expiry Exit Rules:
    - Friday (Options expiry): Mandatory exit by 3:20 PM
    - Last day of futures contract: Mandatory exit by 3:20 PM

    Args:
        position: Position instance
        current_time: Current IST time

    Returns:
        dict: Exit decision
    """

    from datetime import timedelta

    # Check if expiry is today or tomorrow
    days_to_expiry = (position.expiry_date - current_time.date()).days

    # If expiry is today, must exit by 3:20 PM
    if days_to_expiry == 0:
        if current_time.time() >= time(15, 20):
            message = (
                f"⚠️ EXPIRY DAY - MANDATORY EXIT: {position.instrument} "
                f"expires today. IMMEDIATE EXIT REQUIRED."
            )
            logger.warning(message)

            return {
                'should_exit': True,
                'exit_reason': 'EXPIRY_DAY',
                'exit_price': position.current_price,
                'message': message,
                'is_mandatory': True
            }

    # If expiry is tomorrow and it's Friday, exit today
    if days_to_expiry == 1 and current_time.weekday() == WEEKDAY_FRIDAY:
        if current_time.time() >= time(15, 15):
            message = (
                f"⚠️ FRIDAY EOD - MANDATORY EXIT: {position.instrument} "
                f"expires tomorrow. Exiting to avoid weekend risk."
            )
            logger.warning(message)

            return {
                'should_exit': True,
                'exit_reason': 'FRIDAY_EOD',
                'exit_price': position.current_price,
                'message': message,
                'is_mandatory': True
            }

    return {'should_exit': False, 'exit_reason': None, 'exit_price': None,
            'message': 'No expiry exit condition', 'is_mandatory': False}


def should_exit_position(position: Position) -> Tuple[bool, str, Decimal]:
    """
    Determine if position should be exited

    Wrapper function that checks all exit conditions

    Args:
        position: Position instance

    Returns:
        Tuple[bool, str, Decimal]: (should_exit, exit_reason, exit_price)
    """

    exit_check = check_exit_conditions(position)

    return (
        exit_check['should_exit'],
        exit_check['exit_reason'],
        exit_check['exit_price']
    )


def calculate_exit_metrics(position: Position, exit_price: Decimal) -> Dict[str, any]:
    """
    Calculate exit metrics and statistics

    Args:
        position: Position instance
        exit_price: Proposed exit price

    Returns:
        dict: Exit metrics including P&L, ROI, holding period, etc.
    """

    # Calculate P&L at exit price
    if position.direction == 'LONG':
        pnl_per_unit = exit_price - position.entry_price
    elif position.direction == 'SHORT':
        pnl_per_unit = position.entry_price - exit_price
    else:  # NEUTRAL (Strangle)
        pnl_per_unit = position.premium_collected - exit_price

    realized_pnl = pnl_per_unit * position.quantity * position.lot_size

    # Calculate ROI
    if position.direction == 'NEUTRAL':  # Strangle
        roi_pct = (realized_pnl / position.premium_collected * 100) if position.premium_collected > 0 else 0
    else:  # Futures
        roi_pct = (realized_pnl / position.entry_value * 100) if position.entry_value > 0 else 0

    # Calculate ROI on margin
    roi_on_margin = (realized_pnl / position.margin_used * 100) if position.margin_used > 0 else 0

    # Calculate holding period
    from apps.core.utils import get_current_ist_time
    current_time = get_current_ist_time()
    holding_period_hours = (current_time - position.entry_time).total_seconds() / 3600
    holding_period_days = holding_period_hours / 24

    return {
        'exit_price': exit_price,
        'entry_price': position.entry_price,
        'realized_pnl': realized_pnl,
        'roi_pct': roi_pct,
        'roi_on_margin': roi_on_margin,
        'holding_period_hours': holding_period_hours,
        'holding_period_days': holding_period_days,
        'total_quantity': position.quantity * position.lot_size,
        'margin_used': position.margin_used,
        'was_profitable': realized_pnl > 0,
        'averaging_count': position.averaging_count,
    }


def get_recommended_exit_action(position: Position) -> Dict[str, any]:
    """
    Get recommended exit action with reasoning

    This provides a recommendation but doesn't execute

    Args:
        position: Position instance

    Returns:
        dict: Recommendation with detailed reasoning
    """

    exit_check = check_exit_conditions(position)

    if exit_check['should_exit']:
        action = 'EXIT'
        priority = 'HIGH' if exit_check['is_mandatory'] else 'MEDIUM'
    else:
        action = 'HOLD'
        priority = 'LOW'

    # Calculate potential exit metrics
    if exit_check['exit_price']:
        exit_metrics = calculate_exit_metrics(position, exit_check['exit_price'])
    else:
        exit_metrics = None

    return {
        'action': action,
        'priority': priority,
        'reason': exit_check['exit_reason'],
        'message': exit_check['message'],
        'is_mandatory': exit_check['is_mandatory'],
        'exit_price': exit_check['exit_price'],
        'exit_metrics': exit_metrics,
    }
