"""
Strike calculation logic for options strategies.

Shared by kotak_strangle and kotak_broken_iron_condor strategies.
This consolidates the duplicated calculate_strikes functions.
"""

from decimal import Decimal
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def calculate_strangle_strikes(
    spot_price: Decimal,
    days_to_expiry: int,
    vix: Decimal,
    base_delta: Decimal = Decimal('0.5'),
    strike_interval: int = 100,
    delta_adjustments: Dict = None
) -> Dict:
    """
    Calculate OTM call and put strikes for short strangle.

    Formula:
        strike_distance = spot * (adjusted_delta / 100) * days_to_expiry

    VIX-based adjustment:
        - Normal VIX (< 15): 1.0x (standard distance)
        - Elevated VIX (15-18): 1.10x (+10% buffer)
        - High VIX (> 18): 1.20x (+20% buffer)

    Enhanced Analysis adjustment (Phase 3):
        - call_multiplier: Adjust call strike distance
        - put_multiplier: Adjust put strike distance
        - Based on news sentiment, global markets, etc.

    Args:
        spot_price: Current Nifty spot price
        days_to_expiry: Days remaining to expiry
        vix: India VIX value
        base_delta: Base delta percentage (default 0.5%)
        strike_interval: Strike price interval (default 100 for Nifty)
        delta_adjustments: Optional dict from enhanced analysis with:
            - call_multiplier: float (e.g., 1.1 to widen call 10%)
            - put_multiplier: float (e.g., 0.95 to tighten put 5%)
            - adjustment_reasons: list of reason strings

    Returns:
        dict: {
            'call_strike': int,
            'put_strike': int,
            'strike_distance': Decimal,
            'adjusted_delta': Decimal,
            'adjustment_reason': str,
            'is_asymmetric': bool,
            'call_multiplier': float,
            'put_multiplier': float
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

    # Calculate base strike distance in points from spot
    # Formula: spot * (delta% / 100) * days_to_expiry
    # This scales the distance based on time remaining
    base_strike_distance = spot_price * (adjusted_delta / Decimal('100')) * Decimal(str(days_to_expiry))

    # Apply enhanced analysis delta adjustments if provided
    call_multiplier = 1.0
    put_multiplier = 1.0
    is_asymmetric = False

    if delta_adjustments:
        call_multiplier = delta_adjustments.get('call_multiplier', 1.0)
        put_multiplier = delta_adjustments.get('put_multiplier', 1.0)
        is_asymmetric = delta_adjustments.get('is_asymmetric', call_multiplier != put_multiplier)
        adjustment_reasons = delta_adjustments.get('adjustment_reasons', [])

        if is_asymmetric:
            logger.info(f"  Enhanced Analysis Adjustments:")
            logger.info(f"    Call Multiplier: {call_multiplier:.2f}x")
            logger.info(f"    Put Multiplier: {put_multiplier:.2f}x")
            if adjustment_reasons:
                for adj_reason in adjustment_reasons[:3]:
                    logger.info(f"    - {adj_reason}")
            reason += f" + Enhanced: call={call_multiplier:.2f}x, put={put_multiplier:.2f}x"

    # Calculate asymmetric strike distances
    call_distance = base_strike_distance * Decimal(str(call_multiplier))
    put_distance = base_strike_distance * Decimal(str(put_multiplier))

    # Calculate raw strike prices (before rounding)
    call_strike_raw = spot_price + call_distance  # OTM call above spot
    put_strike_raw = spot_price - put_distance    # OTM put below spot

    # Round to nearest strike_interval (Nifty strike interval is 100 points)
    # Example: 24,480 -> 24,500, 23,520 -> 23,500
    call_strike = round(float(call_strike_raw) / strike_interval) * strike_interval
    put_strike = round(float(put_strike_raw) / strike_interval) * strike_interval

    logger.info(f"Strike Calculation:")
    logger.info(f"  Base Strike Distance: {base_strike_distance:.2f} points")
    if is_asymmetric:
        logger.info(f"  Call Distance: {call_distance:.2f} points (×{call_multiplier:.2f})")
        logger.info(f"  Put Distance: {put_distance:.2f} points (×{put_multiplier:.2f})")
    logger.info(f"  Call Strike (OTM): {call_strike:,.0f}")
    logger.info(f"  Put Strike (OTM): {put_strike:,.0f}")

    return {
        'call_strike': int(call_strike),
        'put_strike': int(put_strike),
        'strike_distance': base_strike_distance,
        'call_distance': call_distance,
        'put_distance': put_distance,
        'adjusted_delta': adjusted_delta,
        'adjustment_reason': reason,
        'is_asymmetric': is_asymmetric,
        'call_multiplier': call_multiplier,
        'put_multiplier': put_multiplier,
    }
