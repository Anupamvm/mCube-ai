"""
Level Strength Annotator + Confidence Scorer

Enriches clustered S/R levels with a 0–100 confidence score that drives
the score-gated trigger rules in SLTriggerChecker.

Public API:
    LevelStrengthAnnotator(position).annotate(levels, mtf_data) -> list
    LevelConfidenceScorer().score(level, sr_result) -> int
    estimate_retest_probability(level_price, candles, trend_score, volume_expansion) -> float

Score Components (total = 100 pts):
    source_agreement  25 pts  — how many of 8 sources agree on this level
    mtf_confluence    20 pts  — multi-timeframe alignment (from MTFSREnricher)
    touch_history     20 pts  — number of historical price reactions (bounces)
    oi_reinforcement  15 pts  — OI wall / gamma wall proximity
    volume_at_level   10 pts  — HVN score at this price zone
    recency           10 pts  — days since last touch (decays 2 pts/day)

Score → Trigger Rule Mapping:
    0–30    Weak:          Both A+B + 15-min recovery required
    31–55   Moderate:      Both A+B required (volume filter softened)
    56–75   Strong:        Either A or B + 15-min is sufficient
    76–100  Institutional: Condition A alone triggers (single confirmation)
"""

import logging
from datetime import datetime, timedelta, timezone as dt_timezone

logger = logging.getLogger(__name__)

# Score component weights (sum = 100)
_COMPONENT_MAX = {
    'source_agreement': 25,
    'mtf_confluence':   20,
    'touch_history':    20,
    'oi_reinforcement': 15,
    'volume_at_level':  10,
    'recency':          10,
}

# Touch detection tolerance: level within 0.3% = a "touch"
TOUCH_TOLERANCE_PCT = 0.003

# How many days back to scan for touch history
TOUCH_HISTORY_DAYS = 20

# Recency decay: 2 pts per day since last touch; floors at 0
RECENCY_DECAY_PER_DAY = 2.0


class LevelStrengthAnnotator:
    """
    Annotates each clustered S/R level with a `strength_score` (0–100).

    Takes the output of MultiFactorSRCalculator.compute() (list of levels
    with 'price', 'score', 'source') and adds:
        - 'strength_score': int 0–100
        - 'score_breakdown': dict (components contributing to strength_score)
        - 'high_confluence': bool (MTF confluence flag)
        - 'touch_count': int (historical bounces within TOUCH_TOLERANCE_PCT)

    Never modifies the original level list — returns a new list.
    """

    def __init__(self, position):
        self._position = position

    def annotate(self, levels: list, mtf_data: dict = None, oi_walls: dict = None) -> list:
        """
        Args:
            levels:    list from cluster_levels() — [{'price', 'score', 'source'}, ...]
            mtf_data:  output of MTFSREnricher.compute_mtf_stacking() (optional)
            oi_walls:  output of OIWallEnricher.compute_walls() (optional)

        Returns:
            New list with each level dict extended with strength_score, etc.
        """
        if not levels:
            return []

        try:
            candles_20d = self._fetch_20d_candles()
        except Exception as e:
            logger.debug(f"LevelStrengthAnnotator: candle fetch error: {e}")
            candles_20d = []

        scorer = LevelConfidenceScorer()
        annotated = []

        for level in levels:
            try:
                enriched = dict(level)  # copy
                score_info = scorer.score(
                    level_price=level['price'],
                    source_str=level.get('source', ''),
                    mtf_data=mtf_data or {},
                    oi_walls=oi_walls or {},
                    candles_20d=candles_20d,
                )
                enriched['strength_score'] = score_info['total']
                enriched['score_breakdown'] = score_info['breakdown']
                enriched['high_confluence'] = score_info.get('high_confluence', False)
                enriched['touch_count'] = score_info.get('touch_count', 0)
                annotated.append(enriched)
            except Exception as e:
                logger.debug(f"LevelStrengthAnnotator: level annotation error: {e}")
                enriched = dict(level)
                enriched['strength_score'] = 0
                enriched['score_breakdown'] = {}
                enriched['high_confluence'] = False
                enriched['touch_count'] = 0
                annotated.append(enriched)

        return annotated

    def _fetch_20d_candles(self) -> list:
        from apps.brokers.models import HistoricalPrice
        from apps.positions.services.sr_exit_engine import _position_symbol
        symbol = _position_symbol(self._position)
        cutoff = datetime.now(tz=dt_timezone.utc) - timedelta(days=TOUCH_HISTORY_DAYS)
        qs = HistoricalPrice.objects.filter(
            stock_code=symbol, interval='5minute', datetime__gte=cutoff,
        ).order_by('datetime').values('high', 'low', 'close', 'volume', 'datetime')
        return [
            {
                'high': float(c['high']),
                'low': float(c['low']),
                'close': float(c['close']),
                'volume': float(c['volume']),
                'datetime': c['datetime'],
            }
            for c in qs
        ]


