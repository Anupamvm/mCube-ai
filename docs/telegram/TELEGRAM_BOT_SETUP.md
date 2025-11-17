# Telegram Bot Setup - Step by Step

## Current Status

✅ **Bot Token Configured:** `6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo`
✅ **Bot Username:** `@dmcube_bot`
✅ **Bot Name:** MCube
⏳ **Chat ID:** Pending (needs your first message)

---

## Quick Setup (3 Steps)

### Step 1: Send a Message to Your Bot

1. **Open Telegram** on your phone or computer
2. **Search for:** `@dmcube_bot`
3. **Click "Start"** or send any message (like "hello")

### Step 2: Get Your Chat ID

Run this command:

```bash
python get_telegram_chat_id.py
```

**OR** use this quick check:

```bash
curl -s "https://api.telegram.org/bot6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo/getUpdates" | grep -o '"id":[0-9]*' | head -1
```

You'll see your Chat ID like: `"id":123456789`

### Step 3: Update Settings

Edit `mcube_ai/settings.py` and add your Chat ID:

```python
TELEGRAM_CHAT_ID = '123456789'  # Replace with YOUR chat ID
```

**OR** set as environment variable (recommended):

```bash
export TELEGRAM_CHAT_ID='123456789'
```

---

## Test the Bot

Once you have your Chat ID configured:

```bash
python manage.py run_telegram_bot
```

You should see:

```
Starting Telegram bot...
Press Ctrl+C to stop the bot

Bot is polling for updates...
```

Now send `/start` to your bot in Telegram. You should get a welcome message!

---

## Available Commands

Once the bot is running, you can use these commands:

### Monitoring
- `/start` - Welcome message and quick overview
- `/help` - List all commands
- `/status` - System status and active positions count
- `/positions` - List all active positions
- `/accounts` - Broker account balances
- `/risk` - Risk limits and utilization
- `/pnl` - Today's P&L
- `/pnl_week` - Weekly P&L

### Trading Control
- `/close <id>` - Close a specific position (with confirmation)
- `/closeall` - Close ALL positions (emergency, with confirmation)
- `/pause` - Pause automated trading
- `/resume` - Resume automated trading

---

## Automatic Chat ID Detection (Alternative)

If you don't want to manually configure the Chat ID, you can modify the bot to auto-detect it:

1. Send a message to @dmcube_bot
2. Run the bot: `python manage.py run_telegram_bot`
3. The bot will log your chat ID
4. Update `settings.py` with that Chat ID
5. Restart the bot

---

## Security Notes

🔒 **Bot Token Security:**
- Bot token is configured in `settings.py`
- For production, use environment variable: `export TELEGRAM_BOT_TOKEN='your_token'`
- Never commit the token to git

🔒 **Chat ID Authorization:**
- Only your configured Chat ID can use the bot
- Unauthorized users will get "⛔ Unauthorized access" message

---

## Running in Production

### Option 1: Screen Session

```bash
screen -S telegram-bot
python manage.py run_telegram_bot
# Press Ctrl+A then D to detach

# Reattach later:
screen -r telegram-bot
```

### Option 2: Systemd Service

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
Environment="TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE"
ExecStart=/Users/anupammangudkar/PyProjects/mCube-ai/venv/bin/python manage.py run_telegram_bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
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

**Check 3:** Verify bot token
```bash
curl "https://api.telegram.org/bot6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo/getMe"
```

### "Unauthorized access" message

Your Chat ID is not configured or doesn't match. Verify in `settings.py`:

```python
TELEGRAM_CHAT_ID = '123456789'  # Must match YOUR chat ID
```

### Commands not working

Make sure:
1. Bot is running (`python manage.py run_telegram_bot`)
2. Your Chat ID is configured
3. You're sending commands in the correct format (e.g., `/status` not `status`)

---

## Next Steps

After setup:

1. ✅ Test basic commands (`/start`, `/status`, `/help`)
2. ✅ Test monitoring commands (`/positions`, `/accounts`)
3. ✅ Set up auto-start (systemd or screen)
4. ✅ Test emergency commands (`/pause`, `/closeall`)

For detailed command documentation, see [TELEGRAM_BOT_GUIDE.md](TELEGRAM_BOT_GUIDE.md)

---

**Bot Details:**
- Token: `6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo`
- Username: `@dmcube_bot`
- Status: ✅ Active and ready
