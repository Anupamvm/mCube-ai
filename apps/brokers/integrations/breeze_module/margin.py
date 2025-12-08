"""
ICICI Breeze Margin - Margin Data Fetching

This module provides functions to fetch margin and funds data from Breeze API.
"""

import logging

from apps.brokers.utils.auth_manager import get_credentials
from apps.brokers.utils.api_patterns import (
    get_breeze_customer_details,
    fetch_breeze_margin_data
)

from .client import get_breeze_client

logger = logging.getLogger(__name__)


def get_nfo_margin():
    """
    Get NFO margin information including pledged stocks.

    Returns actual available margin (cash_limit) which includes:
    - Cash allocated to F&O
    - Margin from pledged stocks
    - Available collateral

    Returns:
        dict: Margin data with 'cash_limit', 'amount_allocated', etc.
              Returns None if API call fails
    """
    try:
        breeze = get_breeze_client()

        # Use centralized credential loading
        creds = get_credentials('breeze')
        if not creds:
            logger.error("No Breeze credentials found")
            return None

        # Use common pattern for customer details and margin fetching
        rest_token, _ = get_breeze_customer_details(
            creds.api_key,
            creds.api_secret,
            creds.session_token
        )

        # Use common pattern for margin data fetching
        margins = fetch_breeze_margin_data(
            creds.api_key,
            creds.api_secret,
            rest_token,
            exchange_code="NFO"
        )

        return margins

    except Exception as e:
        logger.error(f"Error fetching NFO margin: {e}", exc_info=True)
        return None
