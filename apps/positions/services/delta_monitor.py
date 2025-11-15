"""
Delta Monitoring Service

Monitors net delta for short strangle positions and generates alerts when
delta exceeds acceptable thresholds.

Delta Management Rules (from design doc):
- Monitor net delta continuously
- Alert when |delta| > 300
- Generate manual adjustment recommendations
- User executes adjustments (NOT automated)

Delta Calculation:
For short options:
- Short Call Delta: Negative (e.g., -0.40)
- Short Put Delta: Positive (e.g., +0.35)
- Net Delta = (Call Delta × Quantity) + (Put Delta × Quantity)

Example:
Sold 50 lots (2500 quantity)
Call Delta: -0.40
Put Delta: +0.35
Net Delta = (-0.40 × 2500) + (+0.35 × 2500) = -1000 + 875 = -125

Target: Net delta close to 0 (delta-neutral)
"""

import logging
from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime

from django.utils import timezone

from apps.positions.models import Position
from apps.alerts.services.telegram_client import send_telegram_notification

logger = logging.getLogger(__name__)


def calculate_option_delta(
    spot_price: Decimal,
    strike_price: Decimal,
    option_type: str,
    days_to_expiry: int,
    volatility: Decimal
) -> Decimal:
    """
    Calculate delta for an option

    This is a simplified approximation. For production, use proper
    options pricing libraries (e.g., py_vollib, mibian).

    Args:
        spot_price: Current underlying spot price
        strike_price: Option strike price
        option_type: 'CALL' or 'PUT'
        days_to_expiry: Days remaining to expiry
        volatility: Implied volatility (as percentage, e.g., 14.5)

    Returns:
        Decimal: Delta value (-1.0 to +1.0)

    TODO: Replace with proper Black-Scholes delta calculation using py_vollib
    """

    # Simplified delta approximation based on moneyness ratio
    # Moneyness = spot / strike (measures how far ITM/OTM the option is)
    # For production, replace with Black-Scholes delta using py_vollib library

    moneyness = float(spot_price / strike_price)

    if option_type == 'CALL':
        # Call delta approximation (higher when ITM, lower when OTM)
        # Long call: 0 to +1, Short call: 0 to -1
        if moneyness > 1.02:  # Deep ITM (spot >> strike, very likely to exercise)
            delta = Decimal('0.70')  # High delta, moves almost 1:1 with spot
        elif moneyness > 1.00:  # ATM (spot ≈ strike, 50-50 chance)
            delta = Decimal('0.50')  # Standard ATM delta
        elif moneyness > 0.98:  # Slightly OTM (spot < strike)
            delta = Decimal('0.40')
        elif moneyness > 0.95:  # OTM (spot << strike)
            delta = Decimal('0.25')  # Lower delta, less price sensitivity
        else:  # Deep OTM (very unlikely to be exercised)
            delta = Decimal('0.10')  # Very low delta

        # For short call (sold), delta is negative (we benefit when price drops)
        return -delta

    else:  # PUT
        # Put delta approximation (negative for long, positive for short)
        # Long put: 0 to -1, Short put: 0 to +1
        if moneyness < 0.98:  # Deep ITM (spot << strike, very likely to exercise)
            delta = Decimal('-0.70')  # High negative delta
        elif moneyness < 1.00:  # ATM (spot ≈ strike)
            delta = Decimal('-0.50')  # Standard ATM delta for puts
        elif moneyness < 1.02:  # Slightly OTM (spot > strike)
            delta = Decimal('-0.40')
        elif moneyness < 1.05:  # OTM (spot >> strike)
            delta = Decimal('-0.25')  # Lower delta, less sensitive
        else:  # Deep OTM (very unlikely to be exercised)
            delta = Decimal('-0.10')  # Very low delta

        # For short put (sold), delta is positive (we benefit when price rises)
        # Negate the long put delta to get short put delta
        return -delta


