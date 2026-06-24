from __future__ import annotations
"""
OI Wall Enricher — Gamma Wall + OI Delta Tracking

Extends the existing OI-based S1/R1 from OISupportResistanceCalculator with:
    - Gamma wall: strike where OI × open-interest-change is maximum
    - OI delta: change in OI since last cycle (from sr_tracking snapshot)
    - Strike pinning signal: spot within 0.5% of max-OI strike for 3+ cycles
    - Max-pain strike: weighted average of ITM option pain (for expiry day)

Public API:
    OIWallEnricher(position).compute_walls(tracker) -> dict

Output shape:
    {
        'gamma_wall_ce':    float | None,   # highest CE OI strike
        'gamma_wall_pe':    float | None,   # highest PE OI strike
        'near_expiry_wall': float | None,   # nearest expiry dominant wall
        'far_expiry_wall':  float | None,   # next expiry wall
        'oi_delta_ce':      float,          # CE OI change vs last snapshot (%)
        'oi_delta_pe':      float,          # PE OI change vs last snapshot (%)
        'pinning_alert':    bool,           # spot pinned near max-OI strike
        'pinning_strike':   float | None,   # strike being pinned to
        'max_pain':         float | None,   # max-pain strike (expiry day only)
        'supports':         [...],          # tagged level dicts for cluster_levels()
        'resistances':      [...],          # tagged level dicts for cluster_levels()
    }

Never raises — returns safe defaults on any error.
Cache TTL: 5 minutes (OI shifts faster near expiry than price levels).
"""

import logging
from datetime import datetime, timezone as dt_timezone

logger = logging.getLogger(__name__)

OI_WALL_WEIGHT = 0.10        # weight when added to cluster_levels()
OI_CACHE_TTL_MINUTES = 5
PINNING_TOLERANCE_PCT = 0.005  # spot within 0.5% of strike = pinning candidate
PINNING_CYCLE_COUNT = 3        # cycles of pinning before alert


