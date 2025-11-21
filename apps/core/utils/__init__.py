"""
Core utility functions for mCube Trading System

This module consolidates common utilities used across the application,
eliminating code duplication and providing a single source of truth.
"""

# Date utilities
from .date_utils import (
    get_current_weekly_expiry,
    get_next_weekly_expiry,
    get_current_month_expiry,
    get_next_month_expiry,
    is_trading_day,
    is_market_hours,
    get_days_to_expiry,
    is_within_entry_window,
    get_current_ist_time,
    format_time_ist,
)

# Formatting utilities
from .formatting import (
    format_indian_currency,
    format_percentage,
    format_quantity,
    format_decimal,
    format_pnl,
    format_strike_price,
    format_option_symbol,
    format_futures_symbol,
    shorten_large_number,
)

# Convenience alias - format_currency is the same as format_indian_currency
format_currency = format_indian_currency

# Validation utilities
from .validators import (
    is_valid_strike,
    is_within_market_hours,
    validate_position_entry,
    validate_margin_usage,
    validate_risk_reward_ratio,
    validate_quantity,
)

# Parsing utilities (NEW - consolidates duplicate _parse_float functions)
from .parsers import (
    parse_float,
    parse_int,
    parse_decimal,
    parse_date,
    parse_percentage,
    parse_boolean,
)

# Decorators (NEW - consolidates duplicate error handling patterns)
from .decorators import (
    handle_exceptions,
    require_broker_auth,
    validate_input,
    log_execution_time,
    require_post_method,
    cache_result,
)

# Custom exceptions (NEW - provides domain-specific exceptions)
from .exceptions import (
    mCubeBaseException,
    BrokerAuthenticationError,
    BrokerAPIError,
    OrderExecutionError,
    MarketDataError,
    InvalidContractError,
    InvalidInputError,
    ValidationError,
    AlgorithmError,
    PositionSizingError,
    ConfigurationError,
    DatabaseError,
    ExternalServiceError,
    LLMServiceError,
    InsufficientPermissionsError,
    handle_exception_gracefully,
)

__all__ = [
    # Date utilities
    'get_current_weekly_expiry',
    'get_next_weekly_expiry',
    'get_current_month_expiry',
    'get_next_month_expiry',
    'is_trading_day',
    'is_market_hours',
    'get_days_to_expiry',
    'is_within_entry_window',
    'get_current_ist_time',
    'format_time_ist',

    # Formatting utilities
    'format_indian_currency',
    'format_currency',  # Alias for format_indian_currency
    'format_percentage',
    'format_quantity',
    'format_decimal',
    'format_pnl',
    'format_strike_price',
    'format_option_symbol',
    'format_futures_symbol',
    'shorten_large_number',

    # Validators
    'is_valid_strike',
    'is_within_market_hours',
    'validate_position_entry',
    'validate_margin_usage',
    'validate_risk_reward_ratio',
    'validate_quantity',

    # Parsers (NEW)
    'parse_float',
    'parse_int',
    'parse_decimal',
    'parse_date',
    'parse_percentage',
    'parse_boolean',

    # Decorators (NEW)
    'handle_exceptions',
    'require_broker_auth',
    'validate_input',
    'log_execution_time',
    'require_post_method',
    'cache_result',

    # Exceptions (NEW)
    'mCubeBaseException',
    'BrokerAuthenticationError',
    'BrokerAPIError',
    'OrderExecutionError',
    'MarketDataError',
    'InvalidContractError',
    'InvalidInputError',
    'ValidationError',
    'AlgorithmError',
    'PositionSizingError',
    'ConfigurationError',
    'DatabaseError',
    'ExternalServiceError',
    'LLMServiceError',
    'InsufficientPermissionsError',
    'handle_exception_gracefully',
]
