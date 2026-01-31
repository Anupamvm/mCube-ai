"""
Abstract base class for all trading strategies.

Provides common workflow with hooks for strategy-specific customization.
Each strategy inherits from this class and implements the abstract methods
for its unique logic.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING
import logging

from apps.strategies.core.result_types import StrategyConfig, EntryResult

if TYPE_CHECKING:
    from apps.accounts.models import BrokerAccount


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Usage:
        class KotakStrangle(BaseStrategy):
            def get_config(self) -> StrategyConfig:
                return StrategyConfig(...)

            def calculate_entry_parameters(self, market_data):
                # Strategy-specific calculation
                ...

    The execute_entry() method runs the standard 9-step workflow,
    calling the abstract methods at appropriate points for strategy-specific logic.
    """

    def __init__(self, account: "BrokerAccount"):
        """
        Initialize strategy with a broker account.

        Args:
            account: BrokerAccount instance for this strategy
        """
        self.account = account
        self.config = self.get_config()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # =========================================================================
    # ABSTRACT METHODS - Must be implemented by each strategy
    # =========================================================================

    @abstractmethod
    def get_config(self) -> StrategyConfig:
        """
        Return strategy configuration.

        Returns:
            StrategyConfig with strategy settings
        """
        pass

    @abstractmethod
    def calculate_entry_parameters(self, market_data: Dict) -> Dict:
        """
        Calculate strategy-specific entry parameters.

        For Options: Returns strikes, premiums, etc.
        For Futures: Returns entry price, direction, symbol, etc.

        Args:
            market_data: Dict with spot_price, vix, expiry, days_to_expiry

        Returns:
            Dict with calculated entry parameters
        """
        pass

    @abstractmethod
    def build_position_details(self, entry_params: Dict, sizing: Dict) -> Dict:
        """
        Build the position details dict for trade suggestion.

        Args:
            entry_params: Entry parameters from calculate_entry_parameters
            sizing: Position sizing results

        Returns:
            Dict with position details for TradeSuggestion
        """
        pass

    @abstractmethod
    def build_algorithm_reasoning(self,
                                  entry_params: Dict,
                                  filters_result: Dict,
                                  sizing: Dict) -> Dict:
        """
        Build the algorithm reasoning dict for trade suggestion.

        Args:
            entry_params: Entry parameters
            filters_result: Filter execution results
            sizing: Position sizing results

        Returns:
            Dict with algorithm reasoning for TradeSuggestion
        """
        pass

    # =========================================================================
    # OPTIONAL OVERRIDES - Strategies can customize these
    # =========================================================================

    def get_entry_filters(self) -> List:
        """
        Return list of entry filter functions.

        Override to customize which filters run for this strategy.

        Returns:
            List of filter callables
        """
        from apps.strategies.shared.entry_filters import get_default_filters
        return get_default_filters()

    def validate_premiums(self, entry_params: Dict) -> Tuple[bool, str]:
        """
        Validate premiums/prices are acceptable.

        Override for custom validation logic.

        Args:
            entry_params: Entry parameters to validate

        Returns:
            Tuple of (is_valid, message)
        """
        return True, "Premiums acceptable"

    def get_expiry_selector(self):
        """
        Return the appropriate expiry selector function.

        Returns:
            Expiry selector function for this strategy type
        """
        if self.config.strategy_type == 'OPTIONS':
            from apps.core.services.expiry_selector import select_expiry_for_options
            return select_expiry_for_options
        else:
            from apps.core.services.expiry_selector import select_expiry_for_futures
            return select_expiry_for_futures

    # =========================================================================
    # CONCRETE METHODS - Shared workflow
    # =========================================================================

    def execute_entry(self) -> EntryResult:
        """
        Execute the complete entry workflow.

        This method orchestrates the standard 9-step workflow:
        1. Morning position check
        2. Entry timing validation
        3. Run entry filters
        4. Expiry selection
        5. Calculate entry parameters (strategy-specific)
        6. Validate premiums/prices
        7. Position sizing
        8. Risk limit checks
        9. Create trade suggestion

        Returns:
            EntryResult with success status, message, and details
        """
        from apps.strategies.core.entry_workflow import EntryWorkflow
        return EntryWorkflow(self).execute()

    def log_header(self, title: str):
        """
        Log a section header.

        Args:
            title: Header title text
        """
        self.logger.info("=" * 100)
        self.logger.info(title)
        self.logger.info("=" * 100)

    def log_step(self, step_num: int, title: str):
        """
        Log a workflow step.

        Args:
            step_num: Step number (1-9)
            title: Step title text
        """
        self.logger.info(f"STEP {step_num}: {title}")
        self.logger.info("-" * 80)
