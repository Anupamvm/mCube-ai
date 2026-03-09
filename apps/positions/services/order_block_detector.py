"""
Order Block Detector

Scans 5-min candle history for institutional order blocks: the base candle
immediately before a strong impulse move.  These candle zones act as major
S/R because they represent unfilled institutional orders.

Public API:
    OrderBlockDetector(position).detect_blocks(last_n_candles=50) -> dict

Output shape:
    {
        'supports':    [{'price': float, 'score': float, 'source': str, 'ob_strength': int}, ...],
        'resistances': [{'price': float, 'score': float, 'source': str, 'ob_strength': int}, ...],
    }

The returned levels follow the same {'price', 'score', 'source'} schema as
MultiFactorSRCalculator so they can be passed directly to cluster_levels()
for de-duplication with existing levels.

Order block weight = 0.10 (same as hvn, distributed from plan).

Detection criteria:
    1. Base candle body < 40% of next candle body (small pause before big move)
    2. Next candle close > 1.5 × ATR from base open (strong impulse)
    3. Impulse direction defines which zone is the order block:
       - Bullish impulse (close > open next): base candle LOW is support OB
       - Bearish impulse (close < open next): base candle HIGH is resistance OB

Strength scoring (1–3):
    1 = impulse > 1.5 × ATR
    2 = impulse > 2.0 × ATR
    3 = impulse > 3.0 × ATR, and occurred within last 5 days

Never raises — returns empty lists on any error.
"""

import logging
from datetime import datetime, timedelta, timezone as dt_timezone

logger = logging.getLogger(__name__)

ORDER_BLOCK_WEIGHT = 0.10
BASE_BODY_RATIO_MAX = 0.40   # base body < 40% of impulse body
IMPULSE_ATR_MIN = 1.5        # impulse > 1.5 × ATR
IMPULSE_ATR_STRONG = 2.0
IMPULSE_ATR_VERY_STRONG = 3.0
RECENCY_DAYS_FOR_BONUS = 5   # +1 strength for blocks within last 5 days


class OrderBlockDetector:
    """
    Detects institutional order blocks from 5-min candle history.
    """

    def __init__(self, position):
        self._position = position

    def detect_blocks(self, last_n_candles: int = 50) -> dict:
        """
        Returns order block support and resistance zones.
        Never raises.
        """
        try:
            return self._detect(last_n_candles)
        except Exception as e:
            logger.debug(
                f"OrderBlockDetector error for pos #{getattr(self._position, 'id', '?')}: {e}"
            )
            return {'supports': [], 'resistances': []}

    def _detect(self, last_n_candles: int) -> dict:
        candles = self._fetch_candles(last_n_candles)
        if len(candles) < 3:
            return {'supports': [], 'resistances': []}

        atr = self._calc_atr(candles)
        if atr <= 0:
            return {'supports': [], 'resistances': []}

        supports = []
        resistances = []
        now = datetime.now(tz=dt_timezone.utc)
        recency_cutoff = now - timedelta(days=RECENCY_DAYS_FOR_BONUS)

        for i in range(len(candles) - 1):
            base = candles[i]
            impulse = candles[i + 1]

            base_open = float(base['open'])
            base_close = float(base['close'])
            impulse_open = float(impulse['open'])
            impulse_close = float(impulse['close'])
            impulse_high = float(impulse['high'])
            impulse_low = float(impulse['low'])

            base_body = abs(base_close - base_open)
            impulse_body = abs(impulse_close - impulse_open)

            # Skip if either candle has zero body
            if impulse_body <= 0 or base_body <= 0:
                continue

            # Condition 1: base body < 40% of impulse body
            if base_body >= impulse_body * BASE_BODY_RATIO_MAX:
                continue

            # Condition 2: impulse size > IMPULSE_ATR_MIN × ATR
            impulse_size = abs(impulse_close - impulse_open)
            if impulse_size < atr * IMPULSE_ATR_MIN:
                continue

            # Determine strength
            if impulse_size >= atr * IMPULSE_ATR_VERY_STRONG:
                strength = 3
            elif impulse_size >= atr * IMPULSE_ATR_STRONG:
                strength = 2
            else:
                strength = 1

            # Recency bonus
            base_dt = base.get('datetime')
            if base_dt:
                try:
                    if isinstance(base_dt, datetime):
                        if base_dt.tzinfo is None:
                            base_dt = base_dt.replace(tzinfo=dt_timezone.utc)
                        if base_dt >= recency_cutoff:
                            strength = min(strength + 1, 3)
                except Exception:
                    pass

            score = ORDER_BLOCK_WEIGHT * (strength / 3.0)

            # Bullish impulse: base candle HIGH/CLOSE area = support order block
            if impulse_close > impulse_open:
                ob_price = max(float(base['low']), base_open)  # bottom of base = support
                supports.append({
                    'price': ob_price,
                    'score': round(score, 4),
                    'source': 'order_block',
                    'ob_strength': strength,
                })

            # Bearish impulse: base candle LOW/OPEN area = resistance order block
            else:
                ob_price = min(float(base['high']), base_open)  # top of base = resistance
                resistances.append({
                    'price': ob_price,
                    'score': round(score, 4),
                    'source': 'order_block',
                    'ob_strength': strength,
                })

        return {'supports': supports, 'resistances': resistances}

    def _get_symbol(self) -> str:
        from apps.positions.services.sr_exit_engine import _position_symbol
        return _position_symbol(self._position)

    def _fetch_candles(self, n: int) -> list:
        from apps.brokers.models import HistoricalPrice
        symbol = self._get_symbol()
        cutoff = datetime.now(tz=dt_timezone.utc) - timedelta(days=5)
        qs = HistoricalPrice.objects.filter(
            stock_code=symbol, interval='5minute', datetime__gte=cutoff,
        ).order_by('-datetime')[:n]
        candles = [
            {
                'open': float(c.open),
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.close),
                'volume': float(c.volume),
                'datetime': c.datetime,
            }
            for c in qs
        ]
        candles.reverse()
        return candles

    def _calc_atr(self, candles: list, period: int = 14) -> float:
        from apps.positions.services.sr_exit_engine_utils import calculate_atr
        bars = [
            {'high': c['high'], 'low': c['low'], 'close': c['close']}
            for c in candles
        ]
        return calculate_atr(bars, period=period)
