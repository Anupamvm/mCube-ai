"""
Single source of truth for every Cover Position safety rule.

Called as SOFT checks (return warnings, don't block) from preview endpoints,
and as HARD checks (raise HedgeValidationError) from the actual
place/roll/close execution paths in execution_service.py — except
validate_margin, which is advisory everywhere (see its docstring). Never
trust a client-supplied number for a hard check — execution_service
re-fetches live data (futures qty) before calling into here.
"""
import datetime
from typing import List, Optional, Tuple

from django.core.cache import cache

from apps.accounts.models import BrokerAccount
from apps.hedging.models import HEDGE_STATUS_ACTIVE, HedgePosition

MIN_OI_WARNING_THRESHOLD = 500
MAX_SPREAD_PCT_WARNING = 5.0
PLACEMENT_LOCK_TIMEOUT_SECONDS = 30


class HedgeValidationError(Exception):
    """Raised by hard validation checks. `code` is machine-readable, `message` is user-facing."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_quantity_cap(live_futures_lots: int, already_covered_lots: int, requested_lots: int) -> None:
    """
    Never allow selling more calls than the futures lots actually held and
    not already covered. `live_futures_lots` and `already_covered_lots` must
    both come from a fresh broker/DB read at call time, not client input.
    """
    uncovered = live_futures_lots - already_covered_lots
    if requested_lots <= 0:
        raise HedgeValidationError('INVALID_QUANTITY', "Quantity must be a positive number of lots.")
    if requested_lots > uncovered:
        raise HedgeValidationError(
            'QTY_EXCEEDS_UNCOVERED',
            f"Requested {requested_lots} lots exceeds {uncovered} uncovered futures lots "
            f"({live_futures_lots} held, {already_covered_lots} already covered).",
        )


def validate_expiry_alignment(option_expiry_date: datetime.date, futures_expiry_date: datetime.date) -> None:
    """The option's expiry may be nearer than the futures expiry (e.g. a weekly
    call against a monthly future) but must never be after it — you can't hedge
    past the life of the position you're hedging."""
    if option_expiry_date > futures_expiry_date:
        raise HedgeValidationError(
            'EXPIRY_MISMATCH',
            f"Option expiry {option_expiry_date} is after the futures expiry "
            f"{futures_expiry_date} — cannot hedge past the futures contract's own expiry.",
        )


def validate_lot_size_match(option_lot_size: int, futures_lot_size: int) -> None:
    if option_lot_size != futures_lot_size:
        raise HedgeValidationError(
            'LOT_SIZE_MISMATCH',
            f"Option lot size ({option_lot_size}) does not match the futures contract's "
            f"lot size ({futures_lot_size}) for this symbol — refusing to place an order "
            f"that would leave the hedge under- or over-sized.",
        )


def build_placement_lock_key(user_id: int, broker: str, symbol: str, strike, expiry) -> str:
    return f"hedge_place_lock_{user_id}_{broker}_{symbol}_{strike}_{expiry}"


def acquire_placement_lock(user_id: int, broker: str, symbol: str, strike, expiry) -> Tuple[bool, str]:
    """
    Atomic duplicate-order guard. Returns (acquired, lock_key). Caller must
    release_placement_lock() in a finally block once the order attempt
    (success or failure) is complete — the TTL is only a safety net for a
    crashed request, not the primary release mechanism.
    """
    lock_key = build_placement_lock_key(user_id, broker, symbol, strike, expiry)
    acquired = cache.add(lock_key, '1', timeout=PLACEMENT_LOCK_TIMEOUT_SECONDS)
    return acquired, lock_key


def release_placement_lock(lock_key: str) -> None:
    cache.delete(lock_key)


def find_existing_active_hedge(
    broker: str, underlying_symbol: str, futures_expiry_date: datetime.date,
) -> Optional[HedgePosition]:
    """
    Only one ACTIVE HedgePosition is allowed per (broker, symbol,
    futures_expiry). If one exists, execution_service should attach a new
    leg to it (still subject to the quantity cap) rather than creating a
    second, independent campaign against the same futures position.
    """
    return HedgePosition.objects.filter(
        broker=broker,
        underlying_symbol=underlying_symbol,
        futures_expiry_date=futures_expiry_date,
        status=HEDGE_STATUS_ACTIVE,
    ).first()


def validate_margin(account: BrokerAccount, required_margin) -> Tuple[bool, str]:
    """
    Advisory only, not a hard gate — execution_service surfaces the result as
    a warning rather than a blocking_issue. check_margin_availability's
    required_margin estimate treats every sell as a naked short call and
    doesn't credit the margin relief a real broker gives for a call sold
    against the long future it's covering, so it can't be trusted to hard-block
    a risk-reducing covered-call trade (same rationale as assess_liquidity_warnings).
    """
    from apps.accounts.services.margin_manager import check_margin_availability
    return check_margin_availability(account, required_margin)


def assess_liquidity_warnings(chain_row: dict) -> List[str]:
    """
    Non-blocking. A capital-preservation tool shouldn't hard-block a user
    trying to reduce risk on a thin strike — but the numbers must be visible
    so they can make an informed choice.
    """
    warnings: List[str] = []
    oi = chain_row.get('open_interest') or 0
    bid = chain_row.get('bid') or chain_row.get('best_bid_price') or 0
    ask = chain_row.get('ask') or chain_row.get('best_offer_price') or 0

    if oi < MIN_OI_WARNING_THRESHOLD:
        warnings.append(f"Low open interest ({oi}) at this strike — may be illiquid.")

    if bid and ask:
        mid = (bid + ask) / 2
        if mid > 0:
            spread_pct = ((ask - bid) / mid) * 100
            if spread_pct > MAX_SPREAD_PCT_WARNING:
                warnings.append(
                    f"Wide bid-ask spread ({spread_pct:.1f}%) at this strike — "
                    f"a market order may fill at an unfavorable price. Consider a limit order."
                )
    else:
        warnings.append("Missing bid/ask quotes for this strike — verify liquidity before placing a market order.")

    return warnings
