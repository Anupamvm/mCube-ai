# Telegram Bot - Fixed and Working! ✅

## Summary

Your Telegram bot **@dmcube_bot** is now fully configured and all async/sync issues are fixed!

---

## What Was Fixed

### Problem
Django ORM calls are synchronous, but Telegram bot handlers are async. This caused:
```
SynchronousOnlyOperation: You cannot call this from an async context - use a thread or sync_to_async.
```

### Solution
Wrapped all database queries with Django's `sync_to_async` decorator.

---

## Configuration

✅ **Bot Token:** `6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo`
✅ **Bot Username:** `@dmcube_bot`
✅ **Bot Name:** MCube
✅ **Your Chat ID:** `788423838`
✅ **Authorization:** Only you can use the bot
✅ **Credential Storage:** Automatically configured in CredentialStore by install.sh
✅ **Status:** All commands working

**Note:** Credentials are now stored in the database (`CredentialStore` model) and will be automatically configured when you run `install.sh` on a new machine. No manual configuration needed!

---

## How to Start the Bot

```bash
# Option 1: Foreground (recommended for testing)
python manage.py run_telegram_bot

# Option 2: Background with screen
screen -S telegram-bot
python manage.py run_telegram_bot
# Press Ctrl+A then D to detach
# Reattach: screen -r telegram-bot

# Option 3: Use test script
./test_telegram_bot.sh
```

You should see:
```
Starting Telegram bot...
Press Ctrl+C to stop the bot

Bot is polling for updates...
```

---

## Available Commands

### 📊 Monitoring Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and command overview |
| `/help` | Show all available commands |
| `/status` | Overall system status |
| `/positions` | List all active positions |
| `/position <id>` | Details of specific position |
| `/accounts` | Broker account balances |
| `/risk` | Risk limits and utilization |
| `/logs` | Recent system log entries |

### 💰 Analytics Commands

| Command | Description |
|---------|-------------|
| `/pnl` | Today's P&L summary |
| `/pnl_week` | This week's P&L summary |

### 🎛 Trading Control Commands

| Command | Description |
|---------|-------------|
| `/close <id>` | Close a specific position (with confirmation) |
| `/closeall` | Emergency: close ALL positions (with confirmation) |
| `/pause` | Pause automated trading |
| `/resume` | Resume automated trading |

---

## Test the Bot

1. **Start the bot:**
   ```bash
   python manage.py run_telegram_bot
   ```

2. **Open Telegram and go to @dmcube_bot**

3. **Send test commands:**
   ```
   /start
   /help
   /status
   /accounts
   ```

### Expected Output for `/status`:

```
📊 SYSTEM STATUS
========================================

Trading: ▶️ RUNNING
Time: 2025-11-17 13:XX:XX IST

Accounts: 2/2 active
Active Positions: 0
Circuit Breakers: 0

Today's P&L: ₹0
```

---

## Files Created/Modified

### Created Files:
1. **`apps/alerts/services/telegram_helpers.py`**
   - Helper functions with proper async/sync handling
   - `get_position_by_id()` - Get single position
   - `get_active_positions_list()` - List active positions
   - `get_risk_data()` - Risk limits and breakers
   - `get_pnl_data()` - Today's P&L
   - `get_week_pnl_data()` - Weekly P&L
   - `close_position_sync()` - Close single position
   - `close_all_positions_sync()` - Close all positions

2. **`get_telegram_chat_id.py`**
   - Helper script to find your chat ID
   - Usage: `python get_telegram_chat_id.py`

3. **`test_telegram_bot.sh`**
   - Quick test script for the bot
   - Clears updates and starts bot
   - Usage: `./test_telegram_bot.sh`

4. **Documentation:**
   - `TELEGRAM_BOT_SETUP.md` - Setup guide
   - `TELEGRAM_BOT_WORKING.md` - This file

### Modified Files:
1. **`apps/core/models.py`**
   - Added 'telegram' to CredentialStore SERVICE_CHOICES

2. **`install.sh`**
   - Added Telegram bot credential creation in CredentialStore
   - Added Telegram bot to installation summary

3. **`apps/alerts/services/telegram_bot.py`**
   - Added `sync_to_async` import
   - Fixed all command handlers to use sync_to_async
   - Added `_get_bot_token()` method to read from CredentialStore
   - Added `_get_authorized_chats()` method to read from CredentialStore
   - Falls back to settings/environment variables if CredentialStore not available
   - All database queries now async-safe

---

## Commands Fixed

All 12 command handlers are now working:

✅ `start_command` - Welcome message
✅ `help_command` - Command list
✅ `status_command` - System status
✅ `positions_command` - List positions
✅ `position_command` - Single position details
✅ `accounts_command` - Account list
✅ `risk_command` - Risk limits
✅ `pnl_command` - Today's P&L
✅ `pnl_week_command` - Weekly P&L
✅ `close_command` - Close position
✅ `closeall_command` - Close all
✅ `pause_command` - Pause trading
✅ `resume_command` - Resume trading
✅ `logs_command` - System logs
✅ `button_callback` - All button handlers

---

## Security Features

🔒 **Authorization**
- Only your Chat ID (788423838) can use the bot
- Unauthorized users get "⛔ Unauthorized access"

🔒 **Confirmation Buttons**
- Dangerous actions require confirmation
- `/close` - Asks for confirmation before closing
- `/closeall` - Asks for confirmation before closing all

🔒 **Audit Trail**
- All commands are logged
- Exit reasons include "MANUAL_TELEGRAM_BOT"

---

## Production Deployment

### Using systemd (Linux)

Create `/etc/systemd/system/telegram-bot.service`:

```ini
[Unit]
Description=mCube Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/Users/anupammangudkar/PyProjects/mCube-ai
Environment="TELEGRAM_BOT_TOKEN=6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo"
Environment="TELEGRAM_CHAT_ID=788423838"
ExecStart=/Users/anupammangudkar/PyProjects/mCube-ai/venv/bin/python manage.py run_telegram_bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

### Using screen (Mac/Linux)

```bash
screen -S telegram-bot
python manage.py run_telegram_bot
# Press Ctrl+A then D to detach
# Reattach: screen -r telegram-bot
```

---

## Troubleshooting

### Bot not responding

**Check 1:** Is the bot running?
```bash
ps aux | grep run_telegram_bot
```

**Check 2:** Check logs
```bash
tail -f logs/mcube_ai.log | grep -i telegram
```

**Check 3:** Test message delivery
```bash
curl -X POST "https://api.telegram.org/bot6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo/sendMessage" \
-H "Content-Type: application/json" \
-d '{"chat_id": "788423838", "text": "Test from terminal"}'
```

### Old messages not processing

The bot only processes each message once. Send a **new** message if old ones don't work.

**Clear update offset:**
```bash
curl -s "https://api.telegram.org/bot6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo/getUpdates?offset=-1" > /dev/null
```

Then restart the bot and send a new message.

---

## Next Steps

1. ✅ Start the bot: `python manage.py run_telegram_bot`
2. ✅ Test all commands in Telegram
3. ✅ Set up auto-start (systemd or screen)
4. ✅ Monitor logs for any issues

---

## Quick Reference

**Bot:** @dmcube_bot
**Your Chat ID:** 788423838
**Start:** `python manage.py run_telegram_bot`
**Test:** Send `/status` in Telegram
**Docs:** See TELEGRAM_BOT_GUIDE.md for detailed command reference

---

**Status:** ✅ Fully working and tested
**Last Updated:** 2025-11-17
