"""
Kotak Broken Iron Condor Strategy

Strategy: Similar to Nifty Strangle but with protective put (insurance)
         - Sell OTM Call (same as strangle)
         - Sell OTM Put (same as strangle)
         - Buy further OTM Put as insurance (new addition)

Account: Kotak Securities
Risk Profile: Defined risk on downside (unlike unlimited risk strangle)

Insurance Put Calculation:
    - Risk Budget = Max Profit * Risk Multiplier (default 2.0)
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
from datetime import time
from typing import Dict, Tuple, List


from apps.strategies.core.base_strategy import BaseStrategy
from apps.strategies.core.result_types import StrategyConfig
from apps.strategies.shared.strike_calculator import calculate_strangle_strikes
from apps.strategies.shared.market_data import get_nifty_price, get_vix, get_option_premiums, get_put_premium
from apps.trading.risk_calculator import SupportResistanceCalculator

logger = logging.getLogger(__name__)

# Default risk multiplier for insurance calculation
DEFAULT_RISK_MULTIPLIER = Decimal('2.0')


class KotakBrokenIronCondorStrategy(BaseStrategy):
    """
    Broken Iron Condor strategy - strangle with protective put.

    Unique Logic:
    - Insurance put calculation based on risk multiplier
    - 3-leg position (sell CE, sell PE, buy PE insurance)
    - Defined max loss on downside
    """

    def __init__(self, account, risk_multiplier: Decimal = DEFAULT_RISK_MULTIPLIER):
        """
        Initialize strategy with account and risk multiplier.

        Args:
            account: BrokerAccount instance
            risk_multiplier: How many times max profit to risk (default 2.0)
        """
        self.risk_multiplier = risk_multiplier
        super().__init__(account)

    def get_config(self) -> StrategyConfig:
        """Return strategy configuration."""
        return StrategyConfig(
            name="Kotak Broken Iron Condor Strategy",
            strategy_type='OPTIONS',
            direction='NEUTRAL',
            entry_start_time=time(9, 0),
            entry_end_time=time(11, 30),
            min_days_to_expiry=1,
            margin_usage_pct=Decimal('0.50'),
            extra={
                'risk_multiplier': self.risk_multiplier,
            }
        )

    def calculate_entry_parameters(self, market_data: Dict) -> Dict:
        """Calculate strikes, premiums, and insurance for iron condor."""
        spot_price = market_data.get('spot_price') or get_nifty_price()
        vix = market_data.get('vix') or get_vix()

        # Calculate strangle strikes (same as strangle)
        strikes = calculate_strangle_strikes(
            spot_price=spot_price,
            days_to_expiry=market_data['days_to_expiry'],
            vix=vix
        )

        # Get option premiums
        call_premium, put_premium = get_option_premiums(
            strikes['call_strike'],
            strikes['put_strike'],
            market_data['expiry']
        )

        total_premium = call_premium + put_premium

        # Calculate insurance strike (UNIQUE TO THIS STRATEGY)
        # Assuming 1 lot = 50 qty for initial calculation
        quantity = 50
        max_profit = total_premium * quantity

        insurance = calculate_insurance_strike(
            put_strike=strikes['put_strike'],
            max_profit=max_profit,
            risk_multiplier=self.risk_multiplier,
            lot_size=50,
            quantity=quantity
        )

        # Get insurance premium
        insurance_premium = get_put_premium(
            insurance['insurance_strike'],
            market_data['expiry']
        )

        return {
            'spot_price': spot_price,
            'vix': vix,
            'strikes': strikes,
            'call_premium': call_premium,
            'put_premium': put_premium,
            'total_strangle_premium': total_premium,
            'insurance': insurance,
            'insurance_premium': insurance_premium,
            'net_premium': total_premium - insurance_premium,
            'expiry': market_data['expiry'],
            'days_to_expiry': market_data['days_to_expiry']
        }

    def build_position_details(self, entry_params: Dict, sizing: Dict) -> Dict:
        """Build 3-leg position details."""
        strikes = entry_params['strikes']
        insurance = entry_params['insurance']
        quantity = sizing['quantity']
        lot_size = sizing['lot_size']
        margin_used = sizing['margin_used']

        # Recalculate net premium with actual quantity
        net_premium_per_qty = entry_params['net_premium'] / 50 * quantity  # Adjust for sizing

        # Support and Resistance
        support_resistance = SupportResistanceCalculator.calculate_next_levels(
            current_price=entry_params['spot_price'],
            support_level=entry_params['spot_price'] * Decimal('0.99'),
            resistance_level=entry_params['spot_price'] * Decimal('1.01')
        )

        return {
            'instrument': 'NIFTY',
            'strategy': 'Broken Iron Condor',
            'legs': [
                {
                    'leg_number': 1,
                    'action': 'SELL',
                    'option_type': 'CE',
                    'strike': strikes['call_strike'],
                    'premium': str(entry_params['call_premium']),
                    'quantity': quantity,
                },
                {
                    'leg_number': 2,
                    'action': 'SELL',
                    'option_type': 'PE',
                    'strike': strikes['put_strike'],
                    'premium': str(entry_params['put_premium']),
                    'quantity': quantity,
                },
                {
                    'leg_number': 3,
                    'action': 'BUY',
                    'option_type': 'PE',
                    'strike': insurance['insurance_strike'],
                    'premium': str(entry_params['insurance_premium']),
                    'quantity': quantity,
                    'purpose': 'Insurance'
                }
            ],
            'call_strike': strikes['call_strike'],
            'put_strike': strikes['put_strike'],
            'insurance_strike': insurance['insurance_strike'],
            'quantity': quantity,
            'lot_size': lot_size,
            'net_premium': str(entry_params['net_premium'] * quantity),
            'max_loss_on_put_side': str(insurance['max_loss_on_put_side']),
            'margin_required': str(margin_used),
            'expiry_date': str(entry_params['expiry']),
            'support_level': str(support_resistance['support']),
            'resistance_level': str(support_resistance['resistance']),
        }

    def build_algorithm_reasoning(self, entry_params: Dict, filters_result: Dict, sizing: Dict) -> Dict:
        """Build algorithm reasoning including insurance details."""
        strikes = entry_params['strikes']
        insurance = entry_params['insurance']
        quantity = sizing['quantity']
        lot_size = sizing['lot_size']

        # Calculate risk scenarios
        risk_scenarios = calculate_broken_iron_condor_scenarios(
            current_price=entry_params['spot_price'],
            call_strike=strikes['call_strike'],
            put_strike=strikes['put_strike'],
            insurance_strike=insurance['insurance_strike'],
            call_premium=entry_params['call_premium'],
            put_premium=entry_params['put_premium'],
            insurance_premium=entry_params['insurance_premium'],
            quantity=quantity,
            lot_size=lot_size
        )

        # Support and Resistance
        support_resistance = SupportResistanceCalculator.calculate_next_levels(
            current_price=entry_params['spot_price'],
            support_level=entry_params['spot_price'] * Decimal('0.99'),
            resistance_level=entry_params['spot_price'] * Decimal('1.01')
        )

        return {
            'title': 'Kotak Broken Iron Condor Strategy',
            'summary': 'Short Strangle with protective put (insurance) for defined downside risk',
            'strategy_type': 'BROKEN_IRON_CONDOR',
            'calculations': {
                'spot_price': str(entry_params['spot_price']),
                'vix': str(entry_params['vix']),
                'days_to_expiry': entry_params['days_to_expiry'],
                'strike_distance': str(strikes['strike_distance']),
                'adjusted_delta': str(strikes['adjusted_delta']),
                'adjustment_reason': strikes['adjustment_reason'],
                'call_premium': str(entry_params['call_premium']),
                'put_premium': str(entry_params['put_premium']),
                'total_strangle_premium': str(entry_params['total_strangle_premium']),
            },
            'insurance': {
                'insurance_strike': insurance['insurance_strike'],
                'insurance_premium': str(entry_params['insurance_premium']),
                'risk_multiplier': str(insurance['risk_multiplier_used']),
                'max_loss_on_put_side': str(insurance['max_loss_on_put_side']),
                'spread_width': insurance['spread_width'],
            },
            'filters': {
                'filters_passed': filters_result.get('filters_passed', []),
                'filters_failed': filters_result.get('filters_failed', []),
                'entry_time_valid': True,
            },
            'position_sizing': {
                'usable_margin': str(sizing['usable_margin']),
                'lot_size': lot_size,
                'lots': sizing['lots'],
                'quantity': quantity,
                'margin_used': str(sizing['margin_used']),
            },
            'risk_scenarios': risk_scenarios,
            'support_resistance': {
                'support_level': str(support_resistance['support']),
                'resistance_level': str(support_resistance['resistance']),
            }
        }


# ============================================================================
# INSURANCE CALCULATION FUNCTIONS (UNIQUE TO THIS STRATEGY)
# ============================================================================

def calculate_insurance_strike(
    put_strike: int,
    max_profit: Decimal,
    risk_multiplier: Decimal,
    lot_size: int,
    quantity: int
) -> Dict:
    """
    Calculate the insurance put strike based on risk budget.

    Insurance Logic:
        - Risk Budget = Max Profit * Risk Multiplier
        - The insurance put should be bought at a strike that limits
          our maximum loss to the risk budget

    For a broken iron condor:
        - We sell a put at put_strike
        - We buy a put at insurance_strike (further OTM)
        - Maximum loss on put side = (put_strike - insurance_strike) * quantity - premium received

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
            'spread_width': int,
            'max_loss_on_put_side': Decimal,
            'risk_multiplier_used': Decimal
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
    logger.info(f"  Max Profit (Premium): Rs.{max_profit:,.2f}")
    logger.info(f"  Risk Multiplier: {risk_multiplier}x")
    logger.info(f"  Risk Budget: Rs.{risk_budget:,.2f}")
    logger.info(f"  Insurance Strike (OTM Put Buy): {insurance_strike}")
    logger.info(f"  Spread Width: {actual_spread} points")
    logger.info(f"  Max Loss on Put Side: Rs.{max_loss_on_put_side:,.2f}")

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
) -> List[Dict]:
    """
    Generate multiple insurance strike options for user selection.

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
    Calculate profit/loss scenarios for broken iron condor.

    Broken Iron Condor P&L:
        - Max profit = Call Premium + Put Premium - Insurance Premium
        - Max loss on upside = Unlimited (but managed by SL)
        - Max loss on downside = (Put Strike - Insurance Strike) * Quantity - Net Premium

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
        'target_price': float(current_price),
        'profit_loss': float(max_profit),
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


def update_insurance_selection(suggestion_id: int, risk_multiplier: float) -> Dict:
    """
    Update the insurance strike based on user's risk multiplier selection from UI.

    This is called when user adjusts the risk slider in the UI.

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
        position_details['max_loss_on_put_side'] = str(selected_option['max_loss_on_put_side'])

        # Update leg 3 (insurance)
        if len(position_details.get('legs', [])) >= 3:
            position_details['legs'][2]['strike'] = selected_option['insurance_strike']
            position_details['legs'][2]['premium'] = str(selected_option['insurance_premium'])

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


