"""
Telegram Bot Command Handler

Interactive Telegram bot for managing trading positions across brokers.

Available Commands:
- /start - Welcome message and command list
- /test - Test bot connectivity
- /positions - View live positions from all brokers

IMPORTANT: Only ONE instance of this bot should run at a time.
The bot uses a file lock to prevent multiple instances from polling.
"""

import logging
import os
import html
import fcntl
import atexit
from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from django.conf import settings
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

# Singleton lock file path
BOT_LOCK_FILE = '/tmp/mcube_telegram_bot.lock'
_lock_file_handle = None


class TelegramBotHandler:
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
        """Handle /start command"""
        if not self.is_authorized(update):
            await update.message.reply_text("Unauthorized access")
            return

        welcome_message = (
            "<b>mCube Trading Bot</b>\n\n"
            "Commands:\n"
            "/test - Test bot connectivity\n"
            "/positions - View live positions\n"
        )
        await update.message.reply_text(welcome_message, parse_mode='HTML')

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

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()

        if not self.is_authorized(update):
            await query.edit_message_text("Unauthorized access")
            return

        data = query.data

        # Broker selection
        if data == "broker_icici":
            await self._show_icici_positions(query)
        elif data == "broker_kotak":
            await self._show_kotak_positions(query)
        elif data == "broker_all":
            await self._show_all_positions(query)

        # Back to broker menu
        elif data == "back_to_brokers":
            keyboard = [
                [InlineKeyboardButton("ICICI Breeze", callback_data="broker_icici")],
                [InlineKeyboardButton("Kotak Neo", callback_data="broker_kotak")],
                [InlineKeyboardButton("All Brokers", callback_data="broker_all")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "<b>Select Broker</b>\n\nChoose a broker to view positions:",
                parse_mode='HTML',
                reply_markup=reply_markup
            )

        # ICICI Position actions
        elif data.startswith("icici_pos_"):
            pos_index = int(data.split("_")[2])
            await self._show_icici_position_actions(query, pos_index)

        elif data.startswith("icici_close_pct_"):
            # New: icici_close_pct_{pos_index}_{percentage}
            parts = data.split("_")
            pos_index = int(parts[3])
            percentage = int(parts[4])
            await self._confirm_icici_close_percentage(query, pos_index, percentage)

        elif data.startswith("icici_exec_close_"):
            # New: icici_exec_close_{pos_index}_{percentage}
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
            # New: kotak_close_pct_{pos_index}_{percentage}
            parts = data.split("_")
            pos_index = int(parts[3])
            percentage = int(parts[4])
            await self._confirm_kotak_close_percentage(query, pos_index, percentage)

        elif data.startswith("kotak_exec_close_"):
            # New: kotak_exec_close_{pos_index}_{percentage}
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

        # Refresh actions
        elif data == "refresh_icici":
            await self._show_icici_positions(query)
        elif data == "refresh_kotak":
            await self._show_kotak_positions(query)
        elif data == "refresh_all":
            await self._show_all_positions(query)

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

        message = (
            f"<b>Position: {symbol}</b>\n\n"
            f"Direction: {direction}\n"
            f"Quantity: {abs(pos.get('net_quantity', 0))}\n"
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

        positions = await self._fetch_kotak_positions()

        # Check for error response
        if positions and len(positions) == 1 and 'error' in positions[0]:
            error_msg = positions[0]['error']
            keyboard = [
                [InlineKeyboardButton("Retry", callback_data="refresh_kotak")],
                [InlineKeyboardButton("Back", callback_data="back_to_brokers")],
            ]
            await query.edit_message_text(
                f"<b>Kotak Neo Error</b>\n\n{html.escape(error_msg[:500])}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

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

            keyboard.append([
                InlineKeyboardButton(
                    f"{symbol[:20]} ({pnl_icon}{pnl:,.0f})",
                    callback_data=f"kotak_pos_{i}"
                )
            ])

        pnl_icon = "+" if total_pnl >= 0 else ""
        message += f"<b>Total P&L: {pnl_icon}{total_pnl:,.2f}</b>"

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

        message = (
            f"<b>Position: {symbol}</b>\n\n"
            f"Direction: {direction}\n"
            f"Quantity: {abs(pos.get('net_quantity', 0))}\n"
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
        kotak_positions = await self._fetch_kotak_positions()

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

        if kotak_positions:
            message += f"<b>Kotak Neo ({len(kotak_positions)})</b>\n"
            for pos in kotak_positions:
                pnl = float(pos.get('unrealized_pnl', 0))
                total_pnl += pnl
                pnl_icon = "+" if pnl >= 0 else ""
                symbol = html.escape(str(pos.get('symbol', 'N/A')))
                message += f"  {symbol}: {pnl_icon}{pnl:,.0f}\n"
            message += "\n"

        pnl_icon = "+" if total_pnl >= 0 else ""
        message += f"<b>Combined P&L: {pnl_icon}{total_pnl:,.2f}</b>"

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
        """Fetch positions from ICICI Breeze"""
        import traceback
        from django.db import close_old_connections

        try:
            # Close old connections for thread safety
            close_old_connections()

            from apps.brokers.integrations.breeze import fetch_and_save_breeze_data
            from apps.accounts.models import BrokerAccount

            # Check if account is active
            if not BrokerAccount.objects.filter(broker='ICICI', is_active=True).exists():
                logger.info("ICICI account not active")
                return [{'error': 'ICICI account not active or not found'}]

            logger.info("Fetching ICICI Breeze positions...")
            _, positions = fetch_and_save_breeze_data()
            logger.info(f"Fetched {len(positions)} raw positions from Breeze")

            # Convert to dict format and filter non-zero positions
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
    def _fetch_kotak_positions(self) -> List[Dict]:
        """Fetch positions from Kotak Neo"""
        import traceback
        from django.db import close_old_connections

        try:
            # Close old connections for thread safety
            close_old_connections()

            from apps.brokers.integrations.kotak_neo import fetch_and_save_kotakneo_data
            from apps.accounts.models import BrokerAccount

            # Check if account is active
            if not BrokerAccount.objects.filter(broker='KOTAK', is_active=True).exists():
                logger.info("Kotak account not active")
                return [{'error': 'Kotak account not active or not found'}]

            logger.info("Fetching Kotak Neo positions...")
            _, positions = fetch_and_save_kotakneo_data()
            logger.info(f"Fetched {len(positions)} raw positions from Kotak")

            # Convert to dict format and filter non-zero positions
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
            error_msg = f"Error fetching Kotak positions: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return [{'error': str(e)}]

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

    def run(self):
        """Run the bot"""
        logger.info("Starting Telegram bot...")

        application = Application.builder().token(self.bot_token).build()

        # Add command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("test", self.test_command))
        application.add_handler(CommandHandler("positions", self.positions_command))

        # Add callback query handler for buttons
        application.add_handler(CallbackQueryHandler(self.button_callback))

        logger.info("Telegram bot started successfully")
        logger.info("Bot is polling for updates...")

        # Start polling
        # NOTE: This will conflict if a webhook is already configured.
        # If using webhook, do NOT run this bot - use telegram_client.py for sending messages instead.
        application.run_polling(allowed_updates=Update.ALL_TYPES)


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
