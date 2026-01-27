# Risk App Documentation

**Location**: `apps/risk/`

The risk app manages risk limits and circuit breakers - the safety mechanisms that protect against catastrophic losses.

---

## What This App Does

1. **Risk Limits** - Tracks daily/weekly loss limits
2. **Circuit Breakers** - Automatic account shutdown on limit breach
3. **Real-time Monitoring** - Continuous risk assessment
4. **Auto-Protection** - Closes positions and deactivates accounts

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | RiskLimit and CircuitBreaker models |
| `services/risk_manager.py` | Risk enforcement engine |
| `tasks.py` | Celery tasks for monitoring |
| `views.py` | API endpoints |
| `admin.py` | Django admin interface |

---

## Key Models

### RiskLimit

Tracks risk limits and current utilization.

```python
# Fields
account = ForeignKey(BrokerAccount)
limit_type = CharField()           # DAILY_LOSS, WEEKLY_LOSS, POSITION_SIZE
limit_value = DecimalField()       # Maximum allowed (e.g., Rs 50,000)
current_value = DecimalField()     # Current utilization
is_breached = BooleanField()       # Has limit been exceeded?
breach_timestamp = DateTimeField() # When breached

# Tracking Period
period_start = DateField()
period_end = DateField()

# Warning
warning_threshold_pct = DecimalField()  # Default: 80%
warning_sent = BooleanField()

# Methods
def get_utilization_pct(self):
    return (self.current_value / self.limit_value) * 100

def check_breach(self):
    return self.current_value >= self.limit_value

def check_warning(self):
    return self.get_utilization_pct() >= self.warning_threshold_pct
```

### CircuitBreaker

Records circuit breaker activation events.

```python
# Fields
account = ForeignKey(BrokerAccount)
trigger_type = CharField()         # DAILY_LOSS, WEEKLY_LOSS, DRAWDOWN
trigger_value = DecimalField()     # Value that triggered (e.g., -55000)
threshold_value = DecimalField()   # Limit that was exceeded (e.g., 50000)
risk_level = CharField()           # HIGH, CRITICAL

# Status
is_active = BooleanField()         # Currently active?
account_deactivated = BooleanField()
positions_closed = IntegerField()  # How many auto-closed
orders_cancelled = IntegerField()

# Recovery
reset_at = DateTimeField()         # When reset
reset_by = CharField()             # Who reset it
cooldown_until = DateTimeField()   # 24-hour lockdown

# Audit
description = TextField()
actions_log = JSONField()          # List of actions taken

# Methods
def add_action(self, action):
    self.actions_log.append({
        'timestamp': timezone.now().isoformat(),
        'action': action
    })
    self.save()

def reset_breaker(self, reset_by):
    self.is_active = False
    self.reset_at = timezone.now()
    self.reset_by = reset_by
    self.save()
```

---

## Risk Manager Service

**File**: `services/risk_manager.py`

### Core Functions

```python
from apps.risk.services.risk_manager import (
    check_risk_limits,
    check_daily_loss_limit,
    check_weekly_loss_limit,
    activate_circuit_breaker,
    enforce_risk_limits,
    get_risk_status,
)
```

#### check_risk_limits(account)

Comprehensive risk assessment.

```python
result = check_risk_limits(account)
# Returns:
# {
#     'all_clear': True/False,
#     'breached_limits': [...],
#     'warnings': [...],
#     'action_required': 'NONE' | 'WARNING' | 'STOP_TRADING' | 'EMERGENCY_EXIT',
#     'message': 'All limits OK'
# }
```

#### check_daily_loss_limit(account)

Checks today's P&L against daily limit.

```python
result = check_daily_loss_limit(account)
# Returns:
# {
#     'breached': True/False,
#     'warning': True/False,
#     'current_loss': Decimal('35000'),
#     'limit': Decimal('50000'),
#     'utilization_pct': 70
# }
```

#### activate_circuit_breaker(account, trigger_type, trigger_value, threshold_value)

**CRITICAL FUNCTION** - Automatic account shutdown.

```python
success, circuit_breaker = activate_circuit_breaker(
    account=account,
    trigger_type='DAILY_LOSS',
    trigger_value=55000,
    threshold_value=50000
)

# What happens:
# 1. Creates CircuitBreaker record
# 2. Closes ALL active positions at current price
# 3. Cancels all pending orders
# 4. Deactivates account (is_active = False)
# 5. Sets 24-hour cooldown
# 6. Sends CRITICAL Telegram alert
```

#### enforce_risk_limits(account)

Main enforcement function, called regularly.

```python
trading_allowed, message = enforce_risk_limits(account)

# Checks:
# 1. Is account already deactivated?
# 2. Is there an active circuit breaker?
# 3. Has cooldown expired?
# 4. Are any limits breached?

# If breached:
#   - Activates circuit breaker
#   - Returns (False, "Circuit breaker activated")

# If OK:
#   - Returns (True, "Trading allowed")
```

#### get_risk_status(account)

Dashboard-style risk overview.

