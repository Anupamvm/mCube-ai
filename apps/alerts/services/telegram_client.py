"""
Telegram Client Service

This service handles sending messages to Telegram via Bot API.

Features:
- Send text messages
- Send formatted messages (Markdown/HTML)
- Send messages with buttons
- Error handling and retry logic
"""

import hashlib
import logging
import os
from typing import Dict, Optional, Tuple
import requests

logger = logging.getLogger(__name__)


class TelegramClient:
    """
    Telegram Bot API client for sending notifications

    Configuration:
        TELEGRAM_BOT_TOKEN: Bot token from @BotFather
        TELEGRAM_CHAT_ID: Default chat ID to send messages
    """

    # Rate limits per priority: (max_messages, window_seconds)
    # Keyed on the first 100 chars of the message to deduplicate identical alerts.
    # CRITICAL is never rate-limited (circuit breakers, SL hits, broker failures).
    _RATE_LIMITS = {
        'WARNING':  (1, 300),   # 1 identical warning per 5 min
        'INFO':     (1, 60),    # 1 identical info per 1 min
        'HIGH':     (3, 600),   # 3 identical high-priority per 10 min
        'CRITICAL': (0, 0),     # no limit
    }

    def __init__(self):
        """Initialize Telegram client with credentials from environment or Django settings"""
        # Try environment variables first, then fall back to Django settings
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.default_chat_ids = self._parse_chat_ids(
            os.getenv('TELEGRAM_CHAT_IDS', ''),
            os.getenv('TELEGRAM_CHAT_ID', ''),
        )

        # Fall back to Django settings if environment variables are not set
        if not self.bot_token:
            try:
                from django.conf import settings
                self.bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
                if not self.default_chat_ids:
                    self.default_chat_ids = self._parse_chat_ids(
                        getattr(settings, 'TELEGRAM_CHAT_IDS', ''),
                        getattr(settings, 'TELEGRAM_CHAT_ID', ''),
                    )
            except Exception:
                pass

        # Keep legacy single-ID attribute for backward compatibility
        self.default_chat_id = self.default_chat_ids[0] if self.default_chat_ids else None

        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram notifications disabled.")
            self.enabled = False
        else:
            self.enabled = True
            self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    @staticmethod
    def _parse_chat_ids(chat_ids_str: str, fallback_single: str) -> list:
        """Parse comma-separated chat IDs, falling back to a single ID if needed."""
        if chat_ids_str:
            ids = [cid.strip() for cid in chat_ids_str.split(',') if cid.strip()]
            if ids:
                return ids
        if fallback_single and fallback_single.strip():
            return [fallback_single.strip()]
        return []

    def is_enabled(self) -> bool:
        """Check if Telegram client is properly configured"""
        return self.enabled

    def send_message(
        self,
        message: str,
        chat_id: Optional[str] = None,
        parse_mode: str = 'HTML',
        disable_notification: bool = False,
        reply_markup: dict = None,
    ) -> Tuple[bool, str]:
        """
        Send a text message to Telegram.

        When `chat_id` is provided, sends to that chat only (e.g. trade confirmation
        replies). When omitted, broadcasts to all configured default chat IDs so
        every authorized user receives the notification.

        Args:
            message: Message text to send
            chat_id: Chat ID to send to (broadcasts to all defaults if not provided)
            parse_mode: Message formatting (HTML, Markdown, or None)
            disable_notification: Send silently without notification
            reply_markup: Optional inline keyboard dict

        Returns:
            Tuple[bool, str]: (success, response/error message)
        """
        if not self.enabled:
            logger.warning("Telegram client not enabled. Skipping message send.")
            return False, "Telegram client not configured"

        if chat_id:
            # Explicit target — send to that one chat only
            targets = [str(chat_id)]
        else:
            targets = self.default_chat_ids

        if not targets:
            logger.error("No chat_id provided and no default chat_id configured")
            return False, "No chat_id configured"

        success = False
        last_result = "No targets"
        for target in targets:
            ok, result = self._send_to_single(
                target, message, parse_mode, disable_notification, reply_markup
            )
            if ok:
                success = True
            last_result = result
        return success, last_result

    def _send_to_single(
        self,
        target_chat_id: str,
        message: str,
        parse_mode: str = 'HTML',
        disable_notification: bool = False,
        reply_markup: dict = None,
    ) -> Tuple[bool, str]:
        """Send a message to a single chat ID via the Telegram Bot API."""
        url = f"{self.base_url}/sendMessage"

        payload = {
            'chat_id': target_chat_id,
            'text': message,
            'parse_mode': parse_mode,
            'disable_notification': disable_notification,
        }
        if reply_markup:
            payload['reply_markup'] = reply_markup

        try:
            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                msg_id = response.json().get('result', {}).get('message_id', '')
                logger.info(f"Telegram message sent successfully to {target_chat_id}")
                return True, str(msg_id)
            else:
                error_msg = f"Telegram API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, error_msg

        except requests.exceptions.Timeout:
            error_msg = "Telegram API request timed out"
            logger.error(error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"Error sending Telegram message: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def edit_message(
        self,
        message_id: int,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = 'HTML',
        reply_markup: dict = None,
    ) -> Tuple[bool, str]:
        """
        Edit an existing Telegram message.

        Args:
            message_id: The message ID to edit
            text: New message text
            chat_id: Chat ID (uses default if not provided)
            parse_mode: Message formatting (HTML, Markdown, or None)

        Returns:
            Tuple[bool, str]: (success, response/error message)
        """
        if not self.enabled:
            return False, "Telegram client not configured"

        target_chat_id = chat_id or self.default_chat_id
        if not target_chat_id:
            return False, "No chat_id configured"

        url = f"{self.base_url}/editMessageText"
        payload = {
            'chat_id': target_chat_id,
            'message_id': int(message_id),
            'text': text,
            'parse_mode': parse_mode,
        }
        if reply_markup:
            payload['reply_markup'] = reply_markup

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True, "Message edited"
            else:
                error_msg = f"Telegram edit error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, error_msg
        except Exception as e:
            error_msg = f"Error editing Telegram message: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def _is_rate_limited(self, message: str, priority: str, dedup_key: Optional[str] = None) -> bool:
        """
        Redis-backed per-message rate limiter for outbound notifications.

        When `dedup_key` is provided (e.g. 'near_sl_42'), it is used directly
        as the cache key suffix so that per-position alerts are tracked
        independently and do not suppress alerts for other positions.

        Without `dedup_key`, falls back to hashing the first 100 characters of
        the message — identical repeated alerts are suppressed within the window.

        Returns True if this message should be suppressed, False otherwise.
        CRITICAL priority is always allowed through (returns False).
        If Redis is unavailable the limiter fails-open (returns False).
        """
        max_count, window = self._RATE_LIMITS.get(priority, (0, 0))
        if max_count == 0 or window == 0:
            return False
        try:
            from django.core.cache import cache
            if dedup_key:
                key = f'tg_rate_{priority}_{dedup_key}'
            else:
                msg_hash = hashlib.md5(message[:100].encode()).hexdigest()
                key = f'tg_rate_{priority}_{msg_hash}'
            current = cache.get(key, 0)
            if current >= max_count:
                return True
            cache.set(key, current + 1, timeout=window)
            return False
        except Exception:
            return False  # fail-open: never block a notification if Redis is down

    def send_priority_message(
        self,
        message: str,
        priority: str,
        chat_id: Optional[str] = None,
        dedup_key: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Send a message with priority-based formatting

        Args:
            message: Message text
            priority: CRITICAL, HIGH, MEDIUM, LOW, INFO
            chat_id: Target chat ID

        Returns:
            Tuple[bool, str]: (success, response)
        """
        if self._is_rate_limited(message, priority, dedup_key=dedup_key):
            logger.debug(f"Telegram [{priority}] suppressed by rate limiter: {message[:60]!r}")
            return True, "rate_limited"

        # Add emoji based on priority
        emoji_map = {
            'CRITICAL': '\U0001F6A8\U0001F6A8\U0001F6A8',  # 🚨🚨🚨
            'HIGH': '\U000026A0\U0000FE0F',  # ⚠️
            'MEDIUM': '\U0001F4CC',  # 📌
            'LOW': '\U00002139\U0000FE0F',  # ℹ️
            'INFO': '\U00002705',  # ✅
        }

        emoji = emoji_map.get(priority, '\U0001F4E2')  # 📢
        formatted_message = f"{emoji} <b>{priority}</b>\n\n{message}"

        # Critical messages should ping
        disable_notification = priority not in ['CRITICAL', 'HIGH']

        return self.send_message(
            formatted_message,
            chat_id=chat_id,
            disable_notification=disable_notification
        )

    def send_notification(
        self,
        payload: 'NotificationPayload',
        chat_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Send a structured NotificationPayload via Telegram.

        Renders the payload with TelegramMessageFormatter, then delivers it
        with the correct priority, dedup key, and inline keyboard (if any).

        This is the preferred entry point for all new notifications —
        it enforces consistent layout and dedup behaviour.
        """
        from apps.alerts.services.notification_formatter import format_notification

        if not self.enabled:
            return False, "Telegram client not configured"

        message = format_notification(payload)

        if payload.keyboard:
            # keyboard is a list of rows; wrap in the API dict format
            keyboard_dict = {'inline_keyboard': payload.keyboard}
            return self.send_message(
                message,
                chat_id=chat_id,
                reply_markup=keyboard_dict,
            )

        # No keyboard — use priority rate-limiting
        return self.send_priority_message(
            message,
            priority=payload.priority,
            chat_id=chat_id,
            dedup_key=payload.dedup_key,
        )

    def send_position_alert(
        self,
        alert_type: str,
        position_data: Dict,
        chat_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Send position-related alert with formatted data

        Args:
            alert_type: Type of alert (SL_HIT, TARGET_HIT, etc.)
            position_data: Position information dictionary
            chat_id: Target chat ID

        Returns:
            Tuple[bool, str]: (success, response)
        """
        message = self._format_position_alert(alert_type, position_data)

        priority = 'CRITICAL' if alert_type in ['SL_HIT', 'CIRCUIT_BREAKER'] else 'HIGH'

        return self.send_priority_message(message, priority, chat_id)

    def send_risk_alert(
        self,
        risk_data: Dict,
        chat_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Send risk management alert

        Args:
            risk_data: Risk information dictionary
            chat_id: Target chat ID

        Returns:
            Tuple[bool, str]: (success, response)
        """
        message = self._format_risk_alert(risk_data)

        priority = 'CRITICAL' if risk_data.get('action_required') == 'EMERGENCY_EXIT' else 'HIGH'

        return self.send_priority_message(message, priority, chat_id)

    def send_daily_summary(
        self,
        summary_data: Dict,
        chat_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Send daily trading summary

        Args:
            summary_data: Daily summary data
            chat_id: Target chat ID

        Returns:
            Tuple[bool, str]: (success, response)
        """
        message = self._format_daily_summary(summary_data)

        return self.send_priority_message(message, 'INFO', chat_id)

    def _format_position_alert(self, alert_type: str, data: Dict) -> str:
        """Format position alert message"""

        title_map = {
            'SL_HIT': 'STOP-LOSS HIT',
            'TARGET_HIT': 'TARGET HIT',
            'POSITION_ENTERED': 'NEW POSITION ENTERED',
            'POSITION_CLOSED': 'POSITION CLOSED',
            'DELTA_ALERT': 'DELTA ALERT',
            'AVERAGING_DONE': 'POSITION AVERAGED',
        }

        title = title_map.get(alert_type, alert_type)

        message = f"<b>{title}</b>\n"
        message += "=" * 40 + "\n\n"

        # Position details
        message += f"<b>Account:</b> {data.get('account_name', 'N/A')}\n"
        message += f"<b>Instrument:</b> {data.get('instrument', 'N/A')}\n"
        message += f"<b>Direction:</b> {data.get('direction', 'N/A')}\n"
        message += f"<b>Quantity:</b> {data.get('quantity', 0)} lots\n\n"

        # Price info
        if 'entry_price' in data:
            message += f"<b>Entry:</b> Rs.{data['entry_price']:,.2f}\n"
        if 'current_price' in data:
            message += f"<b>Current:</b> Rs.{data['current_price']:,.2f}\n"
        if 'exit_price' in data:
            message += f"<b>Exit:</b> Rs.{data['exit_price']:,.2f}\n"

        message += "\n"

        # SL/Target
        if 'stop_loss' in data:
            message += f"<b>Stop-Loss:</b> Rs.{data['stop_loss']:,.2f}\n"
        if 'target' in data:
            message += f"<b>Target:</b> Rs.{data['target']:,.2f}\n"

        message += "\n"

        # P&L
        if 'unrealized_pnl' in data:
            pnl = data['unrealized_pnl']
            pnl_emoji = '\U0001F4C8' if pnl >= 0 else '\U0001F4C9'  # 📈📉
            message += f"{pnl_emoji} <b>Unrealized P&L:</b> Rs.{pnl:,.2f}\n"

        if 'realized_pnl' in data:
            pnl = data['realized_pnl']
            pnl_emoji = '\U0001F4C8' if pnl >= 0 else '\U0001F4C9'
            message += f"{pnl_emoji} <b>Realized P&L:</b> Rs.{pnl:,.2f}\n"

        # Additional info
        if 'message' in data:
            message += f"\n<i>{data['message']}</i>\n"

        return message

    def _format_risk_alert(self, data: Dict) -> str:
        """Format risk management alert message"""

        message = "<b>RISK ALERT</b>\n"
        message += "=" * 40 + "\n\n"

        message += f"<b>Account:</b> {data.get('account_name', 'N/A')}\n"
        message += f"<b>Action Required:</b> {data.get('action_required', 'NONE')}\n\n"

        # Risk limits
        if 'breached_limits' in data and data['breached_limits']:
            message += "<b>BREACHED LIMITS:</b>\n"
            for limit in data['breached_limits']:
                message += f"  - {limit.get('type', 'N/A')}: Rs.{limit.get('current', 0):,.0f} / Rs.{limit.get('limit', 0):,.0f}\n"
            message += "\n"

        if 'warnings' in data and data['warnings']:
            message += "<b>WARNINGS:</b>\n"
            for warning in data['warnings']:
                message += f"  - {warning.get('type', 'N/A')}: {warning.get('utilization', 0):.1f}%\n"
            message += "\n"

        # Current status
        message += f"<b>Trading Allowed:</b> {'YES' if data.get('trading_allowed', False) else 'NO'}\n"
        message += f"<b>Active Breakers:</b> {data.get('active_circuit_breakers', 0)}\n"

        if 'message' in data:
            message += f"\n<i>{data['message']}</i>\n"

        return message

    def _format_daily_summary(self, data: Dict) -> str:
        """Format daily summary message"""

        message = "\U0001F4CA <b>DAILY TRADING SUMMARY</b>\n"  # 📊
        message += "=" * 40 + "\n\n"

        message += f"<b>Date:</b> {data.get('date', 'N/A')}\n\n"

        # P&L Summary
        total_pnl = data.get('total_pnl', 0)
        pnl_emoji = '\U0001F4C8' if total_pnl >= 0 else '\U0001F4C9'

        message += f"{pnl_emoji} <b>Total P&L:</b> Rs.{total_pnl:,.2f}\n"
        message += f"<b>Realized P&L:</b> Rs.{data.get('realized_pnl', 0):,.2f}\n"
        message += f"<b>Unrealized P&L:</b> Rs.{data.get('unrealized_pnl', 0):,.2f}\n\n"

        # Trading stats
        message += f"<b>Trades:</b> {data.get('total_trades', 0)}\n"
        message += f"<b>Winners:</b> {data.get('winning_trades', 0)} ({data.get('win_rate', 0):.1f}%)\n"
        message += f"<b>Losers:</b> {data.get('losing_trades', 0)}\n\n"

        # Account status
        message += f"<b>Active Positions:</b> {data.get('active_positions', 0)}\n"
        message += f"<b>Capital Deployed:</b> Rs.{data.get('capital_deployed', 0):,.0f}\n"
        message += f"<b>Margin Available:</b> Rs.{data.get('margin_available', 0):,.0f}\n\n"

        # Risk metrics
        if 'max_drawdown' in data:
            message += f"<b>Max Drawdown:</b> {data['max_drawdown']:.2f}%\n"

        if 'daily_loss_limit_used' in data:
            message += f"<b>Daily Loss Limit:</b> {data['daily_loss_limit_used']:.1f}%\n"

        return message


# Global instance
_telegram_client = None


def get_telegram_client() -> TelegramClient:
    """Get or create global Telegram client instance"""
    global _telegram_client

    if _telegram_client is None:
        _telegram_client = TelegramClient()

    return _telegram_client


def send_notification(
    payload: 'NotificationPayload',
    chat_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Send a structured NotificationPayload via Telegram.

    Preferred entry point for all new notification code.  Uses
    TelegramMessageFormatter for consistent mobile-optimised layout.
    """
    client = get_telegram_client()
    if not client.is_enabled():
        logger.warning("Telegram notifications disabled - client not configured")
        return False, "Telegram client not configured"
    return client.send_notification(payload, chat_id=chat_id)


def send_telegram_notification(
    message: str,
    priority: str = 'INFO',
    chat_id: Optional[str] = None,
    notification_type: Optional[str] = None,
    dedup_key: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Convenience function to send a Telegram notification

    Args:
        message: Message text
        priority: Message priority level
        chat_id: Target chat ID (optional)
        notification_type: Alias for priority (takes precedence if provided)
        dedup_key: Optional explicit dedup key (e.g. 'near_sl_42') — overrides
                   message-hash dedup so per-position alerts don't suppress each other

    Returns:
        Tuple[bool, str]: (success, response)
    """
    if notification_type is not None:
        priority = notification_type

    client = get_telegram_client()

    if not client.is_enabled():
        logger.warning("Telegram notifications disabled - client not configured")
        return False, "Telegram client not configured"

    return client.send_priority_message(message, priority, chat_id, dedup_key=dedup_key)
