"""
ICICI Breeze API Integration

This module provides integration with ICICI Breeze broker API for:
- Authentication and session management
- Fetching funds, positions, and limits
- Option chain quotes
- Historical price data (cash, futures, options)
- NIFTY spot quotes
"""

import logging
import re
import requests
import json
import hashlib
import calendar
from datetime import datetime, timezone as dt_timezone, timedelta, date
from typing import List

from breeze_connect import BreezeConnect
from django.utils import timezone as dj_timezone
from decimal import Decimal

from apps.core.models import CredentialStore
from apps.core.constants import BROKER_ICICI
from apps.brokers.models import BrokerLimit, BrokerPosition, OptionChainQuote, HistoricalPrice

logger = logging.getLogger(__name__)

NSE_BASE = "https://www.nseindia.com"
NSE_OC_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"


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


def get_next_nifty_expiry(next_expiry: bool = False, timeout: int = 10) -> str:
    """
    Fetch the nearest (or next) NIFTY options expiry date from NSE.

    Args:
        next_expiry: If True, returns the next expiry after the closest one
        timeout: Per-request timeout in seconds

    Returns:
        str: Expiry date in 'DD-MMM-YYYY' format (e.g., '02-SEP-2025')

    Raises:
        RuntimeError: If data fetch/parsing fails
    """
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/option-chain",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    })

    # Priming request to set cookies
    resp_home = sess.get(NSE_BASE, timeout=timeout)
    if not resp_home.ok:
        raise RuntimeError(f"NSE homepage request failed: {resp_home.status_code}")

    # Fetch the option chain JSON
    resp = sess.get(NSE_OC_URL, timeout=timeout)
    if not resp.ok:
        raise RuntimeError(f"Option chain request failed: {resp.status_code}")

    try:
        data = resp.json()
        expiry_list: List[str] = data["records"]["expiryDates"]
        if not expiry_list:
            raise RuntimeError("Expiry list is empty")

        # Parse to real dates and sort
        def parse_dt(s: str) -> datetime:
            return datetime.strptime(s, "%d-%b-%Y")

        unique_dates = sorted({parse_dt(s) for s in expiry_list})
        index = 1 if next_expiry else 0
        if index >= len(unique_dates):
            raise IndexError("Requested next expiry but only one expiry was found")

        # Format as 'DD-MMM-YYYY' with uppercase month
        return unique_dates[index].strftime("%d-%b-%Y").upper()

    except (KeyError, ValueError) as e:
        raise RuntimeError(f"Failed to parse NSE response: {e}") from e


def get_or_prompt_breeze_token():
    """
    Check if Breeze session token is valid.

    Returns:
        str: 'prompt' if token needs to be entered, 'ready' if valid

    Raises:
        Exception: If credentials not found
    """
    creds = CredentialStore.objects.filter(service='breeze').first()
    if not creds:
        raise Exception("No Breeze credentials found in DB")
    if (not creds.session_token or
        not creds.last_session_update or
        creds.last_session_update.date() != dj_timezone.now().date()):
        return 'prompt'
    return 'ready'


def save_breeze_token(session_token):
    """
    Save Breeze session token to database.

    Args:
        session_token: The session token from ICICI portal

    Raises:
        Exception: If credentials not found
    """
    creds = CredentialStore.objects.filter(service='breeze').first()
    if not creds:
        raise Exception("No Breeze credentials found in DB")
    creds.session_token = session_token
    creds.last_session_update = dj_timezone.now()
    creds.save()


def get_breeze_client():
    """
    Get authenticated Breeze API client.

    Returns:
        BreezeConnect: Authenticated client instance

    Raises:
        Exception: If credentials not found or authentication fails
    """
    creds = CredentialStore.objects.filter(service='breeze').first()
    if not creds:
        raise Exception("No Breeze credentials found in DB")
    breeze = BreezeConnect(api_key=creds.api_key)
    breeze.generate_session(
        api_secret=creds.api_secret,
        session_token=creds.session_token
    )
    return breeze


