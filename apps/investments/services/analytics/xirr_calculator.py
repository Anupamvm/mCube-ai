from __future__ import annotations
import logging
from datetime import date, datetime
from decimal import Decimal
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


def compute_product_xirr(product) -> float | None:
    """Build cashflows from a product's transactions and current value."""
    from apps.investments.models import Transaction

    txns = Transaction.objects.filter(
        product=product,
        transaction_type__in=['PURCHASE', 'SALE', 'SIP', 'SWP'],
    ).order_by('transaction_date')

    if not txns.exists():
        # Fallback: single investment → current value
        if product.invested_value and product.current_value:
            cashflows = [
                (product.created_at.date() if product.created_at else date.today(), -float(product.invested_value)),
                (date.today(), float(product.current_value)),
            ]
            return compute_xirr(cashflows)
        return None

    cashflows = []
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
        cashflows.append((date.today(), float(product.current_value)))
        return compute_xirr(cashflows)
    return None
