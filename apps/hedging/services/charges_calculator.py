"""
Estimated NSE F&O option order charges (brokerage, STT, exchange
transaction charges, SEBI turnover fee, stamp duty, GST).

Nothing like this exists elsewhere in the codebase today — `BrokerContractPnL`
(apps/brokers/models.py) only reconciles charges *after* the fact from
imported broker CSVs. This module is a pre-trade ESTIMATE used for the Cover
Position preview panel, not a substitute for the broker's own contract note.

Rates below are a representative discount-broker + NSE fee schedule "as of
2025-04". These rates change periodically (STT on options was last revised
1 Oct 2024) — verify against a current NSE/SEBI circular before relying on
this for anything beyond a preview estimate, and bump the "as of" date in
RATES_AS_OF when you do.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict

RATES_AS_OF = "2025-04"

# Flat per-order brokerage typical of discount brokers for F&O options.
BROKERAGE_FLAT_PER_ORDER = Decimal("20.00")

# STT is charged only on the SELL side of an options trade, on premium turnover.
STT_SELL_PCT = Decimal("0.001")          # 0.1%

# NSE exchange transaction charge on options premium turnover.
EXCHANGE_TXN_PCT = Decimal("0.0003503")  # 0.03503%

# SEBI turnover fee: Rs 10 per crore of turnover.
SEBI_TURNOVER_PCT = Decimal("0.0000001")

# Stamp duty is charged only on the BUY side of an options trade.
STAMP_DUTY_BUY_PCT = Decimal("0.00003")  # 0.003%

# GST applies to (brokerage + exchange transaction charges).
GST_PCT = Decimal("0.18")

TWO_PLACES = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class ChargesBreakdown(TypedDict):
    turnover: Decimal
    brokerage: Decimal
    stt: Decimal
    exchange_txn_charges: Decimal
    sebi_charges: Decimal
    stamp_duty: Decimal
    gst: Decimal
    total_charges: Decimal
    net_amount: Decimal
    rates_as_of: str


def calculate_option_transaction_charges(
    premium_per_share: Decimal,
    lots: int,
    lot_size: int,
    transaction_type: str,
) -> ChargesBreakdown:
    """
    `transaction_type` is 'SELL' or 'BUY'. A roll needs both: the buy-back
    of the existing short call ('BUY') and the new sell ('SELL') — call this
    once per leg and sum, don't try to net them in one call.
    """
    if transaction_type not in ("SELL", "BUY"):
        raise ValueError(f"transaction_type must be 'SELL' or 'BUY', got {transaction_type!r}")

    turnover = premium_per_share * lots * lot_size

    brokerage = BROKERAGE_FLAT_PER_ORDER
    exchange_txn_charges = turnover * EXCHANGE_TXN_PCT
    sebi_charges = turnover * SEBI_TURNOVER_PCT
    stt = turnover * STT_SELL_PCT if transaction_type == "SELL" else Decimal("0")
    stamp_duty = turnover * STAMP_DUTY_BUY_PCT if transaction_type == "BUY" else Decimal("0")
    gst = (brokerage + exchange_txn_charges) * GST_PCT

    total_charges = brokerage + stt + exchange_txn_charges + sebi_charges + stamp_duty + gst

    # SELL: money received minus charges. BUY: money paid plus charges.
    net_amount = (turnover - total_charges) if transaction_type == "SELL" else (turnover + total_charges)

    return {
        "turnover": _round(turnover),
        "brokerage": _round(brokerage),
        "stt": _round(stt),
        "exchange_txn_charges": _round(exchange_txn_charges),
        "sebi_charges": _round(sebi_charges),
        "stamp_duty": _round(stamp_duty),
        "gst": _round(gst),
        "total_charges": _round(total_charges),
        "net_amount": _round(net_amount),
        "rates_as_of": RATES_AS_OF,
    }


def calculate_option_sell_charges(
    premium_per_share: Decimal,
    lots: int,
    lot_size: int,
) -> ChargesBreakdown:
    """Convenience wrapper for the common case: selling a covered call."""
    return calculate_option_transaction_charges(premium_per_share, lots, lot_size, "SELL")
