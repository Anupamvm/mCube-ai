"""
Strike calculation logic for options strategies.

Shared by kotak_strangle and kotak_broken_iron_condor strategies.
This consolidates the duplicated calculate_strikes functions.

Strike Calculation Flow (Enhanced):
1. calculate_strangle_strikes()     → Base strikes (VIX + delta)
2. adjust_strikes_for_sr()          → Move away from S/R levels
3. adjust_strikes_for_premium()     → Adjust to target 3-3.5 INR
4. check_strike_liquidity()         → Warning if OI < 100K
"""

from decimal import Decimal
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# S/R PROXIMITY ADJUSTMENT (Using Conservative Consolidated S/R)
# =============================================================================

def adjust_strikes_for_sr(
    call_strike: int,
    put_strike: int,
    spot_price: Decimal,
    strike_interval: int = 50,
    use_conservative: bool = True
) -> Dict:
    """
    Adjust strikes if too close to Support/Resistance levels.

    Uses CONSERVATIVE S/R from consolidated calculator which combines:
    1. Pivot Points (from historical price data)
    2. OI-Based S/R (from options open interest)

    Conservative approach:
    - For Support: Uses the HIGHER (closer to price) value from all methods
    - For Resistance: Uses the LOWER (closer to price) value from all methods

    Logic:
    - If CALL within 100 pts of conservative R1/R2 → Move UP 50 pts
    - If PUT within 100 pts of conservative S1/S2 → Move DOWN 50 pts

    Args:
        call_strike: Original call strike
        put_strike: Original put strike
        spot_price: Current spot price
        strike_interval: Strike interval for adjustments (default: 50 for NIFTY)
        use_conservative: Use conservative (closest) S/R levels (default: True)

    Returns:
        dict: {
            'call_strike': int (adjusted),
            'put_strike': int (adjusted),
            'call_adjusted': bool,
            'put_adjusted': bool,
            'call_adjustment_reason': str or None,
            'put_adjustment_reason': str or None,
            'sr_data': dict or None (S/R levels used),
            'sr_method': str (which method was used)
        }
    """
    result = {
        'call_strike': call_strike,
        'put_strike': put_strike,
        'call_adjusted': False,
        'put_adjusted': False,
        'call_adjustment_reason': None,
        'put_adjustment_reason': None,
        'sr_data': None,
        'sr_method': None
    }

    proximity_threshold = 100  # Points proximity threshold

    try:
        if use_conservative:
            # Use consolidated conservative S/R (combines Pivot + OI)
            from apps.strategies.services.consolidated_sr_calculator import (
                get_conservative_sr,
                check_strike_vs_conservative_sr
            )

            sr_data = get_conservative_sr('NIFTY', float(spot_price))
            result['sr_data'] = sr_data
            result['sr_method'] = 'Conservative (Pivot + OI)'

            if not sr_data.get('conservative_support', {}).get('s1'):
                logger.warning("Conservative S/R data not available, skipping adjustment")
                return result

            # Get conservative S/R levels
            s1 = sr_data['conservative_support']['s1']
            s2 = sr_data['conservative_support']['s2']
            r1 = sr_data['conservative_resistance']['r1']
            r2 = sr_data['conservative_resistance']['r2']

            # Check CALL strike against conservative resistance
            if r1 and abs(call_strike - r1) <= proximity_threshold:
                result['call_strike'] = call_strike + strike_interval
                result['call_adjusted'] = True
                result['call_adjustment_reason'] = (
                    f"CALL {call_strike} too close to conservative R1 ({r1:.0f}, "
                    f"source: {sr_data['conservative_resistance']['r1_source']})"
                )
                logger.info(f"S/R Adjustment: CALL {call_strike} → {result['call_strike']} "
                           f"({result['call_adjustment_reason']})")
            elif r2 and abs(call_strike - r2) <= proximity_threshold:
                result['call_strike'] = call_strike + strike_interval
                result['call_adjusted'] = True
                result['call_adjustment_reason'] = (
                    f"CALL {call_strike} too close to conservative R2 ({r2:.0f}, "
                    f"source: {sr_data['conservative_resistance']['r2_source']})"
                )
                logger.info(f"S/R Adjustment: CALL {call_strike} → {result['call_strike']} "
                           f"({result['call_adjustment_reason']})")

            # Check PUT strike against conservative support
            if s1 and abs(put_strike - s1) <= proximity_threshold:
                result['put_strike'] = put_strike - strike_interval
                result['put_adjusted'] = True
                result['put_adjustment_reason'] = (
                    f"PUT {put_strike} too close to conservative S1 ({s1:.0f}, "
                    f"source: {sr_data['conservative_support']['s1_source']})"
                )
                logger.info(f"S/R Adjustment: PUT {put_strike} → {result['put_strike']} "
                           f"({result['put_adjustment_reason']})")
            elif s2 and abs(put_strike - s2) <= proximity_threshold:
                result['put_strike'] = put_strike - strike_interval
                result['put_adjusted'] = True
                result['put_adjustment_reason'] = (
                    f"PUT {put_strike} too close to conservative S2 ({s2:.0f}, "
                    f"source: {sr_data['conservative_support']['s2_source']})"
                )
                logger.info(f"S/R Adjustment: PUT {put_strike} → {result['put_strike']} "
                           f"({result['put_adjustment_reason']})")

        else:
            # Fallback to original pivot-only method
            from apps.strategies.services.support_resistance_calculator import (
                calculate_nifty_sr,
                check_strike_sr_proximity
            )

            sr_data = calculate_nifty_sr(float(spot_price))
            result['sr_data'] = sr_data
            result['sr_method'] = 'Pivot Points Only'

            proximity_check = check_strike_sr_proximity(call_strike, put_strike, sr_data)

            call_adj = proximity_check['call_adjustment']
            if call_adj['should_adjust']:
                result['call_strike'] = call_adj['adjusted_strike']
                result['call_adjusted'] = True
                result['call_adjustment_reason'] = call_adj['reason']
                logger.info(f"S/R Adjustment: CALL {call_strike} → {result['call_strike']} "
                           f"({call_adj['reason']})")

            put_adj = proximity_check['put_adjustment']
            if put_adj['should_adjust']:
                result['put_strike'] = put_adj['adjusted_strike']
                result['put_adjusted'] = True
                result['put_adjustment_reason'] = put_adj['reason']
                logger.info(f"S/R Adjustment: PUT {put_strike} → {result['put_strike']} "
                           f"({put_adj['reason']})")

        if not result['call_adjusted'] and not result['put_adjusted']:
            logger.info(f"S/R Adjustment: No adjustments needed - strikes safe from {result['sr_method']} levels")

    except Exception as e:
        logger.warning(f"S/R adjustment failed (continuing with original strikes): {e}")

    return result


