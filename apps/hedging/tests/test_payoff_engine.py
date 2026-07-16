"""
Pure-math tests for payoff_engine.py — the highest-risk module in this
feature since it's the number the whole "Cover Position" UI is built
around. No Django DB access needed; these are plain function calls.
"""
from django.test import SimpleTestCase

from apps.hedging.services import payoff_engine


class EffectiveBreakevenTests(SimpleTestCase):
    def test_reduces_breakeven_by_premium_per_share(self):
        # 90 lots x 400 shares/lot, premium 4.80/share collected.
        be = payoff_engine.calculate_effective_breakeven(482.54, 90, 400, 90 * 400 * 4.80)
        self.assertAlmostEqual(be, 482.54 - 4.80, places=6)

    def test_zero_coverage_returns_avg_price_unchanged(self):
        be = payoff_engine.calculate_effective_breakeven(482.54, 0, 400, 0)
        self.assertEqual(be, 482.54)


class PayoffAtExpiryTests(SimpleTestCase):
    def setUp(self):
        # Fully covered: 90 futures lots, 90 call lots sold at strike 490 for 4.80.
        self.curve = payoff_engine.calculate_payoff_at_expiry(
            [460, 470, 480, 490, 500, 510], 482.54, 90, 400, 490, 4.80, 90,
        )
        self.by_spot = {p['spot']: p for p in self.curve}

    def test_below_strike_call_keeps_full_premium(self):
        below = self.by_spot[460]
        self.assertAlmostEqual(below['call_pnl'], 4.80 * 90 * 400, places=2)

    def test_at_strike_call_still_keeps_full_premium(self):
        at_strike = self.by_spot[490]
        self.assertAlmostEqual(at_strike['call_pnl'], 4.80 * 90 * 400, places=2)

    def test_above_strike_call_pnl_reduced_by_intrinsic_value(self):
        above = self.by_spot[510]
        expected_call_pnl = (4.80 - (510 - 490)) * 90 * 400
        self.assertAlmostEqual(above['call_pnl'], expected_call_pnl, places=2)

    def test_total_pnl_is_sum_of_legs(self):
        for point in self.curve:
            self.assertAlmostEqual(point['total_pnl'], point['futures_pnl'] + point['call_pnl'], places=6)

    def test_fully_covered_position_plateaus_above_strike(self):
        # With call_lots == futures_lots, total P&L above the strike must be flat.
        pnl_500 = self.by_spot[500]['total_pnl']
        pnl_510 = self.by_spot[510]['total_pnl']
        self.assertAlmostEqual(pnl_500, pnl_510, places=2)

    def test_zero_premium_edge_case(self):
        curve = payoff_engine.calculate_payoff_at_expiry([480, 500], 482.54, 10, 400, 490, 0.0, 10)
        for point in curve:
            self.assertAlmostEqual(point['call_pnl'], 0.0 if point['spot'] <= 490 else -(point['spot'] - 490) * 10 * 400, places=2)


class CappingTests(SimpleTestCase):
    def test_is_fully_capped_true_when_call_lots_equal_futures_lots(self):
        self.assertTrue(payoff_engine.is_fully_capped(90, 90))

    def test_is_fully_capped_false_for_partial_coverage(self):
        self.assertFalse(payoff_engine.is_fully_capped(90, 40))

    def test_max_profit_none_when_partially_covered(self):
        max_profit = payoff_engine.calculate_max_profit(482.54, 90, 400, 490, 4.80, 40)
        self.assertIsNone(max_profit)

    def test_max_profit_returns_value_when_fully_covered(self):
        max_profit = payoff_engine.calculate_max_profit(482.54, 90, 400, 490, 4.80, 90)
        self.assertIsNotNone(max_profit)
        expected = (490 - 482.54) * 90 * 400 + 4.80 * 90 * 400
        self.assertAlmostEqual(max_profit, expected, places=2)

    def test_capped_upside_price_matches_strike_when_fully_covered(self):
        self.assertEqual(payoff_engine.calculate_capped_upside_price(90, 490, 90), 490)

    def test_capped_upside_price_none_when_partially_covered(self):
        self.assertIsNone(payoff_engine.calculate_capped_upside_price(90, 490, 40))


class ProtectionMetricsTests(SimpleTestCase):
    def test_protection_pct_none_when_not_underwater(self):
        result = payoff_engine.calculate_protection_metrics(480.0, 490.0, 1000.0, 10, 400)
        self.assertIsNone(result['protection_pct'])

    def test_protection_pct_capped_at_100(self):
        # Premium collected far exceeds the open loss — protection can't exceed 100%.
        result = payoff_engine.calculate_protection_metrics(500.0, 480.0, 10_000_000.0, 10, 400)
        self.assertEqual(result['protection_pct'], 100.0)

    def test_protection_pct_partial(self):
        # Open loss = 20/share. Premium collected = 5/share -> 25% protection.
        result = payoff_engine.calculate_protection_metrics(500.0, 480.0, 5 * 10 * 400, 10, 400)
        self.assertAlmostEqual(result['protection_pct'], 25.0, places=2)


class ZeroCrossingTests(SimpleTestCase):
    def test_finds_interpolated_breakeven_point(self):
        curve = [
            {'spot': 470, 'total_pnl': -1000, 'futures_pnl': 0, 'call_pnl': 0},
            {'spot': 480, 'total_pnl': 1000, 'futures_pnl': 0, 'call_pnl': 0},
        ]
        crossings = payoff_engine.find_zero_crossings(curve)
        self.assertEqual(len(crossings), 1)
        self.assertAlmostEqual(crossings[0], 475.0, places=2)

    def test_no_crossing_when_curve_never_changes_sign(self):
        curve = [
            {'spot': 470, 'total_pnl': 1000, 'futures_pnl': 0, 'call_pnl': 0},
            {'spot': 480, 'total_pnl': 2000, 'futures_pnl': 0, 'call_pnl': 0},
        ]
        self.assertEqual(payoff_engine.find_zero_crossings(curve), [])
