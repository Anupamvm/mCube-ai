"""
Trading Services Package
Contains position sizing, trade approval, and other trading-related services
"""

# Import services - some may fail if dependencies are not available
__all__ = []

try:
    from .position_sizer import PositionSizer
    __all__.append('PositionSizer')
except ImportError:
    pass

try:
    from .strangle_position_sizer import StranglePositionSizer
    __all__.append('StranglePositionSizer')
except ImportError:
    pass

try:
    from .trade_approval_handler import TradeApprovalHandler
    __all__.append('TradeApprovalHandler')
except ImportError:
    pass
