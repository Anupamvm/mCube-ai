from __future__ import annotations
import logging
import math
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

    # XIRR is undefined with zero elapsed time between cashflows (e.g. a
    # freshly-imported holding with no transaction history, where the only
    # available data is a synthetic investment outflow dated today and a
    # current-value inflow also dated today). pyxirr doesn't reliably raise
    # for this — it can return inf, an absurd finite rate, or an arbitrary
    # boundary value like exactly -1.0 depending on the amounts — so guard
    # the actual degenerate condition directly rather than the symptoms.
    if len(set(dates)) < 2:
        return None

    try:
        result = _xirr(dates, amounts)
        if result is None or result != result or math.isinf(result):  # NaN / inf check
            return None
        # A near-zero time span between cashflows (e.g. a fund "invested" and
        # revalued on the same day) can make the solver converge to an
        # absurdly large but finite rate, which then overflows the Decimal
        # field it gets saved to. Treat anything beyond a sane bound as
        # undefined rather than letting it crash the save.
        if abs(result) > 100:  # >10,000% annualised
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
    total_purchases = 0.0
    for txn in txns:
        if txn.amount is not None:
            amount = float(txn.amount)
            if txn.transaction_type in ('PURCHASE', 'SIP'):
                cashflows.append((txn.transaction_date, -amount))
                total_purchases += amount
            elif txn.transaction_type in ('SALE', 'SWP'):
                cashflows.append((txn.transaction_date, amount))
        elif txn.nav_at_transaction:
            # NSDL CAS: compute from units × NAV
            units = float(txn.units_credit - txn.units_debit)
            amount = abs(units) * float(txn.nav_at_transaction)
            sign = -1 if txn.transaction_type in ('PURCHASE', 'SIP') else 1
            cashflows.append((txn.transaction_date, sign * amount))
            if txn.transaction_type in ('PURCHASE', 'SIP'):
                total_purchases += amount

    if cashflows:
        # MF Central (and similar) CAS exports only report transactions
        # within the queried date window — a fund invested earlier shows up
        # purely as an aggregate invested_value with no transaction backing.
        # If known purchases cover only a fraction of invested_value, the
        # visible window is materially incomplete: computing XIRR from it
        # (against the FULL current value) produces a wrong — sometimes
        # wrong-signed — annualised rate, not just an imprecise one (e.g. a
        # fund at an overall loss can appear to have a large positive XIRR).
        # Safer to report "not computable" than a misleading number.
        if product.invested_value and total_purchases < float(product.invested_value) * 0.9:
            return []
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
    today = date.today()
    for product in products:
        product_cashflows = _product_cashflows(product)
        if not product_cashflows:
            # No usable cashflow history for this product (including the
            # "known purchases don't cover invested_value" case) — exclude
            # it entirely rather than counting its current_value without any
            # matching outflow, which would skew the whole group's XIRR the
            # same way a single incomplete fund would skew its own.
            continue
        if all(d == today for d, _ in product_cashflows):
            # This product has no real transaction history at all and fell
            # back to a single synthetic "invested today" cashflow (no
            # investment_date on record). For a single product that's caught
            # by compute_xirr's same-date guard once the terminal value is
            # appended — but pooled with OTHER products' genuinely dated
            # cashflows, the group as a whole no longer looks same-dated, so
            # the guard never fires and this product's full current_value
            # would be counted as if it appeared overnight. Exclude it here
            # for the same reason as an empty history.
            continue
        cashflows.extend(product_cashflows)
        total_current += float(product.current_value)

    if not cashflows:
        return None

    cashflows.append((today, total_current))
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
