"""
Custom exceptions for strategy operations.

Provides structured error handling with context for debugging and logging.
"""

from typing import Dict, Any


class StrategyError(Exception):
    """Base exception for all strategy-related errors."""

    def __init__(self, message: str, code: str = None, details: Dict = None):
        self.message = message
        self.code = code or 'STRATEGY_ERROR'
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict:
        return {
            'error': True,
            'code': self.code,
            'message': self.message,
            'details': self.details
        }


class DataUnavailableError(StrategyError):
    """Raised when required market data is unavailable."""

    def __init__(self, data_type: str, source: str = None, fallback_used: bool = False):
        self.data_type = data_type
        self.source = source
        self.fallback_used = fallback_used

        message = f"{data_type} data unavailable"
        if source:
            message += f" from {source}"
        if fallback_used:
            message += " (using fallback)"

        super().__init__(
            message=message,
            code='DATA_UNAVAILABLE',
            details={
                'data_type': data_type,
                'source': source,
                'fallback_used': fallback_used
            }
        )


class StrikeAdjustmentError(StrategyError):
    """Raised when strike adjustment fails."""

    def __init__(self, adjustment_type: str, original_strike: int, reason: str):
        super().__init__(
            message=f"Failed to adjust {adjustment_type} strike {original_strike}: {reason}",
            code='STRIKE_ADJUSTMENT_ERROR',
            details={
                'adjustment_type': adjustment_type,
                'original_strike': original_strike,
                'reason': reason
            }
        )


class PremiumAdjustmentError(StrategyError):
    """Raised when premium-based strike adjustment fails."""

    def __init__(self, strike: int, option_type: str, reason: str, iterations: int = 0):
        super().__init__(
            message=f"Failed to adjust {strike}{option_type} for target premium: {reason}",
            code='PREMIUM_ADJUSTMENT_ERROR',
            details={
                'strike': strike,
                'option_type': option_type,
                'reason': reason,
                'iterations': iterations
            }
        )


class SupportResistanceError(StrategyError):
    """Raised when S/R calculation fails."""

    def __init__(self, reason: str, spot_price: float = None):
        super().__init__(
            message=f"S/R calculation failed: {reason}",
            code='SR_ERROR',
            details={
                'reason': reason,
                'spot_price': spot_price
            }
        )


class LiquidityWarning(StrategyError):
    """Warning for low liquidity (not a blocking error)."""

    def __init__(self, strike: int, option_type: str, current_oi: int, min_oi: int):
        super().__init__(
            message=f"Low liquidity: {strike}{option_type} OI={current_oi:,} < {min_oi:,}",
            code='LOW_LIQUIDITY_WARNING',
            details={
                'strike': strike,
                'option_type': option_type,
                'current_oi': current_oi,
                'min_oi': min_oi,
                'is_warning': True  # Not a blocking error
            }
        )


class HardRejectError(StrategyError):
    """Raised when a hard reject filter fails - blocks entry."""

    def __init__(self, filter_name: str, reason: str, value: Any = None, threshold: Any = None):
        super().__init__(
            message=f"HARD REJECT - {filter_name}: {reason}",
            code='HARD_REJECT',
            details={
                'filter_name': filter_name,
                'reason': reason,
                'value': value,
                'threshold': threshold
            }
        )


class WeeklySkipError(HardRejectError):
    """Raised when 5D filter triggers - skip entire week."""

    def __init__(self, nifty_5d_change: float, threshold: float):
        super().__init__(
            filter_name='NIFTY_5D_FILTER',
            reason=f"Market moved {nifty_5d_change:+.2f}% in 5 trading days (threshold: {threshold}%)",
            value=nifty_5d_change,
            threshold=threshold
        )
        self.code = 'WEEKLY_SKIP'


# =============================================================================
# RESULT CLASSES FOR SUCCESSFUL OPERATIONS
# =============================================================================

class AdjustmentResult:
    """Result of a strike adjustment operation."""

    def __init__(
        self,
        original_strike: int,
        adjusted_strike: int,
        adjusted: bool,
        reason: str = None,
        iterations: int = 0,
        warnings: list = None
    ):
        self.original_strike = original_strike
        self.adjusted_strike = adjusted_strike
        self.adjusted = adjusted
        self.reason = reason
        self.iterations = iterations
        self.warnings = warnings or []

    def to_dict(self) -> Dict:
        return {
            'original_strike': self.original_strike,
            'adjusted_strike': self.adjusted_strike,
            'adjusted': self.adjusted,
            'reason': self.reason,
            'iterations': self.iterations,
            'warnings': self.warnings
        }


class EnhancedAnalysisResult:
    """Complete result of enhanced strangle analysis."""

    def __init__(
        self,
        passed: bool,
        composite_score: int = 0,
        recommendation: str = 'NO_ENTRY',
        entry_bias: str = 'SYMMETRIC',
        hard_reject: bool = False,
        reject_reason: str = None,
        scores: Dict = None,
        details: Dict = None,
        delta_adjustments: Dict = None,
        adjustment_log: Dict = None,
        warnings: list = None
    ):
        self.passed = passed
        self.composite_score = composite_score
        self.recommendation = recommendation
        self.entry_bias = entry_bias
        self.hard_reject = hard_reject
        self.reject_reason = reject_reason
        self.scores = scores or {}
        self.details = details or {}
        self.delta_adjustments = delta_adjustments or {}
        self.adjustment_log = adjustment_log or {}
        self.warnings = warnings or []

    def to_dict(self) -> Dict:
        return {
            'passed': self.passed,
            'composite_score': self.composite_score,
            'recommendation': self.recommendation,
            'entry_bias': self.entry_bias,
            'hard_reject': self.hard_reject,
            'reject_reason': self.reject_reason,
            'scores': self.scores,
            'details': self.details,
            'delta_adjustments': self.delta_adjustments,
            'adjustment_log': self.adjustment_log,
            'warnings': self.warnings
        }
