"""
Telegram Bot Menu Mixin

Provides all interactive menu rendering methods for the Telegram bot.
Each method builds a message + inline keyboard for a specific sub-menu.
"""

import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# Category display config
CATEGORY_CONFIG = {
    'data': {'emoji': '\U0001f4ca', 'label': 'Data', 'full': 'Market Data Tasks'},
    'strategies': {'emoji': '\U0001f3af', 'label': 'Strategies', 'full': 'Strategy Tasks'},
    'transactions': {'emoji': '\U0001f4b3', 'label': 'Txns', 'full': 'Transaction Tasks'},
    'monitoring': {'emoji': '\U0001f441', 'label': 'Monitoring', 'full': 'Monitoring Tasks'},
    'risk': {'emoji': '\U0001f6e1', 'label': 'Risk', 'full': 'Risk Tasks'},
    'reports': {'emoji': '\U0001f4cb', 'label': 'Reports', 'full': 'Report Tasks'},
}


class MenuMixin:
    """Menu rendering methods for TelegramBotHandler.

    Expects DataMixin methods to be available on self (via multiple inheritance).
    """

    # =========================================================================
    # MAIN MENU
    # =========================================================================

    async def _show_main_menu(self, query_or_message, is_command=False):
        """Show the main menu with header and button grid.

        Args:
            query_or_message: Either a CallbackQuery or a Message object.
            is_command: True if called from a /start command (uses reply_text).
        """
        data = await self._get_main_menu_data()

        now = datetime.now()
        date_str = now.strftime('%a %d %b')
        time_str = now.strftime('%I:%M %p').lstrip('0')

        # Format P&L
        try:
            pnl_val = float(data['current_pnl'])
            pnl_str = f"+{pnl_val:,.0f}" if pnl_val >= 0 else f"{pnl_val:,.0f}"
        except (ValueError, TypeError):
            pnl_str = data['current_pnl']

        header = (
            "<b>mCube Trading Bot</b>\n"
            f"<code>{date_str} | {time_str}</code>\n"
            f"{'=' * 28}\n"
            f"VIX: {data['vix']} ({data['vix_status'] or 'N/A'}) | "
            f"Tradable: {data['is_tradable']}\n"
            f"P&amp;L: {pnl_str} | "
            f"Positions: {data['open_positions']} open"
        )

        keyboard = [
            [
                InlineKeyboardButton("\U0001f4ca Positions", callback_data="menu_positions"),
                InlineKeyboardButton("\U0001f4b0 P&L Today", callback_data="menu_pnl"),
            ],
            [
                InlineKeyboardButton("\U0001f4c8 Market", callback_data="menu_market"),
                InlineKeyboardButton("\U0001f6e1 Risk", callback_data="menu_risk"),
            ],
            [
                InlineKeyboardButton("\u2699\ufe0f Tasks", callback_data="menu_tasks"),
                InlineKeyboardButton("\U0001f39b Settings", callback_data="menu_settings"),
            ],
            [
                InlineKeyboardButton("\U0001f3e5 System", callback_data="menu_system"),
                InlineKeyboardButton("\u26a1 Quick Actions", callback_data="menu_quick"),
            ],
            [
                InlineKeyboardButton("\U0001f504 Refresh", callback_data="menu_refresh"),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        if is_command:
            await query_or_message.reply_text(
                header, parse_mode='HTML', reply_markup=reply_markup
            )
        else:
            await query_or_message.edit_message_text(
                header, parse_mode='HTML', reply_markup=reply_markup
            )

    # =========================================================================
    # P&L MENU
    # =========================================================================

    async def _show_pnl_menu(self, query):
        """Show today's P&L sub-menu."""
        data = await self._get_daily_pnl_data()

        now = datetime.now()
        date_str = now.strftime('%a %d %b')

        def fmt(v):
            return f"+{v:,.0f}" if v >= 0 else f"{v:,.0f}"

        message = (
            f"<b>\U0001f4b0 Today's P&amp;L | {date_str}</b>\n\n"
            f"Realized: {fmt(data['realized'])}\n"
            f"Unrealized: {fmt(data['unrealized'])}\n"
            f"<b>Total: {fmt(data['total'])}</b>\n\n"
            f"Trades: {data['trades']} | "
            f"W: {data['wins']} | L: {data['losses']} | "
            f"Win%: {data['win_pct']}"
        )

        keyboard = [
            [
                InlineKeyboardButton("\U0001f504 Refresh", callback_data="pnl_refresh"),
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # MARKET MENU
    # =========================================================================

    async def _show_market_menu(self, query):
        """Show market snapshot sub-menu."""
        data = await self._get_market_data()

        now = datetime.now()
        time_str = now.strftime('%I:%M %p').lstrip('0')

        message = (
            f"<b>\U0001f4c8 Market Snapshot | {time_str}</b>\n\n"
            f"VIX: {data['vix']} ({data['vix_status'] or 'N/A'})\n"
            f"Day Tradable: {data['is_tradable']}\n"
            f"Daily Delta: {data['daily_delta']}\n"
            f"Open Positions: {data['open_positions']}"
        )

        keyboard = [
            [
                InlineKeyboardButton("\U0001f504 Refresh", callback_data="mkt_refresh"),
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # RISK MENU
    # =========================================================================

    async def _show_risk_menu(self, query):
        """Show risk dashboard sub-menu."""
        data = await self._get_risk_dashboard_data()

        message = "<b>\U0001f6e1 Risk Dashboard</b>\n\n"

        if data['risk_limits']:
            for rl in data['risk_limits']:
                icon = "\u274c" if rl['breached'] else "\u2705"
                message += (
                    f"{rl['type']}: {rl['current']:,.0f} / {rl['limit']:,.0f} "
                    f"({rl['pct']}%) {icon}\n"
                )
        else:
            message += "No risk limits configured.\n"

        message += f"\nCircuit Breakers: {data['active_circuit_breakers']} active"

        keyboard = [
            [
                InlineKeyboardButton("\U0001f504 Refresh", callback_data="risk_refresh"),
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # TASKS MENU - CATEGORY OVERVIEW
    # =========================================================================

    async def _show_tasks_menu(self, query):
        """Show tasks category overview."""
        summary = await self._get_task_summary()

        message = "<b>\u2699\ufe0f Background Tasks</b>\n\n"

        for cat_key, cat_cfg in CATEGORY_CONFIG.items():
            counts = summary.get(cat_key, {'total': 0, 'active': 0})
            message += (
                f"{cat_cfg['emoji']} {cat_cfg['label']}: "
                f"{counts['active']}/{counts['total']} active\n"
            )

        keyboard = [
            [
                InlineKeyboardButton("\U0001f4ca Data", callback_data="task_cat_data"),
                InlineKeyboardButton("\U0001f3af Strategies", callback_data="task_cat_strategies"),
            ],
            [
                InlineKeyboardButton("\U0001f4b3 Txns", callback_data="task_cat_transactions"),
                InlineKeyboardButton("\U0001f441 Monitor", callback_data="task_cat_monitoring"),
            ],
            [
                InlineKeyboardButton("\U0001f6e1 Risk", callback_data="task_cat_risk"),
                InlineKeyboardButton("\U0001f4cb Reports", callback_data="task_cat_reports"),
            ],
            [
                InlineKeyboardButton("\u25b6\ufe0f Start All", callback_data="task_all_start"),
                InlineKeyboardButton("\u23f9 Stop All", callback_data="task_all_stop"),
            ],
            [
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # TASKS MENU - CATEGORY DETAIL
    # =========================================================================

    async def _show_task_category(self, query, category: str):
        """Show tasks for a specific category with toggle/run buttons."""
        tasks = await self._get_category_tasks(category)
        cat_cfg = CATEGORY_CONFIG.get(category, {'emoji': '\u2699\ufe0f', 'full': category.title()})

        message = f"<b>{cat_cfg['emoji']} {cat_cfg['full']}</b>\n\n"

        if not tasks:
            message += "No tasks in this category."
        else:
            for t in tasks:
                icon = "\u2705" if t['is_enabled'] else "\u274c"
                sched = f" ({t['schedule']})" if t['schedule'] else ""
                message += f"{icon} {t['name']}{sched}\n"

        keyboard = []
        for t in tasks:
            status_label = "Disable" if t['is_enabled'] else "Enable"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_label}: {t['name'][:18]}",
                    callback_data=f"tt_{t['key'][:50]}"
                ),
                InlineKeyboardButton(
                    "\u25b6 Run",
                    callback_data=f"tr_{t['key'][:50]}"
                ),
            ])

        keyboard.append([
            InlineKeyboardButton("\u00ab Back to Tasks", callback_data="back_tasks"),
        ])

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # SYSTEM HEALTH MENU
    # =========================================================================

    async def _show_system_menu(self, query):
        """Show system health sub-menu."""
        health = await self._get_system_health()

        def status(ok):
            return "\u2705 Running" if ok else "\u274c Down"

        breeze_status = "\u2705 Valid" if health['breeze'] else "\u274c No Session"
        kotak_status = "\u2705 Active" if health['kotak'] else "\u274c Inactive"

        message = (
            "<b>\U0001f3e5 System Health</b>\n\n"
            f"Celery Worker: {status(health['worker'])}\n"
            f"Celery Beat: {status(health['beat'])}\n"
            f"Redis: {status(health['redis'])}\n"
            f"Breeze: {breeze_status}\n"
            f"Kotak: {kotak_status}\n\n"
            f"Last Task: {health['last_task_ago']}\n"
            f"Errors (24h): {health['errors_24h']}"
        )

        keyboard = [
            [
                InlineKeyboardButton("\U0001f504 Refresh", callback_data="sys_refresh"),
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # QUICK ACTIONS MENU
    # =========================================================================

    async def _show_quick_actions_menu(self, query):
        """Show quick actions sub-menu."""
        message = (
            "<b>\u26a1 Quick Actions</b>\n\n"
            "<i>Use with caution \u2014 these execute immediately</i>"
        )

        keyboard = [
            [
                InlineKeyboardButton("\u23f8 Pause Trading", callback_data="qa_pause"),
                InlineKeyboardButton("\u25b6 Resume Trading", callback_data="qa_resume"),
            ],
            [
                InlineKeyboardButton("\U0001f6a8 Close All Positions", callback_data="qa_closeall"),
            ],
            [
                InlineKeyboardButton("\U0001f511 Refresh Breeze", callback_data="qa_breeze"),
            ],
            [
                InlineKeyboardButton("\U0001f3af Run Futures Algo", callback_data="qa_futures"),
            ],
            [
                InlineKeyboardButton("\U0001f4ca Force Data Sync", callback_data="qa_datasync"),
            ],
            [
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # QUICK ACTION CONFIRMATION
    # =========================================================================

    async def _show_action_result(self, query, action_name: str, result: dict):
        """Show result of a quick action, then return to quick actions menu."""
        if result.get('success'):
            icon = "\u2705"
            msg = result.get('message', 'Done')
        else:
            icon = "\u274c"
            msg = result.get('error', 'Unknown error')

        message = (
            f"{icon} <b>{action_name}</b>\n\n"
            f"{msg}"
        )

        keyboard = [
            [
                InlineKeyboardButton("\u00ab Quick Actions", callback_data="menu_quick"),
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_confirmation(self, query, action: str, message: str):
        """Show a confirmation prompt for dangerous actions."""
        keyboard = [
            [
                InlineKeyboardButton("Yes, do it", callback_data=f"qa_confirm_{action}"),
                InlineKeyboardButton("Cancel", callback_data="menu_quick"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # CALLBACK HANDLERS - MENU NAVIGATION
    # =========================================================================

    async def _handle_menu_nav(self, query, data: str):
        """Handle menu_ prefixed callbacks."""
        menu = data.replace('menu_', '')

        if menu == 'positions':
            # Reuse existing positions flow - show broker picker
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
        elif menu == 'pnl':
            await self._show_pnl_menu(query)
        elif menu == 'market':
            await self._show_market_menu(query)
        elif menu == 'risk':
            await self._show_risk_menu(query)
        elif menu == 'tasks':
            await self._show_tasks_menu(query)
        elif menu == 'settings':
            # Reuse existing core settings flow
            await self._show_core_settings_with_back(query)
        elif menu == 'system':
            await self._show_system_menu(query)
        elif menu == 'quick':
            await self._show_quick_actions_menu(query)
        elif menu == 'refresh':
            await self._show_main_menu(query)

    async def _show_core_settings_with_back(self, query):
        """Show core settings with a Main Menu button added."""
        config = await self._get_core_config()

        futures_status = "ON" if config['enable_futures_trading'] else "OFF"
        options_status = config['options_strategy']

        options_display = {
            'NONE': 'Disabled',
            'AUTO': 'Auto (VIX)',
            'STRANGLE': 'Strangle',
            'BROKEN_IRON_CONDOR': 'Iron Condor'
        }.get(options_status, options_status)

        message = (
            "<b>\U0001f39b Core Trading Settings</b>\n\n"
            f"<b>Futures:</b> {futures_status}\n"
            f"<b>Options:</b> {options_display}\n"
            f"<b>Options Lots:</b> {config['options_lots']}\n"
            f"<b>Futures Lots:</b> {config['futures_lots']}\n"
            f"<b>Telegram Confirm:</b> {'ON' if config['require_confirmation'] else 'OFF'}\n\n"
            "<i>Tap to change:</i>"
        )

        keyboard = [
            [InlineKeyboardButton(f"Futures: {futures_status}", callback_data="core_toggle_futures")],
            [InlineKeyboardButton(f"Options: {options_display}", callback_data="core_options_menu")],
            [
                InlineKeyboardButton(f"Opt Lots: {config['options_lots']}", callback_data="core_options_lots"),
                InlineKeyboardButton(f"Fut Lots: {config['futures_lots']}", callback_data="core_futures_lots"),
            ],
            [InlineKeyboardButton(
                f"Confirm: {'ON' if config['require_confirmation'] else 'OFF'}",
                callback_data="core_toggle_confirm"
            )],
            [InlineKeyboardButton("Refresh", callback_data="core_refresh")],
            [InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main")],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # CALLBACK HANDLERS - TASKS
    # =========================================================================

    async def _handle_task_toggle(self, query, data: str):
        """Handle tt_ prefixed callbacks (task toggle)."""
        task_key = data[3:]  # Remove 'tt_' prefix
        result = await self._toggle_task(task_key)

        if result.get('success'):
            # Refresh the category view to show updated state
            from apps.core.task_config import TASK_DEFAULT_CONFIG
            category = TASK_DEFAULT_CONFIG.get(task_key, {}).get('category', 'data')
            await self._show_task_category(query, category)
        else:
            await query.edit_message_text(f"Error toggling task: {result.get('error', 'Unknown')}")

    async def _handle_task_run(self, query, data: str):
        """Handle tr_ prefixed callbacks (task run now)."""
        task_key = data[3:]  # Remove 'tr_' prefix

        result = await self._run_task_immediately(task_key)

        from apps.core.task_config import TASK_DEFAULT_CONFIG
        task_name = TASK_DEFAULT_CONFIG.get(task_key, {}).get('display_name', task_key)
        category = TASK_DEFAULT_CONFIG.get(task_key, {}).get('category', 'data')

        if result.get('success'):
            task_id = result.get('task_id', 'N/A')[:8]
            # Show brief success then refresh category view
            await self._show_task_category(query, category)
        else:
            await query.edit_message_text(
                f"Failed to run {task_name}: {result.get('error', 'Unknown')[:200]}"
            )

    async def _handle_task_bulk(self, query, data: str):
        """Handle task_all_ prefixed callbacks."""
        action = data.replace('task_all_', '')
        enable = action == 'start'

        result = await self._bulk_toggle_tasks(enable)
        await self._show_tasks_menu(query)

    # =========================================================================
    # CALLBACK HANDLERS - QUICK ACTIONS
    # =========================================================================

    async def _handle_quick_action(self, query, data: str):
        """Handle qa_ prefixed callbacks."""
        action = data.replace('qa_', '')

        # Dangerous actions require confirmation
        if action == 'pause':
            await self._show_confirmation(
                query, 'pause',
                "<b>\u26a0\ufe0f Pause Trading?</b>\n\n"
                "This will set isDayTradable=No.\n"
                "All new trade entries will be blocked.\n\n"
                "Are you sure?"
            )
        elif action == 'closeall':
            await self._show_confirmation(
                query, 'closeall',
                "<b>\U0001f6a8 Close ALL Positions?</b>\n\n"
                "This will trigger the close-trading-day task.\n"
                "All open positions will be closed.\n\n"
                "Are you sure?"
            )
        elif action == 'resume':
            result = await self._resume_trading()
            await self._show_action_result(query, "Resume Trading", result)
        elif action == 'breeze':
            result = await self._refresh_breeze()
            await self._show_action_result(query, "Refresh Breeze", result)
        elif action == 'futures':
            result = await self._run_futures_algo()
            await self._show_action_result(query, "Futures Algorithm", result)
        elif action == 'datasync':
            result = await self._force_data_sync()
            await self._show_action_result(query, "Data Sync", result)
        # Confirmation handlers
        elif action == 'confirm_pause':
            result = await self._pause_trading()
            await self._show_action_result(query, "Pause Trading", result)
        elif action == 'confirm_closeall':
            result = await self._trigger_close_all()
            await self._show_action_result(query, "Close All Positions", result)
