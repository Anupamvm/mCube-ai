"""
Hindsight Tracker — Comprehensive Test Suite

Tests cover:
  1. Trading calendar helper (get_trading_date_offset)
  2. Checkpoint creation (create_checkpoints_for_position)
  3. P&L computation (_compute_pnl_fields, _compute_best_worst)
  4. EOD update logic (update_pending_checkpoints)
  5. Morning seed logic (seed_opening_prices)
  6. Telegram digest (generate_hindsight_digest)
  7. API helpers (get_hindsight_summary, get_hindsight_positions, get_hindsight_detail)
  8. Idempotency and edge cases
  9. Model integration (Position.close_position triggers checkpoints)
  10. View endpoints
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.utils import timezone

from apps.analytics.models import HindsightCheckpoint
from apps.positions.models import Position
from apps.analytics.services.hindsight_tracker import (
    get_trading_date_offset,
    create_checkpoints_for_position,
    _compute_pnl_fields,
    _compute_best_worst,
    update_pending_checkpoints,
    seed_opening_prices,
    generate_hindsight_digest,
    get_hindsight_summary,
    get_hindsight_positions,
    get_hindsight_detail,
)


class TradingCalendarTests(TestCase):
    """Test 1: get_trading_date_offset — trading day arithmetic."""

    def test_offset_zero_weekday(self):
        """offset=0 on a weekday returns the same date."""
        monday = date(2026, 4, 6)  # Monday
        self.assertEqual(get_trading_date_offset(monday, 0), monday)

    def test_offset_zero_saturday(self):
        """offset=0 on Saturday pushes to Monday."""
        saturday = date(2026, 4, 11)  # Saturday
        monday = date(2026, 4, 13)
        self.assertEqual(get_trading_date_offset(saturday, 0), monday)

    def test_offset_zero_sunday(self):
        """offset=0 on Sunday pushes to Monday."""
        sunday = date(2026, 4, 12)
        monday = date(2026, 4, 13)
        self.assertEqual(get_trading_date_offset(sunday, 0), monday)

    def test_offset_1_from_monday(self):
        """1 trading day from Monday = Tuesday."""
        monday = date(2026, 4, 6)
        self.assertEqual(get_trading_date_offset(monday, 1), date(2026, 4, 7))

    def test_offset_1_from_friday(self):
        """1 trading day from Friday = next Monday (skips weekend)."""
        friday = date(2026, 4, 10)
        self.assertEqual(get_trading_date_offset(friday, 1), date(2026, 4, 13))

    def test_offset_3_from_wednesday(self):
        """3 trading days from Wednesday = Monday (Wed→Thu→Fri→Mon)."""
        wednesday = date(2026, 4, 8)
        self.assertEqual(get_trading_date_offset(wednesday, 3), date(2026, 4, 13))

    def test_offset_5_from_monday(self):
        """5 trading days from Monday = next Monday."""
        monday = date(2026, 4, 6)
        self.assertEqual(get_trading_date_offset(monday, 5), date(2026, 4, 13))

    def test_offset_7_from_monday(self):
        """7 trading days from Monday = Wednesday of next-next week."""
        monday = date(2026, 4, 6)
        result = get_trading_date_offset(monday, 7)
        self.assertEqual(result, date(2026, 4, 15))  # Mon+7td = Wed (skips 2 weekends? no, 1)
        self.assertTrue(result.weekday() < 5)

    def test_offset_15_from_monday(self):
        """15 trading days = 3 full weeks of weekdays."""
        monday = date(2026, 4, 6)
        result = get_trading_date_offset(monday, 15)
        self.assertEqual(result, date(2026, 4, 27))  # 3 weeks = 15 trading days
        self.assertTrue(result.weekday() < 5)

    def test_all_results_are_weekdays(self):
        """Every offset result must be a weekday."""
        for start_day in range(7):
            base = date(2026, 4, 6) + timedelta(days=start_day)
            for offset in [0, 1, 3, 5, 7, 15]:
                result = get_trading_date_offset(base, offset)
                self.assertTrue(
                    result.weekday() < 5,
                    f"offset={offset} from {base} ({base.strftime('%A')}) "
                    f"gave {result} ({result.strftime('%A')})"
                )


def _make_position(**overrides):
    """Helper to create a test Position with sensible defaults."""
    defaults = {
        'instrument': 'HDFCBANK26APRFUT',
        'display_name': 'HDFCBANK APR FUT',
        'direction': 'LONG',
        'quantity': 550,
        'lot_size': 550,
        'entry_price': Decimal('1800.00'),
        'current_price': Decimal('1850.00'),
        'status': 'OPEN',
        'is_paper': False,
    }
    defaults.update(overrides)
    return Position.all_objects.create(**defaults)


class CheckpointCreationTests(TestCase):
    """Test 2: create_checkpoints_for_position."""

    def test_creates_6_checkpoints_for_closed_position(self):
        """A closed position should get exactly 6 checkpoints."""
        pos = _make_position()
        pos.close_position(Decimal('1850.00'), 'TARGET')

        # close_position fires the task, but in test the task runs synchronously?
        # We call it directly to avoid Celery dependency:
        HindsightCheckpoint.objects.filter(position=pos).delete()  # clear any from model hook
        created = create_checkpoints_for_position(pos)

        self.assertEqual(len(created), 6)
        offsets = set(c.offset_days for c in created)
        self.assertEqual(offsets, {0, 1, 3, 5, 7, 15})

    def test_skips_open_position(self):
        """Should not create checkpoints for a non-CLOSED position."""
        pos = _make_position(status='OPEN')
        created = create_checkpoints_for_position(pos)
        self.assertEqual(len(created), 0)

    def test_denormalized_fields(self):
        """Checkpoint should copy position context fields."""
        pos = _make_position()
        pos.close_position(Decimal('1900.00'), 'STOP_LOSS')
        HindsightCheckpoint.objects.filter(position=pos).delete()
        created = create_checkpoints_for_position(pos)

        cp = created[0]
        self.assertEqual(cp.instrument, 'HDFCBANK26APRFUT')
        self.assertEqual(cp.display_name, 'HDFCBANK APR FUT')
        self.assertEqual(cp.direction, 'LONG')
        self.assertEqual(cp.exit_reason, 'STOP_LOSS')
        self.assertEqual(cp.entry_price, Decimal('1800.00'))
        self.assertEqual(cp.exit_price, Decimal('1900.00'))
        self.assertEqual(cp.quantity, 550)
        self.assertIsNotNone(cp.actual_realized_pnl)

    def test_exit_reason_captured_for_all_types(self):
        """All exit reasons should be properly stored."""
        for reason in ['TARGET', 'STOP_LOSS', 'MANUAL', 'EOD_THURSDAY', 'EXPIRY_DAY']:
            pos = _make_position(instrument=f'TEST{reason}FUT')
            pos.close_position(Decimal('1850.00'), reason)
            HindsightCheckpoint.objects.filter(position=pos).delete()
            created = create_checkpoints_for_position(pos)
            for cp in created:
                self.assertEqual(
                    cp.exit_reason, reason,
                    f"Checkpoint exit_reason should be {reason}"
                )

    def test_fno_expiry_marks_late_checkpoints_expired(self):
        """Checkpoints past F&O expiry should be EXPIRED."""
        exit_date = date(2026, 4, 10)
        expiry = date(2026, 4, 16)  # Only 4 trading days after exit

        pos = _make_position(expiry_date=expiry)
        pos.exit_time = timezone.now()
        pos.exit_price = Decimal('1850.00')
        pos.exit_reason = 'TARGET'
        pos.status = 'CLOSED'
        pos.realized_pnl = Decimal('27500.00')
        pos.save()

        HindsightCheckpoint.objects.filter(position=pos).delete()
        created = create_checkpoints_for_position(pos)

        statuses = {c.offset_days: c.status for c in created}
        # +0d, +1d, +3d should be before expiry (PENDING)
        # +5d, +7d, +15d should be after expiry (EXPIRED)
        self.assertEqual(statuses[0], 'PENDING')
        self.assertEqual(statuses[1], 'PENDING')
        self.assertEqual(statuses[3], 'PENDING')
        # +5d from Apr 10 = Apr 17, which is > Apr 16 expiry
        self.assertEqual(statuses[5], 'EXPIRED')
        self.assertEqual(statuses[7], 'EXPIRED')
        self.assertEqual(statuses[15], 'EXPIRED')

    def test_idempotent_creation(self):
        """Calling create twice should not duplicate checkpoints."""
        pos = _make_position()
        pos.close_position(Decimal('1850.00'), 'TARGET')
        HindsightCheckpoint.objects.filter(position=pos).delete()

        create_checkpoints_for_position(pos)
        create_checkpoints_for_position(pos)  # second call

        count = HindsightCheckpoint.objects.filter(position=pos).count()
        self.assertEqual(count, 6)

    def test_scheduled_dates_are_weekdays(self):
        """All checkpoint dates should fall on weekdays."""
        pos = _make_position()
        pos.close_position(Decimal('1850.00'), 'TARGET')
        HindsightCheckpoint.objects.filter(position=pos).delete()
        created = create_checkpoints_for_position(pos)

        for cp in created:
            self.assertTrue(
                cp.scheduled_date.weekday() < 5,
                f"Checkpoint {cp.offset_label} scheduled on "
                f"{cp.scheduled_date} ({cp.scheduled_date.strftime('%A')})"
            )

    def test_winning_trade_checkpoints(self):
        """A winning trade (TARGET) should have positive realized_pnl on checkpoints."""
        pos = _make_position(direction='LONG', entry_price=Decimal('1800.00'))
        pos.close_position(Decimal('1900.00'), 'TARGET')
        HindsightCheckpoint.objects.filter(position=pos).delete()
        created = create_checkpoints_for_position(pos)

        for cp in created:
            self.assertGreater(cp.actual_realized_pnl, Decimal('0'))

    def test_losing_trade_checkpoints(self):
        """A losing trade (STOP_LOSS) should have negative realized_pnl on checkpoints."""
        pos = _make_position(direction='LONG', entry_price=Decimal('1800.00'))
        pos.close_position(Decimal('1750.00'), 'STOP_LOSS')
        HindsightCheckpoint.objects.filter(position=pos).delete()
        created = create_checkpoints_for_position(pos)

        for cp in created:
            self.assertLess(cp.actual_realized_pnl, Decimal('0'))


class PnLComputationTests(TestCase):
    """Test 3: _compute_pnl_fields and _compute_best_worst."""

    def _make_checkpoint(self, **kwargs):
        pos = _make_position()
        pos.close_position(Decimal('1850.00'), 'TARGET')
        HindsightCheckpoint.objects.filter(position=pos).delete()
        defaults = {
            'position': pos,
            'offset_days': 1,
            'offset_label': '+1 Day',
            'scheduled_date': date(2026, 4, 11),
            'status': 'PENDING',
            'instrument': 'HDFCBANK26APRFUT',
            'direction': 'LONG',
            'entry_price': Decimal('1800.00'),
            'exit_price': Decimal('1850.00'),
            'quantity': 550,
            'lot_size': 550,
            'actual_realized_pnl': Decimal('27500.00'),
        }
        defaults.update(kwargs)
        return HindsightCheckpoint.objects.create(**defaults)

    def test_long_profitable_pnl(self):
        """LONG: price above entry → positive P&L."""
        cp = self._make_checkpoint(direction='LONG', entry_price=Decimal('1800.00'))
        _compute_pnl_fields(cp, Decimal('1900.00'))

        # (1900 - 1800) * 550 = 55000
        self.assertEqual(cp.hypothetical_pnl, Decimal('55000.00'))
        self.assertGreater(cp.hypothetical_pnl_pct, Decimal('0'))

    def test_long_losing_pnl(self):
        """LONG: price below entry → negative P&L."""
        cp = self._make_checkpoint(direction='LONG', entry_price=Decimal('1800.00'))
        _compute_pnl_fields(cp, Decimal('1700.00'))

        # (1700 - 1800) * 550 = -55000
        self.assertEqual(cp.hypothetical_pnl, Decimal('-55000.00'))

    def test_short_profitable_pnl(self):
        """SHORT: price below entry → positive P&L."""
        cp = self._make_checkpoint(direction='SHORT', entry_price=Decimal('1800.00'))
        _compute_pnl_fields(cp, Decimal('1700.00'))

        # (1800 - 1700) * 550 = 55000
        self.assertEqual(cp.hypothetical_pnl, Decimal('55000.00'))

    def test_short_losing_pnl(self):
        """SHORT: price above entry → negative P&L."""
        cp = self._make_checkpoint(direction='SHORT', entry_price=Decimal('1800.00'))
        _compute_pnl_fields(cp, Decimal('1900.00'))

        # (1800 - 1900) * 550 = -55000
        self.assertEqual(cp.hypothetical_pnl, Decimal('-55000.00'))

    def test_opportunity_delta_positive(self):
        """Hypothetical > actual → positive delta (left money on table)."""
        cp = self._make_checkpoint(
            actual_realized_pnl=Decimal('27500.00'),  # actual
            entry_price=Decimal('1800.00'),
        )
        _compute_pnl_fields(cp, Decimal('1900.00'))  # hypothetical = 55000

        # 55000 - 27500 = 27500 (left money)
        self.assertEqual(cp.opportunity_delta, Decimal('27500.00'))

    def test_opportunity_delta_negative(self):
        """Hypothetical < actual → negative delta (right to exit)."""
        cp = self._make_checkpoint(
            actual_realized_pnl=Decimal('27500.00'),
            entry_price=Decimal('1800.00'),
        )
        _compute_pnl_fields(cp, Decimal('1750.00'))  # hypothetical = -27500

        # -27500 - 27500 = -55000 (right to exit)
        self.assertEqual(cp.opportunity_delta, Decimal('-55000.00'))

    def test_pnl_pct_calculation(self):
        """P&L % should be (pnl / entry_value) * 100."""
        cp = self._make_checkpoint(entry_price=Decimal('1000.00'), quantity=100)
        _compute_pnl_fields(cp, Decimal('1100.00'))

        # pnl = (1100-1000)*100 = 10000, entry_value = 1000*100 = 100000
        # pnl_pct = 10000/100000 * 100 = 10.0%
        self.assertEqual(cp.hypothetical_pnl, Decimal('10000.00'))
        self.assertAlmostEqual(float(cp.hypothetical_pnl_pct), 10.0, places=2)

    def test_best_worst_long(self):
        """LONG: best=high, worst=low."""
        cp = self._make_checkpoint(
            direction='LONG',
            entry_price=Decimal('1800.00'),
            quantity=550,
        )
        cp.high_price = Decimal('1950.00')
        cp.low_price = Decimal('1750.00')
        _compute_best_worst(cp)

        # best = (1950-1800)*550 = 82500, worst = (1750-1800)*550 = -27500
        self.assertEqual(cp.best_case_pnl, Decimal('82500.00'))
        self.assertEqual(cp.worst_case_pnl, Decimal('-27500.00'))

    def test_best_worst_short(self):
        """SHORT: best=low, worst=high."""
        cp = self._make_checkpoint(
            direction='SHORT',
            entry_price=Decimal('1800.00'),
            quantity=550,
        )
        cp.high_price = Decimal('1950.00')
        cp.low_price = Decimal('1750.00')
        _compute_best_worst(cp)

        # best = (1800-1750)*550 = 27500, worst = (1800-1950)*550 = -82500
        self.assertEqual(cp.best_case_pnl, Decimal('27500.00'))
        self.assertEqual(cp.worst_case_pnl, Decimal('-82500.00'))


class EODUpdateTests(TestCase):
    """Test 4: update_pending_checkpoints."""

    def setUp(self):
        self.pos = _make_position()
        self.pos.close_position(Decimal('1850.00'), 'TARGET')
        # Clear auto-created checkpoints and make our own
        HindsightCheckpoint.objects.filter(position=self.pos).delete()

    def _make_pending_checkpoint(self, scheduled_date, offset_days=1, status='PENDING'):
        return HindsightCheckpoint.objects.create(
            position=self.pos,
            offset_days=offset_days,
            offset_label=f'+{offset_days} Day',
            scheduled_date=scheduled_date,
            status=status,
            instrument='HDFCBANK26APRFUT',
            direction='LONG',
            entry_price=Decimal('1800.00'),
            exit_price=Decimal('1850.00'),
            quantity=550,
            lot_size=550,
            actual_realized_pnl=Decimal('27500.00'),
        )

    @patch('apps.analytics.services.hindsight_tracker._get_ohlc_for_checkpoint')
    def test_complete_with_ohlc(self, mock_ohlc):
        """Checkpoint should transition to COMPLETE when OHLC data is available."""
        mock_ohlc.return_value = {
            'open': Decimal('1860.00'),
            'high': Decimal('1920.00'),
            'low': Decimal('1830.00'),
            'close': Decimal('1900.00'),
        }

        today = date(2026, 4, 13)
        cp = self._make_pending_checkpoint(scheduled_date=today)

        result = update_pending_checkpoints(target_date=today)

        cp.refresh_from_db()
        self.assertEqual(cp.status, 'COMPLETE')
        self.assertEqual(cp.open_price, Decimal('1860.00'))
        self.assertEqual(cp.high_price, Decimal('1920.00'))
        self.assertEqual(cp.low_price, Decimal('1830.00'))
        self.assertEqual(cp.close_price, Decimal('1900.00'))
        self.assertIsNotNone(cp.hypothetical_pnl)
        self.assertIsNotNone(cp.best_case_pnl)
        self.assertIsNotNone(cp.worst_case_pnl)
        self.assertIsNotNone(cp.opportunity_delta)
        self.assertEqual(result['completed'], 1)

    @patch('apps.analytics.services.hindsight_tracker._get_ohlc_for_checkpoint')
    def test_stays_pending_when_no_data(self, mock_ohlc):
        """Checkpoint stays PENDING when no OHLC and not overdue."""
        mock_ohlc.return_value = None

        today = date(2026, 4, 13)
        cp = self._make_pending_checkpoint(scheduled_date=today)

        update_pending_checkpoints(target_date=today)

        cp.refresh_from_db()
        self.assertEqual(cp.status, 'PENDING')

    @patch('apps.analytics.services.hindsight_tracker._get_ohlc_for_checkpoint')
    def test_skipped_after_5_calendar_days(self, mock_ohlc):
        """Checkpoint is SKIPPED after 5 calendar days with no data."""
        mock_ohlc.return_value = None

        scheduled = date(2026, 4, 6)
        today = date(2026, 4, 12)  # 6 days later
        cp = self._make_pending_checkpoint(scheduled_date=scheduled)

        update_pending_checkpoints(target_date=today)

        cp.refresh_from_db()
        self.assertEqual(cp.status, 'SKIPPED')

    @patch('apps.analytics.services.hindsight_tracker._get_ohlc_for_checkpoint')
    def test_preserves_existing_open_price(self, mock_ohlc):
        """If open_price was already seeded, don't overwrite it."""
        mock_ohlc.return_value = {
            'open': Decimal('1870.00'),
            'high': Decimal('1920.00'),
            'low': Decimal('1830.00'),
            'close': Decimal('1900.00'),
        }

        today = date(2026, 4, 13)
        cp = self._make_pending_checkpoint(scheduled_date=today, status='PARTIAL')
        cp.open_price = Decimal('1855.00')  # Seeded in the morning
        cp.save()

        update_pending_checkpoints(target_date=today)

        cp.refresh_from_db()
        self.assertEqual(cp.open_price, Decimal('1855.00'))  # Preserved
        self.assertEqual(cp.close_price, Decimal('1900.00'))

    @patch('apps.analytics.services.hindsight_tracker._get_ohlc_for_checkpoint')
    def test_instrument_caching(self, mock_ohlc):
        """Same instrument+date should only fetch OHLC once."""
        mock_ohlc.return_value = {
            'open': Decimal('1860.00'),
            'high': Decimal('1920.00'),
            'low': Decimal('1830.00'),
            'close': Decimal('1900.00'),
        }

        today = date(2026, 4, 13)
        # Create two checkpoints with same instrument and date
        pos2 = _make_position(instrument='HDFCBANK26APRFUT')
        pos2.close_position(Decimal('1870.00'), 'MANUAL')
        HindsightCheckpoint.objects.filter(position=pos2).delete()

        self._make_pending_checkpoint(scheduled_date=today, offset_days=1)
        HindsightCheckpoint.objects.create(
            position=pos2, offset_days=3, offset_label='+3 Days',
            scheduled_date=today, status='PENDING',
            instrument='HDFCBANK26APRFUT', direction='LONG',
            entry_price=Decimal('1800.00'), exit_price=Decimal('1870.00'),
            quantity=550, lot_size=550, actual_realized_pnl=Decimal('38500.00'),
        )

        update_pending_checkpoints(target_date=today)

        # OHLC fetcher should be called only once (cached for same instrument+date)
        self.assertEqual(mock_ohlc.call_count, 1)


