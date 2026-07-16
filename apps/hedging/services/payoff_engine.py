"""
Pure payoff/breakeven math for the Covered Call Protection feature.

Deliberately has ZERO Django imports so it can be:
  1. unit-tested in isolation (apps/hedging/tests/test_payoff_engine.py), and
  2. mirrored, function-for-function, in
     apps/hedging/static/hedging/js/payoff_calculator.js so the "at expiry"
     payoff graph in the Cover Position modal updates instantly on every
     strike/quantity slider tick without a network round trip.

Money in/out of these functions is plain `float`, not `Decimal` — this
module feeds charts and live previews, not ledger entries. Anything that
gets persisted (HedgeLeg.premium_per_share, HedgeLeg.charges, etc.) is
stored as Decimal on the model layer; charges_calculator.py (which touches
real settlement amounts) uses Decimal throughout for that reason. Keep it
that way — don't "fix" this file to use Decimal, it would just make the JS
mirror harder to keep in sync for zero real benefit.
"""
from typing import List, Optional, Sequence, TypedDict


class PayoffPoint(TypedDict):
    spot: float
    futures_pnl: float
    call_pnl: float
    total_pnl: float


def calculate_effective_breakeven(
    futures_avg_price: float,
    lots_covered: int,
    lot_size: int,
    net_premium_collected: float,
) -> float:
    """
    Effective breakeven = futures avg price minus premium collected per share.

    This is THE number the whole feature exists to show: the price the
    underlying needs to be at (or above) for the combined futures + covered
    call position to be flat, after accounting for premium already banked.
    """
    covered_shares = lots_covered * lot_size
    if covered_shares <= 0:
        return futures_avg_price
    return futures_avg_price - (net_premium_collected / covered_shares)


def _call_leg_pnl_at_spot(
    spot: float,
    call_strike: float,
    call_premium: float,
    call_lots: int,
    lot_size: int,
) -> float:
    """P&L of a SHORT call leg (premium received, capped upside) at a given spot."""
    if call_lots <= 0:
        return 0.0
    if spot <= call_strike:
        # Expires worthless (or is bought back for ~0) — seller keeps full premium.
        payoff_per_share = call_premium
    else:
        # Assigned / bought back for intrinsic value; premium partially offsets it.
        payoff_per_share = call_premium - (spot - call_strike)
    return payoff_per_share * call_lots * lot_size


def calculate_payoff_at_expiry(
    spot_range: Sequence[float],
    futures_avg_price: float,
    futures_lots: int,
    lot_size: int,
    call_strike: float,
    call_premium: float,
    call_lots: int,
) -> List[PayoffPoint]:
    """
    Pure algebra: long-futures payoff + short-call payoff, at expiry, across
    a range of hypothetical spot prices. No Greeks/IV needed — this is what
    lets the UI redraw the payoff graph on every slider tick with zero
    backend latency.
    """
    points: List[PayoffPoint] = []
    for spot in spot_range:
        futures_pnl = (spot - futures_avg_price) * futures_lots * lot_size
        call_pnl = _call_leg_pnl_at_spot(spot, call_strike, call_premium, call_lots, lot_size)
        points.append({
            "spot": spot,
            "futures_pnl": futures_pnl,
            "call_pnl": call_pnl,
            "total_pnl": futures_pnl + call_pnl,
        })
    return points


def is_fully_capped(futures_lots: int, call_lots: int) -> bool:
    """
    Upside is only truly capped (flat plateau above the strike) when every
    futures lot is covered. Partial coverage still leaves the uncovered
    lots free to run — there is no single "max profit" point in that case.
    """
    return call_lots >= futures_lots > 0


def calculate_max_profit(
    futures_avg_price: float,
    futures_lots: int,
    lot_size: int,
    call_strike: float,
    call_premium: float,
    call_lots: int,
) -> Optional[float]:
    """
    Returns the capped max profit if the position is fully covered
    (call_lots >= futures_lots), else None to signal genuinely unlimited
    upside on the uncovered portion — callers must render that distinction,
    not silently substitute a number.
    """
    if not is_fully_capped(futures_lots, call_lots):
        return None
    futures_pnl_at_strike = (call_strike - futures_avg_price) * futures_lots * lot_size
    call_pnl_at_strike = _call_leg_pnl_at_spot(call_strike, call_strike, call_premium, call_lots, lot_size)
    return futures_pnl_at_strike + call_pnl_at_strike


