"""
Strike recommendation engine for Covered Call Protection.

Objective function is explicitly CAPITAL PRESERVATION, not premium
maximization: the highest-weighted score component rewards strikes that
close the gap between the futures average price and the market, not
strikes with the fattest absolute premium. SCORE_WEIGHTS below *is* the
product philosophy — keep it reviewable in one place, don't bury tuning
inside the scoring loop.

Every external data source used for context (support/resistance,
OI-based support/resistance) is best-effort: if historical/contract data
isn't available for a given symbol, that score component degrades to
neutral rather than raising. A data gap must never block a user trying to
reduce risk on a losing position.
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SCORE_WEIGHTS = {
    'breakeven_improvement': 0.35,
    'probability_otm': 0.30,
    'resistance_confluence': 0.20,
    'liquidity': 0.10,
    'theta': 0.05,
}

PRESET_CONSERVATIVE = 'CONSERVATIVE'
PRESET_BALANCED = 'BALANCED'
PRESET_AGGRESSIVE = 'AGGRESSIVE'


def _normalize(value: float, lo: float, hi: float) -> float:
    """Clamp+scale `value` into [0, 1] given an expected [lo, hi] range."""
    if hi == lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _get_resistance_levels(underlying_symbol: str, spot_price: float) -> Optional[dict]:
    try:
        from apps.strategies.services.support_resistance_calculator import SupportResistanceCalculator
        calc = SupportResistanceCalculator(symbol=underlying_symbol)
        return calc.calculate_comprehensive_sr(current_price=spot_price)
    except Exception as exc:  # best-effort signal only — never block the user on this
        logger.warning("S/R calculation unavailable for %s: %s", underlying_symbol, exc)
        return None


def _get_oi_based_resistance(underlying_symbol: str) -> Optional[dict]:
    try:
        from apps.strategies.services.oi_support_resistance import OISupportResistanceCalculator
        calc = OISupportResistanceCalculator(symbol=underlying_symbol)
        return calc.get_highest_oi_strikes(top_n=5)
    except Exception as exc:
        logger.warning("OI-based S/R unavailable for %s: %s", underlying_symbol, exc)
        return None


def calculate_max_pain(chain_rows: List[dict]) -> Optional[float]:
    """
    Standard max-pain algorithm: the strike where total option-writer
    payout (sum of ITM intrinsic value across all open calls + puts) is
    minimized. Computed self-contained from `chain_rows` (each row must
    carry 'open_interest' [call OI] and 'put_open_interest') rather than
    reused from apps.positions.services.oi_wall_enricher._calc_max_pain,
    which is tightly coupled to a specific Position/ContractData context
    this engine doesn't have — same well-known formula, no artificial
    dependency on unrelated app internals.
    """
    strikes = [float(row['strike']) for row in chain_rows if row.get('strike') is not None]
    if not strikes:
        return None
    min_pain, max_pain_strike = float('inf'), None
    for test_strike in strikes:
        pain = 0.0
        for row in chain_rows:
            s = float(row['strike'])
            ce_oi = float(row.get('open_interest', 0) or 0)
            pe_oi = float(row.get('put_open_interest', 0) or 0)
            if test_strike > s:
                pain += ce_oi * (test_strike - s)
            if test_strike < s:
                pain += pe_oi * (s - test_strike)
        if pain < min_pain:
            min_pain, max_pain_strike = pain, test_strike
    return max_pain_strike


@dataclass
class StrikeScore:
    strike: float
    premium: float
    delta: float
    theta: float
    open_interest: int
    breakeven_improvement_score: float
    probability_otm_score: float
    resistance_confluence_score: float
    liquidity_score: float
    theta_score: float
    composite_score: float
    effective_breakeven: float
    probability_otm_pct: float
    explanation: str


class CoveredCallRecommendationEngine:
    """
    Scores candidate call strikes for a covered call against an existing
    long futures position, ranked by capital-preservation quality — not
    raw premium size.
    """

    def __init__(
        self,
        underlying_symbol: str,
        spot_price: float,
        futures_avg_price: float,
        uncovered_lots: int,
        lot_size: int,
        days_to_expiry: int,
        chain_rows: List[dict],
        vix: Optional[float] = None,
    ):
        self.underlying_symbol = underlying_symbol
        self.spot_price = spot_price
        self.futures_avg_price = futures_avg_price
        self.uncovered_lots = uncovered_lots
        self.lot_size = lot_size
        self.days_to_expiry = days_to_expiry
        self.chain_rows = chain_rows
        self.vix = vix

        self._sr_data = _get_resistance_levels(underlying_symbol, spot_price)
        self._oi_sr_data = _get_oi_based_resistance(underlying_symbol)
        self._max_pain_strike = calculate_max_pain(chain_rows)

    def _resistance_confluence(self, strike: float) -> float:
        """
        Reward strikes near a resistance confluence (pivot R1/R2/R3,
        highest call-OI strike, or max pain) — statistically more likely
        to cap the position exactly where the market is already reluctant
        to go, reducing assignment risk relative to an arbitrary strike.
        """
        candidate_levels: List[float] = []
        if self._sr_data:
            pr = self._sr_data.get('primary_resistance', {}) or {}
            candidate_levels += [float(v) for v in (pr.get('r1'), pr.get('r2'), pr.get('r3')) if v]
        if self._oi_sr_data and self._oi_sr_data.get('available'):
            candidate_levels += [
                float(s['strike']) for s in self._oi_sr_data.get('highest_call_oi_strikes', [])
            ]
        if self._max_pain_strike:
            candidate_levels.append(float(self._max_pain_strike))

        if not candidate_levels:
            return 0.5  # neutral — no external confirmation available for this symbol

        # Distance-based proximity, scaled by price rather than a fixed point
        # count — strike intervals vary widely across the F&O universe.
        nearest_distance_pct = min(
            abs(strike - level) / max(self.spot_price, 1e-6) for level in candidate_levels
        )
        # Within 1% of a confluence level scores highest; beyond 8% scores ~0.
        return _normalize(0.08 - nearest_distance_pct, 0.0, 0.08)

    @staticmethod
    def _liquidity(row: dict) -> float:
        oi = row.get('open_interest') or 0
        bid, ask = row.get('bid') or 0, row.get('ask') or 0
        oi_score = _normalize(float(oi), 0, 5000)
        if bid and ask and (float(bid) + float(ask)) > 0:
            spread_pct = float(ask - bid) / (float(bid + ask) / 2) * 100
            spread_score = _normalize(10 - spread_pct, 0, 10)
        else:
            spread_score = 0.0
        return (oi_score + spread_score) / 2

    @staticmethod
    def _build_explanation(strike, premium, prob_otm_pct, resistance_score, breakeven, net_premium) -> str:
        parts = [
            f"Selling the {strike:.0f} Call",
            f"~{prob_otm_pct:.0f}% probability of expiring OTM",
            f"₹{premium:.2f} premium moves effective breakeven to ₹{breakeven:.2f}",
        ]
        if resistance_score >= 0.6:
            parts.append("sits near a resistance/OI confluence, adding confidence it holds")
        parts.append(f"generates ~₹{net_premium:,.0f} premium while capping upside above {strike:.0f}")
        return " • ".join(parts)

    def score_strikes(self) -> List[StrikeScore]:
        scored: List[StrikeScore] = []
        gap = max(self.futures_avg_price - self.spot_price, 0.0)
        covered_shares = max(self.uncovered_lots * self.lot_size, 1)

        for row in self.chain_rows:
            strike = float(row['strike'])
            premium = float(row['ltp'] or 0)
            delta = float(row.get('delta') or 0)
            theta = float(row.get('theta') or 0)

            net_premium_collected = premium * self.uncovered_lots * self.lot_size
            effective_breakeven = self.futures_avg_price - (net_premium_collected / covered_shares)

            # How much of the gap between avg cost and spot does this strike's
            # premium close? A position that isn't underwater scores this max.
            breakeven_improvement_score = 1.0 if gap <= 0 else _normalize(premium, 0, gap)

            probability_otm_pct = max(0.0, min(1.0, 1 - abs(delta))) * 100
            probability_otm_score = probability_otm_pct / 100.0

            resistance_confluence_score = self._resistance_confluence(strike)
            liquidity_score = self._liquidity(row)
            # call_theta from greeks_calculator is typically negative (value
            # decays as time passes); we are the seller, so larger-magnitude
            # decay is rewarded.
            theta_score = _normalize(abs(theta), 0, 5)

            composite = (
                SCORE_WEIGHTS['breakeven_improvement'] * breakeven_improvement_score
                + SCORE_WEIGHTS['probability_otm'] * probability_otm_score
                + SCORE_WEIGHTS['resistance_confluence'] * resistance_confluence_score
                + SCORE_WEIGHTS['liquidity'] * liquidity_score
                + SCORE_WEIGHTS['theta'] * theta_score
            )

            scored.append(StrikeScore(
                strike=strike, premium=premium, delta=delta, theta=theta,
                open_interest=int(row.get('open_interest') or 0),
                breakeven_improvement_score=breakeven_improvement_score,
                probability_otm_score=probability_otm_score,
                resistance_confluence_score=resistance_confluence_score,
                liquidity_score=liquidity_score,
                theta_score=theta_score,
                composite_score=composite,
                effective_breakeven=effective_breakeven,
                probability_otm_pct=probability_otm_pct,
                explanation=self._build_explanation(
                    strike, premium, probability_otm_pct, resistance_confluence_score,
                    effective_breakeven, net_premium_collected,
                ),
            ))

        scored.sort(key=lambda s: s.composite_score, reverse=True)
        return scored

    def get_presets(self) -> Dict[str, Optional[StrikeScore]]:
        """
        Conservative/Balanced/Aggressive are three points on the SAME
        capital-preservation objective function's risk curve, not three
        different objectives:
          - Conservative: lowest delta (furthest from assignment) among the
            well-scored candidates.
          - Aggressive: closest to spot (more premium, more breakeven
            improvement, higher assignment probability) among the
            well-scored candidates.
          - Balanced: the single best composite score overall.
        """
        scored = self.score_strikes()
        if not scored:
            return {PRESET_CONSERVATIVE: None, PRESET_BALANCED: None, PRESET_AGGRESSIVE: None}

        top_candidates = scored[: max(5, len(scored) // 3)]
        return {
            PRESET_CONSERVATIVE: min(top_candidates, key=lambda s: abs(s.delta)),
            PRESET_BALANCED: scored[0],
            PRESET_AGGRESSIVE: min(top_candidates, key=lambda s: s.strike),
        }
