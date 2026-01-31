"""
Result types and configuration dataclasses for trading strategies.

These types provide standardized interfaces for:
    - Strategy configuration (timing, margin rules, expiry rules)
    - Entry evaluation results (success/failure with details)
"""

from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal
from typing import Dict, Any, Optional


@dataclass
class StrategyConfig:
    """
    Configuration for a trading strategy.

    Attributes:
        name: Human-readable strategy name
        strategy_type: 'OPTIONS' or 'FUTURES'
        direction: 'NEUTRAL', 'LONG', or 'SHORT'
        entry_start_time: Earliest time to enter trades
        entry_end_time: Latest time to enter trades
        min_days_to_expiry: Minimum days to expiry for trade entry
        margin_usage_pct: Percentage of margin to use (e.g., 0.50 for 50%)
        extra: Strategy-specific additional settings
    """
    name: str
    strategy_type: str  # 'OPTIONS' or 'FUTURES'
    direction: str      # 'NEUTRAL', 'LONG', 'SHORT'

    # Entry timing
    entry_start_time: time
    entry_end_time: time

    # Expiry rules
    min_days_to_expiry: int

    # Margin rules
    margin_usage_pct: Decimal  # e.g., 0.50 for 50%

    # Strategy-specific settings
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntryResult:
    """
    Standardized result from entry evaluation.

    Attributes:
        success: Whether the entry evaluation succeeded
        message: Human-readable result message
        suggestion: TradeSuggestion instance if successful
        details: Additional details dictionary
    """
    success: bool
    message: str
    suggestion: Optional[Any] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert result to dictionary format for backward compatibility."""
        return {
            'success': self.success,
            'message': self.message,
            'suggestion': self.suggestion,
            'details': self.details or {}
        }
