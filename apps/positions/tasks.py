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

logger = logging.getLogger(__name__)


@shared_task(name='apps.positions.tasks.monitor_and_manage_positions')
@task_enabled_guard('monitor-and-manage-positions')
def monitor_and_manage_positions():
    """
    Monitors all active positions: updates P&L, checks exit conditions.

    Scheduled: Every minute during market hours (9:00 AM – 3:59 PM, Mon–Fri)

    Behaviour depends on notification_level in TradingCoreConfig:

    FULL_CONTROL / SUPERVISED  →  "Manual mode"
      • Edits the live daily monitoring dashboard (single Telegram message)
      • On exit trigger: sends suggestion with [✅ Close Now] [⏸️ Hold] keyboard
      • Does NOT execute the exit — waits for user response

    AUTONOMOUS
      • Edits the live daily monitoring dashboard
      • On exit trigger: auto-executes immediately, sends result notification
    """
    try:
        from apps.core.models import TradingCoreConfig
        config = TradingCoreConfig.get_instance()

        # ── Sync latest positions + LTPs from all broker accounts ─────────────
        # This ensures: (a) any new positions are in DB, (b) current_price is
        # fresh for P&L calculations — runs before every monitor cycle.
        try:
            from apps.positions.services.position_sync import sync_positions_from_brokers
            sync_positions_from_brokers(include_history=False)
        except Exception as sync_err:
            logger.warning(f"Pre-monitor broker sync failed (continuing with DB state): {sync_err}")

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

                # ── 2. MonitorLog (timestamped) ───────────────────────────────
                MonitorLog.objects.create(
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
                )

                # ── 3. Per-position dashboard + SR engine (SL/target update) ──
                dashboard, _ = get_or_create_dashboard(position, today)

                # Apply SR-based SL tightening and target initialization.
                # Must run before near-SL warning and exit check so both
                # see the latest structural SL/target values.
                # Also handles new/broker-synced positions that arrive without SL.
                sr_eval = apply_sl_and_target(position, dashboard, now)

                add_snapshot(dashboard, position.current_price, pnl, pnl_pct, now)

                # Collect for consolidated Telegram message
                lot_size = position.lot_size or 1
                lots = position.quantity // lot_size if lot_size > 1 else position.quantity
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
                if (
                    position.stop_loss
                    and position.current_price
                    and not position.is_stop_loss_hit()
                ):
                    price = float(position.current_price)
                    sl = float(position.stop_loss)
                    buffer_pct = abs(price - sl) / price * 100  # % of current price
                    if buffer_pct < 1.0:  # within 1% of SL
                        if should_send_exit_suggestion(dashboard, 'NEAR_SL', cooldown_minutes=15):
                            warn_msg = (
                                f"🟡 <b>NEAR SL WARNING</b>\n\n"
                                f"<b>{position.label}</b>\n"
                                f"Current: ₹{price:,.2f}\n"
                                f"SL:      ₹{sl:,.2f}\n"
                                f"Buffer: {buffer_pct:.2f}% from SL\n\n"
                                f"<i>Position approaching stop-loss — monitor closely.</i>"
                            )
                            send_telegram_notification(warn_msg, notification_type='WARNING')
                            record_exit_suggestion(dashboard, 'NEAR_SL')

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
                            # Same exit reason within cooldown — log but don't spam
                            MonitorLog.objects.create(
                                position=position,
                                check_type='EXIT_SUGGESTION',
                                result='SKIPPED_DUPLICATE',
                                message=(
                                    f"[{ist_datetime_str(now)}] "
                                    f"Exit condition ({reason}) still active — "
                                    f"suggestion already pending, skipping duplicate."
                                ),
                                price_at_check=position.current_price,
                                pnl_at_check=pnl,
                                action_taken='DUPLICATE_SKIPPED',
                            )
                            logger.debug(
                                f"Exit suggestion deduped for pos #{position.id} / {reason}"
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
                        )

                        if success:
                            position.refresh_from_db()
                            pnl_result = position.realized_pnl
                            send_telegram_notification(
                                f"✅ AUTO-EXIT ({mode_label})\n\n"
                                f"<b>{position.label}</b> | #{position.id}\n"
                                f"Reason: {reason.replace('_', ' ')}\n"
                                f"Exit: ₹{exit_price:,.2f}\n"
                                f"P&L: {'+'if pnl_result>=0 else ''}₹{pnl_result:,.0f}",
                                notification_type=(
                                    'SUCCESS' if pnl_result >= 0 else 'WARNING'
                                ),
                            )
                            exits_executed += 1
                        else:
                            send_telegram_notification(
                                f"🚨 AUTO-EXIT FAILED\n\n"
                                f"Position #{position.id} | {position.label}\n"
                                f"Reason: {reason}\n"
                                f"Error: {message}",
                                notification_type='ERROR',
                            )

                updated_count += 1

            except Exception as e:
                logger.error(
                    f"Error processing position #{position.id}: {e}", exc_info=True
                )
                errors.append(f"pos {position.id}: {e}")

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

        return {
            'success': True,
            'positions_updated': updated_count,
            'exits_executed': exits_executed,
            'suggestions_sent': suggestions_sent,
            'errors': errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Critical error in position monitor: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}
