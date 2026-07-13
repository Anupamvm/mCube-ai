from __future__ import annotations
import logging
from datetime import date
from typing import Iterable
from pyxirr import xirr as _xirr, InvalidPaymentsError

logger = logging.getLogger('apps.investments')


def compute_xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """
    cashflows: list of (date, amount) where:
      - negative amounts = outflow (investments)
      - positive amounts = inflow (redemptions + current value)
    Returns annualised XIRR as a decimal (e.g. 0.1234 = 12.34%) or None on failure.
    """
    if len(cashflows) < 2:
        return None

    dates = [c[0] for c in cashflows]
    amounts = [c[1] for c in cashflows]

    has_positive = any(a > 0 for a in amounts)
    has_negative = any(a < 0 for a in amounts)
    if not (has_positive and has_negative):
        return None

    try:
        result = _xirr(dates, amounts)
        if result is None or result != result:  # NaN check
            return None
        return round(float(result), 6)
    except (InvalidPaymentsError, ValueError, ZeroDivisionError) as e:
        logger.debug('XIRR computation failed: %s', e)
        return None


def _product_cashflows(product) -> list[tuple[date, float]]:
    """
    Investment cashflows for a single product (purchases/sales), excluding the
    terminal current-value inflow. Falls back to a single synthetic outflow at
    product.investment_date when there's no transaction history (manual assets,
    CSV/portfolio imports without full history).
    """
    from apps.investments.models import Transaction

    txns = Transaction.objects.filter(
        product=product,
        transaction_type__in=['PURCHASE', 'SALE', 'SIP', 'SWP'],
    ).order_by('transaction_date')

    cashflows: list[tuple[date, float]] = []
    for txn in txns:
        if txn.amount is not None:
            if txn.transaction_type in ('PURCHASE', 'SIP'):
                cashflows.append((txn.transaction_date, -float(txn.amount)))
            elif txn.transaction_type in ('SALE', 'SWP'):
                cashflows.append((txn.transaction_date, float(txn.amount)))
        elif txn.nav_at_transaction:
            # NSDL CAS: compute from units × NAV
            units = float(txn.units_credit - txn.units_debit)
            amount = abs(units) * float(txn.nav_at_transaction)
            sign = -1 if txn.transaction_type in ('PURCHASE', 'SIP') else 1
            cashflows.append((txn.transaction_date, sign * amount))

    if cashflows:
        return cashflows

    if product.invested_value:
        invest_date = product.investment_date or (
            product.created_at.date() if product.created_at else date.today()
        )
        return [(invest_date, -float(product.invested_value))]
    return []


def compute_product_xirr(product) -> float | None:
    """XIRR for a single product's own cashflows plus its current value."""
    cashflows = _product_cashflows(product)
    if not cashflows:
        return None
    cashflows.append((date.today(), float(product.current_value)))
    return compute_xirr(cashflows)


def compute_products_xirr(products: Iterable) -> float | None:
    """
    Aggregate XIRR across many products — the shared aggregator behind account-,
    member-, family-, and fund-level XIRR. Flattens each product's own cashflows
    and appends a single terminal inflow of their combined current value.
    """
    products = list(products)
    cashflows: list[tuple[date, float]] = []
    total_current = 0.0
    for product in products:
        cashflows.extend(_product_cashflows(product))
        total_current += float(product.current_value)

    if not cashflows:
        return None

    cashflows.append((date.today(), total_current))
    return compute_xirr(cashflows)


def compute_account_xirr(account) -> float | None:
    return compute_products_xirr(account.products.filter(is_active=True))


def compute_member_xirr(member) -> float | None:
    from apps.investments.models import InvestmentProduct

    products = InvestmentProduct.objects.filter(
        investment_account__family_member=member, is_active=True,
    )
    return compute_products_xirr(products)


def compute_family_xirr(members) -> float | None:
    from apps.investments.models import InvestmentProduct

    products = InvestmentProduct.objects.filter(
        investment_account__family_member__in=members, is_active=True,
    )
    return compute_products_xirr(products)


def compute_fund_xirr(isin: str, members=None) -> float | None:
    """XIRR for all of the given members' holdings of a single ISIN (across accounts)."""
    from apps.investments.models import InvestmentProduct

    products = InvestmentProduct.objects.filter(isin=isin, is_active=True)
    if members is not None:
        products = products.filter(investment_account__family_member__in=members)
    return compute_products_xirr(products)
