"""
Notification System for mCube Trading

Sends alerts via:
- Telegram
- SMS (Twilio)
- Email (future)
"""

import asyncio
from typing import Optional
from django.conf import settings


def send_telegram_notification(message: str, chat_id: Optional[str] = None) -> bool:
    """
    Send notification via Telegram

    Args:
        message: Message to send
        chat_id: Optional chat ID (defaults to configured bot chat)

    Returns:
        bool: True if sent successfully
    """
    try:
        from telethon.sync import TelegramClient
        from apps.core.models import CredentialStore

        # Get Telegram credentials
        try:
            creds = CredentialStore.objects.filter(service='telegram').first()
            if not creds:
                print("Telegram credentials not configured")
                return False

            api_id = creds.api_key  # Store as api_key
            api_hash = creds.api_secret  # Store as api_secret
            bot_username = creds.username or 'dmcube_bot'

        except Exception as e:
            print(f"Error loading Telegram credentials: {e}")
            return False

        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Send message
        with TelegramClient('session', api_id, api_hash) as client:
            client.connect()

            if not client.is_user_authorized():
                print("Telegram client not authorized. Run setup first.")
                return False

            # Send to configured bot or chat
            client.send_message(bot_username, message)

        return True

    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")
        return False


def send_sms_notification(message: str, phone_number: Optional[str] = None) -> bool:
    """
    Send SMS notification via Twilio

    Args:
        message: Message to send
        phone_number: Optional phone number (defaults to configured number)

    Returns:
        bool: True if sent successfully
    """
    try:
        from twilio.rest import Client
        from apps.core.models import CredentialStore

        # Get Twilio credentials
        try:
            creds = CredentialStore.objects.filter(service='twilio').first()
            if not creds:
                print("Twilio credentials not configured")
                return False

            account_sid = creds.api_key
            auth_token = creds.api_secret
            from_number = creds.username  # Twilio number stored as username
            to_number = phone_number or creds.password  # Default number stored as password

        except Exception as e:
            print(f"Error loading Twilio credentials: {e}")
            return False

        # Send SMS
        client = Client(account_sid, auth_token)
        client.messages.create(
            body=message,
            from_=from_number,
            to=to_number
        )

        return True

    except Exception as e:
        print(f"Failed to send SMS notification: {e}")
        return False


def send_notification(message: str, channels: list = None) -> dict:
    """
    Send notification via multiple channels

    Args:
        message: Message to send
        channels: List of channels ('telegram', 'sms', 'email')
                 If None, sends via all configured channels

    Returns:
        dict: Status of each channel
    """
    if channels is None:
        channels = ['telegram', 'sms']

    results = {}

    for channel in channels:
        if channel == 'telegram':
            results['telegram'] = send_telegram_notification(message)
        elif channel == 'sms':
            results['sms'] = send_sms_notification(message)
        # Add email in future

    return results
