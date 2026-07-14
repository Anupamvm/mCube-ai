import logging
import numpy as np
import pandas as pd
from django.conf import settings

logger = logging.getLogger('apps.investments')

RISK_FREE_RATE = getattr(settings, 'INVESTMENTS_RISK_FREE_RATE', 0.065)

# Comparing every fund's beta/alpha against Nifty 50 regardless of what it
# actually invests in is misleading (a midcap or sectoral fund isn't trying
# to track large caps). Map AMFI sub-categories to a more representative
# index where a liquid, long-history yfinance ticker actually exists.
# No reliable free smallcap index history exists on yfinance, so small cap
# and anything without a good dedicated proxy falls back to the broadest
# market index (Nifty 500) rather than Nifty 50.
DEFAULT_BENCHMARK = '^NSEI'       # Nifty 50
_BROAD_MARKET_BENCHMARK = '^CRSLDX'  # Nifty 500
_CATEGORY_BENCHMARKS = {
    'large cap fund': DEFAULT_BENCHMARK,
    'mid cap fund': '^NSEMDCP50',        # Nifty Midcap 150
    'large & mid cap fund': _BROAD_MARKET_BENCHMARK,
    'small cap fund': _BROAD_MARKET_BENCHMARK,
    'multi cap fund': _BROAD_MARKET_BENCHMARK,
    'flexi cap fund': _BROAD_MARKET_BENCHMARK,
    'focused fund': _BROAD_MARKET_BENCHMARK,
    'value fund': _BROAD_MARKET_BENCHMARK,
    'contra fund': _BROAD_MARKET_BENCHMARK,
    'dividend yield fund': _BROAD_MARKET_BENCHMARK,
    'elss': _BROAD_MARKET_BENCHMARK,
}
# Keyword override for sectoral/thematic funds where the theme itself maps
# cleanly to a liquid index (checked against the scheme name).
_SECTOR_KEYWORD_BENCHMARKS = [
    (('banking', 'financial services', 'psu bank'), '^NSEBANK'),
]


def resolve_benchmark_ticker(sub_category: str = '', scheme_name: str = '') -> str:
    name_lower = (scheme_name or '').lower()
    for keywords, ticker in _SECTOR_KEYWORD_BENCHMARKS:
        if any(k in name_lower for k in keywords):
            return ticker
    return _CATEGORY_BENCHMARKS.get((sub_category or '').strip().lower(), DEFAULT_BENCHMARK)


def compute_risk_metrics(nav_queryset, sub_category: str = '', scheme_name: str = '') -> dict:
    """
    Compute risk metrics from a NAVHistory queryset ordered by date ascending.
    Returns dict with sharpe, sortino, std_dev, max_drawdown, beta, alpha.
    `sub_category`/`scheme_name` pick a representative benchmark for beta/alpha
    (e.g. Nifty Midcap 150 for a mid cap fund) instead of always using Nifty 50.
    """
    data = list(nav_queryset.values_list('date', 'nav').order_by('date'))
    if len(data) < 30:
        return {}

    dates = [d[0] for d in data]
    navs = [float(d[1]) for d in data]

    series = pd.Series(navs, index=pd.to_datetime(dates))
    returns = series.pct_change().dropna()

    if len(returns) < 20:
        return {}

    annual_factor = np.sqrt(252)
    rf_daily = RISK_FREE_RATE / 252

    mean_return = returns.mean()
    std_dev = returns.std()
    sharpe = ((mean_return - rf_daily) / std_dev * annual_factor) if std_dev else 0

    downside = returns[returns < rf_daily]
    downside_std = downside.std() if len(downside) > 1 else std_dev
    sortino = ((mean_return - rf_daily) / downside_std * annual_factor) if downside_std else 0

    # Max Drawdown
    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    max_drawdown = float(drawdown.min())

    # Annualised std dev
    annual_std = float(std_dev * annual_factor)

    benchmark_ticker = resolve_benchmark_ticker(sub_category, scheme_name)
    beta, alpha = _compute_beta_alpha(returns, dates[1:], benchmark_ticker)

    return {
        'sharpe_ratio': round(float(sharpe), 4),
        'sortino_ratio': round(float(sortino), 4),
        'std_dev_annual': round(annual_std, 4),
        'max_drawdown': round(max_drawdown, 4),
        'beta': round(beta, 4) if beta is not None else None,
        'alpha_annual': round(alpha, 4) if alpha is not None else None,
        'benchmark': benchmark_ticker,
        'data_points': len(returns),
    }


def _compute_beta_alpha(scheme_returns: pd.Series, dates: list, benchmark_ticker: str = DEFAULT_BENCHMARK) -> tuple:
    try:
        import yfinance as yf
        start = pd.to_datetime(dates[0]) if dates else None
        end = pd.to_datetime(dates[-1]) if dates else None
        benchmark = yf.download(benchmark_ticker, start=start, end=end, progress=False, auto_adjust=True)
        if benchmark.empty:
            return None, None

        # Newer yfinance versions return MultiIndex columns (Price, Ticker)
        # even for a single symbol, making benchmark['Close'] a 1-column
        # DataFrame rather than a Series — squeeze() normalizes both cases.
        benchmark_close = benchmark['Close'].squeeze()
        nifty_returns = benchmark_close.pct_change().dropna()
        aligned = pd.concat([scheme_returns, nifty_returns], axis=1, join='inner')
        aligned.columns = ['scheme', 'nifty']

        if len(aligned) < 20:
            return None, None

        cov_matrix = np.cov(aligned['scheme'], aligned['nifty'])
        beta = cov_matrix[0, 1] / cov_matrix[1, 1]
        alpha = float((scheme_returns.mean() - beta * nifty_returns.mean()) * 252)
        return float(beta), alpha
    except Exception as e:
        logger.debug('Beta/alpha computation failed: %s', e)
        return None, None
