"""
S/R Exit Engine — Multi-Factor Stop-Loss and Target Engine

Public API (functions called from outside this module):
    apply_sl_and_target(position, dashboard, now=None) -> dict
    compute_initial_sl_target(symbol, price, direction)  -> dict

Architecture (internal):
    IntraDayTracker          — thin JSONField wrapper (session state)
    MultiFactorSRCalculator  — 8-source weighted S/R (15-min cached)
    GapDownFilter            — extends noise window on gap opens
    SLTriggerChecker         — two-condition rule enforcer (direction-aware)
    TargetCalculator         — ATR-scaled target (direction-aware)
    SRExitEngine             — orchestrator

Call flow:
    positions/tasks.py — once per position, per monitor cycle
      └── apply_sl_and_target(position, dashboard, now)
            └── IntraDayTracker(dashboard)
            └── SRExitEngine(position, tracker, now).evaluate()
                  ├── MultiFactorSRCalculator.compute()   [cached 15 min]
                  ├── GapDownFilter.detect_gap()          [cached in tracker]
                  ├── SLTriggerChecker.should_trigger_sl()
                  └── TargetCalculator.calculate()

SL Rule — BOTH must be true per direction:
    LONG:    A: price ≤ support × 0.995   B: session_low  ≤ support   × 0.990
    SHORT:   A: price ≥ resist × 1.005    B: session_high ≥ resistance × 1.010
    NEUTRAL: either direction above triggers (spot breaks S1 or R1)

Target Rule:
    LONG:    target = nearest_resistance × (1 − ATR-scaled offset)
    SHORT:   target = nearest_support    × (1 + ATR-scaled offset)
    NEUTRAL: None (premium-decay target set by strategy)
    Offset: 0.3% (low vol) → 0.5% (high vol)
"""

import logging
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

# ── Underlying symbol helpers ─────────────────────────────────────────────────

_EXPIRY_RE = re.compile(r'^([A-Z&]+)\d{2}[A-Z]{3}(FUT|CE|PE)\d*$')


def _position_symbol(pos) -> str:
    """
    Extract the underlying symbol from any position-like object.

    Handles:
    - _LightweightPos (has .symbol)
    - Real Position model (has .display_name and .instrument)
    - Anything with .stock_code as fallback

    Returns the HistoricalPrice stock_code (Breeze code) for DB queries.
    E.g. HDFCBANK26MARFUT → HDFCBANK → mapped to HDFBAN (Breeze storage code).
    """
    # _LightweightPos or anything with explicit .symbol attribute
    sym = getattr(pos, 'symbol', None)
    if sym:
        return _to_historical_code(sym)

    # Real Position: prefer display_name (e.g. HDFCBANK26MARFUT → HDFCBANK)
    dn = getattr(pos, 'display_name', None)
    if dn:
        m = _EXPIRY_RE.match(dn)
        if m:
            return _to_historical_code(m.group(1))

    # Fall back to instrument (may be broker-specific code like HDFBAN)
    raw = getattr(pos, 'instrument', None) or getattr(pos, 'stock_code', 'NIFTY')
    return _to_historical_code(raw)


# NSE code → Breeze HistoricalPrice stock_code (add entries as needed)
_NSE_TO_BREEZE: dict = {
    'HDFCBANK': 'HDFBAN',
}


def _to_historical_code(symbol: str) -> str:
    """Map NSE/display symbol to the stock_code used in HistoricalPrice table."""
    return _NSE_TO_BREEZE.get(symbol, symbol)


# Reverse mapping: Breeze HistoricalPrice code → NSE/ContractData code
_BREEZE_TO_NSE: dict = {v: k for k, v in _NSE_TO_BREEZE.items()}


def _to_oi_code(symbol: str) -> str:
    """Map Breeze HistoricalPrice code back to NSE code for ContractData/OI queries."""
    return _BREEZE_TO_NSE.get(symbol, symbol)


def _position_oi_symbol(pos) -> str:
    """Return the ContractData/OI symbol (NSE code) for a position."""
    return _to_oi_code(_position_symbol(pos))


def _fetch_spot_price(symbol: str, fallback: float) -> float:
    """
    Return the underlying spot price from the latest options chain data.

    S/R levels are computed from equity spot data, so using the spot price
    ensures 'nearest support below' resolves against the correct reference.

    Only uses ContractData.spot if it was updated today (during live market
    hours).  Stale spot (from a previous session) would skew level selection
    relative to today's actual price, so we fall back to the futures CMP in
    that case — the basis is typically <0.5% so levels remain accurate.

    Never raises.
    """
    try:
        from django.utils import timezone as tz
        from apps.data.models import ContractData
        today = tz.localtime(tz.now()).date()
        contract = ContractData.objects.filter(
            symbol=symbol,
            spot__isnull=False,
            updated_at__date=today,
        ).order_by('-updated_at').first()
        if contract and contract.spot:
            spot = float(contract.spot)
            if spot > 0:
                return spot
    except Exception:
        pass
    return fallback

# ─── constants ───────────────────────────────────────────────────────────────
SR_CACHE_TTL_MINUTES = 15
CONDITION_A_PCT = 0.005   # 0.5% — price must breach reference level by this much
CONDITION_B_PCT = 0.010   # 1.0% — session extreme must have traded this far through
VOLUME_MULTIPLIER = 1.2   # current 5-min volume > 1.2x prior 19-bar avg (soft filter)
NOISE_WINDOW_START_HOUR = 9
NOISE_WINDOW_START_MIN = 30   # block SL before 09:30 IST
GAP_NOISE_EXTENSION_MINS = 15  # extend to 09:45 on gap open
GAP_THRESHOLD = 0.010     # 1.0% gap qualifies as a gap day
VIX_SPIKE_THRESHOLD = 0.20  # 20% intraday VIX spike → immediate NEUTRAL SL

SR_SOURCE_WEIGHTS = {
    'pivot': 0.20,
    'prev_day_hl': 0.15,
    'swing_hl': 0.15,
    'vwap': 0.15,
    'moving_averages': 0.15,
    'hvn': 0.10,
    'atr_zones': 0.05,
    'psychological': 0.05,
}

# Source weights when OI data is unavailable (redistribute OI weight to swing+hvn)
SR_SOURCE_WEIGHTS_NO_OI = {
    'pivot': 0.20,
    'prev_day_hl': 0.15,
    'swing_hl': 0.20,
    'vwap': 0.15,
    'moving_averages': 0.15,
    'hvn': 0.10,
    'atr_zones': 0.05,
    'psychological': 0.05,
}

# Enhancement cache TTL for OI walls (faster than base SR)
OI_WALL_CACHE_TTL_MINUTES = 5

# Confidence score thresholds for score-gated trigger rules
SCORE_INSTITUTIONAL = 76    # single Condition A triggers
SCORE_STRONG = 56           # either A or B + 15-min
SCORE_MODERATE = 31         # both A+B required

# Expiry day gamma mode: hours (IST) before which thresholds are widened
EXPIRY_GAMMA_MODE_HOUR = 14  # 14:00 IST


# ─────────────────────────────────────────────────────────────────────────────
# IntraDayTracker
# ─────────────────────────────────────────────────────────────────────────────

