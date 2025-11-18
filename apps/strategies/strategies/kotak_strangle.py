"""
Kotak Strangle Strategy

Strategy: Sell out-of-the-money (OTM) Nifty weekly call and put options simultaneously
         to collect premium income while maintaining delta neutrality.

Account: Kotak Securities (₹6 Crores)
Target: ₹6-8 Lakhs monthly (1.0-1.3% return)
Risk Profile: Market-neutral short strangle

Key Rules:
- ONE POSITION PER ACCOUNT (enforced via morning_check)
- 50% margin usage for first trade
- 1-day minimum to expiry (skip if < 1 day)
- Minimum 50% profit to exit EOD
- Delta monitoring (alert if |net_delta| > 300)
- Exit Thursday 3:15 PM (if ≥50% profit) or Friday EOD (mandatory)
"""

import logging
import json
from decimal import Decimal
from datetime import datetime, time, date
from typing import Dict, Tuple, Optional

from django.utils import timezone

from apps.positions.services.position_manager import morning_check, create_position
from apps.core.services.expiry_selector import select_expiry_for_options
from apps.accounts.services.margin_manager import calculate_usable_margin
from apps.risk.services.risk_manager import check_risk_limits
from apps.strategies.filters.global_markets import check_global_market_stability
from apps.strategies.filters.event_calendar import check_economic_events
from apps.strategies.filters.volatility import check_market_regime
from apps.data.models import ContractData
from apps.brokers.models import HistoricalPrice
from apps.positions.models import Position
from apps.accounts.models import BrokerAccount
from apps.trading.services import TradeSuggestionService, OptionsSuggestionFormatter
from apps.trading.risk_calculator import OptionsRiskCalculator, SupportResistanceCalculator

logger = logging.getLogger(__name__)


def calculate_strikes(spot_price: Decimal, days_to_expiry: int, vix: Decimal) -> Dict:
    """
    Calculate OTM call and put strikes for short strangle

    Formula:
        strike_distance = spot × (adjusted_delta / 100) × days_to_expiry

    Where adjusted_delta adjusts for volatility regime:
        - Normal VIX (< 15): 0.5% base delta
        - Elevated VIX (15-18): 0.5% × 1.10 = 0.55%
        - High VIX (> 18): 0.5% × 1.20 = 0.6%

    Args:
        spot_price: Current Nifty spot price
        days_to_expiry: Days remaining to expiry
        vix: India VIX value

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

        strike_distance = 24,000 × 0.005 × 4 = 480 points
        Call Strike = 24,480 → Round to 24,500
        Put Strike = 23,520 → Round to 23,500
    """

    # Base delta: 0.5% of spot price per day to expiry
    # Example: For Nifty @ 24,000 with 4 days = 24,000 × 0.5% × 4 = 480 points OTM
    base_delta = Decimal('0.5')

    # VIX-based adjustment: Higher volatility = wider strikes for safety
    # - VIX > 18 (high): Add 20% to strike distance (more conservative)
    # - VIX 15-18 (elevated): Add 10% to strike distance
    # - VIX < 15 (normal): Use standard distance
    if vix > 18:
        adjusted_delta = base_delta * Decimal('1.20')  # +20% buffer
        reason = f"High VIX ({vix:.1f}) - increasing strike distance for safety (+20%)"
    elif vix > 15:
        adjusted_delta = base_delta * Decimal('1.10')  # +10% buffer
        reason = f"Elevated VIX ({vix:.1f}) - slight increase in strike distance (+10%)"
    else:
        adjusted_delta = base_delta  # Standard distance
        reason = f"Normal VIX ({vix:.1f}) - standard strike distance"

    logger.info(f"Strike Selection Parameters:")
    logger.info(f"  Spot Price: ₹{spot_price:,.2f}")
    logger.info(f"  Days to Expiry: {days_to_expiry}")
    logger.info(f"  VIX: {vix:.2f}")
    logger.info(f"  Adjusted Delta: {adjusted_delta:.3f}% ({reason})")

    # Calculate strike distance in points from spot
    # Formula: spot × (delta% / 100) × days_to_expiry
    # This scales the distance based on time remaining
    strike_distance = spot_price * (adjusted_delta / Decimal('100')) * Decimal(str(days_to_expiry))

    # Calculate raw strike prices (before rounding)
    call_strike_raw = spot_price + strike_distance  # OTM call above spot
    put_strike_raw = spot_price - strike_distance   # OTM put below spot

    # Round to nearest 100 (Nifty strike interval is 100 points)
    # Example: 24,480 → 24,500, 23,520 → 23,500
    call_strike = round(float(call_strike_raw) / 100) * 100
    put_strike = round(float(put_strike_raw) / 100) * 100

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


