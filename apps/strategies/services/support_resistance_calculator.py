"""
Support and Resistance Calculator from Historical Data

Calculates comprehensive S/R levels using 1-year NIFTY50 historical data from Breeze API:
- Support levels (S1, S2, S3) using pivot points and historical lows
- Resistance levels (R1, R2, R3) using pivot points and historical highs
- Moving averages (20 DMA, 50 DMA, 100 DMA, 200 DMA)
- Strike proximity checks and adjustments
- Risk calculations at various breach levels

NO ASSUMPTIONS - All data from real historical prices.
"""

import logging
from decimal import Decimal
from typing import Dict, Optional, List, Tuple
from datetime import datetime, date, timedelta

from apps.brokers.models import HistoricalPrice
from apps.brokers.integrations.breeze import get_nifty50_historical_days

logger = logging.getLogger(__name__)


class SupportResistanceCalculator:
    """
    Calculate Support/Resistance levels from historical NIFTY50 data

    Uses multiple methods:
    1. Pivot Points (Classic method)
    2. Historical High/Low clusters
    3. Moving Average support/resistance
    """

    def __init__(self, symbol: str = 'NIFTY', lookback_days: int = 365):
        """
        Initialize S/R calculator

        Args:
            symbol: Stock symbol (default: NIFTY)
            lookback_days: Days of historical data to analyze
        """
        self.symbol = symbol
        self.lookback_days = lookback_days
        self.historical_data = []

    def ensure_and_load_data(self) -> bool:
        """
        Ensure we have 1 year of historical data and load it

        Returns:
            bool: True if data loaded successfully
        """
        # Check existing data
        today = date.today()
        start_date = today - timedelta(days=self.lookback_days)

        existing_count = HistoricalPrice.objects.filter(
            stock_code=self.symbol,
            datetime__gte=datetime.combine(start_date, datetime.min.time())
        ).count()

        logger.info(f"Found {existing_count} existing historical records for {self.symbol}")

        # Fetch if insufficient (need at least 250 for 1 year of trading days)
        if existing_count < 250:
            logger.info(f"Fetching {self.lookback_days} days of historical data from Breeze API...")
            try:
                saved_count = get_nifty50_historical_days(days=self.lookback_days, interval="1day")
                logger.info(f"Fetched and saved {saved_count} historical records")
            except Exception as e:
                logger.error(f"Failed to fetch historical data: {e}")
                raise ValueError(f"Could not fetch historical data from Breeze API: {str(e)}")

        # Load data
        records = HistoricalPrice.objects.filter(
            stock_code=self.symbol,
            datetime__gte=datetime.combine(start_date, datetime.min.time())
        ).order_by('datetime')

        self.historical_data = [
            {
                'date': record.datetime.date(),
                'open': float(record.open),
                'high': float(record.high),
                'low': float(record.low),
                'close': float(record.close),
                'volume': int(record.volume) if record.volume else 0
            }
            for record in records
        ]

        logger.info(f"Loaded {len(self.historical_data)} days of historical data")

        if len(self.historical_data) < 20:
            raise ValueError(f"Insufficient historical data: only {len(self.historical_data)} days available")

        return True

    def calculate_pivot_points(self) -> Dict:
        """
        Calculate classic pivot points from recent price action

        Uses last 5 days average for stable pivots

        Returns:
            dict: Pivot, R1, R2, R3, S1, S2, S3
        """
        if len(self.historical_data) < 5:
            raise ValueError("Need at least 5 days of data for pivot calculation")

        # Use last 5 days for more stable pivots
        recent_data = self.historical_data[-5:]

        avg_high = sum(d['high'] for d in recent_data) / 5
        avg_low = sum(d['low'] for d in recent_data) / 5
        avg_close = sum(d['close'] for d in recent_data) / 5

        # Classic Pivot Point formula
        pivot = (avg_high + avg_low + avg_close) / 3

        # Resistance levels
        r1 = (2 * pivot) - avg_low
        r2 = pivot + (avg_high - avg_low)
        r3 = avg_high + 2 * (pivot - avg_low)

        # Support levels
        s1 = (2 * pivot) - avg_high
        s2 = pivot - (avg_high - avg_low)
        s3 = avg_low - 2 * (avg_high - pivot)

        return {
            'method': 'Pivot Points (5-day average)',
            'pivot': round(pivot, 2),
            'r1': round(r1, 2),
            'r2': round(r2, 2),
            'r3': round(r3, 2),
            's1': round(s1, 2),
            's2': round(s2, 2),
            's3': round(s3, 2),
            'calculation_date': date.today().isoformat()
        }

    def calculate_historical_levels(self) -> Dict:
        """
        Calculate S/R from historical high/low clusters

        Finds significant price levels where price reversed multiple times

        Returns:
            dict: Historical support and resistance zones
        """
        if len(self.historical_data) < 60:
            return {'available': False, 'reason': 'Need at least 60 days for cluster analysis'}

        # Get last 60 days
        recent = self.historical_data[-60:]

        highs = sorted([d['high'] for d in recent], reverse=True)
        lows = sorted([d['low'] for d in recent])

        # Find resistance zones (top 20% of highs)
        resistance_zone_1 = sum(highs[:12]) / 12  # Top 20% average
        resistance_zone_2 = sum(highs[12:24]) / 12  # Next 20%

        # Find support zones (bottom 20% of lows)
        support_zone_1 = sum(lows[:12]) / 12  # Bottom 20% average
        support_zone_2 = sum(lows[12:24]) / 12  # Next 20%

        return {
            'method': 'Historical High/Low Clusters (60-day)',
            'resistance_zone_1': round(resistance_zone_1, 2),
            'resistance_zone_2': round(resistance_zone_2, 2),
            'support_zone_1': round(support_zone_1, 2),
            'support_zone_2': round(support_zone_2, 2)
        }

    def calculate_moving_averages(self) -> Dict:
        """
        Calculate key moving averages: 20, 50, 100, 200 DMA

        Returns:
            dict: All DMAs with availability flags
        """
        mas = {
            'source': 'Calculated from HistoricalPrice table (Breeze data)',
            'data_points': len(self.historical_data)
        }

        closes = [d['close'] for d in self.historical_data]

        # 20 DMA
        if len(closes) >= 20:
            mas['dma_20'] = round(sum(closes[-20:]) / 20, 2)
            mas['dma_20_available'] = True
        else:
            mas['dma_20_available'] = False

        # 50 DMA
        if len(closes) >= 50:
            mas['dma_50'] = round(sum(closes[-50:]) / 50, 2)
            mas['dma_50_available'] = True
        else:
            mas['dma_50_available'] = False

        # 100 DMA
        if len(closes) >= 100:
            mas['dma_100'] = round(sum(closes[-100:]) / 100, 2)
            mas['dma_100_available'] = True
        else:
            mas['dma_100_available'] = False

        # 200 DMA
        if len(closes) >= 200:
            mas['dma_200'] = round(sum(closes[-200:]) / 200, 2)
            mas['dma_200_available'] = True
        else:
            mas['dma_200_available'] = False

        return mas

    def calculate_comprehensive_sr(self, current_price: float) -> Dict:
        """
        Calculate comprehensive support and resistance analysis

        Args:
            current_price: Current market price

        Returns:
            dict: Complete S/R analysis with all methods
        """
        logger.info(f"Starting comprehensive S/R calculation for {self.symbol}")

        # Ensure data is loaded
        self.ensure_and_load_data()

        # Calculate using all methods
        pivot_points = self.calculate_pivot_points()
        historical_levels = self.calculate_historical_levels()
        moving_averages = self.calculate_moving_averages()

        # Consolidate S/R levels (use pivot points as primary)
        sr_levels = {
            'current_price': current_price,
            'pivot_points': pivot_points,
            'historical_levels': historical_levels,
            'moving_averages': moving_averages,

            # Primary S/R (from pivots)
            'primary_resistance': {
                'r1': pivot_points['r1'],
                'r2': pivot_points['r2'],
                'r3': pivot_points['r3']
            },
            'primary_support': {
                's1': pivot_points['s1'],
                's2': pivot_points['s2'],
                's3': pivot_points['s3']
            },

            # Price position analysis
            'price_analysis': self._analyze_price_position(
                current_price,
                pivot_points,
                moving_averages
            ),

            # Data quality
            'data_quality': {
                'days_analyzed': len(self.historical_data),
                'oldest_date': str(self.historical_data[0]['date']),
                'newest_date': str(self.historical_data[-1]['date']),
                'source': 'Breeze API via HistoricalPrice table'
            }
        }

        return sr_levels

    def _analyze_price_position(self, price: float, pivots: Dict, mas: Dict) -> Dict:
        """Analyze where price is relative to S/R levels"""
        analysis = {
            'vs_pivot': self._get_position(price, pivots['pivot']),
            'nearest_resistance': self._find_nearest_resistance(price, pivots),
            'nearest_support': self._find_nearest_support(price, pivots),
        }

        # MA analysis
        if mas.get('dma_20_available'):
            analysis['vs_dma_20'] = self._get_position(price, mas['dma_20'])
        if mas.get('dma_50_available'):
            analysis['vs_dma_50'] = self._get_position(price, mas['dma_50'])
        if mas.get('dma_100_available'):
            analysis['vs_dma_100'] = self._get_position(price, mas['dma_100'])
        if mas.get('dma_200_available'):
            analysis['vs_dma_200'] = self._get_position(price, mas['dma_200'])

        return analysis

    def _get_position(self, price: float, level: float) -> Dict:
        """Get position relative to a level"""
        diff = price - level
        diff_pct = (diff / level * 100) if level > 0 else 0

        return {
            'level': level,
            'distance_points': round(diff, 2),
            'distance_pct': round(diff_pct, 2),
            'position': 'ABOVE' if diff > 0 else 'BELOW'
        }

    def _find_nearest_resistance(self, price: float, pivots: Dict) -> Dict:
        """Find nearest resistance above current price"""
        resistances = [
            ('R1', pivots['r1']),
            ('R2', pivots['r2']),
            ('R3', pivots['r3'])
        ]

        above_price = [(name, level) for name, level in resistances if level > price]

        if above_price:
            name, level = above_price[0]  # Nearest
            distance = level - price
            return {
                'level_name': name,
                'level_value': level,
                'distance_points': round(distance, 2),
                'distance_pct': round((distance / price * 100), 2)
            }

        return {'level_name': None, 'message': 'Price above all resistances'}

    def _find_nearest_support(self, price: float, pivots: Dict) -> Dict:
        """Find nearest support below current price"""
        supports = [
            ('S1', pivots['s1']),
            ('S2', pivots['s2']),
            ('S3', pivots['s3'])
        ]

        below_price = [(name, level) for name, level in supports if level < price]

        if below_price:
            name, level = below_price[-1]  # Nearest (highest below price)
            distance = price - level
            return {
                'level_name': name,
                'level_value': level,
                'distance_points': round(distance, 2),
                'distance_pct': round((distance / price * 100), 2)
            }

        return {'level_name': None, 'message': 'Price below all supports'}

    def check_strike_proximity_to_sr(self, strike: int, option_type: str, sr_data: Dict) -> Dict:
        """
        Check if strike is too close to S/R level and recommend adjustment

        Logic:
        - If CALL strike within 100 points ABOVE resistance → Move UP one strike
        - If PUT strike within 100 points BELOW support → Move DOWN one strike

        Args:
            strike: Strike price to check
            option_type: 'CE' or 'PE'
            sr_data: S/R data from calculate_comprehensive_sr()

        Returns:
            dict: Adjustment recommendation
        """
        strike_interval = 50  # NIFTY strike interval

        if option_type == 'CE':
            # Check if call strike is near resistance
            r1 = sr_data['primary_resistance']['r1']
            r2 = sr_data['primary_resistance']['r2']

            # Check R1
            if abs(strike - r1) <= 100:
                return {
                    'should_adjust': True,
                    'reason': f"CALL strike {strike} too close to R1 ({r1:.0f})",
                    'dangerous_level': r1,
                    'level_type': 'R1',
                    'original_strike': strike,
                    'adjusted_strike': strike + strike_interval,
                    'adjustment': f"+{strike_interval} (moved UP away from resistance)"
                }

            # Check R2
            if abs(strike - r2) <= 100:
                return {
                    'should_adjust': True,
                    'reason': f"CALL strike {strike} too close to R2 ({r2:.0f})",
                    'dangerous_level': r2,
                    'level_type': 'R2',
                    'original_strike': strike,
                    'adjusted_strike': strike + strike_interval,
                    'adjustment': f"+{strike_interval} (moved UP away from resistance)"
                }

        else:  # PE
            # Check if put strike is near support
            s1 = sr_data['primary_support']['s1']
            s2 = sr_data['primary_support']['s2']

            # Check S1
            if abs(strike - s1) <= 100:
                return {
                    'should_adjust': True,
                    'reason': f"PUT strike {strike} too close to S1 ({s1:.0f})",
                    'dangerous_level': s1,
                    'level_type': 'S1',
                    'original_strike': strike,
                    'adjusted_strike': strike - strike_interval,
                    'adjustment': f"-{strike_interval} (moved DOWN away from support)"
                }

            # Check S2
            if abs(strike - s2) <= 100:
                return {
                    'should_adjust': True,
                    'reason': f"PUT strike {strike} too close to S2 ({s2:.0f})",
                    'dangerous_level': s2,
                    'level_type': 'S2',
                    'original_strike': strike,
                    'adjusted_strike': strike - strike_interval,
                    'adjustment': f"-{strike_interval} (moved DOWN away from support)"
                }

        return {
            'should_adjust': False,
            'reason': f"{option_type} {strike} is safe from S/R levels",
            'original_strike': strike,
            'adjusted_strike': strike
        }

    def calculate_risk_at_breach(self, position_data: Dict, sr_data: Dict) -> Dict:
        """
        Calculate risk if S1/R1 or S2/R2 breached

        Args:
            position_data: Position details (strikes, premiums, lot size)
            sr_data: S/R data from calculate_comprehensive_sr()

        Returns:
            dict: Risk calculations at various breach levels
        """
        current_price = sr_data['current_price']
        r1 = sr_data['primary_resistance']['r1']
        r2 = sr_data['primary_resistance']['r2']
        s1 = sr_data['primary_support']['s1']
        s2 = sr_data['primary_support']['s2']

        # For strangle
        if 'call_strike' in position_data and 'put_strike' in position_data:
            return self._calculate_strangle_breach_risk(
                position_data, current_price, r1, r2, s1, s2
            )

        # For futures
        elif 'entry_price' in position_data:
            return self._calculate_futures_breach_risk(
                position_data, current_price, r1, r2, s1, s2
            )

        return {'error': 'Unknown position type'}

    def _calculate_strangle_breach_risk(self, pos: Dict, price: float,
                                       r1: float, r2: float, s1: float, s2: float) -> Dict:
        """Calculate strangle risk at S/R breaches"""
        call_strike = pos['call_strike']
        put_strike = pos['put_strike']
        call_premium = pos.get('call_premium', 0)
        put_premium = pos.get('put_premium', 0)
        lot_size = pos.get('lot_size', 50)

        total_premium = call_premium + put_premium
        max_profit = total_premium * lot_size

        # Risk at R1 breach (call side)
        if price < r1:
            r1_breach_loss = (r1 - call_strike - total_premium) * lot_size if r1 > call_strike else 0
        else:
            r1_breach_loss = 0

        # Risk at R2 breach (call side)
        if price < r2:
            r2_breach_loss = (r2 - call_strike - total_premium) * lot_size if r2 > call_strike else 0
        else:
            r2_breach_loss = 0

        # Risk at S1 breach (put side)
        if price > s1:
            s1_breach_loss = (put_strike - s1 - total_premium) * lot_size if s1 < put_strike else 0
        else:
            s1_breach_loss = 0

        # Risk at S2 breach (put side)
        if price > s2:
            s2_breach_loss = (put_strike - s2 - total_premium) * lot_size if s2 < put_strike else 0
        else:
            s2_breach_loss = 0

        # Risk at 5% move
        five_pct_up = price * 1.05
        five_pct_down = price * 0.95

        loss_5pct_up = max(0, (five_pct_up - call_strike - total_premium) * lot_size)
        loss_5pct_down = max(0, (put_strike - five_pct_down - total_premium) * lot_size)

        return {
            'position_type': 'Short Strangle',
            'max_profit': round(max_profit, 2),
            'breakeven_upper': round(call_strike + total_premium, 2),
            'breakeven_lower': round(put_strike - total_premium, 2),
            'breach_risks': {
                'r1_breach': {
                    'level': r1,
                    'potential_loss': round(r1_breach_loss, 2) if r1_breach_loss > 0 else 0,
                    'status': 'SAFE' if r1_breach_loss <= 0 else 'AT RISK'
                },
                'r2_breach': {
                    'level': r2,
                    'potential_loss': round(r2_breach_loss, 2) if r2_breach_loss > 0 else 0,
                    'status': 'SAFE' if r2_breach_loss <= 0 else 'AT RISK'
                },
                's1_breach': {
                    'level': s1,
                    'potential_loss': round(s1_breach_loss, 2) if s1_breach_loss > 0 else 0,
                    'status': 'SAFE' if s1_breach_loss <= 0 else 'AT RISK'
                },
                's2_breach': {
                    'level': s2,
                    'potential_loss': round(s2_breach_loss, 2) if s2_breach_loss > 0 else 0,
                    'status': 'SAFE' if s2_breach_loss <= 0 else 'AT RISK'
                },
                'five_pct_move': {
                    'up_level': round(five_pct_up, 2),
                    'down_level': round(five_pct_down, 2),
                    'loss_if_up': round(loss_5pct_up, 2),
                    'loss_if_down': round(loss_5pct_down, 2)
                }
            }
        }

    def _calculate_futures_breach_risk(self, pos: Dict, price: float,
                                      r1: float, r2: float, s1: float, s2: float) -> Dict:
        """Calculate futures risk at S/R breaches"""
        entry_price = pos['entry_price']
        lot_size = pos.get('lot_size', 50)
        direction = pos.get('direction', 'LONG')

        if direction == 'LONG':
            # Long position - risk on downside
            s1_loss = (entry_price - s1) * lot_size if s1 < entry_price else 0
            s2_loss = (entry_price - s2) * lot_size if s2 < entry_price else 0
            five_pct_loss = (entry_price - (price * 0.95)) * lot_size

            return {
                'position_type': 'Long Futures',
                'entry_price': entry_price,
                'direction': direction,
                'breach_risks': {
                    's1_breach': {
                        'level': s1,
                        'potential_loss': round(s1_loss, 2),
                        'loss_pct': round((s1_loss / (entry_price * lot_size) * 100), 2)
                    },
                    's2_breach': {
                        'level': s2,
                        'potential_loss': round(s2_loss, 2),
                        'loss_pct': round((s2_loss / (entry_price * lot_size) * 100), 2)
                    },
                    'five_pct_drop': {
                        'level': round(price * 0.95, 2),
                        'potential_loss': round(five_pct_loss, 2),
                        'loss_pct': 5.0
                    }
                }
            }

        else:  # SHORT
            # Short position - risk on upside
            r1_loss = (r1 - entry_price) * lot_size if r1 > entry_price else 0
            r2_loss = (r2 - entry_price) * lot_size if r2 > entry_price else 0
            five_pct_loss = ((price * 1.05) - entry_price) * lot_size

            return {
                'position_type': 'Short Futures',
                'entry_price': entry_price,
                'direction': direction,
                'breach_risks': {
                    'r1_breach': {
                        'level': r1,
                        'potential_loss': round(r1_loss, 2),
                        'loss_pct': round((r1_loss / (entry_price * lot_size) * 100), 2)
                    },
                    'r2_breach': {
                        'level': r2,
                        'potential_loss': round(r2_loss, 2),
                        'loss_pct': round((r2_loss / (entry_price * lot_size) * 100), 2)
                    },
                    'five_pct_rise': {
                        'level': round(price * 1.05, 2),
                        'potential_loss': round(five_pct_loss, 2),
                        'loss_pct': 5.0
                    }
                }
            }


# Convenience functions

def calculate_nifty_sr(current_price: float) -> Dict:
    """
    Calculate NIFTY Support/Resistance from 1-year historical data

    Args:
        current_price: Current NIFTY price

    Returns:
        dict: Complete S/R analysis
    """
    calculator = SupportResistanceCalculator(symbol='NIFTY', lookback_days=365)
    return calculator.calculate_comprehensive_sr(current_price)


def check_strike_sr_proximity(call_strike: int, put_strike: int, sr_data: Dict) -> Dict:
    """
    Check both strikes for S/R proximity

    Args:
        call_strike: Call strike price
        put_strike: Put strike price
        sr_data: S/R data from calculate_nifty_sr()

    Returns:
        dict: Adjustment recommendations for both strikes
    """
    calculator = SupportResistanceCalculator()

    call_check = calculator.check_strike_proximity_to_sr(call_strike, 'CE', sr_data)
    put_check = calculator.check_strike_proximity_to_sr(put_strike, 'PE', sr_data)

    return {
        'call_adjustment': call_check,
        'put_adjustment': put_check,
        'any_adjustments': call_check['should_adjust'] or put_check['should_adjust']
    }
