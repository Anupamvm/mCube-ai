"""
Tests for recommendation_engine.py. The most important test here is a
regression guard on the product philosophy itself: capital preservation
over premium maximization. External data sources (support/resistance,
OI-based support/resistance, max pain) are patched to a neutral, uniform
signal so the tests isolate exactly the score component being verified,
rather than depending on real historical/contract data existing in the
test DB.
"""
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.hedging.services.recommendation_engine import (
    PRESET_AGGRESSIVE,
    PRESET_BALANCED,
    PRESET_CONSERVATIVE,
    CoveredCallRecommendationEngine,
    calculate_max_pain,
)

NEUTRALIZE_EXTERNAL_SIGNALS = {
    'apps.hedging.services.recommendation_engine._get_resistance_levels': None,
    'apps.hedging.services.recommendation_engine._get_oi_based_resistance': None,
}


def _patched_engine(*args, **kwargs):
    with patch('apps.hedging.services.recommendation_engine._get_resistance_levels', return_value=None), \
         patch('apps.hedging.services.recommendation_engine._get_oi_based_resistance', return_value=None), \
         patch('apps.hedging.services.recommendation_engine.calculate_max_pain', return_value=None):
        engine = CoveredCallRecommendationEngine(*args, **kwargs)
    return engine


class MaxPainTests(SimpleTestCase):
    def test_returns_none_for_empty_chain(self):
        self.assertIsNone(calculate_max_pain([]))

    def test_finds_strike_minimizing_total_writer_pain(self):
        # Two strikes, symmetric OI — max pain should land on one of them.
        chain = [
            {'strike': 480, 'open_interest': 1000, 'put_open_interest': 1000},
            {'strike': 500, 'open_interest': 1000, 'put_open_interest': 1000},
        ]
        result = calculate_max_pain(chain)
        self.assertIn(result, [480.0, 500.0])


class CapitalPreservationPhilosophyTests(SimpleTestCase):
    """
    The core regression guard: given two strikes with IDENTICAL premium
    (so breakeven improvement, liquidity, and theta scores are equal),
    the strike with the LOWER delta (higher probability of expiring OTM,
    i.e. safer / less likely to be assigned) must score higher. This is
    the mechanism that keeps the engine from degenerating into "just pick
    the fattest premium," which the product spec explicitly forbids.
    """

    def setUp(self):
        chain_rows = [
            {'strike': 490, 'ltp': 4.80, 'delta': 0.30, 'theta': -1.0, 'open_interest': 3000, 'bid': 4.75, 'ask': 4.85, 'put_open_interest': 2000},
            {'strike': 495, 'ltp': 4.80, 'delta': 0.55, 'theta': -1.0, 'open_interest': 3000, 'bid': 4.75, 'ask': 4.85, 'put_open_interest': 2000},
        ]
        self.engine = _patched_engine(
            underlying_symbol='RELIANCE', spot_price=467.30, futures_avg_price=482.54,
            uncovered_lots=90, lot_size=400, days_to_expiry=10, chain_rows=chain_rows,
        )

    def test_lower_delta_strike_outranks_equal_premium_higher_delta_strike(self):
        scored = self.engine.score_strikes()
        by_strike = {s.strike: s for s in scored}
        self.assertGreater(by_strike[490.0].composite_score, by_strike[495.0].composite_score)

    def test_lower_delta_strike_has_higher_probability_otm(self):
        scored = self.engine.score_strikes()
        by_strike = {s.strike: s for s in scored}
        self.assertGreater(by_strike[490.0].probability_otm_pct, by_strike[495.0].probability_otm_pct)

    def test_breakeven_improvement_score_equal_for_equal_premium(self):
        scored = self.engine.score_strikes()
        by_strike = {s.strike: s for s in scored}
        self.assertAlmostEqual(
            by_strike[490.0].breakeven_improvement_score,
            by_strike[495.0].breakeven_improvement_score,
            places=6,
        )


