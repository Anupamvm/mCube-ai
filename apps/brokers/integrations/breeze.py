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
import requests
import json
import calendar
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict
from django.core.cache import cache

from django.utils import timezone as dj_timezone
from decimal import Decimal

from apps.core.constants import BROKER_ICICI
from apps.brokers.models import BrokerLimit, BrokerPosition, OptionChainQuote, HistoricalPrice
from apps.brokers.exceptions import BreezeAuthenticationError
from apps.brokers.utils.common import parse_float as _parse_float
from apps.brokers.utils.auth_manager import (
    get_credentials,
    save_session_token,
)
from apps.brokers.utils.api_patterns import (
    get_breeze_customer_details,
    fetch_breeze_margin_data,
    calculate_position_pnl
)

logger = logging.getLogger(__name__)

NSE_BASE = "https://www.nseindia.com"
NSE_OC_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"


class BreezeAPI:
    """
    Simplified Breeze API wrapper for login and account queries.

    This class provides a simple interface for authentication and fetching
    account data (margin, positions) from ICICI Breeze.

    For order placement, use BreezeAPIClient instead.
    """

    def __init__(self):
        """Initialize Breeze API wrapper"""
        self.breeze = None

    def login(self) -> bool:
        """
        Authenticate with Breeze API.

        Uses centralized BreezeSessionManager which handles:
        - Session validation
        - Auto-refresh if expired
        - Consistent error handling

        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            self.breeze = get_breeze_client()
            logger.info("Breeze login successful")
            return True
        except BreezeAuthenticationError as e:
            logger.error(f"Breeze authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Breeze login error: {e}")
            return False

    def get_margin(self) -> dict:
        """
        Get NFO margin information.

        Returns:
            dict: Margin data with 'available_margin', 'used_margin', etc.
        """
        try:
            margin_data = get_nfo_margin()
            if margin_data:
                return {
                    'available_margin': _parse_float(margin_data.get('cash_limit', 0)),
                    'used_margin': _parse_float(margin_data.get('amount_allocated', 0)),
                    'raw_data': margin_data
                }
            return {'available_margin': 0, 'used_margin': 0}
        except Exception as e:
            logger.error(f"Error fetching margin: {e}")
            return {'available_margin': 0, 'used_margin': 0}

    def get_positions(self) -> list:
        """
        Get current broker positions.

        Returns:
            list: List of position dicts or position-like objects
        """
        try:
            _, positions = fetch_and_save_breeze_data()
            return positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []


class BreezeAPIClient:
    """
    Client wrapper for ICICI Breeze API with order placement methods.

    Provides simplified methods for placing futures and options orders,
    handling the complexity of SecurityMaster lookups and Breeze API calls.

    This is the main client class for order placement and should be used in new code.
    """

    def __init__(self):
        """Initialize the Breeze API client"""
        self.breeze = get_breeze_client()

    def place_futures_order(
        self,
        symbol: str,
        direction: str,
        quantity: int,
        order_type: str = 'market',
        price: Optional[float] = None,
        expiry_date: Optional[str] = None
    ) -> Dict:
        """
        Place a futures order.

        Args:
            symbol: Stock symbol (e.g., 'NIFTY', 'SBIN')
            direction: 'buy' or 'sell'
            quantity: Number of shares/units
            order_type: 'market' or 'limit'
            price: Limit price (required for limit orders)
            expiry_date: Expiry date in 'DD-MMM-YYYY' format (auto-fetch if not provided)

        Returns:
            dict: {
                'success': bool,
                'order_id': str,
                'executed_price': float,
                'message': str,
                'error': str (if failed)
            }
        """
        try:
            # Use provided expiry or fetch next expiry
            if not expiry_date:
                expiry_date = get_next_nifty_expiry()

            # Calculate lot size and quantity
            # For now, assume quantity is in units (will be converted to lots)
            order_response = place_futures_order_with_security_master(
                symbol=symbol,
                expiry_date=expiry_date,
                action=direction.lower(),
                lots=quantity,
                order_type=order_type.lower(),
                price=float(price) if price else 0.0
            )

            if order_response.get('Status') == 200:
                return {
                    'success': True,
                    'order_id': order_response.get('Success', {}).get('order_id', 'UNKNOWN'),
                    'executed_price': price if price else 0.0,
                    'message': 'Order placed successfully'
                }
            else:
                error_msg = order_response.get('Error', 'Unknown error')
                return {
                    'success': False,
                    'message': f'Order placement failed: {error_msg}',
                    'error': error_msg
                }

        except Exception as e:
            logger.error(f"Error placing futures order: {e}")
            return {
                'success': False,
                'message': f'Order placement error: {str(e)}',
                'error': str(e)
            }

    def place_strangle_order(
        self,
        symbol: str,
        call_strike: float,
        put_strike: float,
        quantity: int,
        expiry: str
    ) -> Dict:
        """
        Place a strangle order (simultaneous call and put).

        Args:
            symbol: Underlying symbol (e.g., 'NIFTY')
            call_strike: Call strike price
            put_strike: Put strike price
            quantity: Quantity in lots
            expiry: Expiry date in 'DD-MMM-YYYY' format

        Returns:
            dict: Combined response from both orders
        """
        try:
            # Place call order
            call_response = place_option_order_with_security_master(
                symbol=symbol,
                expiry_date=expiry,
                strike_price=float(call_strike),
                option_type='CE',
                action='sell',  # Typically sell strangle (sell both call and put)
                lots=quantity,
                order_type='market'
            )

            if call_response.get('Status') != 200:
                return {
                    'success': False,
                    'message': f'Call order failed: {call_response.get("Error", "Unknown error")}',
                    'error': call_response.get('Error')
                }

            # Place put order
            put_response = place_option_order_with_security_master(
                symbol=symbol,
                expiry_date=expiry,
                strike_price=float(put_strike),
                option_type='PE',
                action='sell',  # Sell put
                lots=quantity,
                order_type='market'
            )

            if put_response.get('Status') != 200:
                return {
                    'success': False,
                    'message': f'Put order failed: {put_response.get("Error", "Unknown error")}',
                    'error': put_response.get('Error')
                }

            # Both successful
            call_order_id = call_response.get('Success', {}).get('order_id', 'UNKNOWN')
            put_order_id = put_response.get('Success', {}).get('order_id', 'UNKNOWN')

            return {
                'success': True,
                'order_id': f"{call_order_id},{put_order_id}",  # Combined order IDs
                'message': 'Strangle order placed successfully',
                'call_order_id': call_order_id,
                'put_order_id': put_order_id
            }

        except Exception as e:
            logger.error(f"Error placing strangle order: {e}")
            return {
                'success': False,
                'message': f'Strangle order error: {str(e)}',
                'error': str(e)
            }


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

    Uses centralized BreezeSessionManager for session validation.

    Returns:
        str: 'prompt' if token needs to be entered, 'ready' if valid

    Raises:
        Exception: If credentials not found
    """
    from apps.brokers.services.breeze_session import check_breeze_session

    status = check_breeze_session()
    if status['valid']:
        return 'ready'
    return 'prompt'


