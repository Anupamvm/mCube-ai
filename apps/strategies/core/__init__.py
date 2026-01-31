"""
Core infrastructure for mCube Trading Strategies.

This module provides base classes and common utilities for all trading strategies:
    - BaseStrategy: Abstract base class for strategy implementations
    - EntryWorkflow: Standard 9-step entry workflow engine
    - StrategyConfig: Configuration dataclass for strategies
    - EntryResult: Standardized result type for entry evaluations
"""

from apps.strategies.core.result_types import StrategyConfig, EntryResult
from apps.strategies.core.base_strategy import BaseStrategy
from apps.strategies.core.entry_workflow import EntryWorkflow

__all__ = [
    'BaseStrategy',
    'EntryWorkflow',
    'StrategyConfig',
    'EntryResult',
]
