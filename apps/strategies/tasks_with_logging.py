"""
Strategy Celery Tasks - WITH COMPREHENSIVE LOGGING

Automated tasks for strategy evaluation and execution:
- Kotak Strangle entry evaluation (Mon/Tue 10:00 AM)
- Kotak Strangle exit evaluation (Thu/Fri 3:15 PM)
- ICICI Futures opportunity screening (every 30 min)
- Delta monitoring for strangles (every 5 min)
- Averaging checks for futures (every 10 min)

This file contains the enhanced version with comprehensive logging.
Copy this over tasks.py after testing.
"""

import logging
from decimal import Decimal
from celery import shared_task
from django.utils import timezone

from apps.accounts.models import BrokerAccount
from apps.positions.models import Position
from apps.strategies.strategies.kotak_strangle import execute_kotak_strangle_entry
from apps.strategies.strategies.icici_futures import (
    screen_futures_opportunities,
    execute_icici_futures_entry
)
from apps.positions.services.delta_monitor import monitor_delta
from apps.positions.services.averaging_manager import (
    should_average_position,
    get_averaging_recommendation
)
from apps.positions.services.exit_manager import should_exit_position
from apps.alerts.services.telegram_client import send_telegram_notification

# Import TaskLogger
from apps.core.utils.task_logger import TaskLogger

logger = logging.getLogger(__name__)


# =============================================================================
# KOTAK STRANGLE TASKS
# =============================================================================

