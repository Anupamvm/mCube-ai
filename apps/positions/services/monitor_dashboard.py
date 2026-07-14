"""
Monitor Dashboard Service

One consolidated Telegram message for ALL open positions — edited every
minute instead of spamming.  Exit suggestions remain separate per-position
actionable messages with [Close Now] / [Hold] buttons.

Anti-spam strategy:
- ONE master dashboard message per day (all positions, all brokers).
- Edited in-place each run — never re-sent unless the message was deleted.
- Per-position data (snapshots, exit suggestion state) still tracked in DB
  but NOT sent as individual Telegram messages.
- Exit suggestions: same reason within cooldown window is skipped.
"""

import logging
from decimal import Decimal
from typing import Optional, List, Dict

from django.utils import timezone

logger = logging.getLogger(__name__)

# Rolling window: keep last N snapshots per position (for DB history)
MAX_SNAPSHOTS = 3

# Re-send exit suggestion only after this many minutes if same reason
EXIT_SUGGESTION_COOLDOWN_MINUTES = 5

# Minimum further adverse price move (%) to re-alert after initial suggestion
# Without this, the same SL hit re-fires every 5 min with near-identical P&L
EXIT_RE_ALERT_PRICE_MOVE_PCT = 0.5

# Minimum further adverse price move (%) to clear a user hold and re-alert
HOLD_CLEAR_PRICE_MOVE_PCT = 0.5

# Broker display names
BROKER_DISPLAY = {'KOTAK': 'Kotak Neo', 'ICICI': 'ICICI Breeze'}


# ─────────────────────────────────────────────────────────────────────────────
# Time helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_ist(dt):
    """Convert UTC datetime to IST-aware datetime."""
    import pytz
    ist = pytz.timezone('Asia/Kolkata')
    if timezone.is_aware(dt):
        return dt.astimezone(ist)
    return ist.localize(dt)


def ist_time_str(dt=None) -> str:
    """Return HH:MM in IST."""
    if dt is None:
        dt = timezone.now()
    return _to_ist(dt).strftime('%H:%M')


def ist_datetime_str(dt=None) -> str:
    """Return DD-Mon HH:MM:SS in IST."""
    if dt is None:
        dt = timezone.now()
    return _to_ist(dt).strftime('%d-%b %H:%M:%S')


# ─────────────────────────────────────────────────────────────────────────────
# P&L formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pnl_sign(pnl: Decimal) -> str:
    return "+" if pnl >= 0 else ""


def fmt_pnl(pnl: Decimal, pnl_pct: Decimal) -> str:
    """Verbose: +₹5,250 (+2.3%) or -₹1,500 (-0.7%)"""
    if pnl >= 0:
        return f"+₹{pnl:,.0f} (+{pnl_pct:.1f}%)"
    return f"-₹{abs(pnl):,.0f} (-{abs(pnl_pct):.1f}%)"


def _fmt_compact(pnl: Decimal, pnl_pct: Decimal) -> str:
    """
    Phone-friendly compact P&L: -₹35.3L (-2.3%) or +₹1.5L (+0.3%)
    Thresholds: ≥1Cr → Cr, ≥1L → L, else raw ₹
    """
    sign = "+" if pnl >= 0 else "-"
    abs_pnl = abs(float(pnl))
    abs_pct = abs(float(pnl_pct))
    pct_sign = "+" if pnl >= 0 else "-"

    if abs_pnl >= 1_00_00_000:  # ≥1 Crore
        val = f"₹{abs_pnl / 1_00_00_000:.2f}Cr"
    elif abs_pnl >= 1_00_000:   # ≥1 Lakh
        val = f"₹{abs_pnl / 1_00_000:.1f}L"
    else:
        val = f"₹{abs_pnl:,.0f}"

    return f"{sign}{val} ({pct_sign}{abs_pct:.1f}%)"


def _sl_status(position) -> str:
    """Return a status badge for SL/Target proximity."""
    if not position.stop_loss and not position.target:
        return ""

    if position.is_stop_loss_hit():
        return " 🔴"
    if position.is_target_hit():
        return " 🎯"

    # Approaching SL (within 10% of SL distance from entry)?
    if position.stop_loss and position.current_price and position.entry_price:
        total_range = abs(float(position.entry_price) - float(position.stop_loss))
        current_dist = abs(float(position.current_price) - float(position.stop_loss))
        if total_range > 0 and (current_dist / total_range) < 0.10:
            return " 🟡"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Per-position dashboard CRUD (data tracking only, not for Telegram display)
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_dashboard(position, date=None):
    """
    Get (or create) today's per-position PositionMonitorDashboard.
    Used for: snapshot history, exit suggestion deduplication state.
    NOT used for the Telegram message (that's the master dashboard).

    Returns:
        Tuple[PositionMonitorDashboard, bool]: (dashboard, created)
    """
    from apps.positions.models import PositionMonitorDashboard

    if date is None:
        date = timezone.localdate()

    dashboard, created = PositionMonitorDashboard.objects.get_or_create(
        position=position,
        date=date,
    )
    return dashboard, created


