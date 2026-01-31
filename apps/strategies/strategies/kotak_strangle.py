"""
Kotak Strangle Strategy

Strategy: Sell out-of-the-money (OTM) Nifty weekly call and put options simultaneously
         to collect premium income while maintaining delta neutrality.

Account: Kotak Securities (Rs.6 Crores)
Target: Rs.6-8 Lakhs monthly (1.0-1.3% return)
Risk Profile: Market-neutral short strangle

Key Rules:
- ONE POSITION PER ACCOUNT (enforced via morning_check)
- 50% margin usage for first trade
- 1-day minimum to expiry (skip if < 1 day)
- Minimum 50% profit to exit EOD
- Delta monitoring (alert if |net_delta| > 300)
- Exit Thursday 3:15 PM (if >=50% profit) or Friday EOD (mandatory)
"""

import logging
from decimal import Decimal
from datetime import time
from typing import Dict, Tuple

from apps.strategies.core.base_strategy import BaseStrategy
from apps.strategies.core.result_types import StrategyConfig, EntryResult
from apps.strategies.shared.strike_calculator import calculate_strangle_strikes
from apps.strategies.shared.market_data import get_nifty_price, get_vix, get_option_premiums
from apps.trading.risk_calculator import OptionsRiskCalculator, SupportResistanceCalculator

logger = logging.getLogger(__name__)


