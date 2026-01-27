# Alerts App Documentation

**Location**: `apps/alerts/`

The alerts app handles all notifications via Telegram. It includes an interactive bot for system control and alert delivery.

---

## What This App Does

1. **Telegram Bot** - Interactive bot with 14 commands
2. **Alert Delivery** - Sends notifications for trades, risks, P&L
3. **Trade Approval** - Approve/reject trades via Telegram
4. **System Control** - Pause/resume trading remotely

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | Alert and AlertLog models |
| `services/telegram_bot.py` | Interactive bot handler (39KB) |
| `services/telegram_client.py` | Low-level Telegram API |
| `services/alert_manager.py` | Alert orchestration |
| `services/telegram_helpers.py` | Async database helpers |
| `services/telegram_trade_notifier.py` | Trade notification formatting |
| `admin.py` | Django admin interface |
| `management/commands/run_telegram_bot.py` | Bot start command |

---

## Key Models

### Alert

Stores alert notifications.

```python
# Fields
account = ForeignKey(BrokerAccount, nullable)
priority = CharField()           # CRITICAL, HIGH, MEDIUM, LOW, INFO
alert_type = CharField()         # POSITION_ENTERED, SL_HIT, TARGET_HIT, etc.
title = CharField()
message = TextField()
position = ForeignKey(Position, nullable)
order = ForeignKey(Order, nullable)

# Delivery Status
send_telegram = BooleanField()
telegram_sent = BooleanField()
telegram_sent_at = DateTimeField()

send_email = BooleanField()
email_sent = BooleanField()

send_sms = BooleanField()
sms_sent = BooleanField()

# Action Tracking
requires_action = BooleanField()
action_taken = TextField()

# Metadata
metadata = JSONField()
```

### AlertLog

Audit trail for delivery attempts.

```python
# Fields
alert = ForeignKey(Alert)
channel = CharField()            # TELEGRAM, EMAIL, SMS
status = CharField()             # SUCCESS, FAILED, PENDING
response = TextField()           # API response
error_message = TextField()      # Error if failed
retry_count = IntegerField()
```

---

## Telegram Bot Commands

### System Status

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | List all commands |
| `/status` | System overview (trading status, accounts, positions) |
| `/accounts` | Account balances and margin |
| `/logs` | Recent system logs (last 20 lines) |

### Position Management

| Command | Description |
|---------|-------------|
| `/positions` | All active positions (live from broker) |
| `/position <id>` | Specific position details |
| `/close <id>` | Close specific position (with confirmation) |
| `/closeall` | Emergency close all positions |

### P&L Tracking

| Command | Description |
|---------|-------------|
| `/pnl` | Today's P&L summary |
| `/pnl_week` | This week's P&L |

### Risk Management

| Command | Description |
|---------|-------------|
| `/risk` | Risk limits and utilization |
| `/pause` | Pause automated trading |
| `/resume` | Resume trading |

---

## Starting the Bot

```bash
# Via management command
python manage.py run_telegram_bot

# The bot runs continuously
# Press Ctrl+C to stop
```

---

## Bot Architecture

```
User sends message
      ↓
TelegramBotHandler receives
      ↓
Check authorization (chat ID)
      ↓
Parse command
      ↓
Execute handler (async)
├── Database queries (@sync_to_async)
├── Broker API calls (if needed)
└── Format response (HTML)
      ↓
Send reply to user
```

---

## Alert Types

| Type | Priority | Description |
|------|----------|-------------|
| `POSITION_ENTERED` | MEDIUM | New position opened |
| `POSITION_CLOSED` | HIGH | Position closed |
| `SL_HIT` | CRITICAL | Stop-loss triggered |
| `TARGET_HIT` | HIGH | Target achieved |
| `DELTA_ALERT` | MEDIUM | Delta threshold exceeded |
| `CIRCUIT_BREAKER` | CRITICAL | Circuit breaker activated |
| `RISK_WARNING` | HIGH | Risk limit approaching |
| `DAILY_LOSS_LIMIT` | CRITICAL | Daily loss limit hit |
| `WEEKLY_LOSS_LIMIT` | CRITICAL | Weekly loss limit hit |
| `DAILY_SUMMARY` | INFO | End-of-day summary |
| `SYSTEM_ERROR` | HIGH | System error occurred |

---

## Sending Alerts

### Using Alert Manager