# ============================================================================
# BACKWARD COMPATIBILITY FUNCTIONS
# ============================================================================

def execute_kotak_broken_iron_condor_entry(
    account,
    risk_multiplier: Decimal = DEFAULT_RISK_MULTIPLIER
) -> Dict:
    """
    Complete entry workflow for Kotak Broken Iron Condor Strategy.

    This is the backward-compatible wrapper function.

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
    strategy = KotakBrokenIronCondorStrategy(account, risk_multiplier)
    result = strategy.execute_entry()

    # Add insurance options to the result for UI
    output = result.to_dict()

    if result.success and result.suggestion:
        # Generate insurance options for UI selection
        position_details = result.suggestion.position_details
        reasoning = result.suggestion.algorithm_reasoning

        if 'insurance' in reasoning:
            output['insurance_options'] = get_insurance_strike_options(
                put_strike=position_details.get('put_strike', 0),
                max_profit=Decimal(str(reasoning['calculations'].get('total_strangle_premium', '0'))) * 50,
                quantity=50,
                spot_price=Decimal(str(reasoning['calculations'].get('spot_price', '24000')))
            )

    return output


def calculate_strikes(spot_price: Decimal, days_to_expiry: int, vix: Decimal) -> Dict:
    """
    Calculate OTM call and put strikes for short strangle (same as strangle).

    DEPRECATED: Use apps.strategies.shared.strike_calculator.calculate_strangle_strikes instead.
    """
    return calculate_strangle_strikes(spot_price, days_to_expiry, vix)


def run_entry_filters() -> Tuple[bool, list, list]:
    """
    Execute ALL entry filters for broken iron condor strategy.

    DEPRECATED: Use apps.strategies.shared.entry_filters.run_filters instead.
    """
    from apps.strategies.shared.entry_filters import get_default_filters, run_filters

    filters = get_default_filters()
    all_passed, details = run_filters(filters, logger)

    return all_passed, details.get('filters_passed', []), details.get('filters_failed', [])


def get_current_nifty_price() -> Decimal:
    """
    Get current Nifty spot price.

    DEPRECATED: Use apps.strategies.shared.market_data.get_nifty_price instead.
    """
    return get_nifty_price()


def get_current_vix() -> Decimal:
    """
    Get current India VIX value.

    DEPRECATED: Use apps.strategies.shared.market_data.get_vix instead.
    """
    return get_vix()


def get_option_premiums_wrapper(call_strike: int, put_strike: int, expiry_date) -> Tuple[Decimal, Decimal]:
    """
    Get option premiums for given strikes.

    DEPRECATED: Use apps.strategies.shared.market_data.get_option_premiums instead.
    """
    return get_option_premiums(call_strike, put_strike, expiry_date)


def get_put_option_premium(strike: int, expiry_date) -> Decimal:
    """
    Get put option premium for insurance strike.

    DEPRECATED: Use apps.strategies.shared.market_data.get_put_premium instead.
    """
    return get_put_premium(strike, expiry_date)
