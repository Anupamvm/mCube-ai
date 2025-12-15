"""
Trading Views Module

Refactored from monolithic views.py (3065 lines) into focused modules.
Maintains backward compatibility - all views are re-exported here.

Structure:
    - suggestion_views: Trade suggestion management
    - algorithm_views: Futures & Strangle algorithms
    - verification_views: Trade verification
    - execution_views: Order execution
    - session_views: Broker session management
    - template_views: Page rendering

Migration Strategy:
    1. Import from this module works exactly as before
    2. URLs.py doesn't need changes
    3. Each module is independently testable
    4. Business logic will move to service layer in Phase 2.2
"""

# Import all views from focused modules for backward compatibility
from .suggestion_views import (
    pending_suggestions,
    suggestion_detail,
    approve_suggestion,
    reject_suggestion,
    execute_suggestion,
    confirm_execution,
    suggestion_history,
    export_suggestions_csv,
    auto_trade_config,
)

from .algorithm_views import (
    trigger_futures_algorithm,
    trigger_nifty_strangle,
)

from .verification_views import (
    verify_future_trade,
    get_contracts,
    start_trendlyne_fetch,
    stream_trendlyne_logs,
)

from .execution_views import (
    prepare_manual_execution,
    confirm_manual_execution,
    execute_strangle_orders,
    calculate_position_sizing,
)

from .session_views import (
    update_breeze_session,
    update_neo_session,
)

from .template_views import (
    manual_triggers,
    manual_triggers_refactored,
    view_trades,
)

# Re-export everything for backward compatibility
__all__ = [
    # Suggestion views
    'pending_suggestions',
    'suggestion_detail',
    'approve_suggestion',
    'reject_suggestion',
    'execute_suggestion',
    'confirm_execution',
    'suggestion_history',
    'export_suggestions_csv',
    'auto_trade_config',

    # Algorithm views
    'trigger_futures_algorithm',
    'trigger_nifty_strangle',

    # Verification views
    'verify_future_trade',
    'get_contracts',
    'start_trendlyne_fetch',
    'stream_trendlyne_logs',

    # Execution views
    'prepare_manual_execution',
    'confirm_manual_execution',
    'execute_strangle_orders',
    'calculate_position_sizing',

    # Session views
    'update_breeze_session',
    'update_neo_session',

    # Template views
    'manual_triggers',
    'manual_triggers_refactored',
    'view_trades',
]
