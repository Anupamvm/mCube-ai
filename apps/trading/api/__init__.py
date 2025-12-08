"""
Trading API Module

This module provides API endpoints for the mCube trading platform.
All views are organized into focused submodules for better maintainability.

Modules:
- position_sizing: Position sizing and P&L calculations
- order_views: Order placement and status checking
- margin_views: Margin data fetching
- suggestion_views: Trade suggestion management
- position_management_views: Position viewing and closing
- contract_views: Contract and option data
- execution_views: Order execution control
"""

# Position Sizing & P&L
from apps.trading.api.position_sizing import (
    calculate_position_sizing,
    calculate_pnl_scenarios,
)

# Order Management
from apps.trading.api.order_views import (
    place_futures_order,
    check_order_status,
)

# Margin Data
from apps.trading.api.margin_views import (
    get_margin_data,
)

# Trade Suggestions
from apps.trading.api.suggestion_views import (
    get_suggestion_details,
    get_trade_suggestions,
    update_suggestion_status,
    update_suggestion_parameters,
)

# Position Management
from apps.trading.api.position_management_views import (
    get_active_positions,
    get_position_details,
    close_position,
    close_live_position,
    get_close_position_progress,
    cancel_order_placement,
    analyze_position_averaging,
)

# Contract & Option Data
from apps.trading.api.contract_views import (
    get_option_premiums,
    get_contract_details,
    get_lot_size,
)

# Execution Control
from apps.trading.api.execution_views import (
    create_execution_control,
    cancel_execution,
    get_execution_progress,
)


# Export all views for easy importing
__all__ = [
    # Position Sizing
    'calculate_position_sizing',
    'calculate_pnl_scenarios',
    'analyze_position_averaging',
    # Orders
    'place_futures_order',
    'check_order_status',
    'cancel_order_placement',
    # Margin
    'get_margin_data',
    # Suggestions
    'get_suggestion_details',
    'get_trade_suggestions',
    'update_suggestion_status',
    'update_suggestion_parameters',
    # Positions
    'get_active_positions',
    'get_position_details',
    'close_position',
    'close_live_position',
    'get_close_position_progress',
    # Contracts
    'get_option_premiums',
    'get_contract_details',
    'get_lot_size',
    # Execution
    'create_execution_control',
    'cancel_execution',
    'get_execution_progress',
]
