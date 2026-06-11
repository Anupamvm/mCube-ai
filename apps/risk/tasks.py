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
from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import BrokerAccount
from apps.positions.models import Position
from apps.risk.models import CircuitBreaker
from apps.risk.services.risk_manager import (
    check_risk_limits,
    enforce_risk_limits,
    get_risk_status
)
from apps.alerts.services.telegram_client import send_telegram_notification
from apps.alerts.services.notification_service import notify
from apps.core.utils.decorators import task_enabled_guard

logger = logging.getLogger(__name__)

# Intraday unrealized drawdown thresholds.
# WARNING fires once per account per day; CRITICAL once per account per day.
_INTRADAY_WARN_PCT = 10      # % of allocated_capital
_INTRADAY_CRITICAL_PCT = 15  # % — approach circuit breaker level

# Cache key templates — one counter per account per calendar date.
# TTL = 26 hours so yesterday's flag never bleeds into today.
_DRAWDOWN_WARN_KEY = 'intraday_drawdown_warn_{account_id}_{date}'
_DRAWDOWN_CRIT_KEY = 'intraday_drawdown_crit_{account_id}_{date}'
_PORTFOLIO_WARN_KEY = 'portfolio_drawdown_warn_{date}'
_DRAWDOWN_FLAG_TTL = 26 * 3600


