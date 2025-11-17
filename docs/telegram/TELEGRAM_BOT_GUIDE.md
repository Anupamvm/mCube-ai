# Telegram Bot Guide for mCube Trading System

Complete guide for setting up and using the interactive Telegram bot for manual control of your trading system.

## Overview

The Telegram bot provides **real-time monitoring and manual control** of your trading system through simple text commands. You can check positions, view P&L, close positions, pause trading, and more - all from your Telegram app.

### Key Features

✅ **Real-time monitoring** - Check system status, positions, and P&L anytime
✅ **Manual control** - Close positions, pause/resume trading via commands
✅ **Risk oversight** - View risk limits and circuit breaker status
✅ **Emergency controls** - Quick "close all" for emergency situations
✅ **Authorized access** - Only your configured chat ID can use the bot
✅ **Interactive buttons** - Confirm dangerous actions with inline buttons

---

## Setup Instructions

### Step 1: Create a Telegram Bot

1. **Open Telegram** and search for `@BotFather`

2. **Send `/newbot` command** to BotFather

3. **Follow the prompts:**
   - Choose a name for your bot (e.g., "mCube Trading Bot")
   - Choose a username (must end in 'bot', e.g., "mcube_trading_bot")

4. **Save the bot token** - BotFather will give you a token that looks like:
   ```
   1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789
   ```

### Step 2: Get Your Chat ID

1. **Start a chat with your bot** - Search for your bot's username in Telegram and send `/start`

2. **Get your chat ID** using one of these methods:

   **Method A: Use a bot**
   - Search for `@userinfobot` in Telegram
   - Send it any message
   - It will reply with your chat ID

   **Method B: Use the API**
   - Send a message to your bot
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Look for `"chat":{"id":123456789}` in the JSON response