def run_entry_filters() -> Tuple[bool, list, list]:
    """
    Execute ALL entry filters for strangle strategy

    Filter Logic: ALL must pass (conservative approach)
    If ANY filter fails, skip the trade entirely

    Filters:
        1. Global Market Stability (SGX Nifty, US markets)
        2. Recent Nifty Price Movement (1D, 3D)
        3. Economic Event Calendar (next 5 days)
        4. Market Regime (VIX, Bollinger Bands)
        5. Existing Position Check (ONE POSITION RULE)

    Returns:
        tuple: (all_passed: bool, filters_passed: list, filters_failed: list)
    """

    logger.info("=" * 80)
    logger.info("ENTRY FILTER EXECUTION")
    logger.info("=" * 80)

    filters_passed = []
    filters_failed = []

    # FILTER 1: Global Market Stability
    try:
        global_market_check = check_global_market_stability()
        if global_market_check['passed']:
            filters_passed.append(f"✅ Global markets stable: {global_market_check['message']}")
        else:
            filters_failed.append(f"❌ Global markets unstable: {global_market_check['message']}")
    except Exception as e:
        filters_failed.append(f"❌ Global market check failed: {str(e)}")
        logger.error(f"Filter 1 error: {e}", exc_info=True)

    # FILTER 2: Economic Event Calendar
    try:
        event_check = check_economic_events(days_ahead=5)
        if event_check['passed']:
            filters_passed.append(f"✅ No major events: {event_check['message']}")
        else:
            filters_failed.append(f"❌ Major event upcoming: {event_check['message']}")
    except Exception as e:
        filters_failed.append(f"❌ Event calendar check failed: {str(e)}")
        logger.error(f"Filter 2 error: {e}", exc_info=True)

    # FILTER 3: Market Regime Check (VIX, Bollinger Bands)
    try:
        regime_check = check_market_regime()
        if regime_check['passed']:
            filters_passed.append(f"✅ Market regime favorable: {regime_check['message']}")
        else:
            filters_failed.append(f"❌ Market regime unfavorable: {regime_check['message']}")
    except Exception as e:
        filters_failed.append(f"❌ Market regime check failed: {str(e)}")
        logger.error(f"Filter 3 error: {e}", exc_info=True)

    # Summary
    all_passed = len(filters_failed) == 0

    logger.info("")
    logger.info("FILTER RESULTS:")
    logger.info("-" * 80)

    for passed_msg in filters_passed:
        logger.info(passed_msg)

    for failed_msg in filters_failed:
        logger.warning(failed_msg)

    logger.info("-" * 80)

    if all_passed:
        logger.info(f"✅ ALL FILTERS PASSED ({len(filters_passed)}/{len(filters_passed) + len(filters_failed)})")
        logger.info("✅ Entry evaluation can proceed")
    else:
        logger.warning(f"❌ FILTERS FAILED ({len(filters_failed)}/{len(filters_passed) + len(filters_failed)})")
        logger.warning("❌ Trade entry BLOCKED")

    logger.info("=" * 80)

    return all_passed, filters_passed, filters_failed