class MorningSeedTests(TestCase):
    """Test 5: seed_opening_prices."""

    def setUp(self):
        self.pos = _make_position()
        self.pos.close_position(Decimal('1850.00'), 'TARGET')
        HindsightCheckpoint.objects.filter(position=self.pos).delete()

    @patch('apps.analytics.services.hindsight_tracker._fetch_live_price')
    def test_seed_transitions_to_partial(self, mock_price):
        """Seeded checkpoint should move to PARTIAL."""
        mock_price.return_value = Decimal('1870.00')

        today = date(2026, 4, 13)
        cp = HindsightCheckpoint.objects.create(
            position=self.pos, offset_days=1, offset_label='+1 Day',
            scheduled_date=today, status='PENDING',
            instrument='NIFTY26APRFUT', direction='LONG',
            entry_price=Decimal('1800.00'), exit_price=Decimal('1850.00'),
            quantity=550, lot_size=550,
        )

        result = seed_opening_prices(target_date=today)

        cp.refresh_from_db()
        self.assertEqual(cp.status, 'PARTIAL')
        self.assertEqual(cp.open_price, Decimal('1870.00'))
        self.assertEqual(result['seeded'], 1)

    @patch('apps.analytics.services.hindsight_tracker._fetch_live_price')
    def test_ignores_non_today_checkpoints(self, mock_price):
        """Should not seed checkpoints for future dates."""
        mock_price.return_value = Decimal('1870.00')

        today = date(2026, 4, 13)
        tomorrow = date(2026, 4, 14)
        HindsightCheckpoint.objects.create(
            position=self.pos, offset_days=1, offset_label='+1 Day',
            scheduled_date=tomorrow, status='PENDING',
            instrument='NIFTY26APRFUT', direction='LONG',
            entry_price=Decimal('1800.00'), exit_price=Decimal('1850.00'),
            quantity=550, lot_size=550,
        )

        result = seed_opening_prices(target_date=today)
        self.assertEqual(result['seeded'], 0)

    @patch('apps.analytics.services.hindsight_tracker._fetch_live_price')
    def test_skips_zero_price(self, mock_price):
        """Should not seed if live price is 0."""
        mock_price.return_value = Decimal('0')

        today = date(2026, 4, 13)
        HindsightCheckpoint.objects.create(
            position=self.pos, offset_days=1, offset_label='+1 Day',
            scheduled_date=today, status='PENDING',
            instrument='NIFTY26APRFUT', direction='LONG',
            entry_price=Decimal('1800.00'), exit_price=Decimal('1850.00'),
            quantity=550, lot_size=550,
        )

        result = seed_opening_prices(target_date=today)
        self.assertEqual(result['seeded'], 0)


