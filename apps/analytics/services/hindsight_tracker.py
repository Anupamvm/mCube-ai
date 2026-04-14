"""
Hindsight Tracker Service — What-If Analysis

Tracks what would have happened if a position had been held longer
after exit. Creates checkpoints at EOD, +1d, +3d, +5d, +7d, +15d
and fills them with actual OHLC data as trading days pass.

Public API:
    - create_checkpoints_for_position(position)
    - seed_opening_prices(target_date)
    - update_pending_checkpoints(target_date)
    - generate_hindsight_digest()
    - get_hindsight_summary(filters)
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.db.models import Avg, Count, Q, Sum, F
from django.utils import timezone

from apps.analytics.models import HindsightCheckpoint
from apps.positions.models import Position

logger = logging.getLogger(__name__)


# =============================================================================
# TRADING CALENDAR HELPER
# =============================================================================

def get_trading_date_offset(from_date: date, offset_days: int) -> date:
    """
    Returns the calendar date that is `offset_days` trading days from `from_date`.

    Skips weekends (Sat/Sun). For offset_days=0, returns from_date itself
    (or next Monday if from_date is a weekend).

    Note: This does not account for market holidays. Checkpoints landing on
    holidays will remain PENDING until the next trading day's EOD task fills them.
    """
    if offset_days == 0:
        # For EOD checkpoint, use the exit date itself
        # If exit was on weekend (unlikely but defensive), push to Monday
        result = from_date
        while result.weekday() >= 5:  # Sat=5, Sun=6
            result += timedelta(days=1)
        return result

    current = from_date
    days_counted = 0
    while days_counted < offset_days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            days_counted += 1
    return current


# =============================================================================
# CHECKPOINT CREATION
# =============================================================================

def create_checkpoints_for_position(position: Position) -> List[HindsightCheckpoint]:
    """
    Create 6 hindsight checkpoints for a just-closed position.

    Called as a fire-and-forget task when a position is closed.
    Checkpoints at: Exit Day EOD, +1d, +3d, +5d, +7d, +15d.

    Args:
        position: A Position instance with status=CLOSED

    Returns:
        List of created HindsightCheckpoint instances
    """
    if position.status != 'CLOSED':
        logger.warning(
            f"Skipping hindsight for position #{position.id} — status={position.status}"
        )
        return []

    exit_date = (
        position.exit_time.date()
        if position.exit_time
        else timezone.localtime().date()
    )

    checkpoints = []
    for offset_days, label in HindsightCheckpoint.OFFSET_CHOICES:
        scheduled = get_trading_date_offset(exit_date, offset_days)

        # F&O: if instrument expires before this checkpoint, mark EXPIRED
        status = 'PENDING'
        if position.expiry_date and scheduled > position.expiry_date:
            status = 'EXPIRED'

        checkpoint = HindsightCheckpoint(
            position=position,
            offset_days=offset_days,
            offset_label=label,
            scheduled_date=scheduled,
            status=status,
            # Denormalized position context
            instrument=position.instrument,
            display_name=getattr(position, 'display_name', '') or '',
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=position.exit_price or position.current_price,
            exit_reason=position.exit_reason or '',
            quantity=position.quantity or 0,
            lot_size=getattr(position, 'lot_size', 1) or 1,
            actual_realized_pnl=position.realized_pnl,
        )
        checkpoints.append(checkpoint)

    created = HindsightCheckpoint.objects.bulk_create(
        checkpoints,
        ignore_conflicts=True,  # idempotent — won't duplicate on retry
    )

    logger.info(
        f"Created {len(created)} hindsight checkpoints for "
        f"{position.display_name or position.instrument} "
        f"(exit_reason={position.exit_reason})"
    )
    return created


# =============================================================================
# P&L CALCULATION
# =============================================================================

def _compute_pnl_fields(checkpoint: HindsightCheckpoint, price: Decimal) -> None:
    """
    Compute hypothetical P&L for a checkpoint given a reference price (close, high, or low).

    Mutates checkpoint fields in-place. Caller must save().
    """
    entry = checkpoint.entry_price
    qty = checkpoint.quantity or 1

    if checkpoint.direction == 'LONG':
        pnl = (price - entry) * qty
    elif checkpoint.direction == 'SHORT':
        pnl = (entry - price) * qty
    else:
        # NEUTRAL (e.g., options premium decay) — treat like LONG for simplicity
        pnl = (price - entry) * qty

    entry_value = entry * qty if entry and qty else Decimal('1')
    pnl_pct = (pnl / entry_value * 100) if entry_value else Decimal('0')

    checkpoint.hypothetical_pnl = pnl
    checkpoint.hypothetical_pnl_pct = pnl_pct

    if checkpoint.actual_realized_pnl is not None:
        checkpoint.opportunity_delta = pnl - checkpoint.actual_realized_pnl


def _compute_best_worst(checkpoint: HindsightCheckpoint) -> None:
    """Compute best/worst case P&L based on day high/low."""
    entry = checkpoint.entry_price
    qty = checkpoint.quantity or 1

    if checkpoint.high_price and checkpoint.low_price:
        if checkpoint.direction == 'SHORT':
            best_price, worst_price = checkpoint.low_price, checkpoint.high_price
        else:
            best_price, worst_price = checkpoint.high_price, checkpoint.low_price

        if checkpoint.direction == 'SHORT':
            checkpoint.best_case_pnl = (entry - best_price) * qty
            checkpoint.worst_case_pnl = (entry - worst_price) * qty
        else:
            checkpoint.best_case_pnl = (best_price - entry) * qty
            checkpoint.worst_case_pnl = (worst_price - entry) * qty


# =============================================================================
# PRICE FETCHING
# =============================================================================

def _fetch_ohlc_from_historical(instrument: str, target_date: date) -> Optional[Dict]:
    """
    Try to get OHLC from HistoricalPrice model (already synced by Breeze tasks).

    Returns dict with open/high/low/close or None.
    """
    from apps.brokers.models import HistoricalPrice

    # Match by stock code and date — HistoricalPrice uses datetime field
    from datetime import datetime as dt
    day_start = timezone.make_aware(
        dt.combine(target_date, dt.min.time()),
        timezone.get_current_timezone()
    )
    day_end = timezone.make_aware(
        dt.combine(target_date, dt.max.time()),
        timezone.get_current_timezone()
    )

    record = HistoricalPrice.objects.filter(
        stock_code__icontains=instrument.split('2')[0][:10],  # fuzzy match base symbol
        interval='1day',
        datetime__range=(day_start, day_end),
    ).first()

    if record:
        return {
            'open': record.open,
            'high': record.high,
            'low': record.low,
            'close': record.close,
        }
    return None


def _fetch_ohlc_from_breeze(instrument: str, target_date: date) -> Optional[Dict]:
    """
    Fetch OHLC from Breeze API for a specific instrument and date.
    Falls back to cash segment for the base symbol.
    """
    try:
        from apps.brokers.integrations.breeze import get_breeze_client

        breeze = get_breeze_client()
        # Extract base stock code from instrument name (e.g., HDFCBANK26MARFUT -> HDFCBANK)
        base_symbol = ''.join(c for c in instrument.split('2')[0] if c.isalpha())
        if not base_symbol:
            base_symbol = instrument[:10]

        from_date = target_date.strftime('%Y-%m-%dT09:15:00.000Z')
        to_date = target_date.strftime('%Y-%m-%dT15:30:00.000Z')

        resp = breeze.get_historical_data_v2(
            interval='1day',
            from_date=from_date,
            to_date=to_date,
            stock_code=base_symbol,
            exchange_code='NSE',
            product_type='cash',
        )
        candles = resp.get('Success', [])
        if candles:
            candle = candles[0]
            return {
                'open': Decimal(str(candle.get('open', 0))),
                'high': Decimal(str(candle.get('high', 0))),
                'low': Decimal(str(candle.get('low', 0))),
                'close': Decimal(str(candle.get('close', 0))),
            }
    except Exception as e:
        logger.warning(f"Breeze OHLC fetch failed for {instrument} on {target_date}: {e}")

    return None


def _fetch_live_price(instrument: str) -> Optional[Decimal]:
    """
    Fetch current live price via NeoAPI or Breeze.
    Used for seeding opening prices during market hours.
    """
    try:
        from apps.brokers.integrations.breeze import get_nifty_quote

        if 'NIFTY' in instrument.upper():
            quote = get_nifty_quote()
            if quote:
                return Decimal(str(quote.get('ltp', 0)))
    except Exception as e:
        logger.warning(f"Live price fetch failed for {instrument}: {e}")
    return None


def _get_ohlc_for_checkpoint(checkpoint: HindsightCheckpoint) -> Optional[Dict]:
    """
    Try all price sources in priority order for a checkpoint.
    """
    # 1. Try HistoricalPrice model (already synced)
    ohlc = _fetch_ohlc_from_historical(checkpoint.instrument, checkpoint.scheduled_date)
    if ohlc:
        return ohlc

    # 2. Try Breeze API directly
    ohlc = _fetch_ohlc_from_breeze(checkpoint.instrument, checkpoint.scheduled_date)
    if ohlc:
        return ohlc

    return None


# =============================================================================
# DAILY TASK: SEED OPENING PRICES (Morning)
# =============================================================================

def seed_opening_prices(target_date: date = None) -> Dict:
    """
    Morning task: fetch opening prices for today's pending checkpoints.
    Transitions PENDING → PARTIAL.

    Returns summary dict.
    """
    target_date = target_date or timezone.localtime().date()

    pending = HindsightCheckpoint.objects.filter(
        status='PENDING',
        scheduled_date=target_date,
    )

    updated = 0
    for checkpoint in pending:
        price = _fetch_live_price(checkpoint.instrument)
        if price and price > 0:
            checkpoint.open_price = price
            checkpoint.status = 'PARTIAL'
            checkpoint.save(update_fields=['open_price', 'status', 'updated_at'])
            updated += 1

    logger.info(f"Hindsight morning seed: {updated}/{pending.count()} checkpoints updated for {target_date}")
    return {'date': str(target_date), 'seeded': updated, 'total_pending': pending.count()}


# =============================================================================
# DAILY TASK: UPDATE PENDING CHECKPOINTS (EOD)
# =============================================================================

def update_pending_checkpoints(target_date: date = None) -> Dict:
    """
    EOD task: fill OHLC data for all checkpoints whose scheduled_date has arrived.
    Transitions PENDING/PARTIAL → COMPLETE.

    Groups by instrument to minimize API calls.

    Returns summary dict.
    """
    target_date = target_date or timezone.localtime().date()

    pending = HindsightCheckpoint.objects.filter(
        status__in=['PENDING', 'PARTIAL'],
        scheduled_date__lte=target_date,
    ).order_by('instrument', 'scheduled_date')

    completed = 0
    skipped = 0
    ohlc_cache = {}  # (instrument, date) -> ohlc dict

    for checkpoint in pending:
        cache_key = (checkpoint.instrument, checkpoint.scheduled_date)

        # Use cached OHLC if we already fetched for this instrument+date
        if cache_key not in ohlc_cache:
            ohlc_cache[cache_key] = _get_ohlc_for_checkpoint(checkpoint)

        ohlc = ohlc_cache[cache_key]

        if ohlc:
            checkpoint.open_price = checkpoint.open_price or ohlc['open']
            checkpoint.high_price = ohlc['high']
            checkpoint.low_price = ohlc['low']
            checkpoint.close_price = ohlc['close']
            checkpoint.status = 'COMPLETE'

            # Compute P&L based on close price
            _compute_pnl_fields(checkpoint, ohlc['close'])
            _compute_best_worst(checkpoint)

            checkpoint.save()
            completed += 1
        else:
            # No data found — check if we should skip
            days_overdue = (target_date - checkpoint.scheduled_date).days
            if days_overdue >= 5:  # 5 calendar days = ~3 trading days
                checkpoint.status = 'SKIPPED'
                checkpoint.save(update_fields=['status', 'updated_at'])
                skipped += 1

    logger.info(
        f"Hindsight EOD update: {completed} completed, {skipped} skipped "
        f"(target_date={target_date})"
    )
    return {
        'date': str(target_date),
        'completed': completed,
        'skipped': skipped,
        'total_processed': completed + skipped,
    }


# =============================================================================
# TELEGRAM DIGEST
# =============================================================================

def generate_hindsight_digest() -> Optional[Dict]:
    """
    Build notification kwargs for the daily Telegram hindsight digest.

    Queries checkpoints completed in the last 24 hours and summarizes:
    - Number of checkpoints updated
    - Top missed opportunities (largest positive opportunity_delta)
    - Best exit decisions (largest negative opportunity_delta)

    Returns kwargs dict for notify(), or None if nothing to report.
    """
    since = timezone.now() - timedelta(hours=24)

    recent = HindsightCheckpoint.objects.filter(
        status='COMPLETE',
        updated_at__gte=since,
    ).select_related('position')

    if not recent.exists():
        return None

    count = recent.count()
    positions_count = recent.values('position_id').distinct().count()

    # Aggregate stats
    avg_delta = recent.aggregate(
        avg=Avg('opportunity_delta')
    )['avg'] or Decimal('0')

    # Top missed opportunities (positive delta = left money on table)
    missed = recent.filter(
        opportunity_delta__gt=0
    ).order_by('-opportunity_delta')[:3]

    # Best exit decisions (negative delta = right to exit)
    best_exits = recent.filter(
        opportunity_delta__lt=0
    ).order_by('opportunity_delta')[:3]

    # Build context lines
    context_lines = []
    if missed:
        context_lines.append("📉 Missed Opportunities:")
        for cp in missed:
            name = cp.display_name or cp.instrument
            context_lines.append(
                f"  {name} {cp.offset_label}: "
                f"Would be ₹{cp.hypothetical_pnl:+,.0f} ({cp.hypothetical_pnl_pct:+.1f}%) "
                f"vs actual ₹{cp.actual_realized_pnl:+,.0f} "
                f"[Exit: {cp.exit_reason}]"
            )

    if best_exits:
        context_lines.append("✅ Right to Exit:")
        for cp in best_exits:
            name = cp.display_name or cp.instrument
            context_lines.append(
                f"  {name} {cp.offset_label}: "
                f"Would be ₹{cp.hypothetical_pnl:+,.0f} ({cp.hypothetical_pnl_pct:+.1f}%) "
                f"vs actual ₹{cp.actual_realized_pnl:+,.0f} "
                f"[Exit: {cp.exit_reason}]"
            )

    return {
        'title': 'Hindsight Tracker — Daily Digest',
        'metrics': {
            'Checkpoints Updated': str(count),
            'Positions Tracked': str(positions_count),
            'Avg Opportunity': f"₹{avg_delta:+,.0f}",
        },
        'context': context_lines or ['No significant updates today.'],
        'collapsible': True,
    }


# =============================================================================
# API HELPERS
# =============================================================================

def get_hindsight_summary(
    date_from: date = None,
    date_to: date = None,
    instrument: str = None,
    exit_reason: str = None,
    direction: str = None,
) -> Dict:
    """
    Aggregate stats for the hindsight tracker UI.

    Returns dict with executive metrics and breakdowns.
    """
    qs = HindsightCheckpoint.objects.all()

    # Apply filters
    if date_from:
        qs = qs.filter(scheduled_date__gte=date_from)
    if date_to:
        qs = qs.filter(scheduled_date__lte=date_to)
    if instrument:
        qs = qs.filter(
            Q(instrument__icontains=instrument) | Q(display_name__icontains=instrument)
        )
    if exit_reason:
        qs = qs.filter(exit_reason=exit_reason)
    if direction:
        qs = qs.filter(direction=direction)

    total = qs.count()
    complete = qs.filter(status='COMPLETE').count()
    pending = qs.filter(status__in=['PENDING', 'PARTIAL']).count()
    expired = qs.filter(status='EXPIRED').count()

    # Only analyze completed checkpoints for stats
    completed_qs = qs.filter(status='COMPLETE', opportunity_delta__isnull=False)

    left_money = completed_qs.filter(opportunity_delta__gt=0).count()
    right_to_exit = completed_qs.filter(opportunity_delta__lte=0).count()
    completed_total = left_money + right_to_exit

    left_money_pct = (left_money / completed_total * 100) if completed_total else 0
    right_to_exit_pct = (right_to_exit / completed_total * 100) if completed_total else 0

    # Average opportunity delta at +7d offset
    avg_7d = completed_qs.filter(offset_days=7).aggregate(
        avg=Avg('opportunity_delta')
    )['avg'] or Decimal('0')

    # Breakdown by exit reason
    reason_breakdown = list(
        completed_qs.values('exit_reason').annotate(
            avg_delta=Avg('opportunity_delta'),
            count=Count('id'),
        ).order_by('exit_reason')
    )

    # Breakdown by direction
    direction_breakdown = list(
        completed_qs.values('direction').annotate(
            avg_delta=Avg('opportunity_delta'),
            count=Count('id'),
        ).order_by('direction')
    )

    return {
        'total_checkpoints': total,
        'complete': complete,
        'pending': pending,
        'expired': expired,
        'left_money_pct': round(left_money_pct, 1),
        'right_to_exit_pct': round(right_to_exit_pct, 1),
        'avg_opportunity_7d': float(avg_7d),
        'reason_breakdown': reason_breakdown,
        'direction_breakdown': direction_breakdown,
    }


def get_hindsight_positions(
    date_from: date = None,
    date_to: date = None,
    instrument: str = None,
    exit_reason: str = None,
    direction: str = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict:
    """
    Paginated list of positions with their checkpoint statuses.

    Returns dict with positions list and pagination info.
    """
    # Get distinct positions that have checkpoints matching filters
    qs = HindsightCheckpoint.objects.all()

    if date_from:
        qs = qs.filter(position__exit_time__date__gte=date_from)
    if date_to:
        qs = qs.filter(position__exit_time__date__lte=date_to)
    if instrument:
        qs = qs.filter(
            Q(instrument__icontains=instrument) | Q(display_name__icontains=instrument)
        )
    if exit_reason:
        qs = qs.filter(exit_reason=exit_reason)
    if direction:
        qs = qs.filter(direction=direction)

    position_ids = (
        qs.values_list('position_id', flat=True)
        .distinct()
        .order_by('-position__exit_time')
    )

    # Paginate
    total = position_ids.count()
    start = (page - 1) * page_size
    page_ids = list(position_ids[start:start + page_size])

    # Fetch all checkpoints for these positions in one query
    checkpoints = HindsightCheckpoint.objects.filter(
        position_id__in=page_ids
    ).order_by('position_id', 'offset_days')

    # Group by position
    positions_data = {}
    for cp in checkpoints:
        pid = cp.position_id
        if pid not in positions_data:
            positions_data[pid] = {
                'position_id': pid,
                'instrument': cp.instrument,
                'display_name': cp.display_name,
                'direction': cp.direction,
                'entry_price': float(cp.entry_price),
                'exit_price': float(cp.exit_price),
                'exit_reason': cp.exit_reason,
                'actual_pnl': float(cp.actual_realized_pnl) if cp.actual_realized_pnl else 0,
                'checkpoints': {},
            }
        positions_data[pid]['checkpoints'][cp.offset_days] = {
            'status': cp.status,
            'close_price': float(cp.close_price) if cp.close_price else None,
            'high_price': float(cp.high_price) if cp.high_price else None,
            'low_price': float(cp.low_price) if cp.low_price else None,
            'hypothetical_pnl': float(cp.hypothetical_pnl) if cp.hypothetical_pnl else None,
            'hypothetical_pnl_pct': float(cp.hypothetical_pnl_pct) if cp.hypothetical_pnl_pct else None,
            'opportunity_delta': float(cp.opportunity_delta) if cp.opportunity_delta else None,
            'best_case_pnl': float(cp.best_case_pnl) if cp.best_case_pnl else None,
            'worst_case_pnl': float(cp.worst_case_pnl) if cp.worst_case_pnl else None,
            'offset_label': cp.offset_label,
        }

    # Maintain ordering from position_ids
    result = [positions_data[pid] for pid in page_ids if pid in positions_data]

    return {
        'positions': result,
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': (total + page_size - 1) // page_size,
        },
    }


def get_hindsight_detail(position_id: int) -> Optional[Dict]:
    """
    Full checkpoint detail for a single position.
    """
    checkpoints = HindsightCheckpoint.objects.filter(
        position_id=position_id
    ).order_by('offset_days')

    if not checkpoints.exists():
        return None

    first = checkpoints.first()
    result = {
        'position_id': position_id,
        'instrument': first.instrument,
        'display_name': first.display_name,
        'direction': first.direction,
        'entry_price': float(first.entry_price),
        'exit_price': float(first.exit_price),
        'exit_reason': first.exit_reason,
        'actual_pnl': float(first.actual_realized_pnl) if first.actual_realized_pnl else 0,
        'quantity': first.quantity,
        'lot_size': first.lot_size,
        'checkpoints': [],
    }

    for cp in checkpoints:
        result['checkpoints'].append({
            'offset_days': cp.offset_days,
            'offset_label': cp.offset_label,
            'scheduled_date': str(cp.scheduled_date),
            'status': cp.status,
            'open_price': float(cp.open_price) if cp.open_price else None,
            'high_price': float(cp.high_price) if cp.high_price else None,
            'low_price': float(cp.low_price) if cp.low_price else None,
            'close_price': float(cp.close_price) if cp.close_price else None,
            'hypothetical_pnl': float(cp.hypothetical_pnl) if cp.hypothetical_pnl else None,
            'hypothetical_pnl_pct': float(cp.hypothetical_pnl_pct) if cp.hypothetical_pnl_pct else None,
            'best_case_pnl': float(cp.best_case_pnl) if cp.best_case_pnl else None,
            'worst_case_pnl': float(cp.worst_case_pnl) if cp.worst_case_pnl else None,
            'opportunity_delta': float(cp.opportunity_delta) if cp.opportunity_delta else None,
        })

    return result
