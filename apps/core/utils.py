"""
Core utility functions for mCube Trading System

Includes number formatting, date utilities, and other helpers
"""

import re


def format_indian_number(number, decimals=2):
    """
    Format number in Indian numbering system (lakhs and crores)

    Examples:
        1000 -> 1,000
        100000 -> 1,00,000 (1 lakh)
        10000000 -> 1,00,00,000 (1 crore)
        77200970 -> 7,72,00,970

    Args:
        number: Number to format (int or float)
        decimals: Number of decimal places (default 2)

    Returns:
        str: Formatted number string
    """
    if number is None:
        return "0"

    # Handle negative numbers
    if number < 0:
        return "-" + format_indian_number(abs(number), decimals)

    # Convert to string with decimal places
    if isinstance(number, float):
        num_str = f"{number:.{decimals}f}"
    else:
        num_str = str(int(number))

    # Split into integer and decimal parts
    if '.' in num_str:
        int_part, dec_part = num_str.split('.')
    else:
        int_part = num_str
        dec_part = None

    # Format integer part with Indian numbering
    if len(int_part) <= 3:
        formatted = int_part
    else:
        # Last 3 digits
        formatted = int_part[-3:]
        remaining = int_part[:-3]

        # Add commas every 2 digits from right to left
        while remaining:
            if len(remaining) > 2:
                formatted = remaining[-2:] + ',' + formatted
                remaining = remaining[:-2]
            else:
                formatted = remaining + ',' + formatted
                remaining = ''

    # Add decimal part if exists
    if dec_part:
        formatted = formatted + '.' + dec_part

    return formatted


def format_currency(amount, decimals=2, symbol='₹'):
    """
    Format currency in Indian numbering system

    Examples:
        15210863.91 -> ₹1,52,10,863.91
        77200970 -> ₹7,72,00,970.00

    Args:
        amount: Amount to format
        decimals: Number of decimal places (default 2)
        symbol: Currency symbol (default ₹)

    Returns:
        str: Formatted currency string
    """
    formatted_num = format_indian_number(amount, decimals)
    return f"{symbol}{formatted_num}"


def format_compact(number):
    """
    Format number in compact notation (L for lakhs, Cr for crores)

    Examples:
        100000 -> 1.00L
        10000000 -> 1.00Cr
        77200970 -> 7.72Cr

    Args:
        number: Number to format

    Returns:
        str: Compact formatted string
    """
    if number is None:
        return "0"

    abs_num = abs(number)
    prefix = "-" if number < 0 else ""

    if abs_num >= 10000000:  # 1 crore or more
        return f"{prefix}{abs_num / 10000000:.2f}Cr"
    elif abs_num >= 100000:  # 1 lakh or more
        return f"{prefix}{abs_num / 100000:.2f}L"
    elif abs_num >= 1000:  # 1 thousand or more
        return f"{prefix}{abs_num / 1000:.2f}K"
    else:
        return f"{prefix}{abs_num:.0f}"
