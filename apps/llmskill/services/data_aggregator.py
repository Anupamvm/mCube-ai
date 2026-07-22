"""
Read-only "what do we already know about this symbol" data dump.

This makes NO live API calls (no Breeze, no scraping, no LLM) - it only
reads rows that are already persisted in the database, so the user can see
exactly what's available to build an LLM verification prompt from: which
table each piece of data lives in, when it was last updated, and the raw
field values of the most recent rows.
"""

import logging
from datetime import date, datetime
from datetime import time as dt_time
from decimal import Decimal
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MAX_STR_LEN = 1500


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, dt_time)):
        return value.isoformat()
    if isinstance(value, str) and len(value) > MAX_STR_LEN:
        return value[:MAX_STR_LEN] + f'… [truncated, {len(value)} chars total]'
    return value


def _serialize_instance(instance) -> Dict[str, Any]:
    # field.attname (not field.name) so ForeignKeys read as their raw *_id
    # value instead of triggering a query to resolve the related object.
    return {field.name: _json_safe(getattr(instance, field.attname)) for field in instance._meta.fields}


def _dump_source(label: str, model, queryset) -> Dict[str, Any]:
    """Build a uniform {label, model, table, count, last_updated, rows} block for one data source."""
    rows = list(queryset)

    last_updated = None
    timestamps = [getattr(r, 'updated_at', None) or getattr(r, 'created_at', None) for r in rows]
    timestamps = [t for t in timestamps if t]
    if timestamps:
        last_updated = max(timestamps).isoformat()

    return {
        'label': label,
        'model': model.__name__,
        'table': model._meta.db_table,
        'count': len(rows),
        'last_updated': last_updated,
        'rows': [_serialize_instance(r) for r in rows],
    }


def get_verification_data(symbol: str, expiry_date: str = None) -> Dict[str, Any]:
    """
    Aggregate everything already stored for a symbol (+ optional expiry) into
    one dict of data sources, purely from the database.

    Args:
        symbol: Underlying symbol, e.g. 'HDFCBANK'
        expiry_date: Optional expiry date 'YYYY-MM-DD' to narrow contract-level sources

    Returns:
        dict: {symbol, expiry_date, sources: [...], errors: [...]}
    """
    result: Dict[str, Any] = {
        'symbol': symbol,
        'expiry_date': expiry_date,
        'sources': [],
        'errors': [],
    }

    builders = [
        _dump_prior_suggestions,
        _dump_contract_data,
        _dump_contract_stock_data,
        _dump_tl_stock_data,
        _dump_analyst_price_target,
        _dump_historical_price,
        _dump_option_chain_quotes,
        _dump_news_articles,
        _dump_analyst_reports,
        _dump_investor_calls,
        _dump_oi_intelligence,
        _dump_oi_history,
        _dump_exchange_announcements,
    ]

    for build_fn in builders:
        try:
            result['sources'].append(build_fn(symbol, expiry_date))
        except Exception as e:
            logger.warning(f"{build_fn.__name__} failed for {symbol}: {e}", exc_info=True)
            result['errors'].append(f"{build_fn.__name__}: {e}")

    return result


def _dump_prior_suggestions(symbol: str, expiry_date: str):
    from apps.trading.models import TradeSuggestion

    qs = TradeSuggestion.objects.filter(instrument=symbol)
    if expiry_date:
        qs = qs.filter(expiry_date=expiry_date)
    qs = qs.order_by('-id')[:5]

    return _dump_source('Prior Trade Suggestions (algorithm reasoning saved at suggestion time)', TradeSuggestion, qs)


def _dump_contract_data(symbol: str, expiry_date: str):
    from apps.data.models import ContractData

    qs = ContractData.objects.filter(symbol=symbol)
    if expiry_date:
        qs = qs.filter(expiry=expiry_date)
    qs = qs.order_by('-updated_at')[:20]

    return _dump_source('Trendlyne F&O Contract Data', ContractData, qs)


def _dump_contract_stock_data(symbol: str, expiry_date: str):
    from apps.data.models import ContractStockData

    qs = ContractStockData.objects.filter(nse_code=symbol)[:5]

    return _dump_source('Trendlyne Stock-Level F&O Summary', ContractStockData, qs)


