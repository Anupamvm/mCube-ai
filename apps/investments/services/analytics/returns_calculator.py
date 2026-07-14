from __future__ import annotations
from datetime import timedelta

# (label, days) — CAGR is only meaningful once the period spans a full year.
_PERIODS = [
    ('1W', 7), ('1M', 30), ('3M', 91), ('6M', 182),
    ('1Y', 365), ('3Y', 365 * 3), ('5Y', 365 * 5),
]


def compute_trailing_returns(nav_queryset) -> dict:
    """
    Point-to-point trailing returns for a scheme, over standard advisor-facing
    windows. Periods with insufficient NAV history are simply omitted rather
    than guessed at with whatever's available.
    """
    points = list(nav_queryset.order_by('date').values_list('date', 'nav'))
    if len(points) < 2:
        return {}

    latest_date, latest_nav = points[-1]
    latest_nav = float(latest_nav)
    if latest_nav <= 0:
        return {}

    result = {}
    for label, days in _PERIODS:
        target_date = latest_date - timedelta(days=days)
        base = None
        for d, nav in points:
            if d <= target_date:
                base = (d, nav)
            else:
                break
        if base is None:
            continue

        base_date, base_nav = base
        base_nav = float(base_nav)
        if base_nav <= 0:
            continue

        entry = {
            'return_pct': round((latest_nav - base_nav) / base_nav * 100, 2),
            'from_date': str(base_date),
            'to_date': str(latest_date),
        }
        if days >= 365:
            years = days / 365.0
            entry['cagr_pct'] = round(((latest_nav / base_nav) ** (1 / years) - 1) * 100, 2)
        result[label] = entry

    return result
