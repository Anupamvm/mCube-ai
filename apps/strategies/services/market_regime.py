"""
Market Regime Detection Module

Classifies the current market regime as one of:
TRENDING, RANGING, VOLATILE, BREAKOUT, NORMAL

Uses ADX, ATR expansion, and India VIX to determine regime
with priority ordering: VOLATILE > BREAKOUT > TRENDING > RANGING > NORMAL.
"""

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

REGIME_TRENDING = 'TRENDING'
REGIME_RANGING = 'RANGING'
REGIME_VOLATILE = 'VOLATILE'
REGIME_BREAKOUT = 'BREAKOUT'
REGIME_NORMAL = 'NORMAL'

RECOMMENDATIONS = {
    REGIME_TRENDING: "Strong trend detected — use wider targets, tighter trailing SL",
    REGIME_RANGING: "Range-bound market — use mean-reversion levels, tight SL",
    REGIME_VOLATILE: "High volatility — reduce position size, use wider SL",
    REGIME_BREAKOUT: "Breakout forming — watch for confirmation, use momentum entry",
    REGIME_NORMAL: "Normal conditions — standard parameters apply",
}


class MarketRegimeDetector:
    """Detects current market regime for adaptive trading decisions."""

    def classify(self, symbol='NIFTY') -> dict:
        """
        Classify market regime.

        Returns:
            {
                'regime': str,  # TRENDING, RANGING, VOLATILE, BREAKOUT, NORMAL
                'confidence': float,  # 0-100
                'adx': float or None,
                'atr_expansion': float or None,  # current ATR / 20-day avg ATR
                'vix': float or None,
                'recommendation': str,  # human-readable 1-liner
            }
        """
        adx = None
        atr_expansion = None
        vix = None

        # Step 1: Fetch ADX and ATR from TLStockData
        try:
            from apps.data.models import TLStockData

            stock_data = (
                TLStockData.objects
                .filter(nsecode=symbol, day_adx__isnull=False)
                .order_by('-updated_at')
                .first()
            )
            if stock_data:
                adx = stock_data.day_adx
        except Exception:
            logger.warning("Failed to fetch ADX from TLStockData for %s", symbol, exc_info=True)

        # Step 2: Compute ATR expansion
        try:
            from apps.data.models import TLStockData

            atr_records = (
                TLStockData.objects
                .filter(nsecode=symbol, day_atr__isnull=False)
                .order_by('-updated_at')[:20]
            )
            atr_values = [r.day_atr for r in atr_records if r.day_atr and r.day_atr > 0]

            if atr_values:
                current_atr = atr_values[0]
                if len(atr_values) >= 2:
                    avg_atr = sum(atr_values) / len(atr_values)
                    atr_expansion = round(current_atr / avg_atr, 2) if avg_atr > 0 else 1.0
                else:
                    atr_expansion = 1.0
        except Exception:
            logger.warning("Failed to compute ATR expansion for %s", symbol, exc_info=True)

        # Step 3: Fetch India VIX
        try:
            from apps.strategies.filters.volatility import get_india_vix

            vix_value = get_india_vix()
            if vix_value is not None:
                vix = float(vix_value)
        except Exception:
            logger.warning("Failed to fetch India VIX", exc_info=True)

        # Step 4: Classify regime with priority ordering
        regime, confidence = self._classify_regime(adx, atr_expansion, vix)

        return {
            'regime': regime,
            'confidence': confidence,
            'adx': adx,
            'atr_expansion': atr_expansion,
            'vix': vix,
            'recommendation': RECOMMENDATIONS[regime],
        }

    def _classify_regime(self, adx, atr_expansion, vix):
        """
        Apply classification rules with priority:
        VOLATILE > BREAKOUT > TRENDING > RANGING > NORMAL
        """
        # Check VOLATILE first (highest priority)
        if self._is_volatile(atr_expansion, vix):
            confidence = self._calc_volatile_confidence(atr_expansion, vix)
            return REGIME_VOLATILE, confidence

        # Check BREAKOUT
        if self._is_breakout(adx):
            confidence = self._calc_breakout_confidence(adx)
            return REGIME_BREAKOUT, confidence

        # Check TRENDING
        if self._is_trending(adx, atr_expansion, vix):
            confidence = self._calc_trending_confidence(adx, atr_expansion, vix)
            return REGIME_TRENDING, confidence

        # Check RANGING
        if self._is_ranging(adx, atr_expansion):
            confidence = self._calc_ranging_confidence(adx, atr_expansion)
            return REGIME_RANGING, confidence

        return REGIME_NORMAL, 50.0

    # --- Regime detection rules ---

    def _is_volatile(self, atr_expansion, vix):
        """ATR expansion > 1.5x AND VIX > 16."""
        if atr_expansion is None or vix is None:
            return False
        return atr_expansion > 1.5 and vix > 16

    def _is_breakout(self, adx):
        """
        ADX rising from <20 to 25+.
        With a single snapshot we approximate: ADX in the 20-30 range
        suggests a transition from ranging to trending.
        """
        if adx is None:
            return False
        return 20 <= adx <= 30

    def _is_trending(self, adx, atr_expansion, vix):
        """ADX > 25, ATR expansion < 1.3x, VIX < 18."""
        if adx is None:
            return False
        if adx <= 25:
            return False
        if atr_expansion is not None and atr_expansion >= 1.3:
            return False
        if vix is not None and vix >= 18:
            return False
        return True

    def _is_ranging(self, adx, atr_expansion):
        """ADX < 20, ATR expansion < 1.0x."""
        if adx is None:
            return False
        if adx >= 20:
            return False
        if atr_expansion is not None and atr_expansion >= 1.0:
            return False
        return True

    # --- Confidence calculations ---

    def _calc_volatile_confidence(self, atr_expansion, vix):
        confidence = 60.0
        if atr_expansion is not None and atr_expansion > 2.0:
            confidence += 10
        if vix is not None and vix > 22:
            confidence += 10
        if atr_expansion is not None and atr_expansion > 2.5:
            confidence += 10
        return min(confidence, 95.0)

    def _calc_breakout_confidence(self, adx):
        confidence = 60.0
        if adx is not None and adx >= 25:
            confidence += 10
        if adx is not None and adx >= 28:
            confidence += 10
        return min(confidence, 95.0)

    def _calc_trending_confidence(self, adx, atr_expansion, vix):
        confidence = 60.0
        if adx is not None and adx > 30:
            confidence += 10
        if adx is not None and adx > 35:
            confidence += 10
        if atr_expansion is not None and atr_expansion < 1.0:
            confidence += 10
        return min(confidence, 95.0)

    def _calc_ranging_confidence(self, adx, atr_expansion):
        confidence = 60.0
        if adx is not None and adx < 15:
            confidence += 10
        if atr_expansion is not None and atr_expansion < 0.8:
            confidence += 10
        if adx is not None and adx < 12:
            confidence += 10
        return min(confidence, 95.0)


def get_market_regime(symbol='NIFTY') -> dict:
    """Convenience function to get market regime."""
    return MarketRegimeDetector().classify(symbol)