def save_breeze_token(session_token):
    """
    Save Breeze session token to database.

    Uses centralized auth_manager for token saving.

    Args:
        session_token: The session token from ICICI portal

    Raises:
        Exception: If credentials not found
    """
    # Use centralized token saving
    success = save_session_token('breeze', session_token)
    if not success:
        raise Exception("Failed to save Breeze session token")


def get_breeze_client(auto_refresh: bool = True):
    """
    Get authenticated Breeze API client with automatic session refresh.

    This function uses the centralized BreezeSessionManager which:
    - Validates session before returning client
    - Automatically attempts re-login if session expired
    - Opens browser for OTP entry when needed

    Args:
        auto_refresh: If True, attempt auto-login when session expired (default: True)

    Returns:
        BreezeConnect: Authenticated client instance

    Raises:
        BreezeAuthenticationError: If authentication fails (includes login_url for redirect)

    Usage:
        from apps.brokers.integrations.breeze import get_breeze_client

        try:
            client = get_breeze_client()
            positions = client.get_portfolio_positions()
        except BreezeAuthenticationError as e:
            if e.requires_login:
                # Redirect to e.login_url
                pass
    """
    from apps.brokers.services.breeze_session import get_authenticated_breeze_client
    return get_authenticated_breeze_client(auto_refresh=auto_refresh)