def get_nifty_quote():
    """
    Get NIFTY50 spot price from Breeze cash quote.

    Returns:
        dict: Quote data with LTP and other metrics, or None if failed
    """
    breeze = get_breeze_client()
    resp = breeze.get_quotes(
        stock_code="NIFTY",
        exchange_code="NSE",
        product_type="cash",
        expiry_date="",
        right="",
        strike_price=""
    )
    logger.info(f"NIFTY quote response: {resp}")
    if resp and resp.get("Status") == 200 and resp.get("Success"):
        rows = resp["Success"]
        row = next((r for r in rows if (r or {}).get("exchange_code") == "NSE"), rows[0])
        return row
    return None


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
    funds = funds_resp.get('Success', {})

    creds = CredentialStore.objects.filter(service='breeze').first()
    appkey = creds.api_key
    secret_key = creds.api_secret
    session_key = creds.session_token

    # Fetch customer details for rest token
    cd_url = "https://api.icicidirect.com/breezeapi/api/v1/customerdetails"
    time_stamp = datetime.now(dt_timezone.utc).isoformat()[:19] + '.000Z'
    cd_payload = json.dumps({"SessionToken": session_key, "AppKey": appkey})
    cd_headers = {'Content-Type': 'application/json'}
    cd_resp = requests.get(cd_url, headers=cd_headers, data=cd_payload)
    rest_token = cd_resp.json().get('Success', {}).get('session_token')

    # Fetch margin data
    margin_url = "https://api.icicidirect.com/breezeapi/api/v1/margin"
    payload = json.dumps({"exchange_code": "NFO"}, separators=(',', ':'))
    checksum = hashlib.sha256((time_stamp + payload + secret_key).encode()).hexdigest()
    headers = {
        'Content-Type': 'application/json',
        'X-Checksum': 'token ' + checksum,
        'X-Timestamp': time_stamp,
        'X-AppKey': appkey,
        'X-SessionToken': rest_token,
    }
    margin_resp = requests.get(margin_url, headers=headers, data=payload)
    margins = margin_resp.json().get('Success', {})

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
    raw_positions = pos_resp.get('Success', [])
    pos_objs = []
    for p in raw_positions:
        quantity = int(p.get('quantity') or 0)
        avg_price_val = _parse_float(p.get('average_price'))
        ltp_val = _parse_float(p.get('ltp') or p.get('price'))
        buy_qty = quantity if quantity > 0 else 0
        sell_qty = abs(quantity) if quantity < 0 else 0
        buy_amt = buy_qty * avg_price_val
        sell_amt = sell_qty * avg_price_val
        unrealized = _parse_float(p.get('pnl'))
        symbol = p.get('stock_code') or f"{p.get('underlying', '')} {p.get('strike_price', '')} {p.get('right', '')}".strip()

        pos = BrokerPosition.objects.create(
            broker=BROKER_ICICI,
            fetched_at=dj_timezone.now(),
            symbol=symbol,
            exchange_segment=p.get('segment'),
            product=p.get('product_type'),
            buy_qty=buy_qty,
            sell_qty=sell_qty,
            net_quantity=quantity,
            buy_amount=buy_amt,
            sell_amount=sell_amt,
            ltp=ltp_val,
            average_price=avg_price_val,
            realized_pnl=0.0,
            unrealized_pnl=unrealized,
        )
        pos_objs.append(pos)

    logger.info(f"Saved {len(pos_objs)} Breeze positions")
    return limit_record, pos_objs


def get_next_monthly_expiry():
    """
    Calculate next monthly expiry (last Thursday of month).

    Returns:
        str: Expiry date in 'DD-MMM-YYYY' format
    """
    today = date.today()
    month = today.month
    year = today.year
    last_day = calendar.monthrange(year, month)[1]
    last_date = date(year, month, last_day)
    last_thursday = last_date
    while last_thursday.weekday() != 3:
        last_thursday -= timedelta(days=1)
    if last_thursday <= today:
        month = (month % 12) + 1
        year = year + (1 if month == 1 else 0)
        last_day = calendar.monthrange(year, month)[1]
        last_date = date(year, month, last_day)
        last_thursday = last_date
        while last_thursday.weekday() != 3:
            last_thursday -= timedelta(days=1)
    return last_thursday.strftime('%d-%b-%Y').upper()


