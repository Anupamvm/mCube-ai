# Telegram Integration Examples

This document shows practical examples of integrating Telegram alerts with mCube services.

## Quick Start

```python
from apps.alerts.services import send_position_alert, send_risk_alert

# Send a position alert
send_position_alert(
    position=my_position,
    alert_type='POSITION_ENTERED',
    priority='MEDIUM'
)

# Send a risk alert
send_risk_alert(
    account=my_account,
    alert_type='DAILY_LOSS_LIMIT',
    priority='HIGH'
)
```

## Integration with Position Manager

### apps/positions/services/position_manager.py

```python
from apps.alerts.services import send_position_alert

def create_position(account, strategy_type, instrument, ...):
    """Create a new position with alert"""

    # ... position creation logic ...

    position = Position.objects.create(...)

    # Send Telegram notification
    send_position_alert(
        position,
        alert_type='POSITION_ENTERED',
        priority='MEDIUM',
        message=f"New {position.direction} position in {position.instrument}"
    )

    return True, position, message


def close_position(position, exit_price, exit_reason):
    """Close position with alert"""

    # Close the position
    position.close_position(exit_price, exit_reason)

    # Determine priority based on P&L
    priority = 'HIGH' if position.realized_pnl < 0 else 'MEDIUM'

    # Send Telegram notification
    send_position_alert(
        position,
        alert_type='POSITION_CLOSED',
        priority=priority,
        message=f"Position closed. P&L: Rs.{position.realized_pnl:,.2f}"
    )

    return True, message
```

## Integration with Exit Manager

### apps/positions/services/exit_manager.py

```python
from apps.alerts.services import send_position_alert

def check_exit_conditions(position):
    """Check exit conditions with alerting"""

    # ... exit checking logic ...

    # Check stop-loss
    if position.is_stop_loss_hit():
        # Send CRITICAL alert
        send_position_alert(
            position,
            alert_type='SL_HIT',
            priority='CRITICAL',
            message=f"STOP-LOSS HIT! Current: Rs.{position.current_price:,.2f}"
        )

        return {
            'should_exit': True,
            'exit_reason': 'STOP_LOSS',
            'is_mandatory': True
        }

    # Check target
    if position.is_target_hit():
        # Send HIGH priority alert
        send_position_alert(
            position,
            alert_type='TARGET_HIT',
            priority='HIGH',
            message=f"TARGET HIT! Current: Rs.{position.current_price:,.2f}"
        )

        return {
            'should_exit': True,
            'exit_reason': 'TARGET',
            'is_mandatory': True
        }

    return {'should_exit': False}
```

## Integration with Risk Manager

### apps/risk/services/risk_manager.py

```python
from apps.alerts.services import send_risk_alert, get_alert_manager

def check_risk_limits(account):
    """Check risk limits with alerting"""

    # ... risk checking logic ...

    if breached_limits:
        # Send CRITICAL risk alert
        send_risk_alert(
            account,
            alert_type='CIRCUIT_BREAKER',
            priority='CRITICAL',
            risk_data={
                'action_required': 'EMERGENCY_EXIT',
                'breached_limits': breached_limits,
                'message': f"🚨 CIRCUIT BREAKER: {len(breached_limits)} limit(s) breached"
            }
        )

    elif warnings:
        # Send warning alert
        send_risk_alert(
            account,
            alert_type='RISK_WARNING',
            priority='HIGH',
            risk_data={
                'action_required': 'WARNING',
                'warnings': warnings,
                'message': f"⚠️ WARNING: {len(warnings)} limit(s) approaching threshold"
            }
        )

    return risk_check


def activate_circuit_breaker(account, trigger_type, trigger_value, threshold_value):
    """Activate circuit breaker with immediate alert"""

    # Create circuit breaker
    circuit_breaker = CircuitBreaker.objects.create(...)

    # Send CRITICAL alert immediately
    alert_manager = get_alert_manager()
    alert_manager.create_risk_alert(
        account,
        alert_type='CIRCUIT_BREAKER',
        priority='CRITICAL',
        risk_data={
            'action_required': 'EMERGENCY_EXIT',
            'trigger_type': trigger_type,
            'trigger_value': float(trigger_value),
            'threshold_value': float(threshold_value),
            'breached_limits': [{
                'type': trigger_type,
                'current': float(trigger_value),
                'limit': float(threshold_value)
            }],
            'message': (
                f"🚨🚨🚨 CIRCUIT BREAKER ACTIVATED!\n\n"
                f"Trigger: {trigger_type}\n"
                f"Value: Rs.{trigger_value:,.0f}\n"
                f"Threshold: Rs.{threshold_value:,.0f}\n\n"
                f"ALL TRADING STOPPED. MANUAL INTERVENTION REQUIRED."
            )
        }
    )

    # Close positions...
    # Deactivate account...

    return True, circuit_breaker
```