class IntraDayTracker:
    """
    Thin wrapper around PositionMonitorDashboard.sr_tracking JSONField.

    Persists intraday state (session extremes, SR cache, gap flag) without
    touching any other dashboard fields.
    """

    def __init__(self, dashboard):
        self._dashboard = dashboard
        self._data: dict = dashboard.sr_tracking or {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def save(self):
        self._dashboard.sr_tracking = self._data
        self._dashboard.save(update_fields=['sr_tracking'])


# ─────────────────────────────────────────────────────────────────────────────
# MultiFactorSRCalculator
# ─────────────────────────────────────────────────────────────────────────────

class MultiFactorSRCalculator:
    """
    Computes weighted S/R levels from 8 sources.

    Levels within 0.3% of each other are merged (scores summed).
    Result is cached for SR_CACHE_TTL_MINUTES in the IntraDayTracker.
    """

    def __init__(self, position, tracker: IntraDayTracker):
        self._position = position
        self._tracker = tracker

    def compute(self) -> dict:
        """
        Returns:
            {
                'supports':    [{'price': float, 'score': float, 'source': str}, ...],
                'resistances': [{'price': float, 'score': float, 'source': str}, ...],
                'atr':  float,
                'vwap': float,
            }
        """
        from apps.positions.services.sr_exit_engine_utils import cluster_levels

        raw_supports = []
        raw_resistances = []
        atr_value = 0.0
        vwap_value = 0.0

        sources = [
            ('_get_pivot_sr',          'pivot',           None),
            ('_get_prev_day_hl',       'prev_day_hl',     None),
            ('_get_swing_hl',          'swing_hl',        None),
            ('_get_vwap_bands',        'vwap',            True),   # True = returns (vwap, s, r)
            ('_get_moving_averages',   'moving_averages', None),
            ('_get_hvn_levels',        'hvn',             None),
            ('_get_atr_zones',         'atr_zones',       True),   # True = returns (atr, s, r)
            ('_get_psychological_levels', 'psychological', None),
        ]

        for method_name, source_key, has_extra in sources:
            weight = SR_SOURCE_WEIGHTS[source_key]
            try:
                result = getattr(self, method_name)()
                if has_extra:
                    extra, s_list, r_list = result
                    if source_key == 'vwap' and extra:
                        vwap_value = extra
                    elif source_key == 'atr_zones' and extra:
                        atr_value = extra
                else:
                    s_list, r_list = result
                raw_supports.extend(_tag(s_list, source_key, weight))
                raw_resistances.extend(_tag(r_list, source_key, weight))
            except Exception as e:
                logger.debug(f"SR source '{source_key}' error: {e}")

        return {
            'supports': cluster_levels(raw_supports),
            'resistances': cluster_levels(raw_resistances),
            'atr': atr_value,
            'vwap': vwap_value,
        }

    def compute_enhanced(self) -> dict:
        """
        Extended compute that runs the base 8-source computation, then layers
        on MTF enrichment, order blocks, OI walls, level strength annotation,
        liquidity vacuums, and market regime flags.

        Returns the same shape as compute() plus:
            'mtf':           MTFSREnricher output
            'oi_walls':      OIWallEnricher output
            'vacuums':       list of liquidity gap dicts
            'market_regime': {low_liquidity, expiry_day, volatility_event}
            'strategy':      strategy signal dict (shadow-run only)

        Falls back to base compute() if any enrichment step fails.
        """
        from apps.positions.services.sr_exit_engine_utils import (
            cluster_levels as _cluster_levels,
            detect_liquidity_gaps,
        )

        # Step 1: Base 8-source SR (always)
        base = self.compute()

        # Step 2: MTF enrichment (15-min cache in tracker)
        mtf_data = {}
        try:
            mtf_cache_key = 'mtf_cache'
            cached_mtf = self._tracker.get(mtf_cache_key)
            last_mtf = self._tracker.get('last_mtf_computed_at')
            now_iso = _ist_now().isoformat()
            stale = True
            if cached_mtf and last_mtf:
                try:
                    age_min = (_ist_now() - datetime.fromisoformat(last_mtf)).total_seconds() / 60
                    stale = age_min >= SR_CACHE_TTL_MINUTES
                except Exception:
                    pass
            if stale:
                from apps.positions.services.sr_mtf_enricher import MTFSREnricher
                mtf_data = MTFSREnricher(self._position).compute_mtf_stacking()
                self._tracker.set(mtf_cache_key, mtf_data)
                self._tracker.set('last_mtf_computed_at', now_iso)
            else:
                mtf_data = cached_mtf or {}
        except Exception as e:
            logger.debug(f"SR enhanced: MTF error: {e}")

        # Step 3: Order block detection (15-min cache)
        ob_supports = []
        ob_resistances = []
        try:
            ob_cache_key = 'ob_cache'
            cached_ob = self._tracker.get(ob_cache_key)
            last_ob = self._tracker.get('last_ob_computed_at')
            stale_ob = True
            if cached_ob and last_ob:
                try:
                    age_min = (_ist_now() - datetime.fromisoformat(last_ob)).total_seconds() / 60
                    stale_ob = age_min >= SR_CACHE_TTL_MINUTES
                except Exception:
                    pass
            if stale_ob:
                from apps.positions.services.order_block_detector import OrderBlockDetector
                ob_result = OrderBlockDetector(self._position).detect_blocks(last_n_candles=50)
                ob_supports = ob_result.get('supports', [])
                ob_resistances = ob_result.get('resistances', [])
                self._tracker.set(ob_cache_key, ob_result)
                self._tracker.set('last_ob_computed_at', _ist_now().isoformat())
            else:
                ob_result = cached_ob or {}
                ob_supports = ob_result.get('supports', [])
                ob_resistances = ob_result.get('resistances', [])
        except Exception as e:
            logger.debug(f"SR enhanced: order block error: {e}")

        # Step 4: OI wall enrichment (5-min cache via its own TTL logic)
        oi_walls = {}
        try:
            from apps.positions.services.oi_wall_enricher import OIWallEnricher
            oi_walls = OIWallEnricher(self._position).compute_walls(self._tracker)
        except Exception as e:
            logger.debug(f"SR enhanced: OI wall error: {e}")

        # Step 5: Merge order blocks + OI walls into base levels, re-cluster
        merged_supports = base['supports'] + ob_supports + oi_walls.get('supports', [])
        merged_resistances = base['resistances'] + ob_resistances + oi_walls.get('resistances', [])
        merged_supports = _cluster_levels(merged_supports)
        merged_resistances = _cluster_levels(merged_resistances)

        # Step 6: Annotate with strength scores
        try:
            from apps.positions.services.sr_level_strength import LevelStrengthAnnotator
            annotator = LevelStrengthAnnotator(self._position)
            merged_supports = annotator.annotate(merged_supports, mtf_data, oi_walls)
            merged_resistances = annotator.annotate(merged_resistances, mtf_data, oi_walls)
        except Exception as e:
            logger.debug(f"SR enhanced: annotation error: {e}")

        # Step 7: Liquidity vacuums from today's 5-min candles
        vacuums = []
        try:
            from apps.brokers.models import HistoricalPrice
            from django.utils import timezone
            today = timezone.now().date()
            candles_qs = HistoricalPrice.objects.filter(
                stock_code=_position_symbol(self._position),
                interval='5minute',
                datetime__date=today,
            ).order_by('datetime')
            candles = [
                {'high': float(c.high), 'low': float(c.low),
                 'close': float(c.close), 'volume': float(c.volume)}
                for c in candles_qs
            ]
            if candles:
                vacuums = detect_liquidity_gaps(candles)
        except Exception as e:
            logger.debug(f"SR enhanced: vacuum detection error: {e}")

        # Step 8: Market regime flags
        market_regime = self._detect_market_regime()

        # Step 9: Strategy signals (shadow run — observe, don't act)
        strategy_signals = {}
        try:
            from apps.positions.services.sr_strategy_adapter import run_strategy_signals
            enhanced_sr = {
                'supports': merged_supports,
                'resistances': merged_resistances,
                'atr': base['atr'],
                'vwap': base['vwap'],
                'oi_walls': oi_walls,
                'mtf': mtf_data,
            }
            strategy_signals = run_strategy_signals(self._position, enhanced_sr)
        except Exception as e:
            logger.debug(f"SR enhanced: strategy signals error: {e}")

        return {
            'supports':      merged_supports,
            'resistances':   merged_resistances,
            'atr':           base['atr'],
            'vwap':          base['vwap'],
            'mtf':           mtf_data,
            'oi_walls':      oi_walls,
            'vacuums':       vacuums,
            'market_regime': market_regime,
            'strategy':      strategy_signals,
        }

    def _detect_market_regime(self) -> dict:
        """Detect market regime flags: low_liquidity, expiry_day, volatility_event."""
        regime = {
            'low_liquidity': False,
            'expiry_day': False,
            'volatility_event': bool(self._tracker.get('volatility_event_flag', False)),
        }

        # Expiry day detection
        try:
            from django.utils import timezone
            today = timezone.localdate()
            # Thursday = weekday 3
            if today.weekday() == 3:
                regime['expiry_day'] = True
        except Exception:
            pass

        # Low liquidity day: today's volume < 25th percentile of 20-day avg
        try:
            from apps.brokers.models import HistoricalPrice
            from django.utils import timezone
            today = timezone.localdate()
            today_bars = HistoricalPrice.objects.filter(
                stock_code=_position_symbol(self._position),
                interval='1day',
            ).order_by('-datetime')[:21]
            bars = list(today_bars)
            if len(bars) >= 5:
                volumes = sorted([float(b.volume) for b in bars[1:21]])
                p25 = volumes[max(0, len(volumes) // 4)]
                today_vol = float(bars[0].volume) if bars else 0
                if today_vol > 0 and today_vol < p25:
                    regime['low_liquidity'] = True
        except Exception:
            pass

        return regime

    # ── source helpers ────────────────────────────────────────────────────────

    def _get_symbol(self) -> str:
        return _position_symbol(self._position)

    def _get_oi_symbol(self) -> str:
        """Return the OI/ContractData symbol (NSE code) for this position."""
        return _position_oi_symbol(self._position)

    def _get_current_price(self) -> float:
        """Return underlying spot price; fall back to futures CMP if spot unavailable."""
        futures_price = float(self._position.current_price or 0)
        return _fetch_spot_price(self._get_oi_symbol(), futures_price)

    def _get_pivot_sr(self):
        from apps.strategies.services.consolidated_sr_calculator import ConsolidatedSRCalculator
        result = ConsolidatedSRCalculator(
            self._get_symbol(),
            oi_symbol=self._get_oi_symbol(),
        ).get_conservative_sr(self._get_current_price())
        if not result:
            return [], []
        # Result shape: {'conservative_support': {'s1': v, 's2': v, 's3': v}, 'conservative_resistance': {...}}
        s_data = result.get('conservative_support', {})
        r_data = result.get('conservative_resistance', {})
        supports = [float(v) for k, v in s_data.items() if k in ('s1', 's2', 's3') and v]
        resistances = [float(v) for k, v in r_data.items() if k in ('r1', 'r2', 'r3') and v]
        return supports, resistances

    def _get_prev_day_hl(self):
        from apps.brokers.models import HistoricalPrice
        bars = list(
            HistoricalPrice.objects.filter(stock_code=self._get_symbol(), interval='1day')
            .order_by('-datetime')[:2]
        )
        if len(bars) < 2:
            return [], []
        prev = bars[1]
        return [float(prev.low)], [float(prev.high)]

    def _get_swing_hl(self):
        from apps.brokers.models import HistoricalPrice
        from apps.positions.services.sr_exit_engine_utils import calculate_swing_hl
        candles_qs = (
            HistoricalPrice.objects.filter(stock_code=self._get_symbol(), interval='5minute')
            .order_by('-datetime')[:20]
        )
        candles = [{'high': float(c.high), 'low': float(c.low)} for c in candles_qs]
        candles.reverse()
        swing_high, swing_low = calculate_swing_hl(candles, window=20)
        return ([swing_low] if swing_low else []), ([swing_high] if swing_high else [])

    def _get_vwap_bands(self):
        from apps.brokers.models import HistoricalPrice
        from apps.positions.services.sr_exit_engine_utils import calculate_vwap
        from django.utils import timezone
        today = timezone.now().date()
        candles_qs = HistoricalPrice.objects.filter(
            stock_code=self._get_symbol(), interval='5minute', datetime__date=today,
        ).order_by('datetime')
        candles = [
            {'high': float(c.high), 'low': float(c.low),
             'close': float(c.close), 'volume': float(c.volume)}
            for c in candles_qs
        ]
        vwap, ub1, lb1, ub2, lb2 = calculate_vwap(candles)
        supports = [s for s in (lb1, lb2) if s and s > 0]
        resistances = [r for r in (ub1, ub2) if r and r > 0]
        return vwap, supports, resistances

    def _get_moving_averages(self):
        from apps.strategies.services.support_resistance_calculator import SupportResistanceCalculator
        calc = SupportResistanceCalculator(self._get_symbol())
        calc.ensure_and_load_data()
        ma_data = calc.calculate_moving_averages()
        price = self._get_current_price()
        supports, resistances = [], []
        for key in ('ma20', 'ma50', 'ma100', 'ma200'):
            val = ma_data.get(key)
            if val:
                v = float(val)
                (supports if v < price else resistances).append(v)
        return supports, resistances

    def _get_hvn_levels(self):
        from apps.brokers.models import HistoricalPrice
        from apps.positions.services.sr_exit_engine_utils import detect_hvn_levels
        cutoff = datetime.now(tz=dt_timezone.utc) - timedelta(days=20)
        candles_qs = HistoricalPrice.objects.filter(
            stock_code=self._get_symbol(), interval='5minute', datetime__gte=cutoff,
        ).order_by('datetime')
        candles = [
            {'high': float(c.high), 'low': float(c.low),
             'close': float(c.close), 'volume': float(c.volume)}
            for c in candles_qs
        ]
        price = self._get_current_price()
        hvn = detect_hvn_levels(candles, n_levels=5)
        return (
            [h['price'] for h in hvn if h['price'] < price],
            [h['price'] for h in hvn if h['price'] >= price],
        )

    def _get_atr_zones(self):
        from apps.brokers.models import HistoricalPrice
        from apps.positions.services.sr_exit_engine_utils import calculate_atr
        bars_qs = (
            HistoricalPrice.objects.filter(stock_code=self._get_symbol(), interval='1day')
            .order_by('-datetime')[:20]
        )
        bars = [{'high': float(b.high), 'low': float(b.low), 'close': float(b.close)} for b in bars_qs]
        bars.reverse()
        atr = calculate_atr(bars, period=14)
        price = self._get_current_price()
        if atr == 0 or price == 0:
            return atr, [], []
        return atr, [price - atr, price - 2 * atr], [price + atr, price + 2 * atr]

    def _get_psychological_levels(self):
        from apps.strategies.services.psychological_levels import PsychologicalLevelAnalyzer
        price = self._get_current_price()
        levels = PsychologicalLevelAnalyzer(price)._find_psychological_levels(price)
        return (
            [float(l) for l in levels if float(l) < price],
            [float(l) for l in levels if float(l) >= price],
        )


# ─────────────────────────────────────────────────────────────────────────────
# GapDownFilter
# ─────────────────────────────────────────────────────────────────────────────

class GapDownFilter:
    """
    Detects gap opens and extends the opening noise window.

    Gap > GAP_THRESHOLD vs yesterday close → extend noise window
    to 09:45 IST (reduces false SL on gap-down opens).
    """

    def __init__(self, position, tracker: IntraDayTracker):
        self._position = position
        self._tracker = tracker

    def detect_gap(self) -> bool:
        """Cached: True if today's open gapped > 1% vs yesterday's close."""
        cached = self._tracker.get('gap_detected')
        if cached is not None:
            return bool(cached)

        try:
            from apps.brokers.models import HistoricalPrice
            symbol = getattr(self._position, 'symbol', None) or getattr(self._position, 'stock_code', 'NIFTY')
            bars = list(
                HistoricalPrice.objects.filter(stock_code=symbol, interval='1day')
                .order_by('-datetime')[:2]
            )
            if len(bars) < 2:
                self._tracker.set('gap_detected', False)
                return False
            today_open = float(bars[0].open)
            prev_close = float(bars[1].close)
            gap_pct = abs(today_open - prev_close) / prev_close if prev_close else 0
            is_gap = gap_pct > GAP_THRESHOLD
            self._tracker.set('gap_detected', is_gap)
            return is_gap
        except Exception as e:
            logger.debug(f"GapDownFilter error: {e}")
            return False

    def noise_window_end(self, ist_now: datetime) -> datetime:
        """Returns the datetime after which SL triggers are allowed."""
        extra = GAP_NOISE_EXTENSION_MINS if self.detect_gap() else 0
        return ist_now.replace(
            hour=NOISE_WINDOW_START_HOUR,
            minute=NOISE_WINDOW_START_MIN + extra,
            second=0,
            microsecond=0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# SLTriggerChecker
# ─────────────────────────────────────────────────────────────────────────────

class SLTriggerChecker:
    """
    Enforces the two-condition SL rule, direction-aware.

    LONG:    A: price ≤ support   × 0.995  B: session_low  ≤ support   × 0.990
    SHORT:   A: price ≥ resistance × 1.005  B: session_high ≥ resistance × 1.010
    NEUTRAL: checks both put side (S1) and call side (R1)

    All checks are bracketed by the opening noise window filter.
    """

    def __init__(self, position, sr_result: dict, tracker: IntraDayTracker,
                 ist_now: datetime, gap_filter: GapDownFilter):
        self._pos = position
        self._sr = sr_result
        self._tracker = tracker
        self._ist_now = ist_now
        self._gap_filter = gap_filter

    # ── Session tracking ──────────────────────────────────────────────────────

    def update_session_extremes(self, price: float):
        """Update sticky session low and high in tracker."""
        low = self._tracker.get('session_low')
        if low is None or price < low:
            self._tracker.set('session_low', price)
        high = self._tracker.get('session_high')
        if high is None or price > high:
            self._tracker.set('session_high', price)

    # ── Level selection ───────────────────────────────────────────────────────
    #
    # Two semantically distinct needs:
    #
    # 1. SL TRIGGER CHECK — "which support/resistance did price just break?"
    #    Use nearest_support_for_trigger() / nearest_resistance_for_trigger()
    #    Returns the level CLOSEST to current price (could be above or below).
    #    After a break, the broken support is slightly ABOVE current price.
    #    Condition A naturally ensures direction: price ≤ support×0.995 fires
    #    only when price is actually below the support.
    #
    # 2. ATR-BUFFERED SL PRICE — "where is the next support floor?"
    #    Use nearest_support_below() / nearest_resistance_above()
    #    These find the next structural level that price hasn't reached yet,
    #    used to set the stop-loss price (support − 0.5×ATR).

    def _spot_price(self) -> float:
        """
        Underlying spot price used for level selection.

        S/R levels are derived from equity spot data; selecting 'nearest support
        below' must compare against spot — not the futures CMP — to avoid basis
        mismatch that would select the wrong structural level.

        The trigger-detection conditions (_condition_a_long/short) intentionally
        use self._pos.current_price (futures CMP) because we are checking whether
        the actual traded price has breached the level.
        """
        futures_price = float(self._pos.current_price or 0)
        return _fetch_spot_price(_position_symbol(self._pos), futures_price)

    def nearest_support_below(self) -> float | None:
        """Nearest support floor below spot price (for ATR-buffered SL price)."""
        price = self._spot_price()
        below = [s['price'] for s in self._sr.get('supports', []) if s['price'] < price]
        return max(below) if below else None

    def nearest_resistance_above(self) -> float | None:
        """Nearest resistance ceiling above spot price (for ATR-buffered SL price)."""
        price = self._spot_price()
        above = [r['price'] for r in self._sr.get('resistances', []) if r['price'] > price]
        return min(above) if above else None

    def nearest_support_for_trigger(self) -> float | None:
        """
        Support closest to spot price — may be above or below.
        Used for the two-condition SL trigger check only.
        """
        price = self._spot_price()
        supports = [s['price'] for s in self._sr.get('supports', [])]
        return min(supports, key=lambda s: abs(s - price)) if supports else None

    def nearest_resistance_for_trigger(self) -> float | None:
        """
        Resistance closest to spot price — may be above or below.
        Used for the two-condition SL trigger check only.
        """
        price = self._spot_price()
        resistances = [r['price'] for r in self._sr.get('resistances', [])]
        return min(resistances, key=lambda r: abs(r - price)) if resistances else None

    # For TargetCalculator (target is set relative to the next floor/ceiling)
    def choose_support_level(self) -> float | None:
        if self._pos.direction == 'NEUTRAL':
            return self._get_oi_level('support')
        return self.nearest_support_below()

    def choose_resistance_level(self) -> float | None:
        if self._pos.direction == 'NEUTRAL':
            return self._get_oi_level('resistance')
        return self.nearest_resistance_above()

    def _get_oi_level(self, kind: str) -> float | None:
        """kind = 'support' | 'resistance'"""
        try:
            from apps.strategies.services.oi_support_resistance import OISupportResistanceCalculator
            symbol = _position_symbol(self._pos)
            price = self._spot_price()
            result = OISupportResistanceCalculator(symbol).get_conservative_sr(price)
            val = result.get(kind)
            return float(val) if val else None
        except Exception as e:
            logger.debug(f"OI {kind} error: {e}")
            return None

    # ── Noise window ──────────────────────────────────────────────────────────

    def is_open_noise_window(self) -> bool:
        return self._ist_now < self._gap_filter.noise_window_end(self._ist_now)

    # ── Condition checks (direction-specific) ─────────────────────────────────

    def _get_adaptive_thresholds(self) -> tuple:
        """
        Return ATR-adaptive Condition A/B thresholds.

        Uses scale_sl_conditions() from utils. Falls back to legacy constants
        if ATR is unavailable (backward compat).
        """
        try:
            from apps.positions.services.sr_exit_engine_utils import scale_sl_conditions
            atr = float(self._sr.get('atr', 0) or 0)
            price = float(self._pos.current_price or 1)
            atr_pct = atr / price if price > 0 else 0.0
            return scale_sl_conditions(atr_pct)
        except Exception:
            return (CONDITION_A_PCT, CONDITION_B_PCT)

    def _get_level_score(self, level_price: float, kind: str) -> int:
        """
        Return the strength_score for the given level (0–100).
        Falls back to 0 if levels are not annotated (base compute mode).
        """
        key = 'supports' if kind == 'support' else 'resistances'
        for lvl in self._sr.get(key, []):
            if abs(lvl['price'] - level_price) / level_price < 0.003:
                return int(lvl.get('strength_score', 0))
        return 0

    def _condition_a_long(self, support: float) -> bool:
        """Price ≥ cond_a_pct% below support (ATR-adaptive threshold)."""
        cond_a, _ = self._get_adaptive_thresholds()
        return float(self._pos.current_price or 0) <= support * (1 - cond_a)

    def _condition_b_long(self, support: float) -> bool:
        """Session low ≥ cond_b_pct% below support (ATR-adaptive threshold)."""
        _, cond_b = self._get_adaptive_thresholds()
        low = self._tracker.get('session_low')
        return low is not None and float(low) <= support * (1 - cond_b)

    def _condition_a_short(self, resistance: float) -> bool:
        """Price ≥ cond_a_pct% above resistance (ATR-adaptive threshold)."""
        cond_a, _ = self._get_adaptive_thresholds()
        return float(self._pos.current_price or 0) >= resistance * (1 + cond_a)

    def _condition_b_short(self, resistance: float) -> bool:
        """Session high ≥ cond_b_pct% above resistance (ATR-adaptive threshold)."""
        _, cond_b = self._get_adaptive_thresholds()
        high = self._tracker.get('session_high')
        return high is not None and float(high) >= resistance * (1 + cond_b)

    # ── Soft filters ──────────────────────────────────────────────────────────

    def _volume_confirmed(self) -> bool:
        """True if latest 5-min candle volume > 1.2× prior 19-bar avg."""
        try:
            from apps.brokers.models import HistoricalPrice
            from django.utils import timezone
            symbol = getattr(self._pos, 'symbol', None) or getattr(self._pos, 'stock_code', 'NIFTY')
            candles = list(
                HistoricalPrice.objects.filter(
                    stock_code=symbol, interval='5minute', datetime__date=timezone.now().date(),
                ).order_by('-datetime')[:20]
            )
            if len(candles) < 2:
                return True
            prior_avg = sum(float(c.volume) for c in candles[1:]) / (len(candles) - 1)
            return prior_avg == 0 or float(candles[0].volume) >= prior_avg * VOLUME_MULTIPLIER
        except Exception:
            return True  # default: pass

    def _not_recovering_15min(self, reference: float, direction: str) -> bool:
        """
        True if the 15-min candle confirms the breakout (price still past reference).
        False (→ skip SL) if price has recovered back through the reference level.
        """
        try:
            from apps.brokers.models import HistoricalPrice
            from django.utils import timezone
            symbol = getattr(self._pos, 'symbol', None) or getattr(self._pos, 'stock_code', 'NIFTY')
            candle = HistoricalPrice.objects.filter(
                stock_code=symbol, interval='15minute', datetime__date=timezone.now().date(),
            ).order_by('-datetime').first()
            if not candle:
                return True
            close = float(candle.close)
            if direction == 'LONG':
                return close < reference  # still below support = not recovered
            else:  # SHORT
                return close > reference  # still above resistance = not recovered
        except Exception:
            return True

    # ── Direction-specific SL trigger checks ─────────────────────────────────

    def _in_liquidity_vacuum(self, price: float) -> float:
        """Return vacuum_score if price is inside a liquidity vacuum, else 0.0."""
        vacuums = self._sr.get('vacuums', [])
        for vac in vacuums:
            if vac.get('low', 0) <= price <= vac.get('high', 0):
                return float(vac.get('vacuum_score', 0))
        return 0.0

    def _is_expiry_day_gamma_mode(self) -> bool:
        """True on expiry day before EXPIRY_GAMMA_MODE_HOUR (widen thresholds)."""
        regime = self._sr.get('market_regime', {})
        if not regime.get('expiry_day'):
            return False
        return self._ist_now.hour < EXPIRY_GAMMA_MODE_HOUR

    def _is_low_liquidity_day(self) -> bool:
        return bool(self._sr.get('market_regime', {}).get('low_liquidity'))

    def _check_long_sl(self) -> tuple:
        # Use nearest_support_for_trigger: after a break, the broken support
        # is typically just above current price. Condition A ensures it only
        # fires when price is actually below the support (price ≤ support×cond_a).
        level = self.nearest_support_for_trigger()
        if not level:
            return False, 'NO_SUPPORT_FOUND'

        cond_a = self._condition_a_long(level)
        cond_b = self._condition_b_long(level)

        # ── Structural pressure: Cond A met, Cond B not yet ───────────────────
        if cond_a and not cond_b:
            self._emit_structural_pressure(level, 'support', 'LONG')

        if not cond_a:
            return False, 'CONDITION_A_NOT_MET'

        # ── Confidence-gated trigger rules ────────────────────────────────────
        level_score = self._get_level_score(level, 'support')

        # Expiry day and low-liquidity: require stricter confirmation (both conditions)
        strict_mode = self._is_expiry_day_gamma_mode() or self._is_low_liquidity_day()

        if level_score >= SCORE_INSTITUTIONAL and not strict_mode:
            # Institutional level: Condition A alone triggers
            triggered = True
        elif level_score >= SCORE_STRONG and not strict_mode:
            # Strong level: either A or B + 15-min confirmation
            triggered = cond_b or self._not_recovering_15min(level, 'LONG')
        else:
            # Weak/moderate (or strict mode): both A+B + 15-min required
            if not cond_b:
                return False, 'CONDITION_B_NOT_MET'
            if not self._not_recovering_15min(level, 'LONG'):
                return False, 'PRICE_RECOVERING_15MIN'
            triggered = True

        if not triggered:
            return False, 'CONDITIONS_NOT_MET'

        if not self._volume_confirmed():
            logger.info(f"SR SL: volume unconfirmed for pos #{self._pos.id} — proceeding")

        # Vacuum acceleration suffix
        price = float(self._pos.current_price or 0)
        vac_score = self._in_liquidity_vacuum(price)
        suffix = f' [VACUUM_ACCELERATION score={vac_score:.1f}]' if vac_score > 0 else ''
        score_note = f', score={level_score}' if level_score > 0 else ''
        return True, f'SR_SUPPORT_BREAK (support={level:.2f}{score_note}){suffix}'

    def _check_short_sl(self) -> tuple:
        # After a resistance break, the broken resistance is typically just
        # below current price. Condition A ensures it fires only when price
        # is actually above the resistance (price ≥ resistance×(1+cond_a)).
        level = self.nearest_resistance_for_trigger()
        if not level:
            return False, 'NO_RESISTANCE_FOUND'

        cond_a = self._condition_a_short(level)
        cond_b = self._condition_b_short(level)

        # ── Structural pressure: Cond A met, Cond B not yet ───────────────────
        if cond_a and not cond_b:
            self._emit_structural_pressure(level, 'resistance', 'SHORT')

        if not cond_a:
            return False, 'CONDITION_A_NOT_MET'

        # ── Confidence-gated trigger rules ────────────────────────────────────
        level_score = self._get_level_score(level, 'resistance')
        strict_mode = self._is_expiry_day_gamma_mode() or self._is_low_liquidity_day()

        if level_score >= SCORE_INSTITUTIONAL and not strict_mode:
            triggered = True
        elif level_score >= SCORE_STRONG and not strict_mode:
            triggered = cond_b or self._not_recovering_15min(level, 'SHORT')
        else:
            if not cond_b:
                return False, 'CONDITION_B_NOT_MET'
            if not self._not_recovering_15min(level, 'SHORT'):
                return False, 'PRICE_RECOVERING_15MIN'
            triggered = True

        if not triggered:
            return False, 'CONDITIONS_NOT_MET'

        if not self._volume_confirmed():
            logger.info(f"SR SL: volume unconfirmed for pos #{self._pos.id} — proceeding")

        price = float(self._pos.current_price or 0)
        vac_score = self._in_liquidity_vacuum(price)
        suffix = f' [VACUUM_ACCELERATION score={vac_score:.1f}]' if vac_score > 0 else ''
        score_note = f', score={level_score}' if level_score > 0 else ''
        return True, f'SR_RESISTANCE_BREAK (resistance={level:.2f}{score_note}){suffix}'

    def _emit_structural_pressure(self, level: float, kind: str, direction: str):
        """
        Stage 2 warning: store structural pressure signal in tracker so tasks.py
        can send a Telegram notification on next cycle with cooldown.
        Does NOT send anything directly — tasks.py reads 'structural_pressure' key.
        """
        try:
            from apps.positions.services.sr_risk_interface import StructuralPressureMonitor
            level_score = self._get_level_score(level, kind)
            signal = StructuralPressureMonitor.check(
                position=self._pos,
                cond_a_met=True,
                cond_b_met=False,
                level=level,
                level_score=level_score,
                tracker=self._tracker,
            )
            # Store for tasks.py to read and act on
            if signal.get('should_warn'):
                self._tracker.set('structural_pressure_signal', signal)
        except Exception as e:
            logger.debug(f"_emit_structural_pressure error: {e}")

    def _check_neutral_sl(self) -> tuple:
        """
        Check both put side (S1) and call side (R1).
        Triggers if spot breaks either direction with both conditions met.
        """
        # Put side (S1) — spot falling through support hurts short puts
        s1 = self._get_oi_level('support')
        if s1 and self._condition_a_long(s1) and self._condition_b_long(s1):
            if self._not_recovering_15min(s1, 'LONG'):
                return True, f'SR_SPOT_BELOW_S1 (S1={s1:.2f})'

        # Call side (R1) — spot rising through resistance hurts short calls
        r1 = self._get_oi_level('resistance')
        if r1 and self._condition_a_short(r1) and self._condition_b_short(r1):
            if self._not_recovering_15min(r1, 'SHORT'):
                return True, f'SR_SPOT_ABOVE_R1 (R1={r1:.2f})'

        return False, 'NEUTRAL_CONDITIONS_NOT_MET'

    def should_trigger_sl(self) -> tuple:
        """
        Main entry point. Returns (triggered: bool, reason: str).
        Dispatches to direction-specific check.
        """
        if self.is_open_noise_window():
            return False, 'OPEN_NOISE_WINDOW'

        direction = self._pos.direction
        if direction == 'LONG':
            return self._check_long_sl()
        elif direction == 'SHORT':
            return self._check_short_sl()
        else:  # NEUTRAL
            return self._check_neutral_sl()


# ─────────────────────────────────────────────────────────────────────────────
# TargetCalculator
# ─────────────────────────────────────────────────────────────────────────────

class TargetCalculator:
    """
    Computes ATR-buffered profit target, direction-aware.

    LONG:    target = nearest_resistance × (1 − ATR-offset)   [below resistance]
    SHORT:   target = nearest_support    × (1 + ATR-offset)   [above support]
    NEUTRAL: None — premium-decay target is set by strategy at entry
    """

    def __init__(self, position, sr_result: dict, sl_checker: SLTriggerChecker):
        self._pos = position
        self._sr = sr_result
        self._sl_checker = sl_checker

    def _atr_offset(self) -> float:
        from apps.positions.services.sr_exit_engine_utils import interpolate_target_offset
        atr = float(self._sr.get('atr', 0) or 0)
        price = float(self._pos.current_price or 1)
        return interpolate_target_offset(atr / price if price else 0)

    def calculate(self) -> float | None:
        direction = self._pos.direction
        price = float(self._pos.current_price or 0)
        offset = self._atr_offset()

        if direction == 'LONG':
            resistance = self._sl_checker.nearest_resistance_above()
            if not resistance:
                return None
            target = resistance * (1 - offset)
            return target if target > price else None

        elif direction == 'SHORT':
            support = self._sl_checker.nearest_support_below()
            if not support:
                return None
            target = support * (1 + offset)
            return target if target < price else None

        else:  # NEUTRAL — premium decay; target set at entry
            return None


# ─────────────────────────────────────────────────────────────────────────────
# SRExitEngine — orchestrator (internal)
# ─────────────────────────────────────────────────────────────────────────────

class SRExitEngine:
    """
    Internal orchestrator. Do not call directly from outside this module.
    Use apply_sl_and_target() instead.

    evaluate() returns:
        sl_triggered:    bool
        sl_reason:       str
        new_sl:          float | None   (ATR-buffered structural SL price)
        new_target:      float | None   (ATR-buffered resistance/support target)
    """

    def __init__(self, position, tracker: IntraDayTracker, now: datetime | None = None):
        self._pos = position
        self._tracker = tracker
        self._now = now or _ist_now()

    def evaluate(self) -> dict:
        result = {
            'sl_triggered': False,
            'sl_reason': '',
            'new_sl': None,
            'new_target': None,
            'structural_pressure': None,   # Stage 2 warning signal (for tasks.py)
        }

        # ── Volatility event flag: bypass structural SL if intraday shock ────────
        # If price moved > 2×ATR in a single 5-min candle, flag the event.
        # The flag is auto-cleared after 3 normalisation candles.
        self._update_volatility_event_flag()

        # ── VIX spike: immediate exit for NEUTRAL (IV expansion hits short options) ──
        if self._pos.direction == 'NEUTRAL':
            try:
                from apps.strategies.shared.market_data import get_vix
                vix_now = float(get_vix())
                prev_vix = self._get_prev_vix()
                if prev_vix and prev_vix > 0:
                    adaptive_threshold = _adaptive_vix_spike_threshold(prev_vix)
                    if (vix_now - prev_vix) / prev_vix > adaptive_threshold:
                        result['sl_triggered'] = True
                        result['sl_reason'] = (
                            f'VOLATILITY_SPIKE (VIX {prev_vix:.1f}→{vix_now:.1f}, '
                            f'threshold={adaptive_threshold*100:.0f}%)'
                        )
                        self._tracker.save()
                        return result
            except Exception as e:
                logger.debug(f"VIX spike check error: {e}")

        # ── 1. Refresh S/R cache (15-min TTL) ────────────────────────────────
        sr_result = self._get_or_refresh_sr_cache()
        atr = float(sr_result.get('atr', 0) or 0)
        price = float(self._pos.current_price or 0)

        # ── 2. Update session extremes (both low and high) ────────────────────
        gap_filter = GapDownFilter(self._pos, self._tracker)
        sl_checker = SLTriggerChecker(self._pos, sr_result, self._tracker, self._now, gap_filter)
        sl_checker.update_session_extremes(price)

        # ── 3. Compute ATR-buffered SL price (direction-aware, confidence-adjusted) ──
        direction = self._pos.direction
        vacuums = sr_result.get('vacuums', [])

        if direction == 'LONG':
            support = sl_checker.nearest_support_below()
            if support and support > 0:
                level_score = sl_checker._get_level_score(support, 'support')
                try:
                    from apps.positions.services.sr_risk_interface import AdaptiveSLPlacer
                    new_sl = AdaptiveSLPlacer.compute_sl(
                        direction='LONG',
                        level=support,
                        atr=atr,
                        level_score=level_score,
                        vacuums=vacuums,
                        price=price,
                    )
                except Exception:
                    new_sl = support - 0.5 * atr if atr > 0 else None
                if new_sl and new_sl > 0:
                    result['new_sl'] = new_sl

        elif direction == 'SHORT':
            resistance = sl_checker.nearest_resistance_above()
            if resistance and resistance > 0:
                level_score = sl_checker._get_level_score(resistance, 'resistance')
                try:
                    from apps.positions.services.sr_risk_interface import AdaptiveSLPlacer
                    new_sl = AdaptiveSLPlacer.compute_sl(
                        direction='SHORT',
                        level=resistance,
                        atr=atr,
                        level_score=level_score,
                        vacuums=vacuums,
                        price=price,
                    )
                except Exception:
                    new_sl = resistance + 0.5 * atr if atr > 0 else None
                if new_sl:
                    result['new_sl'] = new_sl

        # NEUTRAL: SL is managed per-leg by strategy; structural SL not computed

        # ── 4. Compute profit target (direction-aware) ────────────────────────
        result['new_target'] = TargetCalculator(self._pos, sr_result, sl_checker).calculate()

        # ── 5. Two-condition SL trigger ───────────────────────────────────────
        result['sl_triggered'], result['sl_reason'] = sl_checker.should_trigger_sl()

        # ── 6. Carry structural pressure signal (Stage 2 warning) ────────────
        # SLTriggerChecker stores the signal in the tracker during _check_*_sl().
        # We surface it here so apply_sl_and_target() can pass it back to tasks.py.
        stage2 = self._tracker.get('structural_pressure_signal')
        if stage2:
            result['structural_pressure'] = stage2
            # Clear from tracker — consumed once per cycle
            self._tracker.set('structural_pressure_signal', None)

        # ── Persist tracker state ─────────────────────────────────────────────
        try:
            self._tracker.save()
        except Exception as e:
            logger.warning(f"Tracker save failed for pos #{self._pos.id}: {e}")

        return result

    def _get_or_refresh_sr_cache(self) -> dict:
        cache = self._tracker.get('sr_cache')
        last_at = self._tracker.get('last_sr_computed_at')
        if cache and last_at:
            try:
                age_min = (self._now - datetime.fromisoformat(last_at)).total_seconds() / 60
                if age_min < SR_CACHE_TTL_MINUTES:
                    return cache
            except Exception:
                pass
        # Use compute_enhanced() — runs base 8-source + MTF + order blocks + OI walls
        # + level strength annotation + liquidity vacuums + market regime flags.
        # Falls back gracefully on any individual enrichment failure.
        try:
            fresh = MultiFactorSRCalculator(self._pos, self._tracker).compute_enhanced()
        except Exception as e:
            logger.warning(f"SR enhanced compute failed, falling back to base: {e}")
            fresh = MultiFactorSRCalculator(self._pos, self._tracker).compute()
        self._tracker.set('sr_cache', fresh)
        self._tracker.set('last_sr_computed_at', self._now.isoformat())
        return fresh

    def _get_prev_vix(self) -> float | None:
        try:
            from apps.brokers.models import HistoricalPrice
            bar = HistoricalPrice.objects.filter(
                symbol='INDIA VIX', interval='1day',
            ).order_by('-datetime').first()
            return float(bar.close) if bar else None
        except Exception:
            return None

    def _update_volatility_event_flag(self):
        """
        Detect and manage the volatility_event_flag.

        Set flag if latest 5-min candle body > 2 × ATR (intraday shock).
        Clear flag after 3 consecutive normalisation candles (body ≤ 1.5 × ATR).
        The flag is read by market_regime detection to bypass structural SL.
        """
        try:
            from apps.brokers.models import HistoricalPrice
            from django.utils import timezone
            today = timezone.now().date()
            candles_qs = list(
                HistoricalPrice.objects.filter(
                    stock_code=_position_symbol(self._pos),
                    interval='5minute',
                    datetime__date=today,
                ).order_by('-datetime')[:15]
            )
            if len(candles_qs) < 3:
                return

            from apps.positions.services.sr_exit_engine_utils import calculate_atr
            bars = [{'high': float(c.high), 'low': float(c.low), 'close': float(c.close)}
                    for c in candles_qs]
            bars.reverse()
            atr = calculate_atr(bars, period=14)
            if atr <= 0:
                return

            latest = candles_qs[0]
            latest_body = abs(float(latest.close) - float(latest.open))
            current_flag = bool(self._tracker.get('volatility_event_flag'))

            if not current_flag and latest_body > 2.0 * atr:
                # New volatility event detected
                self._tracker.set('volatility_event_flag', True)
                self._tracker.set('volatility_normalisation_count', 0)
                logger.info(
                    f"SR engine: volatility event detected for pos #{self._pos.id} "
                    f"(body={latest_body:.2f} > 2×ATR={2*atr:.2f})"
                )
            elif current_flag:
                # Check for normalisation
                if latest_body <= 1.5 * atr:
                    count = int(self._tracker.get('volatility_normalisation_count') or 0) + 1
                    self._tracker.set('volatility_normalisation_count', count)
                    if count >= 3:
                        self._tracker.set('volatility_event_flag', False)
                        self._tracker.set('volatility_normalisation_count', 0)
                        logger.info(
                            f"SR engine: volatility event cleared for pos #{self._pos.id}"
                        )
                else:
                    # Still elevated — reset normalisation counter
                    self._tracker.set('volatility_normalisation_count', 0)
        except Exception as e:
            logger.debug(f"_update_volatility_event_flag error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Public API — the ONLY function called from outside this module
# ─────────────────────────────────────────────────────────────────────────────

def apply_sl_and_target(position, dashboard, now=None) -> dict:
    """
    Single entry point for SR-based SL/target management.

    Called once per position per monitor cycle from positions/tasks.py.
    Also handles new / broker-synced positions that arrive without SL or target.

    Actions performed:
    1. Refreshes S/R cache if stale (15-min TTL).
    2. Persists session extremes (low/high) in tracker.
    3. Tightens position.stop_loss only (never loosens).
       LONG:  new_sl > old_sl  (higher = tighter)
       SHORT: new_sl < old_sl  (lower  = tighter)
    4. Sets position.target if not yet set.
    5. Checks two-condition structural SL trigger.

    Args:
        position:  Open Position instance (current_price must be fresh).
        dashboard: PositionMonitorDashboard for today (already fetched by caller).
        now:       Current datetime (timezone-aware). Defaults to current IST time.

    Returns:
        {'sl_triggered': bool, 'sl_reason': str}

    Never raises — all errors are caught and logged; returns safe defaults.
    """
    try:
        from django.utils import timezone as tz
        tracker = IntraDayTracker(dashboard)
        engine_result = SRExitEngine(position, tracker, now=now or tz.now()).evaluate()

        # Tighten SL only — never loosen
        if engine_result['new_sl'] and is_tighter_sl(position, engine_result['new_sl']):
            new_sl_dec = Decimal(str(round(engine_result['new_sl'], 2)))
            position.stop_loss = new_sl_dec
            position.save(update_fields=['stop_loss'])
            logger.info(
                f"SR engine: SL tightened for pos #{position.id} "
                f"({position.direction}) → {position.stop_loss}"
            )
            # Propagate tighter SL to sibling positions of the same instrument
            _propagate_sl_to_siblings(position, new_sl_dec)

        # Set target only if not yet set (don't override manual targets)
        if engine_result['new_target'] and not position.target:
            new_tgt_dec = Decimal(str(round(engine_result['new_target'], 2)))
            position.target = new_tgt_dec
            position.save(update_fields=['target'])
            logger.info(
                f"SR engine: target set for pos #{position.id} "
                f"({position.direction}) → {position.target}"
            )
            # Set target on siblings that don't have one yet
            _propagate_target_to_siblings(position, new_tgt_dec)

        return {
            'sl_triggered': engine_result['sl_triggered'],
            'sl_reason': engine_result['sl_reason'],
            'structural_pressure': engine_result.get('structural_pressure'),
        }

    except Exception as e:
        logger.warning(f"SR engine error for pos #{position.id}: {e}", exc_info=False)
        return {'sl_triggered': False, 'sl_reason': '', 'structural_pressure': None}


# ─────────────────────────────────────────────────────────────────────────────
# Pre-position public API — compute structural SL/target before entry
# ─────────────────────────────────────────────────────────────────────────────

class _LightweightPos:
    """Duck-typed Position for SR computation (no DB)."""
    def __init__(self, symbol: str, price: float, direction: str):
        self.symbol = symbol
        self.stock_code = symbol
        self.current_price = price
        self.direction = direction
        self.id = 0


class _EphemeralTracker:
    """In-memory tracker — no dashboard, no DB persistence."""
    def __init__(self):
        self._data = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def save(self):
        pass  # no-op


class _DummyGapFilter(GapDownFilter):
    """Noise window never active (not relevant for pre-position calls)."""
    def __init__(self):
        pass  # skip parent __init__

    def detect_gap(self) -> bool:
        return False

    def noise_window_end(self, ist_now: datetime) -> datetime:
        return ist_now  # never blocks


def compute_initial_sl_target(symbol: str, price: float, direction: str) -> dict:
    """
    Compute structural stop-loss and profit target before a position exists.

    Uses the same 8-source weighted S/R engine as apply_sl_and_target() but
    works without a dashboard or database Position.  Intended for trade
    verification and suggestion flows where only a symbol/price/direction is
    known.

    Args:
        symbol:    Underlying symbol (e.g. 'NIFTY', 'HDFCBANK').  Must be the
                   spot/equity symbol — not a broker-specific futures code.
        price:     Futures CMP as float (used only as fallback if spot is absent).
        direction: 'LONG', 'SHORT', or 'NEUTRAL'.

    Returns:
        {'stop_loss': float | None, 'target': float | None}

    Never raises — all errors return {None, None}; callers must apply
    percentage fallbacks.
    """
    try:
        from apps.positions.services.sr_exit_engine_utils import interpolate_target_offset

        # Always resolve spot price — S/R levels are equity-spot based.
        # Entry price (buying price) is irrelevant; only CMP/spot matters.
        spot_price = _fetch_spot_price(symbol, float(price))

        mock_pos = _LightweightPos(symbol, spot_price, direction)
        tracker = _EphemeralTracker()
        gap_filter = _DummyGapFilter()

        sr_result = MultiFactorSRCalculator(mock_pos, tracker).compute()
        atr = float(sr_result.get('atr', 0) or 0)

        # Use a dummy datetime so SLTriggerChecker can be constructed
        dummy_now = _ist_now()
        sl_checker = SLTriggerChecker(mock_pos, sr_result, tracker, dummy_now, gap_filter)

        stop_loss = None
        target = None

        if direction == 'LONG':
            support = sl_checker.nearest_support_below()
            if support and support > 0:
                if atr > 0:
                    stop_loss = support - 0.5 * atr
                else:
                    stop_loss = support * 0.995
            resistance = sl_checker.nearest_resistance_above()
            if resistance and resistance > 0:
                offset = interpolate_target_offset(atr / spot_price if spot_price else 0)
                t = resistance * (1 - offset)
                target = t if t > spot_price else None

        elif direction == 'SHORT':
            resistance = sl_checker.nearest_resistance_above()
            if resistance and resistance > 0:
                if atr > 0:
                    stop_loss = resistance + 0.5 * atr
                else:
                    stop_loss = resistance * 1.005
            support = sl_checker.nearest_support_below()
            if support and support > 0:
                offset = interpolate_target_offset(atr / spot_price if spot_price else 0)
                t = support * (1 + offset)
                target = t if t < spot_price else None

        # NEUTRAL: directional SL/target not applicable
        return {'stop_loss': stop_loss, 'target': target}

    except Exception as e:
        logger.warning(f"compute_initial_sl_target({symbol}, {price}, {direction}): {e}")
        return {'stop_loss': None, 'target': None}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def is_tighter_sl(position, new_sl: float) -> bool:
    """
    Returns True only when new_sl is strictly tighter than the current SL.

    LONG:    higher SL = tighter (limits downside loss)
    SHORT:   lower  SL = tighter (limits upside loss)
    NEUTRAL: SR engine never manages SL for NEUTRAL; always False.
    """
    direction = position.direction
    if direction == 'NEUTRAL':
        return False  # direction check first — None guard must not override this
    old_sl = position.stop_loss
    if old_sl is None:
        return True  # any SL is better than none for LONG/SHORT
    old_sl_f = float(old_sl)
    if direction == 'LONG':
        return new_sl > old_sl_f
    if direction == 'SHORT':
        return new_sl < old_sl_f
    return False


def _underlying_prefix(position) -> str:
    """
    Return the underlying symbol prefix for cross-broker sibling lookup.
    Uses display_name (e.g. HDFCBANK26MARFUT → HDFCBANK) so that positions
    across different brokers (HDFBAN vs HDFCBANK) are correctly grouped.
    """
    return _position_symbol(position)


def _propagate_sl_to_siblings(position, new_sl: Decimal):
    """
    Propagate a tightened SL to all other open positions of the same
    underlying+direction, across all brokers.

    Applies `is_tighter_sl` check to each sibling — never loosens their SL.
    Skips the position that was already saved by the caller.
    """
    try:
        from apps.core.constants import POSITION_STATUS_OPEN
        from apps.positions.models import Position as _Position
        underlying = _underlying_prefix(position)
        siblings = _Position.objects.filter(
            display_name__startswith=underlying,
            direction=position.direction,
            status=POSITION_STATUS_OPEN,
        ).exclude(id=position.id)
        for sib in siblings:
            if is_tighter_sl(sib, float(new_sl)):
                sib.stop_loss = new_sl
                sib.save(update_fields=['stop_loss'])
                logger.info(
                    f"SR propagate: SL tightened for sibling pos #{sib.id} "
                    f"({sib.direction}) → {new_sl}"
                )
    except Exception as e:
        logger.debug(f"SL propagation error for pos #{position.id}: {e}")


def _propagate_target_to_siblings(position, new_target: Decimal):
    """
    Set the same target on sibling positions that don't have a target yet.
    Never overwrites an already-set target.
    Propagates across all brokers using display_name prefix (underlying).
    """
    try:
        from apps.core.constants import POSITION_STATUS_OPEN
        from apps.positions.models import Position as _Position
        underlying = _underlying_prefix(position)
        siblings = _Position.objects.filter(
            display_name__startswith=underlying,
            direction=position.direction,
            status=POSITION_STATUS_OPEN,
        ).exclude(id=position.id).filter(target__isnull=True)
        for sib in siblings:
            sib.target = new_target
            sib.save(update_fields=['target'])
            logger.info(
                f"SR propagate: target set for sibling pos #{sib.id} → {new_target}"
            )
    except Exception as e:
        logger.debug(f"Target propagation error for pos #{position.id}: {e}")


def _ist_now() -> datetime:
    """Current datetime in IST."""
    import zoneinfo
    return datetime.now(tz=zoneinfo.ZoneInfo('Asia/Kolkata'))


def _adaptive_vix_spike_threshold(baseline_vix: float) -> float:
    """
    Compute adaptive VIX spike threshold normalised to baseline VIX level.

    A 20% jump from VIX=10 (to 12) is very different from 20% from VIX=30 (to 36).
    This function scales the threshold so higher-VIX regimes tolerate larger
    absolute swings without triggering.

    Formula: threshold = 0.20 × (15.0 / baseline_vix)
    Clamped to [0.10, 0.35]

    Args:
        baseline_vix: Previous VIX close (float > 0)

    Returns:
        Threshold as fraction (e.g. 0.25 = 25%)
    """
    if not baseline_vix or baseline_vix <= 0:
        return VIX_SPIKE_THRESHOLD  # legacy default

    threshold = 0.20 * (15.0 / baseline_vix)
    return max(0.10, min(0.35, threshold))


def _tag(prices: list, source: str, weight: float) -> list:
    """Convert a list of price floats to tagged level dicts."""
    return [
        {'price': float(p), 'score': weight, 'source': source}
        for p in prices if p and float(p) > 0
    ]


def _prices_from_sr(sr_result: dict, key: str) -> list:
    """
    Extract a list of price floats from an S/R result dict.
    Handles both {'support': value} and {'supports': [value, ...]} shapes.
    """
    if not sr_result:
        return []
    for k in (key + 's', key):
        val = sr_result.get(k)
        if val is None:
            continue
        if isinstance(val, (list, tuple)):
            return [float(v) for v in val if v]
        return [float(val)]
    return []