def get_nifty_quote():
    """
    Get NIFTY50 spot price from Breeze cash quote.

    Returns:
        dict: Quote data with LTP and other metrics

    Raises:
        ValueError: If quote data is invalid or missing
        BreezeAuthenticationError: If session is expired
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

    # Check if response is valid
    if not resp:
        raise ValueError("Empty response from Breeze API for NIFTY quote")

    # Check for API errors
    if resp.get("Status") != 200:
        error_msg = resp.get("Error", "Unknown error")
        status = resp.get("Status", "Unknown")
        raise ValueError(f"Breeze API error (Status {status}): {error_msg}")

    # Check for success data
    if not resp.get("Success"):
        raise ValueError("No success data in Breeze API response")

    rows = resp["Success"]
    if not rows:
        raise ValueError("Empty success data from Breeze API")

    # Find NSE row or use first row
    row = next((r for r in rows if (r or {}).get("exchange_code") == "NSE"), rows[0] if rows else None)

    if not row:
        raise ValueError("No valid quote data found in Breeze API response")

    return row


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
        get_breeze_client()

        # Use centralized credential loading
        creds = get_credentials('breeze')
        if not creds:
            logger.error("No Breeze credentials found")
            return None

        # Use common pattern for customer details and margin fetching
        rest_token, _ = get_breeze_customer_details(
            creds.api_key,
            creds.api_secret,
            creds.session_token
        )

        # Use common pattern for margin data fetching
        margins = fetch_breeze_margin_data(
            creds.api_key,
            creds.api_secret,
            rest_token,
            exchange_code="NFO"
        )

        return margins

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
            from apps.brokers.integrations.breeze_module.data_fetcher import (
                _parse_breeze_expiry, _build_trading_symbol,
            )
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
    Delegates to apps.brokers.integrations.breeze_module.option_chain (single implementation).
    """
    from apps.brokers.integrations.breeze_module.option_chain import (
        fetch_and_save_nifty_option_chain_all_expiries as _impl,
    )
    return _impl()


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
            # Use v2 API for cash/equity data (v1 doesn't support 'cash' product type)
            resp = breeze.get_historical_data_v2(
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


def place_futures_order_in_batches(
    symbol: str,
    expiry_date: str,
    action: str,
    total_lots: int,
    batch_size: int = 10,
    delay_seconds: int = 10,
    order_type: str = 'market',
    price: float = 0.0,
    product: str = 'futures',
    cancellation_check: callable = None,
    progress_callback: callable = None,
) -> Dict:
    """
    Place futures orders in batches with delays for large positions.

    This function splits large orders into smaller batches to:
    - Avoid slippage on large orders
    - Manage execution risk
    - Allow for cancellation mid-execution

    Args:
        symbol: Stock symbol (e.g., 'RELIANCE', 'SBIN')
        expiry_date: Expiry date in 'DD-MMM-YYYY' format
        action: 'buy' or 'sell'
        total_lots: Total number of lots to trade
        batch_size: Maximum lots per order (default: 10)
        delay_seconds: Delay between orders in seconds (default: 5)
        order_type: 'market' or 'limit' (default: 'market')
        price: Price for limit orders (default: 0.0)
        product: Product type (default: 'futures')
        cancellation_check: Optional callable that returns True if execution should stop
        progress_callback: Optional callable(batches_completed, total_batches, orders)

    Returns:
        dict: Batch execution results
            {
                'success': True/False,
                'total_lots': int,
                'lots_executed': int,
                'batches_completed': int,
                'total_batches': int,
                'orders': [list of order results],
                'cancelled': bool,
                'average_price': float,
                'error': str (if failed)
            }

    Example:
        >>> result = place_futures_order_in_batches(
        ...     symbol='RELIANCE',
        ...     expiry_date='27-Feb-2026',
        ...     action='buy',
        ...     total_lots=25,
        ...     batch_size=10,
        ...     delay_seconds=5
        ... )
        >>> # Places 3 orders: 10 + 10 + 5 lots
    """
    import time
    import math

    logger.info(f"Starting batch futures order: {symbol} {action.upper()} {total_lots} lots in batches of {batch_size}")

    # Calculate number of batches
    num_batches = math.ceil(total_lots / batch_size)
    remaining_lots = total_lots

    orders = []
    lots_executed = 0
    total_value = 0
    cancelled = False

    for batch_num in range(num_batches):
        # Check for cancellation
        if cancellation_check and cancellation_check():
            logger.warning(f"Batch execution cancelled at batch {batch_num + 1}/{num_batches}")
            cancelled = True
            break

        # Calculate lots for this batch
        batch_lots = min(batch_size, remaining_lots)

        logger.info(f"Placing batch {batch_num + 1}/{num_batches}: {batch_lots} lots")

        # Place order
        order_result = place_futures_order_with_security_master(
            symbol=symbol,
            expiry_date=expiry_date,
            action=action,
            lots=batch_lots,
            order_type=order_type,
            price=price,
            product=product
        )

        orders.append({
            'batch': batch_num + 1,
            'lots': batch_lots,
            'result': order_result,
            'success': order_result.get('Status') == 200
        })

        if order_result.get('Status') == 200:
            lots_executed += batch_lots
            # Get executed price for average calculation
            executed_price = order_result.get('Success', {}).get('average_price', 0)
            if executed_price:
                total_value += executed_price * batch_lots

        remaining_lots -= batch_lots

        # Report progress
        if progress_callback:
            progress_callback(batch_num + 1, num_batches, orders)

        # Delay before next batch (unless this is the last one)
        if remaining_lots > 0 and delay_seconds > 0:
            logger.info(f"Waiting {delay_seconds}s before next batch...")
            time.sleep(delay_seconds)

    # Calculate summary
    successful_orders = [o for o in orders if o['success']]
    failed_orders = [o for o in orders if not o['success']]

    average_price = total_value / lots_executed if lots_executed > 0 else 0

    result = {
        'success': lots_executed > 0,
        'total_lots': total_lots,
        'lots_executed': lots_executed,
        'lots_pending': total_lots - lots_executed,
        'batches_completed': len(orders),
        'total_batches': num_batches,
        'successful_orders': len(successful_orders),
        'failed_orders': len(failed_orders),
        'orders': orders,
        'cancelled': cancelled,
        'average_price': average_price,
    }

    if failed_orders:
        result['error'] = f"{len(failed_orders)} batch(es) failed"

    logger.info(f"Batch execution complete: {lots_executed}/{total_lots} lots executed, {len(failed_orders)} failures")

    return result


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


# ============================================================================
# BACKWARD COMPATIBILITY - Legacy function names from old tools.breeze module
# ============================================================================

def get_breeze_api():
    """
    Backward compatibility wrapper for legacy code.

    Returns a BreezeAPIClient instance for use with old code patterns.
    New code should use get_breeze_client() for direct Breeze API access
    or BreezeAPIClient() for order placement.

    Returns:
        BreezeAPIClient: Initialized Breeze API client
    """
    return BreezeAPIClient()


# ============================================================================
# ORDER AND TRADE HISTORY FUNCTIONS
# ============================================================================

def get_order_list(from_date: str = None, to_date: str = None, exchange_code: str = 'NFO') -> dict:
    """
    Fetch orders from ICICI Breeze API for a date range.

    Args:
        from_date: Start date in 'YYYY-MM-DD' format (default: today)
        to_date: End date in 'YYYY-MM-DD' format (default: today)
        exchange_code: Exchange segment - 'NFO', 'NSE', etc. (default: 'NFO')

    Returns:
        dict: {
            'success': bool,
            'orders': list of order dicts,
            'error': str (if failed)
        }

    Each order dict contains:
        - order_id: Breeze order ID
        - trading_symbol: Symbol traded
        - transaction_type: BUY or SELL
        - quantity: Order quantity
        - price: Order price
        - status: Order status
        - order_datetime: Time of order
        - filled_quantity: Quantity filled
        - average_price: Average execution price
    """
    try:
        breeze = get_breeze_client()

        # Set default dates to today
        if not from_date or not to_date:
            today = date.today()
            from_date = from_date or today.strftime('%Y-%m-%d')
            to_date = to_date or today.strftime('%Y-%m-%d')

        # Format dates for Breeze API: 'YYYY-MM-DDTHH:MM:SS.000Z'
        from_datetime = f"{from_date}T00:00:00.000Z"
        to_datetime = f"{to_date}T23:59:59.000Z"

        logger.info(f"Fetching Breeze orders: {from_date} to {to_date}, exchange: {exchange_code}")

        response = breeze.get_order_list(
            exchange_code=exchange_code,
            from_date=from_datetime,
            to_date=to_datetime
        )

        logger.info(f"Breeze order list response status: {response.get('Status')}")

        if not response:
            return {'success': True, 'orders': [], 'message': 'No orders found'}

        if response.get('Status') != 200:
            error_msg = response.get('Error', 'Unknown error')
            # "No data" is not an error
            if 'no data' in str(error_msg).lower() or 'no record' in str(error_msg).lower():
                return {'success': True, 'orders': [], 'message': 'No orders for period'}
            return {'success': False, 'error': error_msg, 'orders': []}

        orders_data = response.get('Success', [])

        # Parse orders
        orders = []
        for order in orders_data:
            # Parse order datetime
            order_datetime = None
            order_datetime_str = order.get('order_datetime', '')
            if order_datetime_str:
                try:
                    # Breeze format: '2025-01-27T10:30:00.000Z'
                    order_datetime = datetime.strptime(order_datetime_str[:19], '%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    pass

            parsed_order = {
                'order_id': order.get('order_id', ''),
                'trading_symbol': order.get('stock_code', ''),
                'exchange': order.get('exchange_code', 'NFO'),
                'transaction_type': order.get('action', '').upper(),  # 'buy' -> 'BUY'
                'quantity': int(order.get('quantity', 0)),
                'price': float(order.get('price', 0)),
                'status': order.get('order_status', ''),
                'order_datetime': order_datetime,
                'order_date': order_datetime.date() if order_datetime else None,
                'filled_quantity': int(order.get('pending_quantity', 0)),
                'average_price': float(order.get('average_price', 0)),
                'product': order.get('product', ''),
                'order_type': order.get('order_type', ''),
                'validity': order.get('validity', ''),
                'expiry_date': order.get('expiry_date', ''),
                'strike_price': order.get('strike_price', ''),
                'right': order.get('right', ''),  # 'call', 'put', or 'others'
                'rejection_reason': order.get('rejection_reason', ''),
                'raw_data': order
            }
            orders.append(parsed_order)

        logger.info(f"Fetched {len(orders)} orders from Breeze")
        return {'success': True, 'orders': orders}

    except BreezeAuthenticationError as e:
        logger.error(f"Authentication error fetching order list: {e}")
        return {'success': False, 'error': str(e), 'orders': []}
    except Exception as e:
        logger.exception(f"Error fetching Breeze order list: {e}")
        return {'success': False, 'error': str(e), 'orders': []}


def get_trade_list(from_date: str = None, to_date: str = None, exchange_code: str = 'NFO') -> dict:
    """
    Fetch executed trades from ICICI Breeze API for a date range.

    Uses the native Breeze SDK get_trade_list() method which directly hits
    the TRADE API endpoint.

    Args:
        from_date: Start date in 'YYYY-MM-DD' format (default: today)
        to_date: End date in 'YYYY-MM-DD' format (default: today)
        exchange_code: Exchange segment - 'NFO', 'NSE', etc. (default: 'NFO')

    Returns:
        dict: {
            'success': bool,
            'trades': list of trade dicts,
            'error': str (if failed)
        }

    Each trade dict contains:
        - trade_id: Generated from order_id
        - order_id: Associated order ID
        - trading_symbol: Symbol traded
        - transaction_type: BUY or SELL
        - quantity: Trade quantity
        - price: Trade price
        - trade_datetime: Time of trade
        - exchange: Exchange (NFO, NSE, etc.)
    """
    try:
        breeze = get_breeze_client()

        # Set default dates to today
        if not from_date or not to_date:
            today = date.today()
            from_date = from_date or today.strftime('%Y-%m-%d')
            to_date = to_date or today.strftime('%Y-%m-%d')

        # Format dates for Breeze API: 'YYYY-MM-DDTHH:MM:SS.000Z'
        from_datetime = f"{from_date}T00:00:00.000Z"
        to_datetime = f"{to_date}T23:59:59.000Z"

        logger.info(f"=== BREEZE TRADE LIST DEBUG ===")
        logger.info(f"Requesting trades from {from_datetime} to {to_datetime}, exchange: {exchange_code}")

        # Use native SDK method
        response = breeze.get_trade_list(
            exchange_code=exchange_code,
            from_date=from_datetime,
            to_date=to_datetime,
            product_type="",
            action="",
            stock_code=""
        )

        logger.info(f"Breeze trade list RAW response: {response}")
        logger.info(f"Breeze trade list response: Status={response.get('Status')}, Error={response.get('Error')}")

        if not response:
            return {'success': True, 'trades': [], 'message': 'No trades found'}

        # Check for errors
        if response.get('Status') != 200:
            error_msg = response.get('Error', 'Unknown error')
            # "No data" is not an error
            if 'no data' in str(error_msg).lower() or 'no record' in str(error_msg).lower():
                logger.info(f"No trades found for period {from_date} to {to_date}")
                return {'success': True, 'trades': [], 'message': 'No trades for period'}
            logger.error(f"Breeze trade list error: {error_msg}")
            return {'success': False, 'error': error_msg, 'trades': []}

        trades_data = response.get('Success', [])

        if not trades_data:
            logger.info(f"Empty trades data for period {from_date} to {to_date}")
            return {'success': True, 'trades': [], 'message': 'No trades'}

        # Parse trades
        trades = []
        for idx, trade in enumerate(trades_data):
            # Log FULL raw data for first 3 trades to debug field names
            if idx < 3:
                logger.info(f"=== RAW BREEZE TRADE #{idx+1} ===")
                logger.info(f"All keys: {list(trade.keys())}")
                for key, value in trade.items():
                    logger.info(f"  {key}: {value} (type: {type(value).__name__})")

            # Parse trade datetime
            # Breeze returns trade_date in format "29-Jan-2026"
            trade_datetime = None
            trade_datetime_str = trade.get('trade_date', '') or trade.get('order_datetime', '')
            if trade_datetime_str:
                try:
                    # Try different formats - Breeze uses "29-Jan-2026" format
                    for fmt in ['%d-%b-%Y', '%d-%B-%Y', '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%S', '%d-%b-%Y %H:%M:%S', '%Y-%m-%d']:
                        try:
                            trade_datetime = datetime.strptime(trade_datetime_str[:19], fmt[:min(len(fmt), 19)])
                            break
                        except ValueError:
                            continue
                except Exception:
                    logger.warning(f"Could not parse trade datetime: {trade_datetime_str}")

            # Extract symbol info
            stock_code = trade.get('stock_code', '') or trade.get('scrip_name', '')
            trading_symbol = stock_code

            # Get strike and option type for F&O
            strike_price = trade.get('strike_price', '')
            right = trade.get('right', '')  # 'call', 'put', 'others'
            option_type = ''
            if right:
                if right.lower() == 'call':
                    option_type = 'CE'
                elif right.lower() == 'put':
                    option_type = 'PE'

            # Parse quantity - try multiple field names
            quantity = 0
            for qty_field in ['traded_quantity', 'quantity', 'fillQty', 'fldQty', 'trade_quantity', 'executed_quantity']:
                qty_val = trade.get(qty_field)
                if qty_val is not None and qty_val != '' and qty_val != 0:
                    try:
                        quantity = int(qty_val)
                        if quantity > 0:
                            if idx < 3:
                                logger.info(f"  -> Found quantity in field '{qty_field}': {quantity}")
                            break
                    except (ValueError, TypeError):
                        continue

            # Parse price - try MANY possible field names
            # Breeze API actually returns 'average_cost' for trade execution price!
            price = 0.0
            price_fields_to_try = [
                'average_cost',  # ACTUAL Breeze field for trade price!
                'price', 'average_price', 'trade_price', 'execution_price',
                'rate', 'trade_rate', 'exec_price', 'fillPrice', 'flPrc',
                'avgPrc', 'avg_price', 'ltp', 'last_traded_price',
                'executed_price', 'fill_price', 'market_price'
            ]

            for price_field in price_fields_to_try:
                price_val = trade.get(price_field)
                if price_val is not None and price_val != '' and price_val != 0:
                    try:
                        test_price = float(price_val)
                        if test_price > 0:
                            price = test_price
                            if idx < 3:
                                logger.info(f"  -> Found price in field '{price_field}': {price}")
                            break
                    except (ValueError, TypeError):
                        continue

            # If still no price, scan ALL numeric fields for potential price values
            if price == 0:
                numeric_fields = {}
                for k, v in trade.items():
                    if v is not None and v != '':
                        try:
                            num_val = float(v)
                            # Price should be reasonable (0.01 to 500000 for Indian markets)
                            if 0.01 <= num_val <= 500000:
                                numeric_fields[k] = num_val
                        except (ValueError, TypeError):
                            pass

                if idx < 5:
                    logger.warning(f"Could not find price in known fields! Scanning all numeric fields: {numeric_fields}")

                # Try to pick the most likely price field from numeric fields
                # Prefer fields with 'price' or 'rate' in name
                for key, val in numeric_fields.items():
                    key_lower = key.lower()
                    if 'price' in key_lower or 'rate' in key_lower or 'prc' in key_lower:
                        price = val
                        if idx < 3:
                            logger.info(f"  -> Auto-detected price from field '{key}': {price}")
                        break

                # If still no price, just take the first reasonable numeric value
                if price == 0 and numeric_fields:
                    # Sort by value to pick something that looks like a price
                    sorted_fields = sorted(numeric_fields.items(), key=lambda x: x[1], reverse=True)
                    for key, val in sorted_fields:
                        # Skip quantity-like fields
                        if 'qty' not in key.lower() and 'quantity' not in key.lower():
                            price = val
                            if idx < 3:
                                logger.info(f"  -> Fallback: using field '{key}' as price: {price}")
                            break

            parsed_trade = {
                'trade_id': trade.get('trade_id', '') or trade.get('order_id', '') or f"{stock_code}_{trade_datetime_str}",
                'order_id': trade.get('order_id', ''),
                'trading_symbol': trading_symbol,
                'symbol': stock_code,
                'exchange': trade.get('exchange_code', exchange_code),
                'transaction_type': (trade.get('action', '') or trade.get('transaction_type', '')).upper(),
                'quantity': quantity,
                'price': price,
                'trade_datetime': trade_datetime,
                'trade_date': trade_datetime.date() if trade_datetime else None,
                'trade_time': trade_datetime.time() if trade_datetime else None,
                'product': trade.get('product_type', '') or trade.get('product', ''),
                'expiry_date': trade.get('expiry_date', ''),
                'strike_price': strike_price,
                'option_type': option_type,
                'segment': trade.get('segment', ''),
                'raw_data': trade
            }
            trades.append(parsed_trade)

        logger.info(f"Parsed {len(trades)} trades from Breeze API")
        return {'success': True, 'trades': trades}

    except BreezeAuthenticationError:
        raise
    except Exception as e:
        logger.exception(f"Error fetching Breeze trade list: {e}")
        return {'success': False, 'error': str(e), 'trades': []}


