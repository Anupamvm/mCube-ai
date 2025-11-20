"""
ICICI Breeze API Integration

This module provides integration with ICICI Breeze broker API for:
- Authentication and session management
- Fetching funds, positions, and limits
- Option chain quotes
- Historical price data (cash, futures, options)
- NIFTY spot quotes
- India VIX data
"""

import logging
import re
import requests
import json
import hashlib
import calendar
from datetime import datetime, timezone as dt_timezone, timedelta, date
from typing import List, Optional, Dict
from django.core.cache import cache

from breeze_connect import BreezeConnect
from django.utils import timezone as dj_timezone
from decimal import Decimal

from apps.core.models import CredentialStore
from apps.core.constants import BROKER_ICICI
from apps.brokers.models import BrokerLimit, BrokerPosition, OptionChainQuote, HistoricalPrice, NiftyOptionChain
from apps.data.models import OptionChain
from apps.brokers.exceptions import BreezeAuthenticationError, BreezeAPIError

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


def get_all_nifty_expiry_dates(max_expiries: int = 10, timeout: int = 15) -> List[str]:
    """
    Fetch all available NIFTY options expiry dates from NSE.

    IMPORTANT: This function ONLY fetches the LIST OF EXPIRY DATES from NSE.
    The actual option chain data (LTP, OI, volume, etc.) is ALWAYS fetched from Breeze API.

    This fetches real contract expiry dates which properly handle holidays.
    NSE adjusts expiry dates when Thursday is a trading holiday.

    NOTE: NSE may block automated API access (403 errors). If this fails,
    the caller should fallback to generating Thursday dates.

    Args:
        max_expiries: Maximum number of expiries to return (default 10)
        timeout: Per-request timeout in seconds

    Returns:
        List[str]: List of expiry dates in 'DD-MMM-YYYY' format (e.g., ['21-NOV-2024', '28-NOV-2024', ...])

    Raises:
        RuntimeError: If data fetch/parsing fails or NSE blocks access
    """
    sess = requests.Session()

    # Enhanced headers to avoid 403 errors
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    })

    try:
        # First, visit NSE homepage to get cookies
        logger.info("Fetching NSE homepage to establish session...")
        resp_home = sess.get(NSE_BASE, timeout=timeout)
        if not resp_home.ok:
            logger.warning(f"NSE homepage returned {resp_home.status_code}, continuing anyway...")

        # Small delay to mimic human behavior
        import time
        time.sleep(1)

        # Update headers for API request
        sess.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com/option-chain",
        })

        # Fetch the option chain JSON
        logger.info("Fetching NIFTY option chain from NSE API...")
        resp = sess.get(NSE_OC_URL, timeout=timeout)

        if not resp.ok:
            logger.error(f"NSE API request failed with status {resp.status_code}")
            raise RuntimeError(f"NSE option chain request failed: {resp.status_code}")

        data = resp.json()
        expiry_list: List[str] = data["records"]["expiryDates"]

        if not expiry_list:
            raise RuntimeError("Expiry list is empty from NSE")

        # Parse, sort, and return dates in proper format
        def parse_dt(s: str) -> datetime:
            return datetime.strptime(s, "%d-%b-%Y")

        unique_dates = sorted({parse_dt(s) for s in expiry_list})

        # Format as 'DD-MMM-YYYY' with uppercase month and limit to max_expiries
        result = [dt.strftime("%d-%b-%Y").upper() for dt in unique_dates[:max_expiries]]

        logger.info(f"Successfully fetched {len(result)} NIFTY expiry dates from NSE: {result[:5]}...")
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching NSE data: {e}")
        raise RuntimeError(f"Failed to fetch NSE option chain data: {e}") from e
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse NSE response: {e}")
        raise RuntimeError(f"Failed to parse NSE response: {e}") from e


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
    try:
        expiries = get_all_nifty_expiry_dates(max_expiries=5, timeout=timeout)
        index = 1 if next_expiry else 0
        if index >= len(expiries):
            raise IndexError("Requested next expiry but only one expiry was found")
        return expiries[index]
    except Exception as e:
        raise RuntimeError(f"Failed to get NIFTY expiry: {e}") from e


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
        BreezeAuthenticationError: If credentials not found or authentication fails
    """
    try:
        creds = CredentialStore.objects.filter(service='breeze').first()
        if not creds:
            raise BreezeAuthenticationError("No Breeze credentials found in database")

        breeze = BreezeConnect(api_key=creds.api_key)
        breeze.generate_session(
            api_secret=creds.api_secret,
            session_token=creds.session_token
        )
        return breeze
    except BreezeAuthenticationError:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        # Detect common authentication error messages
        if any(keyword in error_msg for keyword in ['session', 'authentication', 'unauthorized', 'invalid token', 'expired', 'login']):
            raise BreezeAuthenticationError(f"Breeze authentication failed: {str(e)}", original_error=e)
        raise


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


def get_india_vix() -> Decimal:
    """
    Get India VIX (Volatility Index) from Breeze API.

    Uses cache to avoid excessive API calls (5-minute cache).
    Falls back to 15.0 if API fails.

    Returns:
        Decimal: Current India VIX value
    """
    # Check cache first (5-minute TTL)
    cache_key = 'india_vix_value'
    cached_vix = cache.get(cache_key)

    if cached_vix is not None:
        logger.debug(f"Using cached VIX value: {cached_vix}")
        return Decimal(str(cached_vix))

    try:
        breeze = get_breeze_client()

        # Fetch India VIX quote from NSE using correct symbol: INDVIX
        resp = breeze.get_quotes(
            stock_code="INDVIX",
            exchange_code="NSE",
            product_type="cash",
            expiry_date="",
            right="",
            strike_price=""
        )

        logger.info(f"India VIX (INDVIX) quote response: {resp}")

        if resp and resp.get("Status") == 200 and resp.get("Success"):
            rows = resp["Success"]
            if rows:
                row = rows[0]
                vix_value = _parse_float(row.get('ltp', 15.0))
                vix_decimal = Decimal(str(vix_value))

                # Cache for 5 minutes (300 seconds)
                cache.set(cache_key, float(vix_decimal), 300)

                logger.info(f"Successfully fetched India VIX: {vix_decimal}")
                return vix_decimal

        logger.error("Failed to fetch India VIX from Breeze API - no valid response")
        raise ValueError("Could not fetch India VIX from Breeze API - invalid response")

    except Exception as e:
        logger.error(f"Error fetching India VIX: {e}")
        raise ValueError(f"Could not fetch India VIX from Breeze API: {str(e)}")


def get_nfo_margin():
    """
    Get NFO margin information including pledged stocks.

    Returns actual available margin (cash_limit) which includes:
    - Cash allocated to F&O
    - Margin from pledged stocks
    - Available collateral

    Returns:
        dict: Margin data with 'cash_limit', 'amount_allocated', etc.
              Returns None if API call fails
    """
    try:
        breeze = get_breeze_client()
        creds = CredentialStore.objects.filter(service='breeze').first()
        if not creds:
            logger.error("No Breeze credentials found")
            return None

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

        # Fetch margin data for NFO
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
        margin_data = margin_resp.json()

        if margin_data.get('Status') == 200:
            margins = margin_data.get('Success', {})
            logger.info(f"NFO Margin fetched: cash_limit={margins.get('cash_limit')}, amount_allocated={margins.get('amount_allocated')}")
            return margins
        else:
            logger.error(f"Failed to fetch NFO margin: {margin_data}")
            return None

    except Exception as e:
        logger.error(f"Error fetching NFO margin: {e}", exc_info=True)
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
        try:
            quantity = int(p.get('quantity') or 0)
            avg_price_val = _parse_float(p.get('average_price'))
            ltp_val = _parse_float(p.get('ltp') or p.get('price'))
            buy_qty = quantity if quantity > 0 else 0
            sell_qty = abs(quantity) if quantity < 0 else 0
            buy_amt = buy_qty * avg_price_val
            sell_amt = sell_qty * avg_price_val

            # FIXED: Calculate unrealized P&L correctly
            # For LONG (quantity > 0): (LTP - Avg) * quantity
            # For SHORT (quantity < 0): (Avg - LTP) * abs(quantity)
            if quantity > 0:
                unrealized = (ltp_val - avg_price_val) * quantity
            elif quantity < 0:
                unrealized = (avg_price_val - ltp_val) * abs(quantity)
            else:
                unrealized = 0.0

            symbol = p.get('stock_code') or f"{p.get('underlying', '')} {p.get('strike_price', '')} {p.get('right', '')}".strip()

            # Convert to Decimal for database
            pos = BrokerPosition.objects.create(
                broker=BROKER_ICICI,
                fetched_at=dj_timezone.now(),
                symbol=symbol,
                exchange_segment=p.get('segment', ''),
                product=p.get('product_type', ''),
                buy_qty=buy_qty,
                sell_qty=sell_qty,
                net_quantity=quantity,
                buy_amount=Decimal(str(buy_amt)),
                sell_amount=Decimal(str(sell_amt)),
                ltp=Decimal(str(ltp_val)),
                average_price=Decimal(str(avg_price_val)),
                realized_pnl=Decimal('0.00'),
                unrealized_pnl=Decimal(str(unrealized)),
            )
            pos_objs.append(pos)
        except (ValueError, Exception) as e:
            logger.error(f"Error processing Breeze position {p.get('stock_code', 'UNKNOWN')}: {e}")
            continue

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


def fetch_and_save_nifty_option_chain_all_expiries():
    """
    Fetch NIFTY option chain for all available expiries and save to OptionChain model.

    DATA SOURCES:
    - Expiry dates list: NSE (with fallback to generated Thursdays)
    - ALL live option chain data (LTP, OI, volume, bid, ask, etc.): ICICI Breeze API ONLY

    This function:
    1. Gets list of expiry dates from NSE (or generates Thursdays as fallback)
    2. For each expiry, fetches LIVE option chain data from Breeze API
    3. Collects all data in memory first
    4. Clears old data and bulk saves new data (prevents data loss on fetch failure)
    5. Saves option chain data as separate CE and PE records

    Returns:
        int: Total number of option chain records saved

    Raises:
        RuntimeError: If no data could be fetched or API calls fail
    """
    logger.info("Fetching NIFTY option chain for all expiries")

    # Get Breeze client (will use existing valid session)
    breeze = get_breeze_client()

    # Quick session validation - try to get funds (this works even when customer_details doesn't)
    try:
        funds = breeze.get_funds()
        if not funds or funds.get('Status') != 200:
            raise RuntimeError("Breeze session appears to be invalid. Please refresh your session at /brokers/breeze/login/")
        logger.info("Breeze session validated successfully")
    except Exception as e:
        logger.error(f"Breeze session validation failed: {e}")
        raise RuntimeError(
            "Could not validate Breeze session. Please ensure you are logged in at /brokers/breeze/login/. "
            f"Error: {str(e)}"
        )

    # Get NIFTY spot price from Breeze
    try:
        quote = get_nifty_quote()
        # Breeze returns 'ltp' (Last Traded Price) not 'last'
        spot_price = Decimal(str(quote.get('ltp', 0))) if quote else Decimal('0.00')
        logger.info(f"NIFTY spot price: ₹{spot_price:,.2f}")
    except Exception as e:
        logger.warning(f"Could not fetch NIFTY spot price: {e}")
        spot_price = Decimal('0.00')

    # STEP 1: Get list of expiry dates
    # Try NSE first (real contract dates, handles holidays), fallback to generating Thursdays
    # NOTE: NSE is ONLY used for getting the LIST of dates, NOT the actual option chain data
    logger.info("Fetching NIFTY expiry dates...")

    expiry_list = []

    # Try to get real expiry dates from NSE first (may fail due to 403 blocking)
    try:
        expiry_list = get_all_nifty_expiry_dates(max_expiries=10, timeout=15)
        logger.info(f"✓ Got {len(expiry_list)} real expiry dates from NSE (handles holidays): {expiry_list[:3]}...")
    except Exception as nse_error:
        logger.warning(f"NSE expiry fetch failed (this is normal if NSE blocks API): {nse_error}")
        logger.info("Falling back to generating Tuesday expiry dates...")

        # Fallback: Generate NIFTY expiry dates (weekly expiries - Tuesdays as of 2025)
        # Note: NIFTY changed from Thursday to Tuesday expiries in 2025
        from datetime import datetime, timedelta
        today = datetime.now().date()

        current_date = today

        # Find next 4 Tuesdays
        for _ in range(30):  # Look ahead 30 days to find Tuesdays
            if current_date.weekday() == 1:  # Tuesday = 1
                if current_date >= today:
                    expiry_str = current_date.strftime("%d-%b-%Y")  # Keep original case (not uppercase)
                    expiry_list.append(expiry_str)
                    if len(expiry_list) >= 4:  # Get 4 expiries
                        break
            current_date += timedelta(days=1)

        if expiry_list:
            logger.info(f"Generated {len(expiry_list)} fallback expiries: {expiry_list}")
        else:
            raise RuntimeError("Could not fetch or generate expiry dates")

    logger.info(f"Using {len(expiry_list)} expiry dates for NIFTY option chain fetch (spot: ₹{spot_price})")

    # Get Breeze client
    breeze = get_breeze_client()

    # Store new data temporarily before clearing old data
    new_records = []
    total_saved = 0

    # STEP 2: Fetch LIVE option chain data from ICICI Breeze API
    # ALL option chain data (LTP, OI, volume, bid, ask, etc.) comes from Breeze ONLY
    for expiry_str in expiry_list:
        try:
            logger.info(f"Fetching live option chain from Breeze for expiry: {expiry_str}")

            # Convert expiry to date object
            expiry_date_obj = datetime.strptime(expiry_str, "%d-%b-%Y").date()

            # Fetch calls and puts from Breeze API
            calls_data = []
            puts_data = []

            try:
                # Fetch CALL options from Breeze API
                calls_resp = breeze.get_option_chain_quotes(
                    stock_code="NIFTY",
                    exchange_code="NFO",
                    product_type="options",
                    expiry_date=expiry_str,
                    right="call",
                )
                if calls_resp and calls_resp.get("Success"):
                    calls_data = calls_resp["Success"]
                else:
                    logger.warning(f"No calls data for {expiry_str}: {calls_resp.get('Error', 'Unknown error')}")
            except Exception as e:
                logger.warning(f"Failed to fetch calls for {expiry_str}: {e}")

            try:
                # Fetch PUT options from Breeze API
                puts_resp = breeze.get_option_chain_quotes(
                    stock_code="NIFTY",
                    exchange_code="NFO",
                    product_type="options",
                    expiry_date=expiry_str,
                    right="put",
                )
                if puts_resp and puts_resp.get("Success"):
                    puts_data = puts_resp["Success"]
                else:
                    logger.warning(f"No puts data for {expiry_str}: {puts_resp.get('Error', 'Unknown error')}")
            except Exception as e:
                logger.warning(f"Failed to fetch puts for {expiry_str}: {e}")

            # Process call options and create individual records
            for call in calls_data:
                strike = Decimal(str(call.get('strike_price', 0.0) or 0.0))

                # Create CE record
                record = OptionChain(
                    underlying='NIFTY',
                    expiry_date=expiry_date_obj,
                    strike=strike,
                    option_type='CE',
                    ltp=Decimal(str(call.get('ltp', 0.0) or 0.0)),
                    bid=Decimal(str(call.get('best_bid_price', 0.0) or 0.0)),
                    ask=Decimal(str(call.get('best_offer_price', 0.0) or 0.0)),
                    volume=int(call.get('total_quantity_traded', 0) or 0),
                    oi=int(call.get('open_interest', 0) or 0),
                    oi_change=0,  # Not available from Breeze API
                    spot_price=spot_price,
                )
                new_records.append(record)
                total_saved += 1

            # Process put options and create individual records
            for put in puts_data:
                strike = Decimal(str(put.get('strike_price', 0.0) or 0.0))

                # Create PE record
                record = OptionChain(
                    underlying='NIFTY',
                    expiry_date=expiry_date_obj,
                    strike=strike,
                    option_type='PE',
                    ltp=Decimal(str(put.get('ltp', 0.0) or 0.0)),
                    bid=Decimal(str(put.get('best_bid_price', 0.0) or 0.0)),
                    ask=Decimal(str(put.get('best_offer_price', 0.0) or 0.0)),
                    volume=int(put.get('total_quantity_traded', 0) or 0),
                    oi=int(put.get('open_interest', 0) or 0),
                    oi_change=0,  # Not available from Breeze API
                    spot_price=spot_price,
                )
                new_records.append(record)
                total_saved += 1

            if calls_data or puts_data:
                logger.info(f"Collected {len(calls_data)} CE and {len(puts_data)} PE options for expiry {expiry_str}")
            else:
                logger.warning(f"No option chain data available for expiry {expiry_str}")

        except Exception as e:
            logger.error(f"Error processing expiry {expiry_str}: {e}")
            continue

    # Now that we've successfully collected all new data, delete old data and save new records
    if new_records:
        logger.info(f"Successfully fetched {total_saved} records. Clearing old data and saving new records...")

        # Delete all old NIFTY option chain data from OptionChain model
        deleted_count = OptionChain.objects.filter(underlying='NIFTY').delete()[0]
        logger.info(f"Deleted {deleted_count} old OptionChain records for NIFTY")

        # Bulk create all new records
        OptionChain.objects.bulk_create(new_records, batch_size=500)
        logger.info(f"Bulk created {total_saved} new NIFTY option chain records across {len(expiry_list)} expiries")
    else:
        logger.warning("No new records to save, keeping existing data intact")

    if total_saved == 0:
        raise RuntimeError(
            f"No option chain data could be fetched for any of the {len(expiry_list)} expiry dates.\n\n"
            "Possible reasons:\n"
            "1. Market is closed - Option chain data is only available during trading hours (9:15 AM - 3:30 PM IST)\n"
            "2. The expiry dates don't have active contracts yet\n"
            "3. Breeze API session needs refresh\n\n"
            f"Expiry dates tried: {', '.join(expiry_list[:3])}{'...' if len(expiry_list) > 3 else ''}\n\n"
            "Solution: Please try again during market hours (Mon-Fri 9:15 AM - 3:30 PM IST) or refresh Breeze session at /brokers/breeze/login/"
        )

    return total_saved


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
        # Parse datetime and make it timezone-aware
        dt_str = candle_data['datetime'].replace('Z', '+00:00')
        dt = datetime.fromisoformat(dt_str)

        # Ensure datetime is timezone-aware for Django
        if dt.tzinfo is None:
            dt = dj_timezone.make_aware(dt)

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

        # Safely handle None values for volume and open_interest
        volume = candle_data.get('volume')
        open_interest = candle_data.get('open_interest')

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
            volume=int(volume) if volume is not None else 0,
            open_interest=int(open_interest) if open_interest is not None else 0,
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


# ============================================================================
# ORDER PLACEMENT WITH SECURITY MASTER
# ============================================================================

def place_futures_order_with_security_master(
    symbol: str,
    expiry_date: str,
    action: str,
    lots: int,
    order_type: str = 'market',
    price: float = 0.0,
    product: str = 'futures',
    validity: str = 'day'
) -> Dict:
    """
    Place a futures order using SecurityMaster for correct instrument codes.

    This function automatically fetches the correct stock_code and lot_size
    from the SecurityMaster file, ensuring orders are placed with accurate
    instrument details.

    Args:
        symbol: Stock symbol (e.g., 'SBIN', 'NIFTY', 'RELIANCE')
        expiry_date: Expiry date in 'DD-MMM-YYYY' format (e.g., '30-Dec-2025')
        action: 'buy' or 'sell'
        lots: Number of lots to trade
        order_type: Order type - 'market' or 'limit' (default: 'market')
        price: Price for limit orders (default: 0.0 for market orders)
        product: Product type (default: 'futures')
        validity: Order validity (default: 'day')

    Returns:
        dict: Breeze API response with additional SecurityMaster info
            {
                'Status': 200,
                'Success': {
                    'order_id': 'order_id',
                    ...
                },
                'security_master': {
                    'stock_code': 'STABAN',
                    'token': '50066',
                    'lot_size': 750,
                    ...
                },
                'order_params': {...}  # Parameters used for the order
            }

    Example:
        >>> response = place_futures_order_with_security_master(
        ...     symbol='SBIN',
        ...     expiry_date='30-Dec-2025',
        ...     action='buy',
        ...     lots=10
        ... )
        >>> if response['Status'] == 200:
        ...     print(f"Order ID: {response['Success']['order_id']}")
        ...     print(f"Stock Code Used: {response['security_master']['stock_code']}")
    """
    from apps.brokers.utils.security_master import get_futures_instrument

    logger.info(f"Placing futures order: {symbol} {expiry_date} {action.upper()} {lots} lots")

    # Get instrument details from SecurityMaster
    instrument = get_futures_instrument(symbol, expiry_date)

    if not instrument:
        error_msg = f"Could not find instrument in SecurityMaster: {symbol} expiring {expiry_date}"
        logger.error(error_msg)
        return {
            'Status': 400,
            'Error': error_msg,
            'security_master': None
        }

    # Extract details
    stock_code = instrument['short_name']
    lot_size = instrument['lot_size']
    quantity = lots * lot_size

    logger.info(f"SecurityMaster lookup: Symbol={symbol} -> StockCode={stock_code}, "
               f"Token={instrument['token']}, LotSize={lot_size}, Quantity={quantity}")

    # Get Breeze client
    breeze = get_breeze_client()

    # Prepare order parameters
    order_params = {
        'stock_code': stock_code,           # Use short_name from SecurityMaster
        'exchange_code': 'NFO',
        'product': product,
        'action': action.lower(),           # 'buy' or 'sell'
        'order_type': order_type.lower(),   # 'market' or 'limit'
        'quantity': str(quantity),
        'price': str(price) if order_type.lower() == 'limit' else '0',
        'validity': validity,
        'stoploss': '0',
        'disclosed_quantity': '0',
        'expiry_date': expiry_date,
        'right': 'others',                  # 'others' for futures
        'strike_price': '0'
    }

    logger.info(f"Order parameters: {order_params}")

    try:
        # Place order via Breeze
        order_response = breeze.place_order(**order_params)

        # Add SecurityMaster and order params to response
        if order_response:
            order_response['security_master'] = instrument
            order_response['order_params'] = order_params
        else:
            order_response = {
                'Status': 500,
                'Error': 'No response from Breeze API',
                'security_master': instrument,
                'order_params': order_params
            }

        # Log result
        if order_response.get('Status') == 200:
            order_id = order_response.get('Success', {}).get('order_id', 'UNKNOWN')
            logger.info(f"✅ Order placed successfully! Order ID: {order_id}")
        else:
            error = order_response.get('Error', 'Unknown error')
            logger.error(f"❌ Order placement failed: {error}")
            logger.error(f"Full response: {order_response}")

        return order_response

    except Exception as e:
        logger.error(f"Exception during order placement: {e}", exc_info=True)
        return {
            'Status': 500,
            'Error': str(e),
            'security_master': instrument,
            'order_params': order_params
        }


def place_option_order_with_security_master(
    symbol: str,
    expiry_date: str,
    strike_price: float,
    option_type: str,
    action: str,
    lots: int,
    order_type: str = 'market',
    price: float = 0.0,
    product: str = 'options',
    validity: str = 'day'
) -> Dict:
    """
    Place an option order using SecurityMaster for correct instrument codes.

    Args:
        symbol: Stock symbol (e.g., 'NIFTY', 'BANKNIFTY')
        expiry_date: Expiry date in 'DD-MMM-YYYY' format (e.g., '27-Nov-2025')
        strike_price: Strike price (e.g., 24500)
        option_type: 'CE' for Call or 'PE' for Put
        action: 'buy' or 'sell'
        lots: Number of lots to trade
        order_type: Order type - 'market' or 'limit' (default: 'market')
        price: Price for limit orders (default: 0.0 for market orders)
        product: Product type (default: 'options')
        validity: Order validity (default: 'day')

    Returns:
        dict: Breeze API response with SecurityMaster info (same structure as futures)

    Example:
        >>> response = place_option_order_with_security_master(
        ...     symbol='NIFTY',
        ...     expiry_date='27-Nov-2025',
        ...     strike_price=24500,
        ...     option_type='CE',
        ...     action='sell',
        ...     lots=2
        ... )
    """
    from apps.brokers.utils.security_master import get_option_instrument

    logger.info(f"Placing option order: {symbol} {expiry_date} {strike_price}{option_type} "
               f"{action.upper()} {lots} lots")

    # Get instrument details from SecurityMaster
    instrument = get_option_instrument(symbol, expiry_date, strike_price, option_type)

    if not instrument:
        error_msg = (f"Could not find instrument in SecurityMaster: "
                    f"{symbol} {strike_price}{option_type} expiring {expiry_date}")
        logger.error(error_msg)
        return {
            'Status': 400,
            'Error': error_msg,
            'security_master': None
        }

    # Extract details
    stock_code = instrument['short_name']
    lot_size = instrument['lot_size']
    quantity = lots * lot_size

    logger.info(f"SecurityMaster lookup: {symbol} {strike_price}{option_type} -> "
               f"StockCode={stock_code}, Token={instrument['token']}, "
               f"LotSize={lot_size}, Quantity={quantity}")

    # Get Breeze client
    breeze = get_breeze_client()

    # Normalize option type for Breeze API
    right = 'call' if option_type.upper() == 'CE' else 'put'

    # Prepare order parameters
    order_params = {
        'stock_code': stock_code,           # Use short_name from SecurityMaster
        'exchange_code': 'NFO',
        'product': product,
        'action': action.lower(),           # 'buy' or 'sell'
        'order_type': order_type.lower(),   # 'market' or 'limit'
        'quantity': str(quantity),
        'price': str(price) if order_type.lower() == 'limit' else '0',
        'validity': validity,
        'stoploss': '0',
        'disclosed_quantity': '0',
        'expiry_date': expiry_date,
        'right': right,                     # 'call' or 'put'
        'strike_price': str(int(strike_price))
    }

    logger.info(f"Order parameters: {order_params}")

    try:
        # Place order via Breeze
        order_response = breeze.place_order(**order_params)

        # Add SecurityMaster and order params to response
        if order_response:
            order_response['security_master'] = instrument
            order_response['order_params'] = order_params
        else:
            order_response = {
                'Status': 500,
                'Error': 'No response from Breeze API',
                'security_master': instrument,
                'order_params': order_params
            }

        # Log result
        if order_response.get('Status') == 200:
            order_id = order_response.get('Success', {}).get('order_id', 'UNKNOWN')
            logger.info(f"✅ Order placed successfully! Order ID: {order_id}")
        else:
            error = order_response.get('Error', 'Unknown error')
            logger.error(f"❌ Order placement failed: {error}")
            logger.error(f"Full response: {order_response}")

        return order_response

    except Exception as e:
        logger.error(f"Exception during order placement: {e}", exc_info=True)
        return {
            'Status': 500,
            'Error': str(e),
            'security_master': instrument,
            'order_params': order_params
        }
