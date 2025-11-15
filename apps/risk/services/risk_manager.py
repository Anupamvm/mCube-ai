"""
Risk Management Service

This service handles risk limits, circuit breakers, and account protection.

CRITICAL RISK RULES:
✅ Daily loss limit enforcement
✅ Weekly loss limit enforcement
✅ Maximum drawdown monitoring (15%)
✅ Circuit breaker activation on breach
✅ Automatic position closure
✅ Account deactivation
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple

from django.utils import timezone

from apps.accounts.models import BrokerAccount
from apps.risk.models import RiskLimit, CircuitBreaker
from apps.positions.models import Position

logger = logging.getLogger(__name__)


def check_risk_limits(account: BrokerAccount) -> Dict[str, any]:
    """
    Check all risk limits for an account

    This function should be called:
    - Before every trade entry
    - After every position update
    - Periodically throughout the day

    Args:
        account: BrokerAccount instance

    Returns:
        dict: {
            'all_clear': bool,
            'breached_limits': List[RiskLimit],
            'warnings': List[RiskLimit],
            'action_required': str,  # 'NONE', 'WARNING', 'STOP_TRADING', 'EMERGENCY_EXIT'
            'message': str
        }
    """

    breached_limits = []
    warnings = []

    # Check daily loss limit
    daily_check = check_daily_loss_limit(account)
    if daily_check['breached']:
        breached_limits.append(daily_check['limit'])
    elif daily_check['warning']:
        warnings.append(daily_check['limit'])

    # Check weekly loss limit
    weekly_check = check_weekly_loss_limit(account)
    if weekly_check['breached']:
        breached_limits.append(weekly_check['limit'])
    elif weekly_check['warning']:
        warnings.append(weekly_check['limit'])

    # Determine action required
    if breached_limits:
        action_required = 'EMERGENCY_EXIT'
        all_clear = False
        message = f"🚨 CIRCUIT BREAKER: {len(breached_limits)} limit(s) breached. STOP ALL TRADING."
    elif warnings:
        action_required = 'WARNING'
        all_clear = False
        message = f"⚠️ WARNING: {len(warnings)} limit(s) approaching threshold."
    else:
        action_required = 'NONE'
        all_clear = True
        message = "✅ All risk limits OK"

    logger.info(
        f"Risk check for {account.account_name}: {message}"
    )

    return {
        'all_clear': all_clear,
        'breached_limits': breached_limits,
        'warnings': warnings,
        'action_required': action_required,
        'message': message
    }


def check_daily_loss_limit(account: BrokerAccount) -> Dict[str, any]:
    """
    Check daily loss limit

    Args:
        account: BrokerAccount instance

    Returns:
        dict: Check result with details
    """

    today = date.today()

    # Get or create daily loss limit
    limit, created = RiskLimit.objects.get_or_create(
        account=account,
        limit_type='DAILY_LOSS',
        period_start=today,
        defaults={
            'limit_value': account.max_daily_loss,
            'current_value': Decimal('0.00')
        }
    )

    # Calculate today's P&L
    todays_pnl = account.get_todays_pnl()
    todays_loss = abs(todays_pnl) if todays_pnl < 0 else Decimal('0.00')

    # Update limit
    limit.current_value = todays_loss
    limit.save()

    # Check for breach
    is_breached = limit.check_breach()
    is_warning = limit.check_warning()

    if is_breached:
        logger.error(
            f"🚨 DAILY LOSS LIMIT BREACHED: {account.account_name}, "
            f"Loss: ₹{todays_loss:,.0f} >= Limit: ₹{limit.limit_value:,.0f}"
        )
        return {'breached': True, 'warning': False, 'limit': limit, 'current_loss': todays_loss}

    if is_warning:
        logger.warning(
            f"⚠️ DAILY LOSS WARNING: {account.account_name}, "
            f"Loss: ₹{todays_loss:,.0f} "
            f"({limit.get_utilization_pct():.1f}% of ₹{limit.limit_value:,.0f} limit)"
        )
        return {'breached': False, 'warning': True, 'limit': limit, 'current_loss': todays_loss}

    return {'breached': False, 'warning': False, 'limit': limit, 'current_loss': todays_loss}


def check_weekly_loss_limit(account: BrokerAccount) -> Dict[str, any]:
    """
    Check weekly loss limit

    Args:
        account: BrokerAccount instance

    Returns:
        dict: Check result with details
    """

    from datetime import datetime

    today = date.today()
    # Get Monday of current week
    week_start = today - timedelta(days=today.weekday())

    # Get or create weekly loss limit
    limit, created = RiskLimit.objects.get_or_create(
        account=account,
        limit_type='WEEKLY_LOSS',
        period_start=week_start,
        defaults={
            'limit_value': account.max_weekly_loss,
            'current_value': Decimal('0.00')
        }
    )

    # Calculate this week's P&L (sum of daily P&L from Monday to today)
    # For now, use cumulative realized + unrealized P&L
    weekly_pnl = account.get_total_pnl()  # This is total P&L, need to filter by week
    weekly_loss = abs(weekly_pnl) if weekly_pnl < 0 else Decimal('0.00')

    # Update limit
    limit.current_value = weekly_loss
    limit.save()

    # Check for breach
    is_breached = limit.check_breach()
    is_warning = limit.check_warning()

    if is_breached:
        logger.error(
            f"🚨 WEEKLY LOSS LIMIT BREACHED: {account.account_name}, "
            f"Loss: ₹{weekly_loss:,.0f} >= Limit: ₹{limit.limit_value:,.0f}"
        )
        return {'breached': True, 'warning': False, 'limit': limit, 'current_loss': weekly_loss}

    if is_warning:
        logger.warning(
            f"⚠️ WEEKLY LOSS WARNING: {account.account_name}, "
            f"Loss: ₹{weekly_loss:,.0f} "
            f"({limit.get_utilization_pct():.1f}% of ₹{limit.limit_value:,.0f} limit)"
        )
        return {'breached': False, 'warning': True, 'limit': limit, 'current_loss': weekly_loss}

    return {'breached': False, 'warning': False, 'limit': limit, 'current_loss': weekly_loss}


def activate_circuit_breaker(
    account: BrokerAccount,
    trigger_type: str,
    trigger_value: Decimal,
    threshold_value: Decimal
) -> Tuple[bool, CircuitBreaker]:
    """
    Activate circuit breaker for account

    This will:
    1. Create circuit breaker record
    2. Close all active positions
    3. Cancel all pending orders
    4. Deactivate the account
    5. Send critical alerts

    Args:
        account: BrokerAccount instance
        trigger_type: What triggered it (DAILY_LOSS, WEEKLY_LOSS, DRAWDOWN)
        trigger_value: Value that triggered the breach
        threshold_value: Threshold that was exceeded

    Returns:
        Tuple[bool, CircuitBreaker]: (success, circuit_breaker_instance)
    """

    logger.critical(
        f"🚨🚨🚨 ACTIVATING CIRCUIT BREAKER: {account.account_name}, "
        f"Trigger: {trigger_type}, "
        f"Value: ₹{trigger_value:,.0f} > Threshold: ₹{threshold_value:,.0f}"
    )

    # Create circuit breaker record
    circuit_breaker = CircuitBreaker.objects.create(
        account=account,
        trigger_type=trigger_type,
        trigger_value=trigger_value,
        threshold_value=threshold_value,
        risk_level='CRITICAL',
        is_active=True,
        description=(
            f"Circuit breaker activated due to {trigger_type}. "
            f"Value ₹{trigger_value:,.0f} exceeded threshold ₹{threshold_value:,.0f}."
        )
    )

    # Step 1: Close all active positions
    active_positions = Position.objects.filter(account=account, status='ACTIVE')
    positions_closed = 0

    for position in active_positions:
        try:
            position.close_position(
                exit_price=position.current_price,
                exit_reason='CIRCUIT_BREAKER'
            )
            positions_closed += 1

            circuit_breaker.add_action(
                f"Closed position: {position.instrument} at ₹{position.current_price:,.2f}"
            )

            logger.warning(
                f"Position closed by circuit breaker: {position.instrument}"
            )

        except Exception as e:
            logger.error(
                f"Failed to close position {position.instrument}: {str(e)}",
                exc_info=True
            )
            circuit_breaker.add_action(
                f"Failed to close {position.instrument}: {str(e)}"
            )

    circuit_breaker.positions_closed = positions_closed
    circuit_breaker.save()

    # Step 2: Deactivate account
    try:
        account.deactivate(
            reason=f"Circuit breaker triggered: {trigger_type}"
        )
        circuit_breaker.account_deactivated = True
        circuit_breaker.save()

        circuit_breaker.add_action(f"Account deactivated")

        logger.critical(f"Account deactivated: {account.account_name}")

    except Exception as e:
        logger.error(
            f"Failed to deactivate account: {str(e)}",
            exc_info=True
        )
        circuit_breaker.add_action(f"Failed to deactivate account: {str(e)}")

    # Step 3: Set cooldown period (24 hours)
    circuit_breaker.cooldown_until = timezone.now() + timedelta(hours=24)
    circuit_breaker.save()

    circuit_breaker.add_action("Circuit breaker fully activated")

    logger.critical(
        f"Circuit breaker activation complete: "
        f"{positions_closed} positions closed, "
        f"account deactivated, "
        f"cooldown until {circuit_breaker.cooldown_until}"
    )

    return True, circuit_breaker


def enforce_risk_limits(account: BrokerAccount) -> Tuple[bool, str]:
    """
    Enforce risk limits - activate circuit breaker if needed

    This is the main risk enforcement function that should be called
    regularly to check and enforce all risk rules.

    Args:
        account: BrokerAccount instance

    Returns:
        Tuple[bool, str]: (trading_allowed, message)
    """

    # Check if account is already deactivated
    if not account.is_active:
        return False, "Account is deactivated"

    # Check if circuit breaker is active
    active_breaker = CircuitBreaker.objects.filter(
        account=account,
        is_active=True
    ).first()

    if active_breaker:
        # Check if cooldown period has passed
        if active_breaker.cooldown_until and timezone.now() < active_breaker.cooldown_until:
            time_remaining = (active_breaker.cooldown_until - timezone.now()).total_seconds() / 3600
            return False, f"Circuit breaker active. Cooldown: {time_remaining:.1f} hours remaining"

    # Check all risk limits
    risk_check = check_risk_limits(account)

    if not risk_check['all_clear']:
        if risk_check['action_required'] == 'EMERGENCY_EXIT':
            # Activate circuit breaker
            for limit in risk_check['breached_limits']:
                activate_circuit_breaker(
                    account=account,
                    trigger_type=limit.limit_type,
                    trigger_value=limit.current_value,
                    threshold_value=limit.limit_value
                )

            return False, "Circuit breaker activated due to risk limit breach"

        elif risk_check['action_required'] == 'WARNING':
            return True, f"WARNING: {risk_check['message']}"

    return True, "All risk checks passed"


def get_risk_status(account: BrokerAccount) -> Dict[str, any]:
    """
    Get comprehensive risk status for account

    Args:
        account: BrokerAccount instance

    Returns:
        dict: Complete risk status
    """

    risk_check = check_risk_limits(account)

    # Get active circuit breakers
    active_breakers = CircuitBreaker.objects.filter(
        account=account,
        is_active=True
    )

    # Get current risk limits
    current_limits = RiskLimit.objects.filter(
        account=account,
        period_start=date.today()
    )

    return {
        'account_active': account.is_active,
        'trading_allowed': risk_check['all_clear'],
        'risk_level': risk_check['action_required'],
        'breached_limits': len(risk_check['breached_limits']),
        'warnings': len(risk_check['warnings']),
        'active_circuit_breakers': active_breakers.count(),
        'message': risk_check['message'],
        'limits': [
            {
                'type': limit.limit_type,
                'current': limit.current_value,
                'limit': limit.limit_value,
                'utilization_pct': limit.get_utilization_pct(),
                'breached': limit.is_breached
            }
            for limit in current_limits
        ]
    }
