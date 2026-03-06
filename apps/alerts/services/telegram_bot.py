"""
Telegram Bot Command Handler

Interactive Telegram bot for full app control of the mCube trading system.

Available Commands:
- /start - Interactive main menu with inline keyboards
- /test - Test bot connectivity
- /positions - View live positions from all brokers
- /core - Core trading settings
- /trade - Manual trade entry wizard
- /orders - View order book from all brokers
- /margin - View margin and limits
- /pnl - Today's P&L summary
- /analytics - Performance analytics

IMPORTANT: Only ONE instance of this bot should run at a time.
The bot uses a file lock to prevent multiple instances from polling.
"""

import logging
import os
import html
import fcntl
import atexit
from datetime import datetime
from typing import List, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from django.conf import settings
from asgiref.sync import sync_to_async

from apps.alerts.services.telegram_bot_data import DataMixin
from apps.alerts.services.telegram_bot_menus import MenuMixin
from apps.alerts.services.telegram_bot_trade import TradeMixin

logger = logging.getLogger(__name__)

# Singleton lock file path
BOT_LOCK_FILE = '/tmp/mcube_telegram_bot.lock'
_lock_file_handle = None


class TelegramBotHandler(MenuMixin, DataMixin, TradeMixin):
    """
    Telegram bot command handler for position management
    """

    def __init__(self):
        """Initialize bot handler"""
        self.bot_token = self._get_bot_token()
        self.authorized_chat_ids = self._get_authorized_chats()

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured")

    def _get_bot_token(self):
        """Get bot token from CredentialStore, settings, or environment"""
        try:
            from apps.core.models import CredentialStore
            creds = CredentialStore.objects.get(service='telegram', name='default')
            return creds.api_key
        except Exception:
            return getattr(settings, 'TELEGRAM_BOT_TOKEN', os.getenv('TELEGRAM_BOT_TOKEN'))

    def _get_authorized_chats(self):
        """Get list of authorized chat IDs"""
        try:
            from apps.core.models import CredentialStore
            creds = CredentialStore.objects.get(service='telegram', name='default')
            chat_id = creds.username
            if chat_id:
                return [str(chat_id)]
        except Exception:
            pass

        chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', os.getenv('TELEGRAM_CHAT_ID'))
        if chat_id:
            return [str(chat_id)]
        return []

    def is_authorized(self, update: Update) -> bool:
        """Check if user is authorized to use bot"""
        if not self.authorized_chat_ids:
            logger.warning("No authorized chat IDs configured - allowing all users")
            return True
        chat_id = str(update.effective_chat.id)
        return chat_id in self.authorized_chat_ids

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - show interactive main menu"""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return

        await self._show_main_menu(update.message, is_command=True)

    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /test command - simple connectivity test"""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return

        await update.message.reply_text(
            "Bot is working!\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command - show broker selection menu"""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return

        keyboard = [
            [InlineKeyboardButton("ICICI Breeze", callback_data="broker_icici")],
            [InlineKeyboardButton("Kotak Neo", callback_data="broker_kotak")],
            [InlineKeyboardButton("All Brokers", callback_data="broker_all")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "<b>Select Broker</b>\n\nChoose a broker to view positions:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    async def core_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /core command - show and manage core trading settings"""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return

        # Get current config
        config = await self._get_core_config()

        # Format current settings
        futures_status = "ON" if config['enable_futures_trading'] else "OFF"
        options_status = config['options_strategy']

        options_display = {
            'NONE': 'Disabled',
            'AUTO': 'Auto (VIX)',
            'STRANGLE': 'Strangle',
            'BROKEN_IRON_CONDOR': 'Iron Condor'
        }.get(options_status, options_status)

        message = (
            "<b>Core Trading Settings</b>\n\n"
            f"<b>Futures:</b> {futures_status}\n"
            f"<b>Options:</b> {options_display}\n"
            f"<b>Options Lots:</b> {config['options_lots']}\n"
            f"<b>Futures Lots:</b> {config['futures_lots']}\n"
            f"<b>Telegram Confirm:</b> {'ON' if config['require_confirmation'] else 'OFF'}\n\n"
            "<i>Tap to change:</i>"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    f"Futures: {futures_status}",
                    callback_data="core_toggle_futures"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"Options: {options_display}",
                    callback_data="core_options_menu"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"Opt Lots: {config['options_lots']}",
                    callback_data="core_options_lots"
                ),
                InlineKeyboardButton(
                    f"Fut Lots: {config['futures_lots']}",
                    callback_data="core_futures_lots"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"Confirm: {'ON' if config['require_confirmation'] else 'OFF'}",
                    callback_data="core_toggle_confirm"
                ),
            ],
            [InlineKeyboardButton("Refresh", callback_data="core_refresh")],
        ]

        await update.message.reply_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def trade_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trade command - start trade wizard"""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return
        await self._show_trade_broker_selection(update.message, is_command=True)

    async def orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /orders command - show order book"""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return
        breeze_data = await self._get_breeze_orders()
        kotak_data = await self._get_kotak_orders()
        # Build inline message
        now = datetime.now()
        message = f"<b>\U0001f4cb Orders | {now.strftime('%d %b %Y')}</b>\n\n"
        for label, data in [("ICICI Breeze", breeze_data), ("Kotak Neo", kotak_data)]:
            orders = data.get('orders', [])
            message += f"<b>{label} ({len(orders)} orders)</b>\n"
            for i, o in enumerate(orders[:5]):
                sym = str(o.get('trading_symbol', o.get('trdSym', '?')))[:15]
                status = str(o.get('status', o.get('ordSt', '?')))
                message += f"  {i+1}. {sym} | {status}\n"
            if not orders:
                message += "  No orders today\n"
            message += "\n"
        keyboard = [[
            InlineKeyboardButton("\U0001f504 Refresh", callback_data="menu_orders"),
            InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
        ]]
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def margin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /margin command - show margin/limits"""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return
        breeze = await self._get_breeze_margin()
        kotak = await self._get_kotak_margin()
        message = "<b>\U0001f4b3 Margin &amp; Limits</b>\n\n"
        if breeze.get('success'):
            message += f"ICICI: \u20b9{breeze['available']:,.0f} free ({breeze['pct']}%)\n"
        else:
            message += f"ICICI: {breeze.get('error', 'Unavailable')}\n"
        if kotak.get('success'):
            message += f"Kotak: \u20b9{kotak['available']:,.0f} free ({kotak['pct']}%)\n"
        else:
            message += f"Kotak: {kotak.get('error', 'Unavailable')}\n"
        keyboard = [[
            InlineKeyboardButton("Full Details", callback_data="menu_margin"),
            InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
        ]]
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def pnl_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pnl command - show today's P&L"""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return
        data = await self._get_daily_pnl_data()
        def fmt(v):
            return f"+{v:,.0f}" if v >= 0 else f"{v:,.0f}"
        message = (
            f"<b>\U0001f4b0 Today's P&amp;L</b>\n\n"
            f"Realized: {fmt(data['realized'])}\n"
            f"Unrealized: {fmt(data['unrealized'])}\n"
            f"<b>Total: {fmt(data['total'])}</b>\n"
            f"Trades: {data['trades']} | Win%: {data['win_pct']}"
        )
        keyboard = [[
            InlineKeyboardButton("\U0001f504 Refresh", callback_data="menu_pnl"),
            InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
        ]]
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def analytics_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analytics command - show performance summary"""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return
        data = await self._get_performance_summary('FY')
        def fmt_pnl(v):
            return f"+\u20b9{v:,.0f}" if v >= 0 else f"-\u20b9{abs(v):,.0f}"
        message = "<b>\U0001f4c9 Performance | FY</b>\n\n"
        if data.get('total_trades', 0) > 0:
            message += (
                f"Trades: {data['total_trades']} | Win: {data['win_rate']}%\n"
                f"P&L: {fmt_pnl(data['total_pnl'])}\n"
                f"Futures: {data['futures_count']} ({fmt_pnl(data['futures_pnl'])})\n"
                f"Options: {data['options_count']} ({fmt_pnl(data['options_pnl'])})\n"
            )
        else:
            message += "No trades found."
        keyboard = [[
            InlineKeyboardButton("Full Details", callback_data="menu_analytics"),
            InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
        ]]
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /history command - show trade history inline menu."""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return
        data = await self._get_trade_history(10)
        message = "<b>\U0001f4c4 Trade History (Last 10)</b>\n\n"
        if not data.get('success') or not data.get('trades'):
            message += "No closed trades found."
        else:
            for t in data['trades']:
                instrument = t.get('instrument', '?')[:15]
                direction = t.get('direction', '?')
                pnl = float(t.get('net_pnl') or t.get('realized_pnl') or 0)
                pnl_str = f"+\u20b9{pnl:,.0f}" if pnl >= 0 else f"-\u20b9{abs(pnl):,.0f}"
                pnl_icon = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
                message += f"  {pnl_icon} {instrument} {direction} {pnl_str}\n"
            message += (
                f"\nWin Rate: {data['win_rate']}% ({data['wins']}/{data['total_count']})\n"
                f"Total P&L: {'+' if data['total_pnl'] >= 0 else ''}\u20b9{data['total_pnl']:,.0f}"
            )
        keyboard = [[
            InlineKeyboardButton("Full View", callback_data="menu_history"),
            InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
        ]]
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def login_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /login command - show broker login menu."""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return
        keyboard = [[
            InlineKeyboardButton("\U0001f511 Login ICICI", callback_data="login_breeze"),
            InlineKeyboardButton("\U0001f511 Login Kotak", callback_data="login_kotak"),
        ], [
            InlineKeyboardButton("\U0001f4cb Session Status", callback_data="login_view"),
            InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
        ]]
        await update.message.reply_text(
            "<b>\U0001f511 Broker Login</b>\n\nSelect a broker to login:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks using prefix-based routing."""
        query = update.callback_query
        await query.answer()

        if not self.is_authorized(update):
            await query.edit_message_text("Unauthorized access")
            return

        data = query.data

        try:
            await self._route_callback(query, data)
        except Exception as e:
            logger.error(f"Callback error for '{data}': {e}", exc_info=True)
            try:
                await query.edit_message_text(f"Error: {str(e)[:200]}")
            except Exception:
                pass

    async def _route_callback(self, query, data: str):
        """Route callback data to the appropriate handler."""

        # =====================================================================
        # MAIN MENU NAVIGATION (new)
        # =====================================================================
        if data == "back_main":
            await self._show_main_menu(query)
            return

        if data.startswith("menu_"):
            await self._handle_menu_nav(query, data)
            return

        # P&L sub-menu
        if data == "pnl_refresh":
            await self._show_pnl_menu(query)
            return

        # Market sub-menu
        if data == "mkt_refresh":
            await self._show_market_menu(query)
            return

        # Risk sub-menu
        if data == "risk_refresh":
            await self._show_risk_menu(query)
            return

        # System sub-menu
        if data == "sys_refresh":
            await self._show_system_menu(query)
            return

        # Tasks sub-menu
        if data.startswith("task_cat_"):
            category = data.replace("task_cat_", "")
            await self._show_task_category(query, category)
            return

        if data.startswith("task_all_"):
            await self._handle_task_bulk(query, data)
            return

        # Algorithm dependency management
        if data.startswith("algo_"):
            await self._handle_algorithm_action(query, data)
            return

        if data == "back_tasks":
            await self._show_tasks_menu(query)
            return

        if data.startswith("tt_"):
            await self._handle_task_toggle(query, data)
            return

        if data.startswith("tr_"):
            await self._handle_task_run(query, data)
            return

        # Quick actions
        if data.startswith("qa_"):
            await self._handle_quick_action(query, data)
            return

        # =====================================================================
        # NEW FEATURE CALLBACKS
        # =====================================================================

        # Trade wizard
        if data.startswith("trade_"):
            await self._route_trade_callback(query, data)
            return

        # Orders
        if data == "ord_refresh":
            await self._show_orders_menu(query)
            return
        if data.startswith("ord_broker_"):
            broker = data.replace("ord_broker_", "")
            await self._show_broker_orders_detail(query, broker)
            return
        if data.startswith("ord_cancel_kotak_"):
            order_id = data.replace("ord_cancel_kotak_", "")
            result = await self._cancel_kotak_order(order_id)
            if result.get('success'):
                await self._show_broker_orders_detail(query, 'kotak')
            else:
                await query.edit_message_text(f"Cancel failed: {result.get('error', 'Unknown')}")
            return

        # SL modification
        if data.startswith("sl_modify_"):
            position_id = int(data.replace("sl_modify_", ""))
            await self._show_sl_modify_menu(query, position_id)
            return
        if data.startswith("sl_set_"):
            parts = data.split("_")
            position_id = int(parts[2])
            new_sl = int(parts[3]) / 100.0
            result = await self._update_position_sl(position_id, new_sl)
            if result.get('success'):
                msg = f"\u2705 SL updated: {result['instrument']}\n{result.get('old_sl', 'N/A')} \u2192 {new_sl:,.2f}"
            else:
                msg = f"\u274c SL update failed: {result.get('error', 'Unknown')}"
            keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data="back_to_brokers")]]
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Target modification
        if data.startswith("tgt_modify_"):
            position_id = int(data.replace("tgt_modify_", ""))
            await self._show_target_modify_menu(query, position_id)
            return
        if data.startswith("tgt_set_"):
            parts = data.split("_")
            position_id = int(parts[2])
            new_target = int(parts[3]) / 100.0
            result = await self._update_position_target(position_id, new_target)
            if result.get('success'):
                msg = f"\u2705 Target updated: {result['instrument']}\n{result.get('old_target', 'N/A')} \u2192 {new_target:,.2f}"
            else:
                msg = f"\u274c Target update failed: {result.get('error', 'Unknown')}"
            keyboard = [[InlineKeyboardButton("\u00ab Back", callback_data="back_to_brokers")]]
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Margin
        if data == "margin_refresh":
            await self._show_margin_menu(query)
            return

        # Trade history
        if data.startswith("hist_count_"):
            count = int(data.replace("hist_count_", ""))
            await self._show_trade_history_menu(query, count)
            return

        # Broker login
        if data == "login_view":
            await self._show_broker_login_menu(query)
            return
        if data == "login_kotak":
            await query.edit_message_text("\u23f3 Logging in to Kotak Neo...")
            result = await self._trigger_kotak_login()
            await self._show_action_result(query, "Kotak Login", result)
            return
        if data == "login_breeze":
            await query.edit_message_text("\u23f3 Initiating Breeze login...\nSend OTP when prompted.")
            result = await self._trigger_breeze_login()
            await self._show_breeze_login_result(query, result)
            return

        # Analytics
        if data.startswith("analytics_"):
            period = data.replace("analytics_", "")
            await self._show_analytics_menu(query, period)
            return

        # News/Sentiment
        if data == "news_view":
            await self._show_news_sentiment_menu(query)
            return

        # Task schedule editing
        if data.startswith("tsched_edit_"):
            task_key = data.replace("tsched_edit_", "")
            await self._show_task_schedule_menu(query, task_key)
            return
        if data.startswith("tsched_set_"):
            parts = data.replace("tsched_set_", "").rsplit("_", 2)
            if len(parts) == 3:
                task_key = parts[0]
                hour = int(parts[1])
                minute = int(parts[2])
                result = await self._update_task_schedule(task_key, hour, minute)
                if result.get('success'):
                    await self._show_task_schedule_menu(query, task_key)
                else:
                    await query.edit_message_text(f"Error: {result.get('error', 'Unknown')}")
            return

        # =====================================================================
        # BROKER / POSITION CALLBACKS (existing)
        # =====================================================================
        if data == "broker_icici":
            await self._show_icici_positions(query)
        elif data == "broker_kotak":
            await self._show_kotak_positions(query)
        elif data == "broker_all":
            await self._show_all_positions(query)

        elif data == "back_to_brokers":
            keyboard = [
                [InlineKeyboardButton("ICICI Breeze", callback_data="broker_icici")],
                [InlineKeyboardButton("Kotak Neo", callback_data="broker_kotak")],
                [InlineKeyboardButton("All Brokers", callback_data="broker_all")],
                [InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main")],
            ]
            await query.edit_message_text(
                "<b>Select Broker</b>\n\nChoose a broker to view positions:",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        # ICICI Position actions
        elif data.startswith("icici_pos_"):
            pos_index = int(data.split("_")[2])
            await self._show_icici_position_actions(query, pos_index)

        elif data.startswith("icici_close_pct_"):
            parts = data.split("_")
            pos_index = int(parts[3])
            percentage = int(parts[4])
            await self._confirm_icici_close_percentage(query, pos_index, percentage)

        elif data.startswith("icici_exec_close_"):
            parts = data.split("_")
            pos_index = int(parts[3])
            percentage = int(parts[4])
            await self._execute_icici_close_batched(query, pos_index, percentage)

        elif data.startswith("icici_close_"):
            pos_index = int(data.split("_")[2])
            await self._confirm_icici_close(query, pos_index)

        elif data.startswith("icici_avg_"):
            pos_index = int(data.split("_")[2])
            await self._show_icici_average_options(query, pos_index)

        elif data.startswith("icici_confirm_close_"):
            pos_index = int(data.split("_")[3])
            await self._execute_icici_close(query, pos_index)

        elif data.startswith("icici_avg_lots_"):
            parts = data.split("_")
            pos_index = int(parts[3])
            lots = int(parts[4])
            await self._execute_icici_average(query, pos_index, lots)

        # Kotak Position actions
        elif data.startswith("kotak_pos_"):
            pos_index = int(data.split("_")[2])
            await self._show_kotak_position_actions(query, pos_index)

        elif data.startswith("kotak_close_pct_"):
            parts = data.split("_")
            pos_index = int(parts[3])
            percentage = int(parts[4])
            await self._confirm_kotak_close_percentage(query, pos_index, percentage)

        elif data.startswith("kotak_exec_close_"):
            parts = data.split("_")
            pos_index = int(parts[3])
            percentage = int(parts[4])
            await self._execute_kotak_close_batched(query, pos_index, percentage)

        elif data.startswith("kotak_close_"):
            pos_index = int(data.split("_")[2])
            await self._confirm_kotak_close(query, pos_index)

        elif data.startswith("kotak_avg_"):
            pos_index = int(data.split("_")[2])
            await self._show_kotak_average_options(query, pos_index)

        elif data.startswith("kotak_confirm_close_"):
            pos_index = int(data.split("_")[3])
            await self._execute_kotak_close(query, pos_index)

        elif data.startswith("kotak_avg_lots_"):
            parts = data.split("_")
            pos_index = int(parts[3])
            lots = int(parts[4])
            await self._execute_kotak_average(query, pos_index, lots)

        # =================================================================
        # CORE SETTINGS CALLBACKS (/core command)
        # =================================================================

        elif data == "core_toggle_futures":
            await self._toggle_futures_trading(query)

        elif data == "core_toggle_confirm":
            await self._toggle_telegram_confirmation(query)

        elif data == "core_options_menu":
            await self._show_options_strategy_menu(query)

        elif data.startswith("core_set_options_"):
            strategy = data.replace("core_set_options_", "")
            await self._set_options_strategy(query, strategy)

        elif data == "core_options_lots":
            await self._show_lots_menu(query, "options")

        elif data == "core_futures_lots":
            await self._show_lots_menu(query, "futures")

        elif data.startswith("core_set_lots_"):
            parts = data.split("_")
            trade_type = parts[3]  # options or futures
            lots = int(parts[4])
            await self._set_lots(query, trade_type, lots)

        elif data == "core_refresh":
            await self._show_core_settings(query)

        # Position Sizing Mode
        elif data == "core_sizing_menu":
            await self._show_sizing_mode_menu(query)

        elif data.startswith("core_set_sizing_"):
            mode = data.replace("core_set_sizing_", "")
            await self._set_sizing_mode(query, mode)

        # Notification Level
        elif data == "core_notification_menu":
            await self._show_notification_level_menu(query)

        elif data.startswith("core_set_notification_"):
            level = data.replace("core_set_notification_", "")
            await self._set_notification_level(query, level)

        elif data == "core_confirm_autonomous":
            result = await self._update_config_field('notification_level', 'AUTONOMOUS')
            if result['success']:
                await self._show_core_settings(query)
            else:
                await query.edit_message_text(f"Error: {result['error']}")

        # =================================================================
        # TRADE CONFIRMATION CALLBACKS (from trade_confirmation.py)
        # =================================================================

        elif data.startswith("confirm_options_"):
            suggestion_id = int(data.split("_")[2])
            await self._handle_options_confirm(query, suggestion_id)

        elif data.startswith("resize_options_"):
            suggestion_id = int(data.split("_")[2])
            await self._show_options_resize(query, suggestion_id)

        elif data.startswith("options_lots_"):
            parts = data.split("_")
            suggestion_id = int(parts[2])
            lots = int(parts[3])
            await self._handle_options_resize_confirm(query, suggestion_id, lots)

        elif data.startswith("expiry_options_"):
            suggestion_id = int(data.split("_")[2])
            await self._show_options_expiry_toggle(query, suggestion_id)

        elif data.startswith("set_opt_exp_"):
            parts = data.split("_")
            suggestion_id = int(parts[3])
            new_expiry = parts[4]  # YYYYMMDD format
            await self._handle_options_expiry_change(query, suggestion_id, new_expiry)

        elif data.startswith("back_options_"):
            suggestion_id = int(data.split("_")[2])
            await self._resend_options_confirmation(query, suggestion_id)

        elif data.startswith("reject_options_"):
            suggestion_id = int(data.split("_")[2])
            await self._handle_options_reject(query, suggestion_id)

        # =====================================================================
        # TWO-STEP FUTURES APPROVAL FLOW
        # Step 1: select_futures_{id} → Shows detailed view
        # Step 2: confirm_futures_{id} → Spawns background thread for execution
        # =====================================================================

        elif data.startswith("select_futures_"):
            # STEP 1: User selected a suggestion - show detailed view
            suggestion_id = int(data.split("_")[2])
            await self._show_futures_detail(query, suggestion_id)

        elif data.startswith("confirm_futures_"):
            # STEP 2: User confirmed - spawn background thread for execution
            suggestion_id = int(data.split("_")[2])
            await self._handle_futures_confirm_with_thread(query, suggestion_id)

        elif data.startswith("expiry_futures_"):
            suggestion_id = int(data.split("_")[2])
            await self._show_futures_expiry_toggle(query, suggestion_id)

        elif data.startswith("set_expiry_"):
            parts = data.split("_")
            suggestion_id = int(parts[2])
            new_expiry = parts[3]  # YYYYMMDD format
            await self._handle_futures_expiry_change(query, suggestion_id, new_expiry)

        elif data.startswith("resize_futures_"):
            suggestion_id = int(data.split("_")[2])
            await self._show_futures_resize(query, suggestion_id)

        elif data.startswith("futures_lots_"):
            parts = data.split("_")
            suggestion_id = int(parts[2])
            lots = int(parts[3])
            await self._handle_futures_resize_confirm_with_thread(query, suggestion_id, lots)

        elif data.startswith("reject_futures_"):
            suggestion_id = int(data.split("_")[2])
            await self._handle_futures_reject(query, suggestion_id)

        elif data == "back_futures_list":
            # Go back to selection screen
            await self._show_futures_selection_list(query)

        elif data == "futures_skip_all":
            # Skip all pending futures suggestions
            await self._handle_futures_skip_all(query)

        elif data.startswith("cancel_futures_exec_"):
            # User wants to stop ongoing batch execution
            suggestion_id = int(data.split("_")[3])
            await self._handle_cancel_futures_execution(query, suggestion_id)

        # Monitor dashboard position actions
        elif data.startswith("monitor_pos_"):
            position_id = int(data.split("_")[2])
            await self._handle_monitor_pos(query, position_id)

        elif data.startswith("monitor_close_"):
            parts = data.split("_")
            position_id = int(parts[2])
            pct = int(parts[3]) if len(parts) > 3 else 100
            await self._handle_monitor_close(query, position_id, pct)

        elif data.startswith("monitor_confirm_"):
            parts = data.split("_")
            position_id = int(parts[2])
            pct = int(parts[3]) if len(parts) > 3 else 100
            await self._handle_monitor_confirm(query, position_id, pct)

        elif data.startswith("monitor_cancel_"):
            position_id = int(data.split("_")[2])
            await self._handle_monitor_pos(query, position_id)

        elif data.startswith("monitor_hold_"):
            position_id = int(data.split("_")[2])
            await self._handle_monitor_hold(query, position_id)

        elif data.startswith("monitor_back"):
            await self._handle_monitor_back(query)

        # Exit confirmation (SL/Target hit)
        elif data.startswith("confirm_exit_"):
            position_id = int(data.split("_")[2])
            await self._handle_exit_confirm(query, position_id)

        elif data.startswith("hold_exit_"):
            position_id = int(data.split("_")[2])
            await self._handle_exit_hold(query, position_id)

        # Averaging confirmation
        elif data.startswith("confirm_avg_"):
            parts = data.split("_")
            position_id = int(parts[2])
            lots = int(parts[3])
            await self._handle_averaging_confirm(query, position_id, lots)

        elif data.startswith("skip_avg_"):
            position_id = int(data.split("_")[2])
            await self._handle_averaging_skip(query, position_id)

        # Refresh actions
        elif data == "refresh_icici":
            await self._show_icici_positions(query)
        elif data == "refresh_kotak":
            await self._show_kotak_positions(query)
        elif data == "refresh_all":
            await self._show_all_positions(query)

    # =========================================================================
    # OTP MESSAGE HANDLER (for Breeze auto-login)
    # =========================================================================

    async def otp_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle plain text messages - check for trade wizard input first,
        then check for pending Breeze OTP request.
        """
        if not self.is_authorized(update):
            return

        text = (update.message.text or '').strip()

        # Check if trade wizard needs text input (limit price)
        consumed = await self._handle_trade_text_input(update, text)
        if consumed:
            return

        # Check if Breeze has a pending OTP request
        is_pending = await self._is_breeze_otp_pending()
        if not is_pending:
            return

        # Validate OTP format: 4-6 digits
        import re
        if not re.match(r'^\d{4,6}$', text):
            task_name = await self._get_breeze_otp_task_name()
            await update.message.reply_text(
                f"Invalid OTP format. Please send 4-6 digits.\n"
                f"(Waiting for Breeze OTP for: {task_name})"
            )
            return

        # Store OTP and mark as fulfilled
        await self._fulfill_breeze_otp(text)

        task_name = await self._get_breeze_otp_task_name()
        await update.message.reply_text(
            f"OTP received for Breeze. Processing login...\n"
            f"(Task: {task_name})"
        )

    @sync_to_async(thread_sensitive=False)
    def _is_breeze_otp_pending(self) -> bool:
        """Check if Breeze has a pending OTP request."""
        from django.db import close_old_connections
        close_old_connections()
        from apps.core.models import NseFlag

        return NseFlag.get('breeze_otp_request', '') == 'pending'

    @sync_to_async(thread_sensitive=False)
    def _fulfill_breeze_otp(self, otp: str):
        """Store the OTP value and mark the Breeze OTP request as fulfilled."""
        from django.db import close_old_connections
        close_old_connections()
        from apps.core.models import NseFlag

        NseFlag.set('breeze_otp_value', otp, 'OTP from Telegram')
        NseFlag.set('breeze_otp_request', 'fulfilled', 'OTP fulfilled via Telegram')

    @sync_to_async(thread_sensitive=False)
    def _get_breeze_otp_task_name(self) -> str:
        """Get the task name associated with the current Breeze OTP request."""
        from django.db import close_old_connections
        close_old_connections()
        from apps.core.models import NseFlag

        return NseFlag.get('breeze_otp_task', 'Breeze login')

    # =========================================================================
    # TRADE CONFIRMATION HANDLERS
    # =========================================================================

    async def _handle_options_confirm(self, query, suggestion_id: int):
        """Handle options trade confirmation"""
        await query.edit_message_text("Executing options trade...")

        try:
            result = await self._execute_options_trade(suggestion_id)

            if result.get('success'):
                message = (
                    f"<b>Options Trade Executed</b>\n\n"
                    f"Strategy: {result.get('strategy', 'N/A')}\n"
                    f"Lots: {result.get('lots', 'N/A')}\n"
                    f"Order IDs: {result.get('order_ids', 'N/A')}"
                )
            else:
                message = (
                    f"<b>Trade Failed</b>\n\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            await query.edit_message_text(message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error confirming options trade: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _show_options_resize(self, query, suggestion_id: int):
        """Show options lot resize options"""
        try:
            suggestion = await self._get_suggestion(suggestion_id)
            if not suggestion:
                await query.edit_message_text("Suggestion not found.")
                return

            max_lots = suggestion.get('max_lots', 5)
            recommended = suggestion.get('recommended_lots', 1)

            message = (
                f"<b>Resize Options Trade</b>\n\n"
                f"Strategy: {suggestion.get('strategy', 'N/A')}\n"
                f"Recommended: {recommended} lots\n"
                f"Max Available: {max_lots} lots\n\n"
                f"<b>Select lot count:</b>"
            )

            keyboard = []
            lot_options = [1, 2, 3, 5] if max_lots >= 5 else list(range(1, max_lots + 1))
            row = []
            for lots in lot_options:
                if lots <= max_lots:
                    label = f"{lots} Lot{'s' if lots > 1 else ''}"
                    if lots == recommended:
                        label += " (Rec)"
                    row.append(InlineKeyboardButton(label, callback_data=f"options_lots_{suggestion_id}_{lots}"))
                    if len(row) == 3:
                        keyboard.append(row)
                        row = []
            if row:
                keyboard.append(row)

            keyboard.append([InlineKeyboardButton("Cancel", callback_data=f"reject_options_{suggestion_id}")])

            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logger.error(f"Error showing options resize: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_options_resize_confirm(self, query, suggestion_id: int, lots: int):
        """Handle options trade with custom lot size"""
        await query.edit_message_text(f"Executing options trade with {lots} lots...")

        try:
            result = await self._execute_options_trade(suggestion_id, custom_lots=lots)

            if result.get('success'):
                message = (
                    f"<b>Options Trade Executed</b>\n\n"
                    f"Strategy: {result.get('strategy', 'N/A')}\n"
                    f"Lots: {lots}\n"
                    f"Order IDs: {result.get('order_ids', 'N/A')}"
                )
            else:
                message = (
                    f"<b>Trade Failed</b>\n\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            await query.edit_message_text(message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error executing options with custom lots: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_options_reject(self, query, suggestion_id: int):
        """Handle options trade rejection"""
        try:
            await self._reject_suggestion(suggestion_id)
            await query.edit_message_text("Trade rejected. Will try again tomorrow.")
        except Exception as e:
            logger.error(f"Error rejecting options trade: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    # =========================================================================
    # OPTIONS EXPIRY CHANGE HANDLERS
    # =========================================================================

    async def _show_options_expiry_toggle(self, query, suggestion_id: int):
        """Show available expiry options for an options suggestion."""
        try:
            suggestion = await self._get_suggestion_obj(suggestion_id)
            if not suggestion:
                await query.edit_message_text("Suggestion not found.")
                return

            expiries = await self._get_available_options_expiries(suggestion)

            if not expiries or len(expiries) < 2:
                await query.edit_message_text(
                    "<b>No alternate expiry available</b>\n\n"
                    f"Instrument: {suggestion.instrument}\n"
                    "Only one options expiry is currently available.\n\n"
                    "<i>Press Back to return.</i>",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Back", callback_data=f"back_options_{suggestion_id}")]
                    ])
                )
                return

            current_expiry = str(suggestion.expiry_date) if suggestion.expiry_date else ''

            message = (
                f"<b>📅 Change Expiry</b>\n\n"
                f"Instrument: {suggestion.instrument}\n"
                f"Strategy: {suggestion.get_strategy_display()}\n\n"
                f"⚠️ <i>Strikes and premiums may differ for other expiries.</i>\n\n"
                f"<b>Select expiry:</b>"
            )

            keyboard = []
            for exp in expiries:
                label = f"📅 {exp['expiry_formatted']} ({exp['days_to_expiry']}d)"
                if exp['expiry_date'] == current_expiry:
                    label += " ← Current"
                # Callback: set_opt_exp_{id}_{YYYYMMDD}
                expiry_compact = exp['expiry_date'].replace('-', '')
                keyboard.append([InlineKeyboardButton(label, callback_data=f"set_opt_exp_{suggestion_id}_{expiry_compact}")])

            keyboard.append([InlineKeyboardButton("◀️ Back", callback_data=f"back_options_{suggestion_id}")])

            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logger.error(f"Error showing options expiry toggle: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_options_expiry_change(self, query, suggestion_id: int, new_expiry_compact: str):
        """Handle user selecting a new expiry for an options suggestion."""
        try:
            # Convert YYYYMMDD to YYYY-MM-DD
            new_expiry = f"{new_expiry_compact[:4]}-{new_expiry_compact[4:6]}-{new_expiry_compact[6:]}"

            result = await self._update_options_suggestion_expiry(suggestion_id, new_expiry)

            if not result.get('success'):
                await query.edit_message_text(
                    f"<b>Expiry change failed</b>\n\n{result.get('error', 'Unknown error')}",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Back", callback_data=f"back_options_{suggestion_id}")]
                    ])
                )
                return

            # Re-send the options confirmation with updated expiry
            await self._resend_options_confirmation(query, suggestion_id)

        except Exception as e:
            logger.error(f"Error changing options expiry: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _resend_options_confirmation(self, query, suggestion_id: int):
        """Re-display options confirmation message after expiry change."""
        try:
            suggestion = await self._get_suggestion_obj(suggestion_id)
            if not suggestion:
                await query.edit_message_text("Suggestion not found.")
                return

            from apps.trading.services.trade_confirmation import get_confirmation_service
            get_confirmation_service()

            from apps.core.models import TradingCoreConfig
            config = await sync_to_async(TradingCoreConfig.get_instance)()

            # Rebuild the message and keyboard (same as request_options_confirmation but inline)
            strategy = await sync_to_async(suggestion.get_strategy_display)()
            call_strike = suggestion.call_strike or 0
            put_strike = suggestion.put_strike or 0
            total_premium = suggestion.total_premium or 0
            lots = suggestion.recommended_lots or config.options_lots

            expiry_line = ''
            if suggestion.expiry_date:
                from datetime import date
                days_to_exp = (suggestion.expiry_date - date.today()).days
                expiry_fmt = suggestion.expiry_date.strftime('%d-%b-%Y')
                expiry_line = f"<b>📅 Expiry:</b> {expiry_fmt} ({days_to_exp}d)\n"

                details = suggestion.position_details or {}
                if details.get('expiry_changed'):
                    original = details.get('original_expiry', '')
                    expiry_line += f"⚠️ <i>Changed from original: {original}</i>\n"

            message = (
                f"📊 <b>OPTIONS TRADE CONFIRMATION</b>\n\n"
                f"Strategy: {strategy}\n"
                f"Instrument: {suggestion.instrument}\n"
                f"Direction: {suggestion.direction}\n"
                f"{expiry_line}\n"
                f"<b>Strikes:</b>\n"
                f"  • Call: {call_strike:,.0f}\n"
                f"  • Put: {put_strike:,.0f}\n\n"
                f"<b>Position:</b>\n"
                f"  • Lots: {lots}\n"
                f"  • Premium: ₹{total_premium:,.0f}\n"
                f"  • Margin: ₹{suggestion.margin_required or 0:,.0f}\n\n"
                f"<b>Risk:</b>\n"
                f"  • Max Loss: ₹{suggestion.max_loss or 0:,.0f}\n"
                f"  • R:R Ratio: {suggestion.risk_reward_ratio or 0:.2f}\n\n"
                f"<i>Reply with lot count to modify, or use buttons below:</i>"
            )

            keyboard = [
                [InlineKeyboardButton(f'✅ Confirm ({lots} lots)', callback_data=f'confirm_options_{suggestion.id}')],
                [
                    InlineKeyboardButton('📊 Change Size', callback_data=f'resize_options_{suggestion.id}'),
                    InlineKeyboardButton('📅 Change Expiry', callback_data=f'expiry_options_{suggestion.id}'),
                ],
                [InlineKeyboardButton('❌ Reject', callback_data=f'reject_options_{suggestion.id}')],
            ]

            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logger.error(f"Error resending options confirmation: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    @sync_to_async(thread_sensitive=False)
    def _get_available_options_expiries(self, suggestion) -> list:
        """Get available options expiries for a suggestion's instrument."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.data.models import OptionChain
            from datetime import date

            instrument = suggestion.instrument
            today = date.today()

            # Get distinct expiry dates from OptionChain
            db_expiries = (
                OptionChain.objects
                .filter(underlying=instrument, expiry_date__gte=today)
                .values_list('expiry_date', flat=True)
                .distinct()
                .order_by('expiry_date')
            )
            expiry_dates = sorted(set(db_expiries))

            # Fallback to weekly expiry utilities if no DB data
            if not expiry_dates:
                from apps.core.utils import get_current_weekly_expiry, get_next_weekly_expiry
                current_week = get_current_weekly_expiry(instrument)
                next_week = get_next_weekly_expiry(instrument)
                expiry_dates = sorted(set([current_week, next_week]))

            expiries = []
            for expiry_dt in expiry_dates:
                days_to_expiry = (expiry_dt - today).days
                if days_to_expiry < 0:
                    continue

                expiries.append({
                    'expiry_date': str(expiry_dt),
                    'expiry_formatted': expiry_dt.strftime('%d-%b-%Y'),
                    'days_to_expiry': days_to_expiry,
                })

            return expiries

        except Exception as e:
            logger.error(f"Error getting available options expiries: {e}")
            return []

    @sync_to_async(thread_sensitive=False)
    def _update_options_suggestion_expiry(self, suggestion_id: int, new_expiry: str) -> dict:
        """Update an options suggestion's expiry date."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.trading.models import TradeSuggestion
            from datetime import date

            suggestion = TradeSuggestion.objects.get(id=suggestion_id)

            new_expiry_dt = datetime.strptime(new_expiry, '%Y-%m-%d').date()

            # Preserve original expiry on first change
            details = suggestion.position_details or {}
            if not details.get('original_expiry') and suggestion.expiry_date:
                details['original_expiry'] = str(suggestion.expiry_date)

            details['expiry_date'] = new_expiry
            details['expiry_changed'] = (new_expiry != details.get('original_expiry', new_expiry))

            suggestion.position_details = details
            suggestion.expiry_date = new_expiry_dt
            suggestion.days_to_expiry = (new_expiry_dt - date.today()).days

            suggestion.save()

            logger.info(f"Updated options suggestion {suggestion_id} expiry to {new_expiry}")
            return {'success': True}

        except TradeSuggestion.DoesNotExist:
            return {'success': False, 'error': 'Suggestion not found'}
        except Exception as e:
            logger.error(f"Error updating options suggestion expiry: {e}")
            return {'success': False, 'error': str(e)}

    async def _handle_futures_confirm(self, query, suggestion_id: int):
        """Handle futures trade confirmation"""
        await query.edit_message_text("Executing futures trade...")

        try:
            result = await self._execute_futures_trade(suggestion_id)

            if result.get('success'):
                message = (
                    f"<b>Futures Trade Executed</b>\n\n"
                    f"Symbol: {result.get('symbol', 'N/A')}\n"
                    f"Direction: {result.get('direction', 'N/A')}\n"
                    f"Lots: {result.get('lots', 'N/A')}\n"
                    f"Entry Price: {result.get('entry_price', 'N/A')}\n"
                    f"Order ID: {result.get('order_id', 'N/A')}"
                )
            else:
                message = (
                    f"<b>Trade Failed</b>\n\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            await query.edit_message_text(message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error confirming futures trade: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    # =========================================================================
    # FUTURES EXPIRY CHANGE HANDLERS
    # =========================================================================

    async def _show_futures_expiry_toggle(self, query, suggestion_id: int):
        """Show available expiry options for a futures suggestion."""
        try:
            suggestion = await self._get_suggestion_obj(suggestion_id)
            if not suggestion:
                await query.edit_message_text("Suggestion not found.")
                return

            expiries = await self._get_available_expiries(suggestion)

            if not expiries or len(expiries) < 2:
                # Only one expiry available — no alternate
                await query.edit_message_text(
                    "<b>No alternate expiry available</b>\n\n"
                    f"Symbol: {suggestion.instrument}\n"
                    "Only one futures expiry is currently available for this contract.\n\n"
                    "<i>Press Back to return.</i>",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Back to Details", callback_data=f"select_futures_{suggestion_id}")]
                    ])
                )
                return

            current_expiry = (suggestion.position_details or {}).get('expiry_date', '')

            message = (
                f"<b>📅 Change Expiry</b>\n\n"
                f"Symbol: {suggestion.instrument}\n"
                f"Direction: {suggestion.direction}\n\n"
                f"⚠️ <i>Analysis scores were computed for the original expiry.</i>\n\n"
                f"<b>Select expiry:</b>"
            )

            keyboard = []
            for exp in expiries:
                if not exp['has_instrument']:
                    continue
                label = f"📅 {exp['expiry_formatted']} ({exp['days_to_expiry']}d)"
                if exp['expiry_date'] == current_expiry:
                    label += " ← Current"
                # Callback: set_expiry_{id}_{YYYYMMDD}
                expiry_compact = exp['expiry_date'].replace('-', '')
                keyboard.append([InlineKeyboardButton(label, callback_data=f"set_expiry_{suggestion_id}_{expiry_compact}")])

            keyboard.append([InlineKeyboardButton("◀️ Back to Details", callback_data=f"select_futures_{suggestion_id}")])

            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logger.error(f"Error showing expiry toggle: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_futures_expiry_change(self, query, suggestion_id: int, new_expiry_compact: str):
        """Handle user selecting a new expiry for a futures suggestion."""
        try:
            # Convert YYYYMMDD to YYYY-MM-DD
            new_expiry = f"{new_expiry_compact[:4]}-{new_expiry_compact[4:6]}-{new_expiry_compact[6:]}"

            result = await self._update_suggestion_expiry(suggestion_id, new_expiry)

            if not result.get('success'):
                await query.edit_message_text(
                    f"<b>Expiry change failed</b>\n\n{result.get('error', 'Unknown error')}",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Back to Details", callback_data=f"select_futures_{suggestion_id}")]
                    ])
                )
                return

            # Return to detail view which will now show the updated expiry
            await self._show_futures_detail(query, suggestion_id)

        except Exception as e:
            logger.error(f"Error changing expiry: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    @sync_to_async(thread_sensitive=False)
    def _get_available_expiries(self, suggestion) -> list:
        """Get available expiries for a suggestion's symbol from ContractData + SecurityMaster."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.data.models import ContractData
            from apps.brokers.utils.security_master import get_futures_instrument
            from datetime import date

            symbol = suggestion.instrument
            today = date.today()

            contracts = ContractData.objects.filter(
                symbol=symbol,
                option_type='FUTURE',
            ).order_by('expiry')

            seen = set()
            expiries = []
            for contract in contracts:
                if contract.expiry in seen:
                    continue
                seen.add(contract.expiry)

                try:
                    expiry_dt = datetime.strptime(contract.expiry, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue

                if expiry_dt < today:
                    continue

                days_to_expiry = (expiry_dt - today).days
                expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()
                instrument = get_futures_instrument(symbol, expiry_breeze)

                expiries.append({
                    'expiry_date': contract.expiry,
                    'expiry_formatted': expiry_dt.strftime('%d-%b-%Y'),
                    'days_to_expiry': days_to_expiry,
                    'has_instrument': instrument is not None,
                    'lot_size': contract.lot_size,
                    'contract_price': contract.price,
                })

            return expiries

        except Exception as e:
            logger.error(f"Error getting available expiries: {e}")
            return []

    @sync_to_async(thread_sensitive=False)
    def _update_suggestion_expiry(self, suggestion_id: int, new_expiry: str) -> dict:
        """Update a suggestion's expiry date in position_details and model field."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.trading.models import TradeSuggestion
            from apps.data.models import ContractData
            from apps.brokers.utils.security_master import get_futures_instrument
            from datetime import date

            suggestion = TradeSuggestion.objects.get(id=suggestion_id)

            # Validate the new expiry has a contract
            contract = ContractData.objects.filter(
                symbol=suggestion.instrument,
                option_type='FUTURE',
                expiry=new_expiry,
            ).first()

            if not contract:
                return {'success': False, 'error': f'No contract found for {suggestion.instrument} expiry {new_expiry}'}

            # Validate SecurityMaster has instrument
            expiry_dt = datetime.strptime(new_expiry, '%Y-%m-%d').date()
            expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()
            instrument = get_futures_instrument(suggestion.instrument, expiry_breeze)

            if not instrument:
                return {'success': False, 'error': f'No instrument found in SecurityMaster for {new_expiry}'}

            # Update position_details
            details = suggestion.position_details or {}
            current_expiry = details.get('expiry_date', '')

            # Preserve original expiry on first change
            if not details.get('original_expiry'):
                details['original_expiry'] = current_expiry

            details['expiry_date'] = new_expiry
            details['expiry_changed'] = (new_expiry != details.get('original_expiry', new_expiry))

            suggestion.position_details = details

            # Update model-level expiry field too
            suggestion.expiry_date = expiry_dt
            suggestion.days_to_expiry = (expiry_dt - date.today()).days

            suggestion.save()

            logger.info(f"Updated suggestion {suggestion_id} expiry: {current_expiry} -> {new_expiry}")
            return {'success': True}

        except TradeSuggestion.DoesNotExist:
            return {'success': False, 'error': 'Suggestion not found'}
        except Exception as e:
            logger.error(f"Error updating suggestion expiry: {e}")
            return {'success': False, 'error': str(e)}

    async def _show_futures_resize(self, query, suggestion_id: int):
        """Show futures lot resize options"""
        try:
            suggestion = await self._get_suggestion(suggestion_id)
            if not suggestion:
                await query.edit_message_text("Suggestion not found.")
                return

            max_lots = suggestion.get('max_lots', 5)
            recommended = suggestion.get('recommended_lots', 1)

            message = (
                f"<b>Resize Futures Trade</b>\n\n"
                f"Symbol: {suggestion.get('symbol', 'N/A')}\n"
                f"Direction: {suggestion.get('direction', 'N/A')}\n"
                f"Recommended: {recommended} lots\n"
                f"Max Available: {max_lots} lots\n\n"
                f"<b>Select lot count:</b>"
            )

            keyboard = []
            lot_options = [1, 2, 3, 5, 10] if max_lots >= 10 else list(range(1, min(max_lots + 1, 6)))
            row = []
            for lots in lot_options:
                if lots <= max_lots:
                    label = f"{lots} Lot{'s' if lots > 1 else ''}"
                    if lots == recommended:
                        label += " (Rec)"
                    row.append(InlineKeyboardButton(label, callback_data=f"futures_lots_{suggestion_id}_{lots}"))
                    if len(row) == 3:
                        keyboard.append(row)
                        row = []
            if row:
                keyboard.append(row)

            keyboard.append([InlineKeyboardButton("Skip", callback_data=f"reject_futures_{suggestion_id}")])

            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logger.error(f"Error showing futures resize: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_futures_resize_confirm(self, query, suggestion_id: int, lots: int):
        """Handle futures trade with custom lot size"""
        await query.edit_message_text(f"Executing futures trade with {lots} lots...")

        try:
            result = await self._execute_futures_trade(suggestion_id, custom_lots=lots)

            if result.get('success'):
                message = (
                    f"<b>Futures Trade Executed</b>\n\n"
                    f"Symbol: {result.get('symbol', 'N/A')}\n"
                    f"Direction: {result.get('direction', 'N/A')}\n"
                    f"Lots: {lots}\n"
                    f"Entry Price: {result.get('entry_price', 'N/A')}\n"
                    f"Order ID: {result.get('order_id', 'N/A')}"
                )
            else:
                message = (
                    f"<b>Trade Failed</b>\n\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            await query.edit_message_text(message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error executing futures with custom lots: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_futures_reject(self, query, suggestion_id: int):
        """Handle futures trade rejection"""
        try:
            await self._reject_suggestion(suggestion_id)
            await query.edit_message_text("Futures suggestion skipped.")
        except Exception as e:
            logger.error(f"Error rejecting futures trade: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    # =========================================================================
    # TWO-STEP FUTURES APPROVAL HANDLERS
    # =========================================================================

    async def _show_futures_detail(self, query, suggestion_id: int):
        """
        STEP 1 → STEP 2: Show detailed view for a selected futures suggestion.

        User clicked "View Details" - now show full analysis with Confirm button.
        """
        try:
            suggestion = await self._get_suggestion_obj(suggestion_id)
            if not suggestion:
                await query.edit_message_text("Suggestion not found or expired.")
                return

            # Build detailed message using TradeConfirmationService
            from apps.trading.services.trade_confirmation import get_confirmation_service
            confirmation_service = get_confirmation_service()
            message, keyboard_dict = confirmation_service.build_futures_detail_message(suggestion)

            # Convert to Telegram keyboard format
            keyboard = []
            for row in keyboard_dict['inline_keyboard']:
                btn_row = []
                for btn in row:
                    btn_row.append(InlineKeyboardButton(btn['text'], callback_data=btn['callback_data']))
                keyboard.append(btn_row)

            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logger.error(f"Error showing futures detail: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_futures_confirm_with_thread(self, query, suggestion_id: int, lots: int = None):
        """
        STEP 2 → EXECUTION: User confirmed trade - spawn background thread.

        The trade execution runs in a separate thread to avoid blocking the bot.
        User sees immediate feedback, then progress updates.
        """
        try:
            suggestion = await self._get_suggestion_obj(suggestion_id)
            if not suggestion:
                await query.edit_message_text("Suggestion not found or expired.")
                return

            symbol = suggestion.instrument
            direction = suggestion.direction
            final_lots = lots or suggestion.recommended_lots or 1

            # Show immediate confirmation that execution is starting
            await query.edit_message_text(
                f"🚀 <b>EXECUTING TRADE</b>\n\n"
                f"Symbol: {symbol}\n"
                f"Direction: {direction}\n"
                f"Lots: {final_lots}\n\n"
                f"<i>Trade executing in background...</i>\n"
                f"<i>You'll receive progress updates.</i>",
                parse_mode='HTML'
            )

            # Spawn background thread for execution
            import threading
            execution_thread = threading.Thread(
                target=self._execute_futures_in_background,
                args=(suggestion_id, final_lots, str(query.message.chat_id), query.message.message_id),
                daemon=True
            )
            execution_thread.start()

            logger.info(f"Spawned background thread for futures execution: {symbol} ({final_lots} lots)")

        except Exception as e:
            logger.error(f"Error starting futures execution: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    def _execute_futures_in_background(self, suggestion_id: int, lots: int, chat_id: str, message_id: int):
        """
        Background thread execution for futures trade.

        This runs in a separate thread and sends Telegram updates for progress.
        Uses batching for large orders (10 lots per batch, 10 seconds between).
        User can click "Stop Execution" button to cancel remaining batches.
        """
        import requests
        from django.db import close_old_connections

        # Close stale DB connections for thread safety
        close_old_connections()

        try:
            from apps.trading.services.trade_confirmation import get_confirmation_service
            from apps.trading.models import TradeSuggestion
            from apps.core.models import NseFlag

            # Get suggestion
            suggestion = TradeSuggestion.objects.get(id=suggestion_id)

            # Store execution info in NseFlag for cancel button lookup
            NseFlag.set(f'futures_exec_{suggestion_id}', f'{chat_id}:{message_id}')

            # Progress callback for batched execution
            def progress_callback(batch_num, total_batches, batch_result):
                """Send progress update via Telegram with Stop button"""
                try:
                    bot_token = self._get_bot_token()
                    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"

                    lots_done = batch_result.get('lots_executed', 0)

                    if batch_result.get('success'):
                        progress_text = (
                            f"🔄 <b>EXECUTING TRADE</b>\n\n"
                            f"Symbol: {suggestion.instrument}\n"
                            f"Direction: {suggestion.direction}\n\n"
                            f"📊 Progress: Batch {batch_num}/{total_batches}\n"
                            f"✅ Lots executed: {lots_done}/{lots}\n\n"
                            f"<i>Waiting 10 seconds before next batch...</i>\n"
                            f"<i>Click 'Stop' to cancel remaining batches.</i>"
                        )
                    else:
                        progress_text = (
                            f"⚠️ <b>BATCH {batch_num} ISSUE</b>\n\n"
                            f"Symbol: {suggestion.instrument}\n"
                            f"Error: {batch_result.get('error', 'Unknown')}\n\n"
                            f"Continuing with remaining batches...\n"
                            f"<i>Click 'Stop' to cancel.</i>"
                        )

                    # Include Stop button for cancellation
                    keyboard = {
                        'inline_keyboard': [[
                            {'text': '🛑 Stop Execution', 'callback_data': f'cancel_futures_exec_{suggestion_id}'}
                        ]]
                    }

                    requests.post(url, json={
                        'chat_id': chat_id,
                        'message_id': message_id,
                        'text': progress_text,
                        'parse_mode': 'HTML',
                        'reply_markup': keyboard
                    }, timeout=5)
                except Exception as e:
                    logger.warning(f"Failed to send progress update: {e}")

            # Execute trade
            confirmation_service = get_confirmation_service()
            result = confirmation_service.execute_futures_trade(
                suggestion,
                custom_lots=lots,
                progress_callback=progress_callback
            )

            # Send final result
            bot_token = self._get_bot_token()
            url = f"https://api.telegram.org/bot{bot_token}/editMessageText"

            if result.get('success'):
                final_text = (
                    f"✅ <b>TRADE EXECUTED</b>\n\n"
                    f"Symbol: {result.get('symbol', suggestion.instrument)}\n"
                    f"Direction: {result.get('direction', suggestion.direction)}\n"
                    f"Lots: {lots}\n"
                    f"Avg Price: ₹{result.get('average_price', 0):,.2f}\n"
                    f"Order ID: {result.get('order_id', 'N/A')}\n\n"
                )
                if result.get('batches_executed'):
                    final_text += f"Batches: {result.get('batches_executed')}/{result.get('total_batches', 1)}\n"
                if result.get('simulated'):
                    final_text += "📝 <i>Paper trade - no real order</i>"
            else:
                final_text = (
                    f"❌ <b>TRADE FAILED</b>\n\n"
                    f"Symbol: {suggestion.instrument}\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            requests.post(url, json={
                'chat_id': chat_id,
                'message_id': message_id,
                'text': final_text,
                'parse_mode': 'HTML'
            }, timeout=10)

            # Update suggestion status
            suggestion.status = 'EXECUTED' if result.get('success') else 'FAILED'
            suggestion.save()

        except Exception as e:
            logger.error(f"Background futures execution failed: {e}")
            try:
                bot_token = self._get_bot_token()
                url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
                requests.post(url, json={
                    'chat_id': chat_id,
                    'message_id': message_id,
                    'text': f"❌ <b>EXECUTION ERROR</b>\n\n{str(e)[:200]}",
                    'parse_mode': 'HTML'
                }, timeout=10)
            except:
                pass
        finally:
            close_old_connections()

    async def _handle_futures_resize_confirm_with_thread(self, query, suggestion_id: int, lots: int):
        """Handle futures trade with custom lots - spawn background thread"""
        await self._handle_futures_confirm_with_thread(query, suggestion_id, lots)

    async def _show_futures_selection_list(self, query):
        """
        Go back to the futures selection list.

        Reads pending suggestion IDs from NseFlag and rebuilds the list.
        """
        try:
            from apps.core.models import NseFlag
            from apps.trading.models import TradeSuggestion

            # Get pending suggestion IDs
            suggestion_ids_str = await sync_to_async(NseFlag.get)('pending_futures_suggestions', '')
            if not suggestion_ids_str:
                await query.edit_message_text("No pending futures suggestions.")
                return

            suggestion_ids = [int(x) for x in suggestion_ids_str.split(',') if x]

            # Get suggestions that are still pending
            suggestions = await sync_to_async(list)(
                TradeSuggestion.objects.filter(
                    id__in=suggestion_ids,
                    status='PENDING_CONFIRMATION'
                )
            )

            if not suggestions:
                await query.edit_message_text("No more pending futures suggestions.")
                return

            # Rebuild the selection screen
            from apps.trading.services.trade_confirmation import get_confirmation_service
            confirmation_service = get_confirmation_service()
            success, result = confirmation_service.request_futures_confirmation(suggestions)

            if not success:
                await query.edit_message_text(f"Error rebuilding list: {result}")

        except Exception as e:
            logger.error(f"Error showing futures list: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_futures_skip_all(self, query):
        """Skip all pending futures suggestions"""
        try:
            from apps.core.models import NseFlag

            # Get pending suggestion IDs
            suggestion_ids_str = await sync_to_async(NseFlag.get)('pending_futures_suggestions', '')
            if suggestion_ids_str:
                suggestion_ids = [int(x) for x in suggestion_ids_str.split(',') if x]

                # Mark all as rejected
                for sid in suggestion_ids:
                    try:
                        await self._reject_suggestion(sid)
                    except:
                        pass

                # Clear the pending list
                await sync_to_async(NseFlag.set)('pending_futures_suggestions', '')

            await query.edit_message_text(
                "❌ <b>All Futures Suggestions Skipped</b>\n\n"
                "Will try again tomorrow.",
                parse_mode='HTML'
            )

        except Exception as e:
            logger.error(f"Error skipping all futures: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_cancel_futures_execution(self, query, suggestion_id: int):
        """
        Cancel ongoing batch execution for a futures trade.

        Sets is_cancelled=True in OrderExecutionControl, which the
        background thread checks between batches.
        """
        try:
            from apps.trading.models import OrderExecutionControl, TradeSuggestion
            from apps.core.models import NseFlag

            # Find and cancel the execution control
            @sync_to_async
            def cancel_execution():
                try:
                    exec_control = OrderExecutionControl.objects.get(suggestion_id=suggestion_id)
                    batches_done = exec_control.batches_completed
                    total = exec_control.total_batches
                    exec_control.cancel(reason='User cancelled from Telegram')
                    return True, batches_done, total
                except OrderExecutionControl.DoesNotExist:
                    # No execution control - try using NseFlag as fallback
                    NseFlag.set(f'cancel_futures_{suggestion_id}', 'true')
                    return True, 0, 0

            success, batches_done, total = await cancel_execution()

            if success:
                await query.edit_message_text(
                    f"🛑 <b>EXECUTION STOPPED</b>\n\n"
                    f"Remaining batches cancelled.\n"
                    f"Completed: {batches_done}/{total} batches\n\n"
                    f"<i>Orders already placed will not be reversed.</i>\n"
                    f"<i>Check positions for partial execution.</i>",
                    parse_mode='HTML'
                )

                # Update suggestion status
                @sync_to_async
                def update_suggestion():
                    try:
                        suggestion = TradeSuggestion.objects.get(id=suggestion_id)
                        suggestion.status = 'CANCELLED'
                        suggestion.user_notes = f'User cancelled after {batches_done} batches'
                        suggestion.save()
                    except:
                        pass

                await update_suggestion()
            else:
                await query.edit_message_text(
                    "⚠️ Could not find execution to cancel.\n"
                    "It may have already completed.",
                    parse_mode='HTML'
                )

        except Exception as e:
            logger.error(f"Error cancelling futures execution: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    @sync_to_async
    def _get_suggestion_obj(self, suggestion_id: int):
        """Get TradeSuggestion object by ID"""
        from django.db import close_old_connections
        close_old_connections()
        try:
            from apps.trading.models import TradeSuggestion
            return TradeSuggestion.objects.get(id=suggestion_id)
        except TradeSuggestion.DoesNotExist:
            return None

    # =========================================================================
    # MONITOR DASHBOARD POSITION ACTIONS
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_position_detail(self, position_id: int) -> dict:
        """Fetch position detail for the monitor action menu."""
        from django.db import close_old_connections
        close_old_connections()
        from apps.positions.models import Position
        from apps.positions.services.monitor_dashboard import _fmt_compact, _sl_status
        from decimal import Decimal

        try:
            pos = Position.objects.select_related('account').get(id=position_id)
            lot_size = pos.lot_size or 1
            lots = pos.quantity // lot_size if lot_size > 1 else pos.quantity
            broker_map = {'KOTAK': 'Kotak Neo', 'ICICI': 'ICICI Breeze'}
            broker_name = broker_map.get(
                pos.account.broker if pos.account else '', 'Unknown'
            )
            pnl = pos.unrealized_pnl or Decimal('0')
            entry_val = pos.entry_value if (pos.entry_value and pos.entry_value > 0) else (
                pos.entry_price * pos.quantity
            )
            pnl_pct = (pnl / entry_val * Decimal('100')) if entry_val > 0 else Decimal('0')
            direction_arrow = "▲" if pos.direction == 'LONG' else ("▼" if pos.direction == 'SHORT' else "◆")
            pnl_str = _fmt_compact(pnl, pnl_pct)
            sl_badge = _sl_status(pos)

            lines = [
                f"<b>{pos.instrument}</b>  {direction_arrow} {lots}L",
                f"🏦 {broker_name}",
                f"",
                f"Entry:   ₹{pos.entry_price:,.2f}",
                f"Current: ₹{pos.current_price:,.2f}",
            ]
            if pos.stop_loss:
                sl_dist = pos.current_price - pos.stop_loss
                lines.append(f"SL:      ₹{pos.stop_loss:,.2f}  ({sl_dist:+.2f})")
            if pos.target:
                tgt_dist = pos.target - pos.current_price
                lines.append(f"Target:  ₹{pos.target:,.2f}  ({tgt_dist:+.2f})")
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            lines += [
                f"",
                f"{pnl_emoji} <b>P&L: {pnl_str}</b>{sl_badge}",
                f"",
                f"<i>Choose action below:</i>",
            ]
            return {
                'found': True,
                'text': "\n".join(lines),
                'instrument': pos.instrument,
                'lots': lots,
                'status': pos.status,
            }
        except Exception as e:
            return {'found': False, 'error': str(e)}

    async def _handle_monitor_pos(self, query, position_id: int):
        """Show action menu for a specific position from the monitor dashboard."""
        await query.answer()
        detail = await self._get_position_detail(position_id)

        if not detail.get('found'):
            await query.answer(f"Position not found: {detail.get('error', '')}", show_alert=True)
            return

        if detail['status'] != 'OPEN':
            await query.answer("Position is already closed.", show_alert=True)
            return

        keyboard = [
            [
                InlineKeyboardButton("✅ Close 100%", callback_data=f"monitor_close_{position_id}_100"),
                InlineKeyboardButton("📊 Close 50%", callback_data=f"monitor_close_{position_id}_50"),
            ],
            [
                InlineKeyboardButton("⏸️ Hold / Wait", callback_data=f"monitor_hold_{position_id}"),
                InlineKeyboardButton("← Back", callback_data="monitor_back"),
            ],
        ]

        await query.edit_message_text(
            detail['text'],
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _handle_monitor_close(self, query, position_id: int, pct: int):
        """Show confirmation screen before closing — safety gate for large positions."""
        await query.answer()
        detail = await self._get_position_detail(position_id)

        if not detail.get('found'):
            await query.answer(f"Position not found: {detail.get('error', '')}", show_alert=True)
            return

        if detail['status'] != 'OPEN':
            await query.answer("Position is already closed.", show_alert=True)
            return

        pct_label = "100%" if pct == 100 else f"{pct}% (partial)"
        confirm_text = (
            f"⚠️ <b>Confirm Close {pct_label}</b>\n\n"
            f"{detail['text']}\n\n"
            f"<b>Are you sure you want to close this position?</b>\n"
            f"<i>This action cannot be undone.</i>"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    f"✅ YES — Close {pct_label}",
                    callback_data=f"monitor_confirm_{position_id}_{pct}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ NO — Cancel",
                    callback_data=f"monitor_cancel_{position_id}"
                ),
            ],
        ]

        await query.edit_message_text(
            confirm_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _handle_monitor_confirm(self, query, position_id: int, pct: int):
        """Execute close after user confirmed."""
        await query.edit_message_text("⏳ Closing position...")

        try:
            result = await self._close_position_by_id(position_id)

            if result.get('success'):
                pnl_str = result.get('pnl', 'N/A')
                msg = (
                    f"✅ <b>Position Closed</b>\n\n"
                    f"<b>{result.get('symbol', 'N/A')}</b>\n"
                    f"P&L: {pnl_str}\n"
                    f"Reason: Manual (monitor dashboard)"
                )
            else:
                msg = (
                    f"❌ <b>Close Failed</b>\n\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            await query.edit_message_text(msg, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error closing position {position_id} from monitor: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_monitor_hold(self, query, position_id: int):
        """Acknowledge hold — dismiss the action menu, go back to dashboard."""
        await query.answer("Holding position. Monitor continues.", show_alert=False)
        # Restore the consolidated dashboard by re-triggering the monitor view
        await self._handle_monitor_back(query)

    async def _handle_monitor_back(self, query):
        """Restore the consolidated monitor dashboard in-place."""
        await query.answer()

        dashboard_data = await sync_to_async(self._build_dashboard_data)()

        if not dashboard_data:
            await query.edit_message_text(
                "No open positions found.",
                parse_mode='HTML',
            )
            return

        await query.edit_message_text(
            dashboard_data['message'],
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(dashboard_data['keyboard']),
        )

    def _build_dashboard_data(self):
        """Sync helper: build consolidated message + keyboard for current open positions."""
        from decimal import Decimal
        from collections import Counter
        from django.utils import timezone
        from django.db.models import Sum
        from apps.positions.models import Position
        from apps.positions.services.monitor_dashboard import (
            build_consolidated_message,
            _build_dashboard_keyboard,
            BROKER_DISPLAY,
        )
        from apps.core.models import TradingCoreConfig

        active_positions = list(Position.objects.filter(status='OPEN').select_related('account'))
        if not active_positions:
            return None

        config = TradingCoreConfig.get_instance()
        mode_label = config.get_notification_level_display_short()
        now = timezone.now()
        today = timezone.localdate()

        sym_counts = Counter((p.account_id, p.instrument) for p in active_positions)

        positions_data = []
        for pos in active_positions:
            if pos.direction == 'LONG':
                pnl = (pos.current_price - pos.entry_price) * pos.quantity
            elif pos.direction == 'SHORT':
                pnl = (pos.entry_price - pos.current_price) * pos.quantity
            else:
                pnl = pos.premium_collected

            entry_val = pos.entry_value if pos.entry_value > 0 else (pos.entry_price * pos.quantity)
            pnl_pct = (pnl / entry_val * Decimal('100')) if entry_val > 0 else Decimal('0')

            lot_size = pos.lot_size or 1
            lots = pos.quantity // lot_size if lot_size > 1 else pos.quantity
            broker_name = BROKER_DISPLAY.get(
                pos.account.broker if pos.account else '',
                pos.account.broker if pos.account else 'Unknown'
            )
            positions_data.append({
                'position': pos,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'broker_name': broker_name,
                'lots': lots,
                'needs_avg': sym_counts.get((pos.account_id, pos.instrument), 1) > 1,
                'label': pos.label,
            })

        realized_result = Position.objects.filter(
            status='CLOSED', exit_time__date=today,
        ).aggregate(total=Sum('realized_pnl'))
        realized_today = realized_result['total'] or Decimal('0')

        message = build_consolidated_message(positions_data, mode_label, now, realized_today)
        keyboard_dict = _build_dashboard_keyboard(positions_data)
        keyboard = [
            [InlineKeyboardButton(btn['text'], callback_data=btn['callback_data'])
             for btn in row]
            for row in keyboard_dict['inline_keyboard']
        ]
        return {'message': message, 'keyboard': keyboard}

    async def _handle_exit_confirm(self, query, position_id: int):
        """Handle exit confirmation (close position)"""
        await query.edit_message_text("Closing position...")

        try:
            result = await self._close_position_by_id(position_id)

            if result.get('success'):
                message = (
                    f"<b>Position Closed</b>\n\n"
                    f"Symbol: {result.get('symbol', 'N/A')}\n"
                    f"P&L: {result.get('pnl', 'N/A')}\n"
                    f"Reason: {result.get('reason', 'User confirmed')}"
                )
            else:
                message = (
                    f"<b>Close Failed</b>\n\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            await query.edit_message_text(message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_exit_hold(self, query, position_id: int):
        """Handle hold decision (don't close on SL/Target alert)"""
        try:
            await self._mark_position_hold(position_id)
            await query.edit_message_text(
                "Position will be held.\n\n"
                "You will not receive another alert for this trigger level."
            )
        except Exception as e:
            logger.error(f"Error marking position hold: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_averaging_confirm(self, query, position_id: int, lots: int):
        """Handle averaging confirmation"""
        await query.edit_message_text(f"Adding {lots} lots to position...")

        try:
            result = await self._execute_averaging(position_id, lots)

            if result.get('success'):
                message = (
                    f"<b>Position Averaged</b>\n\n"
                    f"Symbol: {result.get('symbol', 'N/A')}\n"
                    f"Lots Added: {lots}\n"
                    f"New Avg Price: {result.get('new_avg_price', 'N/A')}\n"
                    f"Order ID: {result.get('order_id', 'N/A')}"
                )
            else:
                message = (
                    f"<b>Averaging Failed</b>\n\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            await query.edit_message_text(message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error executing averaging: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    async def _handle_averaging_skip(self, query, position_id: int):
        """Handle averaging skip decision"""
        try:
            await query.edit_message_text("Averaging skipped for this position.")
        except Exception as e:
            logger.error(f"Error skipping averaging: {e}")
            await query.edit_message_text(f"Error: {str(e)[:200]}")

    # =========================================================================
    # TRADE EXECUTION HELPER METHODS
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_suggestion(self, suggestion_id: int) -> dict:
        """Get suggestion details by ID"""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.trading.models import TradeSuggestion
            from apps.trading.services.margin_service import get_available_margin

            suggestion = TradeSuggestion.objects.get(id=suggestion_id)

            # Calculate max lots based on available margin
            available_margin = get_available_margin()
            margin_per_lot = suggestion.margin_per_lot or 100000  # Default if not set

            max_lots = int(available_margin / margin_per_lot) if margin_per_lot > 0 else 5

            return {
                'id': suggestion.id,
                'symbol': suggestion.symbol,
                'strategy': suggestion.strategy_type,
                'direction': suggestion.direction,
                'recommended_lots': suggestion.recommended_lots or 1,
                'max_lots': max(1, min(max_lots, 10)),  # Cap at 10 for safety
                'margin_per_lot': margin_per_lot,
            }
        except Exception as e:
            logger.error(f"Error getting suggestion {suggestion_id}: {e}")
            return None

    @sync_to_async(thread_sensitive=False)
    def _execute_options_trade(self, suggestion_id: int, custom_lots: int = None) -> dict:
        """Execute options trade for a suggestion"""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.trading.models import TradeSuggestion
            from apps.trading.services.trade_confirmation import get_confirmation_service

            suggestion = TradeSuggestion.objects.get(id=suggestion_id)

            # Update lots if custom specified
            if custom_lots:
                suggestion.user_modified_lots = custom_lots
                suggestion.save()

            # Use the confirmation service to execute
            service = get_confirmation_service()
            result = service.execute_options_trade(suggestion, lots=custom_lots)

            return result

        except Exception as e:
            logger.error(f"Error executing options trade: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _execute_futures_trade(self, suggestion_id: int, custom_lots: int = None) -> dict:
        """Execute futures trade for a suggestion"""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.trading.models import TradeSuggestion
            from apps.trading.services.trade_confirmation import get_confirmation_service

            suggestion = TradeSuggestion.objects.get(id=suggestion_id)

            # Update lots if custom specified
            if custom_lots:
                suggestion.user_modified_lots = custom_lots
                suggestion.save()

            # Use the confirmation service to execute
            service = get_confirmation_service()
            result = service.execute_futures_trade(suggestion, lots=custom_lots)

            return result

        except Exception as e:
            logger.error(f"Error executing futures trade: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _reject_suggestion(self, suggestion_id: int):
        """Reject a trade suggestion"""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.trading.models import TradeSuggestion

            suggestion = TradeSuggestion.objects.get(id=suggestion_id)
            suggestion.status = 'REJECTED'
            suggestion.save()

        except Exception as e:
            logger.error(f"Error rejecting suggestion: {e}")
            raise

    @sync_to_async(thread_sensitive=False)
    def _close_position_by_id(self, position_id: int) -> dict:
        """Close a position by its ID"""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.positions.models import Position
            from apps.trading.services.trade_confirmation import get_confirmation_service

            position = Position.objects.get(id=position_id)
            service = get_confirmation_service()
            result = service.close_position(position)

            return result

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _mark_position_hold(self, position_id: int):
        """Mark a position to be held (ignore SL/Target alert)"""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.core.models import NseFlag

            # Use NseFlag to track that user chose to hold
            NseFlag.set(
                f'position_hold_{position_id}',
                'true',
                'User chose to hold position despite SL/Target alert'
            )

        except Exception as e:
            logger.error(f"Error marking position hold: {e}")
            raise

    @sync_to_async(thread_sensitive=False)
    def _execute_averaging(self, position_id: int, lots: int) -> dict:
        """Execute averaging for a position"""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.positions.models import Position
            from apps.trading.services.trade_confirmation import get_confirmation_service

            position = Position.objects.get(id=position_id)
            service = get_confirmation_service()
            result = service.execute_averaging(position, lots)

            return result

        except Exception as e:
            logger.error(f"Error executing averaging: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # CORE SETTINGS HANDLERS (/core command)
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_core_config(self) -> dict:
        """Get current core trading config"""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.core.models import TradingCoreConfig
            config = TradingCoreConfig.get_instance()
            return {
                'enable_futures_trading': config.enable_futures_trading,
                'options_strategy': config.options_strategy,
                'options_lots': config.manual_options_lots,
                'futures_lots': config.manual_futures_lots,
                'require_confirmation': config.require_telegram_confirmation,  # Legacy
                'position_sizing_mode': config.position_sizing_mode,
                'notification_level': config.notification_level,
                'margin_utilization_pct': float(config.margin_utilization_pct),
                # Display helpers
                'sizing_display': config.get_position_sizing_display_short(),
                'notification_display': config.get_notification_level_display_short(),
            }
        except Exception as e:
            logger.error(f"Error getting core config: {e}")
            return {
                'enable_futures_trading': True,
                'options_strategy': 'AUTO',
                'options_lots': 1,
                'futures_lots': 1,
                'require_confirmation': True,
                'position_sizing_mode': 'TEST',
                'notification_level': 'FULL_CONTROL',
                'margin_utilization_pct': 50.0,
                'sizing_display': '🧪 Test (1 lot)',
                'notification_display': '🔒 Full Control',
            }

    async def _show_core_settings(self, query):
        """Show current core settings with buttons"""
        config = await self._get_core_config()

        futures_status = "ON" if config['enable_futures_trading'] else "OFF"
        options_status = config['options_strategy']

        options_display = {
            'NONE': 'Disabled',
            'AUTO': 'Auto (VIX)',
            'STRANGLE': 'Strangle',
            'BROKEN_IRON_CONDOR': 'Iron Condor'
        }.get(options_status, options_status)

        # Build detailed message with new fields
        message = (
            "<b>🎯 Core Trading Settings</b>\n\n"
            f"<b>Trading:</b>\n"
            f"  Futures: {futures_status}\n"
            f"  Options: {options_display}\n\n"
            f"<b>Position Sizing:</b>\n"
            f"  {config['sizing_display']}\n\n"
            f"<b>Notification Level:</b>\n"
            f"  {config['notification_display']}\n\n"
            "<i>Tap to change:</i>"
        )

        keyboard = [
            # Trading toggles
            [
                InlineKeyboardButton(f"Futures: {futures_status}", callback_data="core_toggle_futures"),
                InlineKeyboardButton(f"Options", callback_data="core_options_menu"),
            ],
            # Position Sizing Mode
            [
                InlineKeyboardButton(f"📏 {config['sizing_display']}", callback_data="core_sizing_menu"),
            ],
            # Notification Level
            [
                InlineKeyboardButton(f"📱 {config['notification_display']}", callback_data="core_notification_menu"),
            ],
            # Lots (only show if Manual mode)
            [
                InlineKeyboardButton(f"Opt Lots: {config['options_lots']}", callback_data="core_options_lots"),
                InlineKeyboardButton(f"Fut Lots: {config['futures_lots']}", callback_data="core_futures_lots"),
            ] if config['position_sizing_mode'] == 'MANUAL' else [],
            # Navigation
            [InlineKeyboardButton("🔄 Refresh", callback_data="core_refresh")],
            [InlineKeyboardButton("« Main Menu", callback_data="back_main")],
        ]

        # Filter out empty rows
        keyboard = [row for row in keyboard if row]

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _toggle_futures_trading(self, query):
        """Toggle futures trading on/off"""
        result = await self._toggle_config_field('enable_futures_trading')
        if result['success']:
            await self._show_core_settings(query)
        else:
            await query.edit_message_text(f"Error: {result['error']}")

    async def _toggle_telegram_confirmation(self, query):
        """Toggle telegram confirmation on/off"""
        result = await self._toggle_config_field('require_telegram_confirmation')
        if result['success']:
            await self._show_core_settings(query)
        else:
            await query.edit_message_text(f"Error: {result['error']}")

    @sync_to_async(thread_sensitive=False)
    def _toggle_config_field(self, field_name: str) -> dict:
        """Toggle a boolean config field"""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.core.models import TradingCoreConfig
            config = TradingCoreConfig.get_instance()
            current_value = getattr(config, field_name)
            setattr(config, field_name, not current_value)
            config.save()
            return {'success': True, 'new_value': not current_value}
        except Exception as e:
            logger.error(f"Error toggling {field_name}: {e}")
            return {'success': False, 'error': str(e)}

    async def _show_options_strategy_menu(self, query):
        """Show options strategy selection menu"""
        config = await self._get_core_config()
        current = config['options_strategy']

        message = (
            "<b>Select Options Strategy</b>\n\n"
            f"Current: {current}\n\n"
            "<i>Tap to select:</i>"
        )

        strategies = [
            ('NONE', 'Disabled'),
            ('AUTO', 'Auto (VIX)'),
            ('STRANGLE', 'Strangle'),
            ('BROKEN_IRON_CONDOR', 'Iron Condor'),
        ]

        keyboard = []
        for value, label in strategies:
            mark = " ✓" if value == current else ""
            keyboard.append([
                InlineKeyboardButton(f"{label}{mark}", callback_data=f"core_set_options_{value}")
            ])

        keyboard.append([InlineKeyboardButton("« Back", callback_data="core_refresh")])

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _set_options_strategy(self, query, strategy: str):
        """Set options strategy"""
        result = await self._update_config_field('options_strategy', strategy)
        if result['success']:
            await self._show_core_settings(query)
        else:
            await query.edit_message_text(f"Error: {result['error']}")

    async def _show_lots_menu(self, query, trade_type: str):
        """Show lots selection menu"""
        config = await self._get_core_config()
        current = config[f'{trade_type}_lots']

        message = (
            f"<b>Select {trade_type.title()} Lots</b>\n\n"
            f"Current: {current}\n\n"
            "<i>Tap to select:</i>"
        )

        lot_options = [1, 2, 3, 5, 10]
        keyboard = []
        row = []
        for lots in lot_options:
            mark = " ✓" if lots == current else ""
            row.append(
                InlineKeyboardButton(f"{lots}{mark}", callback_data=f"core_set_lots_{trade_type}_{lots}")
            )
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("« Back", callback_data="core_refresh")])

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _set_lots(self, query, trade_type: str, lots: int):
        """Set lots for a trade type"""
        field_name = f'manual_{trade_type}_lots'  # Use new field names
        result = await self._update_config_field(field_name, lots)
        if result['success']:
            await self._show_core_settings(query)
        else:
            await query.edit_message_text(f"Error: {result['error']}")

    @sync_to_async(thread_sensitive=False)
    def _update_config_field(self, field_name: str, value) -> dict:
        """Update a config field"""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.core.models import TradingCoreConfig
            config = TradingCoreConfig.get_instance()
            setattr(config, field_name, value)
            config.save()
            return {'success': True}
        except Exception as e:
            logger.error(f"Error updating {field_name}: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # POSITION SIZING MODE HANDLERS
    # =========================================================================

    async def _show_sizing_mode_menu(self, query):
        """Show position sizing mode selection menu"""
        config = await self._get_core_config()
        current = config['position_sizing_mode']

        message = (
            "<b>📏 Select Position Sizing Mode</b>\n\n"
            f"Current: {config['sizing_display']}\n\n"
            "<b>Options:</b>\n"
            "🧪 <b>Test</b> - 1 lot each (safe testing)\n"
            "✋ <b>Manual</b> - Fixed lots you specify\n"
            "📊 <b>Auto</b> - Based on broker margin\n"
            "📝 <b>Simulated</b> - Paper trade (no orders)\n\n"
            "<i>Tap to select:</i>"
        )

        modes = [
            ('TEST', '🧪 Test (1 Lot)'),
            ('MANUAL', '✋ Manual'),
            ('AUTO', '📊 Auto (Margin)'),
            ('SIMULATED', '📝 Simulated'),
        ]

        keyboard = []
        for value, label in modes:
            mark = " ✓" if value == current else ""
            keyboard.append([
                InlineKeyboardButton(f"{label}{mark}", callback_data=f"core_set_sizing_{value}")
            ])

        keyboard.append([InlineKeyboardButton("« Back", callback_data="core_refresh")])

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _set_sizing_mode(self, query, mode: str):
        """Set position sizing mode"""
        result = await self._update_config_field('position_sizing_mode', mode)
        if result['success']:
            await self._show_core_settings(query)
        else:
            await query.edit_message_text(f"Error: {result['error']}")

    # =========================================================================
    # NOTIFICATION LEVEL HANDLERS
    # =========================================================================

    async def _show_notification_level_menu(self, query):
        """Show notification level selection menu"""
        config = await self._get_core_config()
        current = config['notification_level']

        message = (
            "<b>📱 Select Notification Level</b>\n\n"
            f"Current: {config['notification_display']}\n\n"
            "<b>Options:</b>\n"
            "🔒 <b>Full Control</b> - Confirm everything\n"
            "👁️ <b>Supervised</b> - Confirm entries/exits\n"
            "🤖 <b>Autonomous</b> - Auto-execute all\n\n"
            "<i>⚠️ Autonomous will execute trades without confirmation!</i>\n\n"
            "<i>Tap to select:</i>"
        )

        levels = [
            ('FULL_CONTROL', '🔒 Full Control'),
            ('SUPERVISED', '👁️ Supervised'),
            ('AUTONOMOUS', '🤖 Autonomous'),
        ]

        keyboard = []
        for value, label in levels:
            mark = " ✓" if value == current else ""
            keyboard.append([
                InlineKeyboardButton(f"{label}{mark}", callback_data=f"core_set_notification_{value}")
            ])

        keyboard.append([InlineKeyboardButton("« Back", callback_data="core_refresh")])

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _set_notification_level(self, query, level: str):
        """Set notification level with confirmation for autonomous"""
        if level == 'AUTONOMOUS':
            # Show warning first
            message = (
                "<b>⚠️ Enable Autonomous Mode?</b>\n\n"
                "In Autonomous mode, the system will:\n"
                "• Execute trades without confirmation\n"
                "• Auto-close on stop-loss/target\n"
                "• Only send notifications\n\n"
                "<b>Are you sure?</b>"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Yes, Enable", callback_data="core_confirm_autonomous")],
                [InlineKeyboardButton("❌ Cancel", callback_data="core_notification_menu")],
            ]
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            result = await self._update_config_field('notification_level', level)
            if result['success']:
                await self._show_core_settings(query)
            else:
                await query.edit_message_text(f"Error: {result['error']}")

    # =========================================================================
    # ICICI BREEZE POSITION HANDLERS
    # =========================================================================

    async def _show_icici_positions(self, query):
        """Show ICICI Breeze positions"""
        await query.edit_message_text("Fetching ICICI Breeze positions...")

        positions = await self._fetch_icici_positions()

        # Check for error response
        if positions and len(positions) == 1 and 'error' in positions[0]:
            error_msg = positions[0]['error']
            keyboard = [
                [InlineKeyboardButton("Retry", callback_data="refresh_icici")],
                [InlineKeyboardButton("Back", callback_data="back_to_brokers")],
            ]
            await query.edit_message_text(
                f"<b>ICICI Breeze Error</b>\n\n{html.escape(error_msg[:500])}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        if not positions:
            keyboard = [
                [InlineKeyboardButton("Refresh", callback_data="refresh_icici")],
                [InlineKeyboardButton("Back", callback_data="back_to_brokers")],
            ]
            await query.edit_message_text(
                "<b>ICICI Breeze Positions</b>\n\nNo open positions found.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # Store positions in context for later use
        context_key = f"icici_positions_{query.message.chat_id}"
        await self._store_positions(context_key, positions)

        # Build message and keyboard
        message = f"<b>ICICI Breeze Positions ({len(positions)})</b>\n\n"
        keyboard = []

        total_pnl = 0
        for i, pos in enumerate(positions):
            pnl = float(pos.get('unrealized_pnl', 0))
            total_pnl += pnl
            pnl_icon = "+" if pnl >= 0 else ""
            direction = "LONG" if pos.get('net_quantity', 0) > 0 else "SHORT"

            symbol = html.escape(str(pos.get('symbol', 'N/A')))
            message += (
                f"<b>{i+1}. {symbol}</b>\n"
                f"   {direction} | Qty: {abs(pos.get('net_quantity', 0))}\n"
                f"   Avg: {pos.get('average_price', 0):,.2f} | LTP: {pos.get('ltp', 0):,.2f}\n"
                f"   P&L: {pnl_icon}{pnl:,.2f}\n\n"
            )

            # Add button for each position
            keyboard.append([
                InlineKeyboardButton(
                    f"{symbol[:20]} ({pnl_icon}{pnl:,.0f})",
                    callback_data=f"icici_pos_{i}"
                )
            ])

        pnl_icon = "+" if total_pnl >= 0 else ""
        message += f"<b>Total P&L: {pnl_icon}{total_pnl:,.2f}</b>"

        keyboard.append([InlineKeyboardButton("Refresh", callback_data="refresh_icici")])
        keyboard.append([InlineKeyboardButton("Back", callback_data="back_to_brokers")])

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_icici_position_actions(self, query, pos_index):
        """Show actions for a specific ICICI position"""
        context_key = f"icici_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = html.escape(str(pos.get('symbol', 'N/A')))
        pnl = float(pos.get('unrealized_pnl', 0))
        direction = "LONG" if pos.get('net_quantity', 0) > 0 else "SHORT"
        net_qty = abs(pos.get('net_quantity', 0))
        ls = int(pos.get('lot_size', 1) or 1)
        lots = net_qty // ls if ls > 1 else net_qty

        message = (
            f"<b>Position: {symbol}</b>\n\n"
            f"Direction: {direction}\n"
            f"Lots: {lots}\n"
            f"Avg Price: {pos.get('average_price', 0):,.2f}\n"
            f"LTP: {pos.get('ltp', 0):,.2f}\n"
            f"P&L: {'+' if pnl >= 0 else ''}{pnl:,.2f}\n\n"
            f"<b>Select Action:</b>"
        )

        keyboard = [
            [
                InlineKeyboardButton("Close Position", callback_data=f"icici_close_{pos_index}"),
                InlineKeyboardButton("Average", callback_data=f"icici_avg_{pos_index}"),
            ],
            [InlineKeyboardButton("Back to Positions", callback_data="broker_icici")],
        ]

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _confirm_icici_close(self, query, pos_index):
        """Show percentage options for closing ICICI position"""
        context_key = f"icici_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = html.escape(str(pos.get('symbol', 'N/A')))
        quantity = abs(pos.get('net_quantity', 0))

        # Calculate lot size from symbol
        lot_size = self._get_lot_size(symbol)
        total_lots = quantity // lot_size if lot_size > 0 else quantity

        message = (
            f"<b>Close Position: {symbol}</b>\n\n"
            f"Total: {total_lots} lots ({quantity:,} shares)\n"
            f"LTP: ₹{pos.get('ltp', 0):,.2f}\n\n"
            f"<b>Select % to close:</b>\n"
            f"(Orders will be placed in batches of 10 lots)"
        )

        # Calculate lots for each percentage
        lots_25 = max(1, int(total_lots * 0.25))
        lots_50 = max(1, int(total_lots * 0.50))
        lots_100 = total_lots

        keyboard = [
            [
                InlineKeyboardButton(f"25% ({lots_25} lots)", callback_data=f"icici_close_pct_{pos_index}_25"),
                InlineKeyboardButton(f"50% ({lots_50} lots)", callback_data=f"icici_close_pct_{pos_index}_50"),
            ],
            [
                InlineKeyboardButton(f"100% ({lots_100} lots)", callback_data=f"icici_close_pct_{pos_index}_100"),
            ],
            [InlineKeyboardButton("Cancel", callback_data=f"icici_pos_{pos_index}")],
        ]

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _confirm_icici_close_percentage(self, query, pos_index, percentage):
        """Confirm closing ICICI position with specific percentage"""
        context_key = f"icici_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = html.escape(str(pos.get('symbol', 'N/A')))
        quantity = abs(pos.get('net_quantity', 0))

        lot_size = self._get_lot_size(symbol)
        total_lots = quantity // lot_size if lot_size > 0 else quantity
        lots_to_close = max(1, int(total_lots * percentage / 100))
        shares_to_close = lots_to_close * lot_size

        # Calculate batches
        batch_size = 10
        num_batches = (lots_to_close + batch_size - 1) // batch_size

        message = (
            f"<b>Confirm Close Position</b>\n\n"
            f"Symbol: {symbol}\n"
            f"Closing: {lots_to_close} lots ({shares_to_close:,} shares)\n"
            f"LTP: ₹{pos.get('ltp', 0):,.2f}\n\n"
            f"<b>Execution Plan:</b>\n"
            f"• {num_batches} batch(es) of up to 10 lots each\n"
            f"• 20 second delay between batches\n\n"
            f"Proceed with closing?"
        )

        keyboard = [
            [
                InlineKeyboardButton("Yes, Close", callback_data=f"icici_exec_close_{pos_index}_{percentage}"),
                InlineKeyboardButton("Cancel", callback_data=f"icici_close_{pos_index}"),
            ],
        ]

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_icici_average_options(self, query, pos_index):
        """Show averaging options for ICICI position"""
        context_key = f"icici_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = html.escape(str(pos.get('symbol', 'N/A')))
        direction = "LONG" if pos.get('net_quantity', 0) > 0 else "SHORT"

        message = (
            f"<b>Average Position</b>\n\n"
            f"Symbol: {symbol}\n"
            f"Direction: {direction}\n"
            f"Current Qty: {abs(pos.get('net_quantity', 0))}\n"
            f"LTP: {pos.get('ltp', 0):,.2f}\n\n"
            f"<b>Select lots to add:</b>"
        )

        keyboard = [
            [
                InlineKeyboardButton("1 Lot", callback_data=f"icici_avg_lots_{pos_index}_1"),
                InlineKeyboardButton("2 Lots", callback_data=f"icici_avg_lots_{pos_index}_2"),
                InlineKeyboardButton("5 Lots", callback_data=f"icici_avg_lots_{pos_index}_5"),
            ],
            [
                InlineKeyboardButton("10 Lots", callback_data=f"icici_avg_lots_{pos_index}_10"),
                InlineKeyboardButton("20 Lots", callback_data=f"icici_avg_lots_{pos_index}_20"),
            ],
            [InlineKeyboardButton("Cancel", callback_data=f"icici_pos_{pos_index}")],
        ]

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _execute_icici_close(self, query, pos_index):
        """Execute close position for ICICI"""
        context_key = f"icici_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = pos.get('symbol', 'N/A')
        quantity = abs(pos.get('net_quantity', 0))
        is_long = pos.get('net_quantity', 0) > 0

        await query.edit_message_text(f"Closing position: {symbol}...")

        try:
            result = await self._close_icici_position(symbol, quantity, is_long)

            if result.get('success'):
                message = (
                    f"<b>Position Closed Successfully</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Order ID: {result.get('order_id', 'N/A')}"
                )
            else:
                message = (
                    f"<b>Close Failed</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            keyboard = [[InlineKeyboardButton("Back to Positions", callback_data="broker_icici")]]
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

        except Exception as e:
            logger.error(f"Error closing ICICI position: {e}")
            keyboard = [[InlineKeyboardButton("Back", callback_data="broker_icici")]]
            await query.edit_message_text(
                f"Error: {str(e)[:200]}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def _execute_icici_average(self, query, pos_index, lots):
        """Execute averaging for ICICI position"""
        context_key = f"icici_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = pos.get('symbol', 'N/A')
        is_long = pos.get('net_quantity', 0) > 0

        await query.edit_message_text(f"Adding {lots} lots to {symbol}...")

        try:
            result = await self._average_icici_position(symbol, lots, is_long)

            if result.get('success'):
                message = (
                    f"<b>Position Averaged Successfully</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Lots Added: {lots}\n"
                    f"Order ID: {result.get('order_id', 'N/A')}"
                )
            else:
                message = (
                    f"<b>Averaging Failed</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            keyboard = [[InlineKeyboardButton("Back to Positions", callback_data="broker_icici")]]
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

        except Exception as e:
            logger.error(f"Error averaging ICICI position: {e}")
            keyboard = [[InlineKeyboardButton("Back", callback_data="broker_icici")]]
            await query.edit_message_text(
                f"Error: {str(e)[:200]}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    # =========================================================================
    # KOTAK NEO POSITION HANDLERS
    # =========================================================================

    async def _show_kotak_positions(self, query):
        """Show Kotak Neo positions"""
        await query.edit_message_text("Fetching Kotak Neo positions...")

        result = await self._fetch_kotak_positions()

        # Check for error response (now returns dict with 'error' key)
        if isinstance(result, dict) and 'error' in result:
            error_msg = result['error']
            keyboard = [
                [InlineKeyboardButton("Retry", callback_data="refresh_kotak")],
                [InlineKeyboardButton("Back", callback_data="back_to_brokers")],
            ]
            await query.edit_message_text(
                f"<b>Kotak Neo Error</b>\n\n{html.escape(str(error_msg)[:500])}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        positions = result.get('positions', [])

        if not positions:
            keyboard = [
                [InlineKeyboardButton("Refresh", callback_data="refresh_kotak")],
                [InlineKeyboardButton("Back", callback_data="back_to_brokers")],
            ]
            await query.edit_message_text(
                "<b>Kotak Neo Positions</b>\n\nNo open positions found.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        context_key = f"kotak_positions_{query.message.chat_id}"
        await self._store_positions(context_key, positions)

        message = f"<b>Kotak Neo Positions ({len(positions)})</b>\n\n"
        keyboard = []

        for i, pos in enumerate(positions):
            pnl = float(pos.get('unrealized_pnl', 0))
            pnl_icon = "+" if pnl >= 0 else ""
            direction = "LONG" if pos.get('net_quantity', 0) > 0 else "SHORT"

            symbol = html.escape(str(pos.get('symbol', 'N/A')))
            message += (
                f"<b>{i+1}. {symbol}</b>\n"
                f"   {direction} | Qty: {abs(pos.get('net_quantity', 0))}\n"
                f"   Avg: {pos.get('average_price', 0):,.2f} | LTP: {pos.get('ltp', 0) or 0:,.2f}\n"
                f"   P&L: {pnl_icon}{pnl:,.2f}\n\n"
            )

            keyboard.append([
                InlineKeyboardButton(
                    f"{symbol[:20]} ({pnl_icon}{pnl:,.0f})",
                    callback_data=f"kotak_pos_{i}"
                )
            ])

        # Unrealized P&L (sum of per-position unrealized_pnl)
        unrealized_pnl = sum(float(p.get('unrealized_pnl', 0)) for p in positions)
        pnl_icon = "+" if unrealized_pnl >= 0 else ""
        message += f"<b>Unrealized P&L: {pnl_icon}{unrealized_pnl:,.0f}</b>"

        keyboard.append([InlineKeyboardButton("Refresh", callback_data="refresh_kotak")])
        keyboard.append([InlineKeyboardButton("Back", callback_data="back_to_brokers")])

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_kotak_position_actions(self, query, pos_index):
        """Show actions for a specific Kotak position"""
        context_key = f"kotak_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = html.escape(str(pos.get('symbol', 'N/A')))
        pnl = float(pos.get('unrealized_pnl', 0))
        direction = "LONG" if pos.get('net_quantity', 0) > 0 else "SHORT"
        net_qty = abs(pos.get('net_quantity', 0))
        ls = int(pos.get('lot_size', 1) or 1)
        lots = net_qty // ls if ls > 1 else net_qty

        message = (
            f"<b>Position: {symbol}</b>\n\n"
            f"Direction: {direction}\n"
            f"Lots: {lots}\n"
            f"Avg Price: {pos.get('average_price', 0):,.2f}\n"
            f"LTP: {pos.get('ltp', 0):,.2f}\n"
            f"P&L: {'+' if pnl >= 0 else ''}{pnl:,.2f}\n\n"
            f"<b>Select Action:</b>"
        )

        keyboard = [
            [
                InlineKeyboardButton("Close Position", callback_data=f"kotak_close_{pos_index}"),
                InlineKeyboardButton("Average", callback_data=f"kotak_avg_{pos_index}"),
            ],
            [InlineKeyboardButton("Back to Positions", callback_data="broker_kotak")],
        ]

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _confirm_kotak_close(self, query, pos_index):
        """Show percentage options for closing Kotak position"""
        context_key = f"kotak_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = html.escape(str(pos.get('symbol', 'N/A')))
        quantity = abs(pos.get('net_quantity', 0))

        # Calculate lot size from symbol
        lot_size = self._get_lot_size(symbol)
        total_lots = quantity // lot_size if lot_size > 0 else quantity

        message = (
            f"<b>Close Position: {symbol}</b>\n\n"
            f"Total: {total_lots} lots ({quantity:,} shares)\n"
            f"LTP: ₹{pos.get('ltp', 0):,.2f}\n\n"
            f"<b>Select % to close:</b>\n"
            f"(Orders will be placed in batches of 10 lots)"
        )

        # Calculate lots for each percentage
        lots_25 = max(1, int(total_lots * 0.25))
        lots_50 = max(1, int(total_lots * 0.50))
        lots_100 = total_lots

        keyboard = [
            [
                InlineKeyboardButton(f"25% ({lots_25} lots)", callback_data=f"kotak_close_pct_{pos_index}_25"),
                InlineKeyboardButton(f"50% ({lots_50} lots)", callback_data=f"kotak_close_pct_{pos_index}_50"),
            ],
            [
                InlineKeyboardButton(f"100% ({lots_100} lots)", callback_data=f"kotak_close_pct_{pos_index}_100"),
            ],
            [InlineKeyboardButton("Cancel", callback_data=f"kotak_pos_{pos_index}")],
        ]

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _confirm_kotak_close_percentage(self, query, pos_index, percentage):
        """Confirm closing Kotak position with specific percentage"""
        context_key = f"kotak_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = html.escape(str(pos.get('symbol', 'N/A')))
        quantity = abs(pos.get('net_quantity', 0))

        lot_size = self._get_lot_size(symbol)
        total_lots = quantity // lot_size if lot_size > 0 else quantity
        lots_to_close = max(1, int(total_lots * percentage / 100))
        shares_to_close = lots_to_close * lot_size

        # Calculate batches
        batch_size = 10
        num_batches = (lots_to_close + batch_size - 1) // batch_size

        message = (
            f"<b>Confirm Close Position</b>\n\n"
            f"Symbol: {symbol}\n"
            f"Closing: {lots_to_close} lots ({shares_to_close:,} shares)\n"
            f"LTP: ₹{pos.get('ltp', 0):,.2f}\n\n"
            f"<b>Execution Plan:</b>\n"
            f"• {num_batches} batch(es) of up to 10 lots each\n"
            f"• 10 second delay between batches\n\n"
            f"Proceed with closing?"
        )

        keyboard = [
            [
                InlineKeyboardButton("Yes, Close", callback_data=f"kotak_exec_close_{pos_index}_{percentage}"),
                InlineKeyboardButton("Cancel", callback_data=f"kotak_close_{pos_index}"),
            ],
        ]

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_kotak_average_options(self, query, pos_index):
        """Show averaging options for Kotak position"""
        context_key = f"kotak_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = html.escape(str(pos.get('symbol', 'N/A')))
        direction = "LONG" if pos.get('net_quantity', 0) > 0 else "SHORT"

        message = (
            f"<b>Average Position</b>\n\n"
            f"Symbol: {symbol}\n"
            f"Direction: {direction}\n"
            f"Current Qty: {abs(pos.get('net_quantity', 0))}\n"
            f"LTP: {pos.get('ltp', 0):,.2f}\n\n"
            f"<b>Select lots to add:</b>"
        )

        keyboard = [
            [
                InlineKeyboardButton("1 Lot", callback_data=f"kotak_avg_lots_{pos_index}_1"),
                InlineKeyboardButton("2 Lots", callback_data=f"kotak_avg_lots_{pos_index}_2"),
                InlineKeyboardButton("5 Lots", callback_data=f"kotak_avg_lots_{pos_index}_5"),
            ],
            [
                InlineKeyboardButton("10 Lots", callback_data=f"kotak_avg_lots_{pos_index}_10"),
                InlineKeyboardButton("20 Lots", callback_data=f"kotak_avg_lots_{pos_index}_20"),
            ],
            [InlineKeyboardButton("Cancel", callback_data=f"kotak_pos_{pos_index}")],
        ]

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _execute_kotak_close(self, query, pos_index):
        """Execute close position for Kotak"""
        context_key = f"kotak_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = pos.get('symbol', 'N/A')
        quantity = abs(pos.get('net_quantity', 0))
        is_long = pos.get('net_quantity', 0) > 0

        await query.edit_message_text(f"Closing position: {symbol}...")

        try:
            result = await self._close_kotak_position(symbol, quantity, is_long)

            if result.get('success'):
                message = (
                    f"<b>Position Closed Successfully</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Order ID: {result.get('order_id', 'N/A')}"
                )
            else:
                message = (
                    f"<b>Close Failed</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            keyboard = [[InlineKeyboardButton("Back to Positions", callback_data="broker_kotak")]]
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

        except Exception as e:
            logger.error(f"Error closing Kotak position: {e}")
            keyboard = [[InlineKeyboardButton("Back", callback_data="broker_kotak")]]
            await query.edit_message_text(
                f"Error: {str(e)[:200]}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def _execute_kotak_average(self, query, pos_index, lots):
        """Execute averaging for Kotak position"""
        context_key = f"kotak_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = pos.get('symbol', 'N/A')
        is_long = pos.get('net_quantity', 0) > 0

        await query.edit_message_text(f"Adding {lots} lots to {symbol}...")

        try:
            result = await self._average_kotak_position(symbol, lots, is_long)

            if result.get('success'):
                message = (
                    f"<b>Position Averaged Successfully</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Lots Added: {lots}\n"
                    f"Order ID: {result.get('order_id', 'N/A')}"
                )
            else:
                message = (
                    f"<b>Averaging Failed</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )

            keyboard = [[InlineKeyboardButton("Back to Positions", callback_data="broker_kotak")]]
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

        except Exception as e:
            logger.error(f"Error averaging Kotak position: {e}")
            keyboard = [[InlineKeyboardButton("Back", callback_data="broker_kotak")]]
            await query.edit_message_text(
                f"Error: {str(e)[:200]}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    # =========================================================================
    # ALL BROKERS VIEW
    # =========================================================================

    async def _show_all_positions(self, query):
        """Show positions from all brokers"""
        await query.edit_message_text("Fetching positions from all brokers...")

        icici_positions = await self._fetch_icici_positions()
        kotak_result = await self._fetch_kotak_positions()

        # Extract Kotak positions from dict result
        kotak_positions = []
        if isinstance(kotak_result, dict) and 'error' not in kotak_result:
            kotak_positions = kotak_result.get('positions', [])

        if not icici_positions and not kotak_positions:
            keyboard = [
                [InlineKeyboardButton("Refresh", callback_data="refresh_all")],
                [InlineKeyboardButton("Back", callback_data="back_to_brokers")],
            ]
            await query.edit_message_text(
                "<b>All Positions</b>\n\nNo open positions found in any broker.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        message = "<b>All Broker Positions</b>\n\n"
        total_pnl = 0

        if icici_positions:
            message += f"<b>ICICI Breeze ({len(icici_positions)})</b>\n"
            for pos in icici_positions:
                pnl = float(pos.get('unrealized_pnl', 0))
                total_pnl += pnl
                pnl_icon = "+" if pnl >= 0 else ""
                symbol = html.escape(str(pos.get('symbol', 'N/A')))
                message += f"  {symbol}: {pnl_icon}{pnl:,.0f}\n"
            message += "\n"

        kotak_cumulative = 0
        if kotak_positions:
            message += f"<b>Kotak Neo ({len(kotak_positions)})</b>\n"
            for pos in kotak_positions:
                pnl = float(pos.get('unrealized_pnl', 0))
                kotak_cumulative += pnl
                pnl_icon = "+" if pnl >= 0 else ""
                symbol = html.escape(str(pos.get('symbol', 'N/A')))
                message += f"  {symbol}: {pnl_icon}{pnl:,.0f}\n"
            message += "\n"

        total_pnl += kotak_cumulative
        cum_icon = "+" if total_pnl >= 0 else ""
        message += f"<b>Combined P&L: {cum_icon}{total_pnl:,.0f}</b>"

        keyboard = [
            [InlineKeyboardButton("ICICI Details", callback_data="broker_icici")],
            [InlineKeyboardButton("Kotak Details", callback_data="broker_kotak")],
            [InlineKeyboardButton("Refresh", callback_data="refresh_all")],
            [InlineKeyboardButton("Back", callback_data="back_to_brokers")],
        ]

        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # DATA FETCHING METHODS
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _fetch_icici_positions(self) -> List[Dict]:
        """Fetch positions from ICICI Breeze and sync to DB."""
        import traceback
        from django.db import close_old_connections

        try:
            # Close old connections for thread safety
            close_old_connections()

            from apps.brokers.integrations.breeze import fetch_and_save_breeze_data
            from apps.accounts.models import BrokerAccount

            # Check if account is active
            account = BrokerAccount.objects.filter(broker='ICICI', is_active=True).first()
            if not account:
                logger.info("ICICI account not active")
                return [{'error': 'ICICI account not active or not found'}]

            logger.info("Fetching ICICI Breeze positions...")
            _, positions = fetch_and_save_breeze_data()
            logger.info(f"Fetched {len(positions)} raw positions from Breeze")

            # Sync to DB: create missing, update partial, close stale
            try:
                from apps.positions.services.position_sync import sync_positions_from_broker_objects
                sync_result = sync_positions_from_broker_objects(account, positions)
                logger.info(f"ICICI DB sync: created={sync_result['created']} updated={sync_result['updated']} closed={sync_result['closed']}")
            except Exception as sync_err:
                logger.error(f"ICICI DB sync failed (display continues): {sync_err}")

            # Convert to dict format and filter non-zero positions for display
            result = []
            for pos in positions:
                logger.info(f"Position: {pos.symbol}, net_qty={pos.net_quantity}")
                if pos.net_quantity != 0:
                    result.append({
                        'symbol': pos.symbol,
                        'exchange_segment': pos.exchange_segment,
                        'product': pos.product,
                        'net_quantity': pos.net_quantity,
                        'average_price': float(pos.average_price),
                        'ltp': float(pos.ltp),
                        'unrealized_pnl': float(pos.unrealized_pnl),
                        'realized_pnl': float(pos.realized_pnl),
                    })

            logger.info(f"Returning {len(result)} non-zero positions")
            return result

        except Exception as e:
            error_msg = f"Error fetching ICICI positions: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return [{'error': str(e)}]

    @sync_to_async(thread_sensitive=False)
    def _fetch_kotak_positions(self) -> dict:
        """Fetch positions from Kotak Neo and sync to DB.

        Returns:
            dict with 'positions' list, or
            dict with 'error' key on failure.
        """
        import traceback
        from django.db import close_old_connections

        try:
            close_old_connections()

            from apps.brokers.integrations.kotak_neo import get_neo_open_positions
            from apps.accounts.models import BrokerAccount

            account = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()
            if not account:
                logger.info("Kotak account not active")
                return {'error': 'Kotak account not active or not found'}

            logger.info("Fetching Kotak Neo positions...")
            result = get_neo_open_positions()

            if 'error' in result:
                return result

            # Sync to DB: create missing, update partial, close stale
            try:
                from apps.positions.services.position_sync import sync_positions_from_broker_objects
                sync_result = sync_positions_from_broker_objects(account, result.get('positions', []))
                logger.info(f"Kotak DB sync: created={sync_result['created']} updated={sync_result['updated']} closed={sync_result['closed']}")
            except Exception as sync_err:
                logger.error(f"Kotak DB sync failed (display continues): {sync_err}")

            logger.info(f"Returning {len(result['positions'])} Kotak Neo positions")
            return result

        except Exception as e:
            error_msg = f"Error fetching Kotak positions: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return {'error': str(e)}

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_lot_size(self, symbol: str) -> int:
        """Get lot size for a symbol"""
        # Order matters - check more specific patterns first
        lot_sizes = [
            ('BANKNIFTY', 30),
            ('FINNIFTY', 40),
            ('NIFTY', 75),
            ('HDFCBANK', 550),
            ('HDFBAN', 550),
            ('ICICIBANK', 700),
            ('AXISBANK', 625),
            ('RELIANCE', 250),
            ('TCS', 150),
            ('INFY', 300),
            ('SBIN', 750),
        ]

        symbol_upper = symbol.upper()
        for key, lot_size in lot_sizes:
            if key in symbol_upper:
                return lot_size
        return 1  # Default

    # =========================================================================
    # BATCHED ORDER EXECUTION
    # =========================================================================

    async def _execute_icici_close_batched(self, query, pos_index, percentage):
        """Execute batched close for ICICI position"""
        import asyncio

        context_key = f"icici_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = pos.get('symbol', 'N/A')
        quantity = abs(pos.get('net_quantity', 0))
        is_long = pos.get('net_quantity', 0) > 0

        lot_size = self._get_lot_size(symbol)
        total_lots = quantity // lot_size if lot_size > 0 else quantity
        lots_to_close = max(1, int(total_lots * percentage / 100))

        # Setup batching
        BATCH_SIZE = 10  # lots per batch
        DELAY_SECONDS = 20  # delay between batches

        batches = []
        remaining = lots_to_close
        while remaining > 0:
            batch_lots = min(BATCH_SIZE, remaining)
            batches.append(batch_lots)
            remaining -= batch_lots

        total_batches = len(batches)
        successful = 0
        failed = 0

        # Show initial progress
        await query.edit_message_text(
            f"<b>Closing {symbol}</b>\n\n"
            f"📊 Progress: 0/{total_batches} batches\n"
            f"🎯 Target: {lots_to_close} lots ({percentage}%)\n\n"
            f"Starting...",
            parse_mode='HTML'
        )

        for batch_num, batch_lots in enumerate(batches, 1):
            batch_shares = batch_lots * lot_size

            # Update progress
            await query.edit_message_text(
                f"<b>Closing {symbol}</b>\n\n"
                f"📊 Progress: {batch_num-1}/{total_batches} batches\n"
                f"✅ Successful: {successful}\n"
                f"❌ Failed: {failed}\n\n"
                f"⏳ Processing batch {batch_num}: {batch_lots} lots...",
                parse_mode='HTML'
            )

            # Execute batch
            result = await self._close_icici_position_batch(symbol, batch_shares, is_long)

            if result.get('success'):
                successful += 1
            else:
                failed += 1
                # On failure, show error and stop
                await query.edit_message_text(
                    f"<b>Close Stopped</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Batch {batch_num}/{total_batches} failed\n"
                    f"Error: {result.get('error', 'Unknown')}\n\n"
                    f"✅ Completed: {successful} batches\n"
                    f"❌ Failed: {failed} batches",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Back to Positions", callback_data="broker_icici")]
                    ])
                )
                return

            # Wait before next batch
            if batch_num < total_batches:
                await query.edit_message_text(
                    f"<b>Closing {symbol}</b>\n\n"
                    f"📊 Progress: {batch_num}/{total_batches} batches\n"
                    f"✅ Successful: {successful}\n\n"
                    f"⏸️ Waiting {DELAY_SECONDS}s before next batch...",
                    parse_mode='HTML'
                )
                await asyncio.sleep(DELAY_SECONDS)

        # All done
        await query.edit_message_text(
            f"<b>Position Closed</b>\n\n"
            f"Symbol: {symbol}\n"
            f"Closed: {lots_to_close} lots ({percentage}%)\n\n"
            f"✅ All {total_batches} batches successful",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Back to Positions", callback_data="broker_icici")]
            ])
        )

    async def _execute_kotak_close_batched(self, query, pos_index, percentage):
        """Execute batched close for Kotak position"""
        import asyncio

        context_key = f"kotak_positions_{query.message.chat_id}"
        positions = await self._get_positions(context_key)

        if not positions or pos_index >= len(positions):
            await query.edit_message_text("Position not found. Please refresh.")
            return

        pos = positions[pos_index]
        symbol = pos.get('symbol', 'N/A')
        quantity = abs(pos.get('net_quantity', 0))
        is_long = pos.get('net_quantity', 0) > 0

        lot_size = self._get_lot_size(symbol)
        total_lots = quantity // lot_size if lot_size > 0 else quantity
        lots_to_close = max(1, int(total_lots * percentage / 100))

        # Setup batching
        BATCH_SIZE = 10  # lots per batch
        DELAY_SECONDS = 10  # delay between batches (shorter for Kotak)

        batches = []
        remaining = lots_to_close
        while remaining > 0:
            batch_lots = min(BATCH_SIZE, remaining)
            batches.append(batch_lots)
            remaining -= batch_lots

        total_batches = len(batches)
        successful = 0
        failed = 0

        # Show initial progress
        await query.edit_message_text(
            f"<b>Closing {symbol}</b>\n\n"
            f"📊 Progress: 0/{total_batches} batches\n"
            f"🎯 Target: {lots_to_close} lots ({percentage}%)\n\n"
            f"Starting...",
            parse_mode='HTML'
        )

        for batch_num, batch_lots in enumerate(batches, 1):
            batch_shares = batch_lots * lot_size

            # Update progress
            await query.edit_message_text(
                f"<b>Closing {symbol}</b>\n\n"
                f"📊 Progress: {batch_num-1}/{total_batches} batches\n"
                f"✅ Successful: {successful}\n"
                f"❌ Failed: {failed}\n\n"
                f"⏳ Processing batch {batch_num}: {batch_lots} lots...",
                parse_mode='HTML'
            )

            # Execute batch
            result = await self._close_kotak_position_batch(symbol, batch_shares, is_long)

            if result.get('success'):
                successful += 1
            else:
                failed += 1
                # On failure, show error and stop
                await query.edit_message_text(
                    f"<b>Close Stopped</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Batch {batch_num}/{total_batches} failed\n"
                    f"Error: {result.get('error', 'Unknown')}\n\n"
                    f"✅ Completed: {successful} batches\n"
                    f"❌ Failed: {failed} batches",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Back to Positions", callback_data="broker_kotak")]
                    ])
                )
                return

            # Wait before next batch
            if batch_num < total_batches:
                await query.edit_message_text(
                    f"<b>Closing {symbol}</b>\n\n"
                    f"📊 Progress: {batch_num}/{total_batches} batches\n"
                    f"✅ Successful: {successful}\n\n"
                    f"⏸️ Waiting {DELAY_SECONDS}s before next batch...",
                    parse_mode='HTML'
                )
                await asyncio.sleep(DELAY_SECONDS)

        # All done
        await query.edit_message_text(
            f"<b>Position Closed</b>\n\n"
            f"Symbol: {symbol}\n"
            f"Closed: {lots_to_close} lots ({percentage}%)\n\n"
            f"✅ All {total_batches} batches successful",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Back to Positions", callback_data="broker_kotak")]
            ])
        )

    @sync_to_async
    def _close_icici_position_batch(self, symbol: str, quantity: int, is_long: bool) -> Dict:
        """Close a batch of ICICI position"""
        try:
            from apps.brokers.integrations.breeze import get_breeze_client

            breeze = get_breeze_client()
            action = 'sell' if is_long else 'buy'

            # Determine if futures based on symbol
            product = 'futures' if 'FUT' in symbol.upper() else 'options'

            response = breeze.place_order(
                stock_code=symbol,
                exchange_code='NFO',
                product=product,
                action=action,
                order_type='market',
                quantity=str(quantity),
                price='0',
                validity='day',
                stoploss='0',
                disclosed_quantity='0',
            )

            if response and response.get('Status') == 200:
                return {
                    'success': True,
                    'order_id': response.get('Success', {}).get('order_id', 'N/A')
                }
            else:
                return {
                    'success': False,
                    'error': response.get('Error', 'Unknown error') if response else 'No response'
                }

        except Exception as e:
            logger.error(f"Error closing ICICI batch: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async
    def _close_kotak_position_batch(self, symbol: str, quantity: int, is_long: bool) -> Dict:
        """Close a batch of Kotak position"""
        try:
            from apps.brokers.integrations.kotak_neo import place_option_order

            transaction_type = 'S' if is_long else 'B'

            result = place_option_order(
                trading_symbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                product='NRML',
                order_type='MKT'
            )

            return result

        except Exception as e:
            logger.error(f"Error closing Kotak batch: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # ORDER EXECUTION METHODS (Legacy - single order)
    # =========================================================================

    @sync_to_async
    def _close_icici_position(self, symbol: str, quantity: int, is_long: bool) -> Dict:
        """Close an ICICI position"""
        try:
            from apps.brokers.integrations.breeze import get_breeze_client

            breeze = get_breeze_client()
            action = 'sell' if is_long else 'buy'

            # Parse symbol to determine if it's options or futures
            # For now, assume options with NRML product
            response = breeze.place_order(
                stock_code=symbol,
                exchange_code='NFO',
                product='options',
                action=action,
                order_type='market',
                quantity=str(quantity),
                price='0',
                validity='day',
                stoploss='0',
                disclosed_quantity='0',
            )

            if response and response.get('Status') == 200:
                return {
                    'success': True,
                    'order_id': response.get('Success', {}).get('order_id', 'N/A')
                }
            else:
                return {
                    'success': False,
                    'error': response.get('Error', 'Unknown error') if response else 'No response'
                }

        except Exception as e:
            logger.error(f"Error closing ICICI position: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async
    def _average_icici_position(self, symbol: str, lots: int, is_long: bool) -> Dict:
        """Average an ICICI position"""
        try:
            from apps.brokers.integrations.breeze import get_breeze_client

            breeze = get_breeze_client()
            action = 'buy' if is_long else 'sell'

            # Assume lot size of 25 for NIFTY (should be fetched dynamically)
            lot_size = 25
            quantity = lots * lot_size

            response = breeze.place_order(
                stock_code=symbol,
                exchange_code='NFO',
                product='options',
                action=action,
                order_type='market',
                quantity=str(quantity),
                price='0',
                validity='day',
                stoploss='0',
                disclosed_quantity='0',
            )

            if response and response.get('Status') == 200:
                return {
                    'success': True,
                    'order_id': response.get('Success', {}).get('order_id', 'N/A')
                }
            else:
                return {
                    'success': False,
                    'error': response.get('Error', 'Unknown error') if response else 'No response'
                }

        except Exception as e:
            logger.error(f"Error averaging ICICI position: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async
    def _close_kotak_position(self, symbol: str, quantity: int, is_long: bool) -> Dict:
        """Close a Kotak position"""
        try:
            from apps.brokers.integrations.kotak_neo import place_option_order

            transaction_type = 'S' if is_long else 'B'

            result = place_option_order(
                trading_symbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                product='NRML',
                order_type='MKT'
            )

            return result

        except Exception as e:
            logger.error(f"Error closing Kotak position: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async
    def _average_kotak_position(self, symbol: str, lots: int, is_long: bool) -> Dict:
        """Average a Kotak position"""
        try:
            from apps.brokers.integrations.kotak_neo import place_option_order, get_lot_size_from_neo

            transaction_type = 'B' if is_long else 'S'
            lot_size = get_lot_size_from_neo(symbol)
            quantity = lots * lot_size

            result = place_option_order(
                trading_symbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                product='NRML',
                order_type='MKT'
            )

            return result

        except Exception as e:
            logger.error(f"Error averaging Kotak position: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # POSITION STORAGE (using Django cache)
    # =========================================================================

    @sync_to_async
    def _store_positions(self, key: str, positions: List[Dict]):
        """Store positions in cache"""
        from django.core.cache import cache
        cache.set(key, positions, 300)  # 5 minute TTL

    @sync_to_async
    def _get_positions(self, key: str) -> List[Dict]:
        """Get positions from cache"""
        from django.core.cache import cache
        return cache.get(key) or []

    # =========================================================================
    # BOT RUN METHOD
    # =========================================================================

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in the bot"""
        logger.error(f"Bot error: {context.error}")

        # Check for conflict error (another bot instance running)
        if "Conflict" in str(context.error):
            logger.error(
                "CONFLICT ERROR: Another bot instance is running! "
                "This could be on another machine or process. "
                "Stop the other instance before running this one."
            )

    async def _post_init(self, application: Application) -> None:
        """Register bot commands (pinned menu) and set the menu button after startup."""
        commands = [
            BotCommand("start",     "\U0001f4ca Main Menu"),
            BotCommand("pnl",       "\U0001f4b0 P&L Summary"),
            BotCommand("positions", "\U0001f4c8 Open Positions"),
            BotCommand("orders",    "\U0001f4cb Orders"),
            BotCommand("margin",    "\U0001f4b5 Margin & Limits"),
            BotCommand("trade",     "\u26a1 Manual Trade"),
            BotCommand("history",   "\U0001f4c4 Trade History"),
            BotCommand("analytics", "\U0001f4c9 Analytics"),
            BotCommand("login",     "\U0001f511 Broker Login"),
            BotCommand("core",      "\U0001f39b Core Settings"),
        ]
        await application.bot.set_my_commands(commands)
        # Show a commands menu button next to the message input (pinned at top)
        from telegram import MenuButtonCommands
        await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        logger.info("Bot commands registered and menu button pinned.")

    def run(self):
        """Run the bot"""
        logger.info("Starting Telegram bot...")

        application = (
            Application.builder()
            .token(self.bot_token)
            .post_init(self._post_init)
            .concurrent_updates(True)  # Allow OTP messages to be processed while login is running
            .build()
        )

        # Add error handler
        application.add_error_handler(self.error_handler)

        # Add command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("menu", self.start_command))
        application.add_handler(CommandHandler("test", self.test_command))
        application.add_handler(CommandHandler("positions", self.positions_command))
        application.add_handler(CommandHandler("core", self.core_command))
        application.add_handler(CommandHandler("trade", self.trade_command))
        application.add_handler(CommandHandler("orders", self.orders_command))
        application.add_handler(CommandHandler("margin", self.margin_command))
        application.add_handler(CommandHandler("pnl", self.pnl_command))
        application.add_handler(CommandHandler("analytics", self.analytics_command))
        application.add_handler(CommandHandler("history", self.history_command))
        application.add_handler(CommandHandler("login", self.login_command))

        # Add callback query handler for buttons
        application.add_handler(CallbackQueryHandler(self.button_callback))

        # Add message handler for OTP replies (plain text, non-command)
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.otp_message_handler
        ))

        logger.info("Telegram bot started successfully")
        logger.info("Bot is polling for updates...")

        # Start polling with drop_pending_updates to avoid conflicts with stale updates
        # NOTE: This will conflict if another bot instance is already polling.
        # Make sure only ONE instance runs at a time (check office vs home machine).
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True  # Drop updates from previous/other instances
        )


def acquire_bot_lock() -> bool:
    """
    Acquire exclusive lock to ensure only one bot instance runs.

    Returns:
        bool: True if lock acquired, False if another instance is running
    """
    global _lock_file_handle

    try:
        _lock_file_handle = open(BOT_LOCK_FILE, 'w')
        fcntl.flock(_lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()

        # Register cleanup on exit
        atexit.register(release_bot_lock)

        logger.info(f"Bot lock acquired (PID: {os.getpid()})")
        return True

    except (IOError, OSError) as e:
        if _lock_file_handle:
            _lock_file_handle.close()
            _lock_file_handle = None
        logger.error(f"Failed to acquire bot lock: {e}")
        return False


def release_bot_lock():
    """Release the bot lock on shutdown"""
    global _lock_file_handle

    if _lock_file_handle:
        try:
            fcntl.flock(_lock_file_handle.fileno(), fcntl.LOCK_UN)
            _lock_file_handle.close()
            _lock_file_handle = None

            # Remove lock file
            if os.path.exists(BOT_LOCK_FILE):
                os.remove(BOT_LOCK_FILE)

            logger.info("Bot lock released")
        except Exception as e:
            logger.error(f"Error releasing bot lock: {e}")


def is_bot_running() -> bool:
    """
    Check if another bot instance is already running.

    Returns:
        bool: True if another instance is running, False otherwise
    """
    try:
        with open(BOT_LOCK_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return False  # Lock acquired and released = no other instance
    except (IOError, OSError, FileNotFoundError):
        # FileNotFoundError = no lock file = no instance running
        # IOError/OSError = lock held by another process
        if not os.path.exists(BOT_LOCK_FILE):
            return False
        return True


def start_bot():
    """
    Start the Telegram bot.

    Ensures only one instance can run at a time using file locking.
    If another instance is already running, this will exit with an error.
    """
    # Check if another instance is running
    if is_bot_running():
        logger.error("Another Telegram bot instance is already running!")
        logger.error("Stop the existing instance before starting a new one.")
        logger.error(f"Lock file: {BOT_LOCK_FILE}")
        raise RuntimeError(
            "Telegram bot is already running. "
            "Only one instance can run at a time to avoid polling conflicts."
        )

    # Acquire lock before starting
    if not acquire_bot_lock():
        raise RuntimeError(
            "Failed to acquire bot lock. Another instance may be starting."
        )

    try:
        bot = TelegramBotHandler()
        bot.run()
    finally:
        release_bot_lock()
