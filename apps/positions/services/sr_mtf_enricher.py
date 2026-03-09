"""
Multi-Timeframe S/R Enricher

Computes swing highs and lows across four timeframes and returns a
`mtf_confluence` mapping that LevelStrengthAnnotator uses to boost the
confidence score of levels confirmed by multiple timeframes.

Public API:
    MTFSREnricher(position).compute_mtf_stacking() -> dict

Output shape:
    {
        'levels': {
            <price_bucket>: {
                'timeframes': ['5min', '15min'],
                'confluence_count': 2,
                'high_confluence': False,
            },
            ...
        },
        'high_confluence_zones': [{'low': float, 'high': float}, ...],
    }

Design notes:
    - Tolerates missing data for any single timeframe (skips silently).
    - Results are pure Python — no Django model writes.
    - Intended to be called from SRExitEngine._get_or_refresh_sr_cache()
      and the result stored alongside sr_cache in sr_tracking.
    - Never raises — all errors return empty dict.
"""

import logging
from datetime import datetime, timedelta, timezone as dt_timezone

logger = logging.getLogger(__name__)

# Timeframe config: (label, interval, lookback_bars, weight)
_TIMEFRAMES = [
    ('5min',  '5minute',  20, 0.20),
    ('15min', '15minute', 20, 0.30),
    ('60min', '60minute', 20, 0.30),
    ('1day',  '1day',     20, 0.20),
]

# Two levels agree if within this fraction of each other
CONFLUENCE_TOLERANCE_PCT = 0.005  # 0.5%

# Minimum number of timeframes agreeing to be "high confluence"
HIGH_CONFLUENCE_MIN = 3


class MTFSREnricher:
    """
    Enriches existing S/R levels with multi-timeframe confirmation.

    Does NOT replace the existing MultiFactorSRCalculator output.
    Adds a `mtf_confluence` sub-dict that LevelStrengthAnnotator reads to
    add up to 20 pts to each level's confidence score.
    """

    def __init__(self, position):
        self._position = position

    def compute_mtf_stacking(self) -> dict:
        """
        Returns MTF confluence data for the current position.
        Never raises.
        """
        try:
            return self._compute()
        except Exception as e:
            logger.debug(f"MTFSREnricher error for pos #{getattr(self._position, 'id', '?')}: {e}")
            return {'levels': {}, 'high_confluence_zones': []}

    def _compute(self) -> dict:
        symbol = self._get_symbol()
        all_levels = []   # list of (price, timeframe_label, weight)

        for label, interval, bars, weight in _TIMEFRAMES:
            try:
                candles = self._fetch_candles(symbol, interval, bars)
                if len(candles) < 2:
                    continue
                highs = [float(c['high']) for c in candles]
                lows = [float(c['low']) for c in candles]
                swing_high = max(highs)
                swing_low = min(lows)
                if swing_high > 0:
                    all_levels.append((swing_high, label, weight))
                if swing_low > 0:
                    all_levels.append((swing_low, label, weight))
            except Exception as e:
                logger.debug(f"MTFSREnricher [{label}] error: {e}")

        if not all_levels:
            return {'levels': {}, 'high_confluence_zones': []}

        # Cluster levels across timeframes
        avg_price = sum(p for p, _, _ in all_levels) / len(all_levels)
        bucket_width = avg_price * CONFLUENCE_TOLERANCE_PCT

        # Group into confluence buckets
        buckets: dict = {}  # bucket_price → {timeframes: set, total_weight: float}
        for price, tf_label, weight in all_levels:
            bk = round(price / bucket_width) * bucket_width
            if bk not in buckets:
                buckets[bk] = {'timeframes': set(), 'total_weight': 0.0}
            buckets[bk]['timeframes'].add(tf_label)
            buckets[bk]['total_weight'] += weight

        result_levels = {}
        high_confluence_zones = []

        for bk_price, data in buckets.items():
            tf_list = sorted(data['timeframes'])
            count = len(tf_list)
            is_high = count >= HIGH_CONFLUENCE_MIN
            result_levels[bk_price] = {
                'timeframes': tf_list,
                'confluence_count': count,
                'total_weight': round(data['total_weight'], 3),
                'high_confluence': is_high,
            }
            if is_high:
                half_width = bucket_width * 0.5
                high_confluence_zones.append({
                    'low': bk_price - half_width,
                    'high': bk_price + half_width,
                    'confluence_count': count,
                })

        return {
            'levels': result_levels,
            'high_confluence_zones': high_confluence_zones,
        }

    def _get_symbol(self) -> str:
        from apps.positions.services.sr_exit_engine import _position_symbol
        return _position_symbol(self._position)

    def _fetch_candles(self, symbol: str, interval: str, bars: int) -> list:
        """Fetch OHLCV candles from HistoricalPrice. Never raises."""
        from apps.brokers.models import HistoricalPrice
        # For intraday intervals: fetch last N bars from past 5 days
        if interval in ('5minute', '15minute', '60minute'):
            cutoff = datetime.now(tz=dt_timezone.utc) - timedelta(days=5)
            qs = HistoricalPrice.objects.filter(
                stock_code=symbol, interval=interval, datetime__gte=cutoff,
            ).order_by('-datetime')[:bars]
        else:
            qs = HistoricalPrice.objects.filter(
                stock_code=symbol, interval=interval,
            ).order_by('-datetime')[:bars]

        candles = [
            {'high': float(c.high), 'low': float(c.low),
             'close': float(c.close), 'volume': float(c.volume)}
            for c in qs
        ]
        candles.reverse()
        return candles


def get_level_mtf_confluence(level_price: float, mtf_data: dict) -> dict:
    """
    Check if a given level price is confirmed by MTF data.

    Args:
        level_price: price of the S/R level to check
        mtf_data: output of MTFSREnricher.compute_mtf_stacking()

    Returns:
        {'confluence_count': int, 'high_confluence': bool, 'timeframes': list}
        Returns zero-count dict if no match found.
    """
    if not mtf_data or not level_price:
        return {'confluence_count': 0, 'high_confluence': False, 'timeframes': []}

    best_match = None
    best_distance = float('inf')

    for bk_price, data in mtf_data.get('levels', {}).items():
        dist = abs(bk_price - level_price) / level_price if level_price else float('inf')
        if dist <= CONFLUENCE_TOLERANCE_PCT and dist < best_distance:
            best_distance = dist
            best_match = data

    if best_match:
        return {
            'confluence_count': best_match['confluence_count'],
            'high_confluence': best_match['high_confluence'],
            'timeframes': best_match['timeframes'],
        }

    return {'confluence_count': 0, 'high_confluence': False, 'timeframes': []}