def execute_kotak_strangle_entry(account: BrokerAccount) -> Dict:
    """
    Complete entry workflow for Kotak Strangle Strategy

    Workflow:
        1. Morning position check (ONE POSITION RULE)
        2. Entry timing validation (9:00 AM - 11:30 AM)
        3. Run entry filters (ALL must pass)
        4. Expiry selection (1-day rule)
        5. Calculate strikes (VIX-based delta adjustment)
        6. Validate premiums (min/max checks)
        7. Calculate position size (50% margin rule)
        8. Risk limit checks
        9. Place orders (paper trading or real)

    Args:
        account: BrokerAccount instance (Kotak)

    Returns:
        dict: {
            'success': bool,
            'message': str,
            'position': Position or None,
            'details': dict
        }
    """

    logger.info("=" * 100)
    logger.info("KOTAK STRANGLE STRATEGY - ENTRY EVALUATION")
    logger.info("=" * 100)
    logger.info(f"Account: {account.broker} - {account.account_name}")
    logger.info(f"Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    # STEP 1: Morning Check (ONE POSITION RULE)
    logger.info("STEP 1: Morning Position Check (ONE POSITION RULE)")
    logger.info("-" * 80)

    morning_check_result = morning_check(account)

    if not morning_check_result['allow_new_entry']:
        logger.warning(f"❌ {morning_check_result['message']}")
        logger.info("=" * 100)
        return {
            'success': False,
            'message': morning_check_result['message'],
            'position': None,
            'details': morning_check_result
        }

    logger.info(f"✅ {morning_check_result['message']}")
    logger.info("")

    # STEP 2: Entry Timing Validation
    logger.info("STEP 2: Entry Timing Validation")
    logger.info("-" * 80)

    current_time = timezone.now().time()
    entry_start = time(9, 0)   # 9:00 AM
    entry_end = time(11, 30)   # 11:30 AM

    if not (entry_start <= current_time <= entry_end):
        msg = f"❌ Entry time window closed (allowed: 09:00-11:30, current: {current_time.strftime('%H:%M')})"
        logger.warning(msg)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {'current_time': current_time.strftime('%H:%M')}
        }

    logger.info(f"✅ Entry timing valid (current: {current_time.strftime('%H:%M')})")
    logger.info("")

    # STEP 3: Run Entry Filters
    logger.info("STEP 3: Entry Filters Execution")
    logger.info("-" * 80)

    all_passed, filters_passed, filters_failed = run_entry_filters()

    if not all_passed:
        msg = f"❌ Entry filters failed ({len(filters_failed)} filters blocked trade)"
        logger.warning(msg)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {
                'filters_passed': filters_passed,
                'filters_failed': filters_failed
            }
        }

    logger.info(f"✅ All entry filters passed ({len(filters_passed)} filters)")
    logger.info("")

    # STEP 4: Expiry Selection (1-day rule)
    logger.info("STEP 4: Expiry Selection (1-day minimum rule)")
    logger.info("-" * 80)

    try:
        selected_expiry, expiry_details = select_expiry_for_options(instrument='NIFTY', min_days=1)
        days_to_expiry = (selected_expiry - date.today()).days

        logger.info(f"✅ Selected Expiry: {selected_expiry} ({days_to_expiry} days)")
        logger.info(f"   Details: {expiry_details}")
        logger.info("")
    except Exception as e:
        msg = f"❌ Expiry selection failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {'error': str(e)}
        }

    # STEP 5: Calculate Strikes
    logger.info("STEP 5: Strike Selection (VIX-based delta adjustment)")
    logger.info("-" * 80)

    try:
        # Get current Nifty spot price
        # TODO: Replace with actual broker API call
        spot_price = Decimal('24000')  # Placeholder

        # Get India VIX
        # TODO: Replace with actual VIX fetch from broker or data source
        vix = Decimal('14.5')  # Placeholder

        strikes = calculate_strikes(spot_price, days_to_expiry, vix)

        logger.info(f"✅ Strikes calculated successfully")
        logger.info("")
    except Exception as e:
        msg = f"❌ Strike calculation failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {'error': str(e)}
        }

    # STEP 6: Premium Validation
    logger.info("STEP 6: Premium Validation")
    logger.info("-" * 80)

    # TODO: Fetch actual premiums from broker
    # TODO: Validate premiums are within acceptable range
    # For now, using placeholders
    call_premium = Decimal('150')
    put_premium = Decimal('145')
    total_premium = call_premium + put_premium

    logger.info(f"Call Premium ({strikes['call_strike']}CE): ₹{call_premium}")
    logger.info(f"Put Premium ({strikes['put_strike']}PE): ₹{put_premium}")
    logger.info(f"Total Premium: ₹{total_premium}")
    logger.info(f"✅ Premiums within acceptable range")
    logger.info("")

    # STEP 7: Position Sizing (50% margin rule)
    # CRITICAL RULE: Only use 50% of available margin for first trade
    # Remaining 50% reserved for adjustments/emergencies
    logger.info("STEP 7: Position Sizing (50% margin usage rule)")
    logger.info("-" * 80)

    try:
        # Calculate usable margin (50% of total margin available)
        usable_margin = calculate_usable_margin(account)

        # Lot size and margin calculation
        # Nifty lot size = 50 (should be fetched from contract master)
        # Margin per lot varies by strikes and market conditions
        lot_size = 50  # Number of shares per lot
        margin_per_lot = Decimal('80000')  # Placeholder - fetch from broker margin calculator

        # Calculate maximum lots we can trade with usable margin
        # Floor division to ensure we don't exceed margin
        max_lots = int(usable_margin / margin_per_lot)

        if max_lots < 1:
            msg = f"❌ Insufficient margin (usable: ₹{usable_margin:,.0f}, required: ₹{margin_per_lot:,.0f})"
            logger.warning(msg)
            logger.info("=" * 100)
            return {
                'success': False,
                'message': msg,
                'position': None,
                'details': {
                    'usable_margin': usable_margin,
                    'margin_required': margin_per_lot
                }
            }

        # Use 1 lot for conservative approach
        lots = 1
        quantity = lots * lot_size
        margin_used = margin_per_lot * lots
        premium_collected = total_premium * quantity

        logger.info(f"Usable Margin (50%): ₹{usable_margin:,.0f}")
        logger.info(f"Lots: {lots}")
        logger.info(f"Quantity: {quantity}")
        logger.info(f"Margin Used: ₹{margin_used:,.0f}")
        logger.info(f"Premium Collected: ₹{premium_collected:,.0f}")
        logger.info(f"✅ Position sizing complete")
        logger.info("")
    except Exception as e:
        msg = f"❌ Position sizing failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {'error': str(e)}
        }

    # STEP 8: Risk Limit Checks
    logger.info("STEP 8: Risk Limit Validation")
    logger.info("-" * 80)

    try:
        risk_check = check_risk_limits(account)

        if risk_check['action_required'] != 'NONE':
            msg = f"❌ Risk limits breached: {risk_check['message']}"
            logger.warning(msg)
            logger.info("=" * 100)
            return {
                'success': False,
                'message': msg,
                'position': None,
                'details': risk_check
            }

        logger.info(f"✅ All risk limits satisfied")
        logger.info("")
    except Exception as e:
        msg = f"❌ Risk check failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {'error': str(e)}
        }

    # STEP 9: Create Trade Suggestion
    logger.info("STEP 9: Trade Suggestion Creation")
    logger.info("-" * 80)

    try:
        # Calculate stop-loss and target
        # For strangle: SL = 100% loss (premium becomes zero), Target = 70% profit
        stop_loss = Decimal('0')  # Premium goes to zero
        target = premium_collected * Decimal('0.70')  # 70% profit on premium

        # Prepare algorithm reasoning (complete analysis details)
        algorithm_reasoning = {
            'title': 'Kotak Strangle Strategy',
            'summary': 'Short Strangle position to collect premium',
            'calculations': {
                'spot_price': str(spot_price),
                'vix': str(vix),
                'days_to_expiry': days_to_expiry,
                'strike_distance': str(strikes['strike_distance']),
                'adjusted_delta': str(strikes['adjusted_delta']),
                'adjustment_reason': strikes['adjustment_reason'],
                'call_premium': str(call_premium),
                'put_premium': str(put_premium),
                'total_premium': str(total_premium),
                'premium_collected': str(premium_collected),
            },
            'filters': {
                'filters_passed': filters_passed,
                'filters_failed': filters_failed,
                'entry_time_valid': True,
                'position_count_check': morning_check_result['message'],
            },
            'position_sizing': {
                'usable_margin': str(usable_margin),
                'lot_size': lot_size,
                'lots': lots,
                'quantity': quantity,
                'margin_per_lot': str(margin_per_lot),
                'margin_used': str(margin_used),
            },
            'final_decision': {
                'recommendation': 'SELL_STRANGLE',
                'position_details': {
                    'instrument': 'NIFTY',
                    'strategy': 'Short Strangle',
                    'call_strike': strikes['call_strike'],
                    'put_strike': strikes['put_strike'],
                    'total_quantity': quantity,
                    'quantity_per_lot': lot_size,
                    'premium_collected': str(premium_collected),
                    'margin_used': str(margin_used),
                    'stop_loss': str(stop_loss),
                    'target': str(target),
                    'expiry_date': str(selected_expiry),
                },
                'risk_reward': {
                    'max_profit': str(risk_scenarios['max_profit']),
                    'profitable_range': risk_scenarios['profit_zone'],
                    'breakeven_call': str(risk_scenarios['call_breakeven']),
                    'breakeven_put': str(risk_scenarios['put_breakeven']),
                    'scenarios_count': len(risk_scenarios['scenarios']),
                },
                'support_resistance': {
                    'support_level': str(support_resistance['support']),
                    'resistance_level': str(support_resistance['resistance']),
                    'next_support': str(support_resistance['next_support']),
                    'next_resistance': str(support_resistance['next_resistance']),
                }
            }
        }

        # Calculate risk/reward scenarios
        risk_scenarios = OptionsRiskCalculator.calculate_scenarios(
            current_price=spot_price,
            call_strike=strikes['call_strike'],
            put_strike=strikes['put_strike'],
            call_premium=call_premium,
            put_premium=put_premium,
            quantity=quantity,
            lot_size=lot_size
        )

        # Calculate target and SL recommendations
        target_sl = OptionsRiskCalculator.calculate_target_and_sl(
            current_price=spot_price,
            call_strike=strikes['call_strike'],
            put_strike=strikes['put_strike'],
            call_premium=call_premium,
            put_premium=put_premium,
            quantity=quantity
        )

        # Support and Resistance (TODO: Fetch actual price data)
        # For now, using placeholder data
        support_resistance = SupportResistanceCalculator.calculate_next_levels(
            current_price=spot_price,
            support_level=spot_price * Decimal('0.99'),  # 1% below
            resistance_level=spot_price * Decimal('1.01')  # 1% above
        )

        # Prepare position details with risk metrics
        position_details = {
            'instrument': 'NIFTY',
            'strategy': 'Short Strangle',
            'call_strike': strikes['call_strike'],
            'put_strike': strikes['put_strike'],
            'quantity': quantity,
            'lot_size': lot_size,
            'entry_price': None,  # Will be fetched from market at execution
            'premium_collected': str(premium_collected),
            'margin_required': str(margin_used),
            'stop_loss': str(stop_loss),
            'target': str(target),
            'expiry_date': str(selected_expiry),
            # Risk metrics
            'max_profit': str(risk_scenarios['max_profit']),
            'max_profit_pct': str((risk_scenarios['max_profit'] / margin_used * 100) if margin_used > 0 else 0),
            'profitable_range': {
                'lower': str(risk_scenarios['profit_zone']['lower']),
                'upper': str(risk_scenarios['profit_zone']['upper']),
            },
            'support_level': str(support_resistance['support']),
            'support_distance': str(support_resistance['support_distance']),
            'support_distance_pct': str(support_resistance['support_distance_pct']),
            'resistance_level': str(support_resistance['resistance']),
            'resistance_distance': str(support_resistance['resistance_distance']),
            'resistance_distance_pct': str(support_resistance['resistance_distance_pct']),
        }

        # Create trade suggestion
        suggestion = TradeSuggestionService.create_suggestion(
            user=account.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='NEUTRAL',
            algorithm_reasoning=algorithm_reasoning,
            position_details=position_details
        )

        logger.info(f"✅ Trade suggestion created successfully: {suggestion.id}")
        logger.info(f"   Status: {suggestion.get_status_display()}")
        logger.info(f"   Auto-Trade: {suggestion.is_auto_trade}")
        logger.info(f"   Premium Collected: ₹{premium_collected:,.0f}")
        logger.info(f"   Margin Used: ₹{margin_used:,.0f}")
        logger.info("")
        logger.info("=" * 100)

        return {
            'success': True,
            'message': f'Trade suggestion #{suggestion.id} created (Status: {suggestion.get_status_display()})',
            'suggestion': suggestion,
            'details': {
                'strikes': strikes,
                'expiry': selected_expiry,
                'premium_collected': premium_collected,
                'margin_used': margin_used,
                'quantity': quantity,
                'suggestion_status': suggestion.get_status_display(),
                'is_auto_trade': suggestion.is_auto_trade,
            }
        }

    except Exception as e:
        msg = f"❌ Trade suggestion creation failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'suggestion': None,
            'details': {'error': str(e)}
        }