def get_and_save_option_chain_quotes(stock_code, expiry_date=None, product_type="futures"):
    """
    Fetch option chain quotes from Breeze API and save to database.

    Args:
        stock_code: Stock/index code (e.g., 'NIFTY')
        expiry_date: Expiry date in 'DD-MMM-YYYY' format (if None, fetches from NSE)
        product_type: 'futures' or 'options'

    Returns:
        list: List of OptionChainQuote objects created

    Raises:
        Exception: If API call fails
    """
    breeze = get_breeze_client()

    if not expiry_date:
        expiry_date = get_next_nifty_expiry()

    logger.info(f"Fetching option chain for {stock_code}, expiry: {expiry_date}")

    # Convert to date object for storage
    expiry_date_obj = datetime.strptime(expiry_date, "%d-%b-%Y").date()

    # Delete old quotes for this stock and product type
    OptionChainQuote.objects.filter(
        stock_code=stock_code,
        product_type__iexact=product_type
    ).delete()

    quotes = []
    if product_type == "options":
        for right in ["call", "put"]:
            resp = breeze.get_option_chain_quotes(
                stock_code=stock_code,
                exchange_code="NFO",
                product_type=product_type,
                expiry_date=expiry_date,
                right=right,
            )
            quotes.extend(resp.get("Success", []))
    else:
        resp = breeze.get_option_chain_quotes(
            stock_code=stock_code,
            exchange_code="NFO",
            product_type=product_type,
            expiry_date=expiry_date
        )
        quotes.extend(resp.get("Success", []))

    objs = []
    for q in quotes:
        obj = OptionChainQuote.objects.create(
            exchange_code=q.get('exchange_code', ''),
            product_type=q.get('product_type', ''),
            stock_code=q.get('stock_code', ''),
            expiry_date=expiry_date_obj,
            right=q.get('right', ''),
            strike_price=Decimal(str(q.get('strike_price', 0.0) or 0.0)),
            ltp=Decimal(str(q.get('ltp', 0.0) or 0.0)),
            best_bid_price=Decimal(str(q.get('best_bid_price', 0.0) or 0.0)),
            best_offer_price=Decimal(str(q.get('best_offer_price', 0.0) or 0.0)),
            open=Decimal(str(q.get('open', 0.0) or 0.0)),
            high=Decimal(str(q.get('high', 0.0) or 0.0)),
            low=Decimal(str(q.get('low', 0.0) or 0.0)),
            previous_close=Decimal(str(q.get('previous_close', 0.0) or 0.0)),
            open_interest=int(q.get('open_interest', 0) or 0),
            total_quantity_traded=int(q.get('total_quantity_traded', 0) or 0),
            spot_price=Decimal('0.00'),  # Set separately if needed
        )
        objs.append(obj)

    logger.info(f"Saved {len(objs)} option chain quotes")
    return objs


def save_historical_price_record(stock_code, exchange_code, product_type, candle_data,
                                expiry_date=None, right='', strike_price=None):
    """
    Save a single historical price record to database.

    Args:
        stock_code: Stock/index code
        exchange_code: Exchange code (NSE, NFO, etc.)
        product_type: 'cash', 'futures', or 'options'
        candle_data: Dict with OHLCV data
        expiry_date: Optional expiry date for derivatives
        right: Optional 'call'/'put' for options
        strike_price: Optional strike price for options

    Returns:
        HistoricalPrice: Created object or None if already exists
    """
    try:
        dt = datetime.fromisoformat(candle_data['datetime'].replace('Z', '+00:00'))

        # Check if record already exists
        existing = HistoricalPrice.objects.filter(
            datetime=dt,
            stock_code=stock_code,
            exchange_code=exchange_code,
            product_type=product_type,
            expiry_date=expiry_date,
            right=right,
            strike_price=strike_price
        ).first()

        if existing:
            return None

        obj = HistoricalPrice.objects.create(
            datetime=dt,
            stock_code=stock_code,
            exchange_code=exchange_code,
            product_type=product_type,
            expiry_date=expiry_date,
            right=right,
            strike_price=Decimal(str(strike_price)) if strike_price else None,
            open=Decimal(str(candle_data.get('open', 0))),
            high=Decimal(str(candle_data.get('high', 0))),
            low=Decimal(str(candle_data.get('low', 0))),
            close=Decimal(str(candle_data.get('close', 0))),
            volume=int(candle_data.get('volume', 0)),
            open_interest=int(candle_data.get('open_interest', 0)),
        )
        return obj
    except Exception as e:
        logger.error(f"Error saving historical price: {e}")
        return None


def get_nifty50_historical_days(days=3000, interval="1day"):
    """
    Fetch historical NIFTY50 cash data and save to database.

    Args:
        days: Number of days of historical data to fetch
        interval: Data interval ('1minute', '5minute', '30minute', '1day')

    Returns:
        int: Number of records saved
    """
    breeze = get_breeze_client()
    today = date.today()
    batch_size = 1000
    saved_count = 0

    for batch_start in range(0, days, batch_size):
        batch_days = min(batch_size, days - batch_start)
        from_date = (today - timedelta(days=batch_start + batch_days)).strftime('%Y-%m-%dT09:15:00.000Z')
        to_date = (today - timedelta(days=batch_start)).strftime('%Y-%m-%dT15:30:00.000Z')

        try:
            resp = breeze.get_historical_data(
                interval=interval,
                from_date=from_date,
                to_date=to_date,
                stock_code="NIFTY",
                exchange_code="NSE",
                product_type="cash"
            )
            candles = resp.get('Success', [])
            for candle in candles:
                if save_historical_price_record("NIFTY", "NSE", "cash", candle):
                    saved_count += 1
        except Exception as e:
            logger.error(f"Error fetching historical data batch: {e}")

    logger.info(f"Saved {saved_count} NIFTY historical records")
    return saved_count
