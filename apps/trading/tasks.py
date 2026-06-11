"""
Trading Celery Tasks

Tasks for trade confirmation timeout monitoring.
"""

import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

from apps.core.utils.decorators import task_enabled_guard
from apps.core.utils.task_logger import TaskLogger
from apps.alerts.services.telegram_client import send_telegram_notification
from apps.alerts.services.notification_service import notify

# Minutes after first revalidation before a CRITICAL escalation alert is sent.
# Escalation fires once per suggestion — field suggestion.escalated guards repeats.
_ESCALATION_MINUTES = 15

logger = logging.getLogger(__name__)


@shared_task(name='apps.trading.tasks.check_confirmation_timeouts', bind=True)
@task_enabled_guard('check-confirmation-timeouts')
def check_confirmation_timeouts(self):
    """
    Check for pending trade confirmations that have exceeded timeout.

    Scheduled: Every 1 minute during market hours (9:15 AM - 3:30 PM)

    Workflow:
    1. Find suggestions with status='PENDING_CONFIRMATION'
    2. Check if confirmation_requested_at + timeout exceeded
    3. If not yet revalidated, call revalidate_after_timeout()
    4. Mark revalidation_sent=True to avoid duplicate messages
    """
    task_logger = TaskLogger(
        task_name='check_confirmation_timeouts',
        task_category='transaction',
        task_id=self.request.id
    )

    task_logger.start("Checking for confirmation timeouts")

    try:
        from apps.trading.models import TradeSuggestion
        from apps.trading.services.trade_confirmation import get_confirmation_service

        now = timezone.now()

        # Find pending confirmations that haven't been revalidated
        pending = TradeSuggestion.objects.filter(
            status='PENDING_CONFIRMATION',
            confirmation_requested_at__isnull=False,
            revalidation_sent=False
        )

        if not pending.exists():
            task_logger.info('no_pending', "No pending confirmations to check")
            return {'success': True, 'checked': 0, 'timed_out': 0}

        confirmation_service = get_confirmation_service()
        checked = 0
        timed_out = 0

        for suggestion in pending:
            checked += 1

            # Calculate timeout threshold
            timeout_minutes = suggestion.confirmation_timeout_minutes or 5
            timeout_threshold = suggestion.confirmation_requested_at + timedelta(minutes=timeout_minutes)

            if now > timeout_threshold:
                # Timeout exceeded - revalidate
                task_logger.info(
                    'timeout',
                    f"Suggestion {suggestion.id} timed out after {timeout_minutes} minutes"
                )

                try:
                    confirmation_service.revalidate_after_timeout(suggestion)
                    timed_out += 1
                except Exception as e:
                    task_logger.warning(
                        'revalidate_error',
                        f"Error revalidating suggestion {suggestion.id}: {e}"
                    )

            # ── Escalation: CRITICAL alert if pending for too long ────────────
            # Fires once per suggestion (escalated flag prevents re-spamming).
            # Condition: revalidation already sent AND still pending after
            # _ESCALATION_MINUTES since confirmation was first requested.
            if (
                suggestion.revalidation_sent
                and not suggestion.escalated
            ):
                escalation_threshold = (
                    suggestion.confirmation_requested_at
                    + timedelta(minutes=_ESCALATION_MINUTES)
                )
                if now > escalation_threshold:
                    pending_min = int(
                        (now - suggestion.confirmation_requested_at).total_seconds() / 60
                    )
                    instrument = getattr(suggestion, 'instrument', 'Unknown')
                    strategy = suggestion.get_strategy_display() if hasattr(suggestion, 'get_strategy_display') else suggestion.strategy
                    notify('CRITICAL_ERROR',
                        title='Exit Confirmation Overdue',
                        instrument=str(instrument),
                        strategy=str(strategy),
                        task='check_confirmation_timeouts',
                        metrics={
                            'Pending': f"{pending_min} min",
                        },
                        context=[
                            "Position remains open",
                            "MANUAL ACTION REQUIRED",
                        ],
                    )
                    suggestion.escalated = True
                    suggestion.save(update_fields=['escalated'])

        task_logger.success("Timeout check completed", context={
            'checked': checked,
            'timed_out': timed_out
        })

        return {
            'success': True,
            'checked': checked,
            'timed_out': timed_out
        }

    except Exception as e:
        task_logger.failure("Error in check_confirmation_timeouts", error=e)
        return {'success': False, 'error': str(e)}
