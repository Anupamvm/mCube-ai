# Logging and Error Handling Guide

Comprehensive guide for logging, error handling, and monitoring in the mCube Trading System.

---

## Table of Contents

1. [Logging Architecture](#logging-architecture)
2. [Logging Levels and When to Use](#logging-levels)
3. [Log File Structure](#log-file-structure)
4. [Error Handling Patterns](#error-handling-patterns)
5. [UI vs Backend Logging](#ui-vs-backend-logging)
6. [Monitoring and Alerts](#monitoring-and-alerts)
7. [Best Practices](#best-practices)

---

## Logging Architecture

The system uses a **dual-channel logging strategy**:

1. **Backend Logs** → File system (`logs/mcube_ai.log`)
   - Detailed technical logs
   - Debug information
   - System state changes
   - Performance metrics

2. **UI Notifications** → Telegram
   - User-facing alerts
   - Critical events requiring action
   - Daily/weekly summaries
   - Position status updates

### Logging Configuration

Configured in `mcube_ai/settings.py`:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            # Includes timestamp, module, process/thread IDs
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            # Simpler format for console output
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'mcube_ai.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
        },
        'celery': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',  # Detailed logging for our apps
        },
    },
}
```

---

## Logging Levels and When to Use

### DEBUG (`logger.debug()`)
**When:** Detailed diagnostic information

```python
logger.debug(f"Calculating delta for position {position.id}...")
logger.debug(f"Strike selection: spot={spot}, vix={vix}, delta={delta}")
```

**Use cases:**
- Variable values during calculations
- Function entry/exit
- Intermediate calculation steps
- Not critical for production monitoring

### INFO (`logger.info()`)
**When:** Normal system operations and milestones

```python
logger.info("=" * 80)
logger.info("CELERY TASK: Kotak Strangle Entry Evaluation")
logger.info(f"✅ Filters passed: {len(filters_passed)}")
logger.info(f"Strike Distance: {strike_distance:.2f} points")
```

**Use cases:**
- Task start/completion
- Successful operations
- System state changes
- Filter results
- Position updates

### WARNING (`logger.warning()`)
**When:** Unexpected but non-critical issues

```python
logger.warning(f"⚠️ RISK WARNING: {account.account_name}")
logger.warning(f"Trading paused via Telegram bot command")
logger.warning("Insufficient margin for new position")
```

**Use cases:**
- Risk limit warnings (not breaches)
- Skipped trades due to filters
- Non-critical API failures with retry
- Configuration issues

### ERROR (`logger.error()`)
**When:** Errors that need attention but don't crash the system

```python
logger.error(f"Error monitoring position {position.id}: {e}")
logger.error(f"❌ Strike calculation failed: {str(e)}", exc_info=True)
logger.error(f"Failed to close position {position.instrument}: {str(e)}")
```

**Use cases:**
- Caught exceptions in try/except blocks
- Failed API calls
- Database errors
- Order placement failures

**Important:** Always use `exc_info=True` to capture stack trace

### CRITICAL (`logger.critical()`)
**When:** Severe errors requiring immediate action

```python
logger.critical(f"🚨 RISK LIMIT BREACH: {account.account_name}")
logger.critical(f"Circuit breaker activated: {trigger_type}")
logger.critical(f"Account deactivated: {account.account_name}")
```

**Use cases:**
- Risk limit breaches
- Circuit breaker activations
- System-wide failures
- Data corruption

---

## Log File Structure

### Location
```
/Users/anupammangudkar/Projects/mCube-ai/mCube-ai/logs/mcube_ai.log
```

### Format
```
INFO 2025-11-15 14:30:45,123 positions.tasks 12345 67890 CELERY TASK: Monitor All Positions
INFO 2025-11-15 14:30:45,456 positions.tasks 12345 67890 ✅ Positions monitored: 2
WARNING 2025-11-15 14:31:00,789 risk.tasks 12345 67890 ⚠️ RISK WARNING: Kotak Primary
ERROR 2025-11-15 14:32:15,234 strategies.tasks 12345 67890 Error fetching market data: ConnectionTimeout
```

### Log Rotation (TODO - Not yet implemented)

For production, implement log rotation to prevent disk space issues:

```python
# In settings.py, replace FileHandler with RotatingFileHandler
'file': {
    'class': 'logging.handlers.RotatingFileHandler',
    'filename': BASE_DIR / 'logs' / 'mcube_ai.log',
    'formatter': 'verbose',
    'maxBytes': 10485760,  # 10MB
    'backupCount': 10,  # Keep 10 backup files
},
```

---

## Error Handling Patterns

### Pattern 1: Celery Task Error Handling

**All Celery tasks follow this pattern:**

```python
@shared_task(name='apps.positions.tasks.monitor_all_positions')
def monitor_all_positions():
    """Monitor all active positions"""
    try:
        # Task logic here
        active_positions = Position.objects.filter(status='ACTIVE')

        for position in active_positions:
            try:
                # Individual position processing
                update_position_price(position, current_price)

            except Exception as e:
                # Log error but continue with other positions
                logger.error(f"Error monitoring position {position.id}: {e}")

        # Return success result
        return {
            'success': True,
            'positions_monitored': monitored_count,
            'timestamp': timezone.now().isoformat()
        }

    except Exception as e:
        # Outer catch for catastrophic failures
        logger.error(f"Error in position monitoring: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}
```

**Key Points:**
- ✅ Outer try/except catches task-level failures
- ✅ Inner try/except for loop items prevents one failure from stopping all
- ✅ Always return dict with `success` key for monitoring
- ✅ Use `exc_info=True` for stack traces

### Pattern 2: Strategy Execution Error Handling

**Entry/exit strategies use detailed logging:**

```python
def execute_kotak_strangle_entry(account: BrokerAccount) -> Dict:
    """Execute Kotak strangle entry workflow"""

    logger.info("=" * 100)
    logger.info("KOTAK STRANGLE ENTRY WORKFLOW")
    logger.info("=" * 100)

    # STEP 1: Check existing position
    logger.info("STEP 1: Morning Check (ONE POSITION RULE)")
    logger.info("-" * 80)

    try:
        existing_position = Position.get_active_position(account)

        if existing_position:
            msg = f"Account already has active position #{existing_position.id}"
            logger.warning(f"⚠️ {msg}")
            return {'success': False, 'message': msg}

        logger.info(f"✅ No active position - proceed with entry")
        logger.info("")

    except Exception as e:
        msg = f"❌ Error checking existing position: {str(e)}"
        logger.error(msg, exc_info=True)
        return {'success': False, 'message': msg, 'details': {'error': str(e)}}

    # Continue with other steps...
```

**Key Points:**
- ✅ Clear section headers with separators
- ✅ Emoji for quick visual scanning (✅ success, ❌ error, ⚠️ warning)
- ✅ Each step in try/except
- ✅ Return structured dict with error details

### Pattern 3: Transaction Safety with Logging

**Database operations use atomic transactions:**

```python
from django.db import transaction

@transaction.atomic
def execute_averaging(position: Position, current_price: Decimal) -> Tuple[bool, str, Dict]:
    """Execute averaging (add to position)"""

    logger.info(f"=" * 80)
    logger.info(f"EXECUTING AVERAGING - Position {position.id}")
    logger.info(f"=" * 80)

    try:
        # All database changes happen atomically
        original_quantity = position.quantity

        # ... calculation logic ...

        # Update position (will rollback if exception occurs)
        position.quantity = new_total_quantity
        position.entry_price = new_average_price
        position.save()

        logger.info(f"AVERAGING EXECUTED:")
        logger.info(f"  New Quantity: {new_total_quantity}")
        logger.info(f"  New Average: ₹{new_average_price:,.2f}")
        logger.info("")

        # Send alert
        send_telegram_notification(message, notification_type='WARNING')

        return True, "Averaging executed successfully", {...}

    except Exception as e:
        # Transaction automatically rolls back
        logger.error(f"Averaging failed: {e}", exc_info=True)
        return False, f"Error: {str(e)}", {}
```

**Key Points:**
- ✅ `@transaction.atomic` ensures all-or-nothing database changes
- ✅ Log before and after critical operations
- ✅ Return tuple with (success, message, details)

---

## UI vs Backend Logging

### Backend Logs (File)

**What goes here:**
- All DEBUG, INFO, WARNING, ERROR, CRITICAL logs
- Detailed variable values
- Stack traces
- Performance metrics
- System state changes

**Example:**
```python
# Detailed backend logging
logger.debug(f"Moneyness ratio: {moneyness:.4f}")
logger.debug(f"Call delta: {call_delta}, Put delta: {put_delta}")
logger.info(f"Net delta: {net_delta:.2f} (threshold: {delta_threshold})")
logger.info(f"Strike distance: {strike_distance:.2f} points")
```

### UI Notifications (Telegram)

**What goes here:**
- User-actionable alerts
- Critical events
- Summary reports
- Position status updates

**Example:**
```python
# User-facing Telegram notification
send_telegram_notification(
    f"🚨 CIRCUIT BREAKER ACTIVATED\n\n"
    f"Account: {account.account_name}\n"
    f"Reason: Daily loss limit breached\n\n"
    f"ACTIONS TAKEN:\n"
    f"✅ All positions closed\n"
    f"✅ Account deactivated\n\n"
    f"⚠️ IMMEDIATE ATTENTION REQUIRED",
    notification_type='ERROR'
)
```

### Decision Matrix: Log vs Notify

| Event | Backend Log | Telegram Notify |
|-------|-------------|----------------|
| Task started | ✅ INFO | ❌ |
| Filter failed | ✅ WARNING | ❌ |
| Position entered | ✅ INFO | ✅ SUCCESS |
| Position closed | ✅ INFO | ✅ INFO |
| SL/Target hit | ✅ WARNING | ✅ WARNING |
| Risk warning (80%) | ✅ WARNING | ✅ WARNING |
| Risk breach (100%) | ✅ CRITICAL | ✅ ERROR |
| Circuit breaker | ✅ CRITICAL | ✅ ERROR |
| Daily P&L report | ✅ INFO | ✅ INFO |
| API error | ✅ ERROR | ❌ |
| Calculation error | ✅ ERROR | ❌ |

**Rule of Thumb:**
- If user needs to **know** → Telegram
- If user needs to **act** → Telegram (high priority)
- If developer needs to **debug** → Backend log only
- If both need to know → Both

---

## Monitoring and Alerts

### Real-time Monitoring

**1. Tail logs in real-time:**
```bash
tail -f logs/mcube_ai.log
```

**2. Filter specific levels:**
```bash
# Only errors and critical
tail -f logs/mcube_ai.log | grep -E "ERROR|CRITICAL"

# Specific module
tail -f logs/mcube_ai.log | grep "positions.tasks"

# Specific pattern
tail -f logs/mcube_ai.log | grep -i "circuit breaker"
```

**3. Monitor Celery tasks:**
```bash
# Celery logs only
tail -f logs/mcube_ai.log | grep "CELERY TASK"

# Task failures
tail -f logs/mcube_ai.log | grep "CELERY TASK" | grep "ERROR"
```

### Alert Triggers

**Telegram notifications are sent for:**

1. **Position Events:**
   - New position entered
   - Position closed (SL/Target/Manual/EOD)
   - Position averaged
   - Delta threshold exceeded (|delta| > 300)

2. **Risk Events:**
   - Risk limit warning (80% threshold)
   - Risk limit breach (100% threshold)
   - Circuit breaker activation
   - Circuit breaker cooldown expiry

3. **Strategy Events:**
   - Entry skipped (filter failed, but not logged to Telegram)
   - Exit executed automatically
   - Manual intervention required

4. **Reports:**
   - Daily P&L report (4:00 PM)
   - Weekly summary (Friday 6:00 PM)
   - Risk summary (on request)

### Log Analysis

**Find all position entries today:**
```bash
grep "POSITION ENTERED" logs/mcube_ai.log | grep "$(date +%Y-%m-%d)"
```

**Find all circuit breaker activations:**
```bash
grep "CIRCUIT BREAKER ACTIVATED" logs/mcube_ai.log
```

**Count errors in last hour:**
```bash
# Get logs from last hour and count ERRORs
tail -n 10000 logs/mcube_ai.log | grep "ERROR" | wc -l
```

**Find specific position activity:**
```bash
# All logs for position #42
grep "Position #42\|position 42\|Position: #42" logs/mcube_ai.log
```

---

## Best Practices

### 1. **Use Structured Logging**

```python
# ❌ Poor - hard to parse
logger.info(f"Position closed, P&L is {pnl}")

# ✅ Good - structured, easy to parse
logger.info(f"Position closed: #{position.id}, "
            f"Instrument: {position.instrument}, "
            f"P&L: ₹{pnl:,.0f}, "
            f"Duration: {duration} hours")
```

### 2. **Log Context, Not Just Events**

```python
# ❌ Poor - no context
logger.error("Order placement failed")

# ✅ Good - includes context
logger.error(f"Order placement failed: "
             f"Symbol: {symbol}, "
             f"Qty: {quantity}, "
             f"Price: ₹{price}, "
             f"Error: {str(e)}")
```

### 3. **Use Emoji for Visual Scanning**

```python
# Easy to spot in logs
logger.info("✅ All filters passed")
logger.warning("⚠️ Risk warning threshold reached")
logger.error("❌ Position close failed")
logger.critical("🚨 Circuit breaker activated")
```

### 4. **Always Include Exception Info**

```python
# ❌ Poor - no stack trace
except Exception as e:
    logger.error(f"Error: {str(e)}")

# ✅ Good - includes full stack trace
except Exception as e:
    logger.error(f"Error processing data: {str(e)}", exc_info=True)
```

### 5. **Log Entry and Exit of Critical Functions**

```python
def execute_kotak_strangle_entry(account):
    logger.info("=" * 80)
    logger.info("KOTAK STRANGLE ENTRY WORKFLOW STARTED")
    logger.info("=" * 80)

    try:
        # ... workflow logic ...

        logger.info("=" * 80)
        logger.info("✅ ENTRY WORKFLOW COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
        return {'success': True, ...}

    except Exception as e:
        logger.error("❌ ENTRY WORKFLOW FAILED", exc_info=True)
        logger.info("=" * 80)
        return {'success': False, ...}
```

### 6. **Don't Log Sensitive Data**

```python
# ❌ NEVER log credentials or API keys
logger.info(f"API Key: {api_key}")

# ✅ Good - mask sensitive data
logger.info(f"API Key: {api_key[:4]}...{api_key[-4:]}")

# ✅ Better - don't log at all
logger.info("API authentication successful")
```

### 7. **Use Appropriate Log Levels**

```python
# ❌ Poor - everything is ERROR
logger.error("Task started")
logger.error("Filter passed")
logger.error("Position entered")

# ✅ Good - appropriate levels
logger.info("Task started")
logger.info("Filter passed")
logger.info("Position entered")
logger.warning("Risk limit approaching")
logger.error("API call failed")
logger.critical("Circuit breaker activated")
```

---

## Task-Specific Logging

### Position Monitoring Tasks

**Monitor All Positions:**
```python
logger.info("CELERY TASK: Monitor All Positions")
logger.info(f"Active positions found: {active_positions.count()}")

for position in active_positions:
    logger.debug(f"Monitoring position #{position.id}: {position.instrument}")
    # ... update logic ...
    logger.info(f"✅ Position #{position.id} updated")

logger.info(f"✅ Monitored {monitored_count} positions")
```

**Update P&L:**
```python
logger.info("CELERY TASK: Update Position P&L")

for position in active_positions:
    pnl = calculate_pnl(position)
    logger.debug(f"Position #{position.id} P&L: ₹{pnl:,.0f}")

    # Alert on significant P&L
    if pnl_pct > 5:
        logger.warning(f"🎉 Large profit: Position #{position.id}, P&L: {pnl_pct:.1f}%")
        send_telegram_notification(...)  # Notify user
    elif pnl_pct < -3:
        logger.warning(f"⚠️ Large loss: Position #{position.id}, P&L: {pnl_pct:.1f}%")
        send_telegram_notification(...)  # Notify user

logger.info(f"✅ Updated P&L for {updated_count} positions, {alerts_sent} alerts sent")
```

### Risk Monitoring Tasks

**Check Risk Limits:**
```python
logger.info("CELERY TASK: Risk Limits Check - All Accounts")

for account in active_accounts:
    logger.info(f"Checking risk limits for: {account.account_name}")

    risk_check = check_risk_limits(account)

    if risk_check['breached_limits']:
        logger.critical(f"🚨 RISK BREACH: {account.account_name}")
        # Log each breached limit
        for limit in risk_check['breached_limits']:
            logger.critical(f"  {limit.limit_type}: ₹{limit.current_value:,.0f} / ₹{limit.limit_value:,.0f}")

        # Enforce and notify
        enforce_risk_limits(account)
        send_telegram_notification(...)

    elif risk_check['warnings']:
        logger.warning(f"⚠️ RISK WARNING: {account.account_name}")
        # Log warnings
        for limit in risk_check['warnings']:
            logger.warning(f"  {limit.limit_type}: {limit.get_utilization_pct():.1f}%")
    else:
        logger.info(f"✅ All risk limits OK for {account.account_name}")

logger.info(f"✅ Risk check complete: {accounts_checked} accounts")
```

### Strategy Evaluation Tasks

**Kotak Strangle Entry:**
```python
logger.info("=" * 80)
logger.info("CELERY TASK: Kotak Strangle Entry Evaluation")
logger.info("=" * 80)

logger.info(f"Account: {account.account_name}")

# Execute entry
result = execute_kotak_strangle_entry(account)

if result['success']:
    logger.info(f"✅ ENTRY SUCCESSFUL: Position #{result['position'].id}")
    send_telegram_notification(...)  # Notify user
else:
    logger.info(f"ℹ️ ENTRY SKIPPED: {result['message']}")
    # No Telegram notification for skipped entries (too noisy)

logger.info("=" * 80)
```

---

## Summary

### Logging Checklist

- ✅ **All Celery tasks** log start/completion with counts
- ✅ **All errors** include `exc_info=True` for stack traces
- ✅ **Critical operations** (position entry/exit, averaging) have detailed logging
- ✅ **Risk events** log to file AND send Telegram alerts
- ✅ **User events** (manual closes, pause/resume) are logged
- ✅ **Performance metrics** (tasks monitored, alerts sent) are included in return dicts

### Notification Checklist

- ✅ **Position events** send Telegram notifications
- ✅ **Risk warnings** send Telegram alerts
- ✅ **Circuit breakers** send CRITICAL Telegram alerts
- ✅ **Daily/weekly reports** send summary notifications
- ✅ **Manual actions** (via bot) confirm via Telegram

### Monitoring Commands

```bash
# Real-time monitoring
tail -f logs/mcube_ai.log

# Errors only
tail -f logs/mcube_ai.log | grep ERROR

# Specific task
tail -f logs/mcube_ai.log | grep "positions.tasks"

# Circuit breakers
grep "CIRCUIT BREAKER" logs/mcube_ai.log

# Today's activity
grep "$(date +%Y-%m-%d)" logs/mcube_ai.log

# Count errors
grep "ERROR" logs/mcube_ai.log | wc -l
```

---

**For more information:**
- Django Logging: https://docs.djangoproject.com/en/4.2/topics/logging/
- Python Logging: https://docs.python.org/3/library/logging.html
- Celery Logging: https://docs.celeryproject.org/en/stable/userguide/tasks.html#logging
