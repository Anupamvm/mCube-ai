# Telegram Notifications Setup Guide

This guide explains how to set up Telegram notifications for mCube Trading System.

## Overview

The Telegram integration sends real-time notifications for:
- **Position Events**: Entry, exit, stop-loss hits, target hits
- **Risk Alerts**: Daily/weekly loss limits, circuit breakers
- **Daily Summaries**: P&L, trade statistics, performance metrics
- **System Alerts**: Errors, warnings, and important system events

## Prerequisites

- A Telegram account
- Access to create a Telegram bot

## Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Start a chat and send `/newbot`
3. Follow the prompts:
   - Choose a name for your bot (e.g., "mCube Trading Bot")
   - Choose a username (must end in 'bot', e.g., "mcube_trading_bot")
4. BotFather will give you a **Bot Token** - save this securely
   ```
   Example: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

## Step 2: Get Your Chat ID

### Method 1: Using @userinfobot
1. Search for **@userinfobot** in Telegram
2. Start a chat with it
3. It will send your **Chat ID** (a number like `123456789`)

### Method 2: Using @RawDataBot
1. Search for **@RawDataBot** in Telegram
2. Send it any message
3. Look for `"chat":{"id":123456789}` in the response

### Method 3: For Group Chats
1. Add your bot to the group
2. Send a message in the group
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Look for `"chat":{"id":-123456789}` (note the negative sign for groups)

## Step 3: Configure Environment Variables

1. Copy `.env.example` to `.env` if you haven't already:
   ```bash
   cp .env.example .env
   ```

2. Add your Telegram credentials to `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_CHAT_ID=123456789
   ```

## Step 4: Test the Integration

Run the test command to verify everything is working:

```bash
python manage.py test_telegram
```

This will send a simple test message. If you see:
```
✅ Telegram client configured
✅ Message sent: Message sent successfully
```

Your Telegram integration is working!

### Send All Test Messages

To test all notification types:

```bash
python manage.py test_telegram --send-all
```

This will send:
1. Simple notification
2. Position entry alert
3. Stop-loss hit alert
4. Target hit alert
5. Risk management alert
6. Circuit breaker alert
7. Daily trading summary
8. AlertManager integration test

## Usage in Code

### Sending Alerts via AlertManager

```python
from apps.alerts.services import send_position_alert, send_risk_alert

# Send position alert
send_position_alert(
    position=position_instance,
    alert_type='POSITION_ENTERED',
    priority='MEDIUM'
)

# Send risk alert
send_risk_alert(
    account=account_instance,
    alert_type='DAILY_LOSS_LIMIT',
    priority='HIGH',
    risk_data={'action_required': 'WARNING'}
)
```

### Direct Telegram Client Usage

```python
from apps.alerts.services import get_telegram_client

client = get_telegram_client()

# Send simple message
success, response = client.send_message(
    "Test message",
    parse_mode='HTML'
)

# Send priority message
success, response = client.send_priority_message(
    "Critical alert!",
    priority='CRITICAL'
)
```

## Alert Types and Priorities

### Alert Types
- **POSITION_ENTERED**: New position opened
- **POSITION_CLOSED**: Position closed
- **SL_HIT**: Stop-loss triggered (CRITICAL)
- **TARGET_HIT**: Target achieved
- **DELTA_ALERT**: Delta threshold exceeded
- **CIRCUIT_BREAKER**: Emergency shutdown (CRITICAL)
- **DAILY_LOSS_LIMIT**: Daily loss limit warning
- **WEEKLY_LOSS_LIMIT**: Weekly loss limit warning
- **DAILY_SUMMARY**: End-of-day summary (INFO)
- **SYSTEM_ERROR**: System errors

### Priority Levels
- **CRITICAL** 🚨🚨🚨: Immediate action required (e.g., stop-loss, circuit breaker)
- **HIGH** ⚠️: Important alerts requiring attention
- **MEDIUM** 📌: Regular notifications
- **LOW** ℹ️: Informational messages
- **INFO** ✅: Status updates, summaries

## Message Formatting

### HTML Formatting (Recommended)
```python
message = """
<b>Position Entered</b>
<i>NIFTY 24000 CE</i>

Entry: Rs.100.00
Target: Rs.30.00
"""

