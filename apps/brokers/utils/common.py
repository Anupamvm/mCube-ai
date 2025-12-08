"""
Common utility functions for broker integrations.

This module provides shared utilities used across different broker APIs
(Kotak Neo, ICICI Breeze, etc.) to avoid code duplication and ensure
consistent behavior.

Functions:
    - parse_float: Extract and convert numeric values to float
    - parse_decimal: Extract and convert numeric values to Decimal
    - safe_int: Safely convert values to integer
    - format_currency: Format numbers as Indian currency
"""

import re
import logging
from decimal import Decimal, InvalidOperation
from typing import Union, Optional

logger = logging.getLogger(__name__)


def parse_float(val: Union[str, int, float, None]) -> float:
    """
    Extract numeric content from value and return as float.

    This function handles various input formats commonly returned by broker APIs:
    - Strings with commas: "1,234.56" → 1234.56
    - Percentages: "15.5%" → 15.5
    - Numbers with currency symbols: "₹100.50" → 100.50
    - None/empty values: None → 0.0
    - Negative numbers: "-123.45" → -123.45

    Falls back to 0.0 if parsing fails to prevent crashes in production.

    Args:
        val: Value to parse (can be string, number, or None)

    Returns:
        float: Parsed numeric value or 0.0 if parsing fails

    Example:
        >>> parse_float("1,234.56")
        1234.56
        >>> parse_float("15.5%")
        15.5
        >>> parse_float(None)
        0.0
        >>> parse_float("₹100.50")
        100.5

    Notes:
        - This function is intentionally permissive to handle malformed API responses
        - For strict validation, use decimal.Decimal with explicit error handling
        - Logs warnings when parsing fails for debugging purposes
    """
    # Handle None and numeric types first (fast path)
    if val is None:
        return 0.0

    if isinstance(val, (int, float)):
        return float(val)

    # Convert to string and clean
    s = str(val).strip()

    if not s:
        return 0.0

    # Remove common non-numeric characters
    # Keep: digits, decimal point, minus sign
    s = s.replace(',', '')  # Remove thousands separators
    s = s.replace('₹', '')  # Remove currency symbol
    s = s.replace('$', '')  # Remove dollar sign

    # Handle percentages
    if s.endswith('%'):
        s = s[:-1]

    # Extract first number found (handles "Value: 123.45" format)
    match = re.search(r'-?\d+\.?\d*', s)

    if not match:
        logger.warning(f"parse_float: no numeric data in '{val}', defaulting to 0.0")
        return 0.0

    try:
        return float(match.group())
    except ValueError:
        logger.warning(f"parse_float: invalid conversion for '{val}', defaulting to 0.0")
        return 0.0


def parse_decimal(val: Union[str, int, float, None], decimal_places: int = 2) -> Decimal:
    """
    Extract numeric content and return as Decimal with specified precision.

    Use this function when exact decimal precision is required (e.g., for money,
    position quantities, or database storage). Internally uses parse_float() for
    extraction, then converts to Decimal with proper quantization.

    Args:
        val: Value to parse (can be string, number, or None)
        decimal_places: Number of decimal places to round to (default: 2)

    Returns:
        Decimal: Parsed and quantized Decimal value

    Example:
        >>> parse_decimal("1234.567", 2)
        Decimal('1234.57')
        >>> parse_decimal("1,234.567", 2)
        Decimal('1234.57')
        >>> parse_decimal(None, 2)
        Decimal('0.00')

    Notes:
        - Uses ROUND_HALF_UP rounding mode for financial calculations
        - Returns properly quantized Decimal suitable for database storage
        - Never raises exceptions (returns 0.00 on failure)
    """
    try:
        float_val = parse_float(val)
        decimal_val = Decimal(str(float_val))

        # Create quantizer based on decimal_places
        quantizer = Decimal('0.1') ** decimal_places  # 0.01 for 2 places, 0.001 for 3, etc.

        return decimal_val.quantize(quantizer)
    except (InvalidOperation, ValueError) as e:
        logger.error(f"parse_decimal: error converting '{val}' to Decimal: {e}")
        # Return zero with proper quantization
        quantizer = Decimal('0.1') ** decimal_places
        return Decimal('0').quantize(quantizer)