@shared_task(name='apps.strategies.tasks.evaluate_kotak_strangle_entry', bind=True)
def evaluate_kotak_strangle_entry(self):
    """
    Evaluate Kotak Strangle entry

    Scheduled: Monday & Tuesday @ 10:00 AM

    Workflow:
    1. Get Kotak account
    2. Check if entry is allowed (ONE POSITION RULE)
    3. Execute entry workflow
    4. Send notification with result
    """
    task_logger = TaskLogger(
        task_name='evaluate_kotak_strangle_entry',
        task_category='strategy',
        task_id=self.request.id
    )

    task_logger.start("Evaluating Kotak Strangle entry conditions")

    try:
        # Get Kotak account
        task_logger.step('get_account', "Fetching active Kotak account")
        kotak_account = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()

        if not kotak_account:
            task_logger.error('no_account', "No active Kotak account found")
            return {'success': False, 'message': 'No active Kotak account'}

        task_logger.info('account_found', f"Found account: {kotak_account.account_name}",
                        context={'account_id': kotak_account.id,
                                'account_name': kotak_account.account_name})

        # Execute entry workflow
        task_logger.step('execute_entry', "Executing strangle entry workflow")
        result = execute_kotak_strangle_entry(kotak_account)

        # Send notification
        if result['success']:
            task_logger.success("Kotak Strangle entry executed successfully", context={
                'position_id': result['position'].id,
                'call_strike': result['details']['strikes']['call_strike'],
                'put_strike': result['details']['strikes']['put_strike'],
                'premium_collected': float(result['details']['premium_collected']),
                'margin_used': float(result['details']['margin_used'])
            })

            message = (
                f"✅ KOTAK STRANGLE ENTRY\n\n"
                f"Position Created: #{result['position'].id}\n"
                f"Call Strike: {result['details']['strikes']['call_strike']}\n"
                f"Put Strike: {result['details']['strikes']['put_strike']}\n"
                f"Premium Collected: ₹{result['details']['premium_collected']:,.0f}\n"
                f"Margin Used: ₹{result['details']['margin_used']:,.0f}"
            )
            send_telegram_notification(message, notification_type='SUCCESS')
        else:
            task_logger.info('entry_skipped', f"Entry skipped: {result['message']}",
                           context={'skip_reason': result['message']})

            message = (
                f"ℹ️ KOTAK STRANGLE ENTRY SKIPPED\n\n"
                f"Reason: {result['message']}"
            )
            send_telegram_notification(message, notification_type='INFO')

        return result

    except Exception as e:
        task_logger.failure("Error in Kotak entry evaluation", error=e)
        send_telegram_notification(
            f"❌ ERROR: Kotak entry evaluation failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.strategies.tasks.evaluate_kotak_strangle_exit', bind=True)
def evaluate_kotak_strangle_exit(self, profit_threshold=10000, mandatory=False):
    """
    Evaluate Kotak Strangle exit

    Scheduled: Daily @ 3:15 PM (Mon-Fri)

    Exit Logic:
    - Exit if unrealized P&L >= profit_threshold (e.g., ₹10,000)
    - Exit if Friday (mandatory EOD exit before expiry)
    - Exit if stop-loss hit (checked separately every 30s)
    - Only runs if open positions exist

    Args:
        profit_threshold: Minimum profit required to trigger exit (default: ₹10,000)
        mandatory: If True, exit regardless of profit (Friday EOD)
    """
    task_logger = TaskLogger(
        task_name='evaluate_kotak_strangle_exit',
        task_category='strategy',
        task_id=self.request.id
    )

    task_logger.start(f"Evaluating Kotak Strangle exit (profit threshold: ₹{profit_threshold:,.0f}, mandatory: {mandatory})")

    try:
        # Get Kotak account
        kotak_account = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()

        if not kotak_account:
            task_logger.error('no_account', "No active Kotak account found")
            return {'success': False, 'message': 'No active Kotak account'}

        # Get active position
        position = Position.get_active_position(kotak_account)

        if not position:
            task_logger.info('no_position', "No active position to evaluate for exit")
            return {'success': False, 'message': 'No active position'}

        task_logger.step('check_position', f"Evaluating position {position.id} for exit", context={
            'position_id': position.id,
            'instrument': position.instrument,
            'unrealized_pnl': float(position.unrealized_pnl)
        })

        # Check exit conditions
        current_time = timezone.now()
        should_exit, reason, exit_type = should_exit_position(position, current_time)

        # Check if Friday (mandatory exit)
        if current_time.weekday() == 4:  # Friday
            mandatory = True
            task_logger.info('friday_exit', "Friday detected - mandatory exit enabled")

        # Check profit threshold
        if position.unrealized_pnl >= Decimal(str(profit_threshold)):
            should_exit = True
            reason = f"Profit target reached: ₹{position.unrealized_pnl:,.0f} >= ₹{profit_threshold:,.0f}"
            exit_type = "PROFIT_TARGET"
            task_logger.info('profit_threshold', f"Profit threshold reached: ₹{position.unrealized_pnl:,.0f}",
                           context={'current_pnl': float(position.unrealized_pnl),
                                  'threshold': profit_threshold})

        if mandatory:
            # Friday - exit regardless
            should_exit = True
            reason = "Mandatory Friday EOD exit (before weekly expiry)"
            exit_type = "EOD_MANDATORY"
            task_logger.warning('mandatory_exit', "Mandatory exit triggered")

        if should_exit:
            task_logger.step('closing_position', f"Closing position {position.id}: {reason}")

            # Close position
            from apps.positions.services.position_manager import close_position

            success, closed_position, message = close_position(
                position=position,
                exit_price=position.current_price,  # TODO: Fetch actual current price
                exit_reason=reason
            )

            if success:
                task_logger.success(f"Position {position.id} closed successfully", context={
                    'position_id': position.id,
                    'exit_reason': reason,
                    'realized_pnl': float(closed_position.realized_pnl)
                })

                send_telegram_notification(
                    f"✅ POSITION CLOSED\n\n"
                    f"Position: #{position.id}\n"
                    f"Reason: {reason}\n"
                    f"P&L: ₹{closed_position.realized_pnl:,.0f}",
                    notification_type='SUCCESS'
                )
                return {'success': True, 'message': f'Position closed: {reason}'}
            else:
                task_logger.error('close_failed', f"Failed to close position {position.id}",
                                context={'position_id': position.id, 'error': message})

                send_telegram_notification(
                    f"❌ POSITION CLOSE FAILED\n\n"
                    f"Position: #{position.id}\n"
                    f"Error: {message}",
                    notification_type='ERROR'
                )
                return {'success': False, 'message': message}
        else:
            task_logger.info('no_exit_needed', f"Exit not required: {reason}")
            return {'success': False, 'message': f'Exit not required: {reason}'}

    except Exception as e:
        task_logger.failure("Error in Kotak exit evaluation", error=e)
        send_telegram_notification(
            f"❌ ERROR: Kotak exit evaluation failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.strategies.tasks.monitor_all_strangle_deltas', bind=True)
def monitor_all_strangle_deltas(self, delta_threshold=300):
    """
    Monitor delta for all active strangle positions

    Scheduled: Every 15 minutes during market hours (configurable via UI)

    Checks delta for all strangles and sends alerts if |delta| > delta_threshold

    Args:
        delta_threshold: Alert if |Net Delta| exceeds this value (default: 300)
    """
    task_logger = TaskLogger(
        task_name='monitor_all_strangle_deltas',
        task_category='strategy',
        task_id=self.request.id
    )

    task_logger.start(f"Monitoring delta for all strangles (threshold: {delta_threshold})")

    try:
        # Get all active strangle positions
        strangle_positions = Position.objects.filter(
            status='ACTIVE',
            strategy_type='WEEKLY_NIFTY_STRANGLE'
        )

        if not strangle_positions.exists():
            task_logger.info('no_strangles', "No active strangle positions to monitor")
            return {'success': True, 'positions_monitored': 0}

        task_logger.step('monitoring', f"Monitoring delta for {strangle_positions.count()} strangles")

        monitored_count = 0
        alerts_sent = 0

        for position in strangle_positions:
            try:
                delta_result = monitor_delta(position, delta_threshold=Decimal(str(delta_threshold)))

                task_logger.debug(f'delta_pos_{position.id}',
                                f"Delta monitored for position {position.id}",
                                context={
                                    'position_id': position.id,
                                    'current_delta': float(position.current_delta),
                                    'delta_exceeded': delta_result['delta_exceeded']
                                })

                if delta_result['delta_exceeded']:
                    task_logger.warning(f'delta_alert_pos_{position.id}',
                                      f"Delta alert for position {position.id}",
                                      context={
                                          'position_id': position.id,
                                          'current_delta': float(position.current_delta),
                                          'threshold': delta_threshold
                                      })
                    alerts_sent += 1

                monitored_count += 1

            except Exception as e:
                task_logger.error(f'delta_error_pos_{position.id}',
                                f"Error monitoring delta for position {position.id}",
                                error=e,
                                context={'position_id': position.id})

        task_logger.success(f"Delta monitoring complete", context={
            'positions_monitored': monitored_count,
            'alerts_sent': alerts_sent
        })

        return {
            'success': True,
            'positions_monitored': monitored_count,
            'alerts_sent': alerts_sent
        }

    except Exception as e:
        task_logger.failure("Error in delta monitoring", error=e)
        return {'success': False, 'message': str(e)}


# =============================================================================
# ICICI FUTURES TASKS
# =============================================================================

@shared_task(name='apps.strategies.tasks.screen_futures_opportunities', bind=True)
def screen_futures_opportunities_task(self):
    """
    Screen for futures trading opportunities

    Scheduled: Every 30 minutes during market hours (9 AM - 2:30 PM)

    Workflow:
    1. Screen top candidates
    2. Send top 3 candidates via Telegram
    3. Wait for manual approval to execute entry
    """
    task_logger = TaskLogger(
        task_name='screen_futures_opportunities',
        task_category='strategy',
        task_id=self.request.id
    )

    task_logger.start("Screening for futures trading opportunities")

    try:
        # Screen for opportunities
        task_logger.step('screening', "Running futures screening algorithm")
        candidates = screen_futures_opportunities(
            min_volume_rank=50,
            min_score=65
        )

        if not candidates:
            task_logger.info('no_candidates', "No qualified candidates found")
            return {'success': True, 'candidates_found': 0}

        task_logger.info('screening_complete', f"Found {len(candidates)} qualified candidates",
                        context={'total_candidates': len(candidates)})

        # Send top 3 candidates via Telegram
        top_candidates = candidates[:3]

        message = "📊 FUTURES OPPORTUNITIES\n\n"

        for i, candidate in enumerate(top_candidates, 1):
            message += (
                f"{i}. {candidate['symbol']} - {candidate['direction']}\n"
                f"   Score: {candidate['composite_score']}/100\n"
                f"   OI: {candidate['oi_analysis']['buildup_type']}\n"
                f"   Sector: {candidate['sector_analysis']['verdict']}\n\n"
            )

        message += "\nℹ️ Manual approval required to execute entry"

        send_telegram_notification(message, notification_type='INFO')

        task_logger.success(f"Futures screening complete - sent top 3 to Telegram", context={
            'total_found': len(candidates),
            'top_3_symbols': [c['symbol'] for c in top_candidates]
        })

        return {
            'success': True,
            'candidates_found': len(candidates),
            'top_candidates': [c['symbol'] for c in top_candidates]
        }

    except Exception as e:
        task_logger.failure("Error in futures screening", error=e)
        send_telegram_notification(
            f"❌ ERROR: Futures screening failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.strategies.tasks.check_futures_averaging', bind=True)
def check_futures_averaging(self):
    """
    Check if active futures positions need averaging

    Scheduled: Every 10 minutes during market hours

    Workflow:
    1. Get all active futures positions
    2. Check if averaging needed (1% loss trigger)
    3. Send recommendation via Telegram
    4. Wait for manual approval to execute averaging
    """
    task_logger = TaskLogger(
        task_name='check_futures_averaging',
        task_category='strategy',
        task_id=self.request.id
    )

    task_logger.start("Checking futures positions for averaging opportunities")

    try:
        # Get all active futures positions
        futures_positions = Position.objects.filter(
            status='ACTIVE',
            strategy_type='LLM_VALIDATED_FUTURES'
        )

        if not futures_positions.exists():
            task_logger.info('no_futures', "No active futures positions to check")
            return {'success': True, 'positions_checked': 0}

        task_logger.step('checking', f"Checking {futures_positions.count()} futures positions")

        checked_count = 0
        averaging_recommendations = 0

        for position in futures_positions:
            try:
                # Get current price
                # TODO: Fetch actual current price from broker
                current_price = position.current_price

                # Check if averaging needed
                recommendation = get_averaging_recommendation(position, current_price)

                task_logger.debug(f'avg_check_pos_{position.id}',
                                f"Averaging check for position {position.id}",
                                context={
                                    'position_id': position.id,
                                    'should_average': recommendation['should_average']
                                })

                if recommendation['should_average']:
                    task_logger.warning(f'avg_recommended_pos_{position.id}',
                                      f"Averaging recommended for position {position.id}",
                                      context={
                                          'position_id': position.id,
                                          'loss_pct': recommendation['details']['loss_pct']
                                      })

                    # Send recommendation
                    preview = recommendation['preview']

                    message = (
                        f"⚠️ AVERAGING RECOMMENDATION\n\n"
                        f"Position: #{position.id}\n"
                        f"Symbol: {position.instrument}\n"
                        f"Direction: {position.direction}\n\n"
                        f"Current Entry: ₹{preview['current_entry']:,.2f}\n"
                        f"Current Price: ₹{preview['averaging_price']:,.2f}\n"
                        f"Loss: {recommendation['details']['loss_pct']:.2f}%\n\n"
                        f"RECOMMENDATION:\n"
                        f"Add {preview['quantity_to_add']} quantity\n"
                        f"New Avg Entry: ₹{preview['new_average_entry']:,.2f}\n"
                        f"New Stop-Loss: ₹{preview['new_stop_loss']:,.2f}\n"
                        f"Additional Margin: ₹{preview['additional_margin_needed']:,.0f}\n\n"
                        f"Averaging Count: {preview['averaging_count_after']}/3\n\n"
                        f"ℹ️ Manual approval required"
                    )

                    send_telegram_notification(message, notification_type='WARNING')
                    averaging_recommendations += 1

                checked_count += 1

            except Exception as e:
                task_logger.error(f'avg_error_pos_{position.id}',
                                f"Error checking averaging for position {position.id}",
                                error=e,
                                context={'position_id': position.id})

        task_logger.success(f"Averaging check complete", context={
            'positions_checked': checked_count,
            'averaging_recommendations': averaging_recommendations
        })

        return {
            'success': True,
            'positions_checked': checked_count,
            'averaging_recommendations': averaging_recommendations
        }

    except Exception as e:
        task_logger.failure("Error in averaging check", error=e)
        return {'success': False, 'message': str(e)}
