"""
Position Monitoring Celery Tasks

Consolidated monitor: P&L updates + exit condition checks.

Manual mode (FULL_CONTROL / SUPERVISED):
- Updates P&L every minute
- EDITS a single daily Telegram monitoring dashboard (anti-spam)
- Sends EXIT SUGGESTIONS via Telegram with inline keyboard
- Does NOT auto-execute — waits for user to confirm or cancel

Autonomous mode:
- Same P&L updates and dashboard editing
- Auto-executes exits without waiting for confirmation

Anti-spam rules:
- Monitoring progress → single daily message, edited each run
  (Day start + last 3 snapshots — trader sees the progression)
- Exit suggestions → deduplicated: same trigger re-sent only after
  EXIT_SUGGESTION_COOLDOWN_MINUTES (5 min) to avoid suggestion spam

MonitorLog: every P&L check and exit trigger is stored with IST timestamp.
"""

import logging
from decimal import Decimal
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.positions.models import Position, MonitorLog
from apps.positions.services.position_manager import close_position
from apps.positions.services.exit_manager import should_exit_position
from apps.positions.services.sr_exit_engine import apply_sl_and_target
from apps.positions.services.monitor_dashboard import (
    get_or_create_dashboard,
    add_snapshot,
    send_or_update_master_dashboard,
    should_send_exit_suggestion,
    record_exit_suggestion,
    ist_datetime_str,
    BROKER_DISPLAY,
)
from apps.alerts.services.telegram_client import (
    get_telegram_client,
    send_telegram_notification,
)
from apps.core.utils.decorators import task_enabled_guard
from apps.alerts.services.notification_service import notify

# Redis key for monitor task distributed lock.
# Timeout is set to 55 s — just under the 1-min beat interval so a
# legitimate slow cycle can finish, but a crashed worker won't block
# the next cycle indefinitely.
_MONITOR_LOCK_KEY = 'monitor_and_manage_positions_lock'
_MONITOR_LOCK_TTL = 55  # seconds

# Redis key prefix for sync failure strike counters (per-account).
# Three consecutive failures → CRITICAL Telegram alert.
_SYNC_FAIL_KEY_PREFIX = 'pos_sync_fail_count'
_SYNC_FAIL_THRESHOLD = 3
_SYNC_FAIL_TTL = 600  # 10 min — resets if broker recovers

logger = logging.getLogger(__name__)

# Human-readable labels for exit reasons (avoids raw replace('_', ' ') output).
_EXIT_REASON_LABELS = {
    'SL_HIT': 'Stop-Loss Hit',
    'TARGET_HIT': 'Target Hit',
    'EXIT_ON_EXPIRY': 'Expiry Exit',
    'EOD_EXIT': 'End of Day Exit',
    'NEAR_SL_REQUEST': 'Near-SL Exit',
    'STRUCTURAL_SL': 'Structural SL',
    'TRAILING_SL': 'Trailing SL',
    'SR_BREAKDOWN': 'S/R Breakdown',
    'MANUAL': 'Manual Exit',
}


def _mode_footer(config) -> str:
    """One-line config tag appended to actionable messages."""
    return (
        f"\n<i>⚙️ {config.get_notification_level_display_short()} "
        f"· {config.get_position_sizing_display_short()}</i>"
    )


