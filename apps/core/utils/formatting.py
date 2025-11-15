"""
Formatting utility functions for mCube Trading System

This module provides functions for formatting:
- Currency (Indian Rupees)
- Percentages
- Quantities
- Decimals
"""

from decimal import Decimal
from typing import Union


def format_indian_currency(amount: Union[Decimal, float, int]) -> str:
    """
    Format amount in Indian currency format (Rs.)

    Indian numbering system:
    - First comma after 3 digits from right
    - Subsequent commas after every 2 digits

    Args:
        amount: Amount to format

    Returns:
        str: Formatted currency string

    Example:
        >>> format_indian_currency(1234567)
        'Rs.12,34,567'
        >>> format_indian_currency(72000000)
        'Rs.7,20,00,000'
        >>> format_indian_currency(Decimal('1234.50'))
        'Rs.1,234.50'
    """
    if isinstance(amount, Decimal):
        amount_float = float(amount)
    else:
        amount_float = float(amount)

    # Handle negative amounts
    is_negative = amount_float < 0
    amount_float = abs(amount_float)

    # Split into integer and decimal parts
    if '.' in str(amount_float):
        int_part, dec_part = str(amount_float).split('.')
    else:
        int_part = str(int(amount_float))
        dec_part = None

    # Format integer part with Indian numbering
    int_part = int_part[::-1]  # Reverse
    formatted = ''

    # First group of 3 digits
    if len(int_part) > 3:
        formatted = int_part[:3] + ','
        int_part = int_part[3:]

        # Remaining groups of 2 digits
        while len(int_part) > 2:
            formatted += int_part[:2] + ','
            int_part = int_part[2:]

        formatted += int_part
    else:
        formatted = int_part

    formatted = formatted[::-1]  # Reverse back

    # Add decimal part if exists
    if dec_part:
        # Limit to 2 decimal places
        dec_part = dec_part[:2].ljust(2, '0')
        formatted += '.' + dec_part

    # Add currency symbol and negative sign
    result = f"Rs.{formatted}"
    if is_negative:
        result = f"-{result}"

    return result


def format_percentage(value: Union[Decimal, float], decimal_places: int = 2) -> str:
    """
    Format value as percentage

    Args:
        value: Value to format (e.g., 0.05 for 5%)
        decimal_places: Number of decimal places

    Returns:
        str: Formatted percentage string

    Example:
        >>> format_percentage(0.05)
        '5.00%'
        >>> format_percentage(Decimal('0.125'), 2)
        '12.50%'
        >>> format_percentage(1.5, 1)
        '150.0%'
    """
    if isinstance(value, Decimal):
        value = float(value)

    percentage = value * 100
    return f"{percentage:.{decimal_places}f}%"


def format_quantity(quantity: int) -> str:
    """
    Format quantity with thousand separators

    Args:
        quantity: Quantity to format

    Returns:
        str: Formatted quantity string

    Example:
        >>> format_quantity(1000)
        '1,000'
        >>> format_quantity(50000)
        '50,000'
    """
    return f"{quantity:,}"


def format_decimal(value: Union[Decimal, float], decimal_places: int = 2) -> str:
    """
    Format decimal number to fixed decimal places

    Args:
        value: Value to format
        decimal_places: Number of decimal places

    Returns:
        str: Formatted decimal string

    Example:
        >>> format_decimal(123.456, 2)
        '123.46'
        >>> format_decimal(Decimal('0.12345'), 4)
        '0.1235'
    """
    if isinstance(value, Decimal):
        value = float(value)

    return f"{value:.{decimal_places}f}"


def format_pnl(pnl: Union[Decimal, float]) -> str:
    """
    Format P&L with color indicator and currency

    Args:
        pnl: Profit/Loss amount

    Returns:
        str: Formatted P&L string with sign

    Example:
        >>> format_pnl(12345)
        '+Rs.12,345.00'
        >>> format_pnl(-5000)
        '-Rs.5,000.00'
    """
    if isinstance(pnl, Decimal):
        pnl = float(pnl)

    formatted_amount = format_indian_currency(abs(pnl))

    if pnl > 0:
        return f"+{formatted_amount}"
    elif pnl < 0:
        return f"-{formatted_amount}"
    else:
        return formatted_amount


def format_strike_price(strike: Union[Decimal, float, int]) -> str:
    """
    Format strike price

    Args:
        strike: Strike price

    Returns:
        str: Formatted strike price

    Example:
        >>> format_strike_price(24000)
        '24000'
        >>> format_strike_price(24500.0)
        '24500'
    """
    return str(int(strike))


def format_option_symbol(
    instrument: str,
    expiry: str,
    strike: Union[Decimal, float, int],
    option_type: str
) -> str:
    """
    Format option symbol in standard format

    Args:
        instrument: Instrument name (NIFTY, BANKNIFTY)
        expiry: Expiry date (DDMMMYY format, e.g., 16NOV24)
        strike: Strike price
        option_type: CE or PE

    Returns:
        str: Formatted option symbol

    Example:
        >>> format_option_symbol('NIFTY', '16NOV24', 24000, 'CE')
        'NIFTY16NOV2424000CE'
        >>> format_option_symbol('BANKNIFTY', '16NOV24', 51000, 'PE')
        'BANKNIFTY16NOV2451000PE'
    """
    strike_str = format_strike_price(strike)
    return f"{instrument}{expiry}{strike_str}{option_type}"


def format_futures_symbol(instrument: str, expiry: str) -> str:
    """
    Format futures symbol in standard format

    Args:
        instrument: Instrument name (NIFTY, RELIANCE, etc.)
        expiry: Expiry date (DDMMMYY format, e.g., 28NOV24)

    Returns:
        str: Formatted futures symbol

    Example:
        >>> format_futures_symbol('NIFTY', '28NOV24')
        'NIFTY28NOV24FUT'
        >>> format_futures_symbol('RELIANCE', '28NOV24')
        'RELIANCE28NOV24FUT'
    """
    return f"{instrument}{expiry}FUT"


def shorten_large_number(number: Union[int, float, Decimal]) -> str:
    """
    Convert large numbers to readable format with K/L/Cr suffixes

    Args:
        number: Number to convert

    Returns:
        str: Shortened number string

    Example:
        >>> shorten_large_number(1000)
        '1K'
        >>> shorten_large_number(100000)
        '1L'
        >>> shorten_large_number(10000000)
        '1Cr'
    """
    if isinstance(number, Decimal):
        number = float(number)

    number = abs(number)

    if number >= 10000000:  # Crores (1 Cr = 1,00,00,000)
        return f"{number / 10000000:.2f}Cr"
    elif number >= 100000:  # Lakhs (1 L = 1,00,000)
        return f"{number / 100000:.2f}L"
    elif number >= 1000:  # Thousands
        return f"{number / 1000:.2f}K"
    else:
        return f"{number:.2f}"