class KotakStrangleStrategy(BaseStrategy):
    """
    Short Strangle strategy for Kotak account.

    Unique Logic:
    - VIX-adjusted strike selection
    - Delta monitoring (alert if |net_delta| > 300)
    - Exit Thursday 3:15 PM (if >=50% profit) or Friday EOD
    """

    def get_config(self) -> StrategyConfig:
        """Return strategy configuration."""
        return StrategyConfig(
            name="Kotak Strangle Strategy",
            strategy_type='OPTIONS',
            direction='NEUTRAL',
            entry_start_time=time(9, 0),
            entry_end_time=time(11, 30),
            min_days_to_expiry=1,
            margin_usage_pct=Decimal('0.50'),
            extra={
                'delta_alert_threshold': 300,
                'profit_target_pct': Decimal('0.50'),
            }
        )

    def calculate_entry_parameters(self, market_data: Dict) -> Dict:
        """Calculate strikes and premiums for strangle."""
        spot_price = market_data.get('spot_price') or get_nifty_price()
        vix = market_data.get('vix') or get_vix()

        # Calculate strikes using shared utility
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

        return {
            'spot_price': spot_price,
            'vix': vix,
            'strikes': strikes,
            'call_premium': call_premium,
            'put_premium': put_premium,
            'total_premium': call_premium + put_premium,
            'expiry': market_data['expiry'],
            'days_to_expiry': market_data['days_to_expiry']
        }

    def build_position_details(self, entry_params: Dict, sizing: Dict) -> Dict:
        """Build position details for trade suggestion."""
        strikes = entry_params['strikes']
        quantity = sizing['quantity']
        lot_size = sizing['lot_size']
        premium_collected = entry_params['total_premium'] * quantity
        margin_used = sizing['margin_used']

        # Calculate stop-loss and target
        # For strangle: SL = 100% loss (premium becomes zero), Target = 70% profit
        stop_loss = Decimal('0')  # Premium goes to zero
        target = premium_collected * Decimal('0.70')  # 70% profit on premium

        # Calculate risk/reward scenarios
        risk_scenarios = OptionsRiskCalculator.calculate_scenarios(
            current_price=entry_params['spot_price'],
            call_strike=strikes['call_strike'],
            put_strike=strikes['put_strike'],
            call_premium=entry_params['call_premium'],
            put_premium=entry_params['put_premium'],
            quantity=quantity,
            lot_size=lot_size
        )

        # Support and Resistance
        support_resistance = SupportResistanceCalculator.calculate_next_levels(
            current_price=entry_params['spot_price'],
            support_level=entry_params['spot_price'] * Decimal('0.99'),  # 1% below
            resistance_level=entry_params['spot_price'] * Decimal('1.01')  # 1% above
        )

        return {
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
            'expiry_date': str(entry_params['expiry']),
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

    def build_algorithm_reasoning(self, entry_params: Dict, filters_result: Dict, sizing: Dict) -> Dict:
        """Build algorithm reasoning for trade suggestion."""
        strikes = entry_params['strikes']
        quantity = sizing['quantity']
        lot_size = sizing['lot_size']
        premium_collected = entry_params['total_premium'] * quantity

        # Calculate risk/reward scenarios for reasoning
        risk_scenarios = OptionsRiskCalculator.calculate_scenarios(
            current_price=entry_params['spot_price'],
            call_strike=strikes['call_strike'],
            put_strike=strikes['put_strike'],
            call_premium=entry_params['call_premium'],
            put_premium=entry_params['put_premium'],
            quantity=quantity,
            lot_size=lot_size
        )

        # Support and Resistance for reasoning
        support_resistance = SupportResistanceCalculator.calculate_next_levels(
            current_price=entry_params['spot_price'],
            support_level=entry_params['spot_price'] * Decimal('0.99'),
            resistance_level=entry_params['spot_price'] * Decimal('1.01')
        )

        return {
            'title': 'Kotak Strangle Strategy',
            'summary': 'Short Strangle position to collect premium',
            'calculations': {
                'spot_price': str(entry_params['spot_price']),
                'vix': str(entry_params['vix']),
                'days_to_expiry': entry_params['days_to_expiry'],
                'strike_distance': str(strikes['strike_distance']),
                'adjusted_delta': str(strikes['adjusted_delta']),
                'adjustment_reason': strikes['adjustment_reason'],
                'call_premium': str(entry_params['call_premium']),
                'put_premium': str(entry_params['put_premium']),
                'total_premium': str(entry_params['total_premium']),
                'premium_collected': str(premium_collected),
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
                    'margin_used': str(sizing['margin_used']),
                    'expiry_date': str(entry_params['expiry']),
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


# ============================================================================
# BACKWARD COMPATIBILITY FUNCTIONS
# ============================================================================

def execute_kotak_strangle_entry(account) -> Dict:
    """
    Complete entry workflow for Kotak Strangle Strategy.

    This is the backward-compatible wrapper function that maintains the
    original function signature for existing code that imports and calls it.

    Workflow:
        1. Morning position check (ONE POSITION RULE)
        2. Entry timing validation (9:00 AM - 11:30 AM)
        3. Run entry filters (ALL must pass)
        4. Expiry selection (1-day rule)
        5. Calculate strikes (VIX-based delta adjustment)
        6. Validate premiums (min/max checks)
        7. Calculate position size (50% margin rule)
        8. Risk limit checks
        9. Create trade suggestion

    Args:
        account: BrokerAccount instance (Kotak)

    Returns:
        dict: {
            'success': bool,
            'message': str,
            'suggestion': TradeSuggestion or None,
            'details': dict
        }
    """
    strategy = KotakStrangleStrategy(account)
    result = strategy.execute_entry()
    return result.to_dict()


# Keep original helper functions for backward compatibility
# These are deprecated - use shared utilities instead

def calculate_strikes(spot_price: Decimal, days_to_expiry: int, vix: Decimal) -> Dict:
    """
    Calculate OTM call and put strikes for short strangle.

    DEPRECATED: Use apps.strategies.shared.strike_calculator.calculate_strangle_strikes instead.
    """
    return calculate_strangle_strikes(spot_price, days_to_expiry, vix)


def run_entry_filters() -> Tuple[bool, list, list]:
    """
    Execute ALL entry filters for strangle strategy.

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


def get_option_premiums_wrapper(call_strike: int, put_strike: int, expiry_date) -> Tuple[Decimal, Decimal]:
    """
    Get option premiums for given strikes.

    DEPRECATED: Use apps.strategies.shared.market_data.get_option_premiums instead.
    """
    return get_option_premiums(call_strike, put_strike, expiry_date)
