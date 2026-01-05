"""
Kotak Broken Iron Condor Strategy

Strategy: Similar to Nifty Strangle but with protective put (insurance)
         - Sell OTM Call (same as strangle)
         - Sell OTM Put (same as strangle)
         - Buy further OTM Put as insurance (new addition)

Account: Kotak Securities
Risk Profile: Defined risk on downside (unlike unlimited risk strangle)

Insurance Put Calculation:
    - Risk Budget = Max Profit × Risk Multiplier (default 2.0)
    - Insurance Strike = Put Strike - (Risk Budget / Lot Size)
    - The insurance put caps maximum loss on the downside

Key Differences from Strangle:
    - 3 legs instead of 2
    - Defined risk on put side
    - Slightly reduced max profit (due to insurance cost)
    - Better risk/reward profile

Configurable Parameters:
    - risk_multiplier: How much risk to take (default 2.0 = twice the max profit)
    - Can be adjusted via UI before execution
"""

import logging
from decimal import Decimal
from datetime import date
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# Default risk multiplier for insurance calculation
DEFAULT_RISK_MULTIPLIER = Decimal('2.0')


def calculate_strikes(spot_price: Decimal, days_to_expiry: int, vix: Decimal) -> Dict:
    """
    Calculate OTM call and put strikes for short strangle (same as strangle)

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
    """

    # Base delta: 0.5% of spot price per day to expiry
    base_delta = Decimal('0.5')

    # VIX-based adjustment: Higher volatility = wider strikes for safety
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
    strike_distance = spot_price * (adjusted_delta / Decimal('100')) * Decimal(str(days_to_expiry))

    # Calculate raw strike prices (before rounding)
    call_strike_raw = spot_price + strike_distance  # OTM call above spot
    put_strike_raw = spot_price - strike_distance   # OTM put below spot

    # Round to nearest 100 (Nifty strike interval is 100 points)
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


def calculate_insurance_strike(
    put_strike: int,
    max_profit: Decimal,
    risk_multiplier: Decimal,
    lot_size: int,
    quantity: int
) -> Dict:
    """
    Calculate the insurance put strike based on risk budget

    Insurance Logic:
        - Risk Budget = Max Profit × Risk Multiplier
        - The insurance put should be bought at a strike that limits
          our maximum loss to the risk budget

    For a broken iron condor:
        - We sell a put at put_strike
        - We buy a put at insurance_strike (further OTM)
        - Maximum loss on put side = (put_strike - insurance_strike) × quantity - premium received

    To achieve Risk Budget as max loss:
        insurance_strike = put_strike - (risk_budget / quantity)

    Args:
        put_strike: The sold put strike
        max_profit: Maximum profit from premium collected (call + put sell)
        risk_multiplier: How many times the max profit to risk (default 2.0)
        lot_size: Nifty lot size (50)
        quantity: Total quantity being traded

    Returns:
        dict: {
            'insurance_strike': int,
            'risk_budget': Decimal,
            'estimated_insurance_premium': Decimal,
            'max_loss_on_put_side': Decimal
        }
    """

    # Calculate risk budget
    risk_budget = max_profit * risk_multiplier

    # Calculate how far below put_strike the insurance should be
    # This is the maximum points we can lose per share
    max_loss_per_share = risk_budget / Decimal(str(quantity))

    # Insurance strike is that far below the sold put strike
    insurance_strike_raw = Decimal(str(put_strike)) - max_loss_per_share

    # Round to nearest 100 (Nifty strike interval)
    insurance_strike = round(float(insurance_strike_raw) / 100) * 100

    # Ensure insurance strike is at least 100 points below sold put
    if insurance_strike >= put_strike:
        insurance_strike = put_strike - 100

    # Calculate actual max loss with rounded strike
    actual_spread = put_strike - insurance_strike
    max_loss_on_put_side = Decimal(str(actual_spread)) * Decimal(str(quantity))

    logger.info(f"Insurance Strike Calculation:")
    logger.info(f"  Sold Put Strike: {put_strike}")
    logger.info(f"  Max Profit (Premium): ₹{max_profit:,.2f}")
    logger.info(f"  Risk Multiplier: {risk_multiplier}x")
    logger.info(f"  Risk Budget: ₹{risk_budget:,.2f}")
    logger.info(f"  Insurance Strike (OTM Put Buy): {insurance_strike}")
    logger.info(f"  Spread Width: {actual_spread} points")
    logger.info(f"  Max Loss on Put Side: ₹{max_loss_on_put_side:,.2f}")

    return {
        'insurance_strike': int(insurance_strike),
        'risk_budget': risk_budget,
        'spread_width': actual_spread,
        'max_loss_on_put_side': max_loss_on_put_side,
        'risk_multiplier_used': risk_multiplier
    }


