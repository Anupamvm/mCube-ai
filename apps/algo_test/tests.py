from django.test import TestCase
from decimal import Decimal
from apps.algo_test.services import OptionsAlgorithmCalculator, FuturesAlgorithmCalculator
from datetime import datetime


class OptionsAlgorithmTestCase(TestCase):
    """Test Options Algorithm Calculations"""

    def test_vix_adjusted_delta(self):
        """Test VIX-based delta adjustment"""
        # VIX < 15
        delta = OptionsAlgorithmCalculator.get_vix_adjusted_delta(Decimal('14'))
        self.assertEqual(delta, Decimal('0.5'))

        # VIX 15-18
        delta = OptionsAlgorithmCalculator.get_vix_adjusted_delta(Decimal('16'))
        self.assertEqual(delta, Decimal('0.55'))

        # VIX > 18
        delta = OptionsAlgorithmCalculator.get_vix_adjusted_delta(Decimal('20'))
        self.assertEqual(delta, Decimal('0.6'))

    def test_strike_calculation(self):
        """Test strike distance and rounding"""
        spot = Decimal('24000')
        vix = Decimal('14.5')
        days = 4

        call_strike, put_strike, adjusted_delta = OptionsAlgorithmCalculator.calculate_strikes(
            spot, vix, days
        )

        # Verify strikes are rounded to 100
        self.assertEqual(call_strike % 100, 0)
        self.assertEqual(put_strike % 100, 0)

        # Verify call strike > spot and put strike < spot
        self.assertGreater(call_strike, int(spot))
        self.assertLess(put_strike, int(spot))


class FuturesAlgorithmTestCase(TestCase):
    """Test Futures Algorithm Scoring"""

    def test_oi_score_long_buildup(self):
        """Test OI scoring for long buildup"""
        score, details = FuturesAlgorithmCalculator.calculate_oi_score(
            price_change_pct=Decimal('1.24'),  # Price up
            oi_change_pct=Decimal('5.93'),     # OI up
            pcr_ratio=Decimal('1.31')
        )

        self.assertEqual(details['buildup_pattern'], 'LONG_BUILDUP')
        self.assertGreater(score, Decimal('0'))

    def test_sector_score_all_positive(self):
        """Test sector scoring with all positive timeframes"""
        score, details = FuturesAlgorithmCalculator.calculate_sector_score(
            sector_3d_change=Decimal('2.1'),
            sector_7d_change=Decimal('4.8'),
            sector_21d_change=Decimal('8.3'),
            direction='LONG'
        )

        self.assertEqual(score, Decimal('25'))
        self.assertEqual(details['verdict'], 'APPROVED_FOR_LONG')

    def test_sector_score_mixed(self):
        """Test sector scoring with mixed signals"""
        score, details = FuturesAlgorithmCalculator.calculate_sector_score(
            sector_3d_change=Decimal('2.1'),
            sector_7d_change=Decimal('-4.8'),  # Negative
            sector_21d_change=Decimal('8.3'),
            direction='LONG'
        )

        self.assertEqual(score, Decimal('0'))
        self.assertEqual(details['verdict'], 'BLOCKED_MIXED_SIGNALS')
