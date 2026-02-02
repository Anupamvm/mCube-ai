"""
Entry workflow engine - executes the standard 9-step entry workflow.

This class encapsulates common workflow logic shared across all strategies.
Each step is implemented as a separate method for clarity and testability.
"""

from decimal import Decimal
from datetime import date
from typing import TYPE_CHECKING, Dict, Tuple

from django.utils import timezone

from apps.strategies.core.result_types import EntryResult

if TYPE_CHECKING:
    from apps.strategies.core.base_strategy import BaseStrategy


class EntryWorkflow:
    """
    Executes the standard 9-step entry workflow.

    Steps:
    1. Morning position check (ONE POSITION RULE)
    2. Entry timing validation
    3. Run entry filters
    4. Expiry selection
    5. Calculate entry parameters (strategy-specific)
    6. Validate premiums/prices
    7. Position sizing
    8. Risk limit checks
    9. Create trade suggestion
    """

    def __init__(self, strategy: 'BaseStrategy'):
        """
        Initialize workflow with a strategy instance.

        Args:
            strategy: BaseStrategy subclass instance
        """
        self.strategy = strategy
        self.account = strategy.account
        self.config = strategy.config
        self.logger = strategy.logger

    def execute(self) -> EntryResult:
        """
        Execute the complete entry workflow.

        Returns:
            EntryResult with success status, message, and details
        """
        self._log_header()

        # Step 1: Morning Position Check
        result = self._step_1_morning_check()
        if not result['allow_new_entry']:
            return EntryResult(False, result['message'], details=result)

        # Step 2: Entry Timing Validation
        timing_ok, timing_msg = self._step_2_timing_validation()
        if not timing_ok:
            return EntryResult(False, timing_msg)

        # Step 3: Run Entry Filters
        filters_passed, filter_details = self._step_3_entry_filters()
        if not filters_passed:
            return EntryResult(False, "Entry filters failed", details=filter_details)

        # Step 3b: Enhanced Analysis (if strategy provides it)
        enhanced_result = self._step_3b_enhanced_analysis()
        if enhanced_result and not enhanced_result.get('passed', True):
            return EntryResult(
                False,
                enhanced_result.get('message', 'Enhanced analysis rejected entry'),
                details=enhanced_result
            )

        # Store enhanced analysis for use in reasoning
        if enhanced_result:
            filter_details['enhanced_analysis'] = enhanced_result

        # Step 4: Expiry Selection
        expiry_result = self._step_4_expiry_selection()
        if not expiry_result['success']:
            return EntryResult(False, expiry_result['message'])

        # Step 5: Calculate Entry Parameters (STRATEGY-SPECIFIC)
        market_data = self._gather_market_data()
        market_data['expiry'] = expiry_result['expiry']
        market_data['days_to_expiry'] = expiry_result['days_to_expiry']

        try:
            entry_params = self.strategy.calculate_entry_parameters(market_data)
            self.logger.info("Entry parameters calculated successfully")
            self.logger.info("")
        except Exception as e:
            msg = f"Entry parameter calculation failed: {str(e)}"
            self.logger.error(msg, exc_info=True)
            return EntryResult(False, msg)

        # Step 6: Validate Premiums/Prices
        valid, validation_msg = self.strategy.validate_premiums(entry_params)
        if not valid:
            return EntryResult(False, validation_msg)

        # Step 7: Position Sizing
        sizing = self._step_7_position_sizing(entry_params)
        if not sizing['success']:
            return EntryResult(False, sizing['message'])

        # Step 8: Risk Limit Checks
        risk_ok, risk_details = self._step_8_risk_checks()
        if not risk_ok:
            return EntryResult(False, "Risk limits breached", details=risk_details)

        # Step 9: Create Trade Suggestion
        return self._step_9_create_suggestion(entry_params, filter_details, sizing)

    def _log_header(self):
        """Log the workflow header with account and time info."""
        self.strategy.log_header(f"{self.config.name.upper()} - ENTRY EVALUATION")
        self.logger.info(f"Account: {self.account.broker} - {self.account.account_name}")
        self.logger.info(f"Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("")

    def _step_1_morning_check(self) -> Dict:
        """
        Step 1: Morning Position Check (ONE POSITION RULE).

        Returns:
            Dict with allow_new_entry and message
        """
        from apps.positions.services.position_manager import morning_check

        self.strategy.log_step(1, "Morning Position Check (ONE POSITION RULE)")

        result = morning_check(self.account)

        if result['allow_new_entry']:
            self.logger.info(f"[OK] {result['message']}")
        else:
            self.logger.warning(f"[BLOCKED] {result['message']}")

        self.logger.info("")
        return result

    def _step_2_timing_validation(self) -> Tuple[bool, str]:
        """
        Step 2: Entry Timing Validation.

        Returns:
            Tuple of (is_valid, message)
        """
        self.strategy.log_step(2, "Entry Timing Validation")

        current_time = timezone.now().time()
        start = self.config.entry_start_time
        end = self.config.entry_end_time

        if start <= current_time <= end:
            self.logger.info(f"[OK] Entry timing valid ({current_time.strftime('%H:%M')})")
            self.logger.info("")
            return True, ""
        else:
            msg = (f"Entry window closed (allowed: {start.strftime('%H:%M')}-"
                   f"{end.strftime('%H:%M')}, current: {current_time.strftime('%H:%M')})")
            self.logger.warning(f"[BLOCKED] {msg}")
            return False, msg

    def _step_3_entry_filters(self) -> Tuple[bool, Dict]:
        """
        Step 3: Entry Filters Execution.

        Returns:
            Tuple of (all_passed, details_dict)
        """
        self.strategy.log_step(3, "Entry Filters Execution")

        from apps.strategies.shared.entry_filters import run_filters

        filters = self.strategy.get_entry_filters()
        return run_filters(filters, self.logger)

    def _step_3b_enhanced_analysis(self) -> Dict:
        """
        Step 3b: Enhanced Analysis (optional).

        Strategies can override run_enhanced_analysis() to provide
        comprehensive multi-factor scoring before entry.

        Returns:
            Dict with 'passed' bool, 'message', 'score', 'details'
            or None if strategy doesn't implement enhanced analysis
        """
        if not hasattr(self.strategy, 'run_enhanced_analysis'):
            return None

        self.logger.info("")
        self.logger.info("STEP 3b: Enhanced Multi-Factor Analysis")
        self.logger.info("-" * 80)

        try:
            result = self.strategy.run_enhanced_analysis()

            if result:
                score = result.get('composite_score', 0)
                recommendation = result.get('recommendation', 'UNKNOWN')

                if result.get('hard_reject'):
                    self.logger.warning(f"[HARD REJECT] {result.get('reject_reason')}")
                    return {'passed': False, 'message': result.get('reject_reason'), **result}

                # Check minimum score threshold
                min_score = getattr(self.strategy, 'MIN_ENHANCED_SCORE', 50)
                if score < min_score:
                    self.logger.warning(f"[BLOCKED] Score {score}/100 below threshold ({min_score})")
                    return {
                        'passed': False,
                        'message': f'Enhanced analysis score too low ({score}/{min_score})',
                        **result
                    }

                self.logger.info(f"[OK] Enhanced Score: {score}/100 - {recommendation}")
                self.logger.info("")
                return {'passed': True, **result}

            return None

        except Exception as e:
            self.logger.error(f"[ERROR] Enhanced analysis failed: {str(e)}", exc_info=True)
            # Don't block entry on analysis error, just log it
            return None

    def _step_4_expiry_selection(self) -> Dict:
        """
        Step 4: Expiry Selection.

        Returns:
            Dict with success, expiry, days_to_expiry, and details
        """
        self.strategy.log_step(4, f"Expiry Selection ({self.config.min_days_to_expiry}-day minimum rule)")

        try:
            expiry_selector = self.strategy.get_expiry_selector()

            if self.config.strategy_type == 'OPTIONS':
                selected_expiry, expiry_details = expiry_selector(
                    instrument='NIFTY',
                    min_days=self.config.min_days_to_expiry
                )
            else:
                # For futures, get symbol from strategy if available
                symbol = getattr(self.strategy, 'symbol', 'NIFTY')
                selected_expiry, expiry_details = expiry_selector(
                    symbol=symbol,
                    min_days=self.config.min_days_to_expiry
                )

            days_to_expiry = (selected_expiry - date.today()).days

            self.logger.info(f"[OK] Selected Expiry: {selected_expiry} ({days_to_expiry} days)")
            self.logger.info(f"   Details: {expiry_details}")
            self.logger.info("")

            return {
                'success': True,
                'expiry': selected_expiry,
                'days_to_expiry': days_to_expiry,
                'details': expiry_details
            }
        except Exception as e:
            self.logger.error(f"[ERROR] Expiry selection failed: {str(e)}", exc_info=True)
            return {'success': False, 'message': f"Expiry selection failed: {str(e)}"}

    def _gather_market_data(self) -> Dict:
        """
        Gather current market data for strategy calculations.

        Returns:
            Dict with spot_price and vix
        """
        from apps.strategies.shared.market_data import get_nifty_price, get_vix

        return {
            'spot_price': get_nifty_price(),
            'vix': get_vix(),
        }

    def _step_7_position_sizing(self, entry_params: Dict) -> Dict:
        """
        Step 7: Position Sizing (margin-based).

        Args:
            entry_params: Entry parameters for sizing calculation

        Returns:
            Dict with success, usable_margin, lots, quantity, margin_used
        """
        from apps.accounts.services.margin_manager import calculate_usable_margin

        self.strategy.log_step(7, f"Position Sizing ({int(self.config.margin_usage_pct * 100)}% margin usage rule)")

        try:
            usable_margin = calculate_usable_margin(self.account)

            # Nifty lot size = 50 for options
            lot_size = 50 if self.config.strategy_type == 'OPTIONS' else 1

            # TODO: Fetch actual margin per lot from broker
            margin_per_lot = Decimal('80000')

            max_lots = int(usable_margin / margin_per_lot)

            if max_lots < 1:
                msg = f"Insufficient margin (usable: Rs.{usable_margin:,.0f}, required: Rs.{margin_per_lot:,.0f})"
                self.logger.warning(f"[BLOCKED] {msg}")
                return {'success': False, 'message': msg}

            # Use 1 lot for conservative approach
            lots = 1
            quantity = lots * lot_size
            margin_used = margin_per_lot * lots

            self.logger.info(f"Usable Margin ({int(self.config.margin_usage_pct * 100)}%): Rs.{usable_margin:,.0f}")
            self.logger.info(f"Lots: {lots}, Quantity: {quantity}")
            self.logger.info(f"Margin Used: Rs.{margin_used:,.0f}")
            self.logger.info(f"[OK] Position sizing complete")
            self.logger.info("")

            return {
                'success': True,
                'usable_margin': usable_margin,
                'lot_size': lot_size,
                'lots': lots,
                'quantity': quantity,
                'margin_used': margin_used
            }
        except Exception as e:
            self.logger.error(f"[ERROR] Position sizing failed: {str(e)}", exc_info=True)
            return {'success': False, 'message': f"Position sizing failed: {str(e)}"}

    def _step_8_risk_checks(self) -> Tuple[bool, Dict]:
        """
        Step 8: Risk Limit Validation.

        Returns:
            Tuple of (passed, risk_check_dict)
        """
        from apps.risk.services.risk_manager import check_risk_limits

        self.strategy.log_step(8, "Risk Limit Validation")

        try:
            risk_check = check_risk_limits(self.account)

            if risk_check['action_required'] != 'NONE':
                self.logger.warning(f"[BLOCKED] Risk limits breached: {risk_check['message']}")
                return False, risk_check

            self.logger.info(f"[OK] All risk limits satisfied")
            self.logger.info("")
            return True, risk_check
        except Exception as e:
            self.logger.error(f"[ERROR] Risk check failed: {str(e)}", exc_info=True)
            return False, {'error': str(e)}

    def _step_9_create_suggestion(self, entry_params: Dict, filter_details: Dict, sizing: Dict) -> EntryResult:
        """
        Step 9: Trade Suggestion Creation.

        Args:
            entry_params: Entry parameters
            filter_details: Filter execution results
            sizing: Position sizing results

        Returns:
            EntryResult with success status and suggestion
        """
        from apps.trading.services import TradeSuggestionService

        self.strategy.log_step(9, "Trade Suggestion Creation")

        try:
            # Build strategy-specific details
            position_details = self.strategy.build_position_details(entry_params, sizing)
            algorithm_reasoning = self.strategy.build_algorithm_reasoning(
                entry_params, filter_details, sizing
            )

            # Determine instrument from entry params or position details
            instrument = position_details.get('instrument', 'NIFTY')
            if hasattr(self.strategy, 'symbol'):
                instrument = self.strategy.symbol

            # Create trade suggestion
            suggestion = TradeSuggestionService.create_suggestion(
                user=self.account.user,
                strategy=self.config.name.lower().replace(' ', '_'),
                suggestion_type=self.config.strategy_type,
                instrument=instrument,
                direction=self.config.direction,
                algorithm_reasoning=algorithm_reasoning,
                position_details=position_details
            )

            self.logger.info(f"[OK] Trade suggestion created: {suggestion.id}")
            self.logger.info(f"   Status: {suggestion.get_status_display()}")
            self.logger.info("")
            self.logger.info("=" * 100)

            return EntryResult(
                success=True,
                message=f'Trade suggestion #{suggestion.id} created',
                suggestion=suggestion,
                details={
                    'suggestion_id': suggestion.id,
                    'status': suggestion.get_status_display(),
                }
            )
        except Exception as e:
            self.logger.error(f"[ERROR] Trade suggestion creation failed: {str(e)}", exc_info=True)
            return EntryResult(False, f"Trade suggestion creation failed: {str(e)}")
