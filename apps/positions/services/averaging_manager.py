"""
Averaging Manager

Manages averaging (adding to position) for futures positions when they move against us.

Averaging Rules (from design doc):
- Maximum 3 averaging attempts per position
- Trigger: Position down by 1% from entry
- Action: Add equal quantity at current price
- Adjust: Tighten stop-loss to 0.5% from new average price
- Margin Check: Ensure sufficient margin available before averaging

Averaging Sequence:
- Average 1: Use 20% of current balance
- Average 2: Use 50% of remaining balance
- Average 3: Use 50% of remaining balance

Important: Averaging is ONLY for futures, NOT for options
"""

import logging
from decimal import Decimal
from typing import Dict, Tuple
from datetime import datetime

from django.utils import timezone
from django.db import transaction

from apps.positions.models import Position
from apps.accounts.models import BrokerAccount
from apps.alerts.services.telegram_client import send_telegram_notification

logger = logging.getLogger(__name__)


def should_average_position(position: Position, current_price: Decimal) -> Dict:
    """
    Determine if a position should be averaged

    Checks:
    1. Strategy allows averaging (futures only)
    2. Not exceeded max averaging attempts (max 3)
    3. Loss threshold reached (1% from entry)
    4. Margin available for averaging
    5. Position still active

    Args:
        position: Position instance
        current_price: Current market price

    Returns:
        dict: {
            'should_average': bool,
            'reason': str,
            'loss_pct': Decimal,
            'current_avg_count': int,
            'max_avg_count': int
        }
    """

    logger.info(f"=" * 80)
    logger.info(f"AVERAGING CHECK - Position {position.id}")
    logger.info(f"=" * 80)

    # Check 1: Strategy allows averaging (futures only)
    if position.strategy_type not in ['LLM_VALIDATED_FUTURES', 'ICICI_FUTURES']:
        reason = "Averaging not allowed for this strategy (futures only)"
        logger.warning(f"❌ {reason}")
        return {
            'should_average': False,
            'reason': reason,
            'loss_pct': Decimal('0'),
            'current_avg_count': position.averaging_count,
            'max_avg_count': 3
        }

    # Check 2: Position status
    if position.status != 'ACTIVE':
        reason = f"Position not active (status: {position.status})"
        logger.warning(f"❌ {reason}")
        return {
            'should_average': False,
            'reason': reason,
            'loss_pct': Decimal('0'),
            'current_avg_count': position.averaging_count,
            'max_avg_count': 3
        }

    # Check 3: Not exceeded max averaging attempts
    max_attempts = 3  # From design doc (can be made configurable via StrategyConfig)
    current_count = position.averaging_count

    if current_count >= max_attempts:
        reason = f"Maximum averaging attempts reached ({current_count}/{max_attempts})"
        logger.warning(f"❌ {reason}")
        return {
            'should_average': False,
            'reason': reason,
            'loss_pct': Decimal('0'),
            'current_avg_count': current_count,
            'max_avg_count': max_attempts
        }

    # Check 4: Calculate loss percentage from entry
    # Loss is negative when position is losing money
    entry_price = position.entry_price

    if position.direction == 'LONG':
        # LONG: Losing money when price drops (current < entry)
        # Example: Entry ₹100, Current ₹99 = -1% loss
        loss_pct = ((current_price - entry_price) / entry_price) * Decimal('100')
    else:  # SHORT
        # SHORT: Losing money when price rises (current > entry)
        # Example: Entry ₹100, Current ₹101 = -1% loss
        loss_pct = ((entry_price - current_price) / entry_price) * Decimal('100')

    logger.info(f"Position Details:")
    logger.info(f"  Direction: {position.direction}")
    logger.info(f"  Entry Price: ₹{entry_price:,.2f}")
    logger.info(f"  Current Price: ₹{current_price:,.2f}")
    logger.info(f"  Loss %: {loss_pct:.2f}%")
    logger.info(f"  Averaging Count: {current_count}/{max_attempts}")
    logger.info("")

    # Check if loss threshold reached (1% from design doc)
    loss_threshold = Decimal('-1.0')  # -1% loss

    if loss_pct > loss_threshold:
        reason = f"Loss {loss_pct:.2f}% not reached threshold ({loss_threshold:.2f}%)"
        logger.info(f"✅ {reason}")
        return {
            'should_average': False,
            'reason': reason,
            'loss_pct': loss_pct,
            'current_avg_count': current_count,
            'max_avg_count': max_attempts
        }

    # Check 5: Margin availability
    # This will be checked in execute_averaging(), but we do a preliminary check here
    account = position.account
    available_capital = account.get_available_capital()

    # Estimate margin needed (same as current position)
    estimated_margin_needed = position.margin_used

    if available_capital < estimated_margin_needed:
        reason = (
            f"Insufficient margin (available: ₹{available_capital:,.0f}, "
            f"needed: ₹{estimated_margin_needed:,.0f})"
        )
        logger.warning(f"❌ {reason}")
        return {
            'should_average': False,
            'reason': reason,
            'loss_pct': loss_pct,
            'current_avg_count': current_count,
            'max_avg_count': max_attempts
        }

    # All checks passed - averaging should be done
    reason = (
        f"Loss threshold breached ({loss_pct:.2f}% < {loss_threshold:.2f}%), "
        f"averaging attempt {current_count + 1}/{max_attempts}"
    )
    logger.warning(f"⚠️ AVERAGING TRIGGERED: {reason}")
    logger.info(f"=" * 80)

    return {
        'should_average': True,
        'reason': reason,
        'loss_pct': loss_pct,
        'current_avg_count': current_count,
        'max_avg_count': max_attempts
    }


