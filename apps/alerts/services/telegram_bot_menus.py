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
        margins = await self._get_margin_summary_for_header()

        now = datetime.now()
        date_str = now.strftime('%a %d %b')
        time_str = now.strftime('%I:%M %p').lstrip('0')

        # Format P&L
        try:
            pnl_val = float(data['current_pnl'])
            pnl_str = f"+{pnl_val:,.0f}" if pnl_val >= 0 else f"{pnl_val:,.0f}"
        except (ValueError, TypeError):
            pnl_str = data['current_pnl']

        # Format margin line
        margin_parts = []
        if margins.get('breeze_free') is not None:
            margin_parts.append(f"ICICI: {margins['breeze_free']/100000:.1f}L")
        if margins.get('kotak_free') is not None:
            margin_parts.append(f"Kotak: {margins['kotak_free']/100000:.1f}L")
        margin_line = " | ".join(margin_parts) if margin_parts else ""

        header = (
            "<b>mCube Trading Bot</b>\n"
            f"<code>{date_str} | {time_str}</code>\n"
            f"{'=' * 28}\n"
            f"VIX: {data['vix']} ({data['vix_status'] or 'N/A'}) | "
            f"Tradable: {data['is_tradable']}\n"
            f"P&amp;L: {pnl_str} | "
            f"Positions: {data['open_positions']} open"
        )
        if margin_line:
            header += f"\n{margin_line} free"

        keyboard = [
            [
                InlineKeyboardButton("\U0001f500 Trade", callback_data="menu_trade"),
                InlineKeyboardButton("\U0001f4cb Orders", callback_data="menu_orders"),
            ],
            [
                InlineKeyboardButton("\U0001f4ca Positions", callback_data="menu_positions"),
                InlineKeyboardButton("\U0001f4b0 P&L", callback_data="menu_pnl"),
            ],
            [
                InlineKeyboardButton("\U0001f4c8 Market", callback_data="menu_market"),
                InlineKeyboardButton("\U0001f6e1 Risk", callback_data="menu_risk"),
            ],
            [
                InlineKeyboardButton("\u2699\ufe0f Tasks", callback_data="menu_tasks"),
                InlineKeyboardButton("\U0001f527 Settings", callback_data="menu_settings"),
            ],
            [
                InlineKeyboardButton("\U0001f3e2 System", callback_data="menu_system"),
                InlineKeyboardButton("\u26a1 Quick Actions", callback_data="menu_quick"),
            ],
            [
                InlineKeyboardButton("\U0001f4c9 Analytics", callback_data="menu_analytics"),
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
                InlineKeyboardButton("\U0001f4f0 News/Sentiment", callback_data="news_view"),
            ],
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
        """Show tasks category overview with algorithm status at top."""
        summary = await self._get_task_summary()
        algo_status = await self._get_algorithm_status()

        message = "<b>\u2699\ufe0f Background Tasks</b>\n\n"

        # Algorithm status section
        if algo_status:
            message += "<b>ALGORITHMS</b>\n"
            for algo_key, info in algo_status.items():
                status_icon = "\u2705" if info['is_active'] else "\u274c"
                status_label = "ON" if info['is_active'] else "OFF"
                message += (
                    f"  {info['emoji']} {info['display_name']}: "
                    f"{status_icon} {status_label} "
                    f"({info['enabled_count']}/{info['own_count']} tasks)\n"
                )
            message += "\n"

        # Category section
        message += "<b>CATEGORIES</b>\n"
        for cat_key, cat_cfg in CATEGORY_CONFIG.items():
            counts = summary.get(cat_key, {'total': 0, 'active': 0})
            message += (
                f"  {cat_cfg['emoji']} {cat_cfg['label']}: "
                f"{counts['active']}/{counts['total']} active\n"
            )

        # Build keyboard - algorithm buttons first
        keyboard = []
        if algo_status:
            algo_row = []
            for algo_key, info in algo_status.items():
                if info['is_active']:
                    label = f"Disable {info['display_name'].split()[0]}"
                    cb = f"algo_dis_{algo_key}"
                else:
                    label = f"Enable {info['display_name'].split()[0]}"
                    cb = f"algo_en_{algo_key}"
                algo_row.append(InlineKeyboardButton(label, callback_data=cb))
            keyboard.append(algo_row)

        # Category buttons
        keyboard += [
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
            await self._show_core_settings_with_back(query)
        elif menu == 'system':
            await self._show_system_menu(query)
        elif menu == 'quick':
            await self._show_quick_actions_menu(query)
        elif menu == 'refresh':
            await self._show_main_menu(query)
        # New menus
        elif menu == 'trade':
            await self._show_trade_broker_selection(query)
        elif menu == 'orders':
            await self._show_orders_menu(query)
        elif menu == 'analytics':
            await self._show_analytics_menu(query)
        elif menu == 'margin':
            await self._show_margin_menu(query)
        elif menu == 'history':
            await self._show_trade_history_menu(query)

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
            [InlineKeyboardButton("\U0001f511 Broker Login", callback_data="login_view")],
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

        await self._bulk_toggle_tasks(enable)
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

    # =========================================================================
    # ALGORITHM DEPENDENCY MANAGEMENT
    # =========================================================================

    async def _handle_algorithm_action(self, query, data: str):
        """Route algo_ prefixed callbacks to the appropriate handler.

        Callback patterns:
            algo_en_{key}       – show enable confirmation
            algo_dis_{key}      – show disable confirmation
            algo_ok_en_{key}    – execute enable
            algo_ok_dis_{key}   – execute disable
        """
        # Strip "algo_" prefix
        rest = data[5:]

        if rest.startswith("ok_en_"):
            algo_key = rest[6:]
            result = await self._enable_algorithm(algo_key)
            await self._show_algo_result(query, "Enable Algorithm", result)

        elif rest.startswith("ok_dis_"):
            algo_key = rest[7:]
            result = await self._disable_algorithm(algo_key)
            await self._show_algo_result(query, "Disable Algorithm", result)

        elif rest.startswith("en_"):
            algo_key = rest[3:]
            preview = await self._get_algorithm_enable_preview(algo_key)
            if preview.get('error'):
                await query.edit_message_text(f"Error: {preview['error']}")
            else:
                await self._show_algo_enable_confirm(query, algo_key, preview)

        elif rest.startswith("dis_"):
            algo_key = rest[4:]
            preview = await self._get_algorithm_disable_preview(algo_key)
            if preview.get('error'):
                await query.edit_message_text(f"Error: {preview['error']}")
            else:
                await self._show_algo_disable_confirm(query, algo_key, preview)

    async def _show_algo_enable_confirm(self, query, algo_key: str, preview: dict):
        """Show confirmation screen listing all tasks that will be enabled."""
        emoji = preview['emoji']
        name = preview['display_name']

        message = f"<b>{emoji} Enable {name}?</b>\n\n"

        # Own tasks (strategy)
        message += "<b>STRATEGY TASKS:</b>\n"
        for t in preview['own_tasks']:
            icon = "\u2705" if t['is_enabled'] else "\u26aa"
            message += f"  {icon} {t['name']} ({t['schedule']})\n"

        # Shared tasks
        shared_with = preview.get('shared_with', '')
        shared_label = f"SHARED (also used by {shared_with})" if shared_with else "SHARED"
        message += f"\n<b>{shared_label}:</b>\n"
        for t in preview['shared_tasks']:
            icon = "\u2705" if t['is_enabled'] else "\u26aa"
            message += f"  {icon} {t['name']} ({t['schedule']})\n"

        # Monitoring tasks
        message += "\n<b>MONITORING:</b>\n"
        for t in preview['monitoring_tasks']:
            icon = "\u2705" if t['is_enabled'] else "\u26aa"
            message += f"  {icon} {t['name']} ({t['schedule']})\n"

        total = (
            len(preview['own_tasks'])
            + len(preview['shared_tasks'])
            + len(preview['monitoring_tasks'])
        )
        already = sum(
            1 for t in preview['own_tasks'] + preview['shared_tasks'] + preview['monitoring_tasks']
            if t['is_enabled']
        )
        new_count = total - already
        message += f"\n<i>{total} tasks total, {new_count} will be newly enabled</i>"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"Confirm Enable",
                    callback_data=f"algo_ok_en_{algo_key}"
                ),
                InlineKeyboardButton("Cancel", callback_data="back_tasks"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_algo_disable_confirm(self, query, algo_key: str, preview: dict):
        """Show smart disable screen with tasks to disable vs keep."""
        emoji = preview['emoji']
        name = preview['display_name']

        message = f"<b>{emoji} Disable {name}?</b>\n\n"

        # Tasks to disable
        message += "<b>WILL DISABLE:</b>\n"
        for t in preview['tasks_to_disable']:
            message += f"  \u274c {t['name']}\n"

        # Tasks to keep (if any)
        if preview['tasks_to_keep']:
            message += "\n<b>WILL KEEP (still needed):</b>\n"
            for t in preview['tasks_to_keep']:
                message += f"  \u2705 {t['name']}\n"
                message += f"      <i>{t['reason']}</i>\n"

        disable_count = len(preview['tasks_to_disable'])
        keep_count = len(preview['tasks_to_keep'])
        message += f"\n<i>{disable_count} to disable"
        if keep_count:
            message += f", {keep_count} kept"
        message += "</i>"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"Confirm Disable",
                    callback_data=f"algo_ok_dis_{algo_key}"
                ),
                InlineKeyboardButton("Cancel", callback_data="back_tasks"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_algo_result(self, query, action_name: str, result: dict):
        """Show result of an algorithm action, then offer return to tasks."""
        if result.get('success'):
            icon = "\u2705"
            msg = result.get('message', 'Done')
        else:
            icon = "\u274c"
            msg = result.get('error', 'Unknown error')

        message = f"{icon} <b>{action_name}</b>\n\n{msg}"

        keyboard = [
            [
                InlineKeyboardButton("\u00ab Back to Tasks", callback_data="back_tasks"),
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # ORDERS MENU
    # =========================================================================

    async def _show_orders_menu(self, query):
        """Show order book overview from both brokers."""
        breeze_data = await self._get_breeze_orders()
        kotak_data = await self._get_kotak_orders()

        now = datetime.now()
        date_str = now.strftime('%d %b %Y')

        message = f"<b>\U0001f4cb Orders | {date_str}</b>\n\n"

        # ICICI Breeze orders
        breeze_orders = breeze_data.get('orders', [])
        message += f"<b>ICICI Breeze ({len(breeze_orders)} orders)</b>\n"
        if breeze_orders:
            for i, o in enumerate(breeze_orders[:5]):
                sym = o.get('trading_symbol', '?')[:15]
                action = o.get('transaction_type', '?')[:4]
                qty = o.get('quantity', 0)
                status = o.get('status', '?')
                status_icon = {'Executed': '\u2705', 'Pending': '\U0001f7e1', 'Rejected': '\u274c'}.get(status, '\u2753')
                message += f"  {i+1}. {sym} {action} {qty} | {status} {status_icon}\n"
        else:
            if breeze_data.get('success'):
                message += "  No orders today\n"
            else:
                message += f"  {breeze_data.get('error', 'Unavailable')[:40]}\n"

        message += "\n"

        # Kotak Neo orders
        kotak_orders = kotak_data.get('orders', [])
        message += f"<b>Kotak Neo ({len(kotak_orders)} orders)</b>\n"
        if kotak_orders:
            for i, o in enumerate(kotak_orders[:5]):
                sym = str(o.get('trdSym', o.get('trading_symbol', '?')))[:15]
                action = str(o.get('trnsTp', o.get('transaction_type', '?')))[:4]
                qty = o.get('qty', o.get('quantity', 0))
                status = str(o.get('ordSt', o.get('status', '?')))
                status_icon = {'complete': '\u2705', 'open': '\U0001f7e1', 'rejected': '\u274c'}.get(status.lower(), '\u2753')
                message += f"  {i+1}. {sym} {action} {qty} | {status} {status_icon}\n"
        else:
            if kotak_data.get('success'):
                message += "  No orders today\n"
            else:
                message += f"  {kotak_data.get('error', 'Unavailable')[:40]}\n"

        keyboard = [
            [
                InlineKeyboardButton("ICICI Details", callback_data="ord_broker_breeze"),
                InlineKeyboardButton("Kotak Details", callback_data="ord_broker_kotak"),
            ],
            [
                InlineKeyboardButton("\U0001f504 Refresh", callback_data="ord_refresh"),
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_broker_orders_detail(self, query, broker: str):
        """Show detailed order list for a specific broker."""
        if broker == 'breeze':
            data = await self._get_breeze_orders()
            broker_label = 'ICICI Breeze'
        else:
            data = await self._get_kotak_orders()
            broker_label = 'Kotak Neo'

        orders = data.get('orders', [])
        message = f"<b>\U0001f4cb {broker_label} Orders</b>\n\n"

        if not orders:
            message += "No orders today."
        else:
            for i, o in enumerate(orders[:10]):
                if broker == 'breeze':
                    sym = o.get('trading_symbol', '?')
                    action = o.get('transaction_type', '?')
                    qty = o.get('quantity', 0)
                    price = o.get('average_price', o.get('price', 0))
                    status = o.get('status', '?')
                    order_id = o.get('order_id', '?')
                else:
                    sym = str(o.get('trdSym', o.get('trading_symbol', '?')))
                    action = str(o.get('trnsTp', o.get('transaction_type', '?')))
                    qty = o.get('qty', o.get('quantity', 0))
                    price = o.get('avgPrc', o.get('price', 0))
                    status = str(o.get('ordSt', o.get('status', '?')))
                    order_id = str(o.get('nOrdNo', o.get('order_id', '?')))

                try:
                    price_str = f"{float(price):,.2f}" if price else "—"
                except (ValueError, TypeError):
                    price_str = str(price)

                message += (
                    f"<b>{i+1}. {sym}</b>\n"
                    f"  {action} | Qty: {qty} | @ {price_str}\n"
                    f"  Status: {status} | ID: {str(order_id)[:12]}\n\n"
                )

        keyboard = []
        # Show cancel buttons for pending orders (Kotak only for now)
        if broker == 'kotak':
            for i, o in enumerate(orders[:5]):
                status = str(o.get('ordSt', '')).lower()
                if status in ('open', 'pending', 'trigger pending'):
                    order_id = str(o.get('nOrdNo', ''))
                    if order_id:
                        keyboard.append([
                            InlineKeyboardButton(
                                f"Cancel #{i+1}", callback_data=f"ord_cancel_kotak_{order_id}"
                            )
                        ])

        keyboard.append([
            InlineKeyboardButton("\U0001f504 Refresh", callback_data=f"ord_broker_{broker}"),
            InlineKeyboardButton("\u00ab Orders", callback_data="menu_orders"),
        ])
        keyboard.append([InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main")])

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # MARGIN / LIMITS MENU
    # =========================================================================

    async def _show_margin_menu(self, query):
        """Show margin and limits from both brokers."""
        breeze = await self._get_breeze_margin()
        kotak = await self._get_kotak_margin()

        message = "<b>\U0001f4b3 Margin &amp; Limits</b>\n\n"

        # ICICI Breeze
        message += "<b>ICICI Breeze (NFO)</b>\n"
        if breeze.get('success'):
            message += (
                f"  Cash Limit:  \u20b9{breeze['cash_limit']:,.0f}\n"
                f"  Blocked:     \u20b9{breeze['blocked']:,.0f}\n"
                f"  Available:   \u20b9{breeze['available']:,.0f} ({breeze['pct']}%)\n"
            )
        else:
            message += f"  {breeze.get('error', 'Unavailable')}\n"

        message += "\n<b>Kotak Neo</b>\n"
        if kotak.get('success'):
            message += (
                f"  Total Margin: \u20b9{kotak['total']:,.0f}\n"
                f"  Used:         \u20b9{kotak['used']:,.0f}\n"
                f"  Available:    \u20b9{kotak['available']:,.0f} ({kotak['pct']}%)\n"
            )
        else:
            message += f"  {kotak.get('error', 'Unavailable')}\n"

        # Combined
        combined = 0
        if breeze.get('success'):
            combined += breeze['available']
        if kotak.get('success'):
            combined += kotak['available']
        if combined > 0:
            message += f"\n<b>Combined Free: \u20b9{combined:,.0f}</b>"

        keyboard = [
            [
                InlineKeyboardButton("\U0001f504 Refresh", callback_data="margin_refresh"),
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # TRADE HISTORY MENU
    # =========================================================================

    async def _show_trade_history_menu(self, query, count: int = 10):
        """Show recent closed trades."""
        data = await self._get_trade_history(count)

        message = f"<b>\U0001f4c4 Trade History (Last {count})</b>\n\n"

        if not data.get('success') or not data.get('trades'):
            message += "No closed trades found."
        else:
            for i, t in enumerate(data['trades'], 1):
                instrument = t.get('instrument', '?')[:15]
                direction = t.get('direction', '?')
                pnl = float(t.get('net_pnl') or t.get('realized_pnl') or 0)
                pnl_str = f"+\u20b9{pnl:,.0f}" if pnl >= 0 else f"-\u20b9{abs(pnl):,.0f}"
                pnl_icon = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
                exit_date = ''
                if t.get('exit_time'):
                    try:
                        exit_date = t['exit_time'].strftime('%d-%b')
                    except AttributeError:
                        exit_date = str(t['exit_time'])[:6]

                message += f"  {pnl_icon} {instrument} {direction} {pnl_str} {exit_date}\n"

            message += (
                f"\nWin Rate: {data['win_rate']}% ({data['wins']}/{data['total_count']})\n"
                f"Total P&amp;L: {'+' if data['total_pnl'] >= 0 else ''}\u20b9{data['total_pnl']:,.0f}"
            )

        keyboard = [
            [
                InlineKeyboardButton("Last 5", callback_data="hist_count_5"),
                InlineKeyboardButton("Last 10", callback_data="hist_count_10"),
                InlineKeyboardButton("Last 20", callback_data="hist_count_20"),
            ],
            [
                InlineKeyboardButton("\U0001f504 Refresh", callback_data=f"hist_count_{count}"),
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # ANALYTICS / PERFORMANCE MENU
    # =========================================================================

    async def _show_analytics_menu(self, query, period: str = 'FY'):
        """Show performance analytics summary."""
        data = await self._get_performance_summary(period)

        period_labels = {'week': 'This Week', 'month': 'This Month', 'FY': 'FY 2025-26'}
        period_label = period_labels.get(period, period)

        message = f"<b>\U0001f4c9 Performance | {period_label}</b>\n\n"

        if not data.get('success') or data.get('total_trades', 0) == 0:
            message += "No trades found for this period."
        else:
            def fmt_pnl(v):
                return f"+\u20b9{v:,.0f}" if v >= 0 else f"-\u20b9{abs(v):,.0f}"

            message += (
                f"Total Trades:  {data['total_trades']}\n"
                f"Win Rate:      {data['win_rate']}% ({data['wins']}W / {data['losses']}L)\n"
                f"Total P&amp;L:     {fmt_pnl(data['total_pnl'])}\n"
                f"Avg Win:       {fmt_pnl(data['avg_win'])}\n"
                f"Avg Loss:      {fmt_pnl(data['avg_loss'])}\n"
            )

            if data.get('best_trade_name'):
                message += f"Best Trade:    {data['best_trade_name']} {fmt_pnl(data['best_trade'])}\n"
            if data.get('worst_trade_name'):
                message += f"Worst Trade:   {data['worst_trade_name']} {fmt_pnl(data['worst_trade'])}\n"

            message += (
                f"\n<b>Strategy Breakdown:</b>\n"
                f"  Futures: {data['futures_count']} trades, {fmt_pnl(data['futures_pnl'])}\n"
                f"  Options: {data['options_count']} trades, {fmt_pnl(data['options_pnl'])}\n"
            )

        keyboard = [
            [
                InlineKeyboardButton("This Week", callback_data="analytics_week"),
                InlineKeyboardButton("This Month", callback_data="analytics_month"),
                InlineKeyboardButton("FY", callback_data="analytics_FY"),
            ],
            [
                InlineKeyboardButton("\U0001f504 Refresh", callback_data=f"analytics_{period}"),
                InlineKeyboardButton("\u00ab Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # BROKER LOGIN MENU
    # =========================================================================

    async def _show_broker_login_menu(self, query):
        """Show broker session status and login buttons."""
        status = await self._get_broker_session_status()

        breeze_icon = "\u2705 Valid" if status['breeze_valid'] else "\u274c Expired"
        kotak_icon = "\u2705 Valid" if status['kotak_valid'] else "\u274c Expired"

        breeze_since = f" (since {status['breeze_since']})" if status.get('breeze_since') else ""
        kotak_since = f" (since {status['kotak_since']})" if status.get('kotak_since') else ""

        message = (
            "<b>\U0001f511 Broker Sessions</b>\n\n"
            f"ICICI Breeze: {breeze_icon}{breeze_since}\n"
            f"Kotak Neo:    {kotak_icon}{kotak_since}\n"
        )

        keyboard = [
            [
                InlineKeyboardButton("\U0001f511 Login ICICI", callback_data="login_breeze"),
                InlineKeyboardButton("\U0001f511 Login Kotak", callback_data="login_kotak"),
            ],
            [InlineKeyboardButton("\u00ab Back to Settings", callback_data="menu_settings")],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # NEWS / SENTIMENT MENU
    # =========================================================================

    async def _show_news_sentiment_menu(self, query):
        """Show market sentiment from analyzed news."""
        data = await self._get_market_sentiment()

        label = data.get('overall_label', 'N/A')
        score = data.get('overall_score', 0)

        label_icon = {
            'BULLISH': '\U0001f7e2', 'BEARISH': '\U0001f534', 'NEUTRAL': '\u26aa', 'NO DATA': '\u2753'
        }.get(label, '\u2753')

        message = (
            "<b>\U0001f4f0 Market Sentiment</b>\n\n"
            f"Overall: {label_icon} {label} (Score: {score})\n\n"
        )

        articles = data.get('articles', [])
        if articles:
            message += "<b>Recent Headlines:</b>\n"
            for a in articles:
                title = a.get('title', '?')[:60]
                s = a.get('sentiment_score')
                if s is not None:
                    if s > 0.2:
                        icon = "\U0001f7e2"
                    elif s < -0.2:
                        icon = "\U0001f534"
                    else:
                        icon = "\u26aa"
                else:
                    icon = "\u26aa"
                message += f"  {icon} {title}\n"
        else:
            message += "No analyzed news today.\n"

        blocking = data.get('blocking_news', False)
        message += f"\nBlocking News: {'YES' if blocking else 'None'}"

        now = datetime.now()
        message += f"\nLast Updated: {now.strftime('%I:%M %p').lstrip('0')}"

        keyboard = [
            [
                InlineKeyboardButton("\U0001f504 Refresh", callback_data="news_view"),
                InlineKeyboardButton("\u00ab Back to Market", callback_data="menu_market"),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # SL / TARGET MODIFICATION MENUS
    # =========================================================================

    async def _show_sl_modify_menu(self, query, position_id: int):
        """Show SL modification options for a position."""
        pos = await self._get_position_detail(position_id)
        if not pos.get('success'):
            await query.edit_message_text(f"Error: {pos.get('error', 'Position not found')}")
            return

        current_sl = pos.get('stop_loss')
        entry = pos.get('entry_price', 0)
        current = pos.get('current_price') or entry

        sl_str = f"\u20b9{current_sl:,.2f}" if current_sl else "Not set"

        message = (
            f"<b>Modify Stop Loss</b>\n\n"
            f"<b>{pos['instrument']}</b>\n"
            f"Entry: \u20b9{entry:,.2f} | Current: \u20b9{current:,.2f}\n"
            f"Current SL: {sl_str}\n\n"
            "Adjust SL:"
        )

        # Preset percentage buttons
        base = current_sl if current_sl else current
        pct_buttons = [-2, -1, -0.5, 0.5, 1, 2]

        keyboard = []
        row = []
        for pct in pct_buttons:
            new_val = base * (1 + pct / 100)
            label = f"{'+' if pct > 0 else ''}{pct}%"
            # Encode: sl_pct_{position_id}_{new_value_x100}
            encoded = int(new_val * 100)
            row.append(InlineKeyboardButton(label, callback_data=f"sl_set_{position_id}_{encoded}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("\u00ab Back", callback_data="back_to_brokers")])

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _show_target_modify_menu(self, query, position_id: int):
        """Show target modification options for a position."""
        pos = await self._get_position_detail(position_id)
        if not pos.get('success'):
            await query.edit_message_text(f"Error: {pos.get('error', 'Position not found')}")
            return

        current_target = pos.get('target')
        entry = pos.get('entry_price', 0)
        current = pos.get('current_price') or entry

        tgt_str = f"\u20b9{current_target:,.2f}" if current_target else "Not set"

        message = (
            f"<b>Modify Target</b>\n\n"
            f"<b>{pos['instrument']}</b>\n"
            f"Entry: \u20b9{entry:,.2f} | Current: \u20b9{current:,.2f}\n"
            f"Current Target: {tgt_str}\n\n"
            "Adjust Target:"
        )

        base = current_target if current_target else current
        pct_buttons = [-2, -1, -0.5, 0.5, 1, 2]

        keyboard = []
        row = []
        for pct in pct_buttons:
            new_val = base * (1 + pct / 100)
            label = f"{'+' if pct > 0 else ''}{pct}%"
            encoded = int(new_val * 100)
            row.append(InlineKeyboardButton(label, callback_data=f"tgt_set_{position_id}_{encoded}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("\u00ab Back", callback_data="back_to_brokers")])

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =========================================================================
    # TASK SCHEDULE EDITING MENU
    # =========================================================================

    async def _show_task_schedule_menu(self, query, task_key: str):
        """Show schedule editing options for a specific task."""
        detail = await self._get_task_schedule_detail(task_key)
        if not detail.get('success'):
            await query.edit_message_text(f"Error: {detail.get('error', 'Unknown')}")
            return

        name = detail['display_name']
        hour = detail['current_hour']
        minute = detail['current_minute']
        default_h = detail['default_hour']
        default_m = detail['default_minute']

        message = (
            f"<b>\U0001f4c5 Schedule: {name}</b>\n\n"
            f"Current: <b>{hour:02d}:{minute:02d}</b>\n"
            f"Default: {default_h:02d}:{default_m:02d}\n"
        )

        # Calculate +/- 15 min times
        from datetime import datetime as dt, timedelta
        current_time = dt(2000, 1, 1, hour, minute)
        earlier = current_time - timedelta(minutes=15)
        later = current_time + timedelta(minutes=15)

        eh, em = earlier.hour, earlier.minute
        lh, lm = later.hour, later.minute

        keyboard = [
            [
                InlineKeyboardButton(
                    f"15 min earlier \u2192 {eh:02d}:{em:02d}",
                    callback_data=f"tsched_set_{task_key}_{eh}_{em}"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"15 min later \u2192 {lh:02d}:{lm:02d}",
                    callback_data=f"tsched_set_{task_key}_{lh}_{lm}"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"Reset to default ({default_h:02d}:{default_m:02d})",
                    callback_data=f"tsched_set_{task_key}_{default_h}_{default_m}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "\u00ab Back",
                    callback_data=f"task_cat_{detail.get('category', 'data') if detail.get('category') else 'data'}"
                ),
            ],
        ]

        await query.edit_message_text(
            message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )
