"""
Kotak Neo API Integration

This module provides integration with Kotak Neo broker API for:
- Authentication and session management
- Fetching positions and limits
- Checking open positions
"""

import logging
import re
from neo_api_client import NeoAPI
from django.utils import timezone
from apps.core.models import CredentialStore
from apps.core.constants import BROKER_KOTAK
from apps.brokers.models import BrokerLimit, BrokerPosition

logger = logging.getLogger(__name__)


def _parse_float(val):
    """
    Extract numeric content from val and return as float.
    Falls back to 0.0 if parsing fails.
    Strips commas and percent signs.
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return 0.0
    s = s.replace(',', '')
    if s.endswith('%'):
        s = s[:-1]
    m = re.search(r'-?\d+\.?\d*', s)
    if not m:
        logger.warning(f"Float parse: no numeric data in '{val}', defaulting to 0.0")
        return 0.0
    try:
        return float(m.group())
    except ValueError:
        logger.warning(f"Float parse: invalid conversion for '{val}', defaulting to 0.0")
        return 0.0


def _get_authenticated_client():
    """
    Get authenticated Kotak Neo API client using credentials from database.

    Returns:
        NeoAPI: Authenticated client instance

    Raises:
        ValueError: If credentials not found or authentication fails
    """
    creds = CredentialStore.objects.filter(service='kotakneo').first()
    if not creds:
        raise ValueError("No Kotak Neo credentials found in CredentialStore")

    client = NeoAPI(
        consumer_key=creds.api_key,
        consumer_secret=creds.api_secret,
        environment='prod'
    )

    # Perform login
    client.login(pan=creds.username, password=creds.password)

    # Complete 2FA with OTP
    client.session_2fa(OTP=creds.session_token)

    return client


def fetch_and_save_kotakneo_data():
    """
    Fetch limits and positions from Kotak Neo API and save to database.

    Returns:
        tuple: (limit_record, pos_objs) - BrokerLimit and list of BrokerPosition objects

    Raises:
        Exception: If API call or database save fails
    """
    client = _get_authenticated_client()

    # Fetch & save limits
    lim = client.limits(segment="ALL", exchange="ALL", product="ALL")
    logger.info(f"Kotak Neo limits response: {lim}")

    # Create limit record with guaranteed fields
    limit_record = BrokerLimit.objects.create(
        broker=BROKER_KOTAK,
        fetched_at=timezone.now(),
    )

    # Mapping from API keys to model fields
    kotak_fields = {
        'category': lim.get('Category', ''),
        'net_balance': _parse_float(lim.get('Net')),
        'collateral_value': _parse_float(lim.get('CollateralValue')),
        'margin_available': _parse_float(lim.get('Collateral')),
        'margin_used': _parse_float(lim.get('MarginUsed')),
        'margin_used_percent': _parse_float(lim.get('MarginUsedPrsnt')),
        'margin_warning_pct': _parse_float(lim.get('MarginWarningPrcntPrsnt')),
        'exposure_margin_pct': _parse_float(lim.get('ExposureMarginPrsnt')),
        'span_margin_pct': _parse_float(lim.get('SpanMarginPrsnt')),
        'board_lot_limit': int(lim.get('BoardLotLimit', 0)),
    }

    # Assign only existing attributes
    for attr, val in kotak_fields.items():
        if hasattr(limit_record, attr):
            setattr(limit_record, attr, val)
    limit_record.save()

    # Fetch & save positions
    resp = client.positions()
    raw_positions = resp.get('data', [])

    pos_objs = []
    for p in raw_positions:
        buy_qty = int(p.get('cfBuyQty', 0)) + int(p.get('flBuyQty', 0))
        sell_qty = int(p.get('cfSellQty', 0)) + int(p.get('flSellQty', 0))
        net_q = buy_qty - sell_qty

        buy_amt = _parse_float(p.get('cfBuyAmt', 0)) + _parse_float(p.get('buyAmt', 0))
        sell_amt = _parse_float(p.get('cfSellAmt', 0)) + _parse_float(p.get('sellAmt', 0))
        ltp = _parse_float(p.get('stkPrc', 0))
        avg_price = (buy_amt / buy_qty) if net_q > 0 and buy_qty else (
            (sell_amt / sell_qty) if net_q < 0 and sell_qty else 0.0)
        realized_pnl = sell_amt - buy_amt
        unrealized_pnl = net_q * ltp

        pos = BrokerPosition.objects.create(
            broker=BROKER_KOTAK,
            fetched_at=timezone.now(),
            symbol=p.get('sym', p.get('trdSym', '')),
            exchange_segment=p.get('exSeg', ''),
            product=p.get('prod', ''),
            buy_qty=buy_qty,
            sell_qty=sell_qty,
            net_quantity=net_q,
            buy_amount=buy_amt,
            sell_amount=sell_amt,
            ltp=ltp,
            average_price=avg_price,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
        )
        pos_objs.append(pos)

    logger.info(f"Saved {len(pos_objs)} Kotak Neo positions")
    return limit_record, pos_objs


def auto_login_kotak_neo():
    """
    Perform Kotak Neo login and 2FA, returning session token and sid.

    Returns:
        dict: {'token': str, 'sid': str}

    Raises:
        ValueError: If credentials not found
    """
    creds = CredentialStore.objects.filter(service='kotakneo').first()
    if not creds:
        raise ValueError("No Kotak Neo credentials found in CredentialStore")

    client = NeoAPI(
        consumer_key=creds.api_key,
        consumer_secret=creds.api_secret,
        environment='prod'
    )
    client.login(pan=creds.username, password=creds.password)
    session_2fa = client.session_2fa(OTP=creds.session_token)
    data = session_2fa.get('data', {})
    return {
        'token': data.get('token'),
        'sid': data.get('sid')
    }


def is_open_position() -> bool:
    """
    Returns True if any net position is open, else False.
    A position is 'open' when (cfBuyQty + flBuyQty) - (cfSellQty + flSellQty) != 0.

    Returns:
        bool: True if any position is open, False otherwise
    """
    try:
        client = _get_authenticated_client()
        resp = client.positions()

        # Expecting dict; safely get the list
        raw_positions = resp.get('data', []) if isinstance(resp, dict) else []
        if not isinstance(raw_positions, list):
            raw_positions = []

        for p in raw_positions:
            # Aggregate quantities (defaults 0 if key missing)
            buy_qty = int(p.get('cfBuyQty', 0)) + int(p.get('flBuyQty', 0))
            sell_qty = int(p.get('cfSellQty', 0)) + int(p.get('flSellQty', 0))
            net_q = buy_qty - sell_qty

            # Fallback: if API gives a direct net qty field (rare)
            if net_q == 0 and 'netQty' in p:
                try:
                    net_q = int(p.get('netQty') or 0)
                except Exception:
                    net_q = 0

            if net_q != 0:
                return True

        return False

    except Exception as e:
        logger.exception(f"[is_open_position] Failed to fetch/parse positions: {e}")
        return False