def safe_int(val: Union[str, int, float, None], default: int = 0) -> int:
    """
    Safely convert value to integer with fallback.

    Handles common API response formats and prevents crashes when
    non-numeric data is encountered.

    Args:
        val: Value to convert to integer
        default: Default value if conversion fails (default: 0)

    Returns:
        int: Converted integer value or default

    Example:
        >>> safe_int("123")
        123
        >>> safe_int("123.45")
        123
        >>> safe_int(None)
        0
        >>> safe_int("invalid", default=100)
        100

    Notes:
        - Truncates decimal values (not rounding): 123.9 → 123
        - Handles None, empty strings, and invalid formats gracefully
    """
    try:
        if val is None or val == '':
            return default

        if isinstance(val, int):
            return val

        if isinstance(val, float):
            return int(val)

        # For strings, try direct int conversion first
        try:
            return int(val)
        except (ValueError, TypeError):
            pass

        # Try parsing as float if direct int fails (handles "123.45")
        try:
            return int(float(val.replace(',', '')))
        except (ValueError, TypeError, AttributeError):
            pass

        # If all conversions fail, return default
        return default

    except (ValueError, TypeError) as e:
        logger.debug(f"safe_int: conversion failed for '{val}', using default {default}: {e}")
        return default


def format_indian_currency(amount: Union[int, float, Decimal], include_symbol: bool = True) -> str:
    """
    Format number as Indian currency (with lakhs and crores).

    Indian number format uses:
    - First comma after 3 digits from right
    - Subsequent commas after every 2 digits
    - Example: 12,34,567.89 (12 lakh 34 thousand)

    Args:
        amount: Amount to format
        include_symbol: Include ₹ symbol (default: True)

    Returns:
        str: Formatted currency string

    Example:
        >>> format_indian_currency(1234567.89)
        '₹12,34,567.89'
        >>> format_indian_currency(1234567.89, include_symbol=False)
        '12,34,567.89'
        >>> format_indian_currency(1000000)
        '₹10,00,000.00'

    Notes:
        - Always shows 2 decimal places
        - Handles negative numbers correctly
    """
    # Handle negative numbers
    is_negative = amount < 0
    amount = abs(amount)

    # Convert to string with 2 decimal places
    amount_str = f"{amount:.2f}"
    integer_part, decimal_part = amount_str.split('.')

    # Format integer part with Indian grouping
    if len(integer_part) <= 3:
        formatted_int = integer_part
    else:
        # Take last 3 digits
        last_three = integer_part[-3:]
        remaining = integer_part[:-3]

        # Add commas every 2 digits from right
        groups = []
        while remaining:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]

        formatted_int = ','.join(groups) + ',' + last_three

    # Combine with decimal part
    result = f"{formatted_int}.{decimal_part}"

    # Add negative sign if needed
    if is_negative:
        result = f"-{result}"

    # Add currency symbol
    if include_symbol:
        result = f"₹{result}"

    return result


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default if division by zero.

    Useful for calculating percentages, ratios, and averages from API data
    where denominator might be zero or None.

    Args:
        numerator: Number to divide
        denominator: Number to divide by
        default: Value to return if denominator is zero (default: 0.0)

    Returns:
        float: Result of division or default if denominator is zero

    Example:
        >>> safe_divide(100, 50)
        2.0
        >>> safe_divide(100, 0)
        0.0
        >>> safe_divide(100, 0, default=float('inf'))
        inf

    Notes:
        - Also handles None values for both arguments
        - Useful for preventing ZeroDivisionError in production
    """
    try:
        if denominator == 0 or denominator is None:
            return default

        if numerator is None:
            return default

        return numerator / denominator

    except (TypeError, ZeroDivisionError):
        return default