def calculate_capped_upside_price(
    futures_lots: int,
    call_strike: float,
    call_lots: int,
) -> Optional[float]:
    """The spot price at which profit plateaus, if fully covered; else None."""
    if not is_fully_capped(futures_lots, call_lots):
        return None
    return call_strike


def calculate_protection_metrics(
    futures_avg_price: float,
    current_spot: float,
    net_premium_collected: float,
    lots_covered: int,
    lot_size: int,
) -> dict:
    """
    How much of the CURRENT open loss (if any) does the premium already
    collected offset? Purely descriptive — used in the preview panel to
    answer "how much damage control did this actually buy me."
    """
    covered_shares = lots_covered * lot_size
    open_loss_per_share = max(futures_avg_price - current_spot, 0.0)
    premium_per_share = (net_premium_collected / covered_shares) if covered_shares > 0 else 0.0
    if open_loss_per_share <= 0:
        protection_pct = None  # position isn't underwater; "protection" isn't a meaningful ratio
    else:
        protection_pct = min(premium_per_share / open_loss_per_share, 1.0) * 100.0
    return {
        "open_loss_per_share": open_loss_per_share,
        "premium_per_share": premium_per_share,
        "protection_pct": protection_pct,
    }


def find_zero_crossings(curve: Sequence[PayoffPoint]) -> List[float]:
    """
    Linear-interpolated spot price(s) where total_pnl crosses zero, so the
    UI can mark the exact breakeven point(s) on the payoff graph rather than
    just showing the effective_breakeven number in isolation.
    """
    crossings: List[float] = []
    for prev_point, curr_point in zip(curve, curve[1:]):
        prev_pnl, curr_pnl = prev_point["total_pnl"], curr_point["total_pnl"]
        if prev_pnl == 0:
            crossings.append(prev_point["spot"])
            continue
        if (prev_pnl < 0) != (curr_pnl < 0):
            prev_spot, curr_spot = prev_point["spot"], curr_point["spot"]
            fraction = prev_pnl / (prev_pnl - curr_pnl)
            crossings.append(prev_spot + fraction * (curr_spot - prev_spot))
    return crossings


def calculate_today_mtm_curve(
    spot_range: Sequence[float],
    current_spot: float,
    futures_avg_price: float,
    futures_lots: int,
    lot_size: int,
    call_strike: float,
    call_premium_now: float,
    call_lots: int,
    call_delta: float,
    call_theta: float,
    days_elapsed: float = 0.0,
) -> dict:
    """
    Approximate "today" mark-to-market curve using a first-order Greeks
    move (delta * spot change) plus theta decay over `days_elapsed`. This is
    NOT a full per-point Black-Scholes reprice (that would need IV per
    strike and is overkill for a rough "today" reference line) — it is
    explicitly an approximation, flagged as such in the returned dict so
    the API/UI never present it as precise as the at-expiry curve.

    `call_theta` is expected in the same sign convention as
    apps.strategies.services.greeks_calculator (negative = value lost per
    day held long); since we are SHORT the call, that decay is a gain for
    this position, hence it reduces the estimated buy-back price.
    """
    points: List[PayoffPoint] = []
    for spot in spot_range:
        futures_pnl = (spot - futures_avg_price) * futures_lots * lot_size
        estimated_call_price = max(
            call_premium_now
            + call_delta * (spot - current_spot)
            + call_theta * days_elapsed,
            0.0,
        )
        call_pnl = (call_premium_now - estimated_call_price) * call_lots * lot_size
        points.append({
            "spot": spot,
            "futures_pnl": futures_pnl,
            "call_pnl": call_pnl,
            "total_pnl": futures_pnl + call_pnl,
        })
    return {
        "is_approximation": True,
        "method": "first_order_greeks",
        "curve": points,
    }
