from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date


def mask_pan(pan: str) -> str:
    if not pan or len(pan) < 10:
        return pan
    return pan[:2] + 'X' * 6 + pan[-2:]


@dataclass
class AccountInfo:
    holder_name: str = ''
    pan_masked: str = ''
    pan_full: str = ''  # transient: unmasked PAN, used only for CAS-password auto-learning, never persisted
    email_masked: str = ''
    mobile_masked: str = ''
    dp_name: str = ''
    dp_id: str = ''
    client_id: str = ''
    depository: str = 'NSDL'
    account_type: str = 'Individual'
    nominee_registered: bool | None = None
    address: str = ''
    statement_month: int | None = None
    statement_year: int | None = None


@dataclass
class HoldingEntry:
    isin: str
    security_name: str
    asset_class: str  # E, M, SGB, C, G, etc.
    quantity: float
    current_price: float
    current_value: float
    avg_cost_per_unit: float | None = None
    total_cost: float | None = None
    pledged_quantity: float = 0
    extra_data: dict = field(default_factory=dict)


@dataclass
class TransactionEntry:
    isin: str
    security_name: str
    transaction_date: date
    order_no: str
    description: str
    transaction_type: str
    opening_balance: float
    debit: float
    credit: float
    closing_balance: float
    amount: float | None = None
    nav_at_transaction: float | None = None


@dataclass
class CASData:
    account_info: AccountInfo
    holdings: list[HoldingEntry] = field(default_factory=list)
    transactions: list[TransactionEntry] = field(default_factory=list)
    cas_type: str = 'NSDL'