## Integration with Monitoring Loop

### apps/core/tasks/monitor_positions.py

```python
from celery import shared_task
from apps.positions.models import Position
from apps.alerts.services import send_position_alert

@shared_task
def monitor_active_positions():
    """Monitor active positions and send alerts"""

    active_positions = Position.objects.filter(status='ACTIVE')

    for position in active_positions:
        # Update current price (from broker API)
        current_price = fetch_current_price(position.instrument)
        position.update_current_price(current_price)

        # Check delta for strangles
        if position.direction == 'NEUTRAL':
            delta = calculate_delta(position)

            if abs(delta) > 0.20:  # Delta threshold
                send_position_alert(
                    position,
                    alert_type='DELTA_ALERT',
                    priority='HIGH',
                    message=f"⚠️ Delta alert! Current delta: {delta:.4f}"
                )

        # Check exit conditions
        exit_check = check_exit_conditions(position)

        if exit_check['should_exit']:
            # Alert already sent by exit_manager
            # Execute exit
            close_position(
                position,
                position.current_price,
                exit_check['exit_reason']
            )
```

## Daily Summary Example

### apps/analytics/tasks/daily_summary.py

```python
from celery import shared_task
from datetime import date
from apps.accounts.models import BrokerAccount
from apps.analytics.models import DailyPnL
from apps.alerts.services import get_alert_manager

@shared_task
def send_daily_summary():
    """Send daily trading summary at EOD"""

    for account in BrokerAccount.objects.filter(is_active=True):
        # Get today's P&L
        try:
            daily_pnl = DailyPnL.objects.get(
                account=account,
                date=date.today()
            )
        except DailyPnL.DoesNotExist:
            continue

        # Prepare summary data
        summary_data = {
            'date': date.today().strftime('%d-%b-%Y'),
            'total_pnl': float(daily_pnl.total_pnl),
            'realized_pnl': float(daily_pnl.realized_pnl),
            'unrealized_pnl': float(daily_pnl.unrealized_pnl),
            'total_trades': daily_pnl.total_trades,
            'winning_trades': daily_pnl.winning_trades,
            'losing_trades': daily_pnl.losing_trades,
            'win_rate': (daily_pnl.winning_trades / daily_pnl.total_trades * 100)
                if daily_pnl.total_trades > 0 else 0,
            'active_positions': account.positions.filter(status='ACTIVE').count(),
            'capital_deployed': float(account.get_deployed_capital()),
            'margin_available': float(account.get_available_capital()),
        }

        # Send summary
        alert_manager = get_alert_manager()
        alert_manager.create_daily_summary_alert(
            account,
            summary_data,
            send_telegram=True
        )
```

## Error Handling Example

### apps/brokers/services/kotak_client.py

```python
from apps.alerts.services import get_alert_manager

def execute_order(order):
    """Execute order with error alerting"""

    try:
        # Execute order via broker API
        response = kotak_api.place_order(...)

        if not response['success']:
            # Send error alert
            alert_manager = get_alert_manager()
            alert_manager.create_system_alert(
                alert_type='ORDER_FAILED',
                title=f'Order Execution Failed - {order.instrument}',
                message=(
                    f"Failed to execute order:\n"
                    f"Instrument: {order.instrument}\n"
                    f"Type: {order.order_type}\n"
                    f"Quantity: {order.quantity}\n"
                    f"Error: {response['error']}"
                ),
                priority='HIGH',
                send_telegram=True,
                metadata={'order_id': order.id, 'error': response['error']}
            )

        return response

    except Exception as e:
        # Send critical system alert
        alert_manager = get_alert_manager()
        alert_manager.create_system_alert(
            alert_type='SYSTEM_ERROR',
            title='Critical Error in Order Execution',
            message=(
                f"Exception occurred during order execution:\n"
                f"Order ID: {order.id}\n"
                f"Error: {str(e)}"
            ),
            priority='CRITICAL',
            send_telegram=True,
            metadata={'order_id': order.id, 'exception': str(e)}
        )

        raise
```

## Custom Alert Types

### Creating Custom Alerts