def calculate_strangle_delta(position: Position, current_spot: Decimal, vix: Decimal) -> Dict:
    """
    Calculate net delta for a short strangle position

    Args:
        position: Position instance (short strangle)
        current_spot: Current Nifty spot price
        vix: Current India VIX

    Returns:
        dict: {
            'call_delta': Decimal,
            'put_delta': Decimal,
            'net_delta': Decimal,
            'net_delta_absolute': Decimal,
            'quantity': int,
            'details': dict
        }
    """

    logger.debug(f"Calculating delta for position {position.id}...")

    # Days to expiry
    days_to_expiry = (position.expiry_date - timezone.now().date()).days

    # Calculate individual option deltas
    call_delta = calculate_option_delta(
        spot_price=current_spot,
        strike_price=position.call_strike,
        option_type='CALL',
        days_to_expiry=days_to_expiry,
        volatility=vix
    )

    put_delta = calculate_option_delta(
        spot_price=current_spot,
        strike_price=position.put_strike,
        option_type='PUT',
        days_to_expiry=days_to_expiry,
        volatility=vix
    )

    # Net delta = (call_delta × quantity) + (put_delta × quantity)
    net_delta = (call_delta * position.quantity) + (put_delta * position.quantity)
    net_delta_absolute = abs(net_delta)

    logger.debug(f"Delta Calculation:")
    logger.debug(f"  Call Strike: {position.call_strike}, Delta: {call_delta:.4f}")
    logger.debug(f"  Put Strike: {position.put_strike}, Delta: {put_delta:.4f}")
    logger.debug(f"  Quantity: {position.quantity}")
    logger.debug(f"  Net Delta: {net_delta:.2f}")

    return {
        'call_delta': call_delta,
        'put_delta': put_delta,
        'net_delta': net_delta,
        'net_delta_absolute': net_delta_absolute,
        'quantity': position.quantity,
        'details': {
            'call_strike': float(position.call_strike),
            'put_strike': float(position.put_strike),
            'spot_price': float(current_spot),
            'days_to_expiry': days_to_expiry,
            'vix': float(vix)
        }
    }


def monitor_delta(position: Position, delta_threshold: Decimal = Decimal('300')) -> Dict:
    """
    Monitor delta for a strangle position and generate alerts/recommendations

    Args:
        position: Position instance (short strangle)
        delta_threshold: Alert threshold for absolute net delta (default: 300)

    Returns:
        dict: {
            'delta_exceeded': bool,
            'net_delta': Decimal,
            'threshold': Decimal,
            'recommendation': str or None,
            'alert_sent': bool
        }
    """

    logger.info(f"=" * 80)
    logger.info(f"DELTA MONITORING: Position {position.id}")
    logger.info(f"=" * 80)

    try:
        # Get current market data
        # TODO: Fetch real-time spot price and VIX from broker
        current_spot = Decimal('24000')  # Placeholder
        vix = Decimal('14.5')  # Placeholder

        # Calculate delta
        delta_data = calculate_strangle_delta(position, current_spot, vix)

        net_delta = delta_data['net_delta']
        net_delta_abs = delta_data['net_delta_absolute']
        call_delta = delta_data['call_delta']
        put_delta = delta_data['put_delta']

        logger.info(f"Current Spot: ₹{current_spot:,.2f}")
        logger.info(f"VIX: {vix:.2f}")
        logger.info("")
        logger.info(f"Delta Components:")
        logger.info(f"  Call ({position.call_strike}CE): {call_delta:.4f}")
        logger.info(f"  Put ({position.put_strike}PE): {put_delta:.4f}")
        logger.info(f"  Quantity: {position.quantity}")
        logger.info("")
        logger.info(f"Net Delta: {net_delta:.2f}")
        logger.info(f"Absolute Delta: {net_delta_abs:.2f}")
        logger.info(f"Threshold: {delta_threshold:.2f}")
        logger.info("")

        # Update position with current delta
        position.current_delta = net_delta
        position.save(update_fields=['current_delta'])

        # Check if threshold exceeded
        delta_exceeded = net_delta_abs > delta_threshold

        recommendation = None
        alert_sent = False

        if delta_exceeded:
            logger.warning(f"⚠️ DELTA THRESHOLD EXCEEDED!")
            logger.warning(f"   Net Delta: {net_delta:.2f}")
            logger.warning(f"   Threshold: {delta_threshold:.2f}")
            logger.warning("")

            # Generate adjustment recommendation
            recommendation = generate_adjustment_recommendation(
                net_delta=net_delta,
                call_delta=call_delta,
                put_delta=put_delta,
                quantity=position.quantity,
                current_spot=current_spot,
                call_strike=position.call_strike,
                put_strike=position.put_strike
            )

            logger.warning(f"RECOMMENDATION:")
            logger.warning(f"{recommendation}")
            logger.warning("")

            # Send alert
            try:
                alert_message = (
                    f"⚠️ DELTA ALERT - Position {position.id}\n\n"
                    f"Net Delta: {net_delta:.2f}\n"
                    f"Threshold: {delta_threshold:.2f}\n"
                    f"Spot: ₹{current_spot:,.0f}\n\n"
                    f"Call: {position.call_strike}CE (Δ={call_delta:.4f})\n"
                    f"Put: {position.put_strike}PE (Δ={put_delta:.4f})\n\n"
                    f"RECOMMENDATION:\n{recommendation}"
                )

                send_telegram_notification(
                    message=alert_message,
                    notification_type='WARNING'
                )

                alert_sent = True
                logger.info(f"✅ Alert sent via Telegram")

            except Exception as e:
                logger.error(f"Failed to send delta alert: {e}", exc_info=True)

        else:
            logger.info(f"✅ Delta within acceptable range")

        logger.info(f"=" * 80)

        return {
            'delta_exceeded': delta_exceeded,
            'net_delta': net_delta,
            'net_delta_absolute': net_delta_abs,
            'threshold': delta_threshold,
            'call_delta': call_delta,
            'put_delta': put_delta,
            'recommendation': recommendation,
            'alert_sent': alert_sent,
            'details': delta_data['details']
        }

    except Exception as e:
        logger.error(f"Delta monitoring failed: {e}", exc_info=True)

        return {
            'delta_exceeded': False,
            'net_delta': Decimal('0'),
            'net_delta_absolute': Decimal('0'),
            'threshold': delta_threshold,
            'call_delta': Decimal('0'),
            'put_delta': Decimal('0'),
            'recommendation': None,
            'alert_sent': False,
            'details': {'error': str(e)}
        }