```python
from apps.alerts.services.alert_manager import AlertManager

manager = AlertManager()

# Position alert
manager.create_position_alert(
    account=account,
    position=position,
    alert_type='POSITION_ENTERED',
    priority='MEDIUM',
)

# Risk alert
manager.create_risk_alert(
    account=account,
    alert_type='RISK_WARNING',
    risk_data={'utilization': 85},
)

# Daily summary
manager.create_daily_summary_alert(summary_data={...})

# System alert
manager.create_system_alert(
    alert_type='SYSTEM_ERROR',
    title='Database Error',
    message='Connection lost',
)
```

### Using Telegram Client Directly

```python
from apps.alerts.services.telegram_client import TelegramClient

client = TelegramClient()

# Simple message
client.send_message("Hello from mCube!")

# Priority message (with emoji)
client.send_priority_message(
    message="Stop-loss hit!",
    priority='CRITICAL'  # Adds 🚨🚨🚨
)

# Position alert
client.send_position_alert(position_data={...})

# Daily summary
client.send_daily_summary(summary_data={...})
```

---

## Trade Notifications

For trade suggestions requiring approval:

```python
from apps.alerts.services.telegram_trade_notifier import TelegramTradeNotifier

notifier = TelegramTradeNotifier()

# Send trade notification with approval buttons
message, keyboard = notifier.format_futures_trade_notification(
    suggestion=suggestion,
    analysis_result=result,
)

# Message includes:
# - Trade details (symbol, direction, entry)
# - Entry signal analysis
# - OI analysis
# - Sector analysis
# - Technical indicators
# - AI validation result
# - Risk scenarios

# Buttons:
# ✅ APPROVE & EXECUTE
# ❌ REJECT
# 📊 VIEW FULL ANALYSIS
```

---

## Async Helpers

Database operations in the bot use async wrappers:

```python
from apps.alerts.services.telegram_helpers import (
    get_position_by_id,
    get_active_positions_list,
    get_risk_data,
    get_pnl_data,
    close_position_sync,
    fetch_live_positions,
)

# Example in bot handler
@sync_to_async
def get_position_by_id(position_id):
    return Position.objects.get(id=position_id)

# Usage
position = await get_position_by_id(123)
```

---

## Live Position Fetching

The bot fetches live positions from brokers:

```python
# /positions command
async def handle_positions(self, update, context):
    # Fetch from both brokers
    positions = await fetch_live_positions()

    # Sync to database (updates existing, creates new)
    # Auto-closes positions that no longer exist in broker
```

---

## Configuration

### Credentials

Store in `CredentialStore` with `service='telegram'`:

```python
# Required fields
api_key = "BOT_TOKEN"    # Telegram Bot Token
username = "CHAT_ID"     # Authorized chat ID
```

Or via environment variables:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Authorization

Only authorized chat IDs can use the bot:

```python
def is_authorized(self, chat_id):
    if self.authorized_chat_ids:
        return str(chat_id) in self.authorized_chat_ids
    # Development mode: allow all (with warning)
    return True
```

---

## Retry Mechanism

Failed alerts are retried:

```python
manager = AlertManager()

# Retry failed alerts (max 3 attempts)
manager.retry_failed_alerts()
```

This is typically called by a Celery task periodically.

---

## How to Study This App

1. **Start with `models.py`** - Understand Alert structure
2. **Read `telegram_bot.py`** - Learn the command handlers
3. **Study `alert_manager.py`** - Alert creation flow
4. **Check `telegram_helpers.py`** - Async patterns
5. **Review `telegram_trade_notifier.py`** - Trade notifications

---

## Common Tasks for Developers

### Add New Bot Command

1. Add handler in `telegram_bot.py`:
   ```python
   async def handle_new_command(self, update, context):
       # Your logic here
       await update.message.reply_text("Response")
   ```

2. Register in `__init__`:
   ```python
   self.application.add_handler(
       CommandHandler("newcommand", self.handle_new_command)
   )
   ```

### Add New Alert Type

1. Add to `ALERT_TYPE_CHOICES` in `models.py`
2. Add handler in `alert_manager.py`
3. Add formatting in `telegram_client.py` if needed

### Customize Message Format

Edit the formatting methods in:
- `telegram_client.py` for general alerts
- `telegram_trade_notifier.py` for trade-specific

---

## Priority Emojis

| Priority | Emoji |
|----------|-------|
| CRITICAL | 🚨🚨🚨 |
| HIGH | ⚠️ |
| MEDIUM | 📌 |
| LOW | ℹ️ |
| INFO | ✅ |

---

*For questions, check the code comments or ask the team.*
