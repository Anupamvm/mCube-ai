"""
Tests for every safety rule enforced in validators.py — the single source
of truth for "never sell more calls than uncovered futures lots", expiry
alignment, lot-size matching, duplicate-order locking, and liquidity
warnings.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from apps.accounts.models import BrokerAccount
from apps.hedging.models import HEDGE_STATUS_ACTIVE, HedgePosition
from apps.hedging.services.validators import (
    HedgeValidationError,
    acquire_placement_lock,
    assess_liquidity_warnings,
    find_existing_active_hedge,
    release_placement_lock,
    validate_expiry_alignment,
    validate_lot_size_match,
    validate_margin,
    validate_quantity_cap,
)


class QuantityCapTests(TestCase):
    def test_passes_when_within_uncovered_lots(self):
        validate_quantity_cap(live_futures_lots=90, already_covered_lots=20, requested_lots=40)  # no raise

    def test_rejects_when_exceeding_uncovered_lots(self):
        with self.assertRaises(HedgeValidationError) as ctx:
            validate_quantity_cap(live_futures_lots=90, already_covered_lots=60, requested_lots=40)
        self.assertEqual(ctx.exception.code, 'QTY_EXCEEDS_UNCOVERED')

    def test_rejects_zero_or_negative_quantity(self):
        with self.assertRaises(HedgeValidationError) as ctx:
            validate_quantity_cap(live_futures_lots=90, already_covered_lots=0, requested_lots=0)
        self.assertEqual(ctx.exception.code, 'INVALID_QUANTITY')

    def test_exact_uncovered_amount_is_allowed(self):
        validate_quantity_cap(live_futures_lots=90, already_covered_lots=50, requested_lots=40)  # no raise


class ExpiryAlignmentTests(TestCase):
    def test_passes_when_option_expiry_before_futures_expiry(self):
        validate_expiry_alignment(datetime.date(2026, 7, 23), datetime.date(2026, 7, 30))  # no raise

    def test_passes_when_option_expiry_equals_futures_expiry(self):
        validate_expiry_alignment(datetime.date(2026, 7, 30), datetime.date(2026, 7, 30))  # no raise

    def test_rejects_option_expiry_after_futures_expiry(self):
        with self.assertRaises(HedgeValidationError) as ctx:
            validate_expiry_alignment(datetime.date(2026, 8, 6), datetime.date(2026, 7, 30))
        self.assertEqual(ctx.exception.code, 'EXPIRY_MISMATCH')


class LotSizeMatchTests(TestCase):
    def test_passes_when_equal(self):
        validate_lot_size_match(400, 400)  # no raise

    def test_rejects_mismatch(self):
        with self.assertRaises(HedgeValidationError) as ctx:
            validate_lot_size_match(500, 400)
        self.assertEqual(ctx.exception.code, 'LOT_SIZE_MISMATCH')


class PlacementLockTests(TestCase):
    def tearDown(self):
        cache.clear()

    def test_second_acquire_fails_while_first_held(self):
        acquired1, key1 = acquire_placement_lock(1, 'breeze', 'RELIANCE', 490, datetime.date(2026, 7, 30))
        acquired2, key2 = acquire_placement_lock(1, 'breeze', 'RELIANCE', 490, datetime.date(2026, 7, 30))
        self.assertTrue(acquired1)
        self.assertFalse(acquired2)
        self.assertEqual(key1, key2)

    def test_release_allows_reacquire(self):
        acquired1, key1 = acquire_placement_lock(1, 'breeze', 'RELIANCE', 490, datetime.date(2026, 7, 30))
        self.assertTrue(acquired1)
        release_placement_lock(key1)
        acquired2, _ = acquire_placement_lock(1, 'breeze', 'RELIANCE', 490, datetime.date(2026, 7, 30))
        self.assertTrue(acquired2)

    def test_different_strikes_do_not_collide(self):
        acquired1, _ = acquire_placement_lock(1, 'breeze', 'RELIANCE', 490, datetime.date(2026, 7, 30))
        acquired2, _ = acquire_placement_lock(1, 'breeze', 'RELIANCE', 500, datetime.date(2026, 7, 30))
        self.assertTrue(acquired1)
        self.assertTrue(acquired2)


class ExistingActiveHedgeTests(TestCase):
    def setUp(self):
        self.account = BrokerAccount.objects.create(
            broker='ICICI', account_number='TEST001', account_name='Test',
            allocated_capital=Decimal('1000000'), max_daily_loss=Decimal('100000'), max_weekly_loss=Decimal('500000'),
        )

    def test_returns_none_when_no_active_hedge(self):
        self.assertIsNone(find_existing_active_hedge('breeze', 'RELIANCE', datetime.date(2026, 7, 30)))

    def test_finds_active_hedge_for_matching_key(self):
        hedge = HedgePosition.objects.create(
            account=self.account, broker='breeze', underlying_symbol='RELIANCE',
            futures_expiry_date=datetime.date(2026, 7, 30), status=HEDGE_STATUS_ACTIVE,
            futures_lots_covered=90, futures_lot_size=400, futures_avg_price=Decimal('482.54'),
        )
        found = find_existing_active_hedge('breeze', 'RELIANCE', datetime.date(2026, 7, 30))
        self.assertEqual(found.id, hedge.id)

    def test_does_not_match_different_broker(self):
        HedgePosition.objects.create(
            account=self.account, broker='breeze', underlying_symbol='RELIANCE',
            futures_expiry_date=datetime.date(2026, 7, 30), status=HEDGE_STATUS_ACTIVE,
            futures_lots_covered=90, futures_lot_size=400, futures_avg_price=Decimal('482.54'),
        )
        self.assertIsNone(find_existing_active_hedge('neo', 'RELIANCE', datetime.date(2026, 7, 30)))


class MarginValidationTests(TestCase):
    def test_passes_when_margin_sufficient(self):
        account = BrokerAccount.objects.create(
            broker='ICICI', account_number='TEST002', account_name='Test',
            allocated_capital=Decimal('10000000'), max_daily_loss=Decimal('100000'), max_weekly_loss=Decimal('500000'),
        )
        ok, _ = validate_margin(account, Decimal('100000'))
        self.assertTrue(ok)

    def test_fails_when_margin_insufficient(self):
        account = BrokerAccount.objects.create(
            broker='ICICI', account_number='TEST003', account_name='Test',
            allocated_capital=Decimal('1000'), max_daily_loss=Decimal('100000'), max_weekly_loss=Decimal('500000'),
        )
        ok, message = validate_margin(account, Decimal('100000'))
        self.assertFalse(ok)
        self.assertIn('Insufficient margin', message)


class LiquidityWarningTests(TestCase):
    def test_low_oi_produces_warning(self):
        warnings = assess_liquidity_warnings({'open_interest': 10, 'bid': 4.7, 'ask': 4.9})
        self.assertTrue(any('open interest' in w for w in warnings))

    def test_wide_spread_produces_warning(self):
        warnings = assess_liquidity_warnings({'open_interest': 5000, 'bid': 4.0, 'ask': 6.0})
        self.assertTrue(any('spread' in w for w in warnings))

    def test_missing_quotes_produces_warning(self):
        warnings = assess_liquidity_warnings({'open_interest': 5000, 'bid': 0, 'ask': 0})
        self.assertTrue(any('Missing bid/ask' in w for w in warnings))

    def test_healthy_strike_produces_no_warnings(self):
        warnings = assess_liquidity_warnings({'open_interest': 5000, 'bid': 4.75, 'ask': 4.85})
        self.assertEqual(warnings, [])
