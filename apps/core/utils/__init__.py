"""
Core utility functions for mCube Trading System
"""

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

from .validators import (
    is_valid_strike,
    is_within_market_hours,
    validate_position_entry,
    validate_margin_usage,
    validate_risk_reward_ratio,
    validate_quantity,
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
]
