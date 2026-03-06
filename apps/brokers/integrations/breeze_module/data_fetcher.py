"""
ICICI Breeze Data Fetcher - Fetch Funds, Positions & Save to DB

This module provides functions to fetch and save broker data from Breeze API.
"""

import logging
from decimal import Decimal

from django.utils import timezone as dj_timezone

from apps.core.constants import BROKER_ICICI
from apps.brokers.models import BrokerLimit, BrokerPosition
from apps.brokers.utils.common import parse_float as _parse_float
from apps.brokers.utils.auth_manager import get_credentials
from apps.brokers.utils.api_patterns import (
    get_breeze_customer_details,
    fetch_breeze_margin_data,
    calculate_position_pnl
)

from .client import get_breeze_client

logger = logging.getLogger(__name__)


# Breeze uses abbreviated stock codes; map to full NSE symbol for consistency
# with Kotak Neo's trading_symbol format (e.g. HDFCBANK26MARFUT).
BREEZE_SYMBOL_MAP = {
    'HDFBAN': 'HDFCBANK',
    'LARTOU': 'LTTS',
    'LARTEC': 'LTIMindtree',
    'BAJFIN': 'BAJFINANCE',
    'BAJFI': 'BAJFINANCE',
    'RELIND': 'RELIANCE',
    'TATMOT': 'TATAMOTORS',
    'TATSTE': 'TATASTEEL',
    'BPCL': 'BPCL',
    'POWGRI': 'POWERGRID',
    'INDUSI': 'INDUSINDBK',
}


def _parse_breeze_expiry(raw_expiry):
    """Parse Breeze expiry string like '28-Apr-2026' to a date object."""
    from datetime import datetime as dt
    if not raw_expiry:
        return None
    for fmt in ('%d-%b-%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return dt.strptime(raw_expiry.strip(), fmt).date()
        except ValueError:
            continue
    logger.warning(f"Could not parse Breeze expiry: {raw_expiry}")
    return None


def _build_trading_symbol(stock_code, expiry_date, product_type, strike_price=None, right=None):
    """
    Build a Kotak-style trading symbol from Breeze position fields.

    Examples:
        HDFBAN + 30-Mar-2026 + Futures   -> HDFCBANK26MARFUT
        NIFTY  + 27-Mar-2026 + Options + 26000 + Call -> NIFTY26MAR26000CE
    """
    full_symbol = BREEZE_SYMBOL_MAP.get(stock_code, stock_code)

    if not expiry_date:
        return full_symbol

    yy = str(expiry_date.year)[-2:]
    mon = expiry_date.strftime('%b').upper()  # MAR, APR, etc.

    if product_type and 'future' in product_type.lower():
        return f"{full_symbol}{yy}{mon}FUT"

    if product_type and 'option' in product_type.lower():
        strike = int(float(strike_price)) if strike_price else ''
        opt_type = ''
        if right and right.lower() in ('call', 'ce'):
            opt_type = 'CE'
        elif right and right.lower() in ('put', 'pe'):
            opt_type = 'PE'
        return f"{full_symbol}{yy}{mon}{strike}{opt_type}"

    return full_symbol


def fetch_and_save_breeze_data():
    """
    Fetch funds and positions from Breeze API and save to database.

    Returns:
        tuple: (limit_record, pos_objs) - BrokerLimit and list of BrokerPosition objects

    Raises:
        Exception: If API call or database save fails
    """
    breeze = get_breeze_client()
    funds_resp = breeze.get_funds()
    funds = funds_resp.get('Success') or {}

    # Use centralized credential loading and API patterns
    creds = get_credentials('breeze')

    # Use common pattern for customer details and margin fetching
    rest_token, _ = get_breeze_customer_details(
        creds.api_key,
        creds.api_secret,
        creds.session_token
    )

    margins = fetch_breeze_margin_data(
        creds.api_key,
        creds.api_secret,
        rest_token,
        exchange_code="NFO"
    )

    limit_record = BrokerLimit.objects.create(
        broker=BROKER_ICICI,
        fetched_at=dj_timezone.now(),
        bank_account=funds.get('bank_account'),
        total_bank_balance=_parse_float(funds.get('total_bank_balance')),
        allocated_equity=_parse_float(funds.get('allocated_equity')),
        allocated_fno=_parse_float(funds.get('allocated_fno')),
        block_by_trade_fno=_parse_float(funds.get('block_by_trade_fno')),
        unallocated_balance=_parse_float(funds.get('unallocated_balance')),
        margin_available=_parse_float(margins.get('cash_limit')),
        margin_used=_parse_float(margins.get('amount_allocated')),
    )

    pos_resp = breeze.get_portfolio_positions()
    raw_positions = pos_resp.get('Success') or []
    pos_objs = []
    for p in raw_positions:
        try:
            quantity = int(p.get('quantity') or 0)
            avg_price_val = _parse_float(p.get('average_price'))
            ltp_val = _parse_float(p.get('ltp') or p.get('price'))
            buy_qty = quantity if quantity > 0 else 0
            sell_qty = abs(quantity) if quantity < 0 else 0
            buy_amt = buy_qty * avg_price_val
            sell_amt = sell_qty * avg_price_val

            # Use common pattern for P&L calculation
            unrealized_pnl_val, realized_pnl_val = calculate_position_pnl(
                quantity, avg_price_val, ltp_val
            )

            stock_code = p.get('stock_code') or ''
            symbol = stock_code or f"{p.get('underlying', '')} {p.get('strike_price', '')} {p.get('right', '')}".strip()

            # Parse expiry and build Kotak-style trading symbol
            expiry_date = _parse_breeze_expiry(p.get('expiry_date'))
            product_type = p.get('product_type', '')
            trading_symbol = _build_trading_symbol(
                stock_code, expiry_date, product_type,
                strike_price=p.get('strike_price'),
                right=p.get('right'),
            )

            # Convert to Decimal for database
            pos = BrokerPosition.objects.create(
                broker=BROKER_ICICI,
                fetched_at=dj_timezone.now(),
                symbol=symbol,
                trading_symbol=trading_symbol,
                exchange_segment=p.get('segment', ''),
                product=product_type,
                buy_qty=buy_qty,
                sell_qty=sell_qty,
                net_quantity=quantity,
                buy_amount=Decimal(str(buy_amt)),
                sell_amount=Decimal(str(sell_amt)),
                ltp=Decimal(str(ltp_val)),
                average_price=Decimal(str(avg_price_val)),
                realized_pnl=realized_pnl_val,
                unrealized_pnl=unrealized_pnl_val,
                expiry_date=expiry_date,
            )
            pos_objs.append(pos)
        except (ValueError, Exception) as e:
            logger.error(f"Error processing Breeze position {p.get('stock_code', 'UNKNOWN')}: {e}")
            continue

    logger.info(f"Saved {len(pos_objs)} Breeze positions")
    return limit_record, pos_objs