def _dump_tl_stock_data(symbol: str, expiry_date: str):
    from apps.data.models import TLStockData

    qs = TLStockData.objects.filter(nsecode=symbol)[:5]

    return _dump_source('Trendlyne Comprehensive Stock Data (fundamentals/technicals)', TLStockData, qs)


def _dump_analyst_price_target(symbol: str, expiry_date: str):
    from apps.data.models import AnalystPriceTarget

    qs = AnalystPriceTarget.objects.filter(symbol=symbol).order_by('-fetch_timestamp')[:5]

    return _dump_source('Trendlyne Analyst Price Targets (consensus)', AnalystPriceTarget, qs)


def _dump_historical_price(symbol: str, expiry_date: str):
    from apps.brokers.models import HistoricalPrice

    qs = HistoricalPrice.objects.filter(stock_code=symbol)
    if expiry_date:
        qs = qs.filter(expiry_date=expiry_date)
    qs = qs.order_by('-datetime')[:20]

    return _dump_source('Breeze Historical Price (cached OHLCV)', HistoricalPrice, qs)


def _dump_option_chain_quotes(symbol: str, expiry_date: str):
    from apps.brokers.models import OptionChainQuote

    qs = OptionChainQuote.objects.filter(stock_code=symbol)
    if expiry_date:
        qs = qs.filter(expiry_date=expiry_date)
    qs = qs.order_by('-updated_at')[:20]

    return _dump_source('Breeze Option Chain Quotes (cached snapshots)', OptionChainQuote, qs)


def _dump_news_articles(symbol: str, expiry_date: str):
    from apps.data.models import NewsArticle

    # SQLite JSONField doesn't support __contains for arrays; use __icontains string match.
    # Exclude NSE/BSE filings - those get their own section via _dump_exchange_announcements.
    qs = NewsArticle.objects.filter(
        symbols_mentioned__icontains=f'"{symbol}"'
    ).exclude(source__in=['NSE', 'BSE']).order_by('-published_at')[:20]

    return _dump_source('News Articles (with LLM sentiment/impact)', NewsArticle, qs)


def _dump_analyst_reports(symbol: str, expiry_date: str):
    from apps.data.models import AnalystReport

    qs = AnalystReport.objects.filter(symbol=symbol).order_by('-report_date')[:10]

    return _dump_source('Analyst Research Reports (Trendlyne PDFs, LLM-analyzed)', AnalystReport, qs)


def _dump_investor_calls(symbol: str, expiry_date: str):
    from apps.data.models import InvestorCall

    qs = InvestorCall.objects.filter(symbol=symbol).order_by('-call_date')[:5]

    return _dump_source('Investor Calls / Earnings Transcripts', InvestorCall, qs)


def _dump_oi_intelligence(symbol: str, expiry_date: str):
    from apps.data.models import OIIntelligence

    qs = OIIntelligence.objects.filter(symbol=symbol).order_by('-trading_date')[:5]

    return _dump_source('OI Intelligence (derived buildup/pattern analysis)', OIIntelligence, qs)


def _dump_oi_history(symbol: str, expiry_date: str):
    from apps.data.models import OIHistorySnapshot

    qs = OIHistorySnapshot.objects.filter(symbol=symbol).order_by('-trading_date')[:20]

    return _dump_source('OI History Snapshots (daily, raw)', OIHistorySnapshot, qs)


def _dump_exchange_announcements(symbol: str, expiry_date: str):
    # NSE/BSE filings are stored as NewsArticle rows (source='NSE'/'BSE') by
    # ExchangeFilingsClient - split out from _dump_news_articles into their own
    # section so exchange-grade announcements aren't buried among GNews articles.
    from apps.data.models import NewsArticle

    qs = NewsArticle.objects.filter(
        source__in=['NSE', 'BSE'],
        symbols_mentioned__icontains=f'"{symbol}"',
    ).order_by('-published_at')[:20]

    return _dump_source('NSE/BSE Corporate Announcements', NewsArticle, qs)