def get_or_create_master_dashboard(date=None):
    """
    Get (or create) today's MASTER dashboard (position=None).
    Holds the single consolidated Telegram message_id for all positions.

    Returns:
        PositionMonitorDashboard (position=None)
    """
    from apps.positions.models import PositionMonitorDashboard

    if date is None:
        date = timezone.localdate()

    # Can't use get_or_create because NULL != NULL in SQLite unique constraints
    dashboard = PositionMonitorDashboard.objects.filter(
        position=None, date=date
    ).first()
    if not dashboard:
        dashboard = PositionMonitorDashboard.objects.create(
            position=None, date=date
        )
    return dashboard


def add_snapshot(dashboard, price: Decimal, pnl: Decimal, pnl_pct: Decimal, now=None):
    """
    Record a monitoring snapshot to a per-position dashboard.
    Maintains rolling window of MAX_SNAPSHOTS entries.
    Sets day_start on first call of the day.
    """
    if now is None:
        now = timezone.now()

    snapshot = {
        'time': ist_time_str(now),
        'price': float(price),
        'pnl': float(pnl),
        'pnl_pct': float(pnl_pct),
    }

    if not dashboard.day_start:
        dashboard.day_start = snapshot

    snapshots = list(dashboard.snapshots or [])
    snapshots.append(snapshot)
    if len(snapshots) > MAX_SNAPSHOTS:
        snapshots = snapshots[-MAX_SNAPSHOTS:]

    dashboard.snapshots = snapshots
    dashboard.last_updated = now
    dashboard.save(update_fields=['day_start', 'snapshots', 'last_updated'])


# ─────────────────────────────────────────────────────────────────────────────
# Consolidated message builder
# ─────────────────────────────────────────────────────────────────────────────

