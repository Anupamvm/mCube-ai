from __future__ import annotations
"""
Strategy Integration Layer for S/R Enhancement

Provides strategy-specific signals computed from the enhanced SR data.
All classes are read-only observers — they produce signals and log them,
but never modify positions or send notifications directly.

Public API:
    FuturesStrategyAdapter(position, sr_result).evaluate() -> dict
    StrangleRangeGuard(position, sr_result).evaluate() -> dict
    BrokenIronCondorGuard(position, sr_result).evaluate() -> dict

Signal dicts are added to sr_eval and logged, but have NO effect on the
existing SL/target logic unless tasks.py explicitly reads them.
This allows a shadow-run period where signals are observed without acting.
"""

import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# FuturesStrategyAdapter
# ─────────────────────────────────────────────────────────────────────────────

class FuturesStrategyAdapter:
    """
    Produces signals for directional futures positions (LONG/SHORT).

    Signals:
        breakout_quality: 'STRONG' | 'WEAK' | 'FALSE' | 'UNKNOWN'
        conviction:       float 0–1 — confidence in breakout quality
        trend_continuation: bool — price in sustained trend, avoid premature SL tightening
        breakout_reversal_candidate: bool — strong breakout warrants flip suggestion
    """

    def __init__(self, position, sr_result: dict):
        self._pos = position
        self._sr = sr_result

    def evaluate(self) -> dict:
        try:
            return self._evaluate()
        except Exception as e:
            logger.debug(f"FuturesStrategyAdapter error for pos #{getattr(self._pos, 'id', '?')}: {e}")
            return _empty_futures_signal()

    def _evaluate(self) -> dict:
        result = _empty_futures_signal()

        price = float(self._pos.current_price or 0)
        if not price:
            return result

        atr = float(self._sr.get('atr', 0) or 0)
        vwap = float(self._sr.get('vwap', 0) or 0)
        supports = self._sr.get('supports', [])
        resistances = self._sr.get('resistances', [])

        # ── Trend score (price vs VWAP and structural levels) ────────────────
        trend_score = self._compute_trend_score(price, vwap, supports, resistances)
        result['trend_score'] = trend_score

        # ── Breakout quality assessment ───────────────────────────────────────
        direction = self._pos.direction
        if direction == 'LONG':
            near_level = _nearest_below(price, supports)
        elif direction == 'SHORT':
            near_level = _nearest_above(price, resistances)
        else:
            near_level = None

        if near_level:
            level_score = near_level.get('strength_score', 0)
            p_breakout = self._breakout_probability(trend_score, level_score, atr, price)
            result['breakout_probability'] = round(p_breakout, 3)

            if p_breakout > 0.70 and level_score > 60:
                result['breakout_quality'] = 'STRONG'
                result['conviction'] = min(p_breakout, 0.95)
                if level_score > 75:
                    result['breakout_reversal_candidate'] = True
            elif p_breakout > 0.50:
                result['breakout_quality'] = 'WEAK'
                result['conviction'] = p_breakout
            else:
                result['breakout_quality'] = 'FALSE'
                result['conviction'] = 1.0 - p_breakout

        # ── Trend continuation signal ─────────────────────────────────────────
        # Block premature SL tightening when in a sustained trend
        result['trend_continuation'] = self._is_trend_continuation(price, vwap, supports, resistances)

        return result

    def _compute_trend_score(self, price: float, vwap: float, supports: list, resistances: list) -> float:
        """0 = strongly bearish, 0.5 = neutral, 1 = strongly bullish."""
        score = 0.5

        # VWAP: above = +0.15, below = -0.15
        if vwap and vwap > 0:
            if price > vwap:
                score += 0.15
            else:
                score -= 0.15

        # Support vs resistance balance
        below_count = sum(1 for s in supports if s['price'] < price)
        above_count = sum(1 for r in resistances if r['price'] > price)
        total = below_count + above_count
        if total > 0:
            # More supports below than resistances above = bullish
            ratio = (below_count - above_count) / total
            score += ratio * 0.20

        return max(0.0, min(1.0, score))

    def _breakout_probability(self, trend_score: float, level_score: int,
                              atr: float, price: float) -> float:
        """
        P(breakout) = 0.3 + 0.4×trend + 0.2×vol_exp - 0.3×(confidence/100)
        Volume expansion approximated from ATR % (higher ATR = more expansion).
        """
        atr_pct = atr / price if price else 0
        vol_expansion = min(atr_pct / 0.02, 1.0)  # normalise to 2% ATR = full expansion
        confidence = level_score / 100.0
        p = 0.3 + (0.4 * trend_score) + (0.2 * vol_expansion) - (0.3 * confidence)
        return max(0.0, min(1.0, p))

    def _is_trend_continuation(self, price: float, vwap: float,
                               supports: list, resistances: list) -> bool:
        """
        True when price is in a sustained trend that shouldn't be prematurely stopped.

        Conditions for LONG trend continuation:
            - Price above VWAP
            - Nearest support below has strength_score > 60
            - No strong resistance within 0.5% above price
        """
        direction = self._pos.direction
        if direction not in ('LONG', 'SHORT'):
            return False

        if direction == 'LONG':
            if vwap and price <= vwap:
                return False
            near_support = _nearest_below(price, supports)
            if not near_support or near_support.get('strength_score', 0) < 60:
                return False
            # Check for immediate resistance overhead
            near_resist = _nearest_above(price, resistances)
            if near_resist:
                dist_pct = (near_resist['price'] - price) / price
                if dist_pct < 0.005:  # resistance within 0.5%
                    return False
            return True

        else:  # SHORT
            if vwap and price >= vwap:
                return False
            near_resist = _nearest_above(price, resistances)
            if not near_resist or near_resist.get('strength_score', 0) < 60:
                return False
            near_support = _nearest_below(price, supports)
            if near_support:
                dist_pct = (price - near_support['price']) / price
                if dist_pct < 0.005:
                    return False
            return True


