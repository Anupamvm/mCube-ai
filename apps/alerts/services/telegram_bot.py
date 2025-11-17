"""
Telegram Bot Command Handler

Interactive Telegram bot for manual control of the trading system.

Available Commands:
- /start - Welcome message and command list
- /help - Show all available commands
- /status - Overall system status
- /positions - List all active positions
- /position <id> - Details of specific position
- /accounts - List all accounts with balances
- /risk - Risk limits and utilization
- /pnl - Today's P&L
- /pnl_week - This week's P&L
- /close <id> - Close a specific position
- /closeall - Emergency: close all positions
- /pause - Pause automated trading
- /resume - Resume automated trading
- /logs - Recent system events

Usage:
    Run as a management command:
    python manage.py run_telegram_bot
"""

import logging
import os
import html
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.conf import settings
from asgiref.sync import sync_to_async

# Import telegram helper functions
from apps.alerts.services.telegram_helpers import (
    get_position_by_id,
    get_active_positions_list,
    fetch_live_positions,
    get_risk_data,
    get_pnl_data,
    get_week_pnl_data,
    close_position_sync,
    close_all_positions_sync
)

# Import trading state management
from apps.core.trading_state import is_trading_paused, pause_trading, resume_trading, get_trading_state

logger = logging.getLogger(__name__)


