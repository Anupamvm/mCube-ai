"""
Strike calculation logic for options strategies.

Shared by kotak_strangle and kotak_broken_iron_condor strategies.
This consolidates the duplicated calculate_strikes functions.
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
        - Normal VIX (< 15): 1.0x (standard distance)
        - Elevated VIX (15-18): 1.10x (+10% buffer)
        - High VIX (> 18): 1.20x (+20% buffer)

    Args:
        spot_price: Current Nifty spot price
        days_to_expiry: Days remaining to expiry
        vix: India VIX value
        base_delta: Base delta percentage (default 0.5%)
        strike_interval: Strike price interval (default 100 for Nifty)

    Returns:
        dict: {
            'call_strike': int,
            'put_strike': int,
            'strike_distance': Decimal,
            'adjusted_delta': Decimal,
            'adjustment_reason': str
        }

    Example:
        Nifty = 24,000
        Days = 4
        VIX = 14 (normal)

        strike_distance = 24,000 * 0.005 * 4 = 480 points
        Call Strike = 24,480 -> Round to 24,500
        Put Strike = 23,520 -> Round to 23,500
    """

    # VIX-based adjustment: Higher volatility = wider strikes for safety
    # - VIX > 18 (high): Add 20% to strike distance (more conservative)
    # - VIX 15-18 (elevated): Add 10% to strike distance
    # - VIX < 15 (normal): Use standard distance
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
    logger.info(f"  Spot Price: Rs.{spot_price:,.2f}")
    logger.info(f"  Days to Expiry: {days_to_expiry}")
    logger.info(f"  VIX: {vix:.2f}")
    logger.info(f"  Adjusted Delta: {adjusted_delta:.3f}% ({reason})")

    # Calculate strike distance in points from spot
    # Formula: spot * (delta% / 100) * days_to_expiry
    # This scales the distance based on time remaining
    strike_distance = spot_price * (adjusted_delta / Decimal('100')) * Decimal(str(days_to_expiry))

    # Calculate raw strike prices (before rounding)
    call_strike_raw = spot_price + strike_distance  # OTM call above spot
    put_strike_raw = spot_price - strike_distance   # OTM put below spot

    # Round to nearest strike_interval (Nifty strike interval is 100 points)
    # Example: 24,480 -> 24,500, 23,520 -> 23,500
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
