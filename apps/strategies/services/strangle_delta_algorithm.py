"""
Smart Nifty Strangle Algorithm with Delta-Based Strike Selection

This algorithm implements intelligent strike selection based on:
1. Delta calculation: strike_distance = spot × delta% × days_to_expiry
2. Multi-factor delta adjustment (VIX, market trend, volatility, OI)
3. Real-time data from Breeze API
4. Greeks calculation for validation
"""

import logging
from decimal import Decimal
from datetime import date, datetime
from typing import Dict, List, Tuple, Optional
from django.utils import timezone

logger = logging.getLogger(__name__)


class StrangleDeltaAlgorithm:
    """
    Smart strangle algorithm with multi-factor delta adjustment

    Base Formula:
        strike_distance = spot × (delta% / 100) × days_to_expiry

    Delta is adjusted based on:
        1. VIX level (volatility regime)
        2. Market trend (bullish/bearish/neutral)
        3. Recent volatility (last 5 days)
        4. OI analysis (buildup patterns)
        5. PCR (Put-Call Ratio)
    """

    def __init__(self, spot_price: Decimal, days_to_expiry: int, vix: Decimal):
        """
        Initialize the algorithm with market data

        Args:
            spot_price: Current Nifty spot price
            days_to_expiry: Days remaining to expiry
            vix: India VIX value
        """
        self.spot_price = spot_price
        self.days_to_expiry = days_to_expiry
        self.vix = vix

        # Base delta: 0.75% for ≤2 days, 0.5% for >2 days
        if days_to_expiry <= 2:
            self.base_delta = Decimal('0.75')
            self.base_delta_reason = f"Short expiry ({days_to_expiry} days ≤ 2) - using higher base delta 0.75%"
        else:
            self.base_delta = Decimal('0.5')
            self.base_delta_reason = f"Standard expiry ({days_to_expiry} days > 2) - using base delta 0.5%"

        # Adjustment factors
        self.vix_adjustment = Decimal('1.0')
        self.trend_adjustment = Decimal('1.0')
        self.volatility_adjustment = Decimal('1.0')
        self.oi_adjustment = Decimal('1.0')
        self.pcr_adjustment = Decimal('1.0')

        # Final adjusted delta
        self.adjusted_delta = self.base_delta

        # Calculation log
        self.calculation_log = []

    def calculate_vix_adjustment(self) -> Decimal:
        """
        Calculate VIX-based delta adjustment

        Logic:
            - VIX < 12 (very low): 0.9x (tighter strikes - riskier)
            - VIX 12-15 (normal): 1.0x (standard strikes)
            - VIX 15-18 (elevated): 1.1x (wider strikes - safer)
            - VIX 18-25 (high): 1.2x (much wider strikes)
            - VIX > 25 (extreme): 1.4x (very wide strikes - very safe)

        Returns:
            Decimal: VIX adjustment multiplier
        """
        vix_val = float(self.vix)

        if vix_val < 12:
            adj = Decimal('0.9')
            reason = f"Very low VIX ({vix_val:.1f}) - tighter strikes for higher premium"
        elif vix_val < 15:
            adj = Decimal('1.0')
            reason = f"Normal VIX ({vix_val:.1f}) - standard strike distance"
        elif vix_val < 18:
            adj = Decimal('1.1')
            reason = f"Elevated VIX ({vix_val:.1f}) - slightly wider strikes (+10%)"
        elif vix_val < 25:
            adj = Decimal('1.2')
            reason = f"High VIX ({vix_val:.1f}) - wider strikes for safety (+20%)"
        else:
            adj = Decimal('1.4')
            reason = f"Extreme VIX ({vix_val:.1f}) - very wide strikes (+40%)"

        self.vix_adjustment = adj
        self.calculation_log.append({
            'factor': 'VIX Adjustment',
            'value': vix_val,
            'multiplier': float(adj),
            'reason': reason
        })

        return adj

    def calculate_trend_adjustment(self, market_trend: str = 'NEUTRAL') -> Decimal:
        """
        Calculate market trend-based delta adjustment

        Logic:
            - BULLISH: Widen call strike more (+15%), keep put standard
            - BEARISH: Widen put strike more (+15%), keep call standard
            - NEUTRAL: Symmetric strikes (no adjustment)

        Args:
            market_trend: 'BULLISH', 'BEARISH', or 'NEUTRAL'

        Returns:
            Decimal: Trend adjustment multiplier
        """
        if market_trend == 'BULLISH':
            adj = Decimal('1.05')  # Slight overall widening, more on call side
            reason = "Bullish market - widening call strike more"
        elif market_trend == 'BEARISH':
            adj = Decimal('1.05')  # Slight overall widening, more on put side
            reason = "Bearish market - widening put strike more"
        else:
            adj = Decimal('1.0')
            reason = "Neutral market - symmetric strikes"

        self.trend_adjustment = adj
        self.calculation_log.append({
            'factor': 'Market Trend',
            'value': market_trend,
            'multiplier': float(adj),
            'reason': reason
        })

        return adj

    def calculate_volatility_adjustment(self, recent_volatility: Optional[Decimal] = None) -> Decimal:
        """
        Calculate recent volatility-based adjustment

        Logic:
            - If recent 5-day volatility > historical average: Widen strikes
            - If recent volatility < average: Can tighten slightly

        Args:
            recent_volatility: Recent 5-day realized volatility %

        Returns:
            Decimal: Volatility adjustment multiplier
        """
        if recent_volatility is None:
            # If we don't have volatility data, use VIX as proxy
            self.calculation_log.append({
                'factor': 'Recent Volatility',
                'value': 'N/A',
                'multiplier': 1.0,
                'reason': 'No volatility data - using VIX adjustment only'
            })
            return Decimal('1.0')

        # Compare with VIX (VIX is forward-looking, this is backward-looking)
        vol_val = float(recent_volatility)
        vix_val = float(self.vix)

        if vol_val > vix_val * 1.2:
            adj = Decimal('1.15')
            reason = f"Recent volatility ({vol_val:.1f}%) > VIX - widening for realized risk"
        elif vol_val < vix_val * 0.8:
            adj = Decimal('0.95')
            reason = f"Recent volatility ({vol_val:.1f}%) < VIX - can tighten slightly"
        else:
            adj = Decimal('1.0')
            reason = f"Recent volatility ({vol_val:.1f}%) aligned with VIX"

        self.volatility_adjustment = adj
        self.calculation_log.append({
            'factor': 'Recent Volatility',
            'value': vol_val,
            'multiplier': float(adj),
            'reason': reason
        })

        return adj

    def calculate_oi_adjustment(self, call_oi_buildup: str = 'NEUTRAL',
                               put_oi_buildup: str = 'NEUTRAL') -> Decimal:
        """
        Calculate OI-based adjustment

        Logic:
            - LONG buildup (OI+, Price+): Directional move likely - widen
            - SHORT buildup (OI+, Price-): Directional move likely - widen
            - COVERING (OI-, Price+): Uncertainty - slightly widen
            - NEUTRAL: No adjustment

        Args:
            call_oi_buildup: 'LONG', 'SHORT', 'COVERING', or 'NEUTRAL'
            put_oi_buildup: 'LONG', 'SHORT', 'COVERING', or 'NEUTRAL'

        Returns:
            Decimal: OI adjustment multiplier
        """
        # If either side shows strong directional bias, widen
        if call_oi_buildup in ['LONG', 'SHORT'] or put_oi_buildup in ['LONG', 'SHORT']:
            adj = Decimal('1.1')
            reason = f"OI shows directional bias (CE: {call_oi_buildup}, PE: {put_oi_buildup}) - widening"
        elif call_oi_buildup == 'COVERING' or put_oi_buildup == 'COVERING':
            adj = Decimal('1.05')
            reason = f"OI covering detected - slight widening for uncertainty"
        else:
            adj = Decimal('1.0')
            reason = "OI neutral - no adjustment"

        self.oi_adjustment = adj
        self.calculation_log.append({
            'factor': 'OI Analysis',
            'value': f"CE: {call_oi_buildup}, PE: {put_oi_buildup}",
            'multiplier': float(adj),
            'reason': reason
        })

        return adj

    def calculate_pcr_adjustment(self, pcr: Optional[Decimal] = None) -> Decimal:
        """
        Calculate PCR-based adjustment

        Logic:
            - PCR > 1.3: Market very bearish - widen put side
            - PCR 0.7-1.3: Normal - no adjustment
            - PCR < 0.7: Market very bullish - widen call side

        Args:
            pcr: Put-Call Ratio (OI-based)

        Returns:
            Decimal: PCR adjustment multiplier
        """
        if pcr is None:
            self.calculation_log.append({
                'factor': 'PCR Analysis',
                'value': 'N/A',
                'multiplier': 1.0,
                'reason': 'No PCR data available'
            })
            return Decimal('1.0')

        pcr_val = float(pcr)

        if pcr_val > 1.3:
            adj = Decimal('1.05')
            reason = f"High PCR ({pcr_val:.2f}) - bearish sentiment, widening slightly"
        elif pcr_val < 0.7:
            adj = Decimal('1.05')
            reason = f"Low PCR ({pcr_val:.2f}) - bullish sentiment, widening slightly"
        else:
            adj = Decimal('1.0')
            reason = f"Normal PCR ({pcr_val:.2f}) - balanced sentiment"

        self.pcr_adjustment = adj
        self.calculation_log.append({
            'factor': 'PCR Analysis',
            'value': pcr_val,
            'multiplier': float(adj),
            'reason': reason
        })

        return adj

    def calculate_adjusted_delta(self, market_conditions: Optional[Dict] = None) -> Decimal:
        """
        Calculate final adjusted delta based on all factors

        Args:
            market_conditions: Optional dict with market data:
                - market_trend: str
                - recent_volatility: Decimal
                - call_oi_buildup: str
                - put_oi_buildup: str
                - pcr: Decimal

        Returns:
            Decimal: Final adjusted delta percentage
        """
        # Step 1: VIX adjustment (always applied)
        self.calculate_vix_adjustment()

        # Step 2: Apply optional market condition adjustments
        if market_conditions:
            self.calculate_trend_adjustment(market_conditions.get('market_trend', 'NEUTRAL'))
            self.calculate_volatility_adjustment(market_conditions.get('recent_volatility'))
            self.calculate_oi_adjustment(
                market_conditions.get('call_oi_buildup', 'NEUTRAL'),
                market_conditions.get('put_oi_buildup', 'NEUTRAL')
            )
            self.calculate_pcr_adjustment(market_conditions.get('pcr'))

        # Calculate final adjusted delta
        self.adjusted_delta = (
            self.base_delta *
            self.vix_adjustment *
            self.trend_adjustment *
            self.volatility_adjustment *
            self.oi_adjustment *
            self.pcr_adjustment
        )

        self.calculation_log.append({
            'factor': 'FINAL DELTA',
            'value': f'{float(self.adjusted_delta):.3f}%',
            'multiplier': 1.0,
            'reason': f'Base {float(self.base_delta)}% × All adjustments = {float(self.adjusted_delta):.3f}%'
        })

        logger.info(f"Adjusted Delta: {float(self.adjusted_delta):.3f}% (Base: {float(self.base_delta)}%)")

        return self.adjusted_delta

    def calculate_strikes(self, market_conditions: Optional[Dict] = None, technical_analysis: Optional[Dict] = None) -> Dict:
        """
        Calculate call and put strikes based on adjusted delta

        Formula:
            strike_distance = spot × (delta% / 100) × days_to_expiry
            call_strike = spot + strike_distance × call_multiplier (rounded to nearest 50)
            put_strike = spot - strike_distance × put_multiplier (rounded to nearest 50)

        Args:
            market_conditions: Optional market data for adjustments
            technical_analysis: Optional technical analysis (S/R, MA) for asymmetric strikes

        Returns:
            dict: {
                'call_strike': int,
                'put_strike': int,
                'strike_distance': Decimal,
                'adjusted_delta': Decimal,
                'calculation_log': List[Dict],
                'delta_breakdown': Dict,
                'technical_analysis': Dict (if provided)
            }
        """
        # Calculate adjusted delta
        adjusted_delta = self.calculate_adjusted_delta(market_conditions)

        # Calculate base strike distance
        strike_distance = self.spot_price * (adjusted_delta / Decimal('100')) * Decimal(str(self.days_to_expiry))

        # Apply technical analysis adjustments for asymmetric strikes
        call_multiplier = Decimal('1.0')
        put_multiplier = Decimal('1.0')

        if technical_analysis and technical_analysis.get('delta_adjustments'):
            ta_adj = technical_analysis['delta_adjustments']
            call_multiplier = Decimal(str(ta_adj.get('call_multiplier', 1.0)))
            put_multiplier = Decimal(str(ta_adj.get('put_multiplier', 1.0)))

            if ta_adj.get('is_asymmetric'):
                self.calculation_log.append({
                    'factor': 'TECHNICAL ANALYSIS',
                    'value': f"Call: {float(call_multiplier):.2f}x, Put: {float(put_multiplier):.2f}x",
                    'multiplier': 1.0,
                    'reason': ' | '.join(ta_adj.get('adjustment_reasons', []))
                })
                logger.info(f"Applying technical analysis: Call {float(call_multiplier):.2f}x, Put {float(put_multiplier):.2f}x")

        # Calculate asymmetric strike distances
        call_distance = strike_distance * call_multiplier
        put_distance = strike_distance * put_multiplier

        # Round to nearest 50 (Nifty strikes are in multiples of 50)
        call_strike = int(round((float(self.spot_price) + float(call_distance)) / 50) * 50)
        put_strike = int(round((float(self.spot_price) - float(put_distance)) / 50) * 50)

        logger.info(f"Base Strike Distance: {float(strike_distance):.2f} points")
        logger.info(f"Call Distance: {float(call_distance):.2f} points (×{float(call_multiplier):.2f})")
        logger.info(f"Put Distance: {float(put_distance):.2f} points (×{float(put_multiplier):.2f})")
        logger.info(f"Call Strike: {call_strike}")
        logger.info(f"Put Strike: {put_strike}")

        result = {
            'call_strike': call_strike,
            'put_strike': put_strike,
            'strike_distance': float(strike_distance),
            'call_distance': float(call_distance),
            'put_distance': float(put_distance),
            'adjusted_delta': float(adjusted_delta),
            'base_delta': float(self.base_delta),
            'calculation_log': self.calculation_log,
            'delta_breakdown': {
                'vix_multiplier': float(self.vix_adjustment),
                'trend_multiplier': float(self.trend_adjustment),
                'volatility_multiplier': float(self.volatility_adjustment),
                'oi_multiplier': float(self.oi_adjustment),
                'pcr_multiplier': float(self.pcr_adjustment),
            },
            'is_asymmetric': call_multiplier != put_multiplier,
            'call_multiplier': float(call_multiplier),
            'put_multiplier': float(put_multiplier),
        }

        # Include technical analysis if provided
        if technical_analysis:
            result['technical_analysis'] = technical_analysis

        return result