# =============================================================================
# PREMIUM-BASED STRIKE ADJUSTMENT
# =============================================================================

def adjust_strikes_for_premium(
    call_strike: int,
    put_strike: int,
    expiry_date,
    target_premium_min: Decimal = Decimal('3.0'),
    target_premium_max: Decimal = Decimal('3.5'),
    premium_floor: Decimal = Decimal('1.75'),
    strike_interval: int = 50,
    max_iterations: int = 5
) -> Dict:
    """
    Adjust strikes to achieve target premium range (3-3.5 INR for weekly expiry).

    Thresholds:
    - Premium > 7 INR: Move 100 pts OTM + IV_MISMATCH warning
    - Premium > 5 INR: Move 50 pts OTM
    - Premium < 2 INR: Move 50 pts closer (too cheap)

    Safety: Stop adjusting if premium drops below 1.75 INR (floor)
    Max 5 iterations to find acceptable premium.

    Args:
        call_strike: Call strike to adjust
        put_strike: Put strike to adjust
        expiry_date: Expiry date for premium lookup
        target_premium_min: Lower bound of target premium (default: 3.0)
        target_premium_max: Upper bound of target premium (default: 3.5)
        premium_floor: Minimum acceptable premium (default: 1.75)
        strike_interval: Strike adjustment step (default: 50)
        max_iterations: Max adjustment attempts (default: 5)

    Returns:
        dict: {
            'call_strike': int (adjusted),
            'put_strike': int (adjusted),
            'call_premium': Decimal,
            'put_premium': Decimal,
            'call_iterations': int,
            'put_iterations': int,
            'call_status': str ('OK', 'TOO_HIGH', 'TOO_LOW', 'IV_MISMATCH'),
            'put_status': str,
            'warnings': list
        }
    """
    from apps.strategies.shared.market_data import get_option_premium_for_strike

    result = {
        'call_strike': call_strike,
        'put_strike': put_strike,
        'call_premium': None,
        'put_premium': None,
        'call_iterations': 0,
        'put_iterations': 0,
        'call_status': 'OK',
        'put_status': 'OK',
        'warnings': []
    }

    # Adjust CALL strike
    result['call_strike'], result['call_premium'], result['call_iterations'], call_status = \
        _adjust_single_strike_for_premium(
            strike=call_strike,
            option_type='CE',
            expiry_date=expiry_date,
            target_min=target_premium_min,
            target_max=target_premium_max,
            premium_floor=premium_floor,
            strike_interval=strike_interval,
            max_iterations=max_iterations,
            direction='OTM'  # OTM = higher strike for call
        )
    result['call_status'] = call_status

    # Adjust PUT strike
    result['put_strike'], result['put_premium'], result['put_iterations'], put_status = \
        _adjust_single_strike_for_premium(
            strike=put_strike,
            option_type='PE',
            expiry_date=expiry_date,
            target_min=target_premium_min,
            target_max=target_premium_max,
            premium_floor=premium_floor,
            strike_interval=strike_interval,
            max_iterations=max_iterations,
            direction='OTM'  # OTM = lower strike for put
        )
    result['put_status'] = put_status

    # Log results
    if result['call_iterations'] > 0:
        logger.info(f"Premium Adjustment: CALL {call_strike} → {result['call_strike']} "
                   f"({result['call_iterations']} iterations, premium={result['call_premium']})")
    if result['put_iterations'] > 0:
        logger.info(f"Premium Adjustment: PUT {put_strike} → {result['put_strike']} "
                   f"({result['put_iterations']} iterations, premium={result['put_premium']})")

    # Add warnings
    if call_status == 'IV_MISMATCH':
        result['warnings'].append(f"CALL premium high despite OTM - possible IV mismatch")
    if put_status == 'IV_MISMATCH':
        result['warnings'].append(f"PUT premium high despite OTM - possible IV mismatch")
    if call_status == 'TOO_LOW':
        result['warnings'].append(f"CALL premium below floor ({premium_floor})")
    if put_status == 'TOO_LOW':
        result['warnings'].append(f"PUT premium below floor ({premium_floor})")

    return result


