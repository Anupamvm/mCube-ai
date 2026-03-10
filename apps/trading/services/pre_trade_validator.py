"""
Pre-Trade Validator

Runs a sequence of safety checks before any strategy executes an entry.
Returns a structured pass/fail result so callers can gate execution cleanly.

Design principles:
- Pure read operations: no orders, no DB writes.
- Each check is a separate method so new checks can be added independently.
- All failures are collected and reported together (not first-fail-stop)
  so the trader sees the full picture in a single Telegram notification.

Usage:
    validator = PreTradeValidator()
    ok, reasons = validator.validate(account, strategy_type='FUTURES')
    if not ok:
        send_telegram_notification(...)
        return {'success': False, 'blocked_by': reasons}
"""

import logging
from datetime import date
from typing import List, Tuple

from django.core.cache import cache

logger = logging.getLogger(__name__)


class PreTradeValidator:
    """
    Pre-trade safety gate.

    Checks (in order):
    1. Circuit breaker — account-level hard stop
    2. Risk limits    — daily/weekly loss and drawdown
    3. Broker health  — API connectivity (from health_check_brokers at 06:45)
    4. Duplicate position — same strategy already open on this account
    5. Daily trade count — max entries per day guardrail
    """

    # Maximum new entries per account per day across all strategies.
    # Configurable here; could be moved to TradingCoreConfig in future.
    MAX_TRADES_PER_DAY = 6

    def validate(
        self,
        account,
        strategy_type: str = '',
    ) -> Tuple[bool, List[str]]:
        """
        Run all pre-trade checks.

        Args:
            account: BrokerAccount instance
            strategy_type: Strategy key for duplicate-position check
                           e.g. 'WEEKLY_NIFTY_STRANGLE', 'BROKEN_IRON_CONDOR',
                                'LLM_VALIDATED_FUTURES'

        Returns:
            (is_ok, reasons)  — is_ok=True means safe to proceed.
            reasons is always a list; empty when is_ok=True.
        """
        failures: List[str] = []

        checks = [
            self._check_circuit_breaker(account),
            self._check_risk_limits(account),
            self._check_broker_health(account),
            self._check_duplicate_position(account, strategy_type),
            self._check_daily_trade_limit(account),
        ]

        for passed, message in checks:
            if not passed:
                failures.append(message)

        if failures:
            logger.warning(
                f"PreTradeValidator: {account} / {strategy_type} "
                f"blocked by {len(failures)} check(s): {failures}"
            )
        else:
            logger.info(
                f"PreTradeValidator: {account} / {strategy_type} — all checks passed"
            )

        return (len(failures) == 0), failures

    # ──────────────────────────────────────────────────────────────────────────
    # Individual checks — each returns (passed: bool, message: str)
    # ──────────────────────────────────────────────────────────────────────────

    def _check_circuit_breaker(self, account) -> Tuple[bool, str]:
        """Fail if an active circuit breaker exists for this account."""
        try:
            from apps.risk.models import CircuitBreaker
            cb = CircuitBreaker.objects.filter(
                account=account, is_active=True
            ).first()
            if cb:
                from django.utils import timezone
                cooldown = cb.cooldown_until
                cooldown_str = (
                    cooldown.strftime('%d-%b %H:%M') if cooldown else 'indefinite'
                )
                return False, (
                    f"Circuit breaker active on {account} "
                    f"(trigger: {cb.trigger_type}, until: {cooldown_str})"
                )
        except Exception as e:
            logger.error(f"PreTradeValidator._check_circuit_breaker error: {e}")
        return True, 'circuit_breaker_clear'

    def _check_risk_limits(self, account) -> Tuple[bool, str]:
        """Fail if daily/weekly loss or drawdown limit is breached."""
        try:
            from apps.risk.services.risk_manager import check_risk_limits
            result = check_risk_limits(account)
            if not result.get('all_clear'):
                action = result.get('action_required', '')
                if action in ('EMERGENCY_EXIT', 'STOP_TRADING'):
                    return False, (
                        f"Risk limit breached on {account}: {result.get('message', '')}"
                    )
                # WARNING level — don't block, just note
        except Exception as e:
            logger.error(f"PreTradeValidator._check_risk_limits error: {e}")
        return True, 'risk_limits_clear'

    def _check_broker_health(self, account) -> Tuple[bool, str]:
        """Warn (but don't block) if broker health check stored a failure."""
        try:
            from apps.core.tasks import BROKER_HEALTH_KEY
            broker_health = cache.get(BROKER_HEALTH_KEY)
            if broker_health is None:
                # Task didn't run — don't block, just log
                logger.warning(
                    "PreTradeValidator: broker_health not in cache — "
                    "health-check-brokers may not have run"
                )
                return True, 'broker_health_cache_missing'

            # Map account broker name to health key
            broker_key_map = {'KOTAK': 'neo', 'ICICI': 'breeze'}
            broker_key = broker_key_map.get(account.broker)
            if broker_key:
                status = broker_health.get(broker_key, 'UNKNOWN')
                if status not in ('OK', 'NO_ACCOUNT') and not str(status).startswith('OK'):
                    return False, (
                        f"Broker {account.broker} health check failed at 06:45: {status}"
                    )
        except Exception as e:
            logger.error(f"PreTradeValidator._check_broker_health error: {e}")
        return True, 'broker_healthy'

    def _check_duplicate_position(
        self, account, strategy_type: str
    ) -> Tuple[bool, str]:
        """Fail if the same strategy already has an open position on this account."""
        if not strategy_type:
            return True, 'no_strategy_type_to_check'
        try:
            from apps.positions.models import Position
            existing = Position.objects.filter(
                account=account,
                strategy_type=strategy_type,
                status='OPEN',
            ).exists()
            if existing:
                return False, (
                    f"Duplicate: {strategy_type} position already open on {account}"
                )
        except Exception as e:
            logger.error(f"PreTradeValidator._check_duplicate_position error: {e}")
        return True, 'no_duplicate'

    def _check_daily_trade_limit(self, account) -> Tuple[bool, str]:
        """Fail if the account has already entered MAX_TRADES_PER_DAY trades today."""
        try:
            from apps.positions.models import Position
            today_count = Position.objects.filter(
                account=account,
                entry_time__date=date.today(),
            ).count()
            if today_count >= self.MAX_TRADES_PER_DAY:
                return False, (
                    f"Daily trade limit reached on {account}: "
                    f"{today_count}/{self.MAX_TRADES_PER_DAY} trades today"
                )
        except Exception as e:
            logger.error(f"PreTradeValidator._check_daily_trade_limit error: {e}")
        return True, 'within_daily_limit'
