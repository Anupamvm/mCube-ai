"""
Data Providers Module

Extensible architecture for downloading data from various sources.

Supported providers:
- Trendlyne (F&O, Market Snapshot, Analyst Data)
- Future: NSE, BSE, Yahoo Finance, etc.

Usage:
    from apps.data.providers.trendlyne import TrendlyneProvider

    provider = TrendlyneProvider()
    provider.fetch_all_data()
"""

from .base import BaseDataProvider, DataProviderException
from .trendlyne import TrendlyneProvider

__all__ = [
    'BaseDataProvider',
    'DataProviderException',
    'TrendlyneProvider',
]