def _adjust_single_strike_for_premium(
    strike: int,
    option_type: str,
    expiry_date,
    target_min: Decimal,
    target_max: Decimal,
    premium_floor: Decimal,
    strike_interval: int,
    max_iterations: int,
    direction: str
) -> Tuple[int, Optional[Decimal], int, str]:
    """
    Adjust a single strike to target premium range.

    Args:
        strike: Current strike
        option_type: 'CE' or 'PE'
        expiry_date: Expiry date
        target_min: Lower bound of target premium
        target_max: Upper bound of target premium
        premium_floor: Minimum acceptable premium
        strike_interval: Adjustment step
        max_iterations: Max attempts
        direction: 'OTM' (call=higher, put=lower)

    Returns:
        Tuple: (adjusted_strike, premium, iterations, status)
    """
    from apps.strategies.shared.market_data import get_option_premium_for_strike

    current_strike = strike
    iterations = 0
    status = 'OK'

    for i in range(max_iterations):
        premium = get_option_premium_for_strike(current_strike, option_type, expiry_date)

        if premium is None:
            logger.warning(f"No premium data for {current_strike}{option_type}")
            return current_strike, None, iterations, 'NO_DATA'

        # Check if in target range
        if target_min <= premium <= target_max:
            return current_strike, premium, iterations, 'OK'

        # Premium too high
        if premium > Decimal('7'):
            # Move 100 pts OTM + IV_MISMATCH warning
            if option_type == 'CE':
                current_strike += 100
            else:
                current_strike -= 100
            iterations += 1
            status = 'IV_MISMATCH'
            logger.debug(f"Premium {premium:.2f} > 7 INR, moving 100 pts OTM")

        elif premium > Decimal('5'):
            # Move 50 pts OTM
            if option_type == 'CE':
                current_strike += strike_interval
            else:
                current_strike -= strike_interval
            iterations += 1
            logger.debug(f"Premium {premium:.2f} > 5 INR, moving 50 pts OTM")

        elif premium > target_max:
            # Move 50 pts OTM
            if option_type == 'CE':
                current_strike += strike_interval
            else:
                current_strike -= strike_interval
            iterations += 1

        elif premium < Decimal('2'):
            # Premium too low, move closer to ATM
            # But check floor first
            if premium < premium_floor:
                status = 'TOO_LOW'
                return current_strike, premium, iterations, status

            if option_type == 'CE':
                current_strike -= strike_interval
            else:
                current_strike += strike_interval
            iterations += 1
            logger.debug(f"Premium {premium:.2f} < 2 INR, moving 50 pts closer")

        elif premium < target_min:
            # Slightly below target, move closer
            # Check if moving closer would breach floor
            test_strike = current_strike - strike_interval if option_type == 'CE' else current_strike + strike_interval
            test_premium = get_option_premium_for_strike(test_strike, option_type, expiry_date)

            if test_premium and test_premium >= premium_floor:
                current_strike = test_strike
                iterations += 1
            else:
                # Accept current strike to avoid floor breach
                return current_strike, premium, iterations, 'OK'

    # Max iterations reached
    final_premium = get_option_premium_for_strike(current_strike, option_type, expiry_date)
    return current_strike, final_premium, iterations, status if status != 'OK' else 'MAX_ITERATIONS'


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