def get_insurance_strike_options(
    put_strike: int,
    max_profit: Decimal,
    quantity: int,
    spot_price: Decimal
) -> list:
    """
    Generate multiple insurance strike options for user selection

    Provides 3-4 options with different risk/reward profiles:
        - Conservative (1.5x risk): Closer insurance, lower max loss
        - Moderate (2.0x risk): Balanced approach
        - Aggressive (3.0x risk): Wider spread, higher max loss but cheaper insurance

    Args:
        put_strike: The sold put strike
        max_profit: Maximum profit from premium
        quantity: Total quantity
        spot_price: Current spot price

    Returns:
        list: List of insurance options with details
    """

    risk_options = [
        {'multiplier': Decimal('1.5'), 'label': 'Conservative'},
        {'multiplier': Decimal('2.0'), 'label': 'Moderate (Recommended)'},
        {'multiplier': Decimal('2.5'), 'label': 'Slightly Aggressive'},
        {'multiplier': Decimal('3.0'), 'label': 'Aggressive'},
    ]

    options = []

    for opt in risk_options:
        insurance_data = calculate_insurance_strike(
            put_strike=put_strike,
            max_profit=max_profit,
            risk_multiplier=opt['multiplier'],
            lot_size=50,  # Nifty lot size
            quantity=quantity
        )

        # Calculate distance from spot
        distance_from_spot = spot_price - Decimal(str(insurance_data['insurance_strike']))
        distance_pct = (distance_from_spot / spot_price) * 100

        options.append({
            'label': opt['label'],
            'risk_multiplier': float(opt['multiplier']),
            'insurance_strike': insurance_data['insurance_strike'],
            'spread_width': insurance_data['spread_width'],
            'max_loss_on_put_side': float(insurance_data['max_loss_on_put_side']),
            'risk_budget': float(insurance_data['risk_budget']),
            'distance_from_spot': float(distance_from_spot),
            'distance_from_spot_pct': float(distance_pct),
            # Estimated premium will be fetched from market data
            'estimated_insurance_premium': None
        })

    return options


