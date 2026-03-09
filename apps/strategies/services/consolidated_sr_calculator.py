"""
Consolidated Support and Resistance Calculator

Combines multiple S/R calculation methods:
1. Pivot Points (from historical price data)
2. OI-Based S/R (from options open interest)

Key Principle: CONSERVATIVE S/R
- When selecting S1, use the HIGHER value (closer to current price) = more conservative support
- When selecting R1, use the LOWER value (closer to current price) = more conservative resistance

Conservative S/R provides safer trading boundaries with less room for adverse moves.
"""

import logging
from typing import Dict
from datetime import datetime

from apps.strategies.services.support_resistance_calculator import (
    SupportResistanceCalculator
)
from apps.strategies.services.oi_support_resistance import (
    OISupportResistanceCalculator
)

logger = logging.getLogger(__name__)


class ConsolidatedSRCalculator:
    """
    Consolidated Support/Resistance calculator combining multiple methods

    Priority: CONSERVATIVE approach
    - For Support: Use the HIGHER (closer) value between Pivot-S1 and OI-S1
    - For Resistance: Use the LOWER (closer) value between Pivot-R1 and OI-R1
    """

    def __init__(self, symbol: str = 'NIFTY', oi_symbol: str = None):
        """
        Initialize consolidated S/R calculator

        Args:
            symbol:    Symbol for HistoricalPrice queries (Breeze stock_code)
            oi_symbol: Symbol for ContractData/OI queries (NSE code).
                       Defaults to symbol when both are the same.
        """
        self.symbol = symbol
        self.pivot_calculator = SupportResistanceCalculator(symbol=symbol)
        self.oi_calculator = OISupportResistanceCalculator(symbol=oi_symbol or symbol)

    def calculate_all_sr_methods(self, current_price: float) -> Dict:
        """
        Calculate S/R using all available methods

        Args:
            current_price: Current spot price

        Returns:
            dict: S/R levels from all methods
        """
        logger.info(f"Calculating consolidated S/R for {self.symbol} at price {current_price}")

        results = {
            'symbol': self.symbol,
            'current_price': current_price,
            'calculation_time': datetime.now().isoformat(),
            'methods_used': []
        }

        # Method 1: Pivot Points
        pivot_sr = None
        try:
            pivot_sr = self.pivot_calculator.calculate_comprehensive_sr(current_price)
            results['pivot_based'] = {
                'available': True,
                'r1': pivot_sr['primary_resistance']['r1'],
                'r2': pivot_sr['primary_resistance']['r2'],
                'r3': pivot_sr['primary_resistance']['r3'],
                's1': pivot_sr['primary_support']['s1'],
                's2': pivot_sr['primary_support']['s2'],
                's3': pivot_sr['primary_support']['s3'],
                'pivot': pivot_sr['pivot_points']['pivot'],
                'method': 'Pivot Points (5-day average)'
            }
            results['methods_used'].append('pivot_points')
            logger.info(f"Pivot S/R: S1={pivot_sr['primary_support']['s1']}, R1={pivot_sr['primary_resistance']['r1']}")
        except Exception as e:
            logger.warning(f"Pivot S/R calculation failed: {e}")
            results['pivot_based'] = {'available': False, 'error': str(e)}

        # Method 2: OI-Based S/R
        oi_sr = None
        try:
            oi_sr = self.oi_calculator.calculate_oi_based_sr(current_price)
            if oi_sr.get('available'):
                results['oi_based'] = {
                    'available': True,
                    'r1': oi_sr['resistance']['r1']['strike'],
                    'r2': oi_sr['resistance']['r2']['strike'],
                    'r3': oi_sr['resistance']['r3']['strike'],
                    's1': oi_sr['support']['s1']['strike'],
                    's2': oi_sr['support']['s2']['strike'],
                    's3': oi_sr['support']['s3']['strike'],
                    'r1_oi': oi_sr['resistance']['r1']['oi'],
                    's1_oi': oi_sr['support']['s1']['oi'],
                    'pcr': oi_sr['market_metrics']['pcr_oi'],
                    'expiry': oi_sr['expiry'],
                    'method': 'OI-Based (Options Open Interest)'
                }
                results['methods_used'].append('oi_based')
                logger.info(f"OI S/R: S1={oi_sr['support']['s1']['strike']}, R1={oi_sr['resistance']['r1']['strike']}")
            else:
                results['oi_based'] = {'available': False, 'error': oi_sr.get('error', 'No OI data')}
        except Exception as e:
            logger.warning(f"OI S/R calculation failed: {e}")
            results['oi_based'] = {'available': False, 'error': str(e)}

        return results

    def get_conservative_sr(self, current_price: float) -> Dict:
        """
        Get CONSERVATIVE Support and Resistance levels

        Conservative means:
        - Support: The HIGHER value (closer to current price) = less room to fall
        - Resistance: The LOWER value (closer to current price) = less room to rise

        This approach minimizes risk by assuming tighter ranges.

        Args:
            current_price: Current spot price

        Returns:
            dict: Conservative S/R levels with source information
        """
        all_sr = self.calculate_all_sr_methods(current_price)

        # Collect all S1 values
        s1_values = []
        s2_values = []
        s3_values = []
        r1_values = []
        r2_values = []
        r3_values = []

        # From Pivot method
        if all_sr.get('pivot_based', {}).get('available'):
            pivot = all_sr['pivot_based']
            if pivot.get('s1'):
                s1_values.append(('pivot', pivot['s1']))
            if pivot.get('s2'):
                s2_values.append(('pivot', pivot['s2']))
            if pivot.get('s3'):
                s3_values.append(('pivot', pivot['s3']))
            if pivot.get('r1'):
                r1_values.append(('pivot', pivot['r1']))
            if pivot.get('r2'):
                r2_values.append(('pivot', pivot['r2']))
            if pivot.get('r3'):
                r3_values.append(('pivot', pivot['r3']))

        # From OI method
        if all_sr.get('oi_based', {}).get('available'):
            oi = all_sr['oi_based']
            if oi.get('s1'):
                s1_values.append(('oi', oi['s1']))
            if oi.get('s2'):
                s2_values.append(('oi', oi['s2']))
            if oi.get('s3'):
                s3_values.append(('oi', oi['s3']))
            if oi.get('r1'):
                r1_values.append(('oi', oi['r1']))
            if oi.get('r2'):
                r2_values.append(('oi', oi['r2']))
            if oi.get('r3'):
                r3_values.append(('oi', oi['r3']))

        # Select CONSERVATIVE values
        # For Support: Higher value = closer to price = more conservative
        # For Resistance: Lower value = closer to price = more conservative

        def select_conservative_support(values):
            """Select highest (closest to price) support"""
            if not values:
                return None, None
            # Sort by value descending (highest first)
            sorted_vals = sorted(values, key=lambda x: x[1], reverse=True)
            return sorted_vals[0][1], sorted_vals[0][0]

        def select_conservative_resistance(values):
            """Select lowest (closest to price) resistance"""
            if not values:
                return None, None
            # Sort by value ascending (lowest first)
            sorted_vals = sorted(values, key=lambda x: x[1])
            return sorted_vals[0][1], sorted_vals[0][0]

        # Get conservative levels
        cons_s1, s1_source = select_conservative_support(s1_values)
        cons_s2, s2_source = select_conservative_support(s2_values)
        cons_s3, s3_source = select_conservative_support(s3_values)
        cons_r1, r1_source = select_conservative_resistance(r1_values)
        cons_r2, r2_source = select_conservative_resistance(r2_values)
        cons_r3, r3_source = select_conservative_resistance(r3_values)

        # Build comparison details
        comparison = {
            's1': {
                'conservative_value': cons_s1,
                'source': s1_source,
                'all_values': {src: val for src, val in s1_values}
            },
            'r1': {
                'conservative_value': cons_r1,
                'source': r1_source,
                'all_values': {src: val for src, val in r1_values}
            }
        }

        result = {
            'symbol': self.symbol,
            'current_price': current_price,
            'calculation_time': datetime.now().isoformat(),
            'approach': 'CONSERVATIVE (closest to current price)',

            # Conservative S/R levels
            'conservative_support': {
                's1': cons_s1,
                's1_source': s1_source,
                's2': cons_s2,
                's2_source': s2_source,
                's3': cons_s3,
                's3_source': s3_source,
            },
            'conservative_resistance': {
                'r1': cons_r1,
                'r1_source': r1_source,
                'r2': cons_r2,
                'r2_source': r2_source,
                'r3': cons_r3,
                'r3_source': r3_source,
            },

            # Distance calculations
            'distance_to_s1': round(current_price - cons_s1, 2) if cons_s1 else None,
            'distance_to_s1_pct': round((current_price - cons_s1) / current_price * 100, 2) if cons_s1 else None,
            'distance_to_r1': round(cons_r1 - current_price, 2) if cons_r1 else None,
            'distance_to_r1_pct': round((cons_r1 - current_price) / current_price * 100, 2) if cons_r1 else None,

            # Method comparison
            'comparison': comparison,

            # All raw data
            'all_methods': all_sr,

            # Methods that contributed
            'methods_used': all_sr['methods_used']
        }

        # Add trading range
        if cons_s1 and cons_r1:
            result['conservative_range'] = {
                'lower_bound': cons_s1,
                'upper_bound': cons_r1,
                'range_points': round(cons_r1 - cons_s1, 2),
                'range_pct': round((cons_r1 - cons_s1) / current_price * 100, 2)
            }

        logger.info(
            f"Conservative S/R for {self.symbol}: "
            f"S1={cons_s1} ({s1_source}), R1={cons_r1} ({r1_source})"
        )

        return result

    def check_price_vs_conservative_sr(self, current_price: float) -> Dict:
        """
        Check current price position relative to conservative S/R

        Args:
            current_price: Current spot price

        Returns:
            dict: Position analysis
        """
        sr = self.get_conservative_sr(current_price)

        s1 = sr['conservative_support']['s1']
        r1 = sr['conservative_resistance']['r1']

        if not s1 or not r1:
            return {
                'position': 'UNKNOWN',
                'analysis': 'Insufficient S/R data'
            }

        # Calculate distances
        dist_to_s1 = current_price - s1
        dist_to_r1 = r1 - current_price
        total_range = r1 - s1

        # Determine position
        if dist_to_s1 <= 0:
            position = 'BELOW_SUPPORT'
            risk_level = 'HIGH'
        elif dist_to_r1 <= 0:
            position = 'ABOVE_RESISTANCE'
            risk_level = 'HIGH'
        elif dist_to_s1 < total_range * 0.2:
            position = 'NEAR_SUPPORT'
            risk_level = 'MODERATE'
        elif dist_to_r1 < total_range * 0.2:
            position = 'NEAR_RESISTANCE'
            risk_level = 'MODERATE'
        else:
            position = 'MID_RANGE'
            risk_level = 'LOW'

        return {
            'position': position,
            'risk_level': risk_level,
            'distance_to_support': round(dist_to_s1, 2),
            'distance_to_resistance': round(dist_to_r1, 2),
            'support_level': s1,
            'support_source': sr['conservative_support']['s1_source'],
            'resistance_level': r1,
            'resistance_source': sr['conservative_resistance']['r1_source'],
            'range_width': round(total_range, 2),
            'position_in_range_pct': round((current_price - s1) / total_range * 100, 2) if total_range > 0 else None
        }


