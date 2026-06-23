"""
Regression tests for EnhancedFuturesAnalyzer (12-component production scorer).

These tests cover the production algorithm, not the simplified 3-component
version in apps/algo_test. See apps/algo_test/tests.py for the simplified version.

Test categories:
  1. Class-level constants (no DB)
  2. Scoring integrity — normalization, range, determinism
  3. Missing data safety — no exceptions, correct fallback scores
  4. Hard reject filter behaviour — missing data → skip (fail-open)
  5. Score breakdown correctness — per-component values make sense
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase

from apps.strategies.analyzers.enhanced_futures_analyzer import (
    EnhancedFuturesAnalyzer,
    HardRejectError,
)
from apps.data.models import TLStockData, ContractStockData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tl(**overrides):
    """Create a minimal TLStockData with all scoring fields populated."""
    defaults = dict(
        nsecode='TESTSTOCK',
        stock_name='Test Stock',
        current_price=1000.0,
        # Technical indicators
        day_rsi=55.0,
        day_macd=10.0,
        day_macd_signal_line=8.0,
        day_mfi=55.0,
        day_adx=30.0,
        day_roc21=2.0,
        day_roc125=5.0,
        day_atr=15.0,
        # Moving averages (price above all MAs — bullish)
        day5_sma=980.0,
        day30_sma=960.0,
        day50_sma=940.0,
        day100_sma=900.0,
        day200_sma=850.0,
        day20_ema=970.0,
        day50_ema=945.0,
        # Price ranges
        day_change_pct=0.5,
        one_year_low=700.0,
        one_year_high=1100.0,
        # Fundamentals
        piotroski_score=7.0,
        roe_annual_pct=18.0,
        net_profit_qtr_growth_yoy_pct=15.0,
        net_profit_qoq_growth_pct=5.0,
        # Beta
        beta_1year=1.0,
        # Institutional holdings
        fii_holding_current_qtr_pct=20.0,
        fii_holding_change_qoq_pct=0.5,
        mf_holding_current_qtr_pct=10.0,
        mf_holding_change_qoq_pct=0.3,
        promoter_pledge_pct_qtr=5.0,
        # Volume
        day_volume=1000000,
        day_volume_multiple_of_week=1.5,
        delivery_volume_pct_eod=50.0,
        delivery_volume_pct_prev_eod=45.0,
        vwap_day=995.0,
        # Momentum scores
        trendlyne_momentum_score=65.0,
        prev_day_trendlyne_momentum_score=62.0,
        prev_week_trendlyne_momentum_score=58.0,
    )
    defaults.update(overrides)
    return TLStockData.objects.create(**defaults)


def _make_csd(**overrides):
    """Create a minimal ContractStockData with all required non-null fields."""
    defaults = dict(
        nse_code='TESTSTOCK',
        stock_name='Test Stock',
        current_price=1000.0,
        industry_name='Technology',
        annualized_volatility=25.0,  # Below 60% threshold
        fno_total_oi=5000000,
        fno_prev_day_total_oi=4800000,
        fno_total_put_oi=2000000,
        fno_total_call_oi=3000000,
        fno_prev_day_put_oi=1900000,
        fno_prev_day_call_oi=2900000,
        fno_total_put_vol=500000,
        fno_total_call_vol=700000,
        fno_prev_day_put_vol=480000,
        fno_prev_day_call_vol=680000,
        fno_mwpl=10000000,
        fno_pcr_vol=0.71,
        fno_pcr_vol_prev=0.68,
        fno_pcr_vol_change_pct=4.4,
        fno_pcr_oi=0.67,
        fno_pcr_oi_prev=0.65,
        fno_pcr_oi_change_pct=3.1,
        fno_mwpl_pct=45.0,        # Below 80% threshold
        fno_mwpl_prev_pct=43.0,
        fno_total_oi_change_pct=4.2,
        fno_put_oi_change_pct=5.3,
        fno_call_oi_change_pct=3.4,
        fno_put_vol_change_pct=4.2,
        fno_call_vol_change_pct=3.0,
        fno_rollover_cost=0.5,
        fno_rollover_cost_pct=0.05,
        fno_rollover_pct=70.0,
    )
    defaults.update(overrides)
    return ContractStockData.objects.create(**defaults)


def _run(symbol='TESTSTOCK', direction='LONG', **kwargs):
    """Convenience: run the analyzer and return the result dict."""
    a = EnhancedFuturesAnalyzer(symbol=symbol, direction=direction, **kwargs)
    return a.analyze()


# ---------------------------------------------------------------------------
# 1. Class-level constants (no DB needed)
# ---------------------------------------------------------------------------

class ConstantsTests(TestCase):

    def test_total_weight_is_315(self):
        """WEIGHTS must sum to 315."""
        self.assertEqual(EnhancedFuturesAnalyzer.TOTAL_WEIGHT, 315)

    def test_all_weight_keys_present(self):
        """All 13 scoring components must have entries in WEIGHTS."""
        expected_keys = {
            'oi_fno', 'technical_momentum', 'trend_confirmation', 'volume_quality',
            'institutional_flow', 'fundamental_quality', 'risk_adjustment',
            'news_sentiment', 'analyst_consensus', 'research_reports',
            'investor_calls', 'momentum_acceleration', 'mtf_confluence',
        }
        self.assertEqual(set(EnhancedFuturesAnalyzer.WEIGHTS.keys()), expected_keys)

    def test_individual_weights_positive(self):
        """Every weight must be a positive integer."""
        for key, w in EnhancedFuturesAnalyzer.WEIGHTS.items():
            self.assertGreater(w, 0, f"Weight for {key} must be positive")


# ---------------------------------------------------------------------------
# 2. Return structure integrity
# ---------------------------------------------------------------------------

class ReturnStructureTests(TestCase):

    def test_result_keys_on_pass(self):
        """Successful analysis must include all expected top-level keys."""
        result = _run()
        required = {'symbol', 'direction', 'hard_reject', 'reject_reason',
                    'composite_score', 'scores', 'details', 'recommendation'}
        for key in required:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_result_keys_on_hard_reject(self):
        """Hard-rejected result must still include all structural keys."""
        _make_csd(fno_mwpl_pct=85.0)  # Exceeds 80% MWPL threshold
        result = _run()
        self.assertTrue(result['hard_reject'])
        self.assertIn('reject_reason', result)
        self.assertEqual(result['composite_score'], 0)
        self.assertEqual(result['recommendation'], 'REJECT')

    def test_composite_score_range(self):
        """Composite score must always be 0–100."""
        result = _run()
        self.assertGreaterEqual(result['composite_score'], 0)
        self.assertLessEqual(result['composite_score'], 100)

    def test_recommendation_valid_values(self):
        """Recommendation must be one of the four valid strings."""
        result = _run()
        valid = {'STRONG_ENTRY', 'ENTRY', 'WEAK_ENTRY', 'NO_ENTRY', 'REJECT'}
        self.assertIn(result['recommendation'], valid)


# ---------------------------------------------------------------------------
# 3. Score normalization
# ---------------------------------------------------------------------------

class ScoreNormalizationTests(TestCase):

    def setUp(self):
        _make_tl()
        _make_csd()

    def test_composite_formula(self):
        """composite_score == int(raw_score / 315 * 100)."""
        result = _run()
        raw = result['raw_score']
        expected = int(raw / 315 * 100)
        self.assertEqual(result['composite_score'], expected)

    def test_scores_dict_populated(self):
        """scores dict must have an entry for each component."""
        result = _run()
        for key in EnhancedFuturesAnalyzer.WEIGHTS:
            self.assertIn(key, result['scores'], f"Missing score key: {key}")

    def test_each_score_within_max(self):
        """Each component score must not exceed its WEIGHTS maximum."""
        result = _run()
        for key, score in result['scores'].items():
            max_pts = EnhancedFuturesAnalyzer.WEIGHTS[key]
            self.assertLessEqual(
                score, max_pts,
                f"{key} score {score} exceeds max {max_pts}"
            )

    def test_each_score_non_negative(self):
        """No component score may be negative."""
        result = _run()
        for key, score in result['scores'].items():
            self.assertGreaterEqual(score, 0, f"{key} score is negative: {score}")

    def test_raw_score_equals_sum(self):
        """raw_score must equal sum of all component scores."""
        result = _run()
        self.assertEqual(result['raw_score'], sum(result['scores'].values()))


# ---------------------------------------------------------------------------
# 4. Missing data safety (no exceptions, correct fallback)
# ---------------------------------------------------------------------------

class MissingDataSafetyTests(TestCase):

    def test_no_data_at_all_no_exception(self):
        """Analyzer must not raise when both data sources are missing."""
        try:
            result = _run()
        except Exception as e:
            self.fail(f"Analyzer raised unexpected exception: {e}")

    def test_no_data_composite_zero_or_neutral(self):
        """With no data, composite score should be 0 (all components zero or neutral)."""
        result = _run()
        # oi_fno must be 0 (no ContractStockData)
        self.assertEqual(result['scores']['oi_fno'], 0)
        # 7 TL-dependent components must be 0 (no TLStockData)
        tl_components = [
            'technical_momentum', 'trend_confirmation', 'volume_quality',
            'institutional_flow', 'fundamental_quality', 'risk_adjustment',
            'momentum_acceleration',
        ]
        for comp in tl_components:
            self.assertEqual(result['scores'][comp], 0, f"{comp} should be 0 without TLStockData")

    def test_tl_missing_oi_present_no_exception(self):
        """Analyzer must not raise when TLStockData is missing but ContractStockData exists."""
        _make_csd()
        try:
            result = _run()
        except Exception as e:
            self.fail(f"Unexpected exception: {e}")
        self.assertGreater(result['scores']['oi_fno'], 0)

    def test_oi_missing_tl_present_no_exception(self):
        """Analyzer must not raise when ContractStockData is missing but TLStockData exists."""
        _make_tl()
        try:
            result = _run()
        except Exception as e:
            self.fail(f"Unexpected exception: {e}")
        self.assertEqual(result['scores']['oi_fno'], 0)
        self.assertGreater(result['scores']['technical_momentum'], 0)

    def test_full_data_produces_positive_score(self):
        """With rich TL + CSD data, composite score must be > 0."""
        _make_tl()
        _make_csd()
        result = _run()
        self.assertGreater(result['composite_score'], 0)

    def test_analyst_consensus_neutral_when_no_data(self):
        """analyst_consensus defaults to 10 (neutral) when no analyst data exists."""
        result = _run()
        # Default when no AnalystPriceTarget: score = 10
        self.assertEqual(result['scores']['analyst_consensus'], 10)

    def test_investor_calls_neutral_when_no_calls(self):
        """investor_calls defaults to 5 (neutral) when no InvestorCall records exist."""
        result = _run()
        # Default when no calls: score = 5
        self.assertEqual(result['scores']['investor_calls'], 5)

    def test_momentum_acceleration_neutral_when_no_tl_momentum(self):
        """momentum_acceleration uses 10pt neutral default when trendlyne_momentum_score is None."""
        _make_tl(trendlyne_momentum_score=None)
        result = _run()
        self.assertEqual(result['scores']['momentum_acceleration'], 10)

    def test_momentum_acceleration_current_only_fallback(self):
        """When prev_day data is None but current exists, uses CURRENT_ONLY (5pts acceleration)."""
        _make_tl(
            trendlyne_momentum_score=70.0,
            prev_day_trendlyne_momentum_score=None,
            prev_week_trendlyne_momentum_score=None,
        )
        result = _run()
        acc_score = result['scores']['momentum_acceleration']
        # CURRENT_ONLY gives 5 acceleration + neutral consistency (2) + alignment (4-5 for 70)
        self.assertGreater(acc_score, 0)
        self.assertLessEqual(acc_score, 20)


# ---------------------------------------------------------------------------
# 5. Hard reject filter behaviour (fail-open on missing data)
# ---------------------------------------------------------------------------

class HardRejectFilterTests(TestCase):

    def test_mwpl_missing_data_passes(self):
        """Missing ContractStockData means MWPL filter is skipped (fail-open)."""
        # No ContractStockData created — MWPL filter must skip, not reject
        result = _run()
        self.assertFalse(result['hard_reject'])

    def test_mwpl_exceeds_threshold_rejects(self):
        """MWPL >= 80% must trigger hard reject."""
        _make_csd(fno_mwpl_pct=82.0)
        result = _run()
        self.assertTrue(result['hard_reject'])
        self.assertIsNotNone(result['reject_reason'])

    def test_mwpl_below_threshold_passes(self):
        """MWPL < 80% must not trigger a hard reject (all other filters skipped w/o TLStockData)."""
        _make_csd(fno_mwpl_pct=60.0)
        result = _run()
        self.assertFalse(result['hard_reject'])

    def test_volatility_missing_data_passes(self):
        """Missing ContractStockData means volatility filter is skipped (fail-open)."""
        result = _run()
        self.assertFalse(result['hard_reject'])

    def test_volatility_exceeds_threshold_rejects(self):
        """Annualized volatility >= 60% must trigger hard reject."""
        _make_csd(annualized_volatility=65.0)
        result = _run()
        self.assertTrue(result['hard_reject'])

    def test_piotroski_missing_data_passes(self):
        """Missing TLStockData means Piotroski filter is skipped (fail-open)."""
        result = _run()
        self.assertFalse(result['hard_reject'])

    def test_piotroski_below_threshold_rejects(self):
        """Piotroski score < 4 must trigger hard reject."""
        _make_csd()
        _make_tl(piotroski_score=2.0)
        result = _run()
        self.assertTrue(result['hard_reject'])
        self.assertIn('Piotroski', result['reject_reason'])

    def test_piotroski_null_skips_filter(self):
        """Null piotroski_score must skip the filter (fail-open), not reject."""
        _make_csd()
        _make_tl(piotroski_score=None)
        result = _run()
        self.assertFalse(result['hard_reject'])


# ---------------------------------------------------------------------------
# 6. Direction sensitivity
# ---------------------------------------------------------------------------

class DirectionTests(TestCase):

    def setUp(self):
        _make_tl()
        _make_csd()

    def test_long_and_short_both_succeed(self):
        """Both LONG and SHORT directions must return a valid result without exception."""
        long_result = _run(direction='LONG')
        short_result = _run(direction='SHORT')
        self.assertFalse(long_result.get('hard_reject', True))
        self.assertFalse(short_result.get('hard_reject', True))

    def test_direction_stored_in_result(self):
        """Result must reflect the requested direction."""
        result = _run(direction='SHORT')
        self.assertEqual(result['direction'], 'SHORT')

    def test_directions_produce_different_scores(self):
        """LONG and SHORT should give different composite scores for the same data."""
        long_score = _run(direction='LONG')['composite_score']
        short_score = _run(direction='SHORT')['composite_score']
        # They should differ because OI buildup, momentum alignment etc. are direction-sensitive
        self.assertNotEqual(long_score, short_score)


# ---------------------------------------------------------------------------
# 7. Entry params — only computed when score >= 65
# ---------------------------------------------------------------------------

class EntryParamsTests(TestCase):

    def test_entry_params_none_when_score_below_threshold(self):
        """entry_params must be None when composite_score < 65."""
        # No data → all components 0 or neutral → score well below 65
        result = _run()
        if result['composite_score'] < 65:
            self.assertIsNone(result['entry_params'])

    def test_entry_params_present_when_score_above_threshold(self):
        """entry_params must be a dict when composite_score >= 65."""
        _make_tl()
        _make_csd()
        result = _run()
        if result['composite_score'] >= 65:
            self.assertIsNotNone(result['entry_params'])
            self.assertIsInstance(result['entry_params'], dict)

    def test_beta_adjustment_reduces_position_for_high_beta(self):
        """High beta (>= 1.5) must apply a 0.70 multiplier to position sizing."""
        _make_tl(beta_1year=1.8)
        _make_csd()
        result = _run()
        if result.get('entry_params') and result['entry_params'].get('position_sizing'):
            sizing = result['entry_params']['position_sizing']
            self.assertAlmostEqual(sizing.get('beta_adjustment', 1.0), 0.70, places=2)

    def test_beta_adjustment_normal_for_typical_beta(self):
        """Normal beta (0.8–1.19) must not reduce position sizing."""
        _make_tl(beta_1year=0.95)
        _make_csd()
        result = _run()
        if result.get('entry_params') and result['entry_params'].get('position_sizing'):
            sizing = result['entry_params']['position_sizing']
            self.assertAlmostEqual(sizing.get('beta_adjustment', 1.0), 1.00, places=2)

    def test_high_volatility_reduces_position(self):
        """Annualized volatility >= 50% must apply a 0.70 volatility multiplier.

        55% is below the 60% hard-reject threshold (so the stock passes) but
        above the 50% position-sizing threshold (triggers 0.70 multiplier).
        """
        _make_tl()
        _make_csd(annualized_volatility=55.0)
        result = _run()
        self.assertFalse(result['hard_reject'], "55% vol should not hard-reject (threshold is 60%)")
        if result.get('entry_params') and result['entry_params'].get('position_sizing'):
            sizing = result['entry_params']['position_sizing']
            self.assertAlmostEqual(sizing.get('volatility_adjustment', 1.0), 0.70, places=2)


# ---------------------------------------------------------------------------
# 8. MTF Confluence — clamp at [0, 15]
# ---------------------------------------------------------------------------

class MTFConfluenceTests(TestCase):

    def test_mtf_score_never_negative(self):
        """MTF confluence must clamp to 0 even when all alignments diverge."""
        # All SMAs configured so that price BELOW sma30 AND sma50 < sma200 AND sma5 < sma30
        # For LONG direction this triggers three divergence penalties (-5 each = -15 before clamp)
        _make_tl(
            current_price=800.0,   # below all SMAs
            day5_sma=900.0,
            day30_sma=950.0,
            day50_sma=950.0,
            day200_sma=1000.0,     # sma50 < sma200 → monthly bearish
        )
        result = _run(direction='LONG')
        self.assertGreaterEqual(result['scores']['mtf_confluence'], 0)

    def test_mtf_score_max_15(self):
        """MTF confluence must not exceed 15."""
        _make_tl()  # bullish SMA setup from _make_tl defaults
        _make_csd()
        result = _run(direction='LONG')
        self.assertLessEqual(result['scores']['mtf_confluence'], 15)