@transaction.atomic
def execute_averaging(position: Position, current_price: Decimal) -> Tuple[bool, str, Dict]:
    """
    Execute averaging (add to position)

    Actions:
    1. Add equal quantity at current price
    2. Calculate new average entry price
    3. Update margin used
    4. Tighten stop-loss to 0.5% from new average
    5. Increment averaging count
    6. Send alert notification

    Args:
        position: Position instance
        current_price: Current market price

    Returns:
        tuple: (success: bool, message: str, details: dict)
    """

    logger.info(f"=" * 80)
    logger.info(f"EXECUTING AVERAGING - Position {position.id}")
    logger.info(f"=" * 80)

    try:
        # Store original values before modification (for logging and rollback if needed)
        original_quantity = position.quantity
        original_entry_price = position.entry_price
        original_margin = position.margin_used
        original_entry_value = position.entry_value

        # AVERAGING RULE: Add equal quantity at current price
        # Example: If original qty = 100, add another 100 at current price
        additional_quantity = original_quantity
        new_total_quantity = original_quantity + additional_quantity

        # Calculate new weighted average entry price
        # Formula: (old_price × old_qty + new_price × new_qty) / total_qty
        # Example: (₹100 × 100 + ₹99 × 100) / 200 = ₹99.50
        total_value = (original_entry_price * original_quantity) + (current_price * additional_quantity)
        new_average_price = total_value / new_total_quantity

        # Calculate additional margin needed
        # Assumption: Margin requirement is proportional to quantity
        margin_per_unit = original_margin / original_quantity if original_quantity > 0 else Decimal('0')
        additional_margin = margin_per_unit * additional_quantity

        # Check margin availability
        account = position.account
        available_capital = account.get_available_capital()

        if available_capital < additional_margin:
            msg = (
                f"Insufficient margin for averaging "
                f"(available: ₹{available_capital:,.0f}, needed: ₹{additional_margin:,.0f})"
            )
            logger.error(f"❌ {msg}")
            return False, msg, {}

        # Calculate new tighter stop-loss (0.5% from new average)
        # CRITICAL: After averaging, we tighten SL to protect averaged position
        # Was typically 1-2%, now tightened to 0.5% from new average
        stop_loss_pct = Decimal('0.005')  # 0.5% tight stop-loss

        if position.direction == 'LONG':
            # LONG: SL below new average (exit if price drops 0.5%)
            new_stop_loss = new_average_price * (Decimal('1') - stop_loss_pct)
        else:  # SHORT
            # SHORT: SL above new average (exit if price rises 0.5%)
            new_stop_loss = new_average_price * (Decimal('1') + stop_loss_pct)

        # Update position
        position.quantity = new_total_quantity
        position.entry_price = new_average_price
        position.margin_used = original_margin + additional_margin
        position.entry_value = new_average_price * new_total_quantity
        position.stop_loss = new_stop_loss
        position.averaging_count += 1
        position.save()

        logger.info(f"AVERAGING EXECUTED:")
        logger.info(f"  Previous Quantity: {original_quantity}")
        logger.info(f"  Added Quantity: {additional_quantity}")
        logger.info(f"  New Total Quantity: {new_total_quantity}")
        logger.info("")
        logger.info(f"  Previous Entry: ₹{original_entry_price:,.2f}")
        logger.info(f"  Averaging Price: ₹{current_price:,.2f}")
        logger.info(f"  New Average Entry: ₹{new_average_price:,.2f}")
        logger.info("")
        logger.info(f"  Previous Stop-Loss: ₹{position.stop_loss:,.2f}")
        logger.info(f"  New Stop-Loss (0.5%): ₹{new_stop_loss:,.2f}")
        logger.info("")
        logger.info(f"  Previous Margin: ₹{original_margin:,.0f}")
        logger.info(f"  Additional Margin: ₹{additional_margin:,.0f}")
        logger.info(f"  New Total Margin: ₹{position.margin_used:,.0f}")
        logger.info("")
        logger.info(f"  Averaging Attempt: {position.averaging_count}/3")
        logger.info("")

        # Send alert
        try:
            alert_message = (
                f"⚠️ POSITION AVERAGED - #{position.id}\n\n"
                f"Symbol: {position.instrument}\n"
                f"Direction: {position.direction}\n\n"
                f"Previous Quantity: {original_quantity}\n"
                f"Added Quantity: {additional_quantity}\n"
                f"New Quantity: {new_total_quantity}\n\n"
                f"Previous Entry: ₹{original_entry_price:,.2f}\n"
                f"Averaging Price: ₹{current_price:,.2f}\n"
                f"New Avg Entry: ₹{new_average_price:,.2f}\n\n"
                f"New Stop-Loss: ₹{new_stop_loss:,.2f} (0.5% from avg)\n\n"
                f"Averaging Count: {position.averaging_count}/3"
            )

            send_telegram_notification(
                message=alert_message,
                notification_type='WARNING'
            )

            logger.info("✅ Alert sent")

        except Exception as e:
            logger.error(f"Failed to send averaging alert: {e}")

        logger.info("=" * 80)

        details = {
            'previous_quantity': int(original_quantity),
            'added_quantity': int(additional_quantity),
            'new_quantity': int(new_total_quantity),
            'previous_entry': float(original_entry_price),
            'averaging_price': float(current_price),
            'new_average_entry': float(new_average_price),
            'previous_stop_loss': float(position.stop_loss),
            'new_stop_loss': float(new_stop_loss),
            'averaging_count': position.averaging_count
        }

        return True, "Averaging executed successfully", details

    except Exception as e:
        msg = f"Averaging execution failed: {str(e)}"
        logger.error(msg, exc_info=True)
        return False, msg, {}


