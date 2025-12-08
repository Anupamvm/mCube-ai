"""
ICICI Breeze Quotes - Market Data Fetching

This module provides functions to fetch market quotes, NIFTY prices, and India VIX.
"""

import logging
from decimal import Decimal
from django.core.cache import cache

from apps.brokers.utils.common import parse_float as _parse_float

from .client import get_breeze_client

logger = logging.getLogger(__name__)


def get_nifty_quote():
    """
    Get NIFTY50 spot price from Breeze cash quote.

    Returns:
        dict: Quote data with LTP and other metrics

    Raises:
        ValueError: If quote data is invalid or missing
        BreezeAuthenticationError: If session is expired
    """
    breeze = get_breeze_client()
    resp = breeze.get_quotes(
        stock_code="NIFTY",
        exchange_code="NSE",
        product_type="cash",
        expiry_date="",
        right="",
        strike_price=""
    )
    logger.info(f"NIFTY quote response: {resp}")

    # Check if response is valid
    if not resp:
        raise ValueError("Empty response from Breeze API for NIFTY quote")

    # Check for API errors
    if resp.get("Status") != 200:
        error_msg = resp.get("Error", "Unknown error")
        status = resp.get("Status", "Unknown")
        raise ValueError(f"Breeze API error (Status {status}): {error_msg}")

    # Check for success data
    if not resp.get("Success"):
        raise ValueError("No success data in Breeze API response")

    rows = resp["Success"]
    if not rows:
        raise ValueError("Empty success data from Breeze API")

    # Find NSE row or use first row
    row = next((r for r in rows if (r or {}).get("exchange_code") == "NSE"), rows[0] if rows else None)

    if not row:
        raise ValueError("No valid quote data found in Breeze API response")

    return row


def get_india_vix() -> Decimal:
    """
    Get India VIX (Volatility Index) from Breeze API.

    Uses cache to avoid excessive API calls (5-minute cache).
    Falls back to 15.0 if API fails.

    Returns:
        Decimal: Current India VIX value
    """
    # Check cache first (5-minute TTL)
    cache_key = 'india_vix_value'
    cached_vix = cache.get(cache_key)

    if cached_vix is not None:
        logger.debug(f"Using cached VIX value: {cached_vix}")
        return Decimal(str(cached_vix))

    try:
        breeze = get_breeze_client()

        # Fetch India VIX quote from NSE using correct symbol: INDVIX
        resp = breeze.get_quotes(
            stock_code="INDVIX",
            exchange_code="NSE",
            product_type="cash",
            expiry_date="",
            right="",
            strike_price=""
        )

        logger.info(f"India VIX (INDVIX) quote response: {resp}")

        if resp and resp.get("Status") == 200 and resp.get("Success"):
            rows = resp["Success"]
            if rows:
                row = rows[0]
                vix_value = _parse_float(row.get('ltp', 15.0))
                vix_decimal = Decimal(str(vix_value))

                # Cache for 5 minutes (300 seconds)
                cache.set(cache_key, float(vix_decimal), 300)

                logger.info(f"Successfully fetched India VIX: {vix_decimal}")
                return vix_decimal

        logger.error("Failed to fetch India VIX from Breeze API - no valid response")
        raise ValueError("Could not fetch India VIX from Breeze API - invalid response")

    except Exception as e:
        logger.error(f"Error fetching India VIX: {e}")
        raise ValueError(f"Could not fetch India VIX from Breeze API: {str(e)}")
