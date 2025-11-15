"""
Strategy Celery Tasks

Automated tasks for strategy evaluation and execution:
- Kotak Strangle entry evaluation (Mon/Tue 10:00 AM)
- Kotak Strangle exit evaluation (Thu/Fri 3:15 PM)
- ICICI Futures opportunity screening (every 30 min)
- Delta monitoring for strangles (every 5 min)
- Averaging checks for futures (every 10 min)
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

logger = logging.getLogger(__name__)


# =============================================================================
# KOTAK STRANGLE TASKS
# =============================================================================

@shared_task(name='apps.strategies.tasks.evaluate_kotak_strangle_entry')
def evaluate_kotak_strangle_entry():
    """
    Evaluate Kotak Strangle entry

    Scheduled: Monday & Tuesday @ 10:00 AM

    Workflow:
    1. Get Kotak account
    2. Check if entry is allowed (ONE POSITION RULE)
    3. Execute entry workflow
    4. Send notification with result
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Kotak Strangle Entry Evaluation")
    logger.info("=" * 80)

    try:
        # Get Kotak account
        kotak_account = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()

        if not kotak_account:
            logger.error("❌ No active Kotak account found")
            return {'success': False, 'message': 'No active Kotak account'}

        logger.info(f"Account: {kotak_account.account_name}")

        # Execute entry workflow
        result = execute_kotak_strangle_entry(kotak_account)

        # Send notification
        if result['success']:
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
            message = (
                f"ℹ️ KOTAK STRANGLE ENTRY SKIPPED\n\n"
                f"Reason: {result['message']}"
            )
            send_telegram_notification(message, notification_type='INFO')

        logger.info("=" * 80)
        return result

    except Exception as e:
        logger.error(f"Error in Kotak entry evaluation: {e}", exc_info=True)
        send_telegram_notification(
            f"❌ ERROR: Kotak entry evaluation failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.strategies.tasks.evaluate_kotak_strangle_exit')
def evaluate_kotak_strangle_exit(mandatory=False):
    """
    Evaluate Kotak Strangle exit

    Scheduled:
    - Thursday @ 3:15 PM (conditional exit if ≥50% profit)
    - Friday @ 3:15 PM (mandatory exit)

    Args:
        mandatory: If True, exit regardless of profit (Friday)
    """
    logger.info("=" * 80)
    logger.info(f"CELERY TASK: Kotak Strangle Exit Evaluation (Mandatory: {mandatory})")
    logger.info("=" * 80)

    try:
        # Get Kotak account
        kotak_account = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()

        if not kotak_account:
            logger.error("❌ No active Kotak account found")
            return {'success': False, 'message': 'No active Kotak account'}

        # Get active position
        position = Position.get_active_position(kotak_account)

        if not position:
            logger.info("ℹ️ No active position to evaluate for exit")
            return {'success': False, 'message': 'No active position'}

        logger.info(f"Evaluating position {position.id} for exit")

        # Check exit conditions
        current_time = timezone.now()
        should_exit, reason, exit_type = should_exit_position(position, current_time)

        if mandatory:
            # Friday - exit regardless
            should_exit = True
            reason = "Mandatory Friday EOD exit"
            exit_type = "EOD_MANDATORY"

        if should_exit:
            # Close position
            from apps.positions.services.position_manager import close_position

            success, closed_position, message = close_position(
                position=position,
                exit_price=position.current_price,  # TODO: Fetch actual current price
                exit_reason=reason
            )

            if success:
                send_telegram_notification(
                    f"✅ POSITION CLOSED\n\n"
                    f"Position: #{position.id}\n"
                    f"Reason: {reason}\n"
                    f"P&L: ₹{closed_position.realized_pnl:,.0f}",
                    notification_type='SUCCESS'
                )
                return {'success': True, 'message': f'Position closed: {reason}'}
            else:
                send_telegram_notification(
                    f"❌ POSITION CLOSE FAILED\n\n"
                    f"Position: #{position.id}\n"
                    f"Error: {message}",
                    notification_type='ERROR'
                )
                return {'success': False, 'message': message}
        else:
            logger.info(f"ℹ️ Exit conditions not met: {reason}")
            return {'success': False, 'message': f'Exit not required: {reason}'}

    except Exception as e:
        logger.error(f"Error in Kotak exit evaluation: {e}", exc_info=True)
        send_telegram_notification(
            f"❌ ERROR: Kotak exit evaluation failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.strategies.tasks.monitor_all_strangle_deltas')
def monitor_all_strangle_deltas():
    """
    Monitor delta for all active strangle positions

    Scheduled: Every 5 minutes during market hours

    Checks delta for all strangles and sends alerts if |delta| > 300
    """
    logger.info("CELERY TASK: Delta Monitoring for All Strangles")

    try:
        # Get all active strangle positions
        strangle_positions = Position.objects.filter(
            status='ACTIVE',
            strategy_type='WEEKLY_NIFTY_STRANGLE'
        )

        if not strangle_positions.exists():
            logger.info("ℹ️ No active strangle positions to monitor")
            return {'success': True, 'positions_monitored': 0}

        monitored_count = 0
        alerts_sent = 0

        for position in strangle_positions:
            try:
                delta_result = monitor_delta(position, delta_threshold=Decimal('300'))

                if delta_result['delta_exceeded']:
                    alerts_sent += 1

                monitored_count += 1

            except Exception as e:
                logger.error(f"Error monitoring delta for position {position.id}: {e}")

        logger.info(f"✅ Monitored {monitored_count} positions, {alerts_sent} alerts sent")

        return {
            'success': True,
            'positions_monitored': monitored_count,
            'alerts_sent': alerts_sent
        }

    except Exception as e:
        logger.error(f"Error in delta monitoring: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}


# =============================================================================
# ICICI FUTURES TASKS
# =============================================================================

@shared_task(name='apps.strategies.tasks.screen_futures_opportunities')
def screen_futures_opportunities_task():
    """
    Screen for futures trading opportunities

    Scheduled: Every 30 minutes during market hours (9 AM - 2:30 PM)

    Workflow:
    1. Screen top candidates
    2. Send top 3 candidates via Telegram
    3. Wait for manual approval to execute entry
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Futures Opportunity Screening")
    logger.info("=" * 80)

    try:
        # Screen for opportunities
        candidates = screen_futures_opportunities(
            min_volume_rank=50,
            min_score=65
        )

        if not candidates:
            logger.info("ℹ️ No qualified candidates found")
            return {'success': True, 'candidates_found': 0}

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

        logger.info(f"✅ Found {len(candidates)} candidates, sent top 3")

        return {
            'success': True,
            'candidates_found': len(candidates),
            'top_candidates': [c['symbol'] for c in top_candidates]
        }

    except Exception as e:
        logger.error(f"Error in futures screening: {e}", exc_info=True)
        send_telegram_notification(
            f"❌ ERROR: Futures screening failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.strategies.tasks.check_futures_averaging')
def check_futures_averaging():
    """
    Check if active futures positions need averaging

    Scheduled: Every 10 minutes during market hours

    Workflow:
    1. Get all active futures positions
    2. Check if averaging needed (1% loss trigger)
    3. Send recommendation via Telegram
    4. Wait for manual approval to execute averaging
    """
    logger.info("CELERY TASK: Futures Averaging Check")

    try:
        # Get all active futures positions
        futures_positions = Position.objects.filter(
            status='ACTIVE',
            strategy_type='LLM_VALIDATED_FUTURES'
        )

        if not futures_positions.exists():
            logger.info("ℹ️ No active futures positions to check")
            return {'success': True, 'positions_checked': 0}

        checked_count = 0
        averaging_recommendations = 0

        for position in futures_positions:
            try:
                # Get current price
                # TODO: Fetch actual current price from broker
                current_price = position.current_price

                # Check if averaging needed
                recommendation = get_averaging_recommendation(position, current_price)

                if recommendation['should_average']:
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
                logger.error(f"Error checking averaging for position {position.id}: {e}")

        logger.info(
            f"✅ Checked {checked_count} positions, "
            f"{averaging_recommendations} averaging recommendations"
        )

        return {
            'success': True,
            'positions_checked': checked_count,
            'averaging_recommendations': averaging_recommendations
        }

    except Exception as e:
        logger.error(f"Error in averaging check: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}