class DigestTests(TestCase):
    """Test 6: generate_hindsight_digest."""

    def setUp(self):
        self.pos = _make_position()
        self.pos.close_position(Decimal('1850.00'), 'TARGET')
        HindsightCheckpoint.objects.filter(position=self.pos).delete()

    def test_no_digest_when_empty(self):
        """Should return None when no recent completions."""
        result = generate_hindsight_digest()
        self.assertIsNone(result)

    def test_digest_with_completed_checkpoints(self):
        """Should return digest dict with metrics and context."""
        cp = HindsightCheckpoint.objects.create(
            position=self.pos, offset_days=1, offset_label='+1 Day',
            scheduled_date=date(2026, 4, 13), status='COMPLETE',
            instrument='HDFCBANK26APRFUT', display_name='HDFCBANK APR FUT',
            direction='LONG', entry_price=Decimal('1800.00'),
            exit_price=Decimal('1850.00'), quantity=550, lot_size=550,
            actual_realized_pnl=Decimal('27500.00'),
            hypothetical_pnl=Decimal('55000.00'),
            hypothetical_pnl_pct=Decimal('5.5556'),
            opportunity_delta=Decimal('27500.00'),
            close_price=Decimal('1900.00'),
        )

        result = generate_hindsight_digest()

        self.assertIsNotNone(result)
        self.assertIn('title', result)
        self.assertIn('metrics', result)
        self.assertIn('Checkpoints Updated', result['metrics'])
        self.assertIn('context', result)
        self.assertTrue(len(result['context']) > 0)

    def test_digest_includes_exit_reason(self):
        """Digest context lines should mention exit reason."""
        HindsightCheckpoint.objects.create(
            position=self.pos, offset_days=1, offset_label='+1 Day',
            scheduled_date=date(2026, 4, 13), status='COMPLETE',
            instrument='HDFCBANK26APRFUT', display_name='HDFCBANK',
            direction='LONG', entry_price=Decimal('1800.00'),
            exit_price=Decimal('1850.00'), exit_reason='STOP_LOSS',
            quantity=550, lot_size=550,
            actual_realized_pnl=Decimal('-27500.00'),
            hypothetical_pnl=Decimal('55000.00'),
            hypothetical_pnl_pct=Decimal('5.56'),
            opportunity_delta=Decimal('82500.00'),
            close_price=Decimal('1900.00'),
        )

        result = generate_hindsight_digest()
        context_text = ' '.join(result['context'])
        self.assertIn('STOP_LOSS', context_text)