@shared_task(name='apps.positions.tasks.monitor_and_manage_positions')
@task_enabled_guard(['monitor-and-manage-positions', 'monitor-and-manage-positions-close'])
def monitor_and_manage_positions():
    """
    Monitors all active positions: updates P&L, checks exit conditions.

    Scheduled: Every minute during market hours (9:00 AM – 3:30 PM, Mon–Fri)

    Behaviour depends on notification_level in TradingCoreConfig:

    FULL_CONTROL / SUPERVISED  →  "Manual mode"
      • Edits the live daily monitoring dashboard (single Telegram message)
      • On exit trigger: sends suggestion with [✅ Close Now] [⏸️ Hold] keyboard
      • Does NOT execute the exit — waits for user response

    AUTONOMOUS
      • Edits the live daily monitoring dashboard
      • On exit trigger: auto-executes immediately, sends result notification
    """
    # ── Distributed lock — prevent overlapping monitor cycles ─────────────────
    # cache.add() is atomic on Redis: returns True only if the key did NOT
    # already exist (i.e., we are the first caller).  If another cycle is
    # still running (broker call took >60 s) we skip rather than double-process.
    acquired = cache.add(_MONITOR_LOCK_KEY, '1', timeout=_MONITOR_LOCK_TTL)
    if not acquired:
        logger.warning(
            "monitor_and_manage_positions: previous cycle still running — skipping this tick"
        )
        return {'success': True, 'skipped': True, 'reason': 'lock_held'}

    try:
        from apps.core.models import TradingCoreConfig
        config = TradingCoreConfig.get_instance()

        # ── Sync latest positions + LTPs from all broker accounts ─────────────
        # This ensures: (a) any new positions are in DB, (b) current_price is
        # fresh for P&L calculations — runs before every monitor cycle.
        sync_failed = False
        try:
            from apps.positions.services.position_sync import sync_positions_from_brokers
            sync_positions_from_brokers(include_history=False)
            # Reset strike counter on success — broker is healthy again
            cache.delete(_SYNC_FAIL_KEY_PREFIX)
        except Exception as sync_err:
            sync_failed = True
            logger.warning(f"Pre-monitor broker sync failed (continuing with DB state): {sync_err}")
            # Count consecutive failures
            fail_count = cache.get(_SYNC_FAIL_KEY_PREFIX, 0) + 1
            cache.set(_SYNC_FAIL_KEY_PREFIX, fail_count, timeout=_SYNC_FAIL_TTL)
            # Alert on FIRST failure (warning), escalate to CRITICAL on 3rd
            if fail_count == 1:
                notify('SYSTEM_STATUS',
                    title='Position Sync Failed',
                    task='monitor_and_manage_positions',
                    priority='WARNING',
                    metrics={'P&L': 'using stale prices'},
                    context=[
                        'Broker sync failed — P&L and exit checks use last known prices',
                        f'Error: {str(sync_err)[:150]}',
                    ],
                )
            elif fail_count >= _SYNC_FAIL_THRESHOLD:
                notify('CRITICAL_ERROR',
                    title='Position Sync Failing',
                    task='monitor_and_manage_positions',
                    metrics={
                        'Failures': f'{fail_count} consecutive',
                        'P&L': 'stale',
                    },
                    context=[
                        f'{fail_count} consecutive broker sync errors',
                        'P&L calculations using stale prices',
                    ],
                    system={'Last error': str(sync_err)[:200]},
                )

        all_open = Position.objects.filter(status='OPEN').select_related('account')

        if not all_open.exists():
            return {'success': True, 'positions': 0}

        if config.is_simulated():
            return {
                'success': True,
                'simulated': True,
                'positions': all_open.count(),
            }

        # ── Deduplicate positions ─────────────────────────────────────────
        # Multiple DB accounts per broker can map to the same real broker
        # account, creating duplicate Position rows. Keep one per
        # (broker, instrument, quantity) — prefer the most recently synced.
        seen_keys = set()
        active_positions = []
        for p in all_open.order_by('-updated_at'):
            key = (p.account.broker, p.instrument, p.quantity)
            if key not in seen_keys:
                seen_keys.add(key)
                active_positions.append(p)

        mode_label = config.get_notification_level_display_short()
        is_manual_mode = not config.is_autonomous()   # FULL_CONTROL or SUPERVISED

        telegram = get_telegram_client()
        now = timezone.now()
        today = timezone.localdate()

        updated_count = 0
        exits_executed = 0
        suggestions_sent = 0
        errors = []

        # Collect data for consolidated dashboard (all positions in one message)
        positions_data = []
        # Batch MonitorLog entries to reduce SQLite write contention
        pending_monitor_logs = []

        # Detect duplicate symbols per account (for avg-price disambiguation in display)
        from collections import Counter
        sym_counts = Counter(
            (p.account_id, p.instrument) for p in active_positions
        )

        for position in active_positions:
            try:
                # ── 1. P&L Calculation ────────────────────────────────────────
                if position.direction == 'LONG':
                    pnl = (position.current_price - position.entry_price) * position.quantity
                elif position.direction == 'SHORT':
                    pnl = (position.entry_price - position.current_price) * position.quantity
                else:  # NEUTRAL (strangle / iron condor)
                    pnl = position.premium_collected

                position.unrealized_pnl = pnl
                position.save(update_fields=['unrealized_pnl'])

                # P&L % — use entry_value from DB if set, else derive from price × qty
                entry_val = position.entry_value if position.entry_value > 0 else (
                    position.entry_price * position.quantity
                )
                pnl_pct = (
                    (pnl / entry_val * Decimal('100'))
                    if entry_val > 0
                    else Decimal('0')
                )

                # ── 2. MonitorLog (timestamped) — batched for efficiency ──────
                pending_monitor_logs.append(MonitorLog(
                    position=position,
                    check_type='PNL_UPDATE',
                    result='OK',
                    message=(
                        f"[{ist_datetime_str(now)}] "
                        f"Price: ₹{position.current_price:,.2f} | "
                        f"P&L: ₹{pnl:,.0f} ({pnl_pct:+.2f}%)"
                    ),
                    price_at_check=position.current_price,
                    pnl_at_check=pnl,
                ))

                # ── 3. Per-position dashboard + SR engine (SL/target update) ──
                dashboard, _ = get_or_create_dashboard(position, today)

                # Apply SR-based SL tightening and target initialization.
                # Must run before near-SL warning and exit check so both
                # see the latest structural SL/target values.
                # Also handles new/broker-synced positions that arrive without SL.
                sr_eval = apply_sl_and_target(position, dashboard, now)

                add_snapshot(dashboard, position.current_price, pnl, pnl_pct, now)

                # Collect for consolidated Telegram message
                lots = position.lots
                if position.is_lot_mismatch:
                    logger.warning(
                        f"Position #{position.id} ({position.instrument}) has a "
                        f"quantity/lot_size mismatch: qty={position.quantity} "
                        f"lot_size={position.lot_size} — likely orphaned/corrupted "
                        f"data, not a real broker position. Flagging in dashboard."
                    )
                broker_name = BROKER_DISPLAY.get(
                    position.account.broker if position.account else '',
                    position.account.broker if position.account else 'Unknown'
                )
                positions_data.append({
                    'position': position,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'broker_name': broker_name,
                    'lots': lots,
                    'needs_avg': sym_counts.get((position.account_id, position.instrument), 1) > 1,
                    'label': position.label,
                })

                # ── 4. Near-SL warning (uses SR-updated SL from step 3) ──────
                # Tracked separately from exit suggestions in sr_tracking
                # JSON to avoid cross-contamination. Sent ONCE per day per
                # position — the dashboard already shows live SL proximity.
                if (
                    position.stop_loss
                    and position.current_price
                    and not position.is_stop_loss_hit()
                ):
                    price = float(position.current_price)
                    sl = float(position.stop_loss)
                    buffer_pct = abs(price - sl) / price * 100  # % of current price
                    sr_data = dashboard.sr_tracking or {}
                    already_warned = sr_data.get('near_sl_warned', False)
                    if buffer_pct < 1.0 and not already_warned:  # within 1% of SL, once per day
                        from apps.alerts.services.notification_payload import NotificationPayload
                        from apps.alerts.services.telegram_client import send_notification as _send_notif
                        _near_sl_payload = NotificationPayload(
                            title='Near Stop-Loss',
                            status='WARNING',
                            instrument=position.instrument,
                            strategy=(
                                {'KOTAK': 'Kotak Neo', 'ICICI': 'ICICI Breeze'}.get(
                                    position.account.broker if position.account else '',
                                    position.account.broker if position.account else ''
                                )
                            ),
                            task='monitor_and_manage_positions',
                            timestamp=now,
                            metrics={
                                'Buffer': f"{buffer_pct:.2f}%",
                                'SL': f"₹{sl:,.2f}",
                                'Now': f"₹{price:,.2f}",
                            },
                            keyboard=[[
                                {'text': '📊 View Exit Details', 'callback_data': f'request_exit_{position.id}'},
                                {'text': '⏸ Dismiss',           'callback_data': f'hold_exit_{position.id}'},
                            ]],
                            position={
                                'Direction': position.direction,
                                'Current': f"₹{price:,.2f}",
                                'SL': f"₹{sl:,.2f}",
                                'Distance': f"₹{abs(price - sl):,.2f}  ({buffer_pct:.2f}% buffer)",
                                'P&L': f"₹{float(pnl):+,.0f}",
                            },
                            context=[
                                'Within 1% of stop-loss — once-per-day alert',
                                'Tap [View Exit Details] for full confirmation screen',
                            ],
                            system={'Position ID': f"#{position.id}"},
                            priority='WARNING',
                            dedup_key=f'near_sl_{position.id}',
                            mode_label=config.get_notification_level_display_short(),
                            sizing_label=config.get_position_sizing_display_short(),
                        )
                        _send_notif(_near_sl_payload)
                        sr_data['near_sl_warned'] = True
                        dashboard.sr_tracking = sr_data
                        dashboard.save(update_fields=['sr_tracking'])

                # ── 4b. STRUCTURAL PRESSURE — Stage 2 pre-trigger warning ────
                # Emitted when Condition A is met but Condition B is not yet.
                # Gives the trader ~5 min lead time before the full SL fires.
                # Only sent in manual mode (autonomous mode will auto-exit on trigger).
                if is_manual_mode and sr_eval.get('structural_pressure'):
                    stage2 = sr_eval['structural_pressure']
                    if stage2.get('should_warn') and stage2.get('reason'):
                        MonitorLog.objects.create(
                            position=position,
                            check_type='STRUCTURAL_PRESSURE',
                            result='STAGE2_WARNING_SENT',
                            message=(
                                f"[{ist_datetime_str(now)}] "
                                f"Structural pressure detected @ level={stage2.get('level',0):.2f} "
                                f"score={stage2.get('score',0)}/100"
                            ),
                            price_at_check=position.current_price,
                            pnl_at_check=pnl,
                        )
                        notify('RISK_WARNING',
                            title='Structural Pressure',
                            instrument=position.instrument,
                            task='monitor_and_manage_positions',
                            context=[stage2['reason']],
                            dedup_key=f'struct_pressure_{position.id}',
                            position_id=position.id,
                        )
                        logger.info(
                            f"Stage 2 structural pressure warning sent for pos #{position.id}"
                        )

                # ── 5. Exit condition check ───────────────────────────────────
                # SR structural SL trigger (two-condition rule from step 3)
                if sr_eval['sl_triggered']:
                    should_exit = True
                    reason = sr_eval['sl_reason']
                    exit_price = position.current_price
                else:
                    # Standard checks: is_stop_loss_hit, is_target_hit, EOD, expiry
                    should_exit, reason, exit_price = should_exit_position(position, now)

                if should_exit:
                    logger.warning(
                        f"Exit condition for pos #{position.id}: {reason} @ ₹{exit_price:,.2f}"
                    )

                    if is_manual_mode:
                        # ── Manual mode: send suggestion, do NOT execute ──────
                        dashboard.refresh_from_db()

                        if should_send_exit_suggestion(dashboard, reason):
                            MonitorLog.objects.create(
                                position=position,
                                check_type='EXIT_SUGGESTION',
                                result='SUGGESTION_SENT',
                                message=(
                                    f"[{ist_datetime_str(now)}] "
                                    f"Exit triggered ({reason}) @ ₹{exit_price:,.2f}. "
                                    f"Suggestion sent to Telegram — awaiting confirmation."
                                ),
                                price_at_check=position.current_price,
                                pnl_at_check=pnl,
                                action_taken='SUGGESTION_SENT',
                            )

                            from apps.trading.services.trade_confirmation import (
                                get_confirmation_service,
                            )
                            conf_service = get_confirmation_service()
                            success, result = conf_service.request_exit_confirmation(
                                position, reason, current_pnl=pnl
                            )

                            if success:
                                try:
                                    msg_id = int(result)
                                except (ValueError, TypeError):
                                    msg_id = None
                                record_exit_suggestion(dashboard, reason, msg_id)
                                suggestions_sent += 1
                                logger.info(
                                    f"Exit suggestion sent for pos #{position.id}: {reason}"
                                )
                            else:
                                logger.error(
                                    f"Failed to send exit suggestion for pos #{position.id}: {result}"
                                )
                        else:
                            # Suppressed — either held by user or duplicate cooldown
                            from apps.core.models import NseFlag
                            hold_raw = NseFlag.get(f'position_hold_{position.id}', '')
                            is_held = hold_raw and hold_raw != ''

                            MonitorLog.objects.create(
                                position=position,
                                check_type='EXIT_SUGGESTION',
                                result='HELD_BY_USER' if is_held else 'SKIPPED_DUPLICATE',
                                message=(
                                    f"[{ist_datetime_str(now)}] "
                                    f"Exit condition ({reason}) still active — "
                                    f"{'user chose to hold, suppressing re-alert' if is_held else 'suggestion already pending, skipping duplicate'}."
                                ),
                                price_at_check=position.current_price,
                                pnl_at_check=pnl,
                                action_taken='HELD_BY_USER' if is_held else 'DUPLICATE_SKIPPED',
                            )
                            logger.debug(
                                f"Exit suggestion {'held' if is_held else 'deduped'} "
                                f"for pos #{position.id} / {reason}"
                            )

                    else:
                        # ── Autonomous mode: auto-execute immediately ─────────
                        MonitorLog.objects.create(
                            position=position,
                            check_type='AUTO_EXIT',
                            result='EXECUTING',
                            message=(
                                f"[{ist_datetime_str(now)}] "
                                f"Auto-exit: {reason} @ ₹{exit_price:,.2f}"
                            ),
                            price_at_check=position.current_price,
                            pnl_at_check=pnl,
                            action_taken='AUTO_EXIT',
                        )

                        success, message = close_position(
                            position=position,
                            exit_price=position.current_price,
                            exit_reason=reason,
                            place_broker_order=True,
                        )

                        from apps.alerts.services.notification_payload import NotificationPayload
                        from apps.alerts.services.telegram_client import send_notification as _send_notif
                        reason_label = _EXIT_REASON_LABELS.get(reason, reason.replace('_', ' ').title())
                        if success:
                            position.refresh_from_db()
                            pnl_result = position.realized_pnl
                            pnl_sign = "+" if pnl_result >= 0 else ""
                            _auto_exit_payload = NotificationPayload(
                                title='Auto-Exit Executed',
                                status='SUCCESS' if pnl_result >= 0 else 'WARNING',
                                instrument=position.instrument,
                                strategy=mode_label,
                                task='monitor_and_manage_positions',
                                timestamp=now,
                                metrics={
                                    'P&L': f"{pnl_sign}₹{abs(pnl_result):,.0f}",
                                    'Exit': f"₹{exit_price:,.2f}",
                                    'Reason': reason_label,
                                },
                                system={'Position ID': f"#{position.id}"},
                                priority='INFO',
                                mode_label=config.get_notification_level_display_short(),
                                sizing_label=config.get_position_sizing_display_short(),
                            )
                            _send_notif(_auto_exit_payload)
                            exits_executed += 1
                        else:
                            _auto_exit_fail_payload = NotificationPayload(
                                title='Auto-Exit Failed',
                                status='ERROR',
                                instrument=position.instrument,
                                task='monitor_and_manage_positions',
                                timestamp=now,
                                metrics={'Reason': reason_label},
                                context=[message.splitlines()[0]],
                                system={'Position ID': f"#{position.id}"},
                                priority='CRITICAL',
                                mode_label=config.get_notification_level_display_short(),
                                sizing_label=config.get_position_sizing_display_short(),
                            )
                            _send_notif(_auto_exit_fail_payload)

                updated_count += 1

            except Exception as e:
                logger.error(
                    f"Error processing position #{position.id}: {e}", exc_info=True
                )
                errors.append(f"pos {position.id}: {e}")

        # ── Flush batched MonitorLog entries in one DB write ─────────────────
        if pending_monitor_logs:
            try:
                MonitorLog.objects.bulk_create(pending_monitor_logs)
            except Exception as bulk_err:
                logger.warning(f"bulk_create MonitorLog failed, falling back: {bulk_err}")
                for log in pending_monitor_logs:
                    try:
                        log.save()
                    except Exception:
                        pass

        # ── Consolidated dashboard (ONE message for all positions) ────────────
        if positions_data:
            # Sum today's realized P&L from positions closed today
            from apps.core.constants import POSITION_STATUS_CLOSED
            from django.db.models import Sum
            realized_result = Position.objects.filter(
                status=POSITION_STATUS_CLOSED,
                exit_time__date=today,
            ).aggregate(total=Sum('realized_pnl'))
            realized_today = realized_result['total'] or Decimal('0')

            send_or_update_master_dashboard(
                positions_data, mode_label, telegram, date=today, now=now,
                realized_today=realized_today,
            )

        # ── Clear hold flags at end of trading day (>= 15:30 IST) ─────────
        import pytz
        ist_now = now.astimezone(pytz.timezone('Asia/Kolkata'))
        if ist_now.hour >= 15 and ist_now.minute >= 30:
            from apps.core.models import NseFlag
            for position in active_positions:
                hold_key = f'position_hold_{position.id}'
                if NseFlag.get(hold_key, ''):
                    NseFlag.set(hold_key, '', 'Auto-cleared at day end')
                    logger.info(f"Hold flag cleared for pos #{position.id} (day end)")

        # ── Paper position monitoring (separate, non-blocking) ────────────
        paper_exits = 0
        try:
            if config.is_paper_trading_enabled():
                paper_positions = Position.all_objects.filter(
                    is_paper=True, status='OPEN',
                ).select_related('account')

                for pp in paper_positions:
                    try:
                        _monitor_paper_position(pp, config, now, today)
                        paper_exits += 1
                    except Exception as ppe:
                        logger.error(f"[PAPER] Monitor error for {pp.instrument}: {ppe}")
        except Exception as pe:
            logger.error(f"[PAPER] Paper monitoring error (non-fatal): {pe}", exc_info=True)

        return {
            'success': True,
            'positions_updated': updated_count,
            'exits_executed': exits_executed,
            'suggestions_sent': suggestions_sent,
            'paper_monitored': paper_exits,
            'errors': errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Critical error in position monitor: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}
    finally:
        # Always release the distributed lock so the next cycle can run,
        # even if this cycle raised an unhandled exception.
        cache.delete(_MONITOR_LOCK_KEY)


