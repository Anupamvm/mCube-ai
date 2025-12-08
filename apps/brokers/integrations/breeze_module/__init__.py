"""
ICICI Breeze Module - Modular Breeze API Integration

This package provides a modular implementation of the ICICI Breeze broker API integration.
All functions are exported for backward compatibility with the original breeze.py module.

Modules:
    client: Authentication and session management
    quotes: Market data fetching (NIFTY, India VIX)
    margin: Margin data fetching
    data_fetcher: Fetch funds and positions
    expiry: Expiry date fetching
    option_chain: Option chain data fetching
    orders: Order placement with SecurityMaster
    historical: Historical price data
    api_classes: High-level API wrapper classes
"""

# Client & Authentication
from .client import (
    get_breeze_client,
    get_or_prompt_breeze_token,
    save_breeze_token,
)

# Quotes & Market Data
from .quotes import (
    get_nifty_quote,
    get_india_vix,
)

# Margin
from .margin import (
    get_nfo_margin,
)

# Data Fetcher
from .data_fetcher import (
    fetch_and_save_breeze_data,
)

# Expiry Dates
from .expiry import (
    get_all_nifty_expiry_dates,
    get_next_nifty_expiry,
    get_next_monthly_expiry,
)

# Option Chain
from .option_chain import (
    get_and_save_option_chain_quotes,
    fetch_and_save_nifty_option_chain_all_expiries,
)

# Orders
from .orders import (
    place_futures_order_with_security_master,
    place_option_order_with_security_master,
)

# Historical Data
from .historical import (
    save_historical_price_record,
    get_nifty50_historical_days,
)

# API Classes
from .api_classes import (
    BreezeAPI,
    BreezeAPIClient,
    get_breeze_api,
)

__all__ = [
    # Client & Authentication
    'get_breeze_client',
    'get_or_prompt_breeze_token',
    'save_breeze_token',
    # Quotes & Market Data
    'get_nifty_quote',
    'get_india_vix',
    # Margin
    'get_nfo_margin',
    # Data Fetcher
    'fetch_and_save_breeze_data',
    # Expiry Dates
    'get_all_nifty_expiry_dates',
    'get_next_nifty_expiry',
    'get_next_monthly_expiry',
    # Option Chain
    'get_and_save_option_chain_quotes',
    'fetch_and_save_nifty_option_chain_all_expiries',
    # Orders
    'place_futures_order_with_security_master',
    'place_option_order_with_security_master',
    # Historical Data
    'save_historical_price_record',
    'get_nifty50_historical_days',
    # API Classes
    'BreezeAPI',
    'BreezeAPIClient',
    'get_breeze_api',
]
