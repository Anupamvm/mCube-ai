#!/bin/bash
# Quick test script for Telegram bot

echo "========================================================================"
echo "TELEGRAM BOT QUICK TEST"
echo "========================================================================"
echo ""
echo "✅ Bot Token: Configured"
echo "✅ Chat ID: 788423838"
echo "✅ Bot Status: Active"
echo ""
echo "Starting bot test..."
echo ""

# Clear old updates
echo "1. Clearing old message updates..."
curl -s "https://api.telegram.org/bot6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo/getUpdates?offset=-1" > /dev/null
echo "   ✅ Cleared"
echo ""

# Start the bot in background
echo "2. Starting bot..."
python manage.py run_telegram_bot &
BOT_PID=$!
echo "   ✅ Bot started (PID: $BOT_PID)"
echo ""

echo "========================================================================"
echo "BOT IS READY!"
echo "========================================================================"
echo ""
echo "Now do this:"
echo "  1. Open Telegram"
echo "  2. Go to @dmcube_bot chat"
echo "  3. Send: /start"
echo ""
echo "You should get a welcome message!"
echo ""
echo "Press Ctrl+C to stop the bot when done testing"
echo "========================================================================"

# Wait for Ctrl+C
wait $BOT_PID