def get_averaging_recommendation(position: Position, current_price: Decimal) -> Dict:
    """
    Get averaging recommendation without executing

    Returns:
        dict: {
            'should_average': bool,
            'reason': str,
            'details': dict,
            'preview': dict
        }
    """

    # Check if averaging should be done
    avg_check = should_average_position(position, current_price)

    if not avg_check['should_average']:
        return {
            'should_average': False,
            'reason': avg_check['reason'],
            'details': avg_check,
            'preview': {}
        }

    # Calculate preview
    original_quantity = position.quantity
    additional_quantity = original_quantity
    new_total_quantity = original_quantity + additional_quantity

    total_value = (position.entry_price * original_quantity) + (current_price * additional_quantity)
    new_average_price = total_value / new_total_quantity

    stop_loss_pct = Decimal('0.005')  # 0.5%

    if position.direction == 'LONG':
        new_stop_loss = new_average_price * (Decimal('1') - stop_loss_pct)
    else:
        new_stop_loss = new_average_price * (Decimal('1') + stop_loss_pct)

    margin_per_unit = position.margin_used / original_quantity if original_quantity > 0 else Decimal('0')
    additional_margin = margin_per_unit * additional_quantity

    preview = {
        'current_quantity': int(original_quantity),
        'quantity_to_add': int(additional_quantity),
        'new_total_quantity': int(new_total_quantity),
        'current_entry': float(position.entry_price),
        'averaging_price': float(current_price),
        'new_average_entry': float(new_average_price),
        'current_stop_loss': float(position.stop_loss),
        'new_stop_loss': float(new_stop_loss),
        'additional_margin_needed': float(additional_margin),
        'averaging_count_after': position.averaging_count + 1
    }

    return {
        'should_average': True,
        'reason': avg_check['reason'],
        'details': avg_check,
        'preview': preview
    }
