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

# Import trading state management
from apps.core.trading_state import is_trading_paused, pause_trading, resume_trading, get_trading_state

logger = logging.getLogger(__name__)


class TelegramBotHandler:
    """
    Telegram bot command handler for trading system control
    """

    def __init__(self):
        """Initialize bot handler"""
        self.bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', os.getenv('TELEGRAM_BOT_TOKEN'))
        self.authorized_chat_ids = self._get_authorized_chats()

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured in settings or environment")

    def _get_authorized_chats(self):
        """Get list of authorized chat IDs"""
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

            # Get account status
            active_accounts = BrokerAccount.objects.filter(is_active=True).count()
            total_accounts = BrokerAccount.objects.count()

            # Get position status
            active_positions = Position.objects.filter(status='ACTIVE').count()

            # Get risk status
            active_breakers = CircuitBreaker.objects.filter(is_active=True).count()

            # Trading pause status
            trading_status = "⏸ PAUSED" if is_trading_paused() else "▶️ RUNNING"

            # Calculate today's P&L
            today = timezone.now().date()
            today_positions = Position.objects.filter(
                status='CLOSED',
                exit_timestamp__date=today
            )
            today_pnl = today_positions.aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0.00')

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
            logger.error(f"Error in status command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command - list all active positions"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            from apps.positions.models import Position

            active_positions = Position.objects.filter(status='ACTIVE').select_related('account')

            if not active_positions.exists():
                await update.message.reply_text("ℹ️ No active positions")
                return

            message = f"📈 <b>ACTIVE POSITIONS ({active_positions.count()})</b>\n{'=' * 40}\n\n"

            for pos in active_positions:
                pnl = pos.unrealized_pnl or Decimal('0.00')
                pnl_icon = "📈" if pnl >= 0 else "📉"

                message += (
                    f"<b>#{pos.id}</b> - {pos.instrument}\n"
                    f"  Account: {pos.account.account_name}\n"
                    f"  Direction: {pos.direction}\n"
                    f"  Entry: ₹{pos.entry_price:,.2f}\n"
                    f"  Current: ₹{pos.current_price:,.2f}\n"
                    f"  {pnl_icon} P&L: ₹{pnl:,.0f}\n"
                    f"  Strategy: {pos.strategy_type}\n\n"
                )

            # Add buttons for quick actions
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="positions_refresh")],
                [InlineKeyboardButton("⚠️ Close All", callback_data="closeall_confirm")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in positions command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

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

            from apps.positions.models import Position

            pos = Position.objects.select_related('account').get(id=position_id)

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
            logger.error(f"Error in position command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def accounts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /accounts command - show all accounts"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            from apps.accounts.models import BrokerAccount
            from apps.positions.models import Position

            accounts = BrokerAccount.objects.all()

            if not accounts.exists():
                await update.message.reply_text("ℹ️ No accounts configured")
                return

            message = f"🏦 <b>BROKER ACCOUNTS ({accounts.count()})</b>\n{'=' * 40}\n\n"

            for acc in accounts:
                status_icon = "✅" if acc.is_active else "❌"

                # Get active position for this account
                active_pos = Position.objects.filter(account=acc, status='ACTIVE').first()

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
            logger.error(f"Error in accounts command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def risk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /risk command - show risk limits"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            from apps.risk.models import RiskLimit, CircuitBreaker
            from apps.accounts.models import BrokerAccount

            message = f"⚠️ <b>RISK LIMITS</b>\n{'=' * 40}\n\n"

            accounts = BrokerAccount.objects.filter(is_active=True)

            for acc in accounts:
                message += f"<b>{acc.account_name}</b>\n"

                # Get today's limits
                today = timezone.now().date()
                limits = RiskLimit.objects.filter(
                    account=acc,
                    period_start=today
                )

                if limits.exists():
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
            active_breakers = CircuitBreaker.objects.filter(is_active=True)
            if active_breakers.exists():
                message += f"\n🚨 <b>ACTIVE CIRCUIT BREAKERS ({active_breakers.count()})</b>\n"
                for breaker in active_breakers:
                    message += (
                        f"  • {breaker.account.account_name}\n"
                        f"    Trigger: {breaker.trigger_type}\n"
                        f"    Value: ₹{breaker.trigger_value:,.0f}\n\n"
                    )

            await update.message.reply_text(message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error in risk command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def pnl_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pnl command - show today's P&L"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            from apps.positions.models import Position

            today = timezone.now().date()
            today_positions = Position.objects.filter(
                status='CLOSED',
                exit_timestamp__date=today
            )

            if not today_positions.exists():
                await update.message.reply_text("ℹ️ No closed positions today")
                return

            total_pnl = today_positions.aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0.00')
            winners = today_positions.filter(realized_pnl__gt=0).count()
            losers = today_positions.filter(realized_pnl__lt=0).count()
            total_trades = today_positions.count()
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
            logger.error(f"Error in pnl command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def pnl_week_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pnl_week command - show this week's P&L"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            from apps.positions.models import Position

            today = timezone.now().date()
            week_start = today - timedelta(days=today.weekday())

            week_positions = Position.objects.filter(
                status='CLOSED',
                exit_timestamp__date__gte=week_start,
                exit_timestamp__date__lte=today
            )

            if not week_positions.exists():
                await update.message.reply_text("ℹ️ No closed positions this week")
                return

            total_pnl = week_positions.aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0.00')
            winners = week_positions.filter(realized_pnl__gt=0).count()
            losers = week_positions.filter(realized_pnl__lt=0).count()
            total_trades = week_positions.count()
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
            logger.error(f"Error in pnl_week command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

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

            from apps.positions.models import Position
            from apps.positions.services.position_manager import close_position

            pos = Position.objects.get(id=position_id)

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
            logger.error(f"Error in close command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def closeall_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /closeall command - close all positions (emergency)"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

        try:
            from apps.positions.models import Position

            active_positions = Position.objects.filter(status='ACTIVE')

            if not active_positions.exists():
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
                f"⚠️ This will close ALL {active_positions.count()} active positions.\n\n"
                f"<b>Positions to be closed:</b>\n"
            )

            for pos in active_positions:
                pnl = pos.unrealized_pnl or Decimal('0.00')
                message += f"  • #{pos.id} - {pos.instrument} (₹{pnl:,.0f})\n"

            message += "\n<b>Are you absolutely sure?</b>"

            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in closeall command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command - pause automated trading"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

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

    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command - resume automated trading"""
        if not self.is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized access")
            return

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
            logger.error(f"Error in logs command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()

        if not self.is_authorized(update):
            await query.edit_message_text("⛔ Unauthorized access")
            return

        try:
            if query.data == "positions_refresh":
                # Refresh positions list
                from apps.positions.models import Position
                active_positions = Position.objects.filter(status='ACTIVE').select_related('account')

                if not active_positions.exists():
                    await query.edit_message_text("ℹ️ No active positions")
                    return

                message = f"📈 <b>ACTIVE POSITIONS ({active_positions.count()})</b>\n{'=' * 40}\n\n"

                for pos in active_positions:
                    pnl = pos.unrealized_pnl or Decimal('0.00')
                    pnl_icon = "📈" if pnl >= 0 else "📉"

                    message += (
                        f"<b>#{pos.id}</b> - {pos.instrument}\n"
                        f"  Account: {pos.account.account_name}\n"
                        f"  Direction: {pos.direction}\n"
                        f"  Entry: ₹{pos.entry_price:,.2f}\n"
                        f"  Current: ₹{pos.current_price:,.2f}\n"
                        f"  {pnl_icon} P&L: ₹{pnl:,.0f}\n\n"
                    )

                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data="positions_refresh")],
                    [InlineKeyboardButton("⚠️ Close All", callback_data="closeall_confirm")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)

            elif query.data.startswith("confirm_close_"):
                # Confirm close specific position
                position_id = int(query.data.split("_")[-1])

                from apps.positions.models import Position
                from apps.positions.services.position_manager import close_position

                pos = Position.objects.get(id=position_id)

                success, closed_pos, message_text = close_position(
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
                from apps.positions.models import Position
                from apps.positions.services.position_manager import close_position

                active_positions = Position.objects.filter(status='ACTIVE')

                closed_count = 0
                failed_count = 0
                total_pnl = Decimal('0.00')

                for pos in active_positions:
                    success, closed_pos, msg = close_position(
                        position=pos,
                        exit_price=pos.current_price,
                        exit_reason="EMERGENCY_CLOSEALL_TELEGRAM_BOT"
                    )

                    if success:
                        closed_count += 1
                        total_pnl += closed_pos.realized_pnl
                    else:
                        failed_count += 1

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
            logger.error(f"Error in button callback: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error: {str(e)}")

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