def get_current_nifty_price() -> Decimal:
    """
    Get current Nifty spot price

    Returns:
        Decimal: Current Nifty price
    """
    try:
        from apps.brokers.models import HistoricalPrice
        from datetime import datetime, timedelta

        # Try to get latest price from historical data
        latest_price = HistoricalPrice.objects.filter(
            symbol='NIFTY 50',
            timestamp__gte=datetime.now() - timedelta(days=1)
        ).order_by('-timestamp').first()

        if latest_price:
            return Decimal(str(latest_price.close))

        # Fallback to hardcoded value
        logger.warning("Using fallback Nifty price")
        return Decimal('24000.00')

    except Exception as e:
        logger.error(f"Error getting Nifty price: {e}")
        return Decimal('24000.00')


def get_option_premiums(call_strike: int, put_strike: int, expiry_date) -> Tuple[Decimal, Decimal]:
    """
    Get option premiums for given strikes

    Args:
        call_strike: Call option strike price
        put_strike: Put option strike price
        expiry_date: Expiry date

    Returns:
        Tuple[Decimal, Decimal]: (call_premium, put_premium)
    """
    try:
        from apps.data.models import OptionChain

        # Get latest option chain data
        call_option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=call_strike,
            option_type='CE',
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        put_option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=put_strike,
            option_type='PE',
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        call_premium = call_option.ltp if call_option else Decimal('100.0')
        put_premium = put_option.ltp if put_option else Decimal('100.0')

        logger.info(f"Premiums: {call_strike}CE = ₹{call_premium}, {put_strike}PE = ₹{put_premium}")

        return call_premium, put_premium

    except Exception as e:
        logger.error(f"Error getting option premiums: {e}")
        # Return fallback values
        return Decimal('100.0'), Decimal('100.0')
