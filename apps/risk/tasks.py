"""
Risk Management Celery Tasks

Automated tasks for risk monitoring and enforcement:
- Check risk limits for all accounts (every 1 minute)
- Monitor circuit breakers (every 30 seconds)
- Enforce risk rules and activate circuit breakers
"""

import logging
from decimal import Decimal
from celery import shared_task
from django.utils import timezone

from apps.accounts.models import BrokerAccount
from apps.risk.models import RiskLimit, CircuitBreaker
from apps.risk.services.risk_manager import (
    check_risk_limits,
    enforce_risk_limits,
    activate_circuit_breaker,
    get_risk_status
)
from apps.alerts.services.telegram_client import send_telegram_notification

logger = logging.getLogger(__name__)


@shared_task(name='apps.risk.tasks.check_risk_limits_all_accounts')
def check_risk_limits_all_accounts():
    """
    Check risk limits for all active accounts

    Scheduled: Every 1 minute

    Workflow:
    1. Get all active broker accounts
    2. Check daily/weekly loss limits
    3. Activate circuit breaker if limits breached
    4. Send alerts for warnings and breaches

    Returns:
        dict: Task execution summary
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Risk Limits Check - All Accounts")
    logger.info("=" * 80)

    try:
        # Get all active broker accounts
        active_accounts = BrokerAccount.objects.filter(is_active=True)

        if not active_accounts.exists():
            logger.info("ℹ️ No active accounts to monitor")
            return {'success': True, 'accounts_checked': 0}

        accounts_checked = 0
        warnings_sent = 0
        breaches_detected = 0
        circuit_breakers_activated = 0

        for account in active_accounts:
            try:
                logger.info(f"Checking risk limits for: {account.account_name}")

                # Check risk limits
                risk_check = check_risk_limits(account)

                # Handle breaches - CRITICAL PATH
                if risk_check['breached_limits']:
                    breaches_detected += len(risk_check['breached_limits'])

                    logger.critical(
                        f"🚨 RISK LIMIT BREACH: {account.account_name}, "
                        f"{len(risk_check['breached_limits'])} limit(s) breached"
                    )

                    # Enforce risk limits - THIS WILL:
                    # 1. Close ALL active positions immediately
                    # 2. Deactivate the account (no new trades)
                    # 3. Activate circuit breaker with 24h cooldown
                    trading_allowed, message = enforce_risk_limits(account)

                    if not trading_allowed:
                        # Circuit breaker was activated - account locked
                        circuit_breakers_activated += 1

                        # Send critical alert
                        breach_details = "\n".join([
                            f"• {limit.limit_type}: ₹{limit.current_value:,.0f} / ₹{limit.limit_value:,.0f}"
                            for limit in risk_check['breached_limits']
                        ])

                        send_telegram_notification(
                            f"🚨🚨 CIRCUIT BREAKER ACTIVATED 🚨🚨\n\n"
                            f"Account: {account.account_name}\n"
                            f"Broker: {account.broker}\n\n"
                            f"BREACHED LIMITS:\n{breach_details}\n\n"
                            f"ACTIONS TAKEN:\n"
                            f"✅ All positions closed\n"
                            f"✅ Account deactivated\n"
                            f"✅ 24-hour cooldown activated\n\n"
                            f"⚠️ IMMEDIATE ATTENTION REQUIRED",
                            notification_type='ERROR'
                        )

                # Handle warnings
                elif risk_check['warnings']:
                    warnings_sent += 1

                    logger.warning(
                        f"⚠️ RISK WARNING: {account.account_name}, "
                        f"{len(risk_check['warnings'])} limit(s) approaching threshold"
                    )

                    # Send warning alert
                    warning_details = "\n".join([
                        f"• {limit.limit_type}: ₹{limit.current_value:,.0f} / ₹{limit.limit_value:,.0f} "
                        f"({limit.get_utilization_pct():.1f}%)"
                        for limit in risk_check['warnings']
                    ])

                    send_telegram_notification(
                        f"⚠️ RISK WARNING ⚠️\n\n"
                        f"Account: {account.account_name}\n"
                        f"Broker: {account.broker}\n\n"
                        f"LIMITS APPROACHING:\n{warning_details}\n\n"
                        f"⚠️ Exercise caution with new positions",
                        notification_type='WARNING'
                    )

                else:
                    logger.info(f"✅ All risk limits OK for {account.account_name}")

                accounts_checked += 1

            except Exception as e:
                logger.error(
                    f"Error checking risk limits for {account.account_name}: {e}",
                    exc_info=True
                )

        logger.info(
            f"✅ Risk check complete: {accounts_checked} accounts checked, "
            f"{warnings_sent} warnings, {breaches_detected} breaches, "
            f"{circuit_breakers_activated} circuit breakers activated"
        )
        logger.info("=" * 80)

        return {
            'success': True,
            'accounts_checked': accounts_checked,
            'warnings_sent': warnings_sent,
            'breaches_detected': breaches_detected,
            'circuit_breakers_activated': circuit_breakers_activated,
            'timestamp': timezone.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in risk limits check task: {e}", exc_info=True)
        send_telegram_notification(
            f"❌ ERROR: Risk limits check task failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.risk.tasks.monitor_circuit_breakers')
def monitor_circuit_breakers():
    """
    Monitor active circuit breakers

    Scheduled: Every 30 seconds

    Workflow:
    1. Get all active circuit breakers
    2. Check if cooldown periods have expired
    3. Check if positions were successfully closed
    4. Send periodic reminders
    5. Auto-reset circuit breakers after cooldown (manual approval required)

    Returns:
        dict: Task execution summary
    """
    try:
        # Get all active circuit breakers
        active_breakers = CircuitBreaker.objects.filter(is_active=True)

        if not active_breakers.exists():
            return {'success': True, 'active_breakers': 0}

        breakers_monitored = 0
        cooldowns_expired = 0
        reminders_sent = 0

        for breaker in active_breakers:
            try:
                account = breaker.account
                current_time = timezone.now()

                # Check if cooldown period has expired
                if breaker.cooldown_until and current_time >= breaker.cooldown_until:
                    cooldowns_expired += 1

                    logger.warning(
                        f"⏰ Circuit breaker cooldown expired: {account.account_name}, "
                        f"Trigger: {breaker.trigger_type}"
                    )

                    # Send notification for manual review
                    send_telegram_notification(
                        f"⏰ CIRCUIT BREAKER COOLDOWN EXPIRED\n\n"
                        f"Account: {account.account_name}\n"
                        f"Broker: {account.broker}\n"
                        f"Trigger: {breaker.trigger_type}\n"
                        f"Triggered: {breaker.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"Cooldown Ended: {breaker.cooldown_until.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"MANUAL REVIEW REQUIRED:\n"
                        f"1. Review account status\n"
                        f"2. Verify all positions closed\n"
                        f"3. Check margin availability\n"
                        f"4. Reset circuit breaker manually if approved\n\n"
                        f"⚠️ Account remains deactivated until manual reset",
                        notification_type='WARNING'
                    )

                # Check for long-running circuit breakers (> 24 hours)
                elif (current_time - breaker.created_at).total_seconds() > 86400:  # 24 hours
                    hours_active = (current_time - breaker.created_at).total_seconds() / 3600

                    # Send reminder every 6 hours
                    if int(hours_active) % 6 == 0:
                        reminders_sent += 1

                        logger.warning(
                            f"⚠️ Circuit breaker active for {hours_active:.1f} hours: "
                            f"{account.account_name}"
                        )

                        send_telegram_notification(
                            f"⚠️ CIRCUIT BREAKER STILL ACTIVE\n\n"
                            f"Account: {account.account_name}\n"
                            f"Broker: {account.broker}\n"
                            f"Trigger: {breaker.trigger_type}\n"
                            f"Active For: {hours_active:.1f} hours\n"
                            f"Positions Closed: {breaker.positions_closed}\n\n"
                            f"⚠️ Manual review and reset required",
                            notification_type='WARNING'
                        )

                breakers_monitored += 1

            except Exception as e:
                logger.error(
                    f"Error monitoring circuit breaker {breaker.id}: {e}",
                    exc_info=True
                )

        return {
            'success': True,
            'active_breakers': breakers_monitored,
            'cooldowns_expired': cooldowns_expired,
            'reminders_sent': reminders_sent,
            'timestamp': timezone.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in circuit breaker monitoring task: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.risk.tasks.generate_daily_risk_report')
def generate_daily_risk_report():
    """
    Generate daily risk report for all accounts

    Scheduled: End of day (6:00 PM)

    Workflow:
    1. Get risk status for all accounts
    2. Calculate daily/weekly utilization
    3. Generate summary report
    4. Send via Telegram

    Returns:
        dict: Task execution summary
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Daily Risk Report Generation")
    logger.info("=" * 80)

    try:
        # Get all broker accounts (including inactive)
        all_accounts = BrokerAccount.objects.all()

        if not all_accounts.exists():
            logger.info("ℹ️ No accounts to report on")
            return {'success': True, 'accounts_reported': 0}

        report_lines = ["📊 DAILY RISK REPORT\n"]
        report_lines.append(f"Date: {timezone.now().strftime('%Y-%m-%d')}\n")

        accounts_reported = 0
        total_breaches = 0
        total_warnings = 0

        for account in all_accounts:
            try:
                # Get risk status
                risk_status = get_risk_status(account)

                status_icon = "✅" if account.is_active else "❌"
                status_text = "ACTIVE" if account.is_active else "DEACTIVATED"

                report_lines.append(
                    f"\n{status_icon} {account.account_name} ({account.broker}) - {status_text}\n"
                )

                # Show risk limits
                for limit in risk_status['limits']:
                    utilization = limit['utilization_pct']

                    if limit['breached']:
                        icon = "🚨"
                        total_breaches += 1
                    elif utilization >= 80:
                        icon = "⚠️"
                        total_warnings += 1
                    else:
                        icon = "✅"

                    report_lines.append(
                        f"  {icon} {limit['type']}: "
                        f"₹{limit['current']:,.0f} / ₹{limit['limit']:,.0f} "
                        f"({utilization:.1f}%)\n"
                    )

                # Show active circuit breakers
                if risk_status['active_circuit_breakers'] > 0:
                    report_lines.append(
                        f"  🚨 Active Circuit Breakers: {risk_status['active_circuit_breakers']}\n"
                    )

                accounts_reported += 1

            except Exception as e:
                logger.error(
                    f"Error generating report for {account.account_name}: {e}"
                )
                report_lines.append(f"\n❌ Error for {account.account_name}\n")

        # Summary
        report_lines.append(
            f"\n📈 SUMMARY:\n"
            f"Total Accounts: {accounts_reported}\n"
            f"Breaches: {total_breaches}\n"
            f"Warnings: {total_warnings}\n"
        )

        # Send report
        report_text = "".join(report_lines)
        send_telegram_notification(
            report_text,
            notification_type='INFO'
        )

        logger.info(f"✅ Daily risk report generated for {accounts_reported} accounts")
        logger.info("=" * 80)

        return {
            'success': True,
            'accounts_reported': accounts_reported,
            'total_breaches': total_breaches,
            'total_warnings': total_warnings
        }

    except Exception as e:
        logger.error(f"Error generating daily risk report: {e}", exc_info=True)
        send_telegram_notification(
            f"❌ ERROR: Daily risk report generation failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}
