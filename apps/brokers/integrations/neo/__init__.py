"""
Kotak Neo API Integration Module

This module provides integration with Kotak Neo broker API for:
- Authentication and session management
- Fetching positions and limits
- Placing orders (single and batch)
- Symbol mapping between brokers
- Real-time quotes and LTP

All functions are exported for backward compatibility with the original
kotak_neo.py monolithic file.
"""

# Client & Authentication
from .client import (
    _get_authenticated_client,
    get_kotak_neo_client,
    auto_login_kotak_neo,
)

# Data Fetching
from .data_fetcher import (
    fetch_and_save_kotakneo_data,
    is_open_position,
)

# Symbol Mapping
from .symbol_mapper import (
    map_neo_symbol_to_breeze,
    map_breeze_symbol_to_neo,
    _get_neo_scrip_master,
)

# Quotes & LTP
from .quotes import (
    get_ltp_from_neo,
    get_lot_size_from_neo,
    get_lot_size_from_neo_with_token,
)

# Order Placement
from .orders import (
    place_option_order,
)

# Batch Orders
from .batch_orders import (
    place_strangle_orders_in_batches,
    close_position_in_batches,
    close_strangle_positions_in_batches,
)


# Export all for backward compatibility
__all__ = [
    # Client
    '_get_authenticated_client',
    'get_kotak_neo_client',
    'auto_login_kotak_neo',
    # Data
    'fetch_and_save_kotakneo_data',
    'is_open_position',
    # Symbol Mapping
    'map_neo_symbol_to_breeze',
    'map_breeze_symbol_to_neo',
    '_get_neo_scrip_master',
    # Quotes
    'get_ltp_from_neo',
    'get_lot_size_from_neo',
    'get_lot_size_from_neo_with_token',
    # Orders
    'place_option_order',
    # Batch Orders
    'place_strangle_orders_in_batches',
    'close_position_in_batches',
    'close_strangle_positions_in_batches',
]
