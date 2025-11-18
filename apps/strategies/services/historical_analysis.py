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

    # Thresholds for extreme movements
    EXTREME_3DAY_THRESHOLD = 3.0  # 3% in 3 days = NO TRADE
    EXTREME_5DAY_THRESHOLD = 4.5  # 4.5% in 5 days = NO TRADE
    WARNING_3DAY_THRESHOLD = 2.0  # 2% in 3 days = WARNING
    WARNING_5DAY_THRESHOLD = 3.5  # 3.5% in 5 days = WARNING

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

    def ensure_historical_data(self) -> bool:
        """
        Ensure we have sufficient historical data
        Fetches from Breeze API if needed

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

        # If we have less than 50 records, fetch more
        if existing_count < 50:
            logger.info(f"Insufficient historical data ({existing_count} records). Fetching from Breeze API...")
            try:
                saved_count = get_nifty50_historical_days(days=self.days_to_fetch, interval="1day")
                logger.info(f"Fetched and saved {saved_count} new historical records")
                return saved_count > 0
            except Exception as e:
                logger.error(f"Failed to fetch historical data: {e}")
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
            return None

        recent_closes = [d['close'] for d in self.historical_data[-period:]]
        ma = sum(recent_closes) / period

        logger.info(f"{period} DMA: {ma:.2f}")
        return ma

    def calculate_extreme_movements(self) -> Dict:
        """
        Calculate 3-day and 5-day price movements

        Returns:
            dict: Movement analysis with NO TRADE flags
        """
        if len(self.historical_data) < 5:
            return {
                'status': 'INSUFFICIENT_DATA',
                'days_available': len(self.historical_data),
                'error': 'Need at least 5 days of historical data'
            }

        # Get most recent closes
        closes = [d['close'] for d in self.historical_data[-6:]]  # Last 6 days

        # Calculate 3-day movement (3 days ago to today)
        three_day_start = closes[-4]  # 3 days ago
        three_day_end = closes[-1]    # Today
        three_day_move_pct = ((three_day_end - three_day_start) / three_day_start * 100)

        # Calculate 5-day movement (5 days ago to today)
        five_day_start = closes[-6]   # 5 days ago
        five_day_end = closes[-1]     # Today
        five_day_move_pct = ((five_day_end - five_day_start) / five_day_start * 100)

        # Determine status
        three_day_status = self._get_movement_status(abs(three_day_move_pct),
                                                       self.WARNING_3DAY_THRESHOLD,
                                                       self.EXTREME_3DAY_THRESHOLD)
        five_day_status = self._get_movement_status(abs(five_day_move_pct),
                                                      self.WARNING_5DAY_THRESHOLD,
                                                      self.EXTREME_5DAY_THRESHOLD)

        # Overall verdict
        is_extreme = three_day_status == 'EXTREME' or five_day_status == 'EXTREME'
        is_warning = three_day_status == 'WARNING' or five_day_status == 'WARNING'

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
            '5_day_movement': {
                'start_price': five_day_start,
                'end_price': five_day_end,
                'move_pct': round(five_day_move_pct, 2),
                'move_abs_pct': round(abs(five_day_move_pct), 2),
                'status': five_day_status,
                'threshold_warning': self.WARNING_5DAY_THRESHOLD,
                'threshold_extreme': self.EXTREME_5DAY_THRESHOLD,
            },
            'no_trade_day': is_extreme,
            'reasoning': self._get_reasoning(three_day_move_pct, five_day_move_pct,
                                             three_day_status, five_day_status)
        }

        if is_extreme:
            logger.warning(f"⚠️ EXTREME MOVEMENT DETECTED: 3-day: {three_day_move_pct:+.2f}%, 5-day: {five_day_move_pct:+.2f}%")
        elif is_warning:
            logger.info(f"⚠ Warning: Elevated movements - 3-day: {three_day_move_pct:+.2f}%, 5-day: {five_day_move_pct:+.2f}%")
        else:
            logger.info(f"✓ Normal movements - 3-day: {three_day_move_pct:+.2f}%, 5-day: {five_day_move_pct:+.2f}%")

        return result

    def _get_movement_status(self, abs_move: float, warning_threshold: float, extreme_threshold: float) -> str:
        """Get movement status based on thresholds"""
        if abs_move >= extreme_threshold:
            return 'EXTREME'
        elif abs_move >= warning_threshold:
            return 'WARNING'
        else:
            return 'NORMAL'

    def _get_reasoning(self, three_day: float, five_day: float,
                       three_status: str, five_status: str) -> str:
        """Generate reasoning text"""
        if three_status == 'EXTREME' or five_status == 'EXTREME':
            return f"EXTREME MOVEMENT - Strong trending market. Strangle risk too high. NO TRADE."
        elif three_status == 'WARNING' or five_status == 'WARNING':
            return f"Elevated movement detected. Monitor closely for breakout/breakdown."
        else:
            return f"Normal price movement. Market suitable for strangle."

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
        dma_50 = self.calculate_moving_average(period=50)
        dma_200 = self.calculate_moving_average(period=200)

        return {
            'status': 'SUCCESS',
            'data_summary': {
                'days_available': len(self.historical_data),
                'oldest_date': str(self.historical_data[0]['date']) if self.historical_data else None,
                'newest_date': str(self.historical_data[-1]['date']) if self.historical_data else None,
            },
            'extreme_movements': extreme_movements,
            'trend_vs_20dma': trend_analysis,
            'moving_averages': {
                'dma_20': trend_analysis.get('dma_20'),
                'dma_50': round(dma_50, 2) if dma_50 else None,
                'dma_200': round(dma_200, 2) if dma_200 else None,
            },
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
