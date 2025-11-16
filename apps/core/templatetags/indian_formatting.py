"""
Custom template filters for Indian number formatting

Usage in templates:
    {% load indian_formatting %}
    {{ amount|indian_currency }}
    {{ amount|indian_number }}
"""

from django import template
from decimal import Decimal
from typing import Union

register = template.Library()


@register.filter(name='indian_currency')
def indian_currency(value, decimals=2):
    """
    Format value as Indian currency with ₹ symbol

    Usage:
        {{ amount|indian_currency }}
        {{ amount|indian_currency:0 }}  # No decimals

    Examples:
        77200970 -> ₹7,72,00,970.00
        1234.56 -> ₹1,234.56
    """
    from apps.core.utils.formatting import format_indian_currency

    if value is None:
        return "₹0.00"

    try:
        # Convert to float if needed
        if isinstance(value, (str, Decimal)):
            value = float(value)

        return format_indian_currency(value)
    except (ValueError, TypeError):
        return "₹0.00"


@register.filter(name='indian_number')
def indian_number(value, decimals=2):
    """
    Format value as Indian number without currency symbol

    Usage:
        {{ number|indian_number }}
        {{ number|indian_number:0 }}  # No decimals

    Examples:
        77200970 -> 7,72,00,970
        1234.56 -> 1,234.56
    """
    from apps.core.utils import format_indian_number

    if value is None:
        return "0"

    try:
        # Convert to numeric if needed
        if isinstance(value, (str, Decimal)):
            value = float(value)

        return format_indian_number(value, decimals)
    except (ValueError, TypeError):
        return "0"


@register.filter(name='indian_compact')
def indian_compact(value):
    """
    Format large numbers in compact notation (K/L/Cr)

    Usage:
        {{ number|indian_compact }}

    Examples:
        77200970 -> 7.72Cr
        100000 -> 1.00L
        5000 -> 5.00K
    """
    from apps.core.utils import format_compact

    if value is None:
        return "0"

    try:
        # Convert to numeric if needed
        if isinstance(value, (str, Decimal)):
            value = float(value)

        return format_compact(value)
    except (ValueError, TypeError):
        return "0"