```python
status = get_risk_status(account)
# Returns:
# {
#     'account': account_name,
#     'limits': [
#         {'type': 'DAILY_LOSS', 'limit': 50000, 'current': 35000, 'utilization': 70},
#         {'type': 'WEEKLY_LOSS', 'limit': 150000, 'current': 80000, 'utilization': 53},
#     ],
#     'breached': [],
#     'warnings': ['DAILY_LOSS approaching limit (70%)'],
#     'active_circuit_breakers': [],
#     'trading_allowed': True
# }
```

---

## Circuit Breaker Flow

```
Normal Trading
      ↓
Loss exceeds limit (e.g., daily loss > Rs 50,000)
      ↓
activate_circuit_breaker() called
      ↓
1. Create CircuitBreaker record
   - trigger_type = 'DAILY_LOSS'
   - trigger_value = -55000
   - threshold_value = 50000
      ↓
2. Close ALL active positions
   - For each active position:
     - Close at current market price
     - Record exit reason: "Circuit breaker"
   - positions_closed = count
      ↓
3. Cancel pending orders
   - orders_cancelled = count
      ↓
4. Deactivate account
   - account.is_active = False
   - account.save()
      ↓
5. Set cooldown
   - cooldown_until = now + 24 hours
      ↓
6. Send CRITICAL alert
   - 🚨🚨🚨 CIRCUIT BREAKER ACTIVATED
      ↓
Account locked for 24 hours
      ↓
After cooldown:
   - Manual reset required
   - Check trading conditions
   - Re-enable if appropriate
```

---

## Celery Tasks

| Task | Frequency | Purpose |
|------|-----------|---------|
| `check_risk_limits_all_accounts` | Every 1 min | Check all accounts |
| `monitor_circuit_breakers` | Every 30 sec | Monitor active breakers |
| `generate_daily_risk_report` | 6:00 PM | End-of-day report |

### check_risk_limits_all_accounts

```python
@shared_task
def check_risk_limits_all_accounts():
    for account in BrokerAccount.objects.filter(is_active=True):
        result = check_risk_limits(account)

        if result['breached_limits']:
            # Activate circuit breaker
            activate_circuit_breaker(account, ...)

        if result['warnings']:
            # Send warning alert
            send_warning(account, result['warnings'])
```

### monitor_circuit_breakers

```python
@shared_task
def monitor_circuit_breakers():
    for breaker in CircuitBreaker.objects.filter(is_active=True):
        # Check cooldown
        if timezone.now() > breaker.cooldown_until:
            send_reminder("Cooldown expired, manual reset required")

        # Long-running breaker reminder
        if breaker.created_at < timezone.now() - timedelta(hours=24):
            send_reminder("Circuit breaker active for 24+ hours")
```

---

## Risk Limits

### Daily Loss Limit

- **Default**: Based on `account.max_daily_loss`
- **Example**: Rs 50,000
- **Reset**: Daily at midnight
- **Breach Action**: Circuit breaker activation

### Weekly Loss Limit

- **Default**: Based on `account.max_weekly_loss`
- **Example**: Rs 150,000
- **Reset**: Weekly (Monday midnight)
- **Breach Action**: Circuit breaker activation

### Warning Threshold

- **Default**: 80% of limit
- **Action**: Telegram warning sent
- **Purpose**: Early warning before breach

---

## Admin Interface

Access at `/admin/risk/` to:

- View risk limits and utilization
- See active circuit breakers
- Manually reset circuit breakers (after cooldown)
- Review breach history

---

## How to Study This App

1. **Start with `models.py`** - Understand RiskLimit and CircuitBreaker
2. **Read `risk_manager.py`** - Core enforcement logic
3. **Study `activate_circuit_breaker`** - Critical protection function
4. **Check `tasks.py`** - Automated monitoring
5. **Review admin interface** - Management tools

---

## Common Tasks for Developers

### Adjust Risk Limits

```python
# Via Django shell
from apps.accounts.models import BrokerAccount

account = BrokerAccount.objects.get(broker='KOTAK')
account.max_daily_loss = 75000  # Increase daily limit
account.max_weekly_loss = 200000
account.save()
```

### Manually Reset Circuit Breaker

```python
from apps.risk.models import CircuitBreaker

breaker = CircuitBreaker.objects.get(id=123)
breaker.reset_breaker(reset_by='admin')

# Also re-enable account
breaker.account.is_active = True
breaker.account.save()
```

### Add New Risk Type

1. Add to `LIMIT_TYPE_CHOICES` in `models.py`
2. Add check in `risk_manager.py`
3. Add to `check_risk_limits()` function
4. Test thoroughly

---

## Key Safety Features

1. **Automatic Position Closure** - No manual intervention needed
2. **Account Deactivation** - Prevents further losses
3. **24-Hour Cooldown** - Enforces reflection period
4. **Manual Reset Required** - Ensures conscious decision to continue
5. **Audit Trail** - Complete log of actions taken
6. **Alerts** - Immediate notification of breach

---

## Important Notes

1. **Circuit breakers CANNOT be overridden programmatically**
2. **Cooldown is enforced** - Even admin must wait or explicitly override
3. **Position closure is at market price** - May incur slippage
4. **All active positions closed** - No selective closure
5. **Email/SMS alerts** - Prepared but not implemented (Telegram only)

---

*For questions, check the code comments or ask the team.*