def _monitor_paper_position(position, config, now, today):
    """
    Monitor a single paper position: update P&L and check exit conditions.

    Paper positions always auto-execute exits (no Telegram confirmation needed).
    """
    from apps.positions.services.exit_manager import check_exit_conditions
    from apps.positions.services.position_manager import close_position

    # Fetch current LTP for paper position
    try:
        from apps.brokers.integrations.paper_broker import PaperBroker
        broker = PaperBroker(position.account)
        quote = broker.get_quote(position.instrument)
        if quote and quote.ltp > 0:
            position.current_price = Decimal(str(quote.ltp))
    except Exception:
        pass  # Use existing current_price if quote fails

    # Calculate P&L
    if position.direction == 'LONG':
        pnl = (position.current_price - position.entry_price) * position.quantity
    elif position.direction == 'SHORT':
        pnl = (position.entry_price - position.current_price) * position.quantity
    else:
        pnl = position.premium_collected if position.premium_collected else Decimal('0')

    position.unrealized_pnl = pnl
    position.save(update_fields=['unrealized_pnl', 'current_price'])

    # Check exit conditions
    exit_result = check_exit_conditions(position)

    if exit_result.get('should_exit'):
        exit_reason = exit_result.get('exit_reason', 'PAPER_EXIT')
        exit_price = exit_result.get('exit_price', position.current_price)

        success, msg = close_position(
            position,
            exit_price=exit_price,
            exit_reason=exit_reason,
            place_broker_order=True,  # Routes through PaperBroker
        )

        if success:
            logger.info(
                f"[PAPER] Position closed: {position.instrument} | "
                f"Reason: {exit_reason} | P&L: ₹{pnl:,.0f}"
            )
            notify('EXIT_EXECUTED',
                title=f'[PAPER] Position Closed',
                instrument=position.instrument,
                metrics={
                    'Reason': exit_reason,
                    'P&L': f'₹{pnl:,.0f}',
                    'Exit': f'₹{exit_price:,.2f}',
                },
            )