```python
from apps.alerts.services import get_alert_manager

def send_custom_alert():
    """Send a custom alert"""

    alert_manager = get_alert_manager()

    # Custom expiry warning
    alert_manager.create_system_alert(
        alert_type='EXPIRY_WARNING',
        title='Options Expiring Soon',
        message=(
            "⚠️ Your NIFTY 24000 CE position expires in 2 hours!\n\n"
            "Current P&L: Rs.15,000\n"
            "Consider closing or rolling the position."
        ),
        priority='HIGH',
        send_telegram=True,
        metadata={
            'expiry_time': '15:30',
            'hours_remaining': 2
        }
    )

    # LLM validation alert
    alert_manager.create_system_alert(
        alert_type='LLM_VALIDATION_FAILED',
        title='Trade Rejected by LLM',
        message=(
            "❌ Proposed futures trade rejected by LLM validator\n\n"
            "Symbol: RELIANCE\n"
            "Reason: Low volume, high volatility\n"
            "Confidence: 85%\n\n"
            "No position was entered."
        ),
        priority='MEDIUM',
        send_telegram=True
    )
```

## Batching Alerts

### Preventing Alert Spam

```python
from datetime import timedelta
from django.utils import timezone
from apps.alerts.models import Alert

def should_send_delta_alert(position):
    """Check if delta alert was recently sent"""

    # Check if we sent delta alert in last 30 minutes
    recent_alert = Alert.objects.filter(
        position=position,
        alert_type='DELTA_ALERT',
        created_at__gte=timezone.now() - timedelta(minutes=30)
    ).first()

    return recent_alert is None


def send_delta_alert_throttled(position, delta):
    """Send delta alert with throttling"""

    if should_send_delta_alert(position):
        send_position_alert(
            position,
            alert_type='DELTA_ALERT',
            priority='HIGH',
            message=f"Delta: {delta:.4f}"
        )
    else:
        logger.debug(f"Delta alert throttled for {position.instrument}")
```

## Testing

### Manual Testing

```python
from apps.accounts.models import BrokerAccount
from apps.alerts.services import send_risk_alert

# Get account
account = BrokerAccount.objects.get(account_name='Kotak_Main')

# Send test alert
send_risk_alert(
    account,
    alert_type='RISK_WARNING',
    priority='HIGH',
    risk_data={
        'action_required': 'WARNING',
        'message': 'This is a test risk alert'
    }
)
```

### Automated Testing

```python
from django.test import TestCase
from apps.alerts.services import get_telegram_client
from unittest.mock import patch, MagicMock

class TelegramIntegrationTest(TestCase):
    @patch('requests.post')
    def test_send_message(self, mock_post):
        # Mock successful response
        mock_post.return_value = MagicMock(status_code=200)

        client = get_telegram_client()
        success, response = client.send_message("Test")

        self.assertTrue(success)
        mock_post.assert_called_once()
```

## Monitoring

### Check Alert Delivery Status

```python
from apps.alerts.models import Alert, AlertLog

# Recent alerts
recent_alerts = Alert.objects.order_by('-created_at')[:10]

for alert in recent_alerts:
    print(f"{alert.title}: Telegram={'✅' if alert.telegram_sent else '❌'}")

# Failed deliveries
failed = Alert.objects.filter(
    send_telegram=True,
    telegram_sent=False
)

print(f"Failed deliveries: {failed.count()}")

# Retry failed alerts
from apps.alerts.services import get_alert_manager
manager = get_alert_manager()
retried, success = manager.retry_failed_alerts()
```

## Best Practices

1. **Use appropriate priority levels**:
   - CRITICAL: Stop-loss, circuit breakers, system errors
   - HIGH: Targets, risk warnings, order failures
   - MEDIUM: Position entry/exit, regular updates
   - INFO: Daily summaries, status updates

2. **Avoid alert spam**:
   - Throttle similar alerts (e.g., delta alerts every 30 minutes)
   - Batch multiple updates into summary messages
   - Use INFO priority for non-urgent updates

3. **Include actionable information**:
   - What happened (position entered, SL hit, etc.)
   - Current state (prices, P&L, metrics)
   - What action is required (exit immediately, monitor, etc.)

4. **Test before production**:
   - Use `python manage.py test_telegram --send-all`
   - Verify message formatting on mobile device
   - Test with different priority levels

5. **Monitor delivery**:
   - Check AlertLog for failures
   - Set up retry logic for critical alerts
   - Monitor Telegram API rate limits

---

**Note**: These examples assume Telegram is properly configured. See `TELEGRAM_SETUP.md` for setup instructions.