client.send_message(message, parse_mode='HTML')
```

### Markdown Formatting
```python
message = """
*Position Entered*
_NIFTY 24000 CE_

Entry: Rs.100.00
Target: Rs.30.00
"""

client.send_message(message, parse_mode='Markdown')
```

## Troubleshooting

### Bot Not Sending Messages

1. **Check bot token**:
   ```bash
   curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe
   ```
   Should return bot information.

2. **Check chat ID**:
   - Make sure you've started a chat with your bot
   - For groups, ensure the bot is added as a member

3. **Check logs**:
   ```bash
   # Django logs will show errors
   tail -f logs/django.log
   ```

### Messages Not Reaching You

1. **Check if bot is blocked**: Unblock the bot in Telegram
2. **Check privacy settings**: Ensure you can receive messages from bots
3. **For groups**: Make sure bot has permission to send messages

### Rate Limiting

Telegram has rate limits:
- **30 messages per second** per bot
- **20 messages per minute** to the same group

Our implementation includes:
- Automatic retry logic
- Error logging via AlertLog model
- Failed message tracking

## Security Best Practices

1. **Never commit** `.env` file with real credentials
2. **Use environment variables** for all sensitive data
3. **Restrict bot access**: Only add to necessary groups
4. **Rotate tokens**: Periodically regenerate bot tokens
5. **Monitor logs**: Check AlertLog for suspicious activity

## Advanced Configuration

### Multiple Chat IDs

To send to multiple chats, you can specify `chat_id` in each call:

```python
# Send to primary chat
client.send_message("Message", chat_id=os.getenv('TELEGRAM_CHAT_ID'))

# Send to admin chat
client.send_message("Admin alert", chat_id=os.getenv('TELEGRAM_ADMIN_CHAT_ID'))
```

### Silent Notifications

For low-priority messages:

```python
client.send_message(
    "Low priority update",
    disable_notification=True
)
```

### Custom Chat for Different Alert Types

Configure in Django settings or environment:

```env
TELEGRAM_CHAT_ID=123456789          # Main chat
TELEGRAM_ADMIN_CHAT_ID=987654321    # Admin alerts
TELEGRAM_RISK_CHAT_ID=456789123     # Risk alerts only
```

## Integration with Services

### In Exit Manager

```python
from apps.alerts.services import send_position_alert

def check_exit_conditions(position):
    exit_check = {...}

    if exit_check['should_exit']:
        # Send alert before exiting
        send_position_alert(
            position,
            alert_type=exit_check['exit_reason'],
            priority='CRITICAL' if exit_check['is_mandatory'] else 'HIGH'
        )

    return exit_check
```

### In Risk Manager

```python
from apps.alerts.services import send_risk_alert

def activate_circuit_breaker(account, trigger_type, ...):
    # Activate circuit breaker
    circuit_breaker = CircuitBreaker.objects.create(...)

    # Send critical alert
    send_risk_alert(
        account,
        alert_type='CIRCUIT_BREAKER',
        priority='CRITICAL',
        risk_data={
            'action_required': 'EMERGENCY_EXIT',
            'trigger_type': trigger_type,
            ...
        }
    )
```

## Database Models

### Alert Model
Stores all alerts with delivery status:
- `telegram_sent`: Whether alert was sent via Telegram
- `telegram_sent_at`: When it was sent
- `priority`: Alert priority level
- `metadata`: JSON field for additional data

### AlertLog Model
Tracks delivery attempts:
- `status`: SUCCESS, FAILED, PENDING
- `response`: API response
- `error_message`: Error details if failed
- `retry_count`: Number of retry attempts

## Monitoring

### Check Recent Alerts

```python
from apps.alerts.models import Alert

# Recent critical alerts
Alert.objects.filter(priority='CRITICAL').order_by('-created_at')[:10]

# Failed telegram deliveries
Alert.objects.filter(send_telegram=True, telegram_sent=False)
```

### Retry Failed Alerts

```python
from apps.alerts.services import get_alert_manager

manager = get_alert_manager()
retried, success = manager.retry_failed_alerts(max_retries=3)

print(f"Retried: {retried}, Successful: {success}")
```

## Support

For issues or questions:
1. Check Django logs: `logs/django.log`
2. Check AlertLog model for delivery errors
3. Verify Telegram API status: https://telegram.org/
4. Test with: `python manage.py test_telegram`

---

**Last Updated**: 2024-11-15
**Version**: 1.0