class LevelConfidenceScorer:
    """
    Stateless scorer — call score() per level.
    """

    def score(self, level_price: float, source_str: str,
              mtf_data: dict, oi_walls: dict, candles_20d: list) -> dict:
        """
        Compute 0–100 confidence score for a single S/R level.

        Returns:
            {
                'total': int,
                'breakdown': {component: pts, ...},
                'high_confluence': bool,
                'touch_count': int,
            }
        """
        breakdown = {}
        high_confluence = False
        touch_count = 0

        try:
            # 1. Source agreement (max 25 pts)
            # source_str is like 'pivot+vwap+hvn'
            parts = [s.strip() for s in source_str.split('+') if s.strip()]
            source_count = len(parts)
            src_pts = min(source_count * 4, _COMPONENT_MAX['source_agreement'])
            breakdown['source_agreement'] = src_pts
        except Exception:
            breakdown['source_agreement'] = 0

        try:
            # 2. MTF confluence (max 20 pts, 5 pts per confirming timeframe)
            from apps.positions.services.sr_mtf_enricher import get_level_mtf_confluence
            mtf_info = get_level_mtf_confluence(level_price, mtf_data)
            mtf_count = mtf_info.get('confluence_count', 0)
            mtf_pts = min(mtf_count * 5, _COMPONENT_MAX['mtf_confluence'])
            breakdown['mtf_confluence'] = mtf_pts
            high_confluence = mtf_info.get('high_confluence', False)
        except Exception:
            breakdown['mtf_confluence'] = 0

        try:
            # 3. Touch history (max 20 pts, 5 pts per touch up to 4 touches)
            touch_count = _count_touches(level_price, candles_20d)
            touch_pts = min(touch_count * 5, _COMPONENT_MAX['touch_history'])
            breakdown['touch_history'] = touch_pts
        except Exception:
            breakdown['touch_history'] = 0

        try:
            # 4. OI reinforcement (max 15 pts)
            oi_pts = _oi_reinforcement_pts(level_price, oi_walls)
            breakdown['oi_reinforcement'] = oi_pts
        except Exception:
            breakdown['oi_reinforcement'] = 0

        try:
            # 5. Volume at level / HVN score (max 10 pts)
            hvn_pts = _hvn_score_pts(level_price, candles_20d)
            breakdown['volume_at_level'] = hvn_pts
        except Exception:
            breakdown['volume_at_level'] = 0

        try:
            # 6. Recency decay (max 10 pts, -2 pts/day since last touch)
            days_since = _days_since_last_touch(level_price, candles_20d)
            recency_pts = max(0, _COMPONENT_MAX['recency'] - int(days_since * RECENCY_DECAY_PER_DAY))
            breakdown['recency'] = recency_pts
        except Exception:
            breakdown['recency'] = 0

        total = min(sum(breakdown.values()), 100)
        return {
            'total': total,
            'breakdown': breakdown,
            'high_confluence': high_confluence,
            'touch_count': touch_count,
        }


# ── Helper functions (no Django, pure Python) ─────────────────────────────────

def _count_touches(level_price: float, candles: list) -> int:
    """
    Count how many times price touched (approached within TOUCH_TOLERANCE_PCT
    then reversed) the level over the candle history.

    A "touch" = a candle whose low/high came within tolerance of the level,
    followed by a candle that moved away (opposite direction).
    """
    if not candles or not level_price:
        return 0

    tolerance = level_price * TOUCH_TOLERANCE_PCT
    touches = 0
    was_near = False

    for i, c in enumerate(candles):
        low = float(c['low'])
        high = float(c['high'])
        near_level = (low <= level_price + tolerance) and (high >= level_price - tolerance)

        if near_level and not was_near:
            # Entering touch zone
            was_near = True
        elif not near_level and was_near:
            # Left the touch zone — counts as one bounce
            touches += 1
            was_near = False

    return touches


