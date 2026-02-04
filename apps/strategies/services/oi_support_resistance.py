"""
OI-Based Support and Resistance Calculator

Calculates support and resistance levels from Open Interest (OI) data
in F&O contracts. The logic is:
- Highest PUT OI strike = Support level (PUT writers expect price to stay above)
- Highest CALL OI strike = Resistance level (CALL writers expect price to stay below)

This is market participant-driven S/R, reflecting where big money has placed bets.
"""

import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime, date, timedelta
from django.db.models import Sum

from apps.data.models import ContractData

logger = logging.getLogger(__name__)


class OISupportResistanceCalculator:
    """
    Calculate Support/Resistance levels from Options Open Interest data

    Key Concepts:
    - High PUT OI at a strike = Strong Support (option sellers don't want price below)
    - High CALL OI at a strike = Strong Resistance (option sellers don't want price above)
    - OI buildup indicates conviction of market participants
    """

    def __init__(self, symbol: str = 'NIFTY'):
        """
        Initialize OI S/R calculator

        Args:
            symbol: Symbol to analyze (NIFTY, BANKNIFTY, or stock symbol)
        """
        self.symbol = symbol
        self.expiry = None
        self.current_price = None

    def _get_nearest_expiry(self) -> Optional[str]:
        """
        Get the nearest expiry date for the symbol

        Returns:
            str: Expiry date string or None if not found
        """
        today = date.today()

        # Get distinct expiries for the symbol, ordered by date
        expiries = ContractData.objects.filter(
            symbol=self.symbol,
            option_type__in=['CE', 'PE']
        ).values_list('expiry', flat=True).distinct()

        # Parse and find nearest future expiry
        valid_expiries = []
        for exp in expiries:
            try:
                # Handle various date formats
                if '-' in str(exp):
                    exp_date = datetime.strptime(str(exp), '%Y-%m-%d').date()
                else:
                    exp_date = datetime.strptime(str(exp), '%d-%b-%Y').date()

                if exp_date >= today:
                    valid_expiries.append((exp, exp_date))
            except (ValueError, TypeError):
                continue

        if valid_expiries:
            # Sort by date and return nearest
            valid_expiries.sort(key=lambda x: x[1])
            return valid_expiries[0][0]

        return None

    def _get_current_spot_price(self) -> Optional[float]:
        """
        Get current spot price from contract data

        Returns:
            float: Current spot price or None
        """
        # Get spot price from any recent contract
        contract = ContractData.objects.filter(
            symbol=self.symbol,
            spot__isnull=False
        ).order_by('-updated_at').first()

        if contract and contract.spot:
            return float(contract.spot)

        return None

    def get_highest_oi_strikes(self, expiry: str = None, top_n: int = 5) -> Dict:
        """
        Get strikes with highest OI for both calls and puts

        Args:
            expiry: Expiry date (defaults to nearest expiry)
            top_n: Number of top strikes to return

        Returns:
            dict: Highest OI strikes for calls and puts
        """
        if not expiry:
            expiry = self._get_nearest_expiry()

        if not expiry:
            return {
                'available': False,
                'error': f'No F&O data found for {self.symbol}'
            }

        self.expiry = expiry
        self.current_price = self._get_current_spot_price()

        # Get highest CALL OI strikes (these are RESISTANCE levels)
        call_contracts = ContractData.objects.filter(
            symbol=self.symbol,
            expiry=expiry,
            option_type='CE',
            oi__isnull=False,
            oi__gt=0
        ).order_by('-oi')[:top_n]

        # Get highest PUT OI strikes (these are SUPPORT levels)
        put_contracts = ContractData.objects.filter(
            symbol=self.symbol,
            expiry=expiry,
            option_type='PE',
            oi__isnull=False,
            oi__gt=0
        ).order_by('-oi')[:top_n]

        call_strikes = [
            {
                'strike': c.strike_price,
                'oi': c.oi,
                'oi_change': c.oi_change,
                'oi_change_pct': c.pct_oi_change,
                'buildup': c.build_up or 'Unknown'
            }
            for c in call_contracts
        ]

        put_strikes = [
            {
                'strike': p.strike_price,
                'oi': p.oi,
                'oi_change': p.oi_change,
                'oi_change_pct': p.pct_oi_change,
                'buildup': p.build_up or 'Unknown'
            }
            for p in put_contracts
        ]

        return {
            'available': True,
            'symbol': self.symbol,
            'expiry': expiry,
            'spot_price': self.current_price,
            'highest_call_oi_strikes': call_strikes,  # Resistance levels
            'highest_put_oi_strikes': put_strikes,    # Support levels
            'data_timestamp': datetime.now().isoformat()
        }

    def calculate_oi_based_sr(self, current_price: float = None, expiry: str = None) -> Dict:
        """
        Calculate comprehensive OI-based Support and Resistance levels

        Args:
            current_price: Current spot price (fetched if not provided)
            expiry: Expiry date (defaults to nearest)

        Returns:
            dict: OI-based S/R levels with confidence metrics
        """
        if not expiry:
            expiry = self._get_nearest_expiry()

        if not expiry:
            return {
                'available': False,
                'error': f'No F&O data found for {self.symbol}',
                'method': 'OI-Based S/R'
            }

        self.expiry = expiry

        if current_price:
            self.current_price = current_price
        else:
            self.current_price = self._get_current_spot_price()

        if not self.current_price:
            return {
                'available': False,
                'error': 'Could not determine current spot price',
                'method': 'OI-Based S/R'
            }

        # Get all call and put contracts for this expiry
        call_contracts = list(ContractData.objects.filter(
            symbol=self.symbol,
            expiry=expiry,
            option_type='CE',
            oi__isnull=False,
            oi__gt=0,
            strike_price__isnull=False
        ).order_by('-oi'))

        put_contracts = list(ContractData.objects.filter(
            symbol=self.symbol,
            expiry=expiry,
            option_type='PE',
            oi__isnull=False,
            oi__gt=0,
            strike_price__isnull=False
        ).order_by('-oi'))

        if not call_contracts or not put_contracts:
            return {
                'available': False,
                'error': 'Insufficient OI data for analysis',
                'method': 'OI-Based S/R'
            }

        # Calculate resistance levels from CALL OI
        # R1 = Highest CALL OI above current price
        # R2 = Second highest CALL OI above current price
        # R3 = Third highest CALL OI above current price
        call_above_spot = [c for c in call_contracts if c.strike_price > self.current_price]
        call_above_spot.sort(key=lambda x: x.oi, reverse=True)

        # Calculate support levels from PUT OI
        # S1 = Highest PUT OI below current price
        # S2 = Second highest PUT OI below current price
        # S3 = Third highest PUT OI below current price
        put_below_spot = [p for p in put_contracts if p.strike_price < self.current_price]
        put_below_spot.sort(key=lambda x: x.oi, reverse=True)

        # Extract resistance levels
        r1 = call_above_spot[0] if len(call_above_spot) > 0 else None
        r2 = call_above_spot[1] if len(call_above_spot) > 1 else None
        r3 = call_above_spot[2] if len(call_above_spot) > 2 else None

        # Extract support levels
        s1 = put_below_spot[0] if len(put_below_spot) > 0 else None
        s2 = put_below_spot[1] if len(put_below_spot) > 1 else None
        s3 = put_below_spot[2] if len(put_below_spot) > 2 else None

        # Calculate total OI for confidence metrics
        total_call_oi = sum(c.oi for c in call_contracts)
        total_put_oi = sum(p.oi for p in put_contracts)
        pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0

        # Build result
        result = {
            'available': True,
            'method': 'OI-Based S/R (Options Open Interest)',
            'symbol': self.symbol,
            'expiry': expiry,
            'current_price': self.current_price,
            'calculation_time': datetime.now().isoformat(),

            # Primary S/R levels
            'resistance': {
                'r1': {
                    'strike': r1.strike_price if r1 else None,
                    'oi': r1.oi if r1 else None,
                    'oi_change': r1.oi_change if r1 else None,
                    'buildup': r1.build_up if r1 else None,
                    'distance_from_spot': round(r1.strike_price - self.current_price, 2) if r1 else None,
                    'distance_pct': round((r1.strike_price - self.current_price) / self.current_price * 100, 2) if r1 else None
                },
                'r2': {
                    'strike': r2.strike_price if r2 else None,
                    'oi': r2.oi if r2 else None,
                    'oi_change': r2.oi_change if r2 else None,
                    'buildup': r2.build_up if r2 else None,
                    'distance_from_spot': round(r2.strike_price - self.current_price, 2) if r2 else None,
                    'distance_pct': round((r2.strike_price - self.current_price) / self.current_price * 100, 2) if r2 else None
                },
                'r3': {
                    'strike': r3.strike_price if r3 else None,
                    'oi': r3.oi if r3 else None,
                    'oi_change': r3.oi_change if r3 else None,
                    'buildup': r3.build_up if r3 else None,
                    'distance_from_spot': round(r3.strike_price - self.current_price, 2) if r3 else None,
                    'distance_pct': round((r3.strike_price - self.current_price) / self.current_price * 100, 2) if r3 else None
                }
            },
            'support': {
                's1': {
                    'strike': s1.strike_price if s1 else None,
                    'oi': s1.oi if s1 else None,
                    'oi_change': s1.oi_change if s1 else None,
                    'buildup': s1.build_up if s1 else None,
                    'distance_from_spot': round(self.current_price - s1.strike_price, 2) if s1 else None,
                    'distance_pct': round((self.current_price - s1.strike_price) / self.current_price * 100, 2) if s1 else None
                },
                's2': {
                    'strike': s2.strike_price if s2 else None,
                    'oi': s2.oi if s2 else None,
                    'oi_change': s2.oi_change if s2 else None,
                    'buildup': s2.build_up if s2 else None,
                    'distance_from_spot': round(self.current_price - s2.strike_price, 2) if s2 else None,
                    'distance_pct': round((self.current_price - s2.strike_price) / self.current_price * 100, 2) if s2 else None
                },
                's3': {
                    'strike': s3.strike_price if s3 else None,
                    'oi': s3.oi if s3 else None,
                    'oi_change': s3.oi_change if s3 else None,
                    'buildup': s3.build_up if s3 else None,
                    'distance_from_spot': round(self.current_price - s3.strike_price, 2) if s3 else None,
                    'distance_pct': round((self.current_price - s3.strike_price) / self.current_price * 100, 2) if s3 else None
                }
            },

            # Market sentiment metrics
            'market_metrics': {
                'total_call_oi': total_call_oi,
                'total_put_oi': total_put_oi,
                'pcr_oi': round(pcr, 3),
                'pcr_interpretation': self._interpret_pcr(pcr),
                'contracts_analyzed': len(call_contracts) + len(put_contracts)
            }
        }

        # Add OI concentration analysis
        result['oi_concentration'] = self._analyze_oi_concentration(
            call_contracts, put_contracts, total_call_oi, total_put_oi
        )

        return result

    def _interpret_pcr(self, pcr: float) -> str:
        """Interpret Put-Call Ratio"""
        if pcr > 1.5:
            return 'VERY_BULLISH (High PUT writing suggests strong support)'
        elif pcr > 1.2:
            return 'BULLISH (More PUT writing than CALL writing)'
        elif pcr > 0.8:
            return 'NEUTRAL (Balanced OI)'
        elif pcr > 0.5:
            return 'BEARISH (More CALL writing than PUT writing)'
        else:
            return 'VERY_BEARISH (High CALL writing suggests strong resistance)'

    def _analyze_oi_concentration(self, call_contracts: List, put_contracts: List,
                                   total_call_oi: int, total_put_oi: int) -> Dict:
        """
        Analyze OI concentration at key strikes

        High concentration at a strike = Strong S/R level
        """
        # Top 3 call strikes OI concentration
        top_call_oi = sum(c.oi for c in call_contracts[:3]) if call_contracts else 0
        call_concentration = (top_call_oi / total_call_oi * 100) if total_call_oi > 0 else 0

        # Top 3 put strikes OI concentration
        top_put_oi = sum(p.oi for p in put_contracts[:3]) if put_contracts else 0
        put_concentration = (top_put_oi / total_put_oi * 100) if total_put_oi > 0 else 0

        return {
            'top_3_call_concentration_pct': round(call_concentration, 2),
            'top_3_put_concentration_pct': round(put_concentration, 2),
            'resistance_strength': 'STRONG' if call_concentration > 40 else 'MODERATE' if call_concentration > 25 else 'WEAK',
            'support_strength': 'STRONG' if put_concentration > 40 else 'MODERATE' if put_concentration > 25 else 'WEAK'
        }

    def get_conservative_sr(self, current_price: float = None, expiry: str = None) -> Dict:
        """
        Get conservative (closest to spot) S/R levels from OI data

        This is useful when we want the nearest, most immediate S/R levels
        that the market is defending.

        Args:
            current_price: Current spot price
            expiry: Expiry date

        Returns:
            dict: Conservative S/R levels (closest to current price)
        """
        oi_sr = self.calculate_oi_based_sr(current_price, expiry)

        if not oi_sr.get('available'):
            return oi_sr

        # Get R1 and S1 as conservative levels
        r1_strike = oi_sr['resistance']['r1']['strike']
        s1_strike = oi_sr['support']['s1']['strike']

        return {
            'available': True,
            'method': 'OI-Based Conservative S/R',
            'symbol': self.symbol,
            'expiry': oi_sr['expiry'],
            'current_price': oi_sr['current_price'],

            # Conservative levels (closest to spot with highest OI)
            'conservative_resistance': r1_strike,
            'conservative_support': s1_strike,

            # Full details
            'resistance_details': oi_sr['resistance']['r1'],
            'support_details': oi_sr['support']['s1'],

            # Market context
            'pcr': oi_sr['market_metrics']['pcr_oi'],
            'pcr_interpretation': oi_sr['market_metrics']['pcr_interpretation']
        }


def calculate_oi_sr(symbol: str = 'NIFTY', current_price: float = None) -> Dict:
    """
    Convenience function to calculate OI-based S/R

    Args:
        symbol: Symbol to analyze
        current_price: Current spot price (optional)

    Returns:
        dict: OI-based S/R levels
    """
    calculator = OISupportResistanceCalculator(symbol)
    return calculator.calculate_oi_based_sr(current_price)


def get_conservative_oi_sr(symbol: str = 'NIFTY', current_price: float = None) -> Dict:
    """
    Convenience function to get conservative OI-based S/R

    Args:
        symbol: Symbol to analyze
        current_price: Current spot price (optional)

    Returns:
        dict: Conservative S/R levels
    """
    calculator = OISupportResistanceCalculator(symbol)
    return calculator.get_conservative_sr(current_price)