class OIWallEnricher:
    """
    Computes gamma walls and OI delta from options chain data.
    """

    def __init__(self, position):
        self._position = position

    def compute_walls(self, tracker) -> dict:
        """
        Args:
            tracker: IntraDayTracker instance (for OI snapshot persistence)

        Returns:
            OI wall dict. Never raises.
        """
        try:
            return self._compute(tracker)
        except Exception as e:
            logger.debug(
                f"OIWallEnricher error for pos #{getattr(self._position, 'id', '?')}: {e}"
            )
            return _empty_result()

    def _compute(self, tracker) -> dict:
        # Check cache (5-min TTL)
        cached = tracker.get('oi_wall_cache')
        last_at = tracker.get('oi_wall_computed_at')
        now = datetime.now(tz=dt_timezone.utc)

        if cached and last_at:
            try:
                age_min = (now - datetime.fromisoformat(last_at)).total_seconds() / 60
                if age_min < OI_CACHE_TTL_MINUTES:
                    # Even from cache: update pinning counter (needs current spot)
                    updated = self._update_pinning_from_cache(cached, tracker)
                    return updated
            except Exception:
                pass

        symbol = self._get_symbol()
        spot = self._get_spot(symbol)
        if spot <= 0:
            return _empty_result()

        # Fetch option chain
        chain = self._get_option_chain(symbol, spot)
        if not chain:
            return _empty_result()

        result = self._analyse_chain(chain, spot, tracker, symbol)

        # Persist cache
        tracker.set('oi_wall_cache', result)
        tracker.set('oi_wall_computed_at', now.isoformat())

        return result

    def _analyse_chain(self, chain: list, spot: float, tracker, symbol: str) -> dict:
        """
        chain: list of {strike, ce_oi, pe_oi, ce_oi_change, pe_oi_change}
        """
        # ── Find max OI strikes ───────────────────────────────────────────────
        max_ce_oi = 0.0
        max_pe_oi = 0.0
        gamma_wall_ce = None
        gamma_wall_pe = None
        max_pain_strike = None

        max_pain_pain = float('inf')

        for row in chain:
            strike = float(row.get('strike', 0) or 0)
            ce_oi = float(row.get('ce_oi', 0) or 0)
            pe_oi = float(row.get('pe_oi', 0) or 0)

            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                gamma_wall_ce = strike

            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                gamma_wall_pe = strike

        # ── OI delta (change from last snapshot) ─────────────────────────────
        prev_snap = tracker.get('oi_snapshot') or {}
        oi_delta_ce = 0.0
        oi_delta_pe = 0.0

        if prev_snap:
            prev_ce = float(prev_snap.get('max_ce_oi', 0) or 0)
            prev_pe = float(prev_snap.get('max_pe_oi', 0) or 0)
            if prev_ce > 0:
                oi_delta_ce = (max_ce_oi - prev_ce) / prev_ce
            if prev_pe > 0:
                oi_delta_pe = (max_pe_oi - prev_pe) / prev_pe

        # Save new snapshot
        tracker.set('oi_snapshot', {
            'max_ce_oi': max_ce_oi,
            'max_pe_oi': max_pe_oi,
            'gamma_wall_ce': gamma_wall_ce,
            'gamma_wall_pe': gamma_wall_pe,
        })

        # ── Max pain (sum of ITM pain per strike) ─────────────────────────────
        try:
            max_pain_strike = self._calc_max_pain(chain)
        except Exception:
            max_pain_strike = None

        # ── Pinning detection ─────────────────────────────────────────────────
        dominant_wall = gamma_wall_ce if max_ce_oi >= max_pe_oi else gamma_wall_pe
        pinning_alert, pinning_strike = self._check_pinning(spot, dominant_wall, tracker)

        # ── Build level lists for cluster_levels() ────────────────────────────
        supports = []
        resistances = []

        # PE wall = support (puts protect this floor)
        if gamma_wall_pe and gamma_wall_pe > 0:
            supports.append({
                'price': gamma_wall_pe,
                'score': OI_WALL_WEIGHT,
                'source': 'oi_wall',
            })

        # CE wall = resistance (calls cap upside)
        if gamma_wall_ce and gamma_wall_ce > 0:
            resistances.append({
                'price': gamma_wall_ce,
                'score': OI_WALL_WEIGHT,
                'source': 'oi_wall',
            })

        return {
            'gamma_wall_ce':    gamma_wall_ce,
            'gamma_wall_pe':    gamma_wall_pe,
            'near_expiry_wall': dominant_wall,
            'far_expiry_wall':  None,  # populated if multi-expiry data available
            'oi_delta_ce':      round(oi_delta_ce, 4),
            'oi_delta_pe':      round(oi_delta_pe, 4),
            'pinning_alert':    pinning_alert,
            'pinning_strike':   pinning_strike,
            'max_pain':         max_pain_strike,
            'supports':         supports,
            'resistances':      resistances,
        }

    def _check_pinning(self, spot: float, wall: float | None, tracker) -> tuple:
        """Returns (pinning_alert: bool, pinning_strike: float|None)."""
        if not wall or spot <= 0:
            return False, None

        dist = abs(spot - wall) / spot
        if dist > PINNING_TOLERANCE_PCT:
            # Not near the wall — reset counter
            tracker.set('pinning_cycle_count', 0)
            return False, None

        count = int(tracker.get('pinning_cycle_count') or 0) + 1
        tracker.set('pinning_cycle_count', count)

        if count >= PINNING_CYCLE_COUNT:
            return True, wall

        return False, None

    def _update_pinning_from_cache(self, cached: dict, tracker) -> dict:
        """Re-run pinning check on cached result with current spot."""
        try:
            symbol = self._get_symbol()
            spot = self._get_spot(symbol)
            wall = cached.get('near_expiry_wall')
            pinning_alert, pinning_strike = self._check_pinning(spot, wall, tracker)
            updated = dict(cached)
            updated['pinning_alert'] = pinning_alert
            updated['pinning_strike'] = pinning_strike
            return updated
        except Exception:
            return cached

    def _calc_max_pain(self, chain: list) -> float | None:
        """
        Max-pain strike = strike where total option holder pain is maximum.
        Computed as sum of intrinsic value of all ITM options at each strike.
        """
        strikes = [float(row.get('strike', 0)) for row in chain if row.get('strike')]
        if not strikes:
            return None

        min_pain = float('inf')
        max_pain_strike = None

        for test_strike in strikes:
            pain = 0.0
            for row in chain:
                s = float(row.get('strike', 0) or 0)
                ce_oi = float(row.get('ce_oi', 0) or 0)
                pe_oi = float(row.get('pe_oi', 0) or 0)
                # CE holders lose if spot > strike (CE ITM pain for writers)
                if test_strike > s:
                    pain += ce_oi * (test_strike - s)
                # PE holders lose if spot < strike (PE ITM pain for writers)
                if test_strike < s:
                    pain += pe_oi * (s - test_strike)

            if pain < min_pain:
                min_pain = pain
                max_pain_strike = test_strike

        return max_pain_strike

    def _get_symbol(self) -> str:
        # ContractData uses NSE code (e.g. HDFCBANK), not the Breeze HistoricalPrice code
        from apps.positions.services.sr_exit_engine import _position_oi_symbol
        return _position_oi_symbol(self._position)

    def _get_spot(self, symbol: str) -> float:
        from apps.positions.services.sr_exit_engine import _fetch_spot_price
        fallback = float(getattr(self._position, 'current_price', 0) or 0)
        return _fetch_spot_price(symbol, fallback)

    def _get_option_chain(self, symbol: str, spot: float) -> list:
        """
        Fetch option chain from ContractData.
        Returns list of {strike, ce_oi, pe_oi} dicts.
        """
        try:
            from apps.data.models import ContractData
            from django.utils import timezone
            today = timezone.localtime(timezone.now()).date()

            # Get all contracts for this symbol updated today
            contracts = ContractData.objects.filter(
                symbol=symbol,
                updated_at__date=today,
            ).values('strike_price', 'option_type', 'oi')

            # Build chain dict keyed by strike
            chain_map: dict = {}
            for c in contracts:
                strike = float(c.get('strike_price') or 0)
                if not strike:
                    continue
                opt_type = (c.get('option_type') or '').upper()
                oi = float(c.get('oi') or 0)
                if strike not in chain_map:
                    chain_map[strike] = {'strike': strike, 'ce_oi': 0.0, 'pe_oi': 0.0}
                if opt_type == 'CE':
                    chain_map[strike]['ce_oi'] += oi
                elif opt_type == 'PE':
                    chain_map[strike]['pe_oi'] += oi

            if not chain_map:
                return []

            # Filter to strikes within ±10% of spot (relevant range)
            lo = spot * 0.90
            hi = spot * 1.10
            chain = [v for k, v in chain_map.items() if lo <= k <= hi]
            chain.sort(key=lambda x: x['strike'])
            return chain

        except Exception as e:
            logger.debug(f"OIWallEnricher._get_option_chain error: {e}")
            return []


def _empty_result() -> dict:
    return {
        'gamma_wall_ce':    None,
        'gamma_wall_pe':    None,
        'near_expiry_wall': None,
        'far_expiry_wall':  None,
        'oi_delta_ce':      0.0,
        'oi_delta_pe':      0.0,
        'pinning_alert':    False,
        'pinning_strike':   None,
        'max_pain':         None,
        'supports':         [],
        'resistances':      [],
    }