def generate_adjustment_recommendation(
    net_delta: Decimal,
    call_delta: Decimal,
    put_delta: Decimal,
    quantity: int,
    current_spot: Decimal,
    call_strike: Decimal,
    put_strike: Decimal
) -> str:
    """
    Generate manual adjustment recommendation for delta imbalance

    Args:
        net_delta: Net portfolio delta
        call_delta: Call option delta
        put_delta: Put option delta
        quantity: Current position quantity
        current_spot: Current spot price
        call_strike: Call strike
        put_strike: Put strike

    Returns:
        str: Human-readable adjustment recommendation
    """

    # Determine which side is dominant
    if net_delta > 0:
        # Net long delta (put side stronger)
        bias = "BULLISH"
        action = "sell additional calls or buy back some puts"

        # Calculate adjustment quantity (rough approximation)
        adjustment_qty = int(abs(net_delta / call_delta)) if call_delta != 0 else 0

        recommendation = f"""
Position has NET LONG delta ({net_delta:.0f}) - BULLISH bias

The position will profit if market goes UP, lose if market goes DOWN.
This violates delta-neutral requirement.

MANUAL ADJUSTMENT OPTIONS:

Option 1 (Preferred): Sell Additional Calls
  - Sell {adjustment_qty} quantity of {call_strike}CE or nearby strikes
  - This adds negative delta to neutralize the position

Option 2: Buy Back Puts
  - Buy back {adjustment_qty} quantity of {put_strike}PE
  - This reduces positive delta from short puts

Current Market: ₹{current_spot:,.0f}

⚠️ Execute adjustment manually through broker.
⚠️ Re-check delta after adjustment.
"""

    elif net_delta < 0:
        # Net short delta (call side stronger)
        bias = "BEARISH"
        action = "sell additional puts or buy back some calls"

        # Calculate adjustment quantity
        adjustment_qty = int(abs(net_delta / put_delta)) if put_delta != 0 else 0

        recommendation = f"""
Position has NET SHORT delta ({net_delta:.0f}) - BEARISH bias

The position will profit if market goes DOWN, lose if market goes UP.
This violates delta-neutral requirement.

MANUAL ADJUSTMENT OPTIONS:

Option 1 (Preferred): Sell Additional Puts
  - Sell {adjustment_qty} quantity of {put_strike}PE or nearby strikes
  - This adds positive delta to neutralize the position

Option 2: Buy Back Calls
  - Buy back {adjustment_qty} quantity of {call_strike}CE
  - This reduces negative delta from short calls

Current Market: ₹{current_spot:,.0f}

⚠️ Execute adjustment manually through broker.
⚠️ Re-check delta after adjustment.
"""

    else:
        # Delta is near zero (shouldn't reach here if threshold exceeded)
        recommendation = "Delta is balanced. No adjustment needed."

    return recommendation.strip()
