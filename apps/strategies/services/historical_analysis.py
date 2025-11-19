"""
Historical Data Analysis for Nifty Strangle Strategy

Fetches and analyzes historical NIFTY data from Breeze API to:
1. Calculate 20 DMA (Day Moving Average)
2. Detect extreme 3-day and 5-day movements
3. Determine trend strength and direction
4. Provide NO TRADE recommendations for extreme conditions

This ensures the algorithm has sufficient data for robust decision making.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

from apps.brokers.integrations.breeze import get_nifty50_historical_days
from apps.brokers.models import HistoricalPrice

logger = logging.getLogger(__name__)


class HistoricalAnalyzer:
    """
    Analyzes historical NIFTY data for trend and extreme movements
    """

    # Thresholds for extreme movements (USING 3 DAYS ONLY)
    EXTREME_3DAY_THRESHOLD = 3.0  # 3% in 3 days = NO TRADE
    WARNING_3DAY_THRESHOLD = 2.0  # 2% in 3 days = WARNING

    def __init__(self, symbol: str = 'NIFTY', days_to_fetch: int = 365):
        """
        Initialize analyzer

        Args:
            symbol: Stock symbol (default: NIFTY)
            days_to_fetch: Days of historical data to ensure (default: 365)
        """
        self.symbol = symbol
        self.days_to_fetch = days_to_fetch
        self.historical_data = []

    def ensure_historical_data(self, force_refresh: bool = False) -> bool:
        """
        Ensure we have sufficient historical data (1 year minimum)
        Fetches from Breeze API if needed

        Args:
            force_refresh: Force download even if data exists

        Returns:
            bool: True if sufficient data available
        """
        # Check how much data we have
        today = date.today()
        start_date = today - timedelta(days=self.days_to_fetch)

        existing_count = HistoricalPrice.objects.filter(
            stock_code=self.symbol,
            datetime__gte=datetime.combine(start_date, datetime.min.time())
        ).count()

        logger.info(f"Found {existing_count} existing historical records for {self.symbol}")

        # Check if we need fresh data
        # Need at least 250 records for 1 year (accounting for weekends/holidays)
        # OR force refresh requested
        if existing_count < 250 or force_refresh:
            logger.info(f"{'Forcing refresh' if force_refresh else f'Insufficient data ({existing_count} records)'}. Fetching from Breeze API...")
            try:
                saved_count = get_nifty50_historical_days(days=self.days_to_fetch, interval="1day")
                logger.info(f"Fetched and saved {saved_count} new historical records")

                if saved_count == 0:
                    logger.error("No historical data was fetched from Breeze API")
                    return False

                return True
            except Exception as e:
                logger.error(f"Failed to fetch historical data from Breeze API: {e}", exc_info=True)
                # Check if we have ANY data to work with
                if existing_count > 0:
                    logger.warning(f"Using existing {existing_count} records despite fetch failure")
                    return True
                return False

        return True

    def load_historical_data(self, days: int = 200) -> List[Dict]:
        """
        Load historical data from database

        Args:
            days: Number of days to load

        Returns:
            List of historical records sorted by date ascending
        """
        today = date.today()
        start_date = today - timedelta(days=days + 10)  # Extra buffer

        records = HistoricalPrice.objects.filter(
            stock_code=self.symbol,
            datetime__gte=datetime.combine(start_date, datetime.min.time())
        ).order_by('datetime')

        self.historical_data = []
        for record in records:
            self.historical_data.append({
                'date': record.datetime.date(),
                'open': float(record.open),
                'high': float(record.high),
                'low': float(record.low),
                'close': float(record.close),
                'volume': int(record.volume) if record.volume else 0,
            })

        logger.info(f"Loaded {len(self.historical_data)} historical records")
        return self.historical_data

    def calculate_moving_average(self, period: int = 20) -> Optional[float]:
        """
        Calculate Simple Moving Average

        Args:
            period: MA period (default: 20)

        Returns:
            float: MA value or None if insufficient data
        """
        if len(self.historical_data) < period:
            logger.warning(f"Insufficient data for {period} MA: {len(self.historical_data)} days available")
            return None

        recent_closes = [d['close'] for d in self.historical_data[-period:]]
        ma = sum(recent_closes) / period

        logger.info(f"{period} SMA: {ma:.2f}")
        return ma

    def calculate_all_moving_averages(self) -> Dict:
        """
        Calculate all standard moving averages (5, 10, 20, 50, 100, 200 SMA and 12, 20, 50 EMA)

        Returns:
            dict: All calculated MAs with metadata
        """
        mas = {
            'source': 'Calculated from HistoricalPrice table',
            'data_points': len(self.historical_data),
            'calculation_date': datetime.now().isoformat(),
        }

        # Calculate SMAs (including 10 and 100 as requested)
        sma_5 = self.calculate_moving_average(5)
        if sma_5:
            mas['sma_5'] = round(sma_5, 2)

        sma_10 = self.calculate_moving_average(10)
        if sma_10:
            mas['sma_10'] = round(sma_10, 2)

        sma_20 = self.calculate_moving_average(20)
        if sma_20:
            mas['sma_20'] = round(sma_20, 2)

        sma_50 = self.calculate_moving_average(50)
        if sma_50:
            mas['sma_50'] = round(sma_50, 2)

        sma_100 = self.calculate_moving_average(100)
        if sma_100:
            mas['sma_100'] = round(sma_100, 2)

        sma_200 = self.calculate_moving_average(200)
        if sma_200:
            mas['sma_200'] = round(sma_200, 2)

        # Calculate EMAs
        if len(self.historical_data) >= 12:
            closes = [d['close'] for d in self.historical_data]
            ema_12 = self._calculate_ema(closes, 12)
            if ema_12:
                mas['ema_12'] = round(ema_12, 2)

        if len(self.historical_data) >= 20:
            closes = [d['close'] for d in self.historical_data]
            ema_20 = self._calculate_ema(closes, 20)
            if ema_20:
                mas['ema_20'] = round(ema_20, 2)

        if len(self.historical_data) >= 50:
            closes = [d['close'] for d in self.historical_data]
            ema_50 = self._calculate_ema(closes, 50)
            if ema_50:
                mas['ema_50'] = round(ema_50, 2)

        logger.info(f"Calculated {len([k for k in mas.keys() if 'ma_' in k or 'ema_' in k])} moving averages from {len(self.historical_data)} data points")
        return mas

    def _calculate_ema(self, closes: List[float], period: int) -> Optional[float]:
        """
        Calculate Exponential Moving Average

        Args:
            closes: List of closing prices
            period: EMA period

        Returns:
            float: EMA value or None if insufficient data
        """
        if len(closes) < period:
            return None

        multiplier = 2 / (period + 1)
        # Start with SMA for first value
        ema = sum(closes[:period]) / period

        # Calculate EMA for remaining values
        for price in closes[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def calculate_extreme_movements(self) -> Dict:
        """
        Calculate 3-day price movement (PRIMARY CHECK)

        User requirement: Use only 3 days for extreme movement check

        Returns:
            dict: Movement analysis with NO TRADE flags
        """
        if len(self.historical_data) < 4:
            return {
                'status': 'INSUFFICIENT_DATA',
                'days_available': len(self.historical_data),
                'error': 'Need at least 4 days of historical data for 3-day movement'
            }

        # Get most recent closes (last 4 days to calculate 3-day movement)
        closes = [d['close'] for d in self.historical_data[-4:]]

        # Calculate 3-day movement (3 days ago to today)
        three_day_start = closes[0]  # 3 days ago
        three_day_end = closes[-1]   # Today
        three_day_move_pct = ((three_day_end - three_day_start) / three_day_start * 100)

        # Determine status based on 3-day movement only
        three_day_status = self._get_movement_status(abs(three_day_move_pct),
                                                       self.WARNING_3DAY_THRESHOLD,
                                                       self.EXTREME_3DAY_THRESHOLD)

        # Overall verdict based ONLY on 3-day movement
        is_extreme = three_day_status == 'EXTREME'
        is_warning = three_day_status == 'WARNING'

        result = {
            'status': 'EXTREME' if is_extreme else ('WARNING' if is_warning else 'NORMAL'),
            'days_available': len(self.historical_data),
            '3_day_movement': {
                'start_price': three_day_start,
                'end_price': three_day_end,
                'move_pct': round(three_day_move_pct, 2),
                'move_abs_pct': round(abs(three_day_move_pct), 2),
                'status': three_day_status,
                'threshold_warning': self.WARNING_3DAY_THRESHOLD,
                'threshold_extreme': self.EXTREME_3DAY_THRESHOLD,
            },
            'no_trade_day': is_extreme,
            'reasoning': self._get_reasoning_3day(three_day_move_pct, three_day_status)
        }

        if is_extreme:
            logger.warning(f"⚠️ EXTREME MOVEMENT DETECTED: 3-day: {three_day_move_pct:+.2f}% (Threshold: {self.EXTREME_3DAY_THRESHOLD}%)")
        elif is_warning:
            logger.info(f"⚠ Warning: Elevated 3-day movement: {three_day_move_pct:+.2f}%")
        else:
            logger.info(f"✓ Normal 3-day movement: {three_day_move_pct:+.2f}%")

        return result

    def _get_movement_status(self, abs_move: float, warning_threshold: float, extreme_threshold: float) -> str:
        """Get movement status based on thresholds"""
        if abs_move >= extreme_threshold:
            return 'EXTREME'
        elif abs_move >= warning_threshold:
            return 'WARNING'
        else:
            return 'NORMAL'

    def _get_reasoning_3day(self, three_day_move: float, status: str) -> str:
        """
        Generate reasoning text based on 3-day movement

        Args:
            three_day_move: 3-day percentage movement
            status: Movement status (EXTREME/WARNING/NORMAL)

        Returns:
            str: Reasoning for strangle decision
        """
        if status == 'EXTREME':
            direction = "UP" if three_day_move > 0 else "DOWN"
            return f"EXTREME {direction} MOVEMENT ({abs(three_day_move):.2f}% in 3 days) - Strong trending market. Strangle risk too high. NO TRADE."
        elif status == 'WARNING':
            direction = "upward" if three_day_move > 0 else "downward"
            return f"Elevated {direction} movement ({abs(three_day_move):.2f}% in 3 days). Monitor closely - reduce position size if entering."
        else:
            return f"Normal 3-day movement ({abs(three_day_move):.2f}%). Market suitable for strangle."

    def calculate_trend_vs_20dma(self, current_price: float) -> Dict:
        """
        Calculate position relative to 20 DMA

        Args:
            current_price: Current market price

        Returns:
            dict: Trend analysis
        """
        dma_20 = self.calculate_moving_average(period=20)

        if dma_20 is None:
            return {
                'status': 'INSUFFICIENT_DATA',
                'dma_20': None,
                'position': 'UNKNOWN'
            }

        diff_pct = ((current_price - dma_20) / dma_20 * 100)

        # Determine trend
        if abs(diff_pct) < 1.0:
            position = 'AT_20DMA'
            trend = 'RANGE_BOUND'
        elif diff_pct > 2.0:
            position = 'WELL_ABOVE_20DMA'
            trend = 'STRONG_UPTREND'
        elif diff_pct > 0:
            position = 'ABOVE_20DMA'
            trend = 'UPTREND'
        elif diff_pct < -2.0:
            position = 'WELL_BELOW_20DMA'
            trend = 'STRONG_DOWNTREND'
        else:
            position = 'BELOW_20DMA'
            trend = 'DOWNTREND'

        return {
            'status': 'CALCULATED',
            'dma_20': round(dma_20, 2),
            'current_price': current_price,
            'diff_pct': round(diff_pct, 2),
            'position': position,
            'trend': trend,
            'interpretation': self._get_trend_interpretation(trend)
        }

    def _get_trend_interpretation(self, trend: str) -> str:
        """Get trend interpretation for trading"""
        interpretations = {
            'RANGE_BOUND': 'Ideal for strangle - price consolidating around 20 DMA',
            'UPTREND': 'Moderate uptrend - consider wider call side',
            'DOWNTREND': 'Moderate downtrend - consider wider put side',
            'STRONG_UPTREND': 'Strong uptrend - widen call side significantly',
            'STRONG_DOWNTREND': 'Strong downtrend - widen put side significantly',
        }
        return interpretations.get(trend, 'Unknown trend')

    def run_complete_analysis(self, current_price: float) -> Dict:
        """
        Run complete historical analysis

        Args:
            current_price: Current market price

        Returns:
            dict: Complete analysis report
        """
        logger.info("Running complete historical analysis")

        # Ensure we have data
        if not self.ensure_historical_data():
            return {
                'status': 'ERROR',
                'error': 'Could not fetch historical data'
            }

        # Load data
        self.load_historical_data(days=200)

        if len(self.historical_data) < 5:
            return {
                'status': 'INSUFFICIENT_DATA',
                'days_available': len(self.historical_data),
                'error': 'Need at least 5 days of historical data'
            }

        # Run all analyses
        extreme_movements = self.calculate_extreme_movements()
        trend_analysis = self.calculate_trend_vs_20dma(current_price)

        # Calculate ALL moving averages from historical data
        all_mas = self.calculate_all_moving_averages()

        return {
            'status': 'SUCCESS',
            'data_summary': {
                'days_available': len(self.historical_data),
                'oldest_date': str(self.historical_data[0]['date']) if self.historical_data else None,
                'newest_date': str(self.historical_data[-1]['date']) if self.historical_data else None,
            },
            'extreme_movements': extreme_movements,
            'trend_vs_20dma': trend_analysis,
            'moving_averages': all_mas,  # Now includes ALL MAs (SMA 5,20,50,200 and EMA 12,20,50)
            'overall_verdict': self._get_overall_verdict(extreme_movements, trend_analysis),
        }

    def _get_overall_verdict(self, extreme_movements: Dict, trend_analysis: Dict) -> str:
        """Get overall trading verdict"""
        if extreme_movements.get('no_trade_day'):
            return "NO TRADE: Extreme movement detected in last 3-5 days"

        if extreme_movements.get('status') == 'WARNING':
            return "CAUTION: Elevated movement - proceed with wider strikes"

        trend = trend_analysis.get('trend', 'UNKNOWN')
        if trend in ['STRONG_UPTREND', 'STRONG_DOWNTREND']:
            return f"CAUTION: Strong trend detected - use asymmetric strangle"

        return "CLEAR: Normal market conditions suitable for strangle"


def analyze_nifty_historical(current_price: float, days_to_fetch: int = 365) -> Dict:
    """
    Convenience function to analyze NIFTY historical data

    Args:
        current_price: Current NIFTY price
        days_to_fetch: Days of data to ensure (default: 365)

    Returns:
        dict: Complete historical analysis
    """
    analyzer = HistoricalAnalyzer(symbol='NIFTY', days_to_fetch=days_to_fetch)
    return analyzer.run_complete_analysis(current_price)
