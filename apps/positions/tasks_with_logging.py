"""
Position Monitoring Celery Tasks - WITH COMPREHENSIVE LOGGING

Automated tasks for position monitoring and management:
- Monitor all active positions (every 10 seconds)
- Update position P&L (every 15 seconds)
- Check exit conditions (every 30 seconds)

This file contains the enhanced version with comprehensive logging.
Copy this over tasks.py after testing.
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

# Import TaskLogger
from apps.core.utils.task_logger import TaskLogger

logger = logging.getLogger(__name__)


@shared_task(name='apps.positions.tasks.monitor_all_positions', bind=True)
def monitor_all_positions(self):
    """
    Monitor all active positions for status updates

    Scheduled: Every 10 seconds during market hours

    Workflow:
    1. Get all active positions
    2. Update current prices from broker
    3. Update position P&L
    4. Log any significant changes
    """
    task_logger = TaskLogger(
        task_name='monitor_all_positions',
        task_category='position',
        task_id=self.request.id
    )

    try:
        # Get all active positions
        active_positions = Position.objects.filter(status='ACTIVE')

        if not active_positions.exists():
            task_logger.info('no_positions', "No active positions to monitor")
            return {'success': True, 'positions_monitored': 0}

        task_logger.start(f"Monitoring {active_positions.count()} active positions")

        monitored_count = 0
        errors = []

        for position in active_positions:
            try:
                # TODO: Fetch actual current price from broker API
                # For now, keeping existing current_price
                current_price = position.current_price

                task_logger.debug(
                    f'monitor_pos_{position.id}',
                    f"Monitoring position {position.id} - {position.instrument}",
                    context={
                        'position_id': position.id,
                        'instrument': position.instrument,
                        'current_price': float(current_price),
                        'entry_price': float(position.entry_price)
                    }
                )

                # Update position price and P&L
                update_position_price(position, current_price)

                monitored_count += 1

            except Exception as e:
                task_logger.error(
                    f'monitor_error_pos_{position.id}',
                    f"Error monitoring position {position.id}",
                    error=e,
                    context={'position_id': position.id}
                )
                errors.append(str(e))

        task_logger.success(
            f"Successfully monitored {monitored_count} positions",
            context={
                'positions_monitored': monitored_count,
                'errors_count': len(errors)
            }
        )

        return {
            'success': True,
            'positions_monitored': monitored_count,
            'errors': errors if errors else None,
            'timestamp': timezone.now().isoformat()
        }

    except Exception as e:
        task_logger.failure("Critical error in position monitoring", error=e)
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.positions.tasks.update_position_pnl', bind=True)
def update_position_pnl(self):
    """
    Update P&L for all active positions

    Scheduled: Every 15 seconds

    Workflow:
    1. Get all active positions
    2. Calculate unrealized P&L
    3. Update position records
    4. Send alerts for significant P&L changes
    """
    task_logger = TaskLogger(
        task_name='update_position_pnl',
        task_category='position',
        task_id=self.request.id
    )

    try:
        active_positions = Position.objects.filter(status='ACTIVE')

        if not active_positions.exists():
            task_logger.info('no_positions', "No active positions to update P&L")
            return {'success': True, 'positions_updated': 0}

        task_logger.start(f"Updating P&L for {active_positions.count()} positions")

        updated_count = 0
        alerts_sent = 0
        total_pnl = Decimal('0')

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

                total_pnl += pnl

                # Check if P&L crosses significant thresholds
                pnl_pct = (pnl / position.entry_value * Decimal('100')) if position.entry_value > 0 else Decimal('0')

                task_logger.debug(
                    f'pnl_update_pos_{position.id}',
                    f"P&L updated for position {position.id}",
                    context={
                        'position_id': position.id,
                        'instrument': position.instrument,
                        'pnl': float(pnl),
                        'pnl_pct': float(pnl_pct)
                    }
                )

                # Alert on large profit (>5%) or large loss (>3%)
                if pnl_pct > 5:
                    task_logger.info(
                        f'profit_alert_pos_{position.id}',
                        f"Profit alert triggered for position {position.id}",
                        context={
                            'position_id': position.id,
                            'pnl': float(pnl),
                            'pnl_pct': float(pnl_pct)
                        }
                    )
                    send_telegram_notification(
                        f"🎉 PROFIT ALERT\n\n"
                        f"Position #{position.id}\n"
                        f"Instrument: {position.instrument}\n"
                        f"P&L: ₹{pnl:,.0f} ({pnl_pct:.2f}%)",
                        notification_type='SUCCESS'
                    )
                    alerts_sent += 1
                elif pnl_pct < -3:
                    task_logger.warning(
                        f'loss_alert_pos_{position.id}',
                        f"Loss alert triggered for position {position.id}",
                        context={
                            'position_id': position.id,
                            'pnl': float(pnl),
                            'pnl_pct': float(pnl_pct)
                        }
                    )
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
                task_logger.error(
                    f'pnl_error_pos_{position.id}',
                    f"Error updating P&L for position {position.id}",
                    error=e,
                    context={'position_id': position.id}
                )

        task_logger.success(
            f"P&L updated for {updated_count} positions",
            context={
                'positions_updated': updated_count,
                'alerts_sent': alerts_sent,
                'total_unrealized_pnl': float(total_pnl)
            }
        )

        return {
            'success': True,
            'positions_updated': updated_count,
            'alerts_sent': alerts_sent,
            'total_pnl': float(total_pnl)
        }

    except Exception as e:
        task_logger.failure("Critical error in P&L update", error=e)
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.positions.tasks.check_exit_conditions', bind=True)
def check_exit_conditions(self):
    """
    Check exit conditions for all active positions

    Scheduled: Every 30 seconds

    Workflow:
    1. Get all active positions
    2. Check stop-loss and target conditions
    3. Execute exit if conditions met
    4. Send notifications
    """
    task_logger = TaskLogger(
        task_name='check_exit_conditions',
        task_category='position',
        task_id=self.request.id
    )

    try:
        active_positions = Position.objects.filter(status='ACTIVE')

        if not active_positions.exists():
            task_logger.info('no_positions', "No active positions to check for exit")
            return {'success': True, 'positions_checked': 0}

        task_logger.start(f"Checking exit conditions for {active_positions.count()} positions")

        checked_count = 0
        exits_executed = 0
        exit_details = []

        for position in active_positions:
            try:
                current_time = timezone.now()

                # Check exit conditions
                should_exit, reason, exit_type = should_exit_position(position, current_time)

                task_logger.debug(
                    f'exit_check_pos_{position.id}',
                    f"Exit check for position {position.id}: should_exit={should_exit}",
                    context={
                        'position_id': position.id,
                        'instrument': position.instrument,
                        'should_exit': should_exit,
                        'reason': reason,
                        'exit_type': exit_type
                    }
                )

                if should_exit:
                    task_logger.warning(
                        f'exit_triggered_pos_{position.id}',
                        f"Exit condition triggered for position {position.id}: {reason}",
                        context={
                            'position_id': position.id,
                            'reason': reason,
                            'exit_type': exit_type
                        }
                    )

                    # Close position
                    success, closed_position, message = close_position(
                        position=position,
                        exit_price=position.current_price,
                        exit_reason=reason
                    )

                    if success:
                        task_logger.info(
                            f'exit_success_pos_{position.id}',
                            f"Position {position.id} closed successfully",
                            context={
                                'position_id': position.id,
                                'realized_pnl': float(closed_position.realized_pnl),
                                'exit_reason': reason
                            }
                        )

                        send_telegram_notification(
                            f"✅ AUTO-EXIT EXECUTED\n\n"
                            f"Position: #{position.id}\n"
                            f"Instrument: {position.instrument}\n"
                            f"Reason: {reason}\n"
                            f"Exit Type: {exit_type}\n"
                            f"P&L: ₹{closed_position.realized_pnl:,.0f}",
                            notification_type='SUCCESS' if closed_position.realized_pnl > 0 else 'WARNING'
                        )
                        exits_executed += 1
                        exit_details.append({
                            'position_id': position.id,
                            'reason': reason,
                            'pnl': float(closed_position.realized_pnl)
                        })
                    else:
                        task_logger.error(
                            f'exit_failed_pos_{position.id}',
                            f"Failed to close position {position.id}",
                            context={
                                'position_id': position.id,
                                'error_message': message
                            }
                        )

                        send_telegram_notification(
                            f"❌ AUTO-EXIT FAILED\n\n"
                            f"Position: #{position.id}\n"
                            f"Reason: {reason}\n"
                            f"Error: {message}",
                            notification_type='ERROR'
                        )

                checked_count += 1

            except Exception as e:
                task_logger.error(
                    f'exit_check_error_pos_{position.id}',
                    f"Error checking exit for position {position.id}",
                    error=e,
                    context={'position_id': position.id}
                )

        task_logger.success(
            f"Exit conditions checked for {checked_count} positions, {exits_executed} exits executed",
            context={
                'positions_checked': checked_count,
                'exits_executed': exits_executed,
                'exit_details': exit_details
            }
        )

        return {
            'success': True,
            'positions_checked': checked_count,
            'exits_executed': exits_executed,
            'exit_details': exit_details
        }

    except Exception as e:
        task_logger.failure("Critical error in exit condition check", error=e)
        return {'success': False, 'message': str(e)}
