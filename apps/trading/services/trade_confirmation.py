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
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from django.utils import timezone

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

        # Expiry display
        expiry_line = ''
        if suggestion.expiry_date:
            from datetime import date
            days_to_exp = (suggestion.expiry_date - date.today()).days
            expiry_fmt = suggestion.expiry_date.strftime('%d-%b-%Y')
            expiry_line = f"<b>📅 Expiry:</b> {expiry_fmt} ({days_to_exp}d)\n"

            # Check if expiry was changed
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
            f"⏱️ Auto-expires in {config.confirmation_timeout_minutes} minutes\n\n"
            f"<i>Reply with lot count to modify, or use buttons below:</i>"
        )

        # Build inline keyboard
        keyboard = {
            'inline_keyboard': [
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
        }

        success, result = self._send_with_keyboard(message, keyboard)

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
        message_lines = [
            "📈 <b>FUTURES OPPORTUNITIES</b>\n",
            f"💰 Available Margin: ₹{available:,.0f}",
            f"⏱️ Expires in {config.confirmation_timeout_minutes} min\n",
            "─" * 20,
            "\n<i>Select a trade to view details:</i>\n",
        ]

        for i, suggestion in enumerate(suggestions[:3], 1):
            symbol = suggestion.instrument
            direction = suggestion.direction
            score = suggestion.position_details.get('composite_score', 0) if suggestion.position_details else 0
            entry_price = suggestion.position_details.get('entry_price', 0) if suggestion.position_details else 0

            direction_emoji = "🟢" if direction == "LONG" else "🔴"

            message_lines.append(
                f"\n{i}️⃣ <b>{symbol}</b> {direction_emoji} {direction}\n"
                f"   Score: <b>{score}/100</b> | Entry: ₹{entry_price:,.0f}"
            )

        message_lines.append("\n\n<i>Click 'View Details' to see full analysis before approving.</i>")

        message = '\n'.join(message_lines)

        # Build keyboard with "View Details" button for each
        keyboard_rows = []
        for suggestion in suggestions[:3]:
            keyboard_rows.append([
                {'text': f'📊 View {suggestion.instrument}', 'callback_data': f'select_futures_{suggestion.id}'},
            ])

        keyboard_rows.append([
            {'text': '❌ Skip All', 'callback_data': 'futures_skip_all'},
        ])

        keyboard = {'inline_keyboard': keyboard_rows}

        success, result = self._send_with_keyboard(message, keyboard)

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

        config = TradingCoreConfig.get_instance()

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

        # Build detailed message
        message = (
            f"📊 <b>TRADE CONFIRMATION</b>\n"
            f"{'─' * 25}\n\n"
        )

        if news_warning:
            message += (
                f"⚠️ <b>NEWS WARNING</b>\n"
                f"{news_warning}\n"
                f"{'─' * 25}\n\n"
            )

        # Extract expiry info
        expiry_date_str = details.get('expiry_date', '')
        expiry_changed = details.get('expiry_changed', False)
        original_expiry = details.get('original_expiry', '')

        expiry_display = ''
        if expiry_date_str:
            try:
                from datetime import date
                expiry_dt = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                days_to_exp = (expiry_dt - date.today()).days
                expiry_display = f"{expiry_dt.strftime('%d-%b-%Y')} ({days_to_exp}d)"
            except (ValueError, TypeError):
                expiry_display = expiry_date_str

        message += (
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Direction:</b> {direction_emoji} {direction}\n"
            f"<b>Score:</b> {score}/100\n"
        )

        if expiry_display:
            message += f"<b>📅 Expiry:</b> {expiry_display}\n"
            if expiry_changed:
                message += f"⚠️ <i>Changed from original: {original_expiry}</i>\n"

        message += (
            f"\n"
            f"<b>📍 PRICE LEVELS</b>\n"
            f"  Entry: ₹{entry_price:,.2f}\n"
            f"  Stop-Loss: ₹{stop_loss:,.2f}\n"
            f"  Target: ₹{target:,.2f}\n\n"

            f"<b>📐 POSITION SIZE</b>\n"
            f"  Lots: {recommended_lots}\n"
            f"  Lot Size: {lot_size}\n"
            f"  Margin Required: ₹{margin_per_lot * recommended_lots:,.0f}\n\n"

            f"<b>⚖️ RISK/REWARD</b>\n"
            f"  Risk: ₹{risk_amount:,.0f}\n"
            f"  Reward: ₹{reward_amount:,.0f}\n"
            f"  Ratio: 1:{rr_ratio:.1f}\n\n"

            f"<b>🔬 ANALYSIS SIGNALS</b>\n"
            f"  OI: {oi_signal}\n"
            f"  DMA: {dma_signal}\n"
            f"  Sector: {sector_signal}\n\n"

            f"{'─' * 25}\n"
            f"<i>Click 'Confirm Trade' to execute.</i>\n"
            f"<i>Trade will execute in background with batching.</i>"
        )

        # Build keyboard for Step 2
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': f'✅ Confirm Trade ({recommended_lots}L)', 'callback_data': f'confirm_futures_{suggestion.id}'},
                ],
                [
                    {'text': '📊 Change Lots', 'callback_data': f'resize_futures_{suggestion.id}'},
                    {'text': '📅 Change Expiry', 'callback_data': f'expiry_futures_{suggestion.id}'},
                ],
                [
                    {'text': '◀️ Back to List', 'callback_data': 'back_futures_list'},
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
        Send exit alert (SL/Target hit) for confirmation.

        Args:
            position: Position model instance
            reason: Exit reason (STOP_LOSS_HIT, TARGET_HIT, etc.)
            current_pnl: Current P&L

        Returns:
            Tuple[bool, str]: (success, message_id or error)
        """
        pnl = current_pnl or position.unrealized_pnl or Decimal('0')
        pnl_str = f"+₹{pnl:,.0f}" if pnl >= 0 else f"-₹{abs(pnl):,.0f}"

        reason_emoji = {
            'STOP_LOSS_HIT': '🛑',
            'TARGET_HIT': '🎯',
            'TIME_EXIT': '⏰',
            'MANUAL': '👤',
        }.get(reason, '📊')

        message = (
            f"{reason_emoji} <b>EXIT ALERT</b>\n\n"
            f"Position: #{position.id}\n"
            f"Symbol: {position.instrument}\n"
            f"Direction: {position.direction}\n\n"
            f"<b>Reason: {reason.replace('_', ' ')}</b>\n\n"
            f"Current P&L: <b>{pnl_str}</b>\n"
            f"Entry: ₹{position.entry_price:,.0f}\n"
            f"Current: ₹{position.current_price:,.0f}\n\n"
            f"<i>Confirm to close position now:</i>"
        )

        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '✅ Close Now', 'callback_data': f'confirm_exit_{position.id}'},
                    {'text': '⏸️ Hold', 'callback_data': f'hold_exit_{position.id}'},
                ],
            ]
        }

        return self._send_with_keyboard(message, keyboard)

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

        message = (
            f"📊 <b>AVERAGING RECOMMENDATION</b>\n\n"
            f"Position: #{position.id}\n"
            f"Symbol: {position.instrument}\n"
            f"Direction: {position.direction}\n\n"
            f"Current P&L: <b>{pnl_str}</b>\n"
            f"Entry: ₹{position.entry_price:,.0f}\n"
            f"Current: ₹{position.current_price:,.0f}\n\n"
        )

        if averaging_preview:
            message += (
                f"<b>If you average with {recommended_lots} lots:</b>\n"
                f"  • New Avg Entry: ₹{averaging_preview.get('new_average_entry', 0):,.0f}\n"
                f"  • New Stop-Loss: ₹{averaging_preview.get('new_stop_loss', 0):,.0f}\n"
                f"  • Additional Margin: ₹{averaging_preview.get('additional_margin', 0):,.0f}\n\n"
            )

        message += "<i>Confirm to add to position:</i>"

        keyboard = {
            'inline_keyboard': [
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
        }

        return self._send_with_keyboard(message, keyboard)

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
            message = (
                f"⏰ <b>TIMEOUT - REVALIDATED</b>\n\n"
                f"You took some time. Let me recheck...\n\n"
                f"✅ Position still valid! Original parameters apply.\n\n"
                f"Confirm to proceed?"
            )
            keyboard = {
                'inline_keyboard': [
                    [
                        {'text': '✅ Confirm Now', 'callback_data': f'confirm_options_{suggestion.id}'},
                        {'text': '❌ Cancel', 'callback_data': f'reject_options_{suggestion.id}'},
                    ],
                ]
            }
        else:
            message = (
                f"⏰ <b>TIMEOUT - EXPIRED</b>\n\n"
                f"You took some time. Position no longer viable.\n\n"
                f"Reason: {reason}\n\n"
                f"Will try again tomorrow."
            )
            keyboard = None

            # Mark as expired
            suggestion.status = 'EXPIRED'
            suggestion.user_notes = f"Revalidation failed: {reason}"
            suggestion.save()

        suggestion.revalidation_sent = True
        suggestion.save()

        if keyboard:
            return self._send_with_keyboard(message, keyboard)
        else:
            return self.telegram.send_message(message)

    def _revalidate_futures(self, suggestion) -> Tuple[bool, str]:
        """Revalidate futures suggestion after timeout."""
        # For futures, check if score is still above threshold
        current_score = suggestion.position_details.get('composite_score', 0) if suggestion.position_details else 0

        # Consider still valid if score >= 60
        is_valid = current_score >= 60

        if is_valid:
            message = (
                f"⏰ <b>TIMEOUT - STILL VALID</b>\n\n"
                f"Symbol: {suggestion.instrument}\n"
                f"Score: {current_score}/100\n\n"
                f"Opportunity still available. Confirm to proceed?"
            )
            keyboard = {
                'inline_keyboard': [
                    [
                        {'text': '✅ Confirm', 'callback_data': f'confirm_futures_{suggestion.id}'},
                        {'text': '❌ Skip', 'callback_data': f'reject_futures_{suggestion.id}'},
                    ],
                ]
            }
        else:
            message = (
                f"⏰ <b>TIMEOUT - EXPIRED</b>\n\n"
                f"Symbol: {suggestion.instrument}\n"
                f"Current Score: {current_score}/100\n\n"
                f"Opportunity no longer meets criteria."
            )
            keyboard = None

            suggestion.status = 'EXPIRED'
            suggestion.user_notes = f"Revalidation: Score dropped to {current_score}"
            suggestion.save()

        suggestion.revalidation_sent = True
        suggestion.save()

        if keyboard:
            return self._send_with_keyboard(message, keyboard)
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

    def execute_options_trade(self, suggestion, lots: int = None) -> Dict:
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
            from apps.trading.models import TradeSuggestion

            # Determine strategy type
            strategy = suggestion.strategy_type

            # Get lot count
            final_lots = lots or suggestion.user_modified_lots or suggestion.recommended_lots or 1

            # Get the active Kotak account
            account = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()
            if not account:
                return {'success': False, 'error': 'No active Kotak account found'}

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
        progress_callback: callable = None
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
            from apps.brokers.integrations.breeze import (
                place_futures_order_with_security_master,
                place_futures_order_in_batches
            )
            from apps.brokers.services.breeze_session import get_breeze_client
            from apps.accounts.models import BrokerAccount
            from apps.positions.models import Position
            from apps.trading.models import OrderExecutionControl
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
                self.telegram.send_message(
                    f"📝 SIMULATED FUTURES TRADE\n\n"
                    f"Symbol: {symbol}\n"
                    f"Direction: {direction}\n"
                    f"Lots: {final_lots}\n\n"
                    f"Paper trade - no real order placed."
                )
                suggestion.status = 'SIMULATED'
                suggestion.save()
                return {'success': True, 'simulated': True, 'lots': final_lots}

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
                self.telegram.send_message(
                    f"🚀 STARTING FUTURES EXECUTION\n\n"
                    f"Symbol: {symbol} ({direction})\n"
                    f"Total Lots: {final_lots}\n"
                    f"Batch Size: {BATCH_SIZE}\n"
                    f"Batches: {execution_control.total_batches}\n\n"
                    f"⏳ Executing..."
                )

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

                # Build result message
                msg_parts = [
                    f"✅ FUTURES TRADE EXECUTED\n",
                    f"Symbol: {symbol}",
                    f"Direction: {direction}",
                    f"Lots: {lots_executed}",
                ]
                if order_result.get('average_price'):
                    msg_parts.append(f"Avg Price: ₹{order_result['average_price']:,.2f}")
                if order_result.get('cancelled'):
                    msg_parts.append(f"\n⚠️ Partially executed (cancelled)")
                    msg_parts.append(f"Pending: {final_lots - lots_executed} lots")

                self.telegram.send_message('\n'.join(msg_parts))

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

                self.telegram.send_message(
                    f"❌ FUTURES TRADE FAILED\n\n"
                    f"Symbol: {symbol}\n"
                    f"Error: {order_result.get('error', 'Unknown')}"
                )

                return order_result

        except Exception as e:
            logger.error(f"Error executing futures trade: {e}")
            return {'success': False, 'error': str(e)}

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
