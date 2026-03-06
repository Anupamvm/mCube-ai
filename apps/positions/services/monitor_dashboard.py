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

            msg += f"<b>{sym_label}</b> {direction_arrow} {lots}L\n"
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

        label = f"{badge} {sym_label}  {direction_arrow}{lots}L  {pnl_label}  [{broker_short}]"
        rows.append([{'text': label, 'callback_data': f'monitor_pos_{pos.id}'}])

    return {'inline_keyboard': rows}


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
    - Subsequent calls → edits in place (no spam)

    Returns True if successful.
    """
    if now is None:
        now = timezone.now()

    master = get_or_create_master_dashboard(date)
    message = build_consolidated_message(positions_data, mode_label, now, realized_today)
    keyboard = _build_dashboard_keyboard(positions_data)

    if master.telegram_message_id:
        success, result = telegram_client.edit_message(
            message_id=master.telegram_message_id,
            text=message,
            reply_markup=keyboard,
        )
        if success:
            master.last_updated = now
            master.save(update_fields=['last_updated'])
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
    - Different reason than last time → always send
    - Same reason but cooldown elapsed → send again (reminder)
    - Same reason within cooldown → skip (already pending)
    """
    if not dashboard.last_exit_sent_at:
        return True
    if dashboard.last_exit_reason != reason:
        return True
    from datetime import timedelta
    elapsed = timezone.now() - dashboard.last_exit_sent_at
    if elapsed.total_seconds() >= cooldown_minutes * 60:
        return True
    return False


def record_exit_suggestion(dashboard, reason: str, message_id: Optional[int] = None):
    """Persist that an exit suggestion was just sent."""
    dashboard.last_exit_reason = reason
    dashboard.last_exit_sent_at = timezone.now()
    if message_id is not None:
        dashboard.last_exit_msg_id = message_id
    dashboard.save(update_fields=['last_exit_reason', 'last_exit_sent_at', 'last_exit_msg_id'])
