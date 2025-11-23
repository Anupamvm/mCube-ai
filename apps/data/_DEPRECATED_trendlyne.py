"""
DEPRECATED: This file is deprecated and will be removed in a future release.

Please use the new provider architecture instead:

    from apps.data.providers.trendlyne import TrendlyneProvider

    with TrendlyneProvider() as provider:
        provider.fetch_all_data()

Or for backwards compatibility:

    from apps.data.providers.trendlyne import get_all_trendlyne_data
    get_all_trendlyne_data()

See apps/data/TRENDLYNE_REFACTORING.md for migration guide.
"""

import warnings

warnings.warn(
    "apps.data.trendlyne is deprecated. Use apps.data.providers.trendlyne instead.",
    DeprecationWarning,
    stacklevel=2
)

# Import from new location for backwards compatibility
from .providers.trendlyne import get_all_trendlyne_data

__all__ = ['get_all_trendlyne_data']
