"""
Trade Confirmation Service

Orchestrates Telegram-based confirmation flow for trades.
This is a thin wrapper around existing services - does NOT implement
new broker APIs or order placement logic.

Uses:
- TelegramClient for sending confirmation messages
- margin_service for margin calculations
- position_service for position sizing
- Existing approve_trade/reject_trade handlers

Flow:
1. Algorithm generates suggestion -> save to TradeSuggestion
2. TradeConfirmationService.request_confirmation() -> sends Telegram message with buttons
3. User clicks button -> telegram_bot.py callback handler
4. Handler calls approve_trade() or reject_trade() from trade_approval_handler.py
"""

import logging
from decimal import Decimal
from typing import Dict, List, Tuple
from datetime import datetime
from django.utils import timezone

from apps.alerts.services.notification_payload import NotificationPayload
from apps.alerts.services.notification_formatter import format_notification
from apps.alerts.services.notification_service import notify

logger = logging.getLogger(__name__)


class TradeConfirmationService:
    """
    Orchestrates Telegram-based confirmation flow for trades.

    This service is a thin wrapper around existing functionality:
    - Uses TelegramClient for sending messages
    - Uses margin_service for margin calculations
    - Delegates actual order execution to existing handlers
    """

    def __init__(self):
        """Initialize with Telegram client."""
        from apps.alerts.services.telegram_client import get_telegram_client
        self.telegram = get_telegram_client()

    def request_options_confirmation(
        self,
        suggestion,
        config=None
    ) -> Tuple[bool, str]:
        """
        Send options trade for user confirmation via Telegram.

        Args:
            suggestion: TradeSuggestion instance with options trade details
            config: TradingCoreConfig instance (fetched if not provided)

        Returns:
            Tuple[bool, str]: (success, message_id or error)
        """
        if not config:
            from apps.core.models import TradingCoreConfig
            config = TradingCoreConfig.get_instance()

        strategy = suggestion.get_strategy_display()
        call_strike = suggestion.call_strike or 0
        put_strike = suggestion.put_strike or 0
        total_premium = suggestion.total_premium or 0
        lots = suggestion.recommended_lots or config.options_lots

        # Expiry context
        context_lines = []
        if suggestion.expiry_date:
            from datetime import date
            days_to_exp = (suggestion.expiry_date - date.today()).days
            expiry_fmt = suggestion.expiry_date.strftime('%d-%b-%Y')
            context_lines.append(f"Expiry: {expiry_fmt} ({days_to_exp}d)")

            # Check if expiry was changed
            details = suggestion.position_details or {}
            if details.get('expiry_changed'):
                original = details.get('original_expiry', '')
                context_lines.append(f"Expiry changed from: {original}")

        margin = suggestion.margin_required or 0
        max_loss = suggestion.max_loss or 0
        rr = suggestion.risk_reward_ratio or 0
        timeout = config.confirmation_timeout_minutes

        context_lines.extend([
            f'Max Loss: ₹{max_loss:,.0f}',
            f'R:R Ratio: {rr:.2f}',
            f'Auto-expires in {timeout} min',
        ])

        # Build inline keyboard rows
        keyboard_rows = [
            [
                {'text': f'✅ Confirm ({lots} lots)', 'callback_data': f'confirm_options_{suggestion.id}'},
            ],
            [
                {'text': '📊 Change Size', 'callback_data': f'resize_options_{suggestion.id}'},
                {'text': '📅 Change Expiry', 'callback_data': f'expiry_options_{suggestion.id}'},
            ],
            [
                {'text': '❌ Reject', 'callback_data': f'reject_options_{suggestion.id}'},
            ],
        ]

        payload = NotificationPayload(
            title='Options Trade Confirmation',
            status='ACTION_REQUIRED',
            instrument=suggestion.instrument,
            metrics={
                'Strategy': strategy,
                'Lots': str(lots),
                'Premium': f'₹{total_premium:,.0f}',
            },
            position={
                'Call Strike': str(call_strike),
                'Put Strike': str(put_strike),
                'Margin': f'₹{margin:,.0f}',
            },
            context=context_lines,
            keyboard=keyboard_rows,
            collapsible=True,
        )

        message = format_notification(payload)
        keyboard_dict = {'inline_keyboard': payload.keyboard}
        success, result = self._send_with_keyboard(message, keyboard_dict)

        if success:
            # Update suggestion with confirmation tracking
            suggestion.status = 'PENDING_CONFIRMATION'
            suggestion.confirmation_requested_at = timezone.now()
            suggestion.telegram_message_id = result
            suggestion.confirmation_timeout_minutes = config.confirmation_timeout_minutes
            suggestion.save()

            logger.info(f"Options confirmation request sent for suggestion {suggestion.id}")

        return success, result

    def request_futures_confirmation(
        self,
        suggestions: List,
        breeze=None
    ) -> Tuple[bool, str]:
        """
        Send TOP 3 futures suggestions for user selection (Step 1 of 2-step approval).

        TWO-STEP APPROVAL FLOW:
        1. SELECTION: User sees list and clicks "View Details" for one
        2. CONFIRMATION: User sees full details and clicks "Confirm Trade"
        3. EXECUTION: Background thread executes the trade with batching

        Args:
            suggestions: List of TradeSuggestion instances (top 3)
            breeze: Breeze client instance for margin calculations

        Returns:
            Tuple[bool, str]: (success, message_id or error)
        """
        from apps.trading.services.margin_service import get_available_margin
        from apps.core.models import TradingCoreConfig, NseFlag

        config = TradingCoreConfig.get_instance()

        # Get available margin
        available = get_available_margin(breeze) if breeze else 5000000

        # Store suggestion IDs for "back to list" functionality
        suggestion_ids = [s.id for s in suggestions[:3]]
        NseFlag.set('pending_futures_suggestions', ','.join(map(str, suggestion_ids)))

        # =====================================================================
        # STEP 1: SELECTION SCREEN - Show summary with "View Details" buttons
        # =====================================================================
        timeout = config.confirmation_timeout_minutes

        # Build compact per-suggestion context lines
        context_lines = ['Select a trade to view details:']
        for i, suggestion in enumerate(suggestions[:3], 1):
            symbol = suggestion.instrument
            direction = suggestion.direction
            det = suggestion.position_details or {}
            score = det.get('composite_score', 0)
            rr = suggestion.risk_reward_ratio or det.get('risk_reward_ratio', 0) or 0
            regime_label = det.get('regime', '')

            direction_emoji = "🟢" if direction == "LONG" else "🔴"
            rr_str = f" | R:R 1:{float(rr):.1f}" if rr else ""
            regime_str = f" | {regime_label}" if regime_label else ""

            context_lines.append(
                f"{i}. {symbol} {direction_emoji} {direction} — Score: {score}/100{rr_str}{regime_str}"
            )

        # Build keyboard with "View Details" button for each
        keyboard_rows = []
        for suggestion in suggestions[:3]:
            keyboard_rows.append([
                {'text': f'📊 View {suggestion.instrument}', 'callback_data': f'select_futures_{suggestion.id}'},
            ])

        keyboard_rows.append([
            {'text': '❌ Skip All', 'callback_data': 'futures_skip_all'},
        ])

        payload = NotificationPayload(
            title='Futures Opportunities',
            status='ACTION_REQUIRED',
            metrics={
                'Margin Available': f'₹{available:,.0f}',
                'Expires': f'{timeout} min',
            },
            context=context_lines,
            keyboard=keyboard_rows,
            collapsible=True,
        )

        message = format_notification(payload)
        keyboard_dict = {'inline_keyboard': payload.keyboard}
        success, result = self._send_with_keyboard(message, keyboard_dict)

        if success:
            # Update all suggestions with confirmation tracking
            for suggestion in suggestions[:3]:
                suggestion.status = 'PENDING_CONFIRMATION'
                suggestion.confirmation_requested_at = timezone.now()
                suggestion.telegram_message_id = result
                suggestion.confirmation_timeout_minutes = config.confirmation_timeout_minutes
                suggestion.save()

            logger.info(f"Futures selection screen sent for {len(suggestions[:3])} suggestions")

        return success, result

    def build_futures_detail_message(self, suggestion) -> Tuple[str, Dict]:
        """
        Build the detailed confirmation message for Step 2 of approval.

        Args:
            suggestion: TradeSuggestion instance

        Returns:
            Tuple[str, Dict]: (message_text, keyboard_dict)
        """
        from apps.core.models import TradingCoreConfig

        TradingCoreConfig.get_instance()

        symbol = suggestion.instrument
        direction = suggestion.direction
        details = suggestion.position_details or {}

        # Extract all details
        score = details.get('composite_score', 0)
        entry_price = details.get('entry_price', 0)
        stop_loss = details.get('stop_loss', 0)
        target = details.get('target', 0)
        lot_size = details.get('lot_size', 0)
        margin_per_lot = suggestion.margin_per_lot or details.get('margin_per_lot', 0)
        recommended_lots = suggestion.recommended_lots or 1

        # Calculate risk:reward
        if direction == 'LONG' and entry_price and stop_loss and target:
            risk = entry_price - stop_loss
            reward = target - entry_price
            rr_ratio = reward / risk if risk > 0 else 0
            risk_amount = risk * lot_size * recommended_lots
            reward_amount = reward * lot_size * recommended_lots
        elif direction == 'SHORT' and entry_price and stop_loss and target:
            risk = stop_loss - entry_price
            reward = entry_price - target
            rr_ratio = reward / risk if risk > 0 else 0
            risk_amount = risk * lot_size * recommended_lots
            reward_amount = reward * lot_size * recommended_lots
        else:
            rr_ratio = suggestion.risk_reward_ratio or 0
            risk_amount = 0
            reward_amount = 0

        # Get algorithm reasoning components
        reasoning = details.get('algorithm_reasoning', {})
        oi_signal = reasoning.get('oi_analysis', {}).get('signal', 'N/A')
        dma_signal = reasoning.get('dma_analysis', {}).get('signal', 'N/A')
        sector_signal = reasoning.get('sector_analysis', {}).get('signal', 'N/A')

        direction_emoji = "🟢" if direction == "LONG" else "🔴"

        # Check for news warning from analysis details
        news_warning = details.get('news_warning', '')

        # Extract expiry info
        expiry_date_str = details.get('expiry_date', '')
        expiry_changed = details.get('expiry_changed', False)
        original_expiry = details.get('original_expiry', '')
        regime = details.get('regime', '')

        expiry_display = ''
        days_to_exp = 0
        if expiry_date_str:
            try:
                from datetime import date
                expiry_dt = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                days_to_exp = (expiry_dt - date.today()).days
                expiry_display = f"{expiry_dt.strftime('%d-%b')} ({days_to_exp}d)"
            except (ValueError, TypeError):
                expiry_display = expiry_date_str

        # SL/Target % from entry
        sl_pct = abs(entry_price - stop_loss) / entry_price * 100 if entry_price > 0 else 0
        tgt_pct = abs(target - entry_price) / entry_price * 100 if entry_price > 0 else 0
        sl_sign = "-" if direction == 'LONG' else "+"
        tgt_sign = "+" if direction == 'LONG' else "-"

        # Compact margin display
        total_margin = margin_per_lot * recommended_lots
        margin_compact = f"₹{total_margin / 100000:.2f}L" if total_margin >= 100000 else f"₹{total_margin:,.0f}"

        # Build hybrid format message — compact headline + labeled sections
        message = f"{direction_emoji} <b>{symbol} {direction}</b> | {score}/100\n"

        regime_str = f"{regime} | " if regime else ""
        message += f"{regime_str}R:R 1:{rr_ratio:.1f}"
        if expiry_display:
            message += f" | Expiry {expiry_display}"
        message += "\n"

        if news_warning:
            message += f"⚠️ {news_warning}\n"

        if expiry_changed:
            message += f"⚠️ <i>Expiry changed from {original_expiry}</i>\n"

        message += (
            f"\n📍 <b>Price Levels</b>\n"
            f"  Entry: ₹{entry_price:,.2f} | "
            f"SL: ₹{stop_loss:,.2f} ({sl_sign}{sl_pct:.1f}%) | "
            f"Target: ₹{target:,.2f} ({tgt_sign}{tgt_pct:.1f}%)\n"

            f"\n📐 <b>Position</b>\n"
            f"  {recommended_lots} lots × {lot_size} | Margin: {margin_compact}\n"

            f"\n⚖️ <b>Risk / Reward</b>\n"
            f"  Risk: ₹{risk_amount:,.0f} | Reward: ₹{reward_amount:,.0f}\n"

            f"\n🔬 <b>Signals</b>\n"
            f"  OI: {oi_signal} | DMA: {dma_signal} | Sector: {sector_signal}"
        )

        # Build keyboard for Step 2 — compact labels
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': f'✅ Confirm ({margin_compact})', 'callback_data': f'confirm_futures_{suggestion.id}'},
                    {'text': '📊 Lots', 'callback_data': f'resize_futures_{suggestion.id}'},
                ],
                [
                    {'text': '📅 Expiry', 'callback_data': f'expiry_futures_{suggestion.id}'},
                    {'text': '◀️ Back', 'callback_data': 'back_futures_list'},
                    {'text': '❌ Skip', 'callback_data': f'reject_futures_{suggestion.id}'},
                ],
            ]
        }

        return message, keyboard

    def request_exit_confirmation(
        self,
        position,
        reason: str,
        current_pnl: Decimal = None
    ) -> Tuple[bool, str]:
        """
        Send exit suggestion for user confirmation (Manual mode).

        Uses NotificationPayload + TelegramMessageFormatter for a structured,
        mobile-optimised message that puts the most critical info (P&L, price,
        trigger) at the top and full context in the expandable details section.

        Returns:
            Tuple[bool, str]: (success, message_id or error)
        """
        from django.utils import timezone

        now = timezone.now()
        pnl = current_pnl if current_pnl is not None else (position.unrealized_pnl or Decimal('0'))

        # P&L % — entry_value may be 0 for broker-synced positions; derive it
        entry_val = position.entry_value if (position.entry_value and position.entry_value > 0) else (
            position.entry_price * position.quantity
        )
        pnl_pct = (pnl / entry_val * Decimal('100')) if entry_val > 0 else Decimal('0')

        pnl_sign = "+" if pnl >= 0 else ""
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        if pnl < 0:
            pnl_display = f"{pnl_emoji} -₹{abs(pnl):,.0f} ({pnl_pct:.1f}%)"
        else:
            pnl_display = f"{pnl_emoji} +₹{abs(pnl):,.0f} ({pnl_sign}{pnl_pct:.1f}%)"

        # Lot / size display
        lot_size = position.lot_size or 1
        lots = position.quantity // lot_size if lot_size > 1 else position.quantity
        lots_str = f"{lots} lot{'s' if lots != 1 else ''}"

        # Broker label
        broker_map = {'KOTAK': 'Kotak Neo', 'ICICI': 'ICICI Breeze'}
        broker_name = broker_map.get(
            position.account.broker if position.account else '',
            position.account.broker if position.account else 'Unknown'
        )

        # Reason → status + title mapping
        _REASON_MAP = {
            'STOP_LOSS':       ('ACTION_REQUIRED', 'Stop-Loss Hit'),
            'STOP_LOSS_HIT':   ('ACTION_REQUIRED', 'Stop-Loss Hit'),
            'SL_HIT':          ('ACTION_REQUIRED', 'Stop-Loss Hit'),
            'STRUCTURAL_SL':   ('ACTION_REQUIRED', 'Structural SL Triggered'),
            'SR_BREAKDOWN':    ('ACTION_REQUIRED', 'S/R Breakdown Exit'),
            'TARGET':          ('ACTION_REQUIRED', 'Target Hit'),
            'TARGET_HIT':      ('ACTION_REQUIRED', 'Target Hit'),
            'EOD':             ('ACTION_REQUIRED', 'End-of-Day Exit'),
            'EOD_THURSDAY':    ('ACTION_REQUIRED', 'EOD Thursday Exit'),
            'FRIDAY_EOD':      ('ACTION_REQUIRED', 'Friday EOD Exit'),
            'EXPIRY_DAY':      ('ACTION_REQUIRED', 'Expiry Day Exit'),
            'NEAR_SL_REQUEST': ('WARNING',         'Near Stop-Loss — Exit?'),
            'MANUAL':          ('ACTION_REQUIRED', 'Manual Exit Request'),
        }
        status, title = _REASON_MAP.get(reason, ('ACTION_REQUIRED', 'Exit Suggestion'))

        # Price context
        price_diff = position.current_price - position.entry_price
        diff_sign = "+" if price_diff >= 0 else ""
        price_move = f"{diff_sign}₹{price_diff:,.2f}/unit"

        # SL / Target display strings
        sl_str = "—"
        tgt_str = "—"
        context_bullets = []
        if position.stop_loss:
            sl_dist = position.current_price - position.stop_loss
            sl_flag = " ✓ triggered" if position.is_stop_loss_hit() else f" ({sl_dist:+,.2f} away)"
            sl_str = f"₹{position.stop_loss:,.2f}{sl_flag}"
        if position.target:
            tgt_dist = position.target - position.current_price
            tgt_flag = " ✓ triggered" if position.is_target_hit() else f" ({tgt_dist:+,.2f} away)"
            tgt_str = f"₹{position.target:,.2f}{tgt_flag}"
            # Also show % upside from entry for targets
            if position.entry_price > 0:
                tgt_pct = abs(float(position.target) - float(position.entry_price)) / float(position.entry_price) * 100
                tgt_str += f"  ({tgt_pct:.1f}%)"

        context_bullets.append(f"Trigger: {title}")
        context_bullets.append("System will NOT auto-execute in manual mode")

        # Config mode tag
        mode_label = sizing_label = None
        try:
            from apps.core.models import TradingCoreConfig
            config = TradingCoreConfig.get_instance()
            mode_label = config.get_notification_level_display_short()
            sizing_label = config.get_position_sizing_display_short()
        except Exception:
            pass

        payload = NotificationPayload(
            title=title,
            status=status,
            instrument=position.instrument,
            strategy=broker_name,
            task='monitor_and_manage_positions',
            timestamp=now,
            metrics={
                'P&L': pnl_display,
                'Move': price_move,
                'Entry': f"₹{position.entry_price:,.2f}",
                'Now': f"₹{position.current_price:,.2f}",
            },
            keyboard=[[
                {'text': '✅ Close Now',   'callback_data': f'confirm_exit_{position.id}'},
                {'text': '⏸ Hold / Wait', 'callback_data': f'hold_exit_{position.id}'},
            ]],
            position={
                'Direction': f"{position.direction}  ·  {lots_str}",
                'Entry': f"₹{position.entry_price:,.2f}",
                'Current': f"₹{position.current_price:,.2f}  ({price_move})",
                'SL': sl_str,
                'Target': tgt_str,
            },
            context=context_bullets,
            system={
                'Position ID': f"#{position.id}",
                'Account': broker_name,
            },
            priority='CRITICAL' if status == 'ACTION_REQUIRED' else 'WARNING',
            dedup_key=f'exit_suggestion_{position.id}',
            mode_label=mode_label,
            sizing_label=sizing_label,
        )

        message = format_notification(payload)
        keyboard_dict = {'inline_keyboard': payload.keyboard}
        return self._send_with_keyboard(message, keyboard_dict)

    def _ist_time_str(self) -> str:
        """Return current time as HH:MM IST string."""
        try:
            import pytz
            from django.utils import timezone as tz
            ist = pytz.timezone('Asia/Kolkata')
            return tz.now().astimezone(ist).strftime('%H:%M')
        except Exception:
            from django.utils import timezone as tz
            return tz.now().strftime('%H:%M')

    def request_averaging_confirmation(
        self,
        position,
        recommended_lots: int,
        averaging_preview: Dict = None
    ) -> Tuple[bool, str]:
        """
        Send averaging recommendation for confirmation.

        Args:
            position: Position model instance
            recommended_lots: Recommended number of lots to add
            averaging_preview: Preview calculations (new avg, SL, etc.)

        Returns:
            Tuple[bool, str]: (success, message_id or error)
        """
        current_pnl = position.unrealized_pnl or Decimal('0')
        pnl_str = f"+₹{current_pnl:,.0f}" if current_pnl >= 0 else f"-₹{abs(current_pnl):,.0f}"

        # Build position details with averaging preview
        position_details = {
            'Direction': position.direction,
            'Position ID': f'#{position.id}',
        }
        context_lines = []

        if averaging_preview:
            position_details.update({
                'New Avg Entry': f"₹{averaging_preview.get('new_average_entry', 0):,.0f}",
                'New Stop-Loss': f"₹{averaging_preview.get('new_stop_loss', 0):,.0f}",
                'Additional Margin': f"₹{averaging_preview.get('additional_margin', 0):,.0f}",
            })
            context_lines.append(f'Preview for adding {recommended_lots} lots')

        context_lines.append('Confirm to add to position')

        keyboard_rows = [
            [
                {'text': f'✅ Add {recommended_lots} lots', 'callback_data': f'confirm_avg_{position.id}_{recommended_lots}'},
            ],
            [
                {'text': '1 lot', 'callback_data': f'confirm_avg_{position.id}_1'},
                {'text': '2 lots', 'callback_data': f'confirm_avg_{position.id}_2'},
                {'text': '5 lots', 'callback_data': f'confirm_avg_{position.id}_5'},
            ],
            [
                {'text': '❌ Skip', 'callback_data': f'skip_avg_{position.id}'},
            ],
        ]

        payload = NotificationPayload(
            title='Averaging Recommendation',
            status='ACTION_REQUIRED',
            instrument=position.instrument,
            metrics={
                'P&L': pnl_str,
                'Current': f'₹{position.current_price:,.0f}',
            },
            position=position_details,
            context=context_lines,
            keyboard=keyboard_rows,
            collapsible=True,
        )

        message = format_notification(payload)
        keyboard_dict = {'inline_keyboard': payload.keyboard}
        return self._send_with_keyboard(message, keyboard_dict)

    def revalidate_after_timeout(self, suggestion) -> Tuple[bool, str]:
        """
        Called after confirmation timeout.

        Re-checks if position is still valid (prices, movement, etc.)
        and sends updated message.

        Args:
            suggestion: TradeSuggestion that timed out

        Returns:
            Tuple[bool, str]: (success, message or error)
        """
        if suggestion.suggestion_type == 'OPTIONS':
            return self._revalidate_options(suggestion)
        elif suggestion.suggestion_type == 'FUTURES':
            return self._revalidate_futures(suggestion)
        else:
            return False, f"Unknown suggestion type: {suggestion.suggestion_type}"

    def _revalidate_options(self, suggestion) -> Tuple[bool, str]:
        """Revalidate options suggestion after timeout."""
        from apps.core.models import TradingCoreConfig

        config = TradingCoreConfig.get_instance()

        # Check if market conditions still valid
        # For now, simple revalidation - in production would recalculate strikes
        is_valid = True
        reason = ""

        # Check movement threshold
        try:
            movement = self._calculate_current_movement()
            if abs(movement) > float(config.movement_threshold):
                is_valid = False
                reason = f"Market moved {movement:.2f}% since open (threshold: {config.movement_threshold}%)"
        except Exception as e:
            logger.warning(f"Could not check movement: {e}")

        if is_valid:
            keyboard_rows = [[
                {'text': '✅ Confirm Now', 'callback_data': f'confirm_options_{suggestion.id}'},
                {'text': '❌ Cancel', 'callback_data': f'reject_options_{suggestion.id}'},
            ]]

            payload = NotificationPayload(
                title='Timeout - Revalidated',
                status='ACTION_REQUIRED',
                context=['Position still valid — original parameters apply.', 'Confirm to proceed?'],
                keyboard=keyboard_rows,
                collapsible=False,
            )

            message = format_notification(payload)
            keyboard_dict = {'inline_keyboard': payload.keyboard}
        else:
            payload = NotificationPayload(
                title='Timeout - Expired',
                status='WARNING',
                context=[reason, 'Will try again tomorrow.'],
            )

            message = format_notification(payload)
            keyboard_dict = None

            # Mark as expired
            suggestion.status = 'EXPIRED'
            suggestion.user_notes = f"Revalidation failed: {reason}"
            suggestion.save()

        suggestion.revalidation_sent = True
        suggestion.save()

        if keyboard_dict:
            return self._send_with_keyboard(message, keyboard_dict)
        else:
            return self.telegram.send_message(message)

    def _revalidate_futures(self, suggestion) -> Tuple[bool, str]:
        """Revalidate futures suggestion after timeout."""
        # For futures, check if score is still above threshold
        current_score = suggestion.position_details.get('composite_score', 0) if suggestion.position_details else 0

        # Consider still valid if score >= 60
        is_valid = current_score >= 60

        if is_valid:
            keyboard_rows = [[
                {'text': '✅ Confirm', 'callback_data': f'confirm_futures_{suggestion.id}'},
                {'text': '❌ Skip', 'callback_data': f'reject_futures_{suggestion.id}'},
            ]]

            payload = NotificationPayload(
                title='Timeout - Still Valid',
                status='ACTION_REQUIRED',
                instrument=suggestion.instrument,
                metrics={'Score': f'{current_score}/100'},
                context=['Opportunity still available. Confirm to proceed?'],
                keyboard=keyboard_rows,
                collapsible=False,
            )

            message = format_notification(payload)
            keyboard_dict = {'inline_keyboard': payload.keyboard}
        else:
            payload = NotificationPayload(
                title='Timeout - Expired',
                status='WARNING',
                instrument=suggestion.instrument,
                metrics={'Score': f'{current_score}/100'},
                context=['Opportunity no longer meets criteria.'],
            )

            message = format_notification(payload)
            keyboard_dict = None

            suggestion.status = 'EXPIRED'
            suggestion.user_notes = f"Revalidation: Score dropped to {current_score}"
            suggestion.save()

        suggestion.revalidation_sent = True
        suggestion.save()

        if keyboard_dict:
            return self._send_with_keyboard(message, keyboard_dict)
        else:
            return self.telegram.send_message(message)

    def _send_with_keyboard(
        self,
        message: str,
        keyboard: Dict
    ) -> Tuple[bool, str]:
        """
        Send message with inline keyboard via Telegram API.

        Args:
            message: Message text
            keyboard: Inline keyboard dictionary

        Returns:
            Tuple[bool, str]: (success, message_id or error)
        """
        import requests
        import os

        bot_token = self.telegram.bot_token if self.telegram.enabled else os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = self.telegram.default_chat_id if self.telegram.enabled else os.getenv('TELEGRAM_CHAT_ID')

        if not bot_token or not chat_id:
            return False, "Telegram not configured"

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'reply_markup': keyboard,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                result = response.json()
                message_id = result.get('result', {}).get('message_id', '')
                return True, str(message_id)
            else:
                error = f"Telegram API error: {response.status_code} - {response.text}"
                logger.error(error)
                return False, error

        except Exception as e:
            error = f"Error sending Telegram message: {e}"
            logger.error(error)
            return False, error

    def _calculate_current_movement(self) -> float:
        """
        Calculate NIFTY % movement from 9:15 open to current.

        Returns:
            float: Movement percentage (e.g., 0.5 for +0.5%)
        """
        try:
            from apps.data.models import ContractStockData

            nifty = ContractStockData.objects.filter(symbol='NIFTY').first()
            if not nifty:
                return 0.0

            day_open = float(nifty.day_open) if nifty.day_open else 0
            current = float(nifty.close_price) if nifty.close_price else 0

            if day_open <= 0:
                return 0.0

            movement = ((current - day_open) / day_open) * 100
            return movement

        except Exception as e:
            logger.warning(f"Error calculating movement: {e}")
            return 0.0

    # =========================================================================
    # TRADE EXECUTION METHODS (Called from Telegram bot callbacks)
    # =========================================================================

    def execute_options_trade(self, suggestion, lots: int = None, paper_account=None) -> Dict:
        """
        Execute options trade after confirmation.

        Uses existing strategy entry functions (execute_kotak_strangle_entry, etc.)

        Args:
            suggestion: TradeSuggestion instance
            lots: Custom lot count (uses suggestion.recommended_lots if None)

        Returns:
            Dict with success status and order details
        """
        try:
            from apps.accounts.models import BrokerAccount

            # Determine strategy type
            strategy = suggestion.strategy_type

            # Get lot count
            final_lots = lots or suggestion.user_modified_lots or suggestion.recommended_lots or 1

            # Use paper account if provided, else get live Kotak account
            if paper_account and paper_account.is_paper_trading:
                account = paper_account
            else:
                account = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()
            if not account:
                return {'success': False, 'error': 'No active Kotak account found'}

            # Paper trading — simulate options entry via PaperBroker
            if account.is_paper_trading:
                return self._execute_paper_options_trade(
                    suggestion, account, strategy, final_lots,
                )

            # Execute based on strategy type
            if strategy == 'STRANGLE' or strategy == 'SHORT_STRANGLE':
                from apps.strategies.strategies.kotak_strangle import execute_kotak_strangle_entry

                result = execute_kotak_strangle_entry(
                    account,
                    call_strike=suggestion.call_strike,
                    put_strike=suggestion.put_strike,
                    lots=final_lots,
                    execute=True  # Actually execute the trade
                )

            elif strategy == 'BROKEN_IRON_CONDOR' or strategy == 'IRON_CONDOR':
                from apps.strategies.strategies.kotak_broken_iron_condor import execute_kotak_broken_iron_condor_entry

                result = execute_kotak_broken_iron_condor_entry(
                    account,
                    call_strike=suggestion.call_strike,
                    put_strike=suggestion.put_strike,
                    lots=final_lots,
                    execute=True  # Actually execute the trade
                )

            else:
                return {'success': False, 'error': f'Unknown strategy type: {strategy}'}

            if result.get('success'):
                # Update suggestion status
                suggestion.status = 'EXECUTED'
                suggestion.executed_at = timezone.now()
                suggestion.executed_lots = final_lots
                suggestion.save()

                return {
                    'success': True,
                    'strategy': strategy,
                    'lots': final_lots,
                    'order_ids': result.get('order_ids', []),
                    'position_id': result.get('position_id'),
                }
            else:
                suggestion.status = 'FAILED'
                suggestion.user_notes = f"Execution failed: {result.get('error', 'Unknown')}"
                suggestion.save()

                return result

        except Exception as e:
            logger.error(f"Error executing options trade: {e}")
            return {'success': False, 'error': str(e)}

    def execute_futures_trade(
        self,
        suggestion,
        custom_lots: int = None,
        use_batching: bool = True,
        progress_callback: callable = None,
        paper_account=None
    ) -> Dict:
        """
        Execute futures trade after confirmation with optional batching.

        For large orders (>10 lots), uses batch ordering to:
        - Reduce slippage
        - Allow cancellation mid-execution
        - Provide progress updates via callback

        This method is typically called from a background thread for non-blocking
        execution. The progress_callback is used to update the Telegram message
        with execution progress.

        Args:
            suggestion: TradeSuggestion instance
            custom_lots: Custom lot count (uses suggestion.recommended_lots if None)
            use_batching: If True, uses batch ordering for orders > batch_threshold
            progress_callback: Optional callback(batch_num, total_batches, batch_result)
                              for progress updates to the UI

        Returns:
            Dict with success status and order details:
            {
                'success': bool,
                'symbol': str,
                'direction': str,
                'lots': int (executed),
                'average_price': float,
                'order_id': str,
                'batches_executed': int (if batched),
                'total_batches': int (if batched),
                'simulated': bool,
                'error': str (if failed)
            }
        """
        try:
            from apps.accounts.models import BrokerAccount
            from apps.positions.models import Position
            from apps.core.models import TradingCoreConfig

            config = TradingCoreConfig.get_instance()

            # Get lot count
            final_lots = custom_lots or suggestion.user_modified_lots or suggestion.recommended_lots or 1

            # Get position details
            symbol = suggestion.instrument
            direction = suggestion.direction
            entry_price = suggestion.position_details.get('entry_price', 0) if suggestion.position_details else 0
            stop_loss = suggestion.position_details.get('stop_loss', 0) if suggestion.position_details else 0
            target = suggestion.position_details.get('target', 0) if suggestion.position_details else 0

            # Get expiry date: prefer position_details (user may have changed it), fallback to model field
            expiry_date_raw = suggestion.position_details.get('expiry_date') if suggestion.position_details else None
            if not expiry_date_raw and suggestion.expiry_date:
                expiry_date_raw = suggestion.expiry_date.strftime('%Y-%m-%d') if hasattr(suggestion.expiry_date, 'strftime') else str(suggestion.expiry_date)

            # Convert to Breeze format (DD-MMM-YYYY) for order placement
            if expiry_date_raw:
                try:
                    from datetime import date as date_type
                    if isinstance(expiry_date_raw, date_type):
                        expiry_dt_parsed = expiry_date_raw
                    else:
                        expiry_dt_parsed = datetime.strptime(str(expiry_date_raw), '%Y-%m-%d').date()
                    expiry_date = expiry_dt_parsed.strftime('%d-%b-%Y').upper()
                except (ValueError, TypeError):
                    # Already in Breeze format or unknown — pass as-is
                    expiry_date = str(expiry_date_raw)
                logger.info(f"Futures execution expiry: raw={expiry_date_raw} -> breeze_format={expiry_date}")
            else:
                expiry_date = None
                logger.warning(f"No expiry date found for suggestion {suggestion.id}")

            # Check for simulated mode
            if config.is_simulated():
                logger.info(f"SIMULATED: Would execute {symbol} {direction} {final_lots} lots")
                notify('SYSTEM_STATUS', title='Simulated Futures Trade', instrument=symbol,
                       metrics={'Direction': direction, 'Lots': str(final_lots)},
                       context=['Paper trade - no real order placed.'])
                suggestion.status = 'SIMULATED'
                suggestion.save()
                return {'success': True, 'simulated': True, 'lots': final_lots}

            # Paper trading mode — simulate via PaperBroker
            if paper_account and paper_account.is_paper_trading:
                return self._execute_paper_futures_trade(
                    suggestion, paper_account, symbol, direction,
                    final_lots, entry_price, stop_loss, target, expiry_date,
                )

            # Import Breeze modules (after paper check — paper doesn't need these)
            from apps.brokers.integrations.breeze import (
                place_futures_order_with_security_master,
                place_futures_order_in_batches
            )
            from apps.brokers.services.breeze_session import get_breeze_client
            from apps.trading.models import OrderExecutionControl

            # Get Breeze client
            breeze = get_breeze_client()
            if not breeze:
                return {'success': False, 'error': 'Could not connect to ICICI Breeze'}

            action = 'buy' if direction == 'LONG' else 'sell'

            # Batching configuration
            BATCH_THRESHOLD = 10  # Use batching for orders > 10 lots
            BATCH_SIZE = 10       # Max lots per batch
            BATCH_DELAY = 10      # Seconds between batches

            # Create execution control for large orders
            execution_control = None
            if use_batching and final_lots > BATCH_THRESHOLD:
                execution_control, _ = OrderExecutionControl.objects.get_or_create(
                    suggestion=suggestion,
                    defaults={'total_batches': (final_lots + BATCH_SIZE - 1) // BATCH_SIZE}
                )

                # Send progress update
                total_batches = execution_control.total_batches
                notify('SYSTEM_STATUS', title='Starting Futures Execution', instrument=symbol,
                       metrics={'Total Lots': str(final_lots), 'Batches': str(total_batches)})

                # Progress callback
                def on_progress(completed, total, orders):
                    execution_control.update_progress(completed)

                    # Build batch result for external callback
                    batch_result = {
                        'success': len(orders) > 0 and orders[-1].get('success', False) if orders else False,
                        'lots_executed': sum(o.get('lots', 0) for o in orders if o.get('success')),
                    }

                    # Call external progress callback if provided (for background thread)
                    if progress_callback:
                        try:
                            progress_callback(completed, total, batch_result)
                        except Exception as e:
                            logger.warning(f"Progress callback error: {e}")
                    else:
                        # Default: Update Telegram every 3 batches
                        if completed % 3 == 0 or completed == total:
                            executed = sum(o['lots'] for o in orders if o['success'])
                            self.telegram.send_message(
                                f"📊 Progress: {completed}/{total} batches\n"
                                f"Executed: {executed}/{final_lots} lots"
                            )

                # Cancellation check - uses both OrderExecutionControl and NseFlag fallback
                def check_cancellation():
                    from apps.core.models import NseFlag

                    # Check OrderExecutionControl first
                    execution_control.refresh_from_db()
                    if execution_control.is_cancelled:
                        return True

                    # Fallback: Check NseFlag (set by Telegram cancel button)
                    cancel_flag = NseFlag.get(f'cancel_futures_{suggestion.id}', 'false')
                    if cancel_flag == 'true':
                        execution_control.cancel(reason='User cancelled from Telegram (NseFlag)')
                        return True

                    return False

                # Use batch ordering
                order_result = place_futures_order_in_batches(
                    symbol=symbol,
                    expiry_date=expiry_date,
                    action=action,
                    total_lots=final_lots,
                    batch_size=BATCH_SIZE,
                    delay_seconds=BATCH_DELAY,
                    cancellation_check=check_cancellation,
                    progress_callback=on_progress,
                )
            else:
                # Single order for small positions
                order_result = place_futures_order_with_security_master(
                    symbol=symbol,
                    expiry_date=expiry_date,
                    action=action,
                    lots=final_lots,
                    order_type='market'
                )
                # Normalize response format
                if order_result.get('Status') == 200:
                    order_result = {
                        'success': True,
                        'lots_executed': final_lots,
                        'average_price': order_result.get('Success', {}).get('average_price', entry_price),
                        'order_id': order_result.get('Success', {}).get('order_id'),
                        'orders': [order_result]
                    }
                else:
                    order_result = {
                        'success': False,
                        'lots_executed': 0,
                        'error': order_result.get('Error', 'Unknown error')
                    }

            if order_result.get('success') and order_result.get('lots_executed', 0) > 0:
                # Get ICICI account
                icici_account = BrokerAccount.objects.filter(broker='ICICI', is_active=True).first()
                lots_executed = order_result.get('lots_executed', final_lots)

                # Create Position record
                position = Position.objects.create(
                    account=icici_account,
                    instrument=symbol,
                    strategy_type='LLM_VALIDATED_FUTURES',
                    direction=direction,
                    quantity=lots_executed * (suggestion.lot_size or 1),
                    entry_price=order_result.get('average_price', entry_price),
                    stop_loss=stop_loss,
                    target=target,
                    algorithm_score=suggestion.position_details.get('composite_score', 0) if suggestion.position_details else 0,
                    entry_analysis=suggestion.algorithm_reasoning,
                )

                # Update suggestion
                suggestion.status = 'EXECUTED'
                suggestion.executed_at = timezone.now()
                suggestion.executed_lots = lots_executed
                suggestion.save()

                # Build result notification
                exec_metrics = {'Lots': str(lots_executed)}
                if order_result.get('average_price'):
                    exec_metrics['Avg Price'] = f"₹{order_result['average_price']:,.2f}"
                exec_context = None
                if order_result.get('cancelled'):
                    exec_context = [
                        f'Partially executed (cancelled)',
                        f'Pending: {final_lots - lots_executed} lots',
                    ]

                notify('TRADE_EXECUTED', title='Futures Trade Executed', instrument=symbol,
                       metrics=exec_metrics, context=exec_context)

                return {
                    'success': True,
                    'symbol': symbol,
                    'direction': direction,
                    'lots': lots_executed,
                    'lots_requested': final_lots,
                    'average_price': order_result.get('average_price', entry_price),
                    'entry_price': order_result.get('average_price', entry_price),
                    'order_id': order_result.get('order_id', 'N/A'),
                    'position_id': position.id,
                    'batched': use_batching and final_lots > BATCH_THRESHOLD,
                    'batches_executed': order_result.get('batches_completed', 1),
                    'total_batches': order_result.get('total_batches', 1),
                    'cancelled': order_result.get('cancelled', False),
                }

            else:
                suggestion.status = 'FAILED'
                suggestion.user_notes = f"Execution failed: {order_result.get('error', 'Unknown')}"
                suggestion.save()

                error_msg = str(order_result.get('error', 'Unknown'))[:200]
                notify('TASK_ERROR', title='Futures Trade Failed', instrument=symbol,
                       context=[error_msg])

                return order_result

        except Exception as e:
            logger.error(f"Error executing futures trade: {e}")
            return {'success': False, 'error': str(e)}

    def _execute_paper_options_trade(self, suggestion, account, strategy, lots) -> Dict:
        """Execute a paper (simulated) options trade via PaperBroker."""
        from apps.brokers.utils.broker_resolver import get_broker_for_account
        from apps.positions.services.position_manager import create_position
        from decimal import Decimal

        broker = get_broker_for_account(account)

        # Simulate selling call and put legs
        call_symbol = f"NIFTY-{suggestion.call_strike}-CE" if suggestion.call_strike else suggestion.instrument
        put_symbol = f"NIFTY-{suggestion.put_strike}-PE" if suggestion.put_strike else suggestion.instrument

        lot_size = 75  # NIFTY default
        total_qty = lots * lot_size

        call_order_id = broker.place_order(
            symbol=call_symbol, action='S', quantity=total_qty, order_type='MKT',
        )
        put_order_id = broker.place_order(
            symbol=put_symbol, action='S', quantity=total_qty, order_type='MKT',
        )

        if not call_order_id and not put_order_id:
            suggestion.status = 'FAILED'
            suggestion.user_notes = 'Paper options order simulation failed'
            suggestion.save()
            return {'success': False, 'error': 'Paper options order simulation failed'}

        # Get fill prices from PaperOrder
        from apps.brokers.models import PaperOrder
        call_fill = PaperOrder.objects.filter(order_id=call_order_id).first() if call_order_id else None
        put_fill = PaperOrder.objects.filter(order_id=put_order_id).first() if put_order_id else None

        call_premium = float(call_fill.fill_price) if call_fill else float(suggestion.call_premium or 0)
        put_premium = float(put_fill.fill_price) if put_fill else float(suggestion.put_premium or 0)
        total_premium = call_premium + put_premium

        # Create position
        success, position, msg = create_position(
            account=account,
            strategy_type=strategy,
            instrument=suggestion.instrument or 'NIFTY',
            direction='NEUTRAL',
            quantity=total_qty,
            lot_size=lot_size,
            entry_price=Decimal(str(total_premium)),
            stop_loss=Decimal('0'),
            target=Decimal('0'),
            expiry_date=suggestion.expiry_date,
            margin_used=Decimal(str(suggestion.margin_required or 0)),
            call_strike=suggestion.call_strike,
            put_strike=suggestion.put_strike,
            call_premium=Decimal(str(call_premium)),
            put_premium=Decimal(str(put_premium)),
            premium_collected=Decimal(str(total_premium * total_qty)),
        )

        if success and position:
            suggestion.status = 'EXECUTED'
            suggestion.executed_at = timezone.now()
            suggestion.executed_lots = lots
            suggestion.save()

            logger.info(f"[PAPER] Options trade executed: {strategy} {lots} lots, premium={total_premium}")
            notify('TRADE_EXECUTED', title=f'[PAPER] Options {strategy} Executed',
                   instrument=suggestion.instrument or 'NIFTY',
                   metrics={'Lots': str(lots), 'Premium': f'₹{total_premium:,.2f}'})

            return {
                'success': True,
                'strategy': strategy,
                'lots': lots,
                'order_ids': [call_order_id, put_order_id],
                'position_id': position.id,
                'paper': True,
            }
        return {'success': False, 'error': msg}

    def _execute_paper_futures_trade(
        self, suggestion, account, symbol, direction,
        lots, entry_price, stop_loss, target, expiry_date,
    ) -> Dict:
        """Execute a paper (simulated) futures trade via PaperBroker."""
        from apps.brokers.utils.broker_resolver import get_broker_for_account
        from apps.positions.services.position_manager import create_position
        from decimal import Decimal

        broker = get_broker_for_account(account)
        action = 'B' if direction == 'LONG' else 'S'

        # Get lot size from suggestion
        lot_size = (suggestion.position_details.get('lot_size', 1)
                    if suggestion.position_details else 1)
        total_qty = lots * lot_size

        order_id = broker.place_order(
            symbol=symbol, action=action, quantity=total_qty, order_type='MKT',
        )

        if not order_id:
            logger.warning(f"[PAPER] Futures paper order failed for {symbol}")
            suggestion.status = 'FAILED'
            suggestion.user_notes = 'Paper order simulation failed (margin or LTP issue)'
            suggestion.save()
            return {'success': False, 'error': 'Paper order simulation failed'}

        # Get fill price from PaperOrder
        from apps.brokers.models import PaperOrder
        paper_order = PaperOrder.objects.filter(order_id=order_id).first()
        fill_price = float(paper_order.fill_price) if paper_order else entry_price

        # Parse expiry_date to YYYY-MM-DD format (may arrive as DD-MMM-YYYY)
        parsed_expiry = expiry_date
        if expiry_date and isinstance(expiry_date, str) and '-' in expiry_date:
            try:
                parsed_expiry = datetime.strptime(expiry_date, '%d-%b-%Y').date()
            except (ValueError, TypeError):
                try:
                    parsed_expiry = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    parsed_expiry = suggestion.expiry_date

        # Create position via position_manager (handles is_paper tagging)
        success, position, msg = create_position(
            account=account,
            strategy_type='LLM_VALIDATED_FUTURES',
            instrument=symbol,
            direction=direction,
            quantity=total_qty,
            lot_size=lot_size,
            entry_price=Decimal(str(fill_price)),
            stop_loss=Decimal(str(stop_loss)) if stop_loss else Decimal('0'),
            target=Decimal(str(target)) if target else Decimal('0'),
            expiry_date=parsed_expiry,
            margin_used=Decimal(str(fill_price * total_qty)),
        )

        if success and position:
            suggestion.status = 'EXECUTED'
            suggestion.executed_at = timezone.now()
            suggestion.executed_lots = lots
            suggestion.save()

            logger.info(f"[PAPER] Futures trade executed: {symbol} {direction} {lots} lots @ {fill_price}")
            notify('TRADE_EXECUTED', title='[PAPER] Futures Trade Executed', instrument=symbol,
                   metrics={'Lots': str(lots), 'Price': f'₹{fill_price:,.2f}'})

            return {
                'success': True,
                'symbol': symbol,
                'direction': direction,
                'lots': lots,
                'average_price': fill_price,
                'order_id': order_id,
                'position_id': position.id,
                'paper': True,
            }
        else:
            return {'success': False, 'error': msg}

    def close_position(self, position) -> Dict:
        """
        Close a position (called when user confirms exit).

        Args:
            position: Position model instance

        Returns:
            Dict with success status and close details
        """
        try:
            from apps.alerts.services.telegram_helpers import close_position_sync

            # Use existing close function
            result = close_position_sync(position.id)

            if result.get('success'):
                return {
                    'success': True,
                    'symbol': position.instrument,
                    'pnl': result.get('pnl', 0),
                    'reason': 'User confirmed exit',
                }
            else:
                return result

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return {'success': False, 'error': str(e)}

    def execute_averaging(self, position, lots: int) -> Dict:
        """
        Execute averaging for a position.

        Args:
            position: Position model instance
            lots: Number of lots to add

        Returns:
            Dict with success status and new position details
        """
        try:
            # Determine broker based on position account
            broker = position.account.broker if position.account else 'KOTAK'

            if broker == 'ICICI':
                from apps.brokers.integrations.breeze import get_breeze_client

                breeze = get_breeze_client()
                if not breeze:
                    return {'success': False, 'error': 'Could not connect to ICICI Breeze'}

                # Determine action based on direction
                action = 'buy' if position.direction == 'LONG' else 'sell'

                # Place averaging order
                lot_size = self._get_lot_size(position.instrument)
                quantity = lots * lot_size

                response = breeze.place_order(
                    stock_code=position.instrument,
                    exchange_code='NFO',
                    product='futures' if 'FUT' in position.instrument.upper() else 'options',
                    action=action,
                    order_type='market',
                    quantity=str(quantity),
                    price='0',
                    validity='day',
                    stoploss='0',
                    disclosed_quantity='0',
                )

                if response and response.get('Status') == 200:
                    order_id = response.get('Success', {}).get('order_id', 'N/A')
                else:
                    return {
                        'success': False,
                        'error': response.get('Error', 'Unknown error') if response else 'No response'
                    }

            elif broker == 'KOTAK':
                from apps.brokers.integrations.kotak_neo import place_option_order, get_lot_size_from_neo

                transaction_type = 'B' if position.direction == 'LONG' else 'S'
                lot_size = get_lot_size_from_neo(position.instrument)
                quantity = lots * lot_size

                result = place_option_order(
                    trading_symbol=position.instrument,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    product='NRML',
                    order_type='MKT'
                )

                if not result.get('success'):
                    return result

                order_id = result.get('order_id', 'N/A')

            else:
                return {'success': False, 'error': f'Unsupported broker: {broker}'}

            # Update position with new average (simplified)
            # In production, would refetch actual position data from broker
            old_qty = position.quantity
            new_qty = old_qty + (lots * self._get_lot_size(position.instrument))

            position.quantity = new_qty
            position.save()

            return {
                'success': True,
                'symbol': position.instrument,
                'lots_added': lots,
                'new_avg_price': position.entry_price,  # Would need to recalculate
                'order_id': order_id,
            }

        except Exception as e:
            logger.error(f"Error executing averaging: {e}")
            return {'success': False, 'error': str(e)}

    def _get_lot_size(self, symbol: str) -> int:
        """Get lot size for a symbol."""
        lot_sizes = {
            'NIFTY': 75,
            'BANKNIFTY': 30,
            'FINNIFTY': 40,
            'HDFCBANK': 550,
            'ICICIBANK': 700,
            'AXISBANK': 625,
            'RELIANCE': 250,
            'TCS': 150,
            'INFY': 300,
            'SBIN': 750,
        }

        symbol_upper = symbol.upper()
        for key, lot_size in lot_sizes.items():
            if key in symbol_upper:
                return lot_size
        return 1  # Default


# Module-level convenience instance
_confirmation_service = None


def get_confirmation_service() -> TradeConfirmationService:
    """Get or create global TradeConfirmationService instance."""
    global _confirmation_service

    if _confirmation_service is None:
        _confirmation_service = TradeConfirmationService()

    return _confirmation_service
