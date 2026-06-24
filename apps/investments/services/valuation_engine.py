from __future__ import annotations
import logging
from datetime import date
from decimal import Decimal

logger = logging.getLogger('apps.investments')


def compute_product_value(product) -> Decimal:
    """Compute and save current_value for a product based on its type and extra_data."""
    try:
        value = _compute(product)
        if value is not None:
            product.current_value = value
            product.as_of_date = date.today()
            product.save(update_fields=['current_value', 'as_of_date', 'gain_loss', 'updated_at'])
        return product.current_value
    except Exception as e:
        logger.error('Valuation error for product %d (%s): %s', product.id, product.product_type, e)
        return product.current_value


def _compute(product) -> Decimal | None:
    ptype = product.product_type
    ed = product.extra_data or {}

    if ptype == 'MUTUAL_FUND':
        return _mf_value(ed)
    elif ptype == 'EQUITY':
        return _equity_value(product.isin, ed)
    elif ptype == 'SGB':
        return _sgb_value(ed)
    elif ptype == 'FD':
        return _fd_value(ed)
    elif ptype == 'RD':
        return _rd_value(ed)
    elif ptype == 'PHYSICAL_GOLD':
        return _gold_value(ed)
    elif ptype == 'BOND':
        return _bond_value(ed)
    # PPF, EPF, NPS, REAL_ESTATE, CASH, SAVINGS, CRYPTO — manual entry only
    return None


def _mf_value(ed: dict) -> Decimal | None:
    units = ed.get('units')
    nav = ed.get('nav')
    if units is not None and nav is not None:
        return Decimal(str(units)) * Decimal(str(nav))
    return None


def _equity_value(isin: str, ed: dict) -> Decimal | None:
    from apps.investments.models import EquityPrice
    shares = ed.get('shares')
    if not shares:
        return None
    latest = EquityPrice.objects.filter(isin=isin).order_by('-date').first()
    if latest:
        return Decimal(str(shares)) * latest.price
    return None


def _sgb_value(ed: dict) -> Decimal | None:
    units = ed.get('units')
    gold_price = ed.get('gold_price')
    if units and gold_price:
        # SGB face value = 1 gram of gold per unit
        return Decimal(str(units)) * Decimal(str(gold_price))
    return None


def _fd_value(ed: dict) -> Decimal | None:
    principal = ed.get('principal')
    rate = ed.get('interest_rate')  # annual %, e.g. 7.5
    start_date_str = ed.get('start_date')
    compounding = ed.get('compounding', 'quarterly')

    if not all([principal, rate, start_date_str]):
        return Decimal(str(principal)) if principal else None

    from datetime import datetime
    try:
        start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    except ValueError:
        return Decimal(str(principal))

    today = date.today()
    years = (today - start).days / 365.0
    r = float(rate) / 100
    p = float(principal)

    n_map = {'monthly': 12, 'quarterly': 4, 'annually': 1, 'simple': None}
    n = n_map.get(compounding, 4)

    if n is None:
        # Simple interest
        value = p * (1 + r * years)
    else:
        value = p * ((1 + r / n) ** (n * years))

    return Decimal(str(round(value, 2)))


def _rd_value(ed: dict) -> Decimal | None:
    monthly = ed.get('monthly_amount')
    rate = ed.get('interest_rate')
    start_date_str = ed.get('start_date')
    tenure_months = ed.get('tenure_months')

    if not all([monthly, rate, start_date_str]):
        return None

    from datetime import datetime
    try:
        start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    except ValueError:
        return None

    today = date.today()
    months_elapsed = min(
        (today.year - start.year) * 12 + (today.month - start.month),
        int(tenure_months or 999)
    )
    r = float(rate) / 100 / 12
    m = float(monthly)

    if r == 0:
        return Decimal(str(m * months_elapsed))
    value = m * (((1 + r) ** months_elapsed - 1) / r) * (1 + r)
    return Decimal(str(round(value, 2)))


def _gold_value(ed: dict) -> Decimal | None:
    grams = ed.get('quantity_grams')
    purity = ed.get('purity', '24K')
    gold_price = ed.get('gold_price_per_gram')  # cached from last price update

    if not (grams and gold_price):
        return None

    purity_factor = {'24K': 1.0, '22K': 22 / 24, '18K': 18 / 24}.get(purity, 1.0)
    return Decimal(str(round(float(grams) * purity_factor * float(gold_price), 2)))


def _bond_value(ed: dict) -> Decimal | None:
    face_value = ed.get('face_value')
    units = ed.get('units')
    market_price_pct = ed.get('market_price_pct', 100)  # % of face value

    if face_value and units:
        return Decimal(str(face_value)) * Decimal(str(units)) * Decimal(str(market_price_pct)) / 100
    return None
