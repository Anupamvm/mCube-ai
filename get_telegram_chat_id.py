#!/usr/bin/env python
"""
Helper script to get your Telegram Chat ID

Usage:
1. Run this script: python get_telegram_chat_id.py
2. Send any message to your bot @dmcube_bot in Telegram
3. The script will show your chat ID
4. Press Ctrl+C to stop
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from django.conf import settings
import requests
import time

BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN

if not BOT_TOKEN:
    print("❌ Error: TELEGRAM_BOT_TOKEN not configured in settings.py")
    exit(1)

print("=" * 70)
print("TELEGRAM CHAT ID FINDER")
print("=" * 70)
print()
print(f"✅ Bot Token: {BOT_TOKEN[:20]}...")
print(f"✅ Bot Username: @dmcube_bot")
print()
print("📱 INSTRUCTIONS:")
print("   1. Open Telegram")
print("   2. Search for @dmcube_bot")
print("   3. Send ANY message to the bot (e.g., 'hello')")
print("   4. Your chat ID will appear below")
print()
print("⏳ Waiting for your message... (Press Ctrl+C to stop)")
print()

# Track offset to get only new messages
offset = 0
found_chat_ids = set()

try:
    while True:
        # Get updates from Telegram
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        params = {
            'offset': offset,
            'timeout': 30
        }

        try:
            response = requests.get(url, params=params, timeout=35)
            data = response.json()

            if data.get('ok') and data.get('result'):
                for update in data['result']:
                    # Update offset to mark as processed
                    offset = update['update_id'] + 1

                    # Extract chat info
                    if 'message' in update:
                        message = update['message']
                        chat = message.get('chat', {})
                        chat_id = chat.get('id')
                        chat_type = chat.get('type')
                        first_name = chat.get('first_name', '')
                        last_name = chat.get('last_name', '')
                        username = chat.get('username', '')

                        if chat_id and chat_id not in found_chat_ids:
                            found_chat_ids.add(chat_id)

                            print("=" * 70)
                            print("✅ MESSAGE RECEIVED!")
                            print("=" * 70)
                            print()
                            print(f"📱 Chat Type: {chat_type}")
                            print(f"👤 Name: {first_name} {last_name}".strip())
                            if username:
                                print(f"🔗 Username: @{username}")
                            print()
                            print(f"🆔 YOUR CHAT ID: {chat_id}")
                            print()
                            print("=" * 70)
                            print("NEXT STEPS:")
                            print("=" * 70)
                            print()
                            print("1. Copy your Chat ID from above")
                            print(f"   Chat ID: {chat_id}")
                            print()
                            print("2. Update settings.py:")
                            print(f"   TELEGRAM_CHAT_ID = '{chat_id}'")
                            print()
                            print("3. Test the bot:")
                            print("   python manage.py run_telegram_bot")
                            print()
                            print("Press Ctrl+C to exit this script")
                            print()

        except requests.exceptions.Timeout:
            # Timeout is normal with long polling
            continue
        except requests.exceptions.RequestException as e:
            print(f"⚠️  Connection error: {e}")
            print("   Retrying in 5 seconds...")
            time.sleep(5)
            continue

        # Small delay between polls
        time.sleep(0.5)

except KeyboardInterrupt:
    print()
    print("=" * 70)
    print("Script stopped.")
    print()
    if found_chat_ids:
        print("✅ Found chat IDs:")
        for cid in found_chat_ids:
            print(f"   {cid}")
        print()
        print("Update settings.py with your chat ID and run:")
        print("   python manage.py run_telegram_bot")
    else:
        print("⚠️  No messages received.")
        print("   Make sure you sent a message to @dmcube_bot")
    print("=" * 70)