def run_entry_filters() -> Tuple[bool, list, list]:
    """
    Execute ALL entry filters for broken iron condor strategy
    (Same filters as strangle - conservative approach)

    Filter Logic: ALL must pass
    If ANY filter fails, skip the trade entirely

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


def calculate_broken_iron_condor_scenarios(
    current_price: Decimal,
    call_strike: int,
    put_strike: int,
    insurance_strike: int,
    call_premium: Decimal,
    put_premium: Decimal,
    insurance_premium: Decimal,
    quantity: int,
    lot_size: int
) -> Dict:
    """
    Calculate profit/loss scenarios for broken iron condor

    Broken Iron Condor P&L:
        - Max profit = Call Premium + Put Premium - Insurance Premium
        - Max loss on upside = Unlimited (but managed by SL)
        - Max loss on downside = (Put Strike - Insurance Strike) × Quantity - Net Premium

    Args:
        current_price: Current spot price
        call_strike: Sold call strike
        put_strike: Sold put strike
        insurance_strike: Bought put strike (insurance)
        call_premium: Premium received for call
        put_premium: Premium received for put
        insurance_premium: Premium paid for insurance put
        quantity: Total quantity
        lot_size: Lot size

    Returns:
        dict: Comprehensive P&L scenarios
    """

    net_premium = call_premium + put_premium - insurance_premium
    max_profit = net_premium * quantity

    # Max loss on put side is capped
    put_spread_width = put_strike - insurance_strike
    max_loss_put_side = (Decimal(str(put_spread_width)) * quantity) - (net_premium * quantity)

    # Breakeven levels
    call_breakeven = Decimal(str(call_strike)) + net_premium
    put_breakeven = Decimal(str(put_strike)) - net_premium

    scenarios = []

    # Current price (0% move)
    scenarios.append({
        'move_pct': 0,
        'move_direction': 'NEUTRAL',
        'target_price': current_price,
        'profit_loss': max_profit,
        'description': 'Current price (max profit zone)'
    })

    # Upside scenarios
    for move_pct in [0.5, 1, 2, 5, 10]:
        target_price = current_price * (Decimal('1') + Decimal(str(move_pct)) / Decimal('100'))

        # For short call, loss increases as price goes up
        call_loss = (target_price - Decimal(str(call_strike))) * quantity if target_price > call_strike else Decimal('0')
        total_pl = (net_premium * quantity) - call_loss

        scenarios.append({
            'move_pct': move_pct,
            'move_direction': 'UP',
            'target_price': float(target_price),
            'profit_loss': float(total_pl),
            'description': f'Nifty up {move_pct}% to {target_price:.0f}'
        })

    # Downside scenarios
    for move_pct in [0.5, 1, 2, 5, 10]:
        target_price = current_price * (Decimal('1') - Decimal(str(move_pct)) / Decimal('100'))

        # For short put with insurance, loss is capped
        if target_price >= put_strike:
            # Above put strike - keep full premium
            put_loss = Decimal('0')
        elif target_price >= insurance_strike:
            # Between put strikes - loss on short put
            put_loss = (Decimal(str(put_strike)) - target_price) * quantity
        else:
            # Below insurance strike - loss is capped
            put_loss = Decimal(str(put_spread_width)) * quantity

        total_pl = (net_premium * quantity) - put_loss

        scenarios.append({
            'move_pct': -move_pct,
            'move_direction': 'DOWN',
            'target_price': float(target_price),
            'profit_loss': float(total_pl),
            'is_loss_capped': target_price < insurance_strike,
            'description': f'Nifty down {move_pct}% to {target_price:.0f}'
        })

    return {
        'strategy': 'Broken Iron Condor',
        'max_profit': float(max_profit),
        'max_loss_put_side': float(max_loss_put_side),
        'max_loss_call_side': 'Unlimited (managed by SL)',
        'net_premium_per_share': float(net_premium),
        'call_breakeven': float(call_breakeven),
        'put_breakeven': float(put_breakeven),
        'profit_zone': {
            'lower': float(put_breakeven),
            'upper': float(call_breakeven),
            'description': f'Profitable range: {put_breakeven:.0f} to {call_breakeven:.0f}'
        },
        'insurance_details': {
            'insurance_strike': insurance_strike,
            'put_spread_width': put_spread_width,
            'protection_starts_at': insurance_strike,
            'max_loss_capped_at': float(max_loss_put_side)
        },
        'scenarios': scenarios
    }


def execute_kotak_broken_iron_condor_entry(
    account: "BrokerAccount",
    risk_multiplier: Decimal = DEFAULT_RISK_MULTIPLIER
) -> Dict:
    """
    Complete entry workflow for Kotak Broken Iron Condor Strategy

    Workflow:
        1. Morning position check (ONE POSITION RULE)
        2. Entry timing validation (9:00 AM - 11:30 AM)
        3. Run entry filters (ALL must pass)
        4. Expiry selection (1-day rule)
        5. Calculate strikes (VIX-based delta adjustment)
        6. Calculate insurance strike (based on risk_multiplier)
        7. Validate premiums (min/max checks)
        8. Calculate position size (50% margin rule)
        9. Risk limit checks
        10. Create trade suggestion (3 legs)

    Args:
        account: BrokerAccount instance (Kotak)
        risk_multiplier: How many times max profit to risk (default 2.0)

    Returns:
        dict: {
            'success': bool,
            'message': str,
            'suggestion': TradeSuggestion or None,
            'insurance_options': list (if success, for UI selection),
            'details': dict
        }
    """

    logger.info("=" * 100)
    logger.info("KOTAK BROKEN IRON CONDOR STRATEGY - ENTRY EVALUATION")
    logger.info("=" * 100)
    logger.info(f"Account: {account.broker} - {account.account_name}")
    logger.info(f"Risk Multiplier: {risk_multiplier}x")
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
            'suggestion': None,
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
            'suggestion': None,
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
            'suggestion': None,
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
            'suggestion': None,
            'details': {'error': str(e)}
        }

    # STEP 5: Calculate Strikes
    logger.info("STEP 5: Strike Selection (VIX-based delta adjustment)")
    logger.info("-" * 80)

    try:
        # Get current Nifty spot price
        spot_price = get_current_nifty_price()

        # Get India VIX
        vix = get_current_vix()

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
            'suggestion': None,
            'details': {'error': str(e)}
        }

    # STEP 6: Position Sizing (50% margin rule)
    logger.info("STEP 6: Position Sizing (50% margin usage rule)")
    logger.info("-" * 80)

    try:
        usable_margin = calculate_usable_margin(account)
        lot_size = 50  # Nifty lot size
        margin_per_lot = Decimal('80000')  # Placeholder

        max_lots = int(usable_margin / margin_per_lot)

        if max_lots < 1:
            msg = f"❌ Insufficient margin (usable: ₹{usable_margin:,.0f}, required: ₹{margin_per_lot:,.0f})"
            logger.warning(msg)
            logger.info("=" * 100)
            return {
                'success': False,
                'message': msg,
                'suggestion': None,
                'details': {
                    'usable_margin': usable_margin,
                    'margin_required': margin_per_lot
                }
            }

        lots = 1  # Conservative approach
        quantity = lots * lot_size
        margin_used = margin_per_lot * lots

        logger.info(f"✅ Position sizing complete")
        logger.info(f"   Lots: {lots}, Quantity: {quantity}")
        logger.info("")
    except Exception as e:
        msg = f"❌ Position sizing failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'suggestion': None,
            'details': {'error': str(e)}
        }

    # STEP 7: Get Premiums and Calculate Insurance
    logger.info("STEP 7: Premium Validation & Insurance Calculation")
    logger.info("-" * 80)

    try:
        # Get option premiums
        call_premium, put_premium = get_option_premiums(
            strikes['call_strike'],
            strikes['put_strike'],
            selected_expiry
        )

        total_premium = call_premium + put_premium
        max_profit_from_strangle = total_premium * quantity

        logger.info(f"Call Premium ({strikes['call_strike']}CE): ₹{call_premium}")
        logger.info(f"Put Premium ({strikes['put_strike']}PE): ₹{put_premium}")
        logger.info(f"Total Premium (Strangle): ₹{total_premium}")
        logger.info(f"Max Profit from Strangle: ₹{max_profit_from_strangle:,.2f}")

        # Calculate insurance options
        insurance_options = get_insurance_strike_options(
            put_strike=strikes['put_strike'],
            max_profit=max_profit_from_strangle,
            quantity=quantity,
            spot_price=spot_price
        )

        # Get insurance premiums for each option
        for opt in insurance_options:
            ins_premium = get_put_option_premium(opt['insurance_strike'], selected_expiry)
            opt['insurance_premium'] = float(ins_premium)
            opt['net_premium'] = float(total_premium - ins_premium)
            opt['adjusted_max_profit'] = float((total_premium - ins_premium) * quantity)

        logger.info("")
        logger.info("Insurance Options Available:")
        for opt in insurance_options:
            logger.info(f"  {opt['label']}: Strike {opt['insurance_strike']}, "
                       f"Premium ₹{opt['insurance_premium']:.2f}, "
                       f"Max Loss ₹{opt['max_loss_on_put_side']:,.2f}")

        logger.info("")

    except Exception as e:
        msg = f"❌ Premium/Insurance calculation failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'suggestion': None,
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
                'suggestion': None,
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
            'suggestion': None,
            'details': {'error': str(e)}
        }

    # STEP 9: Prepare trade suggestion with insurance options for UI
    logger.info("STEP 9: Trade Suggestion Preparation")
    logger.info("-" * 80)

    # Use default (moderate) insurance option for initial suggestion
    default_insurance = next(
        (opt for opt in insurance_options if 'Recommended' in opt['label']),
        insurance_options[1]  # Fallback to second option (moderate)
    )

    # Calculate risk scenarios with default insurance
    risk_scenarios = calculate_broken_iron_condor_scenarios(
        current_price=spot_price,
        call_strike=strikes['call_strike'],
        put_strike=strikes['put_strike'],
        insurance_strike=default_insurance['insurance_strike'],
        call_premium=call_premium,
        put_premium=put_premium,
        insurance_premium=Decimal(str(default_insurance['insurance_premium'])),
        quantity=quantity,
        lot_size=lot_size
    )

    # Support and Resistance
    support_resistance = SupportResistanceCalculator.calculate_next_levels(
        current_price=spot_price,
        support_level=spot_price * Decimal('0.99'),
        resistance_level=spot_price * Decimal('1.01')
    )

    # Prepare algorithm reasoning
    algorithm_reasoning = {
        'title': 'Kotak Broken Iron Condor Strategy',
        'summary': 'Short Strangle with protective put (insurance) for defined downside risk',
        'strategy_type': 'BROKEN_IRON_CONDOR',
        'calculations': {
            'spot_price': str(spot_price),
            'vix': str(vix),
            'days_to_expiry': days_to_expiry,
            'strike_distance': str(strikes['strike_distance']),
            'adjusted_delta': str(strikes['adjusted_delta']),
            'adjustment_reason': strikes['adjustment_reason'],
            'call_premium': str(call_premium),
            'put_premium': str(put_premium),
            'total_strangle_premium': str(total_premium),
        },
        'insurance': {
            'selected_option': default_insurance['label'],
            'insurance_strike': default_insurance['insurance_strike'],
            'insurance_premium': default_insurance['insurance_premium'],
            'risk_multiplier': default_insurance['risk_multiplier'],
            'max_loss_on_put_side': default_insurance['max_loss_on_put_side'],
            'available_options': insurance_options,
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
        'risk_scenarios': risk_scenarios,
        'support_resistance': {
            'support_level': str(support_resistance['support']),
            'resistance_level': str(support_resistance['resistance']),
        }
    }

    # Position details (3 legs)
    position_details = {
        'instrument': 'NIFTY',
        'strategy': 'Broken Iron Condor',
        'legs': [
            {
                'leg_number': 1,
                'action': 'SELL',
                'option_type': 'CE',
                'strike': strikes['call_strike'],
                'premium': str(call_premium),
                'quantity': quantity,
            },
            {
                'leg_number': 2,
                'action': 'SELL',
                'option_type': 'PE',
                'strike': strikes['put_strike'],
                'premium': str(put_premium),
                'quantity': quantity,
            },
            {
                'leg_number': 3,
                'action': 'BUY',
                'option_type': 'PE',
                'strike': default_insurance['insurance_strike'],
                'premium': str(default_insurance['insurance_premium']),
                'quantity': quantity,
                'purpose': 'Insurance'
            }
        ],
        'call_strike': strikes['call_strike'],
        'put_strike': strikes['put_strike'],
        'insurance_strike': default_insurance['insurance_strike'],
        'quantity': quantity,
        'lot_size': lot_size,
        'net_premium': str(default_insurance['net_premium']),
        'adjusted_max_profit': str(default_insurance['adjusted_max_profit']),
        'max_loss_on_put_side': str(default_insurance['max_loss_on_put_side']),
        'margin_required': str(margin_used),
        'expiry_date': str(selected_expiry),
        # Configurable parameters for UI editing
        'configurable': {
            'risk_multiplier': {
                'current': default_insurance['risk_multiplier'],
                'options': [opt['risk_multiplier'] for opt in insurance_options],
                'description': 'Risk multiplier for insurance calculation'
            },
            'insurance_strike': {
                'current': default_insurance['insurance_strike'],
                'options': [opt['insurance_strike'] for opt in insurance_options],
                'description': 'Insurance put strike price'
            }
        }
    }

    try:
        # Create trade suggestion
        from apps.trading.models import TradeSuggestion
        suggestion = TradeSuggestion.objects.create(
            user=account.user,
            strategy='kotak_broken_iron_condor',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='NEUTRAL',
            algorithm_reasoning=algorithm_reasoning,
            position_details=position_details
        )

        logger.info(f"✅ Trade suggestion created: {suggestion.id}")
        logger.info(f"   Status: {suggestion.get_status_display()}")
        logger.info(f"   Legs: 3 (Sell CE, Sell PE, Buy PE Insurance)")
        logger.info(f"   Net Premium: ₹{default_insurance['net_premium'] * quantity:,.2f}")
        logger.info(f"   Max Loss (Put Side): ₹{default_insurance['max_loss_on_put_side']:,.2f}")
        logger.info("")
        logger.info("=" * 100)

        return {
            'success': True,
            'message': f'Trade suggestion #{suggestion.id} created - Review insurance options',
            'suggestion': suggestion,
            'insurance_options': insurance_options,
            'details': {
                'strikes': strikes,
                'expiry': selected_expiry,
                'default_insurance': default_insurance,
                'quantity': quantity,
                'suggestion_status': suggestion.get_status_display(),
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


def update_insurance_selection(suggestion_id: int, risk_multiplier: float) -> Dict:
    """
    Update the insurance strike based on user's risk multiplier selection from UI

    This is called when user adjusts the risk slider in the UI

    Args:
        suggestion_id: TradeSuggestion ID
        risk_multiplier: New risk multiplier selected by user

    Returns:
        dict: Updated suggestion details
    """
    from apps.trading.models import TradeSuggestion

    try:
        suggestion = TradeSuggestion.objects.get(id=suggestion_id)

        if suggestion.status != 'SUGGESTED':
            return {
                'success': False,
                'message': f'Cannot modify - suggestion status is {suggestion.status}'
            }

        # Get existing data
        reasoning = suggestion.algorithm_reasoning
        position_details = suggestion.position_details
        insurance_options = reasoning.get('insurance', {}).get('available_options', [])

        # Find the matching insurance option
        selected_option = None
        for opt in insurance_options:
            if abs(opt['risk_multiplier'] - risk_multiplier) < 0.01:
                selected_option = opt
                break

        if not selected_option:
            return {
                'success': False,
                'message': f'Invalid risk multiplier: {risk_multiplier}'
            }

        # Update reasoning
        reasoning['insurance']['selected_option'] = selected_option['label']
        reasoning['insurance']['insurance_strike'] = selected_option['insurance_strike']
        reasoning['insurance']['insurance_premium'] = selected_option['insurance_premium']
        reasoning['insurance']['risk_multiplier'] = selected_option['risk_multiplier']
        reasoning['insurance']['max_loss_on_put_side'] = selected_option['max_loss_on_put_side']

        # Update position details
        position_details['insurance_strike'] = selected_option['insurance_strike']
        position_details['net_premium'] = str(selected_option['net_premium'])
        position_details['adjusted_max_profit'] = str(selected_option['adjusted_max_profit'])
        position_details['max_loss_on_put_side'] = str(selected_option['max_loss_on_put_side'])

        # Update leg 3 (insurance)
        if len(position_details.get('legs', [])) >= 3:
            position_details['legs'][2]['strike'] = selected_option['insurance_strike']
            position_details['legs'][2]['premium'] = str(selected_option['insurance_premium'])

        # Update configurable
        position_details['configurable']['risk_multiplier']['current'] = selected_option['risk_multiplier']
        position_details['configurable']['insurance_strike']['current'] = selected_option['insurance_strike']

        # Save updates
        suggestion.algorithm_reasoning = reasoning
        suggestion.position_details = position_details
        suggestion.save()

        logger.info(f"Updated suggestion #{suggestion_id} with insurance strike {selected_option['insurance_strike']}")

        return {
            'success': True,
            'message': f'Insurance updated to {selected_option["label"]}',
            'updated_details': {
                'insurance_strike': selected_option['insurance_strike'],
                'insurance_premium': selected_option['insurance_premium'],
                'net_premium': selected_option['net_premium'],
                'max_loss_on_put_side': selected_option['max_loss_on_put_side'],
                'risk_multiplier': selected_option['risk_multiplier']
            }
        }

    except TradeSuggestion.DoesNotExist:
        return {
            'success': False,
            'message': f'Suggestion #{suggestion_id} not found'
        }
    except Exception as e:
        logger.error(f"Error updating insurance selection: {e}", exc_info=True)
        return {
            'success': False,
            'message': str(e)
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

        latest_price = HistoricalPrice.objects.filter(
            symbol='NIFTY 50',
            timestamp__gte=datetime.now() - timedelta(days=1)
        ).order_by('-timestamp').first()

        if latest_price:
            return Decimal(str(latest_price.close))

        logger.warning("Using fallback Nifty price")
        return Decimal('24000.00')

    except Exception as e:
        logger.error(f"Error getting Nifty price: {e}")
        return Decimal('24000.00')


def get_current_vix() -> Decimal:
    """
    Get current India VIX value

    Returns:
        Decimal: Current VIX value
    """
    try:
        from apps.brokers.models import HistoricalPrice
        from datetime import datetime, timedelta

        latest_vix = HistoricalPrice.objects.filter(
            symbol='INDIA VIX',
            timestamp__gte=datetime.now() - timedelta(days=1)
        ).order_by('-timestamp').first()

        if latest_vix:
            return Decimal(str(latest_vix.close))

        logger.warning("Using fallback VIX value")
        return Decimal('14.50')

    except Exception as e:
        logger.error(f"Error getting VIX: {e}")
        return Decimal('14.50')


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
        return Decimal('100.0'), Decimal('100.0')


def get_put_option_premium(strike: int, expiry_date) -> Decimal:
    """
    Get put option premium for insurance strike

    Args:
        strike: Put option strike price
        expiry_date: Expiry date

    Returns:
        Decimal: Put premium
    """
    try:
        from apps.data.models import OptionChain

        put_option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=strike,
            option_type='PE',
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        if put_option:
            return Decimal(str(put_option.ltp))

        # Estimate premium based on distance from ATM
        # Further OTM puts are cheaper
        logger.warning(f"Using estimated premium for {strike}PE")
        return Decimal('50.0')

    except Exception as e:
        logger.error(f"Error getting put premium: {e}")
        return Decimal('50.0')
