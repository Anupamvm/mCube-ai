"""
Data Parsing Utilities

Centralized parsing functions to handle data conversion from various broker APIs
and external sources. Consolidates duplicate parsing logic found across the codebase.

This module replaces duplicate implementations in:
- apps/brokers/integrations/breeze.py (_parse_float)
- apps/brokers/integrations/kotak_neo.py (_parse_float)
"""

from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any, Optional, Union
import logging

logger = logging.getLogger(__name__)


def parse_float(value: Any, default: float = 0.0) -> float:
    """
    Safely parse a value to float, handling various input types.

    This function consolidates the duplicate _parse_float implementations
    found in broker integration modules.

    Args:
        value: Value to parse (can be str, int, float, Decimal, or None)
        default: Default value to return if parsing fails (default: 0.0)

    Returns:
        Parsed float value or default if parsing fails

    Examples:
        >>> parse_float("123.45")
        123.45
        >>> parse_float(None, default=0.0)
        0.0
        >>> parse_float("N/A", default=-1.0)
        -1.0
        >>> parse_float("1,234.56")  # Handles Indian number format
        1234.56
    """
    if value is None or value == '':
        return default

    try:
        # Handle string inputs
        if isinstance(value, str):
            # Remove common formatting characters
            value = value.strip().replace(',', '').replace('₹', '').replace('%', '')

            # Handle empty or placeholder values
            if value in ('', 'N/A', 'NA', '-', '--', 'None'):
                return default

            return float(value)

        # Handle Decimal inputs
        if isinstance(value, Decimal):
            return float(value)

        # Handle numeric inputs
        return float(value)

    except (ValueError, TypeError, InvalidOperation) as e:
        logger.warning(f"Failed to parse float from value '{value}': {e}")
        return default


def parse_int(value: Any, default: int = 0) -> int:
    """
    Safely parse a value to integer.

    Args:
        value: Value to parse (can be str, int, float, or None)
        default: Default value to return if parsing fails (default: 0)

    Returns:
        Parsed integer value or default if parsing fails

    Examples:
        >>> parse_int("123")
        123
        >>> parse_int("123.99")  # Truncates decimal
        123
        >>> parse_int(None)
        0
    """
    if value is None or value == '':
        return default

    try:
        if isinstance(value, str):
            value = value.strip().replace(',', '').replace('₹', '')
            if value in ('', 'N/A', 'NA', '-', '--', 'None'):
                return default

        return int(float(value))  # Convert through float to handle "123.99"

    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse int from value '{value}': {e}")
        return default


def parse_decimal(value: Any, default: Decimal = Decimal('0.00')) -> Decimal:
    """
    Safely parse a value to Decimal for precise financial calculations.

    Args:
        value: Value to parse
        default: Default Decimal value (default: Decimal('0.00'))

    Returns:
        Parsed Decimal value or default if parsing fails

    Examples:
        >>> parse_decimal("123.45")
        Decimal('123.45')
        >>> parse_decimal(None)
        Decimal('0.00')
    """
    if value is None or value == '':
        return default

    try:
        if isinstance(value, Decimal):
            return value

        if isinstance(value, str):
            value = value.strip().replace(',', '').replace('₹', '').replace('%', '')
            if value in ('', 'N/A', 'NA', '-', '--', 'None'):
                return default

        return Decimal(str(value))

    except (ValueError, TypeError, InvalidOperation) as e:
        logger.warning(f"Failed to parse Decimal from value '{value}': {e}")
        return default


def parse_date(value: Any, format_str: str = '%Y-%m-%d', default: Optional[datetime] = None) -> Optional[datetime]:
    """
    Safely parse a date string to datetime object.

    Args:
        value: Date string to parse
        format_str: Expected date format (default: '%Y-%m-%d')
        default: Default datetime to return if parsing fails (default: None)

    Returns:
        Parsed datetime object or default if parsing fails

    Examples:
        >>> parse_date("2025-11-21")
        datetime.datetime(2025, 11, 21, 0, 0)
        >>> parse_date("21-Nov-2025", format_str="%d-%b-%Y")
        datetime.datetime(2025, 11, 21, 0, 0)
    """
    if value is None or value == '':
        return default

    try:
        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            return datetime.strptime(value.strip(), format_str)

        return default

    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse date from value '{value}' with format '{format_str}': {e}")
        return default


def parse_percentage(value: Any, default: float = 0.0) -> float:
    """
    Parse percentage values, handling both "15.5%" and "0.155" formats.

    Args:
        value: Percentage value (can include '%' symbol)
        default: Default value if parsing fails

    Returns:
        Percentage as decimal (15.5% -> 0.155)

    Examples:
        >>> parse_percentage("15.5%")
        0.155
        >>> parse_percentage("0.155")
        0.155
        >>> parse_percentage(15.5)
        0.155
    """
    if value is None or value == '':
        return default

    try:
        if isinstance(value, str):
            value = value.strip().replace('%', '')
            if value in ('', 'N/A', 'NA', '-', '--'):
                return default

        num = float(value)

        # If value is > 1, assume it's in percentage form (15.5 -> 0.155)
        if num > 1:
            return num / 100.0

        # Otherwise, assume it's already decimal (0.155 -> 0.155)
        return num

    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse percentage from value '{value}': {e}")
        return default


def parse_boolean(value: Any, default: bool = False) -> bool:
    """
    Parse boolean values from various formats.

    Args:
        value: Value to parse (can be str, int, bool)
        default: Default value if parsing fails

    Returns:
        Boolean value

    Examples:
        >>> parse_boolean("true")
        True
        >>> parse_boolean("1")
        True
        >>> parse_boolean("yes")
        True
        >>> parse_boolean(0)
        False
    """
    if value is None or value == '':
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        value = value.strip().lower()
        if value in ('true', 'yes', '1', 'y', 't', 'on'):
            return True
        if value in ('false', 'no', '0', 'n', 'f', 'off'):
            return False

    logger.warning(f"Failed to parse boolean from value '{value}', returning default")
    return default
