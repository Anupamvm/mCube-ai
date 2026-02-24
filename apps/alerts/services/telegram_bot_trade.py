"""
Telegram Bot Trade Mixin

Multi-step trade wizard for placing manual orders from Telegram.
State stored in Django cache (trade_state_{chat_id}).

Flow: Broker → Type → Symbol → Expiry → Direction+Lots → Order Type → Confirm → Execute
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

# Top F&O symbols shown in the grid
TOP_FO_SYMBOLS = [
    'NIFTY', 'BANKNIFTY', 'FINNIFTY',
    'RELIANCE', 'SBIN', 'TATAMOTORS',
    'HDFCBANK', 'INFY', 'TCS',
    'ITC', 'LT', 'AXISBANK',
    'ICICIBANK', 'BHARTIARTL', 'BAJFINANCE',
]

LOT_CHOICES = [1, 2, 3, 5, 10]

CACHE_TIMEOUT = 600  # 10 min wizard timeout


class TradeMixin:
    """Trade wizard mixin for TelegramBotHandler.

    Provides a multi-step order entry wizard via inline keyboards.
    State is persisted in Django cache keyed by chat_id.
    """

    # =========================================================================
    # WIZARD STATE MANAGEMENT
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_trade_state(self, chat_id) -> dict:
        from django.db import close_old_connections
        close_old_connections()
        from django.core.cache import cache
        return cache.get(f'trade_state_{chat_id}') or {}

    @sync_to_async(thread_sensitive=False)
    def _set_trade_state(self, chat_id, state: dict):
        from django.db import close_old_connections
        close_old_connections()
        from django.core.cache import cache
        cache.set(f'trade_state_{chat_id}', state, CACHE_TIMEOUT)

    @sync_to_async(thread_sensitive=False)
    def _clear_trade_state(self, chat_id):
        from django.db import close_old_connections
        close_old_connections()
        from django.core.cache import cache
        cache.delete(f'trade_state_{chat_id}')

    # =========================================================================
    # STEP 1: BROKER SELECTION
    # =========================================================================

    async def _show_trade_broker_selection(self, query_or_message, is_command=False):
        """Show broker selection — first step of the trade wizard."""
        message = (
            "<b>🔀 New Trade</b>\n\n"
            "Select broker:"
        )
        keyboard = [
            [
                InlineKeyboardButton("ICICI Breeze", callback_data="trade_broker_breeze"),
                InlineKeyboardButton("Kotak Neo", callback_data="trade_broker_kotak"),
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="trade_cancel")],
        ]
        markup = InlineKeyboardMarkup(keyboard)

        if is_command:
            await query_or_message.reply_text(message, parse_mode='HTML', reply_markup=markup)
        else:
            await query_or_message.edit_message_text(message, parse_mode='HTML', reply_markup=markup)

    # =========================================================================
    # STEP 2: INSTRUMENT TYPE
    # =========================================================================

    async def _show_trade_type_selection(self, query, broker: str):
        """Show instrument type selection."""
        chat_id = query.message.chat_id
        await self._set_trade_state(chat_id, {'broker': broker})

        broker_label = 'ICICI Breeze' if broker == 'breeze' else 'Kotak Neo'
        message = (
            f"<b>🔀 New Trade</b>\n"
            f"Broker: {broker_label}\n\n"
            "Select instrument type:"
        )
        keyboard = [
            [
                InlineKeyboardButton("Futures", callback_data=f"trade_type_{broker}_futures"),
                InlineKeyboardButton("Options", callback_data=f"trade_type_{broker}_options"),
            ],
            [InlineKeyboardButton("« Back", callback_data="menu_trade")],
        ]
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # =========================================================================
    # STEP 3: SYMBOL SELECTION
    # =========================================================================

    async def _show_trade_symbol_grid(self, query, broker: str, inst_type: str):
        """Show symbol selection grid."""
        chat_id = query.message.chat_id
        state = await self._get_trade_state(chat_id)
        state.update({'broker': broker, 'inst_type': inst_type})
        await self._set_trade_state(chat_id, state)

        broker_label = 'ICICI Breeze' if broker == 'breeze' else 'Kotak Neo'
        type_label = inst_type.title()

        message = (
            f"<b>🔀 New Trade</b>\n"
            f"Broker: {broker_label} | {type_label}\n\n"
            "Select symbol:"
        )

        # Build 3-column grid of symbols
        keyboard = []
        row = []
        for i, sym in enumerate(TOP_FO_SYMBOLS):
            row.append(InlineKeyboardButton(sym, callback_data=f"trade_sym_{sym}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        # More symbols button + navigation
        keyboard.append([InlineKeyboardButton("More symbols...", callback_data="trade_sym_more")])
        keyboard.append([InlineKeyboardButton("« Back", callback_data=f"trade_broker_{broker}")])

        await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_trade_more_symbols(self, query):
        """Show extended symbol list from ContractData."""
        chat_id = query.message.chat_id
        state = await self._get_trade_state(chat_id)
        symbols = await self._get_available_fo_symbols()

        broker_label = 'ICICI Breeze' if state.get('broker') == 'breeze' else 'Kotak Neo'
        type_label = (state.get('inst_type') or 'futures').title()

        message = (
            f"<b>🔀 New Trade</b>\n"
            f"Broker: {broker_label} | {type_label}\n\n"
            "All F&O symbols:"
        )

        keyboard = []
        row = []
        for sym in symbols[:45]:  # Cap at 45 to fit Telegram limits
            row.append(InlineKeyboardButton(sym, callback_data=f"trade_sym_{sym}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("« Back", callback_data=f"trade_type_{state.get('broker', 'breeze')}_{state.get('inst_type', 'futures')}")])

        await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    @sync_to_async(thread_sensitive=False)
    def _get_available_fo_symbols(self) -> list:
        """Get distinct F&O symbols from ContractData."""
        from django.db import close_old_connections
        close_old_connections()
        try:
            from apps.data.models import ContractData
            symbols = (
                ContractData.objects
                .values_list('symbol', flat=True)
                .distinct()
                .order_by('symbol')
            )
            return list(symbols)
        except Exception as e:
            logger.error(f"Error fetching F&O symbols: {e}")
            return TOP_FO_SYMBOLS

    # =========================================================================
    # STEP 4: EXPIRY SELECTION (+ Option Type & Strike for Options)
    # =========================================================================

    async def _show_trade_expiry_selection(self, query, symbol: str):
        """Show available expiries for the selected symbol."""
        chat_id = query.message.chat_id
        state = await self._get_trade_state(chat_id)
        state['symbol'] = symbol
        await self._set_trade_state(chat_id, state)

        inst_type = state.get('inst_type', 'futures')
        expiries = await self._get_symbol_expiries(symbol, inst_type)

        broker_label = 'ICICI Breeze' if state.get('broker') == 'breeze' else 'Kotak Neo'

        message = (
            f"<b>🔀 New Trade</b>\n"
            f"Broker: {broker_label} | {inst_type.title()}\n"
            f"Symbol: {symbol}\n\n"
            "Select expiry:"
        )

        keyboard = []
        for exp in expiries[:8]:  # Max 8 expiries
            keyboard.append([
                InlineKeyboardButton(exp, callback_data=f"trade_exp_{exp}")
            ])

        if not expiries:
            message += "\n\n<i>No expiries found for this symbol.</i>"

        keyboard.append([InlineKeyboardButton("« Back", callback_data=f"trade_type_{state.get('broker', 'breeze')}_{inst_type}")])

        await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_trade_option_type(self, query, expiry: str):
        """Show CE/PE selection for options trades."""
        chat_id = query.message.chat_id
        state = await self._get_trade_state(chat_id)
        state['expiry'] = expiry
        await self._set_trade_state(chat_id, state)

        if state.get('inst_type') == 'options':
            message = (
                f"<b>🔀 New Trade</b>\n"
                f"{state['symbol']} | {expiry}\n\n"
                "Select option type:"
            )
            keyboard = [
                [
                    InlineKeyboardButton("CE (Call)", callback_data="trade_opttype_CE"),
                    InlineKeyboardButton("PE (Put)", callback_data="trade_opttype_PE"),
                ],
                [InlineKeyboardButton("« Back", callback_data=f"trade_sym_{state['symbol']}")],
            ]
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            # Futures — skip option type, go to direction
            await self._show_trade_direction(query)

    async def _show_trade_strike_selection(self, query, option_type: str):
        """Show strike price selection for options."""
        chat_id = query.message.chat_id
        state = await self._get_trade_state(chat_id)
        state['option_type'] = option_type
        await self._set_trade_state(chat_id, state)

        strikes = await self._get_option_strikes(
            state['symbol'], state['expiry'], option_type
        )

        message = (
            f"<b>🔀 New Trade</b>\n"
            f"{state['symbol']} {option_type} | {state['expiry']}\n\n"
            "Select strike:"
        )

        keyboard = []
        row = []
        for strike in strikes[:20]:  # Max 20 strikes
            label = f"{strike:g}" if isinstance(strike, float) else str(strike)
            row.append(InlineKeyboardButton(label, callback_data=f"trade_strike_{label}"))
            if len(row) == 4:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        if not strikes:
            message += "\n\n<i>No strikes found.</i>"

        keyboard.append([InlineKeyboardButton("« Back", callback_data=f"trade_exp_{state['expiry']}")])

        await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    @sync_to_async(thread_sensitive=False)
    def _get_symbol_expiries(self, symbol: str, inst_type: str) -> list:
        """Get available expiries for a symbol."""
        from django.db import close_old_connections
        close_old_connections()
        try:
            from apps.data.models import ContractData
            qs = ContractData.objects.filter(symbol=symbol)
            if inst_type == 'futures':
                qs = qs.filter(option_type='FUT')
            else:
                qs = qs.exclude(option_type='FUT')
            expiries = list(
                qs.values_list('expiry', flat=True)
                .distinct()
                .order_by('expiry')
            )
            return expiries
        except Exception as e:
            logger.error(f"Error fetching expiries for {symbol}: {e}")
            return []

    @sync_to_async(thread_sensitive=False)
    def _get_option_strikes(self, symbol: str, expiry: str, option_type: str) -> list:
        """Get available strikes for a symbol/expiry/option_type."""
        from django.db import close_old_connections
        close_old_connections()
        try:
            from apps.data.models import ContractData
            strikes = list(
                ContractData.objects
                .filter(symbol=symbol, expiry=expiry, option_type=option_type)
                .exclude(strike_price__isnull=True)
                .values_list('strike_price', flat=True)
                .distinct()
                .order_by('strike_price')
            )
            # Try to center around spot price
            spot_data = (
                ContractData.objects
                .filter(symbol=symbol, option_type='FUT')
                .first()
            )
            if spot_data and spot_data.spot and strikes:
                spot = float(spot_data.spot)
                # Return 10 strikes around ATM
                closest_idx = min(range(len(strikes)), key=lambda i: abs(float(strikes[i]) - spot))
                start = max(0, closest_idx - 10)
                end = min(len(strikes), closest_idx + 11)
                return strikes[start:end]
            return strikes[:20]
        except Exception as e:
            logger.error(f"Error fetching strikes: {e}")
            return []

    # =========================================================================
    # STEP 5: DIRECTION + LOTS
    # =========================================================================

    async def _show_trade_direction(self, query):
        """Show BUY/SELL direction and lot selection."""
        chat_id = query.message.chat_id
        state = await self._get_trade_state(chat_id)

        symbol = state.get('symbol', '?')
        expiry = state.get('expiry', '?')
        inst_type = state.get('inst_type', 'futures')
        opt_info = ''
        if inst_type == 'options':
            opt_info = f" {state.get('option_type', '')} {state.get('strike', '')}"

        message = (
            f"<b>🔀 New Trade</b>\n"
            f"{symbol}{opt_info} | {expiry}\n\n"
            "Select direction and lots:"
        )

        keyboard = [
            [
                InlineKeyboardButton("BUY", callback_data="trade_dir_BUY"),
                InlineKeyboardButton("SELL", callback_data="trade_dir_SELL"),
            ],
        ]

        # Back button
        if inst_type == 'options':
            keyboard.append([InlineKeyboardButton("« Back", callback_data=f"trade_opttype_{state.get('option_type', 'CE')}")])
        else:
            keyboard.append([InlineKeyboardButton("« Back", callback_data=f"trade_sym_{symbol}")])

        await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_trade_lots(self, query, direction: str):
        """Show lot count selection after direction is chosen."""
        chat_id = query.message.chat_id
        state = await self._get_trade_state(chat_id)
        state['direction'] = direction
        await self._set_trade_state(chat_id, state)

        symbol = state.get('symbol', '?')
        dir_emoji = "🟢" if direction == "BUY" else "🔴"

        message = (
            f"<b>🔀 New Trade</b>\n"
            f"{symbol} | {direction} {dir_emoji}\n\n"
            "Select number of lots:"
        )

        keyboard = []
        row = []
        for lots in LOT_CHOICES:
            row.append(InlineKeyboardButton(str(lots), callback_data=f"trade_lots_{lots}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("« Back", callback_data="trade_dir_back")])

        await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # =========================================================================
    # STEP 6: ORDER TYPE
    # =========================================================================

    async def _show_trade_order_type(self, query, lots: int):
        """Show order type selection (Market/Limit)."""
        chat_id = query.message.chat_id
        state = await self._get_trade_state(chat_id)
        state['lots'] = lots
        await self._set_trade_state(chat_id, state)

        symbol = state.get('symbol', '?')
        direction = state.get('direction', '?')

        message = (
            f"<b>🔀 New Trade</b>\n"
            f"{symbol} | {direction} | {lots} lots\n\n"
            "Select order type:"
        )

        keyboard = [
            [
                InlineKeyboardButton("MARKET", callback_data="trade_otype_MARKET"),
                InlineKeyboardButton("LIMIT", callback_data="trade_otype_LIMIT"),
            ],
            [InlineKeyboardButton("« Back", callback_data=f"trade_dir_{state.get('direction', 'BUY')}")],
        ]

        await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # =========================================================================
    # STEP 7: CONFIRMATION SCREEN
    # =========================================================================

    async def _show_trade_confirmation(self, query, order_type: str, limit_price: float = 0):
        """Show order confirmation screen with margin info."""
        chat_id = query.message.chat_id
        state = await self._get_trade_state(chat_id)
        state['order_type'] = order_type
        if limit_price:
            state['limit_price'] = limit_price
        await self._set_trade_state(chat_id, state)

        # Fetch margin info
        margin_info = await self._get_trade_margin_info(state)

        broker = state.get('broker', 'breeze')
        broker_label = 'ICICI Breeze' if broker == 'breeze' else 'Kotak Neo'
        symbol = state.get('symbol', '?')
        inst_type = state.get('inst_type', 'futures')
        expiry = state.get('expiry', '?')
        direction = state.get('direction', '?')
        lots = state.get('lots', 1)
        dir_emoji = "🟢 BUY" if direction == "BUY" else "🔴 SELL"

        opt_info = ''
        if inst_type == 'options':
            opt_info = f" {state.get('option_type', '')} {state.get('strike', '')}"

        order_info = order_type
        if order_type == 'LIMIT' and limit_price:
            order_info = f"LIMIT @ {limit_price:,.2f}"

        margin_req = margin_info.get('margin_required', 0)
        margin_free = margin_info.get('margin_available', 0)
        margin_req_str = f"~{margin_req:,.0f}" if margin_req else "N/A"
        margin_free_str = f"{margin_free:,.0f}" if margin_free else "N/A"

        message = (
            "<b>CONFIRM ORDER</b>\n"
            f"{'=' * 28}\n"
            f"Broker: {broker_label}\n"
            f"<b>{symbol}{opt_info} {inst_type.upper()}</b>\n"
            f"Expiry: {expiry}\n"
            f"Direction: {dir_emoji} | Lots: {lots}\n"
            f"Order: {order_info}\n"
            f"{'=' * 28}\n"
            f"Margin Req: {margin_req_str}\n"
            f"Margin Free: {margin_free_str}\n"
        )

        if margin_req and margin_free and margin_req > margin_free:
            message += "\n⚠️ <b>Insufficient margin!</b>"

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"trade_confirm_{chat_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="trade_cancel"),
            ],
        ]

        await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    @sync_to_async(thread_sensitive=False)
    def _get_trade_margin_info(self, state: dict) -> dict:
        """Get margin requirements and available margin for the trade."""
        from django.db import close_old_connections
        close_old_connections()

        result = {'margin_required': 0, 'margin_available': 0}
        broker = state.get('broker', 'breeze')

        try:
            if broker == 'kotak':
                from tools.neo import NeoAPI
                neo = NeoAPI()
                margin_data = neo.get_margin()
                if margin_data:
                    result['margin_available'] = margin_data.get('available_margin', 0)
            else:
                from apps.trading.services.margin_service import get_available_margin
                try:
                    from apps.brokers.services.breeze_session import get_breeze_client
                    breeze = get_breeze_client()
                    result['margin_available'] = get_available_margin(breeze)
                except Exception:
                    result['margin_available'] = 0

            # Estimate margin required
            try:
                from apps.data.models import ContractData
                symbol = state.get('symbol', '')
                inst_type = state.get('inst_type', 'futures')
                lots = state.get('lots', 1)

                if inst_type == 'futures':
                    contract = ContractData.objects.filter(
                        symbol=symbol, option_type='FUT'
                    ).first()
                else:
                    contract = ContractData.objects.filter(
                        symbol=symbol,
                        option_type=state.get('option_type', 'CE'),
                        strike_price=state.get('strike'),
                        expiry=state.get('expiry'),
                    ).first()

                if contract and contract.price and contract.lot_size:
                    # Rough estimate: ~15% of notional for futures, premium for options
                    if inst_type == 'futures':
                        notional = float(contract.price) * contract.lot_size * lots
                        result['margin_required'] = notional * 0.15
                    else:
                        result['margin_required'] = float(contract.price) * contract.lot_size * lots
            except Exception as e:
                logger.error(f"Margin estimate error: {e}")

        except Exception as e:
            logger.error(f"Error fetching margin info: {e}")

        return result

    # =========================================================================
    # STEP 8: EXECUTION
    # =========================================================================

    async def _execute_trade(self, query, chat_id):
        """Execute the trade from wizard state."""
        state = await self._get_trade_state(int(chat_id))
        if not state:
            await query.edit_message_text("Trade session expired. Please start again with /trade")
            return

        state.get('broker', 'breeze')
        symbol = state.get('symbol', '')
        state.get('inst_type', 'futures')
        state.get('expiry', '')
        direction = state.get('direction', 'BUY')
        lots = state.get('lots', 1)
        order_type = state.get('order_type', 'MARKET')
        state.get('limit_price', 0)

        await query.edit_message_text(
            f"<b>⏳ Placing order...</b>\n"
            f"{symbol} {direction} {lots} lots",
            parse_mode='HTML'
        )

        result = await self._place_trade_order(state)

        # Clear wizard state
        await self._clear_trade_state(int(chat_id))

        if result.get('success'):
            order_id = result.get('order_id', 'N/A')
            message = (
                f"<b>✅ Order Placed</b>\n\n"
                f"Symbol: {symbol}\n"
                f"Direction: {direction}\n"
                f"Lots: {lots}\n"
                f"Order Type: {order_type}\n"
                f"Order ID: <code>{order_id}</code>\n"
                f"Status: {result.get('status', 'SUBMITTED')}"
            )
        else:
            message = (
                f"<b>❌ Order Failed</b>\n\n"
                f"Symbol: {symbol}\n"
                f"Error: {result.get('error', 'Unknown error')[:300]}"
            )

        keyboard = [
            [
                InlineKeyboardButton("🔀 New Trade", callback_data="menu_trade"),
                InlineKeyboardButton("« Main Menu", callback_data="back_main"),
            ],
        ]

        await query.edit_message_text(message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    @sync_to_async(thread_sensitive=False)
    def _place_trade_order(self, state: dict) -> dict:
        """Place the actual order with the broker."""
        from django.db import close_old_connections
        close_old_connections()

        broker = state.get('broker', 'breeze')
        state.get('symbol', '')
        state.get('inst_type', 'futures')
        state.get('expiry', '')
        state.get('direction', 'BUY')
        state.get('lots', 1)
        state.get('order_type', 'MARKET')
        state.get('limit_price', 0)

        try:
            if broker == 'kotak':
                return self._place_kotak_order(state)
            else:
                return self._place_breeze_order(state)
        except Exception as e:
            logger.error(f"Order placement error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _place_kotak_order(self, state: dict) -> dict:
        """Place order via Kotak Neo API."""
        from tools.neo import NeoAPI

        symbol = state.get('symbol', '')
        inst_type = state.get('inst_type', 'futures')
        expiry = state.get('expiry', '')
        direction = state.get('direction', 'BUY')
        lots = state.get('lots', 1)
        order_type = state.get('order_type', 'MARKET')
        limit_price = state.get('limit_price', 0)

        neo = NeoAPI()

        # Get lot size
        from apps.data.models import ContractData
        if inst_type == 'futures':
            contract = ContractData.objects.filter(
                symbol=symbol, option_type='FUT', expiry=expiry
            ).first()
        else:
            contract = ContractData.objects.filter(
                symbol=symbol,
                option_type=state.get('option_type', 'CE'),
                strike_price=state.get('strike'),
                expiry=expiry,
            ).first()

        lot_size = contract.lot_size if contract else 25
        quantity = lot_size * lots

        # Map direction
        action = 'B' if direction == 'BUY' else 'S'
        neo_order_type = 'MKT' if order_type == 'MARKET' else 'L'
        price = limit_price if order_type == 'LIMIT' else 0

        order_id = neo.place_order(
            symbol=symbol,
            action=action,
            quantity=quantity,
            order_type=neo_order_type,
            price=price,
        )

        if order_id:
            return {'success': True, 'order_id': order_id, 'status': 'SUBMITTED'}
        else:
            return {'success': False, 'error': 'Order rejected by Kotak Neo'}

    def _place_breeze_order(self, state: dict) -> dict:
        """Place order via ICICI Breeze API."""
        from apps.brokers.services.breeze_session import get_breeze_client

        symbol = state.get('symbol', '')
        inst_type = state.get('inst_type', 'futures')
        expiry = state.get('expiry', '')
        direction = state.get('direction', 'BUY')
        lots = state.get('lots', 1)
        order_type = state.get('order_type', 'MARKET')
        limit_price = state.get('limit_price', 0)

        breeze = get_breeze_client()
        if not breeze:
            return {'success': False, 'error': 'Breeze session not available'}

        from apps.brokers.integrations.breeze import (
            place_futures_order_with_security_master,
            place_option_order_with_security_master,
        )

        breeze_action = 'buy' if direction == 'BUY' else 'sell'
        breeze_order_type = 'market' if order_type == 'MARKET' else 'limit'

        if inst_type == 'futures':
            result = place_futures_order_with_security_master(
                symbol=symbol,
                expiry_date=expiry,
                action=breeze_action,
                lots=lots,
                order_type=breeze_order_type,
                price=limit_price if order_type == 'LIMIT' else 0.0,
            )
        else:
            strike = state.get('strike', 0)
            option_type = state.get('option_type', 'CE')
            try:
                strike_float = float(strike)
            except (ValueError, TypeError):
                strike_float = 0.0

            result = place_option_order_with_security_master(
                symbol=symbol,
                expiry_date=expiry,
                strike_price=strike_float,
                option_type=option_type,
                action=breeze_action,
                lots=lots,
                order_type=breeze_order_type,
                price=limit_price if order_type == 'LIMIT' else 0.0,
            )

        if result and result.get('Status') == 200:
            order_id = ''
            if result.get('Success'):
                order_id = result['Success'].get('order_id', '')
            return {'success': True, 'order_id': order_id, 'status': 'SUBMITTED'}
        else:
            error = str(result)[:300] if result else 'No response from Breeze'
            return {'success': False, 'error': error}

    # =========================================================================
    # TRADE WIZARD CALLBACK ROUTER
    # =========================================================================

    async def _route_trade_callback(self, query, data: str):
        """Route trade_* callbacks through the wizard steps."""
        chat_id = query.message.chat_id

        if data == "trade_cancel":
            await self._clear_trade_state(chat_id)
            await self._show_main_menu(query)
            return

        # Step 1: Broker selection
        if data.startswith("trade_broker_"):
            broker = data.replace("trade_broker_", "")
            await self._show_trade_type_selection(query, broker)

        # Step 2: Instrument type
        elif data.startswith("trade_type_"):
            parts = data.replace("trade_type_", "").split("_", 1)
            broker = parts[0]
            inst_type = parts[1] if len(parts) > 1 else 'futures'
            await self._show_trade_symbol_grid(query, broker, inst_type)

        # Step 3: Symbol selection
        elif data == "trade_sym_more":
            await self._show_trade_more_symbols(query)
        elif data.startswith("trade_sym_"):
            symbol = data.replace("trade_sym_", "")
            await self._show_trade_expiry_selection(query, symbol)

        # Step 4: Expiry selection
        elif data.startswith("trade_exp_"):
            expiry = data.replace("trade_exp_", "")
            await self._show_trade_option_type(query, expiry)

        # Step 4b: Option type (CE/PE)
        elif data.startswith("trade_opttype_"):
            option_type = data.replace("trade_opttype_", "")
            await self._show_trade_strike_selection(query, option_type)

        # Step 4c: Strike selection
        elif data.startswith("trade_strike_"):
            strike = data.replace("trade_strike_", "")
            state = await self._get_trade_state(chat_id)
            state['strike'] = strike
            await self._set_trade_state(chat_id, state)
            await self._show_trade_direction(query)

        # Step 5: Direction
        elif data == "trade_dir_back":
            await self._show_trade_direction(query)
        elif data.startswith("trade_dir_"):
            direction = data.replace("trade_dir_", "")
            if direction in ("BUY", "SELL"):
                await self._show_trade_lots(query, direction)

        # Step 5b: Lots
        elif data.startswith("trade_lots_"):
            lots = int(data.replace("trade_lots_", ""))
            await self._show_trade_order_type(query, lots)

        # Step 6: Order type
        elif data.startswith("trade_otype_"):
            order_type = data.replace("trade_otype_", "")
            if order_type == "LIMIT":
                # For limit orders, we'll set a waiting state and use MARKET for now
                # TODO: Implement text input handler for limit price
                await self._show_trade_confirmation(query, 'LIMIT', 0)
            else:
                await self._show_trade_confirmation(query, order_type)

        # Step 7: Confirm/Execute
        elif data.startswith("trade_confirm_"):
            target_chat_id = data.replace("trade_confirm_", "")
            await self._execute_trade(query, target_chat_id)

    # =========================================================================
    # LIMIT PRICE TEXT HANDLER
    # =========================================================================

    async def _handle_trade_text_input(self, update, text: str) -> bool:
        """Handle text input during trade wizard (for limit prices).

        Returns True if the text was consumed by the wizard, False otherwise.
        """
        chat_id = update.effective_chat.id
        state = await self._get_trade_state(chat_id)

        if not state or state.get('order_type') != 'LIMIT' or state.get('limit_price') is not None:
            return False

        try:
            price = float(text.replace(',', ''))
            state['limit_price'] = price
            await self._set_trade_state(chat_id, state)
            # Re-show confirmation with the price
            # We need to send a new message since this is from text input
            message = await self._build_confirmation_message(state, price)
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm", callback_data=f"trade_confirm_{chat_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="trade_cancel"),
                ],
            ]
            await update.message.reply_text(
                message, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return True
        except ValueError:
            return False

    async def _build_confirmation_message(self, state: dict, limit_price: float) -> str:
        """Build confirmation message text."""
        broker = state.get('broker', 'breeze')
        broker_label = 'ICICI Breeze' if broker == 'breeze' else 'Kotak Neo'
        symbol = state.get('symbol', '?')
        inst_type = state.get('inst_type', 'futures')
        expiry = state.get('expiry', '?')
        direction = state.get('direction', '?')
        lots = state.get('lots', 1)
        dir_emoji = "🟢 BUY" if direction == "BUY" else "🔴 SELL"

        opt_info = ''
        if inst_type == 'options':
            opt_info = f" {state.get('option_type', '')} {state.get('strike', '')}"

        return (
            "<b>CONFIRM ORDER</b>\n"
            f"{'=' * 28}\n"
            f"Broker: {broker_label}\n"
            f"<b>{symbol}{opt_info} {inst_type.upper()}</b>\n"
            f"Expiry: {expiry}\n"
            f"Direction: {dir_emoji} | Lots: {lots}\n"
            f"Order: LIMIT @ {limit_price:,.2f}\n"
        )