class APISummaryTests(TestCase):
    """Test 7: API helper functions."""

    def setUp(self):
        # Create a winning LONG position (TARGET)
        self.pos1 = _make_position(
            instrument='WINNER26APRFUT', display_name='WINNER',
            direction='LONG', entry_price=Decimal('1000.00'),
        )
        self.pos1.close_position(Decimal('1100.00'), 'TARGET')
        HindsightCheckpoint.objects.filter(position=self.pos1).delete()

        # Create a losing SHORT position (STOP_LOSS)
        self.pos2 = _make_position(
            instrument='LOSER26APRFUT', display_name='LOSER',
            direction='SHORT', entry_price=Decimal('2000.00'),
        )
        self.pos2.close_position(Decimal('2100.00'), 'STOP_LOSS')
        HindsightCheckpoint.objects.filter(position=self.pos2).delete()

        # Create completed checkpoints
        for pos, delta in [(self.pos1, Decimal('5000.00')), (self.pos2, Decimal('-10000.00'))]:
            for offset, label in HindsightCheckpoint.OFFSET_CHOICES:
                HindsightCheckpoint.objects.create(
                    position=pos, offset_days=offset, offset_label=label,
                    scheduled_date=date(2026, 4, 13) + timedelta(days=offset),
                    status='COMPLETE',
                    instrument=pos.instrument, display_name=pos.display_name,
                    direction=pos.direction,
                    entry_price=pos.entry_price, exit_price=pos.exit_price,
                    exit_reason=pos.exit_reason or '',
                    quantity=pos.quantity, lot_size=pos.lot_size,
                    actual_realized_pnl=pos.realized_pnl,
                    hypothetical_pnl=delta, hypothetical_pnl_pct=Decimal('5.0'),
                    opportunity_delta=delta,
                    close_price=Decimal('1200.00'),
                )

    def test_summary_counts(self):
        """Summary should have correct total and status counts."""
        summary = get_hindsight_summary()
        self.assertEqual(summary['total_checkpoints'], 12)  # 2 positions × 6 offsets
        self.assertEqual(summary['complete'], 12)
        self.assertEqual(summary['pending'], 0)

    def test_summary_left_money_pct(self):
        """left_money_pct should reflect positive deltas."""
        summary = get_hindsight_summary()
        # pos1 has positive delta (left money), pos2 has negative (right to exit)
        self.assertEqual(summary['left_money_pct'], 50.0)
        self.assertEqual(summary['right_to_exit_pct'], 50.0)

    def test_summary_filter_by_exit_reason(self):
        """Filtering by exit_reason should only show matching checkpoints."""
        summary = get_hindsight_summary(exit_reason='TARGET')
        self.assertEqual(summary['total_checkpoints'], 6)

    def test_summary_filter_by_direction(self):
        """Filtering by direction should only show matching."""
        summary = get_hindsight_summary(direction='LONG')
        self.assertEqual(summary['total_checkpoints'], 6)

    def test_summary_filter_by_instrument(self):
        """Filtering by instrument name should work (case-insensitive)."""
        summary = get_hindsight_summary(instrument='winner')
        self.assertEqual(summary['total_checkpoints'], 6)

    def test_summary_reason_breakdown(self):
        """Breakdown by exit_reason should have entries for TARGET and STOP_LOSS."""
        summary = get_hindsight_summary()
        reasons = {r['exit_reason'] for r in summary['reason_breakdown']}
        self.assertIn('TARGET', reasons)
        self.assertIn('STOP_LOSS', reasons)

    def test_positions_list_pagination(self):
        """get_hindsight_positions should return paginated results."""
        result = get_hindsight_positions(page=1, page_size=1)
        self.assertEqual(len(result['positions']), 1)
        self.assertEqual(result['pagination']['total'], 2)
        self.assertEqual(result['pagination']['total_pages'], 2)

    def test_positions_list_has_checkpoints(self):
        """Each position in the list should have checkpoint data."""
        result = get_hindsight_positions()
        for pos in result['positions']:
            self.assertIn('checkpoints', pos)
            self.assertIn('exit_reason', pos)
            self.assertEqual(len(pos['checkpoints']), 6)

    def test_detail_returns_all_checkpoints(self):
        """get_hindsight_detail should return all 6 checkpoints."""
        detail = get_hindsight_detail(self.pos1.id)
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail['checkpoints']), 6)
        self.assertEqual(detail['exit_reason'], 'TARGET')
        self.assertEqual(detail['instrument'], 'WINNER26APRFUT')

    def test_detail_nonexistent_position(self):
        """get_hindsight_detail should return None for unknown position."""
        detail = get_hindsight_detail(99999)
        self.assertIsNone(detail)

    def test_empty_summary(self):
        """Summary with no data should not crash."""
        HindsightCheckpoint.objects.all().delete()
        summary = get_hindsight_summary()
        self.assertEqual(summary['total_checkpoints'], 0)
        self.assertEqual(summary['left_money_pct'], 0)
        self.assertEqual(summary['right_to_exit_pct'], 0)


class ModelIntegrationTests(TestCase):
    """Test 9: Position.close_position() triggers hindsight checkpoint creation."""

    @patch('apps.analytics.tasks.create_hindsight_checkpoints_task')
    def test_close_position_fires_task(self, mock_task):
        """Position.close_position() should call the hindsight task."""
        pos = _make_position()
        pos.close_position(Decimal('1850.00'), 'TARGET')

        mock_task.delay.assert_called_once_with(pos.id)

    @patch('apps.analytics.tasks.create_hindsight_checkpoints_task')
    def test_close_position_still_works_if_task_fails(self, mock_task):
        """Close should succeed even if hindsight task fails."""
        mock_task.delay.side_effect = Exception("Celery down")

        pos = _make_position()
        pos.close_position(Decimal('1850.00'), 'TARGET')

        pos.refresh_from_db()
        self.assertEqual(pos.status, 'CLOSED')
        self.assertEqual(pos.exit_price, Decimal('1850.00'))
        self.assertEqual(pos.exit_reason, 'TARGET')


class ViewEndpointTests(TestCase):
    """Test 10: View endpoints return correct responses.

    Uses SERVER_NAME=localhost to satisfy ALLOWED_HOSTS.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')

    def test_hindsight_page_loads(self):
        """The hindsight tracker page should return 200."""
        response = self.client.get('/analytics/hindsight/', SERVER_NAME='localhost')
        self.assertEqual(response.status_code, 200)

    def test_api_summary_returns_json(self):
        """Summary API should return valid JSON."""
        response = self.client.get('/analytics/api/hindsight/summary/', SERVER_NAME='localhost')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('total_checkpoints', data)

    def test_api_positions_returns_json(self):
        """Positions API should return paginated JSON."""
        response = self.client.get('/analytics/api/hindsight/positions/', SERVER_NAME='localhost')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('positions', data)
        self.assertIn('pagination', data)

    def test_api_detail_404_for_unknown(self):
        """Detail API should return 404 for nonexistent position."""
        response = self.client.get('/analytics/api/hindsight/detail/99999/', SERVER_NAME='localhost')
        self.assertEqual(response.status_code, 404)

    def test_api_summary_with_filters(self):
        """Summary API should accept filter query params."""
        response = self.client.get(
            '/analytics/api/hindsight/summary/?exit_reason=TARGET&direction=LONG',
            SERVER_NAME='localhost',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    def test_unauthenticated_redirects(self):
        """Unauthenticated requests should redirect to login."""
        self.client.logout()
        response = self.client.get('/analytics/hindsight/', SERVER_NAME='localhost')
        self.assertEqual(response.status_code, 302)
