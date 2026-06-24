import logging
import numpy as np
import pandas as pd
from django.conf import settings

logger = logging.getLogger('apps.investments')

RISK_FREE_RATE = getattr(settings, 'INVESTMENTS_RISK_FREE_RATE', 0.065)


def compute_risk_metrics(nav_queryset) -> dict:
    """
    Compute risk metrics from a NAVHistory queryset ordered by date ascending.
    Returns dict with sharpe, sortino, std_dev, max_drawdown, beta, alpha.
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

    # Beta vs Nifty 50 (fetch via yfinance if available)
    beta, alpha = _compute_beta_alpha(returns, dates[1:])

    return {
        'sharpe_ratio': round(float(sharpe), 4),
        'sortino_ratio': round(float(sortino), 4),
        'std_dev_annual': round(annual_std, 4),
        'max_drawdown': round(max_drawdown, 4),
        'beta': round(beta, 4) if beta is not None else None,
        'alpha_annual': round(alpha, 4) if alpha is not None else None,
        'data_points': len(returns),
    }


def _compute_beta_alpha(scheme_returns: pd.Series, dates: list) -> tuple:
    try:
        import yfinance as yf
        start = pd.to_datetime(dates[0]) if dates else None
        end = pd.to_datetime(dates[-1]) if dates else None
        nifty = yf.download('^NSEI', start=start, end=end, progress=False, auto_adjust=True)
        if nifty.empty:
            return None, None

        nifty_returns = nifty['Close'].pct_change().dropna()
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