# ─────────────────────────────────────────────────────────────────────────────
# StrangleRangeGuard
# ─────────────────────────────────────────────────────────────────────────────

class StrangleRangeGuard:
    """
    Monitors range integrity for short strangles (NEUTRAL positions).

    Signals:
        range_integrity:    bool — S1 and R1 are structurally sound
        range_warning:      str | None — reason for integrity concern
        early_breakout:     bool — higher-timeframe breach before 5-min confirms
        premium_adj_leg:    str | None — 'CE' | 'PE' | None — which leg to close
        breakout_prob_ce:   float — P(CE leg threatened)
        breakout_prob_pe:   float — P(PE leg threatened)
    """

    def __init__(self, position, sr_result: dict):
        self._pos = position
        self._sr = sr_result

    def evaluate(self) -> dict:
        try:
            return self._evaluate()
        except Exception as e:
            logger.debug(f"StrangleRangeGuard error for pos #{getattr(self._pos, 'id', '?')}: {e}")
            return _empty_strangle_signal()

    def _evaluate(self) -> dict:
        result = _empty_strangle_signal()

        supports = self._sr.get('supports', [])
        resistances = self._sr.get('resistances', [])
        oi_walls = self._sr.get('oi_walls', {})
        price = float(self._pos.current_price or 0)

        if not price:
            return result

        # Get S1 and R1
        s1_level = _nearest_below(price, supports) if supports else None
        r1_level = _nearest_above(price, resistances) if resistances else None

        # Range integrity: both boundaries need score > 40
        s1_score = s1_level.get('strength_score', 0) if s1_level else 0
        r1_score = r1_level.get('strength_score', 0) if r1_level else 0

        if s1_score >= 40 and r1_score >= 40:
            result['range_integrity'] = True
        else:
            result['range_integrity'] = False
            if s1_score < 40:
                result['range_warning'] = f'S1 score weak ({s1_score}/100)'
            elif r1_score < 40:
                result['range_warning'] = f'R1 score weak ({r1_score}/100)'

        # Early breakout detection from MTF (60-min breach)
        mtf_data = self._sr.get('mtf', {})
        if mtf_data:
            result['early_breakout'] = self._check_mtf_breach(price, s1_level, r1_level, mtf_data)

        # Breakout probability for each leg
        atr = float(self._sr.get('atr', 0) or 0)
        if s1_level:
            dist_pe = abs(price - s1_level['price']) / price
            result['breakout_prob_pe'] = round(max(0, 0.5 - dist_pe * 5 + 0.1 * (1 - s1_score / 100)), 3)
        if r1_level:
            dist_ce = abs(r1_level['price'] - price) / price
            result['breakout_prob_ce'] = round(max(0, 0.5 - dist_ce * 5 + 0.1 * (1 - r1_score / 100)), 3)

        # Premium adjustment suggestion
        if result['breakout_prob_ce'] > 0.55:
            result['premium_adj_leg'] = 'CE'
        elif result['breakout_prob_pe'] > 0.55:
            result['premium_adj_leg'] = 'PE'

        return result

    def _check_mtf_breach(self, price: float, s1_level, r1_level, mtf_data: dict) -> bool:
        """Check if 60-min timeframe is already breaching S1 or R1."""
        high_conf_zones = mtf_data.get('high_confluence_zones', [])
        for zone in high_conf_zones:
            zone_mid = (zone['low'] + zone['high']) / 2
            if s1_level and abs(zone_mid - s1_level['price']) / s1_level['price'] < 0.005:
                if price < zone['low']:
                    return True
            if r1_level and abs(zone_mid - r1_level['price']) / r1_level['price'] < 0.005:
                if price > zone['high']:
                    return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# BrokenIronCondorGuard
