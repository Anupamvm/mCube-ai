"""
Telegram Client Service

This service handles sending messages to Telegram via Bot API.

Features:
- Send text messages
- Send formatted messages (Markdown/HTML)
- Send messages with buttons
- Error handling and retry logic
"""

import logging
import os
from typing import Dict, List, Optional, Tuple
import requests
from decimal import Decimal

logger = logging.getLogger(__name__)


class TelegramClient:
    """
    Telegram Bot API client for sending notifications

    Configuration:
        TELEGRAM_BOT_TOKEN: Bot token from @BotFather
        TELEGRAM_CHAT_ID: Default chat ID to send messages
    """

    def __init__(self):
        """Initialize Telegram client with credentials from environment"""
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.default_chat_id = os.getenv('TELEGRAM_CHAT_ID')

        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram notifications disabled.")
            self.enabled = False
        else:
            self.enabled = True
            self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def is_enabled(self) -> bool:
        """Check if Telegram client is properly configured"""
        return self.enabled

    def send_message(
        self,
        message: str,
        chat_id: Optional[str] = None,
        parse_mode: str = 'HTML',
        disable_notification: bool = False
    ) -> Tuple[bool, str]:
        """
        Send a text message to Telegram

        Args:
            message: Message text to send
            chat_id: Chat ID to send to (uses default if not provided)
            parse_mode: Message formatting (HTML, Markdown, or None)
            disable_notification: Send silently without notification

        Returns:
            Tuple[bool, str]: (success, response/error message)
        """
        if not self.enabled:
            logger.warning("Telegram client not enabled. Skipping message send.")
            return False, "Telegram client not configured"

        target_chat_id = chat_id or self.default_chat_id

        if not target_chat_id:
            logger.error("No chat_id provided and no default chat_id configured")
            return False, "No chat_id configured"

        url = f"{self.base_url}/sendMessage"

        payload = {
            'chat_id': target_chat_id,
            'text': message,
            'parse_mode': parse_mode,
            'disable_notification': disable_notification
        }

        try:
            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                logger.info(f"Telegram message sent successfully to {target_chat_id}")
                return True, "Message sent successfully"
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

    def send_priority_message(
        self,
        message: str,
        priority: str,
        chat_id: Optional[str] = None
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


def send_telegram_notification(
    message: str,
    priority: str = 'INFO',
    chat_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Convenience function to send a Telegram notification

    Args:
        message: Message text
        priority: Message priority level
        chat_id: Target chat ID (optional)

    Returns:
        Tuple[bool, str]: (success, response)
    """
    client = get_telegram_client()

    if not client.is_enabled():
        logger.warning("Telegram notifications disabled - client not configured")
        return False, "Telegram client not configured"

    return client.send_priority_message(message, priority, chat_id)