def _days_since_last_touch(level_price: float, candles: list) -> float:
    """
    Returns fractional days since the last candle that touched the level.
    Returns TOUCH_HISTORY_DAYS if no touch found (max decay).
    """
    if not candles or not level_price:
        return float(TOUCH_HISTORY_DAYS)

    tolerance = level_price * TOUCH_TOLERANCE_PCT
    now = datetime.now(tz=dt_timezone.utc)

    for c in reversed(candles):
        low = float(c['low'])
        high = float(c['high'])
        if (low <= level_price + tolerance) and (high >= level_price - tolerance):
            candle_dt = c.get('datetime')
            if candle_dt:
                try:
                    if isinstance(candle_dt, datetime):
                        if candle_dt.tzinfo is None:
                            candle_dt = candle_dt.replace(tzinfo=dt_timezone.utc)
                        return (now - candle_dt).total_seconds() / 86400.0
                except Exception:
                    pass
            return 0.0  # found but no timestamp — treat as recent

    return float(TOUCH_HISTORY_DAYS)


def _oi_reinforcement_pts(level_price: float, oi_walls: dict) -> int:
    """
    Award up to 15 pts based on proximity to OI gamma wall.

    oi_walls shape (from OIWallEnricher):
        {'gamma_wall_ce': float, 'gamma_wall_pe': float,
         'near_expiry_wall': float, 'far_expiry_wall': float}
    """
    if not oi_walls or not level_price:
        return 0

    walls = [
        oi_walls.get('gamma_wall_ce'),
        oi_walls.get('gamma_wall_pe'),
        oi_walls.get('near_expiry_wall'),
    ]
    walls = [float(w) for w in walls if w]

    if not walls:
        return 0

    min_dist = min(abs(w - level_price) / level_price for w in walls)
    if min_dist < 0.005:     # within 0.5%
        return 15
    elif min_dist < 0.010:   # within 1.0%
        return 8
    elif min_dist < 0.020:   # within 2.0%
        return 3
    return 0


def _hvn_score_pts(level_price: float, candles: list) -> int:
    """
    Compute a 0–10 score based on relative volume concentration near this level.
    Uses same logic as detect_hvn_levels() but returns pts for this specific level.
    """
    if not candles or not level_price:
        return 0

    try:
        from apps.positions.services.sr_exit_engine_utils import detect_hvn_levels
        hvn = detect_hvn_levels(candles, n_levels=10, bucket_pct=0.001)
        if not hvn:
            return 0
        tolerance = level_price * 0.003  # 0.3%
        for node in hvn:
            if abs(node['price'] - level_price) <= tolerance:
                # score is volume/avg_volume ratio; map to 0–10 pts
                raw_score = node.get('score', 0)
                return min(int(raw_score * 3), 10)
        return 0
    except Exception:
        return 0


def estimate_retest_probability(
    level_price: float,
    candles: list,
    trend_score: float = 0.5,
    volume_expansion: float = 0.5,
    is_psychological: bool = False,
    oi_nearby: bool = False,
) -> float:
    """
    Estimate probability (0–1) that price will react to this level again.

    Args:
        level_price:        Price of the S/R level.
        candles:            20-day 5-min candle history.
        trend_score:        0–1, directional strength away from level.
                            0 = strongly against level, 1 = strongly toward.
        volume_expansion:   0–1, current volume vs 20-bar avg normalised.
        is_psychological:   True if level is a round number.
        oi_nearby:          True if OI wall within 0.5% of level.

    Returns:
        float in [0.0, 1.0]
    """
    touch_count = _count_touches(level_price, candles)

    # Base probability from historical touches (3 touches → ~70%)
    base = min(0.3 + touch_count * 0.13, 0.70)

    # Modifiers
    if is_psychological:
        base += 0.10
    if oi_nearby:
        base += 0.10
    if trend_score > 0.7:  # strongly directional away from level
        base -= 0.15

    return max(0.0, min(1.0, base))