@shared_task(name='apps.positions.tasks.alert_open_positions_pre_close')
@task_enabled_guard('alert-open-positions-pre-close')
def alert_open_positions_pre_close():
    """
    Sends a consolidated summary of all open positions to Telegram at 15:15.

    Scheduled: 15:15 Mon-Fri (10 min before close_trading_day fires at 15:25).

    Purpose:
    - Gives the trader a heads-up to review positions before EOD auto-close logic runs.
    - No positions are modified — purely informational.
    - In manual mode this acts as a prompt to decide: hold overnight or close now.
    """
    try:
        open_positions = Position.objects.filter(status='OPEN').select_related('account')

        if not open_positions.exists():
            logger.info("alert_open_positions_pre_close: no open positions, nothing to report")
            return {'success': True, 'positions': 0}

        from apps.core.models import TradingCoreConfig
        config = TradingCoreConfig.get_instance()

        now = timezone.now()

        _position_items = []
        for pos in open_positions:
            pnl = pos.unrealized_pnl or 0
            entry_val = pos.entry_value if pos.entry_value and pos.entry_value > 0 else (
                pos.entry_price * pos.quantity if pos.entry_price else None
            )
            pnl_pct = (pnl / entry_val * 100) if entry_val else None
            pnl_pct_str = f" ({pnl_pct:+.1f}%)" if pnl_pct is not None else ""
            sl_str = f"SL ₹{pos.stop_loss:,.0f}" if pos.stop_loss else "SL —"
            tgt_str = f"T ₹{pos.target:,.0f}" if pos.target else "T —"
            _position_items.append(
                f"{pos.label}: ₹{pnl:+,.0f}{pnl_pct_str} | {sl_str} | {tgt_str}"
            )

        notify('SYSTEM_STATUS',
            title='Pre-Close Position Summary',
            task='alert_open_positions_pre_close',
            metrics={'Positions': str(open_positions.count())},
            context=_position_items + ['Market closes in ~15 min. close_trading_day runs at 15:25.'],
            collapsible=True,
            priority='HIGH',
        )

        return {'success': True, 'positions': open_positions.count()}

    except Exception as e:
        logger.error(f"alert_open_positions_pre_close failed: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.positions.tasks.reconcile_positions_eod')
@task_enabled_guard('reconcile-positions-eod')
def reconcile_positions_eod():
    """
    End-of-day position reconciliation (15:45 Mon–Fri).

    Runs a fresh broker sync after market close, then compares what the DB
    thinks is open against actual broker state.  Reports three outcome types:

    1. Clean  — all positions closed, DB and broker agree. ✅
    2. Carry-forward — positions remain open (held overnight). Informational.
    3. Mismatch — DB says OPEN but broker reports nothing for that instrument.
                  This should never happen; requires immediate manual review. 🚨

    Does NOT auto-close any position — purely observational.
    """
    try:
        now = timezone.now()
        now_str = ist_datetime_str(now)

        # ── Step 1: Sync from brokers to get latest state ─────────────────────
        from apps.positions.services.position_sync import sync_positions_from_brokers
        sync_errors = []
        try:
            sync_result = sync_positions_from_brokers(include_history=False)
            sync_errors = sync_result.get('errors', []) or []
        except Exception as sync_err:
            sync_errors = [str(sync_err)]
            logger.error(f"reconcile_positions_eod: broker sync failed — {sync_err}")

        # ── Step 2: Check what remains open after sync ───────────────────────
        still_open = list(
            Position.objects.filter(status='OPEN').select_related('account')
        )

        # ── Step 3: Build report ──────────────────────────────────────────────
        if sync_errors:
            # Can't trust reconciliation if sync itself failed
            error_lines = [str(e)[:200] for e in sync_errors[:5]]
            notify('CRITICAL_ERROR',
                title='EOD Reconciliation: Sync Failed',
                task='reconcile_positions_eod',
                context=['Broker sync had errors — position state may be unreliable'] + error_lines,
                actions=['Manual broker check required'],
            )
            return {'success': False, 'sync_errors': sync_errors}

        if not still_open:
            # Clean day — all positions resolved
            notify('JOB_COMPLETED',
                title='EOD Reconciliation',
                task='reconcile_positions_eod',
                context=['All positions closed. Clean slate for tomorrow.'],
            )
            return {'success': True, 'open_count': 0, 'status': 'clean'}

        # Positions still open after sync — either legitimate carry-forward
        # or a mismatch.  Report them all so trader can verify.
        _carry_items = []
        for pos in still_open:
            pnl = pos.unrealized_pnl or 0
            entry_val = (
                pos.entry_value
                if pos.entry_value and pos.entry_value > 0
                else (pos.entry_price * pos.quantity if pos.entry_price else None)
            )
            pnl_pct = (pnl / entry_val * 100) if entry_val else None
            pnl_pct_str = f" ({pnl_pct:+.1f}%)" if pnl_pct is not None else ""
            _carry_items.append(f"{pos.label} | P&L ₹{pnl:+,.0f}{pnl_pct_str} | {pos.account}")

        notify('RISK_WARNING',
            title='EOD Reconciliation',
            task='reconcile_positions_eod',
            metrics={'Positions Open': str(len(still_open))},
            context=_carry_items,
            actions=['Carry-forward detected. Review positions before tomorrow\'s open.'],
        )

        return {
            'success': True,
            'open_count': len(still_open),
            'open_positions': [pos.label for pos in still_open],
            'status': 'positions_open',
        }

    except Exception as e:
        logger.error(f"reconcile_positions_eod failed: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}
