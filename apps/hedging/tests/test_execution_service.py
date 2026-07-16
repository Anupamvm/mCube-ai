"""
Orchestration tests for execution_service.py, with all broker integration
calls mocked — never hits a real broker API. Verifies: lock acquisition
prevents duplicate placement, the quantity cap is a hard block (and blocks
BEFORE any DB row is written), lots are correctly split into batches, and
every placed leg produces an auditable HedgeAuditLog row carrying the
acting user.
"""
import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase

from apps.accounts.models import BrokerAccount
from apps.hedging.models import HedgeAuditLog, HedgeLeg, HedgePosition
from apps.hedging.services import execution_service
from apps.hedging.services.validators import HedgeValidationError

FUTURES_EXPIRY = datetime.date(2026, 7, 30)
OPTION_EXPIRY = datetime.date(2026, 7, 30)

LIVE_FUTURES_POSITION = {
    'direction': 'LONG', 'lots': 90, 'lot_size': 400,
    'average_price': 482.54, 'ltp': 467.30,
}

RESOLVED_SYMBOL = {'trading_symbol': 'RELIANCE26JUL490CE', 'lot_size': 400, 'source': 'test'}


def _patches():
    return (
        patch('apps.hedging.services.execution_service._fetch_live_futures_position', return_value=dict(LIVE_FUTURES_POSITION)),
        patch('apps.hedging.services.chain_service.resolve_execution_symbol', return_value=dict(RESOLVED_SYMBOL)),
        patch('apps.hedging.services.execution_service._dispatch_sell_order', return_value={'success': True, 'order_id': 'TEST123'}),
    )


class LotSizeUnconfirmedWarningTests(TestCase):
    """
    A symbol with no resolvable lot size (falls back to 1) must surface a
    non-blocking warning everywhere futures context is read — NOT a hard
    block (rolled back per explicit product decision: block-on-load made
    legitimate symbols like VARBEV untestable). The user decides whether
    to proceed after seeing the warning.
    """

    def test_is_lot_size_unconfirmed(self):
        self.assertTrue(execution_service.is_lot_size_unconfirmed(1))
        self.assertTrue(execution_service.is_lot_size_unconfirmed(0))
        self.assertFalse(execution_service.is_lot_size_unconfirmed(400))

    def test_get_futures_context_flags_unconfirmed_lot_size(self):
        with patch(
            'apps.hedging.services.execution_service._fetch_live_futures_position',
            return_value={'direction': 'LONG', 'lots': 70125, 'lot_size': 1, 'average_price': 1400.0, 'ltp': 1420.0},
        ):
            ctx = execution_service.get_futures_context('breeze', 'VARBEV', FUTURES_EXPIRY)
        self.assertTrue(ctx['lot_size_unconfirmed'])

    def test_get_futures_context_does_not_flag_confirmed_lot_size(self):
        with patch(
            'apps.hedging.services.execution_service._fetch_live_futures_position',
            return_value=dict(LIVE_FUTURES_POSITION),
        ):
            ctx = execution_service.get_futures_context('breeze', 'RELIANCE', FUTURES_EXPIRY)
        self.assertFalse(ctx['lot_size_unconfirmed'])

    def test_preview_warns_but_does_not_block_on_unconfirmed_lot_size(self):
        with patch(
            'apps.hedging.services.execution_service._fetch_live_futures_position',
            return_value={'direction': 'LONG', 'lots': 70125, 'lot_size': 1, 'average_price': 1400.0, 'ltp': 1420.0},
        ), patch(
            'apps.hedging.services.chain_service.fetch_covered_call_chain',
            return_value=[{'strike': 1450, 'ltp': 20.0, 'bid': 19.5, 'ask': 20.5, 'open_interest': 5000, 'delta': 0.3, 'theta': -1.0}],
        ), patch(
            'apps.hedging.services.chain_service.resolve_execution_symbol',
            return_value={'trading_symbol': 'VARBEV26JUL1450CE', 'lot_size': 1, 'source': 'test'},
        ):
            account = BrokerAccount.objects.create(
                broker='ICICI', account_number='VARBEV001', account_name='Test',
                allocated_capital=Decimal('50000000'), max_daily_loss=Decimal('200000'), max_weekly_loss=Decimal('1000000'),
            )
            result = execution_service.preview_cover_order(
                broker='breeze', underlying_symbol='VARBEV',
                futures_expiry_date=FUTURES_EXPIRY, option_expiry_date=OPTION_EXPIRY,
                strike=1450, lots=1, order_type='MARKET',
            )
        warning_codes = [w['code'] for w in result['warnings']]
        self.assertIn('LOT_SIZE_UNCONFIRMED', warning_codes)
        # Non-blocking: no blocking_issue for this reason, so can_place_order isn't
        # forced False purely because of the unconfirmed lot size.
        blocking_codes = [b['code'] for b in result['blocking_issues']]
        self.assertNotIn('LOT_SIZE_UNCONFIRMED', blocking_codes)


class PlaceCoverOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='trader', password='testpass123')
        self.account = BrokerAccount.objects.create(
            broker='KOTAK', account_number='NEO001', account_name='Test Neo',
            allocated_capital=Decimal('50000000'), max_daily_loss=Decimal('200000'), max_weekly_loss=Decimal('1000000'),
        )

    def test_places_order_and_creates_hedge_position_and_leg(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            result = execution_service.place_cover_order(
                user=self.user, broker='neo', underlying_symbol='RELIANCE',
                futures_expiry_date=FUTURES_EXPIRY, option_expiry_date=OPTION_EXPIRY,
                strike=490, lots=5, order_type='MARKET',
            )

        self.assertTrue(result['success'])
        hedge = HedgePosition.objects.get(id=result['hedge_position_id'])
        self.assertEqual(hedge.status, 'ACTIVE')
        self.assertEqual(hedge.broker, 'neo')
        self.assertEqual(hedge.created_by, self.user)

        legs = list(hedge.legs.all())
        self.assertEqual(len(legs), 1)
        self.assertEqual(legs[0].lots, 5)
        self.assertEqual(legs[0].status, HedgeLeg.STATUS_PLACED)
        self.assertEqual(legs[0].direction, HedgeLeg.DIRECTION_SELL)

    def test_audit_log_carries_the_acting_user(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            result = execution_service.place_cover_order(
                user=self.user, broker='neo', underlying_symbol='RELIANCE',
                futures_expiry_date=FUTURES_EXPIRY, option_expiry_date=OPTION_EXPIRY,
                strike=490, lots=5, order_type='MARKET',
            )
        hedge = HedgePosition.objects.get(id=result['hedge_position_id'])
        placed_logs = hedge.audit_logs.filter(action=HedgeAuditLog.ACTION_PLACED)
        self.assertTrue(placed_logs.exists())
        for log in placed_logs:
            self.assertEqual(log.user, self.user)

    def test_rejects_unauthenticated_user_before_touching_the_db(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            with self.assertRaises(HedgeValidationError) as ctx:
                execution_service.place_cover_order(
                    user=AnonymousUser(), broker='neo', underlying_symbol='RELIANCE',
                    futures_expiry_date=FUTURES_EXPIRY, option_expiry_date=OPTION_EXPIRY,
                    strike=490, lots=5, order_type='MARKET',
                )
        self.assertEqual(ctx.exception.code, 'AUTH_REQUIRED')
        self.assertEqual(HedgePosition.objects.count(), 0)

    def test_quantity_cap_blocks_before_any_order_is_placed(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            with self.assertRaises(HedgeValidationError) as ctx:
                execution_service.place_cover_order(
                    user=self.user, broker='neo', underlying_symbol='RELIANCE',
                    futures_expiry_date=FUTURES_EXPIRY, option_expiry_date=OPTION_EXPIRY,
                    strike=490, lots=200, order_type='MARKET',  # more than the 90 lots held
                )
        self.assertEqual(ctx.exception.code, 'QTY_EXCEEDS_UNCOVERED')
        self.assertEqual(HedgePosition.objects.count(), 0)
        self.assertEqual(HedgeLeg.objects.count(), 0)

    def test_large_order_splits_into_batches(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            result = execution_service.place_cover_order(
                user=self.user, broker='neo', underlying_symbol='RELIANCE',
                futures_expiry_date=FUTURES_EXPIRY, option_expiry_date=OPTION_EXPIRY,
                strike=490, lots=25, order_type='MARKET',  # > BATCH_THRESHOLD_LOTS (10)
            )
        self.assertTrue(result['is_batched'])
        self.assertEqual(result['total_batches'], 3)  # 10 + 10 + 5

        hedge = HedgePosition.objects.get(id=result['hedge_position_id'])
        legs = list(hedge.legs.order_by('id'))
        self.assertEqual([leg.lots for leg in legs], [10, 10, 5])
        self.assertTrue(all(leg.status == HedgeLeg.STATUS_PLACED for leg in legs))

    def test_second_hedge_attaches_to_existing_active_hedge_not_a_new_one(self):
        p1, p2, p3 = _patches()
        with p1, p2, p3:
            first = execution_service.place_cover_order(
                user=self.user, broker='neo', underlying_symbol='RELIANCE',
                futures_expiry_date=FUTURES_EXPIRY, option_expiry_date=OPTION_EXPIRY,
                strike=490, lots=5, order_type='MARKET',
            )
            second = execution_service.place_cover_order(
                user=self.user, broker='neo', underlying_symbol='RELIANCE',
                futures_expiry_date=FUTURES_EXPIRY, option_expiry_date=OPTION_EXPIRY,
                strike=500, lots=5, order_type='MARKET',
            )
        self.assertEqual(first['hedge_position_id'], second['hedge_position_id'])
        self.assertEqual(HedgePosition.objects.count(), 1)
        self.assertEqual(HedgeLeg.objects.filter(hedge_position_id=first['hedge_position_id']).count(), 2)

    def test_broker_failure_marks_leg_failed_and_logs_validation_blocked(self):
        p1, p2, _ = _patches()
        with p1, p2, patch(
            'apps.hedging.services.execution_service._dispatch_sell_order',
            return_value={'success': False, 'error': 'Exchange rejected order'},
        ):
            with self.assertRaises(HedgeValidationError) as ctx:
                execution_service.place_cover_order(
                    user=self.user, broker='neo', underlying_symbol='RELIANCE',
                    futures_expiry_date=FUTURES_EXPIRY, option_expiry_date=OPTION_EXPIRY,
                    strike=490, lots=5, order_type='MARKET',
                )
        self.assertEqual(ctx.exception.code, 'ORDER_FAILED')
        leg = HedgeLeg.objects.get()
        self.assertEqual(leg.status, HedgeLeg.STATUS_FAILED)
        self.assertTrue(
            HedgeAuditLog.objects.filter(action=HedgeAuditLog.ACTION_VALIDATION_BLOCKED).exists()
        )