@shared_task(name='apps.risk.tasks.check_risk_limits_all_accounts')
@task_enabled_guard('check-risk-limits-all-accounts')
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
                        # Telegram notification is sent inside activate_circuit_breaker()
                        # with mode-accurate text (manual vs autonomous)
                        circuit_breakers_activated += 1

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

                    from apps.alerts.services.notification_payload import NotificationPayload
                    from apps.alerts.services.telegram_client import send_notification as _send_notif
                    _limit_lines = [
                        f"{limit.limit_type}: ₹{limit.current_value:,.0f} / ₹{limit.limit_value:,.0f} "
                        f"({limit.get_utilization_pct():.1f}%)"
                        for limit in risk_check['warnings']
                    ]
                    _rw_payload = NotificationPayload(
                        title='Risk Warning',
                        status='WARNING',
                        instrument=account.account_name,
                        strategy=account.broker,
                        task='check_risk_limits_all_accounts',
                        context=_limit_lines + ["Exercise caution with new positions"],
                        actions=["Review open positions", "Avoid new entries until below threshold"],
                        system={'Account': account.account_name, 'Broker': account.broker},
                        priority='WARNING',
                        dedup_key=f'risk_warn_{account.id}_{timezone.localdate().isoformat()}',
                    )
                    _send_notif(_rw_payload)

                else:
                    logger.info(f"✅ All risk limits OK for {account.account_name}")

                # ── Intraday unrealized drawdown check ────────────────────────
                # Runs regardless of realized limit status above.
                # Uses allocated_capital as the denominator.
                try:
                    open_pos = Position.objects.filter(account=account, status='OPEN')
                    total_unrealized = sum(
                        (p.unrealized_pnl or Decimal('0')) for p in open_pos
                    )
                    if total_unrealized < 0 and account.allocated_capital:
                        drawdown_pct = float(
                            abs(total_unrealized) / account.allocated_capital * 100
                        )
                        today_str = timezone.localdate().isoformat()

                        try:
                            from apps.core.models import TradingCoreConfig
                            _cfg = TradingCoreConfig.get_instance()
                            _mode_tag = (
                                f"\n<i>⚙️ {_cfg.get_notification_level_display_short()} "
                                f"· {_cfg.get_position_sizing_display_short()}</i>"
                            )
                        except Exception:
                            _mode_tag = ''

                        if drawdown_pct >= _INTRADAY_CRITICAL_PCT:
                            crit_key = _DRAWDOWN_CRIT_KEY.format(
                                account_id=account.id, date=today_str
                            )
                            if cache.add(crit_key, '1', timeout=_DRAWDOWN_FLAG_TTL):
                                notify('RISK_WARNING',
                                    title='Critical Intraday Drawdown',
                                    instrument=account.account_name,
                                    task='check_risk_limits_all_accounts',
                                    metrics={
                                        'Unrealized Loss': f"₹{abs(total_unrealized):,.0f}",
                                        'Drawdown': f"{drawdown_pct:.1f}% of capital",
                                    },
                                    context=["Approaching circuit breaker threshold"],
                                )

                        elif drawdown_pct >= _INTRADAY_WARN_PCT:
                            warn_key = _DRAWDOWN_WARN_KEY.format(
                                account_id=account.id, date=today_str
                            )
                            if cache.add(warn_key, '1', timeout=_DRAWDOWN_FLAG_TTL):
                                notify('RISK_WARNING',
                                    title='Intraday Drawdown Warning',
                                    instrument=account.account_name,
                                    task='check_risk_limits_all_accounts',
                                    metrics={
                                        'Unrealized Loss': f"₹{abs(total_unrealized):,.0f}",
                                        'Drawdown': f"{drawdown_pct:.1f}% of capital",
                                    },
                                    context=["Monitor open positions closely"],
                                )
                except Exception as dd_err:
                    logger.error(
                        f"Intraday drawdown check failed for {account.account_name}: {dd_err}"
                    )

                accounts_checked += 1

            except Exception as e:
                logger.error(
                    f"Error checking risk limits for {account.account_name}: {e}",
                    exc_info=True
                )

        # ── Portfolio-level aggregate drawdown check ──────────────────────────
        # Aggregates unrealized P&L across ALL accounts — catches cases where
        # individual accounts are within limits but combined exposure is high.
        try:
            all_open = Position.objects.filter(status='OPEN').select_related('account')
            portfolio_unrealized = sum(
                (p.unrealized_pnl or Decimal('0')) for p in all_open
            )
            total_capital = sum(
                (acc.allocated_capital or Decimal('0'))
                for acc in active_accounts
                if acc.allocated_capital
            )
            if portfolio_unrealized < 0 and total_capital > 0:
                portfolio_dd_pct = float(
                    abs(portfolio_unrealized) / total_capital * 100
                )
                if portfolio_dd_pct >= _INTRADAY_WARN_PCT:
                    today_str = timezone.localdate().isoformat()
                    port_key = _PORTFOLIO_WARN_KEY.format(date=today_str)
                    if cache.add(port_key, '1', timeout=_DRAWDOWN_FLAG_TTL):
                        try:
                            from apps.core.models import TradingCoreConfig
                            _cfg = TradingCoreConfig.get_instance()
                            _port_mode_tag = (
                                f"\n<i>⚙️ {_cfg.get_notification_level_display_short()} "
                                f"· {_cfg.get_position_sizing_display_short()}</i>"
                            )
                        except Exception:
                            _port_mode_tag = ''
                        notify('RISK_WARNING',
                            title='Portfolio Drawdown Warning',
                            task='check_risk_limits_all_accounts',
                            metrics={
                                'Unrealized Loss': f"₹{abs(portfolio_unrealized):,.0f}",
                                'Drawdown': f"{portfolio_dd_pct:.1f}% of total capital",
                            },
                            context=["Total unrealized loss across all accounts", "Review all open positions"],
                        )
        except Exception as port_err:
            logger.error(f"Portfolio drawdown check failed: {port_err}")

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
        notify('TASK_ERROR',
            title='Risk Limits Check Failed',
            task='check_risk_limits_all_accounts',
            context=[str(e)[:200]],
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.risk.tasks.monitor_circuit_breakers')
@task_enabled_guard('monitor-circuit-breakers')
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

                    # One-shot dedup: only notify ONCE per breaker until manually reset.
                    # Without this, the 30s task loop fires every cycle for days.
                    cb_expired_key = f'cb_expired_notified_{breaker.id}'
                    if not cache.add(cb_expired_key, '1', timeout=24 * 3600):
                        # Already notified within 24h — skip
                        breakers_monitored += 1
                        continue

                    logger.warning(
                        f"⏰ Circuit breaker cooldown expired: {account.account_name}, "
                        f"Trigger: {breaker.trigger_type}"
                    )

                    # Send notification for manual review (via unified notify API)
                    notify('CIRCUIT_BREAKER',
                        title="Circuit Breaker Expired",
                        instrument=f"{account.account_name}",
                        task='monitor_circuit_breakers',
                        metrics={
                            "Trigger": breaker.trigger_type,
                            "Since": breaker.created_at.strftime('%-d %b %H:%M'),
                        },
                        actions=[
                            "Review account status",
                            "Verify all positions closed",
                            "Check margin availability",
                            "Reset circuit breaker manually if approved",
                        ],
                        system={
                            "Triggered": breaker.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                            "Cooldown Ended": breaker.cooldown_until.strftime('%Y-%m-%d %H:%M:%S'),
                        },
                        context=["Account remains deactivated until manual reset"],
                    )

                # Check for long-running circuit breakers (> 24 hours)
                elif (current_time - breaker.created_at).total_seconds() > 86400:  # 24 hours
                    hours_active = (current_time - breaker.created_at).total_seconds() / 3600

                    # Send reminder every 6 hours — use Redis atomic add (TTL=6h) instead
                    # of modulo-on-float which is unreliable for tasks running every 30s.
                    cb_reminder_key = f'cb_reminder_{breaker.id}'
                    if cache.add(cb_reminder_key, '1', timeout=6 * 3600):
                        reminders_sent += 1

                        logger.warning(
                            f"⚠️ Circuit breaker active for {hours_active:.1f} hours: "
                            f"{account.account_name}"
                        )

                        notify('CIRCUIT_BREAKER',
                            title="Circuit Breaker Still Active",
                            instrument=f"{account.account_name}",
                            task='monitor_circuit_breakers',
                            metrics={
                                "Trigger": breaker.trigger_type,
                                "Active For": f"{hours_active:.1f} hours",
                            },
                            system={
                                "Positions Closed": str(breaker.positions_closed),
                                "Broker": str(account.broker),
                            },
                            context=["Manual review and reset required"],
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
        notify('JOB_COMPLETED',
            title='Daily Risk Report',
            task='generate_daily_risk_report',
            metrics={
                'Accounts': str(accounts_reported),
                'Breaches': str(total_breaches),
                'Warnings': str(total_warnings),
            },
            context=report_lines[2:],  # skip header lines already in title
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
        notify('TASK_ERROR',
            title='Risk Report Failed',
            task='generate_daily_risk_report',
            context=[str(e)[:200]],
        )
        return {'success': False, 'message': str(e)}