# ─────────────────────────────────────────────────────────────────────────────

class BrokenIronCondorGuard:
    """
    Monitors range stability and gamma risk for BIC strategies.

    Signals:
        range_stability_score:  int 0–100 — averaged S/R confluence
        bic_entry_valid:        bool — range stable enough for BIC
        gamma_squeeze_risk:     bool — spot near high gamma concentration
        gamma_squeeze_alert:    str | None — description of squeeze zone
        delta_hedge_suggestion: bool — early hedge needed (score dropped <40)
    """

    def __init__(self, position, sr_result: dict):
        self._pos = position
        self._sr = sr_result

    def evaluate(self) -> dict:
        try:
            return self._evaluate()
        except Exception as e:
            logger.debug(f"BrokenIronCondorGuard error for pos #{getattr(self._pos, 'id', '?')}: {e}")
            return _empty_bic_signal()

    def _evaluate(self) -> dict:
        result = _empty_bic_signal()

        supports = self._sr.get('supports', [])
        resistances = self._sr.get('resistances', [])
        oi_walls = self._sr.get('oi_walls', {})
        price = float(self._pos.current_price or 0)

        if not price:
            return result

        # Range stability = average score across top 3 supports and resistances
        top_supports = sorted(supports, key=lambda x: x.get('strength_score', 0), reverse=True)[:3]
        top_resists = sorted(resistances, key=lambda x: x.get('strength_score', 0), reverse=True)[:3]
        all_top = top_supports + top_resists

        if all_top:
            avg_score = sum(l.get('strength_score', 0) for l in all_top) / len(all_top)
            result['range_stability_score'] = int(avg_score)
            result['bic_entry_valid'] = avg_score >= 65
            result['delta_hedge_suggestion'] = avg_score < 40
        else:
            result['range_stability_score'] = 0
            result['bic_entry_valid'] = False
            result['delta_hedge_suggestion'] = True

        # Gamma squeeze: spot near max OI strike with high OI density
        gamma_wall_ce = oi_walls.get('gamma_wall_ce')
        gamma_wall_pe = oi_walls.get('gamma_wall_pe')

        walls_nearby = []
        for wall in [gamma_wall_ce, gamma_wall_pe]:
            if wall:
                dist = abs(price - wall) / price
                if dist < 0.01:  # within 1% of gamma wall
                    walls_nearby.append((wall, dist))

        if walls_nearby:
            closest_wall, dist = min(walls_nearby, key=lambda x: x[1])
            result['gamma_squeeze_risk'] = True
            result['gamma_squeeze_alert'] = (
                f"Spot {price:.2f} within {dist*100:.2f}% of gamma wall {closest_wall:.2f}"
            )

        return result


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _nearest_below(price: float, levels: list) -> dict | None:
    """Return the highest level below price."""
    below = [l for l in levels if l['price'] < price]
    return max(below, key=lambda x: x['price']) if below else None


def _nearest_above(price: float, levels: list) -> dict | None:
    """Return the lowest level above price."""
    above = [l for l in levels if l['price'] > price]
    return min(above, key=lambda x: x['price']) if above else None


def _empty_futures_signal() -> dict:
    return {
        'breakout_quality': 'UNKNOWN',
        'conviction': 0.0,
        'trend_score': 0.5,
        'breakout_probability': 0.0,
        'trend_continuation': False,
        'breakout_reversal_candidate': False,
    }


def _empty_strangle_signal() -> dict:
    return {
        'range_integrity': True,
        'range_warning': None,
        'early_breakout': False,
        'premium_adj_leg': None,
        'breakout_prob_ce': 0.0,
        'breakout_prob_pe': 0.0,
    }


def _empty_bic_signal() -> dict:
    return {
        'range_stability_score': 0,
        'bic_entry_valid': False,
        'gamma_squeeze_risk': False,
        'gamma_squeeze_alert': None,
        'delta_hedge_suggestion': False,
    }


def run_strategy_signals(position, sr_result: dict) -> dict:
    """
    Convenience wrapper: run all three strategy adapters and return combined signals.
    Called optionally from SRExitEngine.evaluate() to populate sr_eval['strategy'].
    """
    direction = getattr(position, 'direction', 'NEUTRAL')

    if direction in ('LONG', 'SHORT'):
        strategy_signals = FuturesStrategyAdapter(position, sr_result).evaluate()
        strategy_signals['type'] = 'FUTURES'
    else:
        # For NEUTRAL: run both strangle and BIC guards
        strangle = StrangleRangeGuard(position, sr_result).evaluate()
        bic = BrokenIronCondorGuard(position, sr_result).evaluate()
        strategy_signals = {
            'type': 'NEUTRAL',
            'strangle': strangle,
            'bic': bic,
        }

    return strategy_signals