class TelegramBotHandler:
    """
    Telegram bot command handler for trading system control
    """

    def __init__(self):
        """Initialize bot handler"""
        # Try to get credentials from CredentialStore first, then fall back to settings/env
        self.bot_token = self._get_bot_token()
        self.authorized_chat_ids = self._get_authorized_chats()

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured in CredentialStore, settings, or environment")

    def _get_bot_token(self):
        """Get bot token from CredentialStore, settings, or environment"""
        try:
            from apps.core.models import CredentialStore
            creds = CredentialStore.objects.get(service='telegram', name='default')
            return creds.api_key
        except Exception:
            # Fall back to settings or environment variable
            return getattr(settings, 'TELEGRAM_BOT_TOKEN', os.getenv('TELEGRAM_BOT_TOKEN'))

    def _get_authorized_chats(self):
        """Get list of authorized chat IDs from CredentialStore, settings, or environment"""
        # Try CredentialStore first
        try:
            from apps.core.models import CredentialStore
            creds = CredentialStore.objects.get(service='telegram', name='default')
            chat_id = creds.username  # Chat ID stored in username field
            if chat_id:
                return [str(chat_id)]
        except Exception:
            pass

        # Fall back to settings or environment variable
        chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', os.getenv('TELEGRAM_CHAT_ID'))
        if chat_id:
            return [str(chat_id)]
        return []

    def is_authorized(self, update: Update) -> bool:
        """
        Check if user is authorized to use bot

        SECURITY: Only users with chat IDs in authorized list can use commands
        If no list configured, allows all (development only - NOT for production!)
        """
        if not self.authorized_chat_ids:
            # Development mode - no restrictions
            # WARNING: In production, ALWAYS configure TELEGRAM_CHAT_ID
            logger.warning("No authorized chat IDs configured - allowing all users")
            return True

        # Check if user's chat ID is in authorized list
        chat_id = str(update.effective_chat.id)
        return chat_id in self.authorized_chat_ids

    async def handle_error(self, update: Update, error: Exception, command: str):
        """
        Handle errors gracefully and send user-friendly messages

        Args:
            update: Telegram update object
            error: The exception that occurred
            command: The command that failed (e.g., 'status', 'positions')
        """
        error_msg = str(error)
        logger.error(f"Error in {command} command: {error_msg}", exc_info=True)

        # User-friendly error messages
        user_message = (
            f"❌ <b>Error in /{command} command</b>\n\n"
            f"Something went wrong while processing your request.\n\n"
            f"<b>Details:</b> {error_msg[:200]}\n\n"
            f"Please try again or contact support if the issue persists."
        )

        try:
            # Check if this is a callback query or regular message
            if update.callback_query:
                await update.callback_query.edit_message_text(user_message, parse_mode='HTML')
            elif update.message:
                await update.message.reply_text(user_message, parse_mode='HTML')
        except Exception as send_error:
            logger.error(f"Failed to send error message: {send_error}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        welcome_message = (
            "🤖 <b>mCube Trading System Bot</b>\n\n"
            "Welcome! I can help you monitor and control your trading system.\n\n"
            "<b>Quick Commands:</b>\n"
            "• /status - System overview\n"
            "• /positions - Active positions\n"
            "• /risk - Risk limits\n"
            "• /pnl - Today's P&L\n"
            "• /help - All commands\n\n"
            "Type /help to see all available commands."
        )

        await update.message.reply_text(welcome_message, parse_mode='HTML')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        help_text = (
            "📋 <b>AVAILABLE COMMANDS</b>\n\n"

            "<b>📊 MONITORING</b>\n"
            "• /status - Overall system status\n"
            "• /positions - List all active positions\n"
            "• /position &lt;id&gt; - Details of specific position\n"
            "• /accounts - Account balances and status\n"
            "• /risk - Risk limits and utilization\n"
            "• /logs - Recent system events\n\n"

            "<b>💰 ANALYTICS</b>\n"
            "• /pnl - Today's P&L summary\n"
            "• /pnl_week - This week's P&L\n\n"

            "<b>🎛 TRADING CONTROL</b>\n"
            "• /close &lt;id&gt; - Close specific position\n"
            "• /closeall - ⚠️ Close ALL positions (emergency)\n"
            "• /pause - Pause automated trading\n"
            "• /resume - Resume automated trading\n\n"

            "<b>ℹ️ HELP</b>\n"
            "• /start - Welcome message\n"
            "• /help - This help message\n"
        )

        await update.message.reply_text(help_text, parse_mode='HTML')

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - show overall system status"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            from apps.accounts.models import BrokerAccount
            from apps.positions.models import Position
            from apps.risk.models import CircuitBreaker

            # Get account status (wrapped in sync_to_async)
            @sync_to_async
            def get_account_counts():
                return (
                    BrokerAccount.objects.filter(is_active=True).count(),
                    BrokerAccount.objects.count()
                )

            @sync_to_async
            def get_position_count():
                return Position.objects.filter(status='ACTIVE').count()

            @sync_to_async
            def get_breaker_count():
                return CircuitBreaker.objects.filter(is_active=True).count()

            @sync_to_async
            def get_today_pnl():
                today = timezone.now().date()
                today_positions = Position.objects.filter(
                    status='CLOSED',
                    exit_time__date=today
                )
                return today_positions.aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0.00')

            active_accounts, total_accounts = await get_account_counts()
            active_positions = await get_position_count()
            active_breakers = await get_breaker_count()
            today_pnl = await get_today_pnl()

            # Trading pause status
            trading_status = "⏸ PAUSED" if is_trading_paused() else "▶️ RUNNING"

            status_message = (
                f"📊 <b>SYSTEM STATUS</b>\n"
                f"{'=' * 40}\n\n"
                f"<b>Trading:</b> {trading_status}\n"
                f"<b>Time:</b> {timezone.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n\n"

                f"<b>Accounts:</b> {active_accounts}/{total_accounts} active\n"
                f"<b>Active Positions:</b> {active_positions}\n"
                f"<b>Circuit Breakers:</b> {active_breakers}\n\n"

                f"<b>Today's P&L:</b> ₹{today_pnl:,.0f}\n"
            )

            if active_breakers > 0:
                status_message += f"\n⚠️ <b>WARNING:</b> {active_breakers} active circuit breaker(s)\n"

            if is_trading_paused():
                status_message += f"\n⏸ <b>Automated trading is PAUSED</b>\n"

            await update.message.reply_text(status_message, parse_mode='HTML')

        except Exception as e:
            await self.handle_error(update, e, 'status')

    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command - fetch and list live positions from broker accounts"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            # Send "fetching" message
            status_msg = await update.message.reply_text("📊 Fetching live positions from broker accounts...")

            # Fetch live positions from both brokers
            breeze_positions, kotak_positions, errors = await fetch_live_positions()

            # Count total positions
            total_positions = len(breeze_positions) + len(kotak_positions)

            if total_positions == 0 and not errors:
                await status_msg.edit_text("ℹ️ No active positions found in any broker account")
                return

            # Build detailed message
            message = f"📈 <b>LIVE POSITIONS ({total_positions})</b>\n{'=' * 40}\n\n"

            # Display ICICI Breeze positions
            if breeze_positions:
                message += f"<b>🏦 ICICI BREEZE ({len(breeze_positions)} positions)</b>\n\n"

                for pos in breeze_positions:
                    # Convert Decimal to float for display
                    pnl = float(pos.unrealized_pnl or 0)
                    pnl_icon = "📈" if pnl >= 0 else "📉"
                    direction = "LONG" if pos.net_quantity > 0 else "SHORT" if pos.net_quantity < 0 else "FLAT"

                    # Escape HTML special characters
                    symbol = html.escape(str(pos.symbol))
                    exchange = html.escape(str(pos.exchange_segment))
                    product = html.escape(str(pos.product))

                    message += (
                        f"<b>{symbol}</b>\n"
                        f"  Exchange: {exchange}\n"
                        f"  Product: {product}\n"
                        f"  Direction: {direction}\n"
                        f"  Quantity: {abs(pos.net_quantity)}\n"
                        f"  Avg Price: ₹{float(pos.average_price):,.2f}\n"
                        f"  LTP: ₹{float(pos.ltp):,.2f}\n"
                        f"  {pnl_icon} Unrealized P&L: ₹{pnl:,.2f}\n\n"
                    )

            # Display Kotak Neo positions
            if kotak_positions:
                message += f"<b>🏦 KOTAK NEO ({len(kotak_positions)} positions)</b>\n\n"

                for pos in kotak_positions:
                    # Convert Decimal to float for display
                    pnl = float(pos.unrealized_pnl or 0)
                    pnl_icon = "📈" if pnl >= 0 else "📉"
                    direction = "LONG" if pos.net_quantity > 0 else "SHORT" if pos.net_quantity < 0 else "FLAT"

                    # Escape HTML special characters
                    symbol = html.escape(str(pos.symbol))
                    exchange = html.escape(str(pos.exchange_segment))
                    product = html.escape(str(pos.product))

                    message += (
                        f"<b>{symbol}</b>\n"
                        f"  Exchange: {exchange}\n"
                        f"  Product: {product}\n"
                        f"  Direction: {direction}\n"
                        f"  Quantity: {abs(pos.net_quantity)}\n"
                        f"  Avg Price: ₹{float(pos.average_price):,.2f}\n"
                        f"  LTP: ₹{float(pos.ltp):,.2f}\n"
                        f"  {pnl_icon} Unrealized P&L: ₹{pnl:,.2f}\n\n"
                    )

            # Display errors if any
            if errors:
                message += "\n<b>⚠️ ERRORS:</b>\n"
                for broker, error in errors.items():
                    error_escaped = html.escape(str(error)[:100])
                    message += f"  {broker}: {error_escaped}...\n"

            # Add summary - convert all Decimals to float to avoid type mismatch
            total_pnl = sum(float(p.unrealized_pnl or 0) for p in breeze_positions + kotak_positions)
            pnl_icon = "📈" if total_pnl >= 0 else "📉"
            message += f"\n{pnl_icon} <b>Total Unrealized P&L: ₹{total_pnl:,.2f}</b>\n"

            # Add buttons for quick actions
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="positions_refresh")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Update status message with full results
            await status_msg.edit_text(message, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as e:
            await self.handle_error(update, e, 'positions')

    async def position_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /position <id> command - show specific position details"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text("Usage: /position <id>")
                return

            position_id = int(context.args[0])

            pos = await get_position_by_id(position_id)

            pnl = pos.realized_pnl if pos.status == 'CLOSED' else pos.unrealized_pnl or Decimal('0.00')
            pnl_icon = "📈" if pnl >= 0 else "📉"

            message = (
                f"📊 <b>POSITION #{pos.id}</b>\n"
                f"{'=' * 40}\n\n"

                f"<b>Account:</b> {pos.account.account_name} ({pos.account.broker})\n"
                f"<b>Instrument:</b> {pos.instrument}\n"
                f"<b>Strategy:</b> {pos.strategy_type}\n"
                f"<b>Direction:</b> {pos.direction}\n"
                f"<b>Status:</b> {pos.status}\n\n"

                f"<b>Entry Price:</b> ₹{pos.entry_price:,.2f}\n"
                f"<b>Current Price:</b> ₹{pos.current_price:,.2f}\n"
                f"<b>Quantity:</b> {pos.quantity} lots\n"
                f"<b>Entry Value:</b> ₹{pos.entry_value:,.0f}\n\n"

                f"<b>Stop-Loss:</b> ₹{pos.stop_loss:,.2f}\n"
                f"<b>Target:</b> ₹{pos.target:,.2f}\n\n"

                f"{pnl_icon} <b>P&L:</b> ₹{pnl:,.0f}\n\n"

                f"<b>Entry Time:</b> {pos.entry_timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            )

            if pos.status == 'CLOSED':
                message += (
                    f"<b>Exit Time:</b> {pos.exit_timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"<b>Exit Reason:</b> {pos.exit_reason}\n"
                )

            # Add action buttons
            keyboard = []
            if pos.status == 'ACTIVE':
                keyboard.append([InlineKeyboardButton("⚠️ Close Position", callback_data=f"close_position_{pos.id}")])

            if keyboard:
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
            else:
                await update.message.reply_text(message, parse_mode='HTML')

        except Position.DoesNotExist:
            await update.message.reply_text(f"❌ Position #{position_id} not found")
        except ValueError:
            await update.message.reply_text("❌ Invalid position ID. Must be a number.")
        except Exception as e:
            await self.handle_error(update, e, 'position')

    async def accounts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /accounts command - show all accounts"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            from apps.accounts.models import BrokerAccount
            from apps.positions.models import Position

            @sync_to_async
            def get_accounts_with_positions():
                accounts = list(BrokerAccount.objects.all())
                result = []
                for acc in accounts:
                    active_pos = Position.objects.filter(account=acc, status='ACTIVE').first()
                    result.append((acc, active_pos))
                return result

            accounts_data = await get_accounts_with_positions()

            if not accounts_data:
                await update.message.reply_text("ℹ️ No accounts configured")
                return

            message = f"🏦 <b>BROKER ACCOUNTS ({len(accounts_data)})</b>\n{'=' * 40}\n\n"

            for acc, active_pos in accounts_data:
                status_icon = "✅" if acc.is_active else "❌"

                message += (
                    f"{status_icon} <b>{acc.account_name}</b> ({acc.broker})\n"
                    f"  Balance: ₹{acc.current_balance:,.0f}\n"
                    f"  Margin: ₹{acc.margin_available:,.0f}\n"
                )

                if active_pos:
                    message += f"  Active Position: #{active_pos.id} ({active_pos.instrument})\n"
                else:
                    message += f"  Active Position: None\n"

                message += "\n"

            await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            await self.handle_error(update, e, 'accounts')

    async def risk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /risk command - show risk limits"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            accounts_data, active_breakers = await get_risk_data()

            message = f"⚠️ <b>RISK LIMITS</b>\n{'=' * 40}\n\n"

            for acc, limits in accounts_data:
                message += f"<b>{acc.account_name}</b>\n"

                if limits:
                    for limit in limits:
                        utilization = limit.get_utilization_pct()

                        if limit.is_breached:
                            icon = "🚨"
                        elif utilization >= 80:
                            icon = "⚠️"
                        else:
                            icon = "✅"

                        message += (
                            f"  {icon} {limit.limit_type}: "
                            f"₹{limit.current_value:,.0f} / ₹{limit.limit_value:,.0f} "
                            f"({utilization:.1f}%)\n"
                        )
                else:
                    message += f"  ℹ️ No limits tracked today\n"

                message += "\n"

            # Show active circuit breakers
            if active_breakers:
                message += f"\n🚨 <b>ACTIVE CIRCUIT BREAKERS ({len(active_breakers)})</b>\n"
                for breaker in active_breakers:
                    message += (
                        f"  • {breaker.account.account_name}\n"
                        f"    Trigger: {breaker.trigger_type}\n"
                        f"    Value: ₹{breaker.trigger_value:,.0f}\n\n"
                    )

            await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            await self.handle_error(update, e, 'risk')

    async def pnl_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pnl command - show today's P&L"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            today = timezone.now().date()

            total_pnl, winners, losers, total_trades = await get_pnl_data(today)

            if total_pnl is None:
                await update.message.reply_text("ℹ️ No closed positions today")
                return

            win_rate = (winners / total_trades * 100) if total_trades > 0 else 0

            pnl_icon = "📈" if total_pnl >= 0 else "📉"

            message = (
                f"💰 <b>TODAY'S P&L</b>\n"
                f"{'=' * 40}\n\n"
                f"{pnl_icon} <b>Total P&L:</b> ₹{total_pnl:,.0f}\n\n"
                f"<b>Trades:</b> {total_trades}\n"
                f"<b>Winners:</b> {winners} ({win_rate:.1f}%)\n"
                f"<b>Losers:</b> {losers}\n\n"
                f"<b>Date:</b> {today.strftime('%Y-%m-%d (%A)')}\n"
            )

            await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            await self.handle_error(update, e, 'pnl')

    async def pnl_week_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pnl_week command - show this week's P&L"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            today = timezone.now().date()

            total_pnl, winners, losers, total_trades, week_start = await get_week_pnl_data()

            if total_pnl is None:
                await update.message.reply_text("ℹ️ No closed positions this week")
                return

            win_rate = (winners / total_trades * 100) if total_trades > 0 else 0

            pnl_icon = "📈" if total_pnl >= 0 else "📉"

            message = (
                f"💰 <b>WEEKLY P&L</b>\n"
                f"{'=' * 40}\n\n"
                f"{pnl_icon} <b>Total P&L:</b> ₹{total_pnl:,.0f}\n\n"
                f"<b>Trades:</b> {total_trades}\n"
                f"<b>Winners:</b> {winners} ({win_rate:.1f}%)\n"
                f"<b>Losers:</b> {losers}\n\n"
                f"<b>Week:</b> {week_start.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}\n"
            )

            await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            await self.handle_error(update, e, 'pnl_week')

    async def close_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /close <id> command - close specific position"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text("Usage: /close <position_id>")
                return

            position_id = int(context.args[0])

            pos = await get_position_by_id(position_id)

            if pos.status != 'ACTIVE':
                await update.message.reply_text(f"❌ Position #{position_id} is not active (status: {pos.status})")
                return

            # Confirm before closing
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm Close", callback_data=f"confirm_close_{position_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_close")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = (
                f"⚠️ <b>CONFIRM POSITION CLOSE</b>\n\n"
                f"Position: #{pos.id}\n"
                f"Instrument: {pos.instrument}\n"
                f"Direction: {pos.direction}\n"
                f"Current P&L: ₹{pos.unrealized_pnl or Decimal('0.00'):,.0f}\n\n"
                f"Are you sure you want to close this position?"
            )

            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)

        except Position.DoesNotExist:
            await update.message.reply_text(f"❌ Position #{position_id} not found")
        except ValueError:
            await update.message.reply_text("❌ Invalid position ID. Must be a number.")
        except Exception as e:
            await self.handle_error(update, e, 'close')

    async def closeall_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /closeall command - close all positions (emergency)"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            active_positions = await get_active_positions_list()

            if not active_positions:
                await update.message.reply_text("ℹ️ No active positions to close")
                return

            # Confirm before closing all
            keyboard = [
                [
                    InlineKeyboardButton("✅ CONFIRM CLOSE ALL", callback_data="confirm_closeall"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_closeall")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = (
                f"🚨 <b>EMERGENCY: CLOSE ALL POSITIONS</b>\n\n"
                f"⚠️ This will close ALL {len(active_positions)} active positions.\n\n"
                f"<b>Positions to be closed:</b>\n"
            )

            for pos in active_positions:
                pnl = pos.unrealized_pnl or Decimal('0.00')
                message += f"  • #{pos.id} - {pos.instrument} (₹{pnl:,.0f})\n"

            message += "\n<b>Are you absolutely sure?</b>"

            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as e:
            await self.handle_error(update, e, 'closeall')

    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command - pause automated trading"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            if is_trading_paused():
                await update.message.reply_text("ℹ️ Trading is already paused")
                return

            pause_trading(reason="Manual pause via Telegram bot", paused_by="TELEGRAM_BOT")

            message = (
                "⏸ <b>TRADING PAUSED</b>\n\n"
                "Automated trading has been paused.\n\n"
                "• No new positions will be opened\n"
                "• Existing positions will continue to be monitored\n"
                "• Exit conditions will still be checked\n\n"
                "Use /resume to resume automated trading."
            )

            await update.message.reply_text(message, parse_mode='HTML')
            logger.warning("Trading paused via Telegram bot command")

        except Exception as e:
            await self.handle_error(update, e, 'pause')

    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command - resume automated trading"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            if not is_trading_paused():
                await update.message.reply_text("ℹ️ Trading is not paused")
                return

            resume_trading()

            message = (
                "▶️ <b>TRADING RESUMED</b>\n\n"
                "Automated trading has been resumed.\n\n"
                "• New positions can be opened\n"
                "• All strategies are active\n"
                "• Normal operations restored\n"
            )

            await update.message.reply_text(message, parse_mode='HTML')
            logger.info("Trading resumed via Telegram bot command")

        except Exception as e:
            await self.handle_error(update, e, 'resume')

    async def logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /logs command - show recent system events"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            import os
            from pathlib import Path

            log_file = Path(settings.BASE_DIR) / 'logs' / 'mcube_ai.log'

            if not log_file.exists():
                await update.message.reply_text("ℹ️ No log file found")
                return

            # Read last 20 lines
            with open(log_file, 'r') as f:
                lines = f.readlines()
                recent_lines = lines[-20:] if len(lines) > 20 else lines

            message = (
                f"📋 <b>RECENT LOGS (Last 20 lines)</b>\n"
                f"{'=' * 40}\n\n"
                f"<pre>{(''.join(recent_lines))[:3000]}</pre>"  # Telegram message limit
            )

            await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            await self.handle_error(update, e, 'logs')

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()

        if not self.is_authorized(update):
            await query.edit_message_text("⛔ Unauthorized access")
            return

        try:
            if query.data == "positions_refresh":
                # Refresh positions list - fetch live from brokers
                await query.edit_message_text("📊 Fetching live positions...")

                breeze_positions, kotak_positions, errors = await fetch_live_positions()
                total_positions = len(breeze_positions) + len(kotak_positions)

                if total_positions == 0 and not errors:
                    await query.edit_message_text("ℹ️ No active positions found in any broker account")
                    return

                # Build detailed message
                message = f"📈 <b>LIVE POSITIONS ({total_positions})</b>\n{'=' * 40}\n\n"

                # Display ICICI Breeze positions
                if breeze_positions:
                    message += f"<b>🏦 ICICI BREEZE ({len(breeze_positions)} positions)</b>\n\n"
                    for pos in breeze_positions:
                        # Convert Decimal to float for display
                        pnl = float(pos.unrealized_pnl or 0)
                        pnl_icon = "📈" if pnl >= 0 else "📉"
                        direction = "LONG" if pos.net_quantity > 0 else "SHORT" if pos.net_quantity < 0 else "FLAT"

                        # Escape HTML special characters
                        symbol = html.escape(str(pos.symbol))
                        exchange = html.escape(str(pos.exchange_segment))
                        product = html.escape(str(pos.product))

                        message += (
                            f"<b>{symbol}</b>\n"
                            f"  Exchange: {exchange} | Product: {product}\n"
                            f"  Direction: {direction} | Qty: {abs(pos.net_quantity)}\n"
                            f"  Avg: ₹{float(pos.average_price):,.2f} | LTP: ₹{float(pos.ltp):,.2f}\n"
                            f"  {pnl_icon} P&L: ₹{pnl:,.2f}\n\n"
                        )

                # Display Kotak Neo positions
                if kotak_positions:
                    message += f"<b>🏦 KOTAK NEO ({len(kotak_positions)} positions)</b>\n\n"
                    for pos in kotak_positions:
                        # Convert Decimal to float for display
                        pnl = float(pos.unrealized_pnl or 0)
                        pnl_icon = "📈" if pnl >= 0 else "📉"
                        direction = "LONG" if pos.net_quantity > 0 else "SHORT" if pos.net_quantity < 0 else "FLAT"

                        # Escape HTML special characters
                        symbol = html.escape(str(pos.symbol))
                        exchange = html.escape(str(pos.exchange_segment))
                        product = html.escape(str(pos.product))

                        message += (
                            f"<b>{symbol}</b>\n"
                            f"  Exchange: {exchange} | Product: {product}\n"
                            f"  Direction: {direction} | Qty: {abs(pos.net_quantity)}\n"
                            f"  Avg: ₹{float(pos.average_price):,.2f} | LTP: ₹{float(pos.ltp):,.2f}\n"
                            f"  {pnl_icon} P&L: ₹{pnl:,.2f}\n\n"
                        )

                # Display errors if any
                if errors:
                    message += "\n<b>⚠️ ERRORS:</b>\n"
                    for broker, error in errors.items():
                        error_escaped = html.escape(str(error)[:100])
                        message += f"  {broker}: {error_escaped}...\n"

                # Add summary - convert all Decimals to float to avoid type mismatch
                total_pnl = sum(float(p.unrealized_pnl or 0) for p in breeze_positions + kotak_positions)
                pnl_icon = "📈" if total_pnl >= 0 else "📉"
                message += f"\n{pnl_icon} <b>Total Unrealized P&L: ₹{total_pnl:,.2f}</b>\n"

                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data="positions_refresh")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)

            elif query.data.startswith("confirm_close_"):
                # Confirm close specific position
                position_id = int(query.data.split("_")[-1])

                pos = await get_position_by_id(position_id)

                success, closed_pos, message_text = await close_position_sync(
                    position=pos,
                    exit_price=pos.current_price,
                    exit_reason="MANUAL_TELEGRAM_BOT"
                )

                if success:
                    await query.edit_message_text(
                        f"✅ Position #{position_id} closed successfully\n"
                        f"Realized P&L: ₹{closed_pos.realized_pnl:,.0f}",
                        parse_mode='HTML'
                    )
                else:
                    await query.edit_message_text(
                        f"❌ Failed to close position #{position_id}\n"
                        f"Error: {message_text}",
                        parse_mode='HTML'
                    )

            elif query.data == "cancel_close":
                await query.edit_message_text("❌ Close operation cancelled")

            elif query.data == "confirm_closeall":
                # Close all positions
                closed_count, failed_count, total_pnl = await close_all_positions_sync()

                result_message = (
                    f"✅ <b>CLOSE ALL COMPLETE</b>\n\n"
                    f"Closed: {closed_count}\n"
                    f"Failed: {failed_count}\n"
                    f"Total P&L: ₹{total_pnl:,.0f}"
                )

                await query.edit_message_text(result_message, parse_mode='HTML')

            elif query.data == "cancel_closeall":
                await query.edit_message_text("❌ Close all operation cancelled")

        except Exception as e:
            await self.handle_error(update, e, 'button_callback')

    def run(self):
        """Run the bot"""
        logger.info("Starting Telegram bot...")

        # Create application
        application = Application.builder().token(self.bot_token).build()

        # Add command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(CommandHandler("positions", self.positions_command))
        application.add_handler(CommandHandler("position", self.position_command))
        application.add_handler(CommandHandler("accounts", self.accounts_command))
        application.add_handler(CommandHandler("risk", self.risk_command))
        application.add_handler(CommandHandler("pnl", self.pnl_command))
        application.add_handler(CommandHandler("pnl_week", self.pnl_week_command))
        application.add_handler(CommandHandler("close", self.close_command))
        application.add_handler(CommandHandler("closeall", self.closeall_command))
        application.add_handler(CommandHandler("pause", self.pause_command))
        application.add_handler(CommandHandler("resume", self.resume_command))
        application.add_handler(CommandHandler("logs", self.logs_command))

        # Add callback query handler for buttons
        application.add_handler(CallbackQueryHandler(self.button_callback))

        logger.info("Telegram bot started successfully")
        logger.info("Bot is polling for updates...")

        # Start polling
        application.run_polling(allowed_updates=Update.ALL_TYPES)


def start_bot():
    """Start the Telegram bot"""
    bot = TelegramBotHandler()
    bot.run()
