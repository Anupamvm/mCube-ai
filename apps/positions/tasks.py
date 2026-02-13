"""
Position Monitoring Celery Tasks

Single consolidated task that monitors all active positions:
- Updates P&L
- Sends threshold-crossing alerts
- Checks and executes exit conditions
"""

import logging
from decimal import Decimal
from celery import shared_task
from django.utils import timezone

from apps.positions.models import Position
from apps.positions.services.position_manager import close_position
from apps.positions.services.exit_manager import should_exit_position
from apps.alerts.services.telegram_client import send_telegram_notification
from apps.core.utils.decorators import task_enabled_guard

logger = logging.getLogger(__name__)


@shared_task(name='apps.positions.tasks.monitor_and_manage_positions')
@task_enabled_guard('monitor-and-manage-positions')
def monitor_and_manage_positions():
    """
    Consolidated position monitor: P&L update + exit condition check.

    Scheduled: Every minute during market hours (9 AM - 3:59 PM, Mon-Fri)

    For each active position:
    1. Calculate and save unrealized P&L
    2. Send Telegram alerts if P&L crosses thresholds (>5% profit, >3% loss)
    3. Check exit conditions (stop-loss, target, EOD)
    4. Execute exit if conditions met (respecting confirmation mode)
    """
    try:
        from apps.core.models import TradingCoreConfig
        config = TradingCoreConfig.get_instance()

        active_positions = Position.objects.filter(status='ACTIVE')

        if not active_positions.exists():
            return {'success': True, 'positions': 0}

        if config.is_simulated():
            return {'success': True, 'simulated': True, 'positions': active_positions.count()}

        mode_label = config.get_notification_level_display_short()
        updated_count = 0
        alerts_sent = 0
        exits_executed = 0
        confirmations_sent = 0
        errors = []

        for position in active_positions:
            try:
                # --- P&L Update ---
                if position.direction == 'LONG':
                    pnl = (position.current_price - position.entry_price) * position.quantity
                elif position.direction == 'SHORT':
                    pnl = (position.entry_price - position.current_price) * position.quantity
                else:  # NEUTRAL (strangle)
                    pnl = position.premium_collected  # Placeholder

                position.unrealized_pnl = pnl
                position.save(update_fields=['unrealized_pnl'])

                pnl_pct = (pnl / position.entry_value * Decimal('100')) if position.entry_value > 0 else Decimal('0')

                # --- P&L Alerts ---
                if pnl_pct > 5:
                    send_telegram_notification(
                        f"PROFIT ALERT\n\n"
                        f"Position #{position.id}\n"
                        f"Instrument: {position.instrument}\n"
                        f"P&L: {pnl:,.0f} ({pnl_pct:.2f}%)",
                        notification_type='SUCCESS'
                    )
                    alerts_sent += 1
                elif pnl_pct < -3:
                    send_telegram_notification(
                        f"LOSS ALERT\n\n"
                        f"Position #{position.id}\n"
                        f"Instrument: {position.instrument}\n"
                        f"P&L: {pnl:,.0f} ({pnl_pct:.2f}%)",
                        notification_type='WARNING'
                    )
                    alerts_sent += 1

                # --- Exit Condition Check ---
                current_time = timezone.now()
                should_exit, reason, exit_price = should_exit_position(position, current_time)

                if should_exit:
                    logger.warning(f"Exit condition triggered for position {position.id}: {reason}")

                    if config.requires_confirmation('EXIT'):
                        from apps.trading.services.trade_confirmation import get_confirmation_service
                        confirmation_service = get_confirmation_service()
                        success, result = confirmation_service.request_exit_confirmation(position, reason)

                        if success:
                            confirmations_sent += 1
                        else:
                            send_telegram_notification(
                                f"EXIT TRIGGERED ({mode_label})\n\n"
                                f"Position: #{position.id}\n"
                                f"Instrument: {position.instrument}\n"
                                f"Reason: {reason}\n"
                                f"Exit Price: {exit_price:,.2f}\n"
                                f"Current P&L: {position.unrealized_pnl:,.0f}\n\n"
                                f"Confirmation required",
                                notification_type='WARNING'
                            )
                            confirmations_sent += 1
                    else:
                        # AUTONOMOUS mode - auto-execute exit
                        success, message = close_position(
                            position=position,
                            exit_price=position.current_price,
                            exit_reason=reason
                        )

                        if success:
                            # Refresh position from DB to get realized_pnl
                            position.refresh_from_db()
                            send_telegram_notification(
                                f"AUTO-EXIT ({mode_label})\n\n"
                                f"Position: #{position.id}\n"
                                f"Instrument: {position.instrument}\n"
                                f"Reason: {reason}\n"
                                f"Exit Price: {exit_price:,.2f}\n"
                                f"P&L: {position.realized_pnl:,.0f}",
                                notification_type='SUCCESS' if position.realized_pnl > 0 else 'WARNING'
                            )
                            exits_executed += 1
                        else:
                            send_telegram_notification(
                                f"AUTO-EXIT FAILED\n\n"
                                f"Position: #{position.id}\n"
                                f"Reason: {reason}\n"
                                f"Error: {message}",
                                notification_type='ERROR'
                            )

                updated_count += 1

            except Exception as e:
                logger.error(f"Error processing position {position.id}: {e}", exc_info=True)
                errors.append(f"pos {position.id}: {e}")

        return {
            'success': True,
            'positions_updated': updated_count,
            'alerts_sent': alerts_sent,
            'exits_executed': exits_executed,
            'confirmations_sent': confirmations_sent,
            'errors': errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Critical error in position monitor: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}
