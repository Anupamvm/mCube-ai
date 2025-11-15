"""
Position Management Service

This service handles position lifecycle management and enforces the ONE POSITION RULE.

CRITICAL BUSINESS RULE:
✅ ONE POSITION PER ACCOUNT AT ANY TIME
   - Before ANY entry decision, verify no active position exists
   - If position active → Monitor only, NO new entries
   - This rule is non-negotiable and enforced at code level
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional, Tuple

from django.utils import timezone

from apps.positions.models import Position
from apps.accounts.models import BrokerAccount
from apps.core.utils import get_current_ist_time

logger = logging.getLogger(__name__)


def morning_check(account: BrokerAccount) -> Dict[str, any]:
    """
    CRITICAL: Check existing position FIRST before any entry evaluation

    Morning Routine:
    1. Check if an active position exists for this account
    2. If YES → Enter MONITOR-ONLY mode, block all new entries
    3. If NO → Proceed to evaluate entry conditions

    This function must be called at the start of every trading day
    before any entry evaluation logic runs.

    Args:
        account: BrokerAccount instance

    Returns:
        dict: {
            'action': str - 'MONITOR' or 'EVALUATE_ENTRY',
            'position': Position or None - Active position if exists,
            'allow_new_entry': bool - Whether new entry is permitted,
            'message': str - Descriptive message
        }

    Example:
        >>> result = morning_check(kotak_account)
        >>> if not result['allow_new_entry']:
        ...     print(result['message'])
        ...     monitor_position(result['position'])
        ... else:
        ...     evaluate_entry_opportunities(account)
    """

    # RULE 1: Check for existing active position (ONE POSITION RULE)
    existing_position = Position.get_active_position(account)

    if existing_position:
        logger.info(
            f"✋ Active position exists: {existing_position.instrument} "
            f"{existing_position.direction}"
        )
        logger.info("📊 MONITOR MODE - No new entry permitted (ONE POSITION RULE)")

        message = (
            f"Active position: {existing_position.instrument} "
            f"{existing_position.direction}. "
            f"Entry: ₹{existing_position.entry_price:,.2f}, "
            f"Current: ₹{existing_position.current_price:,.2f}, "
            f"P&L: ₹{existing_position.unrealized_pnl:,.2f}. "
            f"Monitor only - no new entries allowed."
        )

        return {
            'action': 'MONITOR',
            'position': existing_position,
            'allow_new_entry': False,
            'message': message
        }

    logger.info("✅ No active position - Entry evaluation permitted")

    message = (
        f"No active position for {account.account_name}. "
        f"Entry evaluation is permitted."
    )

    return {
        'action': 'EVALUATE_ENTRY',
        'position': None,
        'allow_new_entry': True,
        'message': message
    }


def create_position(
    account: BrokerAccount,
    strategy_type: str,
    instrument: str,
    direction: str,
    quantity: int,
    lot_size: int,
    entry_price: Decimal,
    stop_loss: Decimal,
    target: Decimal,
    expiry_date,
    margin_used: Decimal,
    **kwargs
) -> Tuple[bool, Optional[Position], str]:
    """
    Create a new position with ONE POSITION RULE validation

    CRITICAL: This function enforces the ONE POSITION RULE before creating

    Args:
        account: BrokerAccount instance
        strategy_type: Strategy type (WEEKLY_NIFTY_STRANGLE, LLM_VALIDATED_FUTURES)
        instrument: Instrument name
        direction: LONG, SHORT, or NEUTRAL
        quantity: Number of lots
        lot_size: Lot size
        entry_price: Entry price
        stop_loss: Stop-loss price
        target: Target price
        expiry_date: Expiry date
        margin_used: Margin blocked
        **kwargs: Additional fields (call_strike, put_strike, premium_collected, etc.)

    Returns:
        Tuple[bool, Position, str]: (success, position, message)
    """

    # CRITICAL: Check ONE POSITION RULE
    if Position.has_active_position(account):
        existing = Position.get_active_position(account)
        message = (
            f"❌ Cannot create position. ONE POSITION RULE violated. "
            f"Active position exists: {existing.instrument}"
        )
        logger.error(message)
        return False, None, message

    # Calculate entry value
    entry_value = quantity * lot_size * entry_price

    # Create position
    try:
        position = Position.objects.create(
            account=account,
            strategy_type=strategy_type,
            instrument=instrument,
            direction=direction,
            quantity=quantity,
            lot_size=lot_size,
            entry_price=entry_price,
            current_price=entry_price,  # Initially same as entry
            stop_loss=stop_loss,
            target=target,
            expiry_date=expiry_date,
            margin_used=margin_used,
            entry_value=entry_value,
            status='ACTIVE',
            **kwargs  # Additional fields like call_strike, put_strike, etc.
        )

        message = (
            f"✅ Position created: {instrument} {direction} "
            f"Qty: {quantity} lots x {lot_size} = {quantity * lot_size} units, "
            f"Entry: ₹{entry_price:,.2f}, "
            f"SL: ₹{stop_loss:,.2f}, "
            f"Target: ₹{target:,.2f}, "
            f"Margin: ₹{margin_used:,.0f}"
        )
        logger.info(message)

        return True, position, message

    except Exception as e:
        message = f"❌ Failed to create position: {str(e)}"
        logger.error(message, exc_info=True)
        return False, None, message


def update_position_price(
    position: Position,
    current_price: Decimal
) -> bool:
    """
    Update position's current price and recalculate P&L

    Args:
        position: Position instance
        current_price: Current market price

    Returns:
        bool: Success status
    """

    try:
        old_price = position.current_price
        old_pnl = position.unrealized_pnl

        position.update_current_price(current_price)

        logger.debug(
            f"Price updated for {position.instrument}: "
            f"₹{old_price:,.2f} → ₹{current_price:,.2f}, "
            f"P&L: ₹{old_pnl:,.2f} → ₹{position.unrealized_pnl:,.2f}"
        )

        return True

    except Exception as e:
        logger.error(f"Failed to update position price: {str(e)}", exc_info=True)
        return False


def close_position(
    position: Position,
    exit_price: Decimal,
    exit_reason: str = "MANUAL"
) -> Tuple[bool, str]:
    """
    Close an active position

    Args:
        position: Position instance
        exit_price: Exit price
        exit_reason: Reason for exit (TARGET, STOP_LOSS, EOD, MANUAL, etc.)

    Returns:
        Tuple[bool, str]: (success, message)
    """

    try:
        position.close_position(exit_price, exit_reason)

        message = (
            f"✅ Position closed: {position.instrument} {position.direction}, "
            f"Entry: ₹{position.entry_price:,.2f}, "
            f"Exit: ₹{exit_price:,.2f}, "
            f"Realized P&L: ₹{position.realized_pnl:,.2f}, "
            f"Reason: {exit_reason}"
        )
        logger.info(message)

        return True, message

    except Exception as e:
        message = f"❌ Failed to close position: {str(e)}"
        logger.error(message, exc_info=True)
        return False, message


def get_position_summary(position: Position) -> Dict[str, any]:
    """
    Get comprehensive position summary

    Args:
        position: Position instance

    Returns:
        dict: Position summary with all key metrics
    """

    # Calculate holding period
    if position.status == 'ACTIVE':
        holding_period = (get_current_ist_time() - position.entry_time).days
        time_to_expiry = (position.expiry_date - timezone.now().date()).days
    else:
        holding_period = (position.exit_time - position.entry_time).days if position.exit_time else 0
        time_to_expiry = 0

    # Calculate P&L percentage
    if position.direction == 'NEUTRAL':  # Strangle
        pnl_pct = (position.unrealized_pnl / position.premium_collected * 100) if position.premium_collected > 0 else 0
    else:  # Futures
        pnl_pct = (position.unrealized_pnl / position.entry_value * 100) if position.entry_value > 0 else 0

    # Distance to SL and Target
    if position.direction == 'LONG':
        dist_to_sl = ((position.current_price - position.stop_loss) / position.current_price * 100)
        dist_to_target = ((position.target - position.current_price) / position.current_price * 100)
    elif position.direction == 'SHORT':
        dist_to_sl = ((position.stop_loss - position.current_price) / position.current_price * 100)
        dist_to_target = ((position.current_price - position.target) / position.current_price * 100)
    else:  # NEUTRAL
        dist_to_sl = 0
        dist_to_target = 0

    return {
        'instrument': position.instrument,
        'direction': position.direction,
        'strategy_type': position.strategy_type,
        'status': position.status,
        'quantity': position.quantity,
        'lot_size': position.lot_size,
        'total_quantity': position.quantity * position.lot_size,
        'entry_price': position.entry_price,
        'current_price': position.current_price,
        'stop_loss': position.stop_loss,
        'target': position.target,
        'entry_value': position.entry_value,
        'margin_used': position.margin_used,
        'unrealized_pnl': position.unrealized_pnl,
        'realized_pnl': position.realized_pnl,
        'pnl_pct': pnl_pct,
        'holding_period_days': holding_period,
        'time_to_expiry_days': time_to_expiry,
        'dist_to_sl_pct': dist_to_sl,
        'dist_to_target_pct': dist_to_target,
        'averaging_count': position.averaging_count,
        'entry_time': position.entry_time,
        'exit_time': position.exit_time,
        'exit_reason': position.exit_reason,
        # Strangle specific
        'call_strike': position.call_strike,
        'put_strike': position.put_strike,
        'premium_collected': position.premium_collected,
        'current_delta': position.current_delta,
    }


def average_position(
    position: Position,
    new_quantity: int,
    new_price: Decimal,
    new_margin: Decimal
) -> Tuple[bool, str]:
    """
    Average a futures position (add more quantity)

    Rules:
    - Maximum 2 averaging attempts
    - Only for LONG or SHORT positions (not NEUTRAL/Strangle)
    - Updates average price and adjusts stop-loss

    Args:
        position: Position instance
        new_quantity: Additional quantity (in lots)
        new_price: Price at which averaging
        new_margin: Additional margin required

    Returns:
        Tuple[bool, str]: (success, message)
    """

    if position.direction == 'NEUTRAL':
        return False, "Averaging not allowed for strangle positions"

    if position.averaging_count >= 2:
        return False, "Maximum 2 averaging attempts already used"

    try:
        # Store original entry price if first average
        if position.averaging_count == 0:
            position.original_entry_price = position.entry_price

        # Calculate new weighted average price
        old_qty = position.quantity * position.lot_size
        new_qty = new_quantity * position.lot_size
        total_qty = old_qty + new_qty

        weighted_price = (
            (position.entry_price * old_qty) + (new_price * new_qty)
        ) / total_qty

        # Update position
        position.quantity += new_quantity
        position.entry_price = weighted_price
        position.margin_used += new_margin
        position.averaging_count += 1

        # Tighten stop-loss to 0.5% from new average
        if position.direction == 'LONG':
            position.stop_loss = weighted_price * Decimal('0.995')  # 0.5% below
        else:  # SHORT
            position.stop_loss = weighted_price * Decimal('1.005')  # 0.5% above

        position.save()

        message = (
            f"✅ Position averaged (Attempt #{position.averaging_count}): "
            f"Added {new_quantity} lots @ ₹{new_price:,.2f}, "
            f"New avg price: ₹{weighted_price:,.2f}, "
            f"New SL: ₹{position.stop_loss:,.2f}, "
            f"Total qty: {position.quantity} lots"
        )
        logger.info(message)

        return True, message

    except Exception as e:
        message = f"❌ Failed to average position: {str(e)}"
        logger.error(message, exc_info=True)
        return False, message
