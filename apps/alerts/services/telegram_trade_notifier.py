"""
Telegram Trade Notification Service

Sends comprehensive trade suggestions to Telegram with:
- Complete analysis breakdown
- Risk scenarios (5% and 10% losses)
- Entry point details
- Approval buttons for user confirmation
"""

import logging
import html
from decimal import Decimal
from typing import Dict, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from apps.core.models import CredentialStore
from django.conf import settings
import os

logger = logging.getLogger(__name__)


class TelegramTradeNotifier:
    """
    Sends formatted trade notifications to Telegram
    """

    @staticmethod
    def format_futures_trade_notification(
        suggestion_id: int,
        symbol: str,
        direction: str,
        entry_price: Decimal,
        composite_score: int,
        oi_analysis: Dict,
        sector_analysis: Dict,
        technical_analysis: Dict,
        llm_validation: Dict,
        risk_scenarios: Dict,
        entry_point: Dict,
        expiry_date: str
    ) -> tuple[str, InlineKeyboardMarkup]:
        """
        Format comprehensive trade notification for futures

        Args:
            suggestion_id: Trade suggestion ID
            symbol: Stock symbol
            direction: LONG or SHORT
            entry_price: Suggested entry price
            composite_score: Algorithm composite score
            oi_analysis: Open interest analysis results
            sector_analysis: Sector analysis results
            technical_analysis: Technical analysis results
            llm_validation: LLM validation results
            risk_scenarios: Risk/reward scenarios
            entry_point: Entry point detection results
            expiry_date: Contract expiry date

        Returns:
            tuple: (message, reply_markup) for Telegram
        """

        # Direction emoji
        direction_emoji = "📈" if direction == "LONG" else "📉"

        # Escape HTML special characters in dynamic content
        symbol_safe = html.escape(symbol)

        # Build comprehensive message
        message = (
            f"{direction_emoji} <b>NEW FUTURES TRADE OPPORTUNITY</b>\n"
            f"{'=' * 40}\n\n"

            f"<b>🎯 TRADE DETAILS</b>\n"
            f"  Symbol: <b>{symbol_safe}</b>\n"
            f"  Direction: <b>{direction}</b>\n"
            f"  Entry Price: ₹{entry_price:,.2f}\n"
            f"  Expiry: {expiry_date}\n"
            f"  Score: {composite_score}/100\n\n"
        )

        # Entry Point Signal
        if entry_point and entry_point.get('entry_signal'):
            signal_type = entry_point.get('signal_type', 'UNKNOWN')
            signal_strength = entry_point.get('signal_strength', 0) * 100
            entry_reasoning = html.escape(entry_point.get('reasoning', 'N/A'))

            message += (
                f"<b>🎯 ENTRY SIGNAL: {signal_type}</b>\n"
                f"  Strength: {signal_strength:.0f}%\n"
                f"  {entry_reasoning}\n\n"
            )

        # OI Analysis
        oi_signal = oi_analysis.get('signal', 'NEUTRAL')
        buildup_type = oi_analysis.get('buildup_type', 'UNKNOWN')
        pcr = oi_analysis.get('pcr', 0)

        message += (
            f"<b>📊 OPEN INTEREST ANALYSIS</b>\n"
            f"  Signal: {oi_signal}\n"
            f"  Buildup: {buildup_type}\n"
            f"  OI Change: {oi_analysis.get('oi_change_pct', 0):.1f}%\n"
            f"  Price Change: {oi_analysis.get('price_change_pct', 0):.1f}%\n"
            f"  PCR: {pcr:.2f}\n\n"
        )

        # Sector Analysis
        sector_verdict = sector_analysis.get('verdict', 'UNKNOWN')
        sector_perf = sector_analysis.get('performance', {})

        message += (
            f"<b>🏭 SECTOR ANALYSIS</b>\n"
            f"  Verdict: {sector_verdict}\n"
            f"  3D: {sector_perf.get('3d', 0):.2f}%\n"
            f"  7D: {sector_perf.get('7d', 0):.2f}%\n"
            f"  21D: {sector_perf.get('21d', 0):.2f}%\n\n"
        )

        # Technical Indicators
        indicators = entry_point.get('indicators', {}) if entry_point else {}
        message += (
            f"<b>📈 TECHNICAL INDICATORS</b>\n"
            f"  RSI: {indicators.get('rsi', 50):.1f}\n"
            f"  MACD: {indicators.get('macd_signal', 'NEUTRAL')}\n"
            f"  Above 20 DMA: {'✅' if indicators.get('above_20dma') else '❌'}\n"
            f"  Above 50 DMA: {'✅' if indicators.get('above_50dma') else '❌'}\n\n"
        )

        # LLM Validation
        llm_approved = llm_validation.get('approved', False)
        llm_confidence = llm_validation.get('confidence', 0) * 100
        llm_reasoning = html.escape(llm_validation.get('reasoning', 'N/A')[:200])

        message += (
            f"<b>🤖 AI VALIDATION</b>\n"
            f"  Status: {'✅ APPROVED' if llm_approved else '❌ REJECTED'}\n"
            f"  Confidence: {llm_confidence:.1f}%\n"
            f"  Analysis: {llm_reasoning}\n\n"
        )

        # Risk Scenarios
        message += TelegramTradeNotifier._format_risk_scenarios(risk_scenarios)

        # Footer
        message += (
            f"\n<b>⏰ Suggestion ID: #{suggestion_id}</b>\n"
            f"<i>Generated by mCube AI Trading System</i>\n"
        )

        # Create approval buttons
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ APPROVE & EXECUTE",
                    callback_data=f"approve_trade_{suggestion_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ REJECT",
                    callback_data=f"reject_trade_{suggestion_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "📊 VIEW FULL ANALYSIS",
                    callback_data=f"view_analysis_{suggestion_id}"
                ),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        return message, reply_markup

    @staticmethod
    def _format_risk_scenarios(risk_scenarios: Dict) -> str:
        """Format risk scenarios section"""

        loss_5 = risk_scenarios['scenarios']['loss_5pct']
        loss_10 = risk_scenarios['scenarios']['loss_10pct']
        default_sl = risk_scenarios['scenarios']['default_sl']
        default_target = risk_scenarios['scenarios']['default_target']

        risk_reward = Decimal(risk_scenarios['risk_reward_ratio'])

        return (
            f"<b>💰 RISK/REWARD ANALYSIS</b>\n"
            f"{'=' * 40}\n"
            f"  Position Value: ₹{Decimal(risk_scenarios['position_value']):,.0f}\n"
            f"  Quantity: {risk_scenarios['quantity']} lots ({risk_scenarios['total_units']} units)\n\n"

            f"  ⚠️ <b>LOSS SCENARIOS:</b>\n"
            f"  📉 5% Loss: -₹{abs(loss_5['pnl']):,.0f} (Exit: ₹{loss_5['exit_price']:,.2f})\n"
            f"  📉 10% Loss: -₹{abs(loss_10['pnl']):,.0f} (Exit: ₹{loss_10['exit_price']:,.2f})\n"
            f"  🛑 Stop Loss: -₹{abs(default_sl['pnl']):,.0f} (Exit: ₹{default_sl['exit_price']:,.2f})\n\n"

            f"  💵 <b>PROFIT SCENARIOS:</b>\n"
            f"  📈 Target: +₹{abs(default_target['pnl']):,.0f} (Exit: ₹{default_target['exit_price']:,.2f})\n\n"

            f"  <b>Risk/Reward Ratio: {risk_reward:.2f}:1</b>\n"
        )

    @staticmethod
    async def send_trade_notification(
        chat_id: str,
        message: str,
        reply_markup: InlineKeyboardMarkup,
        bot
    ) -> bool:
        """
        Send trade notification to Telegram

        Args:
            chat_id: Telegram chat ID
            message: Formatted message (HTML)
            reply_markup: Inline keyboard markup
            bot: Telegram bot instance

        Returns:
            bool: True if sent successfully
        """

        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            logger.info(f"Trade notification sent to chat {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send trade notification: {e}")
            return False

    @staticmethod
    def get_telegram_credentials() -> tuple[Optional[str], Optional[str]]:
        """
        Get Telegram bot token and chat ID from credentials store

        Returns:
            tuple: (bot_token, chat_id)
        """

        try:
            from apps.core.models import CredentialStore
            creds = CredentialStore.objects.get(service='telegram', name='default')
            return creds.api_key, creds.username  # username field stores chat_id
        except Exception:
            # Fall back to settings or environment variable
            bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', os.getenv('TELEGRAM_BOT_TOKEN'))
            chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', os.getenv('TELEGRAM_CHAT_ID'))
            return bot_token, chat_id

    @staticmethod
    def format_approval_confirmation(
        suggestion_id: int,
        symbol: str,
        direction: str,
        entry_price: Decimal,
        quantity: int
    ) -> str:
        """
        Format approval confirmation message

        Args:
            suggestion_id: Trade suggestion ID
            symbol: Stock symbol
            direction: LONG or SHORT
            entry_price: Entry price
            quantity: Quantity in lots

        Returns:
            str: Formatted confirmation message
        """

        direction_emoji = "📈" if direction == "LONG" else "📉"

        return (
            f"{direction_emoji} <b>TRADE APPROVED</b>\n\n"
            f"Placing order for:\n"
            f"  Symbol: <b>{html.escape(symbol)}</b>\n"
            f"  Direction: {direction}\n"
            f"  Entry: ₹{entry_price:,.2f}\n"
            f"  Quantity: {quantity} lots\n\n"
            f"Order ID: #{suggestion_id}\n\n"
            f"You will receive confirmation once the order is executed."
        )

    @staticmethod
    def format_rejection_message(suggestion_id: int) -> str:
        """
        Format rejection message

        Args:
            suggestion_id: Trade suggestion ID

        Returns:
            str: Formatted rejection message
        """

        return (
            f"❌ <b>TRADE REJECTED</b>\n\n"
            f"Trade suggestion #{suggestion_id} has been rejected.\n\n"
            f"No orders will be placed."
        )

    @staticmethod
    def format_execution_confirmation(
        suggestion_id: int,
        symbol: str,
        direction: str,
        executed_price: Decimal,
        quantity: int,
        order_id: str
    ) -> str:
        """
        Format execution confirmation message

        Args:
            suggestion_id: Trade suggestion ID
            symbol: Stock symbol
            direction: LONG or SHORT
            executed_price: Actual execution price
            quantity: Executed quantity
            order_id: Broker order ID

        Returns:
            str: Formatted confirmation message
        """

        direction_emoji = "📈" if direction == "LONG" else "📉"

        return (
            f"✅ {direction_emoji} <b>ORDER EXECUTED</b>\n\n"
            f"  Symbol: <b>{html.escape(symbol)}</b>\n"
            f"  Direction: {direction}\n"
            f"  Executed Price: ₹{executed_price:,.2f}\n"
            f"  Quantity: {quantity} lots\n\n"
            f"  Order ID: {html.escape(order_id)}\n"
            f"  Suggestion ID: #{suggestion_id}\n\n"
            f"Position is now being monitored."
        )
