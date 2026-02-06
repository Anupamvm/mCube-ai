"""
Position Monitoring Celery Tasks

Automated tasks for position monitoring and management:
- Monitor all active positions (every 10 seconds)
- Update position P&L (every 15 seconds)
- Check exit conditions (every 30 seconds)
"""

import logging
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from datetime import datetime

from apps.positions.models import Position
from apps.positions.services.position_manager import update_position_price, close_position
from apps.positions.services.exit_manager import should_exit_position, check_exit_conditions
from apps.alerts.services.telegram_client import send_telegram_notification
from apps.core.utils.decorators import task_enabled_guard

logger = logging.getLogger(__name__)


@shared_task(name='apps.positions.tasks.monitor_all_positions')
@task_enabled_guard('monitor-all-positions')
def monitor_all_positions():
    """
    Monitor all active positions for status updates

    Scheduled: Every 10 seconds during market hours

    Workflow:
    1. Get all active positions
    2. Update current prices from broker
    3. Update position P&L
    4. Log any significant changes
    """
    try:
        # Get all active positions
        active_positions = Position.objects.filter(status='ACTIVE')

        if not active_positions.exists():
            return {'success': True, 'positions_monitored': 0}

        monitored_count = 0

        for position in active_positions:
            try:
                # TODO: Fetch actual current price from broker API
                # For now, keeping existing current_price
                current_price = position.current_price

                # Update position price and P&L
                update_position_price(position, current_price)

                monitored_count += 1

            except Exception as e:
                logger.error(f"Error monitoring position {position.id}: {e}")

        return {
            'success': True,
            'positions_monitored': monitored_count,
            'timestamp': timezone.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in position monitoring: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.positions.tasks.update_position_pnl')
@task_enabled_guard('update-position-pnl')
def update_position_pnl():
    """
    Update P&L for all active positions

    Scheduled: Every 15 seconds

    Workflow:
    1. Get all active positions
    2. Calculate unrealized P&L
    3. Update position records
    4. Send alerts for significant P&L changes
    """
    try:
        active_positions = Position.objects.filter(status='ACTIVE')

        if not active_positions.exists():
            return {'success': True, 'positions_updated': 0}

        updated_count = 0
        alerts_sent = 0

        for position in active_positions:
            try:
                # Calculate P&L
                if position.direction == 'LONG':
                    pnl = (position.current_price - position.entry_price) * position.quantity
                elif position.direction == 'SHORT':
                    pnl = (position.entry_price - position.current_price) * position.quantity
                else:  # NEUTRAL (strangle)
                    # For strangle, P&L is premium collected minus current premium value
                    # TODO: Fetch actual current premium from broker
                    pnl = position.premium_collected  # Placeholder

                # Update unrealized P&L
                position.unrealized_pnl = pnl
                position.save(update_fields=['unrealized_pnl'])

                # Check if P&L crosses significant thresholds
                pnl_pct = (pnl / position.entry_value * Decimal('100')) if position.entry_value > 0 else Decimal('0')

                # Alert on large profit (>5%) or large loss (>3%)
                if pnl_pct > 5:
                    send_telegram_notification(
                        f"🎉 PROFIT ALERT\n\n"
                        f"Position #{position.id}\n"
                        f"Instrument: {position.instrument}\n"
                        f"P&L: ₹{pnl:,.0f} ({pnl_pct:.2f}%)",
                        notification_type='SUCCESS'
                    )
                    alerts_sent += 1
                elif pnl_pct < -3:
                    send_telegram_notification(
                        f"⚠️ LOSS ALERT\n\n"
                        f"Position #{position.id}\n"
                        f"Instrument: {position.instrument}\n"
                        f"P&L: ₹{pnl:,.0f} ({pnl_pct:.2f}%)",
                        notification_type='WARNING'
                    )
                    alerts_sent += 1

                updated_count += 1

            except Exception as e:
                logger.error(f"Error updating P&L for position {position.id}: {e}")

        return {
            'success': True,
            'positions_updated': updated_count,
            'alerts_sent': alerts_sent
        }

    except Exception as e:
        logger.error(f"Error in P&L update: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.positions.tasks.check_exit_conditions')
@task_enabled_guard('check-exit-conditions')
def check_exit_conditions():
    """
    Check exit conditions for all active positions

    Scheduled: Every 30 seconds

    Workflow:
    1. Get all active positions
    2. Check stop-loss and target conditions
    3. Based on notification level:
       - FULL_CONTROL: Send confirmation request
       - SUPERVISED: Send confirmation for exits
       - AUTONOMOUS: Auto-execute exit
    """
    try:
        # Get core config for confirmation settings
        from apps.core.models import TradingCoreConfig
        config = TradingCoreConfig.get_instance()

        active_positions = Position.objects.filter(status='ACTIVE')

        if not active_positions.exists():
            return {'success': True, 'positions_checked': 0}

        # Check for simulated mode
        if config.is_simulated():
            return {'success': True, 'simulated': True, 'positions': active_positions.count()}

        mode_label = config.get_notification_level_display_short()
        checked_count = 0
        exits_executed = 0
        confirmations_sent = 0

        for position in active_positions:
            try:
                current_time = timezone.now()

                # Check exit conditions
                should_exit, reason, exit_type = should_exit_position(position, current_time)

                if should_exit:
                    logger.warning(f"⚠️ Exit condition triggered for position {position.id}: {reason}")

                    # Check if confirmation required for exits
                    if config.requires_confirmation('EXIT'):
                        # Send confirmation request
                        from apps.trading.services.trade_confirmation import get_confirmation_service
                        confirmation_service = get_confirmation_service()
                        success, result = confirmation_service.request_exit_confirmation(position, reason)

                        if success:
                            confirmations_sent += 1
                        else:
                            # Fallback to notification
                            send_telegram_notification(
                                f"⚠️ EXIT TRIGGERED ({mode_label})\n\n"
                                f"Position: #{position.id}\n"
                                f"Instrument: {position.instrument}\n"
                                f"Reason: {reason}\n"
                                f"Exit Type: {exit_type}\n"
                                f"Current P&L: ₹{position.unrealized_pnl:,.0f}\n\n"
                                f"ℹ️ Confirmation required",
                                notification_type='WARNING'
                            )
                            confirmations_sent += 1
                    else:
                        # AUTONOMOUS mode - auto-execute exit
                        success, closed_position, message = close_position(
                            position=position,
                            exit_price=position.current_price,
                            exit_reason=reason
                        )

                        if success:
                            send_telegram_notification(
                                f"🤖 AUTO-EXIT ({mode_label})\n\n"
                                f"Position: #{position.id}\n"
                                f"Instrument: {position.instrument}\n"
                                f"Reason: {reason}\n"
                                f"Exit Type: {exit_type}\n"
                                f"P&L: ₹{closed_position.realized_pnl:,.0f}",
                                notification_type='SUCCESS' if closed_position.realized_pnl > 0 else 'WARNING'
                            )
                            exits_executed += 1
                        else:
                            send_telegram_notification(
                                f"❌ AUTO-EXIT FAILED\n\n"
                                f"Position: #{position.id}\n"
                                f"Reason: {reason}\n"
                                f"Error: {message}",
                                notification_type='ERROR'
                            )

                checked_count += 1

            except Exception as e:
                logger.error(f"Error checking exit for position {position.id}: {e}")

        return {
            'success': True,
            'positions_checked': checked_count,
            'exits_executed': exits_executed,
            'confirmations_sent': confirmations_sent,
            'mode': config.notification_level
        }

    except Exception as e:
        logger.error(f"Error in exit condition check: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}