class PresetTests(SimpleTestCase):
    def setUp(self):
        chain_rows = [
            {'strike': 480, 'ltp': 8.00, 'delta': 0.60, 'theta': -1.5, 'open_interest': 4000, 'bid': 7.9, 'ask': 8.1, 'put_open_interest': 2000},
            {'strike': 490, 'ltp': 5.00, 'delta': 0.40, 'theta': -1.2, 'open_interest': 4000, 'bid': 4.9, 'ask': 5.1, 'put_open_interest': 2000},
            {'strike': 500, 'ltp': 3.00, 'delta': 0.25, 'theta': -0.9, 'open_interest': 4000, 'bid': 2.9, 'ask': 3.1, 'put_open_interest': 2000},
            {'strike': 510, 'ltp': 1.50, 'delta': 0.12, 'theta': -0.5, 'open_interest': 4000, 'bid': 1.4, 'ask': 1.6, 'put_open_interest': 2000},
            {'strike': 520, 'ltp': 0.75, 'delta': 0.05, 'theta': -0.3, 'open_interest': 4000, 'bid': 0.7, 'ask': 0.8, 'put_open_interest': 2000},
        ]
        self.engine = _patched_engine(
            underlying_symbol='RELIANCE', spot_price=467.30, futures_avg_price=482.54,
            uncovered_lots=90, lot_size=400, days_to_expiry=10, chain_rows=chain_rows,
        )

    def test_all_three_presets_present(self):
        presets = self.engine.get_presets()
        self.assertIn(PRESET_CONSERVATIVE, presets)
        self.assertIn(PRESET_BALANCED, presets)
        self.assertIn(PRESET_AGGRESSIVE, presets)
        for p in presets.values():
            self.assertIsNotNone(p)

    def test_conservative_has_the_lowest_delta_in_the_chain(self):
        # By construction, CONSERVATIVE = min(|delta|) among the top-scored
        # candidates; with a monotonic delta/strike chain like this fixture,
        # that is deterministically the highest-strike, lowest-delta row —
        # regardless of which strike wins the overall composite score.
        presets = self.engine.get_presets()
        self.assertEqual(presets[PRESET_CONSERVATIVE].strike, 520.0)
        self.assertAlmostEqual(abs(presets[PRESET_CONSERVATIVE].delta), 0.05, places=4)

    def test_aggressive_has_the_lowest_strike_in_the_chain(self):
        # By construction, AGGRESSIVE = min(strike) among the top-scored
        # candidates — deterministic for the same reason as above.
        presets = self.engine.get_presets()
        self.assertEqual(presets[PRESET_AGGRESSIVE].strike, 480.0)

    def test_empty_chain_returns_all_none(self):
        engine = _patched_engine(
            underlying_symbol='RELIANCE', spot_price=467.30, futures_avg_price=482.54,
            uncovered_lots=90, lot_size=400, days_to_expiry=10, chain_rows=[],
        )
        presets = engine.get_presets()
        self.assertTrue(all(v is None for v in presets.values()))


class NotUnderwaterTests(SimpleTestCase):
    def test_breakeven_improvement_maxed_when_position_already_profitable(self):
        # spot > futures_avg_price -> gap is 0 -> every strike scores 1.0 on this component.
        chain_rows = [
            {'strike': 500, 'ltp': 3.00, 'delta': 0.30, 'theta': -1.0, 'open_interest': 3000, 'bid': 2.9, 'ask': 3.1, 'put_open_interest': 2000},
        ]
        engine = _patched_engine(
            underlying_symbol='RELIANCE', spot_price=490.0, futures_avg_price=460.0,
            uncovered_lots=90, lot_size=400, days_to_expiry=10, chain_rows=chain_rows,
        )
        scored = engine.score_strikes()
        self.assertEqual(scored[0].breakeven_improvement_score, 1.0)
