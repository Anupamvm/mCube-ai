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

try:
    from .trade_suggestions import (
        TradeSuggestionService,
        OptionsSuggestionFormatter,
        FuturesSuggestionFormatter
    )
    __all__.extend(['TradeSuggestionService', 'OptionsSuggestionFormatter', 'FuturesSuggestionFormatter'])
except ImportError:
    pass

try:
    from .iron_condor_position_sizer import IronCondorPositionSizer
    __all__.append('IronCondorPositionSizer')
except ImportError:
    pass

# New shared services for futures algorithm unification
try:
    from .margin_service import (
        get_available_margin,
        get_margin_per_lot,
        get_margin_summary
    )
    __all__.extend(['get_available_margin', 'get_margin_per_lot', 'get_margin_summary'])
except ImportError:
    pass

try:
    from .position_service import (
        calculate_position_sizing,
        calculate_stop_loss_target,
        calculate_risk_metrics,
        build_position_sizing_response
    )
    __all__.extend([
        'calculate_position_sizing',
        'calculate_stop_loss_target',
        'calculate_risk_metrics',
        'build_position_sizing_response'
    ])
except ImportError:
    pass

try:
    from .analysis_service import (
        run_basic_analysis,
        run_historical_verification,
        run_news_verification,
        run_analyst_verification,
        run_full_analysis,
        format_analysis_for_response
    )
    __all__.extend([
        'run_basic_analysis',
        'run_historical_verification',
        'run_news_verification',
        'run_analyst_verification',
        'run_full_analysis',
        'format_analysis_for_response'
    ])
except ImportError:
    pass

try:
    from .suggestion_service import save_futures_suggestions
    __all__.append('save_futures_suggestions')
except ImportError:
    pass

try:
    from .chart_data_service import (
        ChartDataService,
        ContractChartDataService,
        get_chart_data_for_suggestion,
        get_chart_data_for_contract
    )
    __all__.extend([
        'ChartDataService',
        'ContractChartDataService',
        'get_chart_data_for_suggestion',
        'get_chart_data_for_contract'
    ])
except ImportError:
    pass