# Convenience functions

def get_conservative_sr(symbol: str = 'NIFTY', current_price: float = None) -> Dict:
    """
    Get conservative S/R for a symbol

    Args:
        symbol: Symbol to analyze
        current_price: Current spot price

    Returns:
        dict: Conservative S/R levels
    """
    calculator = ConsolidatedSRCalculator(symbol)

    if not current_price:
        # Try to get from OI calculator
        oi_calc = OISupportResistanceCalculator(symbol)
        current_price = oi_calc._get_current_spot_price()

    if not current_price:
        return {
            'available': False,
            'error': 'Could not determine current price'
        }

    return calculator.get_conservative_sr(current_price)


def get_nifty_conservative_sr(current_price: float) -> Dict:
    """
    Get conservative S/R for NIFTY

    Args:
        current_price: Current NIFTY spot price

    Returns:
        dict: Conservative S/R levels for NIFTY
    """
    return get_conservative_sr('NIFTY', current_price)


def check_strike_vs_conservative_sr(symbol: str, strike: int, option_type: str,
                                     current_price: float) -> Dict:
    """
    Check if a strike is dangerously close to conservative S/R levels

    Args:
        symbol: Symbol
        strike: Strike price to check
        option_type: 'CE' or 'PE'
        current_price: Current spot price

    Returns:
        dict: Strike proximity analysis
    """
    calculator = ConsolidatedSRCalculator(symbol)
    sr = calculator.get_conservative_sr(current_price)

    if not sr.get('conservative_support', {}).get('s1'):
        return {'available': False, 'error': 'No S/R data available'}

    s1 = sr['conservative_support']['s1']
    s2 = sr['conservative_support']['s2']
    r1 = sr['conservative_resistance']['r1']
    r2 = sr['conservative_resistance']['r2']

    threshold = 100  # Points proximity threshold

    result = {
        'strike': strike,
        'option_type': option_type,
        'should_adjust': False,
        'reason': None,
        'adjusted_strike': strike
    }

    if option_type == 'CE':
        # Check call strike against resistance levels
        if r1 and abs(strike - r1) <= threshold:
            result['should_adjust'] = True
            result['reason'] = f"CALL strike {strike} too close to conservative R1 ({r1})"
            result['dangerous_level'] = r1
            result['adjusted_strike'] = strike + 50  # Move UP
        elif r2 and abs(strike - r2) <= threshold:
            result['should_adjust'] = True
            result['reason'] = f"CALL strike {strike} too close to conservative R2 ({r2})"
            result['dangerous_level'] = r2
            result['adjusted_strike'] = strike + 50

    else:  # PE
        # Check put strike against support levels
        if s1 and abs(strike - s1) <= threshold:
            result['should_adjust'] = True
            result['reason'] = f"PUT strike {strike} too close to conservative S1 ({s1})"
            result['dangerous_level'] = s1
            result['adjusted_strike'] = strike - 50  # Move DOWN
        elif s2 and abs(strike - s2) <= threshold:
            result['should_adjust'] = True
            result['reason'] = f"PUT strike {strike} too close to conservative S2 ({s2})"
            result['dangerous_level'] = s2
            result['adjusted_strike'] = strike - 50

    result['conservative_sr'] = {
        's1': s1,
        's2': s2,
        'r1': r1,
        'r2': r2
    }

    return result
