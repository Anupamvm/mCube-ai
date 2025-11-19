"""
Technical Analysis Service for Nifty Strangle Strategy

Calculates support/resistance levels, moving averages, and uses them
to intelligently adjust delta for optimal strike selection.

Key Concepts:
- Price near support → Widen put side (increase put delta)
- Price near resistance → Widen call side (increase call delta)
- Price above all MAs (bullish) → Widen call side
- Price below all MAs (bearish) → Widen put side
- Price between MAs → Balanced strangle
"""

import logging
from decimal import Decimal
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta

from apps.brokers.models import HistoricalPrice
from apps.data.models import TLStockData

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """
    Analyzes technical indicators for NIFTY to adjust strangle delta
    """

    def __init__(self, symbol: str = 'NIFTY', current_price: float = None):
        """
        Initialize technical analyzer

        Args:
            symbol: Symbol to analyze (default: NIFTY)
            current_price: Current spot price
        """
        self.symbol = symbol
        self.current_price = current_price
        self.analysis_result = {}

    def analyze_all(self) -> Dict:
        """
        Run complete technical analysis using REAL calculated data from historical prices

        Returns:
            dict: Complete technical analysis with delta adjustments
        """
        logger.info(f"Starting technical analysis for {self.symbol}")

        # STEP 1: Ensure we have 1 year of historical data
        from apps.strategies.services.historical_analysis import analyze_nifty_historical

        logger.info(f"Fetching and analyzing 1-year historical data for {self.symbol}")
        historical_analysis = analyze_nifty_historical(
            current_price=self.current_price,
            days_to_fetch=365
        )

        # STEP 2: Extract REAL moving averages (not assumptions!)
        if historical_analysis.get('status') == 'SUCCESS':
            moving_averages = historical_analysis['moving_averages']
            logger.info(f"Using REAL calculated MAs: {moving_averages.get('source')}")
        else:
            logger.warning(f"Historical analysis failed: {historical_analysis.get('error')}, falling back to Trendlyne")
            # Fallback to Trendlyne only if historical analysis completely failed
            tl_data = self._get_trendlyne_data()
            moving_averages = self._get_trendlyne_mas(tl_data)

        # STEP 3: Calculate support/resistance from real pivot points
        support_resistance = self._calculate_support_resistance_from_history()

        # STEP 4: Determine trend from MAs
        trend_analysis = self._analyze_trend(moving_averages)

        # STEP 5: Calculate position relative to S/R levels
        sr_position = self._analyze_sr_position(support_resistance)

        # STEP 6: Calculate delta adjustments
        delta_adjustments = self._calculate_delta_adjustments(
            sr_position, trend_analysis, moving_averages
        )

        return {
            'support_resistance': support_resistance,
            'moving_averages': moving_averages,
            'trend_analysis': trend_analysis,
            'sr_position': sr_position,
            'delta_adjustments': delta_adjustments,
            'technical_verdict': self._get_technical_verdict(delta_adjustments),
            'data_quality': {
                'historical_data_available': historical_analysis.get('status') == 'SUCCESS',
                'days_analyzed': historical_analysis.get('data_summary', {}).get('days_available', 0),
                'ma_source': moving_averages.get('source', 'Unknown')
            }
        }

    def _get_trendlyne_data(self) -> Optional[TLStockData]:
        """Get Trendlyne data for the symbol"""
        try:
            # Try exact match first
            data = TLStockData.objects.filter(nsecode__iexact=self.symbol).first()
            if data:
                return data

            # Try partial match
            data = TLStockData.objects.filter(nsecode__icontains=self.symbol).first()
            return data
        except Exception as e:
            logger.warning(f"Could not fetch Trendlyne data: {e}")
            return None

    def _get_trendlyne_mas(self, tl_data: Optional[TLStockData]) -> Dict:
        """Get MAs from Trendlyne data (fallback only)"""
        if tl_data and tl_data.day30_sma:
            return {
                'source': 'Trendlyne (fallback)',
                'sma_5': float(tl_data.day5_sma) if tl_data.day5_sma else None,
                'sma_20': float(tl_data.day30_sma) if tl_data.day30_sma else None,
                'sma_50': float(tl_data.day50_sma) if tl_data.day50_sma else None,
                'sma_200': float(tl_data.day200_sma) if tl_data.day200_sma else None,
                'ema_12': float(tl_data.day12_ema) if tl_data.day12_ema else None,
                'ema_20': float(tl_data.day20_ema) if tl_data.day20_ema else None,
                'ema_50': float(tl_data.day50_ema) if tl_data.day50_ema else None,
            }
        return {'source': 'Not Available'}

    def _calculate_support_resistance_from_history(self) -> Dict:
        """Calculate S/R from recent historical data using pivot points"""
        try:
            # Get last 5 days of data for pivot calculation
            from datetime import date
            start_date = date.today() - timedelta(days=10)

            recent = HistoricalPrice.objects.filter(
                stock_code=self.symbol,
                datetime__gte=datetime.combine(start_date, datetime.min.time())
            ).order_by('-datetime').first()

            if recent:
                high = float(recent.high)
                low = float(recent.low)
                close = float(recent.close)

                # Calculate pivot points
                pivot = (high + low + close) / 3
                r1 = (2 * pivot) - low
                r2 = pivot + (high - low)
                r3 = high + 2 * (pivot - low)
                s1 = (2 * pivot) - high
                s2 = pivot - (high - low)
                s3 = low - 2 * (high - pivot)

                return {
                    'source': 'Calculated from Recent Historical Data',
                    'pivot': pivot,
                    'r1': r1,
                    'r2': r2,
                    'r3': r3,
                    's1': s1,
                    's2': s2,
                    's3': s3,
                    'calculation_date': recent.datetime.date().isoformat()
                }
        except Exception as e:
            logger.warning(f"Could not calculate S/R from history: {e}")

        return {
            'source': 'Not Available',
            'pivot': None,
            'r1': None,
            'r2': None,
            'r3': None,
            's1': None,
            's2': None,
            's3': None,
        }

    def _calculate_support_resistance(self, tl_data: Optional[TLStockData]) -> Dict:
        """
        Calculate support and resistance levels

        Uses Trendlyne data if available, otherwise calculates pivot points
        from recent price action
        """
        if tl_data and tl_data.pivot_point:
            # Use Trendlyne S/R data
            return {
                'source': 'Trendlyne',
                'pivot': float(tl_data.pivot_point) if tl_data.pivot_point else None,
                'r1': float(tl_data.first_resistance_r1) if tl_data.first_resistance_r1 else None,
                'r2': float(tl_data.second_resistance_r2) if tl_data.second_resistance_r2 else None,
                'r3': float(tl_data.third_resistance_r3) if tl_data.third_resistance_r3 else None,
                's1': float(tl_data.first_support_s1) if tl_data.first_support_s1 else None,
                's2': float(tl_data.second_support_s2) if tl_data.second_support_s2 else None,
                's3': float(tl_data.third_support_s3) if tl_data.third_support_s3 else None,
            }

        # Calculate pivot points from recent historical data
        try:
            from django.db.models import Max, Min
            from datetime import date

            # Get yesterday's data for pivot calculation
            yesterday = date.today() - timedelta(days=1)
            recent = HistoricalPrice.objects.filter(
                stock_code=self.symbol,
                datetime__date=yesterday
            ).first()

            if not recent:
                # Get most recent available data
                recent = HistoricalPrice.objects.filter(
                    stock_code=self.symbol
                ).order_by('-datetime').first()

            if recent:
                high = float(recent.high)
                low = float(recent.low)
                close = float(recent.close)

                # Standard pivot point calculation
                pivot = (high + low + close) / 3
                r1 = 2 * pivot - low
                r2 = pivot + (high - low)
                r3 = high + 2 * (pivot - low)
                s1 = 2 * pivot - high
                s2 = pivot - (high - low)
                s3 = low - 2 * (high - pivot)

                return {
                    'source': 'Calculated from Historical Data',
                    'pivot': pivot,
                    'r1': r1,
                    'r2': r2,
                    'r3': r3,
                    's1': s1,
                    's2': s2,
                    's3': s3,
                    'calculation_date': recent.datetime.date().isoformat()
                }
        except Exception as e:
            logger.warning(f"Could not calculate pivot points: {e}")

        return {
            'source': 'Not Available',
            'pivot': None,
            'r1': None,
            'r2': None,
            'r3': None,
            's1': None,
            's2': None,
            's3': None,
        }

    def _calculate_moving_averages(self, tl_data: Optional[TLStockData]) -> Dict:
        """
        Calculate moving averages

        Uses Trendlyne data if available, otherwise calculates from historical data
        """
        if tl_data and tl_data.day30_sma:
            # Use Trendlyne MA data
            return {
                'source': 'Trendlyne',
                'sma_5': float(tl_data.day5_sma) if tl_data.day5_sma else None,
                'sma_20': float(tl_data.day30_sma) if tl_data.day30_sma else None,
                'sma_50': float(tl_data.day50_sma) if tl_data.day50_sma else None,
                'sma_200': float(tl_data.day200_sma) if tl_data.day200_sma else None,
                'ema_12': float(tl_data.day12_ema) if tl_data.day12_ema else None,
                'ema_20': float(tl_data.day20_ema) if tl_data.day20_ema else None,
                'ema_50': float(tl_data.day50_ema) if tl_data.day50_ema else None,
            }

        # Calculate from historical data
        try:
            from datetime import date

            # Get last 200 days of data for SMA200
            start_date = date.today() - timedelta(days=250)
            historical = HistoricalPrice.objects.filter(
                stock_code=self.symbol,
                datetime__gte=datetime.combine(start_date, datetime.min.time())
            ).order_by('-datetime')[:200]

            if historical.count() < 5:
                logger.warning(f"Insufficient historical data for MA calculation: {historical.count()} days")
                return {'source': 'Not Available'}

            closes = [float(h.close) for h in reversed(list(historical))]

            mas = {
                'source': 'Calculated from Historical Data',
            }

            # Calculate SMAs
            if len(closes) >= 5:
                mas['sma_5'] = sum(closes[-5:]) / 5
            if len(closes) >= 20:
                mas['sma_20'] = sum(closes[-20:]) / 20
            if len(closes) >= 50:
                mas['sma_50'] = sum(closes[-50:]) / 50
            if len(closes) >= 200:
                mas['sma_200'] = sum(closes[-200:]) / 200

            # Calculate EMAs (simplified exponential moving average)
            if len(closes) >= 20:
                mas['ema_12'] = self._calculate_ema(closes, 12)
                mas['ema_20'] = self._calculate_ema(closes, 20)
            if len(closes) >= 50:
                mas['ema_50'] = self._calculate_ema(closes, 50)

            return mas

        except Exception as e:
            logger.warning(f"Could not calculate moving averages: {e}")
            return {'source': 'Not Available'}

    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Start with SMA

        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def _analyze_trend(self, mas: Dict) -> Dict:
        """
        Analyze trend from moving averages

        Returns:
            dict: Trend analysis with bias (bullish/bearish/neutral)
        """
        if not self.current_price or mas.get('source') == 'Not Available':
            return {
                'bias': 'NEUTRAL',
                'strength': 'UNKNOWN',
                'reasoning': 'Insufficient data for trend analysis'
            }

        price = self.current_price
        signals = []

        # Check price vs each MA
        if mas.get('sma_20'):
            if price > mas['sma_20']:
                signals.append(('BULLISH', 'Price above SMA20'))
            else:
                signals.append(('BEARISH', 'Price below SMA20'))

        if mas.get('sma_50'):
            if price > mas['sma_50']:
                signals.append(('BULLISH', 'Price above SMA50'))
            else:
                signals.append(('BEARISH', 'Price below SMA50'))

        if mas.get('ema_20'):
            if price > mas['ema_20']:
                signals.append(('BULLISH', 'Price above EMA20'))
            else:
                signals.append(('BEARISH', 'Price below EMA20'))

        # Check MA alignment (golden/death cross indicators)
        if mas.get('sma_20') and mas.get('sma_50'):
            if mas['sma_20'] > mas['sma_50']:
                signals.append(('BULLISH', 'SMA20 > SMA50 (golden cross territory)'))
            else:
                signals.append(('BEARISH', 'SMA20 < SMA50 (death cross territory)'))

        # Count bullish vs bearish signals
        bullish_count = sum(1 for s in signals if s[0] == 'BULLISH')
        bearish_count = sum(1 for s in signals if s[0] == 'BEARISH')

        # Determine overall bias
        if bullish_count > bearish_count:
            bias = 'BULLISH'
            strength = 'STRONG' if bullish_count >= bearish_count + 2 else 'MODERATE'
        elif bearish_count > bullish_count:
            bias = 'BEARISH'
            strength = 'STRONG' if bearish_count >= bullish_count + 2 else 'MODERATE'
        else:
            bias = 'NEUTRAL'
            strength = 'BALANCED'

        return {
            'bias': bias,
            'strength': strength,
            'bullish_signals': bullish_count,
            'bearish_signals': bearish_count,
            'reasoning': ' | '.join([s[1] for s in signals]),
            'signals': signals
        }

    def _analyze_sr_position(self, sr: Dict) -> Dict:
        """
        Analyze price position relative to support/resistance

        Returns:
            dict: Position analysis with delta adjustment recommendations
        """
        if not self.current_price or sr.get('source') == 'Not Available':
            return {
                'position': 'UNKNOWN',
                'nearest_support': None,
                'nearest_resistance': None,
                'recommendation': 'No S/R data available'
            }

        price = self.current_price

        # Find nearest support and resistance
        supports = [sr['s1'], sr['s2'], sr['s3']]
        resistances = [sr['r1'], sr['r2'], sr['r3']]

        # Filter out None values
        supports = [s for s in supports if s is not None and s < price]
        resistances = [r for r in resistances if r is not None and r > price]

        nearest_support = max(supports) if supports else None
        nearest_resistance = min(resistances) if resistances else None

        # Calculate distance to S/R as percentage
        dist_to_support = ((price - nearest_support) / price * 100) if nearest_support else None
        dist_to_resistance = ((nearest_resistance - price) / price * 100) if nearest_resistance else None

        # Determine position
        if dist_to_support and dist_to_support < 1.0:
            position = 'NEAR_SUPPORT'
            recommendation = 'Widen put side (price near support)'
        elif dist_to_resistance and dist_to_resistance < 1.0:
            position = 'NEAR_RESISTANCE'
            recommendation = 'Widen call side (price near resistance)'
        elif dist_to_support and dist_to_resistance:
            if dist_to_support < dist_to_resistance:
                position = 'CLOSER_TO_SUPPORT'
                recommendation = 'Slightly favor put side'
            else:
                position = 'CLOSER_TO_RESISTANCE'
                recommendation = 'Slightly favor call side'
        else:
            position = 'NEUTRAL'
            recommendation = 'Balanced strangle'

        return {
            'position': position,
            'nearest_support': nearest_support,
            'nearest_resistance': nearest_resistance,
            'dist_to_support_pct': round(dist_to_support, 2) if dist_to_support else None,
            'dist_to_resistance_pct': round(dist_to_resistance, 2) if dist_to_resistance else None,
            'recommendation': recommendation
        }

    def _calculate_delta_adjustments(self, sr_position: Dict, trend: Dict, mas: Dict) -> Dict:
        """
        Calculate delta adjustments based on technical analysis

        Returns:
            dict: Delta adjustment multipliers for call and put sides
        """
        call_multiplier = 1.0
        put_multiplier = 1.0
        reasons = []

        # Adjust based on S/R position (stronger weight)
        if sr_position['position'] == 'NEAR_SUPPORT':
            put_multiplier *= 1.15  # Widen put side by 15%
            reasons.append("Near support: Widened put side 15%")
        elif sr_position['position'] == 'NEAR_RESISTANCE':
            call_multiplier *= 1.15  # Widen call side by 15%
            reasons.append("Near resistance: Widened call side 15%")
        elif sr_position['position'] == 'CLOSER_TO_SUPPORT':
            put_multiplier *= 1.08  # Slightly widen put side
            reasons.append("Closer to support: Widened put side 8%")
        elif sr_position['position'] == 'CLOSER_TO_RESISTANCE':
            call_multiplier *= 1.08  # Slightly widen call side
            reasons.append("Closer to resistance: Widened call side 8%")

        # Adjust based on trend (moderate weight)
        if trend['bias'] == 'BULLISH' and trend['strength'] == 'STRONG':
            call_multiplier *= 1.10  # Widen call side in strong uptrend
            reasons.append("Strong bullish trend: Widened call side 10%")
        elif trend['bias'] == 'BEARISH' and trend['strength'] == 'STRONG':
            put_multiplier *= 1.10  # Widen put side in strong downtrend
            reasons.append("Strong bearish trend: Widened put side 10%")
        elif trend['bias'] == 'BULLISH' and trend['strength'] == 'MODERATE':
            call_multiplier *= 1.05
            reasons.append("Moderate bullish trend: Widened call side 5%")
        elif trend['bias'] == 'BEARISH' and trend['strength'] == 'MODERATE':
            put_multiplier *= 1.05
            reasons.append("Moderate bearish trend: Widened put side 5%")

        return {
            'call_multiplier': round(call_multiplier, 3),
            'put_multiplier': round(put_multiplier, 3),
            'is_asymmetric': call_multiplier != put_multiplier,
            'adjustment_reasons': reasons,
            'total_call_adjustment_pct': round((call_multiplier - 1) * 100, 1),
            'total_put_adjustment_pct': round((put_multiplier - 1) * 100, 1)
        }

    def _get_technical_verdict(self, adjustments: Dict) -> str:
        """Get overall technical verdict"""
        if not adjustments['is_asymmetric']:
            return "SYMMETRIC: Balanced technical conditions - Standard strangle recommended"

        call_adj = adjustments['total_call_adjustment_pct']
        put_adj = adjustments['total_put_adjustment_pct']

        if call_adj > put_adj:
            return f"CALL-BIASED: Widen call side by {call_adj:.1f}% based on technical analysis"
        elif put_adj > call_adj:
            return f"PUT-BIASED: Widen put side by {put_adj:.1f}% based on technical analysis"
        else:
            return "SYMMETRIC: Balanced adjustments"


def analyze_technical_indicators(symbol: str = 'NIFTY', current_price: float = None) -> Dict:
    """
    Convenience function to run technical analysis

    Args:
        symbol: Symbol to analyze
        current_price: Current spot price

    Returns:
        dict: Complete technical analysis
    """
    analyzer = TechnicalAnalyzer(symbol, current_price)
    return analyzer.analyze_all()