3. **Save your chat ID** (it's a number like `123456789` or `-987654321` for groups)

### Step 3: Configure the Bot

Add your bot credentials to `mcube_ai/settings.py`:

```python
# =============================================================================
# TELEGRAM BOT CONFIGURATION
# =============================================================================

# Telegram Bot API settings
TELEGRAM_BOT_TOKEN = '1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789'  # Your bot token
TELEGRAM_CHAT_ID = '123456789'  # Your chat ID
```

**⚠️ For production:** Use environment variables instead:

```bash
export TELEGRAM_BOT_TOKEN='your_bot_token_here'
export TELEGRAM_CHAT_ID='your_chat_id_here'
```

### Step 4: Test the Bot

```bash
# Run the bot
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

### 📊 Monitoring Commands

#### `/start`
Welcome message and quick command overview

```
Example:
> /start

🤖 mCube Trading System Bot

Welcome! I can help you monitor and control your trading system.

Quick Commands:
• /status - System overview
• /positions - Active positions
• /risk - Risk limits
• /pnl - Today's P&L
• /help - All commands
```

#### `/help`
Show all available commands with descriptions

#### `/status`
Overall system status snapshot

```
Example output:
📊 SYSTEM STATUS
========================================

Trading: ▶️ RUNNING
Time: 2025-11-15 14:30:45 IST

Accounts: 2/2 active
Active Positions: 1
Circuit Breakers: 0

Today's P&L: ₹12,450
```

#### `/positions`
List all currently active positions

```
Example output:
📈 ACTIVE POSITIONS (1)
========================================

#42 - NIFTY 19500 CE
  Account: Kotak Primary
  Direction: SHORT
  Entry: ₹185.50
  Current: ₹142.30
  📈 P&L: ₹43,200
  Strategy: WEEKLY_NIFTY_STRANGLE

[Refresh] [Close All] buttons appear below
```

#### `/position <id>`
Detailed view of a specific position

```
Example:
> /position 42

📊 POSITION #42
========================================

Account: Kotak Primary (KOTAK)
Instrument: NIFTY 19500 CE
Strategy: WEEKLY_NIFTY_STRANGLE
Direction: SHORT
Status: ACTIVE

Entry Price: ₹185.50
Current Price: ₹142.30
Quantity: 100 lots
Entry Value: ₹1,855,000

Stop-Loss: ₹250.00
Target: ₹90.00

📈 P&L: ₹43,200

Entry Time: 2025-11-12 10:05:23

[Close Position] button appears below
```

#### `/accounts`
List all broker accounts with balances

```
Example output:
🏦 BROKER ACCOUNTS (2)
========================================

✅ Kotak Primary (KOTAK)
  Balance: ₹6,15,00,000
  Margin: ₹3,25,00,000
  Active Position: #42 (NIFTY 19500 CE)

✅ ICICI Futures (ICICI)
  Balance: ₹1,20,00,000
  Margin: ₹60,00,000
  Active Position: None
```

#### `/risk`
Risk limits and utilization for all accounts

```
Example output:
⚠️ RISK LIMITS
========================================

Kotak Primary
  ✅ DAILY_LOSS: ₹5,000 / ₹30,000 (16.7%)
  ✅ WEEKLY_LOSS: ₹12,000 / ₹1,00,000 (12.0%)

ICICI Futures
  ✅ DAILY_LOSS: ₹0 / ₹12,000 (0.0%)
  ✅ WEEKLY_LOSS: ₹0 / ₹40,000 (0.0%)
```

#### `/logs`
View recent system log entries (last 20 lines)

---

### 💰 Analytics Commands

#### `/pnl`
Today's profit & loss summary

```
Example output:
💰 TODAY'S P&L
========================================
📈 Total P&L: ₹12,450

Trades: 3
Winners: 2 (66.7%)
Losers: 1

Date: 2025-11-15 (Friday)
```

#### `/pnl_week`
This week's profit & loss summary

```
Example output:
💰 WEEKLY P&L
========================================
📈 Total P&L: ₹58,720

Trades: 12
Winners: 8 (66.7%)
Losers: 4

Week: 2025-11-11 to 2025-11-15
```

---

### 🎛 Trading Control Commands

#### `/close <id>`
Close a specific position (with confirmation)

```
Example:
> /close 42

⚠️ CONFIRM POSITION CLOSE

Position: #42
Instrument: NIFTY 19500 CE
Direction: SHORT
Current P&L: ₹43,200

Are you sure you want to close this position?

[✅ Confirm Close] [❌ Cancel] buttons appear
```

After confirming:
```
✅ Position #42 closed successfully
Realized P&L: ₹43,200
```

#### `/closeall`
**EMERGENCY:** Close all active positions (with confirmation)

```
Example:
> /closeall

🚨 EMERGENCY: CLOSE ALL POSITIONS

⚠️ This will close ALL 2 active positions.

Positions to be closed:
  • #42 - NIFTY 19500 CE (₹43,200)
  • #45 - BANKNIFTY FUT (₹-8,500)

Are you absolutely sure?

[✅ CONFIRM CLOSE ALL] [❌ Cancel] buttons appear
```

After confirming:
```
✅ CLOSE ALL COMPLETE

Closed: 2
Failed: 0
Total P&L: ₹34,700
```

#### `/pause`
Pause automated trading (positions still monitored, no new entries)

```
Example:
> /pause

⏸ TRADING PAUSED

Automated trading has been paused.

• No new positions will be opened
• Existing positions will continue to be monitored
• Exit conditions will still be checked

Use /resume to resume automated trading.
```

**What happens when paused:**
- ✅ Position monitoring continues
- ✅ Exit conditions are still checked (SL/Target)
- ✅ Risk limits are still enforced
- ❌ No new strategy entry signals will execute
- ❌ No new positions will be opened

**Use cases:**
- During high volatility/uncertain market conditions
- Before important news announcements
- When you want to review strategy performance
- End of trading day if you don't want new entries

#### `/resume`
Resume automated trading

```
Example:
> /resume

▶️ TRADING RESUMED

Automated trading has been resumed.

• New positions can be opened
• All strategies are active
• Normal operations restored
```

---

## How Pause/Resume Works

The pause/resume functionality uses a **shared trading state** that all Celery tasks check before executing entry strategies.

### Implementation Details

1. **Trading State Module** (`apps/core/trading_state.py`)
   - Centralized singleton class managing pause state
   - Can be checked by any strategy or task
   - Thread-safe for concurrent access

2. **Strategy Integration**
   - All entry functions should check `is_trading_paused()` before executing
   - Example integration in strategy code:

```python
from apps.core.trading_state import is_trading_paused

def execute_kotak_strangle_entry(account):
    """Execute Kotak strangle entry"""

    # Check if trading is paused
    if is_trading_paused():
        logger.info("Trading is paused - skipping entry")
        return {
            'success': False,
            'message': 'Trading paused via Telegram bot'
        }

    # Proceed with normal entry logic...
```

3. **What's NOT Affected by Pause**
   - Position monitoring tasks (continue running)
   - Exit condition checks (SL/Target still enforced)
   - Risk limit monitoring
   - P&L updates
   - Market data updates

---

## Running the Bot in Production

### Option 1: Screen/tmux Session

```bash
# Start a screen session
screen -S telegram-bot

# Run the bot
python manage.py run_telegram_bot

# Detach from screen (Ctrl+A, then D)

# Reattach later
screen -r telegram-bot
```

### Option 2: Systemd Service (Linux)

Create `/etc/systemd/system/telegram-bot.service`:

```ini
[Unit]
Description=mCube Telegram Bot
After=network.target

[Service]
Type=simple
User=mcube
Group=mcube
WorkingDirectory=/path/to/mCube-ai
Environment="PATH=/path/to/venv/bin"
Environment="TELEGRAM_BOT_TOKEN=your_token_here"
Environment="TELEGRAM_CHAT_ID=your_chat_id_here"
ExecStart=/path/to/venv/bin/python manage.py run_telegram_bot
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

# Check status
sudo systemctl status telegram-bot

# View logs
sudo journalctl -u telegram-bot -f
```

### Option 3: Supervisor

Add to supervisor config:

```ini
[program:telegram-bot]
command=/path/to/venv/bin/python manage.py run_telegram_bot
directory=/path/to/mCube-ai
user=mcube
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/telegram-bot.log
environment=TELEGRAM_BOT_TOKEN="your_token",TELEGRAM_CHAT_ID="your_id"
```

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start telegram-bot
```

---

## Security Best Practices

### 1. Protect Your Bot Token
```bash
# NEVER commit tokens to git
echo "TELEGRAM_BOT_TOKEN=your_token" >> .env
echo ".env" >> .gitignore

# Use environment variables
export TELEGRAM_BOT_TOKEN='your_token_here'
export TELEGRAM_CHAT_ID='your_chat_id_here'
```

### 2. Restrict Access

The bot only responds to authorized chat IDs configured in settings. Unauthorized users will get:
```
⛔ Unauthorized access
```

### 3. Enable 2FA on Telegram

Enable two-factor authentication on your Telegram account to prevent unauthorized access.

### 4. Use Private Chats

Don't add the bot to public groups. Keep it in a private chat with yourself or a private group with trusted team members.

### 5. Monitor Bot Usage

Check logs regularly for unusual activity:
```bash
tail -f logs/mcube_ai.log | grep -i telegram
```

---

## Troubleshooting

### Bot not responding

**Check 1:** Is the bot running?
```bash
ps aux | grep run_telegram_bot
```

**Check 2:** Check logs for errors
```bash
tail -f logs/mcube_ai.log
```

**Check 3:** Verify bot token
```bash
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

Should return bot info. If not, token is invalid.

### "Unauthorized access" message

Your chat ID is not configured. Verify:
```python
# In settings.py
TELEGRAM_CHAT_ID = '123456789'  # Must match YOUR chat ID
```

Get your chat ID from `@userinfobot` and update settings.

### Commands timing out

Long-running commands (like `/closeall` with many positions) may timeout. The bot will still execute the action, but you may not get a response. Check `/positions` or `/status` after a few seconds.

### Bot stops working after server restart

Make sure the bot is set up to auto-start:
- Use systemd service (recommended)
- Use supervisor
- Add to cron with `@reboot` directive

---

## Advanced Usage

### Custom Commands

You can add custom commands by editing `apps/alerts/services/telegram_bot.py`:

```python
async def custom_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /custom command"""
    if not self.is_authorized(update):
        await update.message.reply_text("⛔ Unauthorized access")
        return

    # Your custom logic here
    await update.message.reply_text("Custom command executed!")

# Register in run() method:
application.add_handler(CommandHandler("custom", self.custom_command))
```

### Integration with Strategy Code

Update your strategy entry functions to respect pause state:

```python
# In apps/strategies/strategies/kotak_strangle.py

from apps.core.trading_state import is_trading_paused

def execute_kotak_strangle_entry(account: BrokerAccount) -> Dict:
    """Execute Kotak strangle entry"""

    # Check if trading is paused
    if is_trading_paused():
        logger.info("⏸ Trading paused - skipping entry")
        return {
            'success': False,
            'message': 'Trading paused via manual control',
            'skip_reason': 'TRADING_PAUSED'
        }

    # Normal entry logic continues...
```

### Group Chat Support

To use the bot in a group:

1. Add the bot to your private group
2. Get the group chat ID (will be negative, like `-987654321`)
3. Update `TELEGRAM_CHAT_ID` with the group ID
4. All authorized group members can use commands

---

## FAQ

**Q: Can I use the bot from multiple devices?**
A: Yes! As long as you're logged into the same Telegram account on all devices, you can control the bot from anywhere.

**Q: Will the bot work if my computer is off?**
A: No. The bot runs on your server/computer. If the server is off, the bot won't respond. Use a cloud server or VPS for 24/7 availability.

**Q: Can I have multiple people control the bot?**
A: Yes, add the bot to a private group with your team. Configure the group chat ID in settings.

**Q: What happens if I send an invalid command?**
A: The bot will simply not respond to unrecognized commands. Send `/help` to see all available commands.

**Q: Can I close positions even when trading is paused?**
A: Yes! `/close` and `/closeall` work regardless of pause state. Pause only affects NEW position entries.

**Q: How do I stop the bot?**
A: Press `Ctrl+C` in the terminal, or `sudo systemctl stop telegram-bot` if using systemd.

---

## Summary

The Telegram bot gives you **full manual control** over your trading system from anywhere. Key capabilities:

✅ Real-time monitoring (status, positions, P&L, risk)
✅ Emergency controls (close all, pause trading)
✅ Manual overrides (close specific positions)
✅ Analytics (daily/weekly P&L)
✅ Secure (authorized access only)

**Quick Start:**
1. Create bot with @BotFather → get token
2. Get your chat ID from @userinfobot
3. Add credentials to settings.py
4. Run: `python manage.py run_telegram_bot`
5. Send `/start` to your bot

**Production:**
- Set up systemd service for auto-restart
- Use environment variables for credentials
- Monitor logs regularly
- Keep bot private (don't share with unauthorized users)

For additional help, see the main [CELERY_SETUP.md](CELERY_SETUP.md) guide.