def build_consolidated_message(
    positions_data: List[Dict],
    mode_label: str,
    now=None,
    realized_today: Decimal = Decimal('0'),
) -> str:
    """
    Build ONE message showing all open positions grouped by broker.

    positions_data: list of dicts, each with:
        position     — Position ORM object
        pnl          — Decimal
        pnl_pct      — Decimal
        broker_name  — str  e.g. 'Kotak Neo'
        lots         — int
        needs_avg    — bool  (True when same symbol appears multiple times)

    Phone-optimised format — clean 2-line per position:
        HDFCBANK26MARFUT ▲ 305L
          ₹903→₹882 | 📉 -₹35.3L (-2.3%) 🔴
    """
    if now is None:
        now = timezone.now()

    now_str = ist_datetime_str(now)
    n = len(positions_data)
    total_unrealized = sum(d['pnl'] for d in positions_data)
    total_pnl = total_unrealized + realized_today

    # Day P&L summary line
    def _pnl_compact_sign(val: Decimal) -> str:
        abs_val = abs(float(val))
        sign = "+" if val >= 0 else "-"
        if abs_val >= 1_00_00_000:
            return f"{sign}₹{abs_val/1_00_00_000:.2f}Cr"
        if abs_val >= 1_00_000:
            return f"{sign}₹{abs_val/1_00_000:.1f}L"
        return f"{sign}₹{abs_val:,.0f}"

    day_pnl_line = (
        f"📅 Day P&L: {_pnl_compact_sign(total_pnl)}"
        f"  (live {_pnl_compact_sign(total_unrealized)}"
        f" + realized {_pnl_compact_sign(realized_today)})"
    )

    # Header
    msg = (
        f"📊 <b>PORTFOLIO MONITOR</b>  [{ist_time_str(now)}]\n"
        f"{mode_label} | {n} position{'s' if n != 1 else ''}\n"
        f"{day_pnl_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    # Group by broker (preserve order: sort by broker name then by worst P&L)
    from collections import OrderedDict
    by_broker: Dict[str, List[Dict]] = OrderedDict()
    for d in sorted(positions_data, key=lambda x: (x['broker_name'], float(x['pnl']))):
        bn = d['broker_name']
        by_broker.setdefault(bn, []).append(d)

    for broker_name, items in by_broker.items():
        msg += f"\n🏦 <b>{broker_name}</b>\n"
        for d in items:
            pos = d['position']
            lots = d['lots']
            pnl = d['pnl']
            pnl_pct = d['pnl_pct']
            sl_badge = _sl_status(pos)

            direction_arrow = "▲" if pos.direction == 'LONG' else ("▼" if pos.direction == 'SHORT' else "◆")
            pnl_emoji = "📈" if pnl >= 0 else "📉"

            # Distinguish duplicate symbols with avg price
            sym_label = d.get('label', pos.label)
            if d.get('needs_avg'):
                sym_label += f" [avg ₹{pos.entry_price:,.0f}]"

            # Price move
            move = pos.current_price - pos.entry_price
            move_sign = "+" if move >= 0 else ""

            # SL / Target reference (compact)
            risk_parts = []
            if pos.stop_loss:
                sl_dist = pos.current_price - pos.stop_loss
                risk_parts.append(f"SL ₹{pos.stop_loss:,.0f} ({sl_dist:+.0f})")
            if pos.target:
                tgt_dist = pos.target - pos.current_price
                risk_parts.append(f"Tgt ₹{pos.target:,.0f} ({tgt_dist:+.0f})")

            lots_label = (
                f"⚠️ qty={pos.quantity} (lot={pos.lot_size})"
                if pos.is_lot_mismatch else f"{lots}L"
            )
            msg += f"<b>{sym_label}</b> {direction_arrow} {lots_label}\n"
            msg += f"  ₹{pos.entry_price:,.0f}→₹{pos.current_price:,.0f} ({move_sign}₹{move:,.2f}/u)\n"
            msg += f"  {pnl_emoji} <b>{_fmt_compact(pnl, pnl_pct)}</b>{sl_badge}\n"
            if risk_parts:
                msg += f"  <i>{' | '.join(risk_parts)}</i>\n"

    # Footer — show combined unrealized (open positions)
    total_emoji = "📈" if total_unrealized >= 0 else "📉"
    abs_total = abs(float(total_unrealized))
    if abs_total >= 1_00_00_000:
        total_fmt = f"{'+'if total_unrealized>=0 else '-'}₹{abs_total/1_00_00_000:.2f}Cr"
    elif abs_total >= 1_00_000:
        total_fmt = f"{'+'if total_unrealized>=0 else '-'}₹{abs_total/1_00_000:.1f}L"
    else:
        total_fmt = f"{'+'if total_unrealized>=0 else '-'}₹{abs_total:,.0f}"

    msg += (
        f"\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{total_emoji} <b>Open P&L: {total_fmt}</b>\n"
        f"🔄 <i>{now_str}</i>"
    )
    return msg


# ─────────────────────────────────────────────────────────────────────────────
# Master dashboard send / edit
# ─────────────────────────────────────────────────────────────────────────────

def _build_dashboard_keyboard(positions_data: List[Dict]) -> dict:
    """
    Inline keyboard — one button per row, worst P&L first.

    Label format:  📉 HDFCBANK26MARFUT  ▲ 305L  -₹35.3L
    Status prefix: 🔴 = SL hit, 🎯 = Target hit, 📈/📉 = normal
    """
    rows = []
    for d in sorted(positions_data, key=lambda x: float(x['pnl'])):
        pos = d['position']
        pnl = d['pnl']
        lots = d['lots']

        # P&L compact
        abs_pnl = abs(float(pnl))
        sign = "+" if pnl >= 0 else "-"
        if abs_pnl >= 1_00_00_000:
            pnl_label = f"{sign}₹{abs_pnl/1_00_00_000:.2f}Cr"
        elif abs_pnl >= 1_00_000:
            pnl_label = f"{sign}₹{abs_pnl/1_00_000:.1f}L"
        else:
            pnl_label = f"{sign}₹{abs_pnl:,.0f}"

        # Status badge
        if pos.is_stop_loss_hit():
            badge = "🔴"
        elif pos.is_target_hit():
            badge = "🎯"
        elif pnl >= 0:
            badge = "📈"
        else:
            badge = "📉"

        direction_arrow = "▲" if pos.direction == 'LONG' else ("▼" if pos.direction == 'SHORT' else "◆")
        broker_short = {'KOTAK': 'NEO', 'ICICI': 'ICICI'}.get(
            pos.account.broker if pos.account else '', '?'
        )

        # Disambiguation: show avg price for duplicate symbols
        sym_label = d.get('label', pos.label)
        if d.get('needs_avg'):
            sym_label += f" @{pos.entry_price:,.0f}"

        lots_label = f"⚠️qty{pos.quantity}" if pos.is_lot_mismatch else f"{direction_arrow}{lots}L"
        label = f"{badge} {sym_label}  {lots_label}  {pnl_label}  [{broker_short}]"
        rows.append([{'text': label, 'callback_data': f'monitor_pos_{pos.id}'}])

    return {'inline_keyboard': rows}


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard update triggers
#
# Updates are sent when ANY of these conditions is true:
#   1. Day start (first run) or day end (>= 3:30 PM)
#   2. P&L moved outside ±5% band from last sent value
#   3. Any position within 0.2% of SL or target price
# ─────────────────────────────────────────────────────────────────────────────
PNL_BAND_PCT = Decimal('5')  # ±5% band around last sent P&L
SL_TARGET_PROXIMITY_PCT = 0.002  # 0.2% of price = "close to SL/target"


def _is_first_or_last_run(master, now=None) -> bool:
    """True on first run of the day, or ONCE at/after 3:30 PM (closing snapshot).

    Bug history: this used to return True for every tick from 15:30 onward
    (not just the first one), which — combined with a beat schedule that ran
    until 15:59 — forced a dashboard edit every single minute for 30 minutes
    past market close. Now it fires the closing snapshot exactly once, by
    checking whether the last update already happened at/after 15:30 today.
    """
    if not master.snapshots:
        return True

    if now is None:
        now = timezone.now()
    ist_now = _to_ist(now)
    is_close_window = ist_now.hour >= 15 and ist_now.minute >= 30
    if not is_close_window:
        return False

    if master.last_updated:
        ist_last = _to_ist(master.last_updated)
        already_sent_closing = ist_last.hour >= 15 and ist_last.minute >= 30
        if already_sent_closing:
            return False

    return True


def _near_sl_or_target(positions_data: List[Dict]) -> bool:
    """True if any position's current price is within 0.2% of its SL or target."""
    for d in positions_data:
        pos = d['position']
        price = float(pos.current_price or 0)
        if price <= 0:
            continue

        if pos.stop_loss:
            sl = float(pos.stop_loss)
            if sl > 0 and abs(price - sl) / price <= SL_TARGET_PROXIMITY_PCT:
                logger.info(f"Near SL: {pos.label} price={price:.2f} SL={sl:.2f}")
                return True

        if pos.target:
            tgt = float(pos.target)
            if tgt > 0 and abs(price - tgt) / price <= SL_TARGET_PROXIMITY_PCT:
                logger.info(f"Near target: {pos.label} price={price:.2f} Tgt={tgt:.2f}")
                return True

    return False


def _pnl_outside_band(master, positions_data: List[Dict]) -> bool:
    """True if total P&L moved outside ±5% of the last sent value.

    Example: last sent at -₹1.5Cr → band is [-₹1.575Cr, -₹1.425Cr].
    Update only when P&L exits this band.
    """
    last = (master.snapshots or [{}])[-1] if master.snapshots else {}
    prev_pnl = Decimal(str(last.get('total_pnl', 0)))
    total_pnl = sum(d['pnl'] for d in positions_data)

    if prev_pnl == 0:
        # No baseline yet — update if P&L exceeds ₹50K
        outside = abs(total_pnl) >= Decimal('50000')
    else:
        pct_change = abs(total_pnl - prev_pnl) / abs(prev_pnl) * 100
        outside = pct_change >= PNL_BAND_PCT

    logger.info(
        f"PnL band check: {prev_pnl:,.0f}→{total_pnl:,.0f} "
        f"(Δ₹{abs(total_pnl - prev_pnl):,.0f}, "
        f"band ±{PNL_BAND_PCT}% = ±₹{abs(prev_pnl) * PNL_BAND_PCT / 100:,.0f}) | "
        f"{'OUTSIDE' if outside else 'within'}"
    )
    return outside


def should_update_dashboard(master, positions_data: List[Dict], now=None) -> bool:
    """Decide whether to send/edit the Telegram dashboard.

    Triggers:
    1. Day start (first run) / day end (>= 3:30 PM)
    2. P&L outside ±5% band of last sent value
    3. Any position within 0.2% of SL or target
    """
    if _is_first_or_last_run(master, now):
        return True

    if _near_sl_or_target(positions_data):
        return True

    return _pnl_outside_band(master, positions_data)


def _store_master_snapshot(master, positions_data: List[Dict], now):
    """Record current totals in master dashboard snapshots for next comparison."""
    total_pnl = sum(d['pnl'] for d in positions_data)
    total_entry = sum(
        (d['position'].entry_value if d['position'].entry_value > 0
         else d['position'].entry_price * d['position'].quantity)
        for d in positions_data
    )
    total_pct = float(total_pnl / total_entry * 100) if total_entry > 0 else 0.0

    snapshot = {
        'time': ist_time_str(now),
        'total_pnl': float(total_pnl),
        'total_pnl_pct': total_pct,
    }
    master.snapshots = [snapshot]  # only keep latest for comparison
    master.save(update_fields=['snapshots'])


def send_or_update_master_dashboard(
    positions_data: List[Dict],
    mode_label: str,
    telegram_client,
    date=None,
    now=None,
    realized_today: Decimal = Decimal('0'),
) -> bool:
    """
    Send or edit the single consolidated monitoring message.

    - First call → sends new silent message, stores message_id
    - Subsequent calls → edits in place ONLY if:
      • P&L moved outside ±5% band of last sent value, OR
      • Any position within 0.2% of SL or target price

    Returns True if successful.
    """
    if now is None:
        now = timezone.now()

    master = get_or_create_master_dashboard(date)
    message = build_consolidated_message(positions_data, mode_label, now, realized_today)
    keyboard = _build_dashboard_keyboard(positions_data)

    if master.telegram_message_id:
        # Skip edit if no trigger condition met
        if not should_update_dashboard(master, positions_data, now):
            logger.info("Dashboard update SKIPPED — within band, no events")
            return True
        logger.info("Dashboard update PROCEEDING")
        success, result = telegram_client.edit_message(
            message_id=master.telegram_message_id,
            text=message,
            reply_markup=keyboard,
        )
        if success:
            master.last_updated = now
            master.save(update_fields=['last_updated'])
            _store_master_snapshot(master, positions_data, now)
            return True
        logger.warning(
            f"Could not edit master dashboard msg {master.telegram_message_id}: {result}. "
            "Sending new message."
        )
        master.telegram_message_id = None

    success, result = telegram_client.send_message(
        message, disable_notification=True, reply_markup=keyboard
    )
    if success:
        try:
            msg_id = int(result)
            master.telegram_message_id = msg_id
            master.last_updated = now
            master.save(update_fields=['telegram_message_id', 'last_updated'])
        except (ValueError, TypeError):
            pass
        _store_master_snapshot(master, positions_data, now)
        return True

    logger.error(f"Failed to send master monitoring dashboard: {result}")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Exit suggestion deduplication
# ─────────────────────────────────────────────────────────────────────────────

def should_send_exit_suggestion(
    dashboard, reason: str, cooldown_minutes: int = EXIT_SUGGESTION_COOLDOWN_MINUTES
) -> bool:
    """
    Return True if we should send a new exit suggestion.

    Deduplication rules:
    - First suggestion of the day → always send
    - User explicitly held with same reason → suppress (respect hold)
    - User held but reason changed substantially → clear hold, re-alert
    - Different reason than last time → always send
    - Same reason but cooldown elapsed → send again (reminder)
    - Same reason within cooldown → skip (already pending)
    """
    import json

    # Approaching market close (last 30 min) — always re-alert regardless of hold
    import pytz
    ist_now = _to_ist(timezone.now())
    approaching_close = (ist_now.hour == 15 and ist_now.minute >= 0) or ist_now.hour >= 16
    if approaching_close:
        # Clear any hold flag — market closing, must decide
        position_id = dashboard.position_id
        if position_id:
            from apps.core.models import NseFlag
            hold_raw = NseFlag.get(f'position_hold_{position_id}', '')
            if hold_raw and hold_raw != '':
                NseFlag.set(
                    f'position_hold_{position_id}', '',
                    'Cleared: approaching market close'
                )
                logger.info(
                    f"Hold cleared for pos #{position_id}: approaching market close"
                )
        # Apply normal cooldown logic (don't spam every minute in last 30 min)

    # Check if user explicitly held this position
    position_id = dashboard.position_id
    if position_id and not approaching_close:
        from apps.core.models import NseFlag
        hold_raw = NseFlag.get(f'position_hold_{position_id}', '')
        if hold_raw and hold_raw != '':
            # Parse hold data (may be 'true' or JSON with reason/price)
            hold_data = _parse_hold_data(hold_raw)
            held_reason = hold_data.get('reason', '')
            held_price = hold_data.get('price')

            # Same reason as when user held → respect the hold decision
            if held_reason and held_reason == reason:
                logger.info(
                    f"Exit suggestion suppressed for pos #{position_id}: "
                    f"user held with same reason '{reason}'"
                )
                return False

            if not held_reason and dashboard.last_exit_reason == reason:
                # Old-style hold flag ('true') — same reason as last sent
                logger.info(
                    f"Exit suggestion suppressed for pos #{position_id}: "
                    f"user held (legacy flag), same reason '{reason}'"
                )
                return False

            # Price moved significantly against position since hold? Re-alert.
            if held_price and dashboard.position:
                try:
                    current_price = float(dashboard.position.current_price or 0)
                    price_move_pct = abs(current_price - held_price) / held_price * 100
                    if price_move_pct > HOLD_CLEAR_PRICE_MOVE_PCT:
                        logger.info(
                            f"Clearing hold for pos #{position_id}: "
                            f"price moved {price_move_pct:.1f}% since hold "
                            f"(threshold {HOLD_CLEAR_PRICE_MOVE_PCT}%)"
                        )
                        NseFlag.set(
                            f'position_hold_{position_id}', '',
                            f'Cleared: price moved >{HOLD_CLEAR_PRICE_MOVE_PCT}% since hold'
                        )
                        # Fall through to normal logic — will re-alert
                    else:
                        # Price hasn't moved enough — keep respecting hold
                        return False
                except (ValueError, TypeError):
                    pass

            # Reason changed substantially → clear hold and re-alert
            if held_reason and held_reason != reason:
                logger.info(
                    f"Clearing hold for pos #{position_id}: "
                    f"reason changed from '{held_reason}' to '{reason}'"
                )
                NseFlag.set(
                    f'position_hold_{position_id}', '',
                    f'Cleared: reason changed to {reason}'
                )
                return True

    if not dashboard.last_exit_sent_at:
        return True
    if dashboard.last_exit_reason != reason:
        return True

    # Same reason as last alert — only re-send if BOTH:
    #   (a) time cooldown elapsed, AND
    #   (b) price has moved further against position by EXIT_RE_ALERT_PRICE_MOVE_PCT
    # This prevents the same SL hit from re-firing every 5 min with 0.1% P&L diff.
    from datetime import timedelta
    elapsed = timezone.now() - dashboard.last_exit_sent_at
    if elapsed.total_seconds() < cooldown_minutes * 60:
        return False  # Too soon

    # Time cooldown passed — now check price movement
    if position_id and dashboard.position:
        try:
            from django.core.cache import cache
            price_key = f'tg_exit_price_{position_id}'
            last_alert_price = cache.get(price_key)
            current_price = float(dashboard.position.current_price or 0)

            if last_alert_price is not None and current_price > 0:
                move_pct = abs(current_price - float(last_alert_price)) / float(last_alert_price) * 100
                if move_pct < EXIT_RE_ALERT_PRICE_MOVE_PCT:
                    logger.debug(
                        f"Exit re-alert suppressed for pos #{position_id}: "
                        f"price moved only {move_pct:.2f}% (need {EXIT_RE_ALERT_PRICE_MOVE_PCT}%)"
                    )
                    return False

            # Record current price for next comparison
            cache.set(price_key, str(current_price), timeout=3600)
        except Exception:
            pass  # Fail-open: if cache fails, allow re-alert

    return True


def _parse_hold_data(raw: str) -> dict:
    """Parse hold flag value — may be 'true' (legacy) or JSON."""
    import json
    if not raw or raw == '':
        return {}
    if raw == 'true':
        return {'held': True}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {'held': True}


def record_exit_suggestion(dashboard, reason: str, message_id: Optional[int] = None):
    """Persist that an exit suggestion was just sent."""
    dashboard.last_exit_reason = reason
    dashboard.last_exit_sent_at = timezone.now()
    if message_id is not None:
        dashboard.last_exit_msg_id = message_id
    dashboard.save(update_fields=['last_exit_reason', 'last_exit_sent_at', 'last_exit_msg_id'])

    # Record the price at alert time for re-alert price-change gating
    position_id = dashboard.position_id
    if position_id and dashboard.position:
        try:
            from django.core.cache import cache
            price_key = f'tg_exit_price_{position_id}'
            current_price = float(dashboard.position.current_price or 0)
            if current_price > 0:
                cache.set(price_key, str(current_price), timeout=3600)
        except Exception:
            pass
