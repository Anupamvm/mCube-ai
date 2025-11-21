"""
Kotak Neo API Integration

This module provides integration with Kotak Neo broker API for:
- Authentication and session management
- Fetching positions and limits
- Checking open positions
"""

import logging
import re
import jwt
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
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


def _is_token_valid(token):
    """
    Check if a JWT token is still valid (not expired).

    Args:
        token: JWT token string

    Returns:
        bool: True if token is valid and not expired
    """
    if not token:
        return False

    try:
        # Decode without verification to check expiration
        payload = jwt.decode(token, options={'verify_signature': False})
        exp_timestamp = payload.get('exp')

        if not exp_timestamp:
            return False

        # Check if token expires in more than 5 minutes
        exp_datetime = datetime.fromtimestamp(exp_timestamp)
        now = datetime.now()
        time_until_expiry = exp_datetime - now

        # Return True if token has more than 5 minutes validity
        return time_until_expiry.total_seconds() > 300
    except Exception as e:
        logger.warning(f"Error checking token validity: {e}")
        return False


def _get_authenticated_client():
    """
    Get authenticated Kotak Neo API client using tools.neo.NeoAPI wrapper.

    Uses the NeoAPI wrapper from tools.neo which handles authentication properly.

    Returns:
        NeoAPI: Authenticated Neo API client (the .neo attribute from tools.neo.NeoAPI)

    Raises:
        ValueError: If credentials not found or authentication fails
    """
    try:
        from tools.neo import NeoAPI as NeoAPIWrapper

        logger.info("Using NeoAPI wrapper from tools.neo for authentication")

        # Create NeoAPI wrapper instance (loads creds from database automatically)
        neo_wrapper = NeoAPIWrapper()

        # Perform login (handles 2FA automatically)
        login_result = neo_wrapper.login()
        logger.info(f"Neo login result: {login_result}, session_active: {neo_wrapper.session_active}")

        if login_result and neo_wrapper.session_active:
            logger.info("✅ Neo API authentication successful via tools.neo wrapper")
            # Return the underlying neo_api_client instance
            logger.info(f"Returning Neo client: {neo_wrapper.neo}")
            return neo_wrapper.neo
        else:
            logger.error(f"❌ Neo API login failed: result={login_result}, session_active={neo_wrapper.session_active}")
            raise ValueError("Neo API login failed via tools.neo wrapper")

    except Exception as e:
        logger.error(f"Failed to get authenticated Neo client: {e}")
        raise


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

    # Mapping from API keys to model fields (convert all floats to Decimal with proper rounding)
    try:
        # Helper to create properly quantized Decimal with 2 decimal places
        def to_decimal_2dp(value):
            """Convert value to Decimal with exactly 2 decimal places"""
            return Decimal(str(_parse_float(value))).quantize(Decimal('0.01'))

        kotak_fields = {
            'category': lim.get('Category', ''),
            # Monetary fields (absolute values)
            'net_balance': to_decimal_2dp(lim.get('Net')),
            'collateral_value': to_decimal_2dp(lim.get('CollateralValue')),
            'margin_available': to_decimal_2dp(lim.get('Collateral')),
            'margin_used': to_decimal_2dp(lim.get('MarginUsed')),
            # IMPORTANT: Kotak API naming is confusing!
            # Fields ending in "Prsnt" are ABSOLUTE values, not percentages
            # Fields ending in "PrcntPrsnt" are actual percentages
            # Only mapping the one true percentage field available:
            'margin_warning_pct': to_decimal_2dp(lim.get('MarginWarningPrcntPrsnt')),
            # Skip margin_used_percent, exposure_margin_pct, span_margin_pct
            # as API doesn't provide these as percentages (they're absolute values)
            'board_lot_limit': int(lim.get('BoardLotLimit', 0)),
        }

        # Assign only existing attributes
        for attr, val in kotak_fields.items():
            try:
                if hasattr(limit_record, attr):
                    setattr(limit_record, attr, val)
            except Exception as field_error:
                logger.error(f"Error setting {attr}={val}: {field_error}")
                raise

        limit_record.save()
        logger.info("Kotak Neo limits saved successfully")
    except (ValueError, InvalidOperation) as e:
        import traceback
        logger.error(f"Error saving Kotak Neo limits: {type(e).__name__}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Continue with positions even if limits fail
        pass

    # Fetch & save positions
    resp = client.positions()
    raw_positions = resp.get('data', [])

    pos_objs = []
    for p in raw_positions:
        try:
            buy_qty = int(p.get('cfBuyQty', 0)) + int(p.get('flBuyQty', 0))
            sell_qty = int(p.get('cfSellQty', 0)) + int(p.get('flSellQty', 0))
            net_q = buy_qty - sell_qty

            buy_amt = _parse_float(p.get('cfBuyAmt', 0)) + _parse_float(p.get('buyAmt', 0))
            sell_amt = _parse_float(p.get('cfSellAmt', 0)) + _parse_float(p.get('sellAmt', 0))

            # FIXED: Kotak Neo positions API returns stkPrc as 0.00
            # Need to fetch LTP using quotes API
            ltp = _parse_float(p.get('stkPrc', 0))

            # If LTP is 0, try to fetch it using quotes API
            if ltp == 0.0:
                try:
                    instrument_token = p.get('tok')

                    if instrument_token:
                        # FIXED: Kotak Neo quotes API signature: quotes(instrument_tokens, quote_type=None, isIndex=False)
                        quote_resp = client.quotes(
                            instrument_tokens=[instrument_token],  # Must be a list
                            isIndex=False
                        )

                        # Extract LTP from quote response
                        # Response format: {"data": [{"ltp": value, ...}]}
                        if quote_resp and isinstance(quote_resp, dict):
                            data = quote_resp.get('data', [])
                            if data and len(data) > 0:
                                ltp = _parse_float(data[0].get('ltp', 0))
                                if ltp == 0:  # Try 'last' field
                                    ltp = _parse_float(data[0].get('last', 0))
                except Exception as quote_error:
                    logger.warning(f"Could not fetch LTP for {p.get('sym')}: {quote_error}")

                # If we still don't have LTP, use average price as fallback
                if ltp == 0.0:
                    ltp = (buy_amt / buy_qty) if buy_qty > 0 else (
                        (sell_amt / sell_qty) if sell_qty > 0 else 0.0)
                    logger.info(f"Using average price as LTP fallback for {p.get('sym')}: ₹{ltp:,.2f}")

            # Calculate average price
            avg_price = (buy_amt / buy_qty) if net_q > 0 and buy_qty else (
                (sell_amt / sell_qty) if net_q < 0 and sell_qty else 0.0)

            # Calculate P&L
            realized_pnl = sell_amt - buy_amt
            # FIXED: Unrealized P&L = net_quantity * (ltp - avg_price)
            unrealized_pnl = net_q * (ltp - avg_price)

            # Convert to Decimal for database
            pos = BrokerPosition.objects.create(
                broker=BROKER_KOTAK,
                fetched_at=timezone.now(),
                symbol=p.get('sym', p.get('trdSym', '')),
                exchange_segment=p.get('exSeg', ''),
                product=p.get('prod', ''),
                buy_qty=buy_qty,
                sell_qty=sell_qty,
                net_quantity=net_q,
                buy_amount=Decimal(str(buy_amt)),
                sell_amount=Decimal(str(sell_amt)),
                ltp=Decimal(str(ltp)),
                average_price=Decimal(str(avg_price)),
                realized_pnl=Decimal(str(realized_pnl)),
                unrealized_pnl=Decimal(str(unrealized_pnl)),
            )
            pos_objs.append(pos)
        except (ValueError, InvalidOperation, ZeroDivisionError) as e:
            logger.error(f"Error processing Kotak position {p.get('sym', 'UNKNOWN')}: {e}")
            continue

    logger.info(f"Saved {len(pos_objs)} Kotak Neo positions")
    return limit_record, pos_objs


def auto_login_kotak_neo():
    """
    Perform Kotak Neo login and 2FA, returning session token and sid.

    This function uses the same session management as _get_authenticated_client(),
    reusing saved tokens when available to avoid OTP requirement.

    Returns:
        dict: {'token': str, 'sid': str}

    Raises:
        ValueError: If credentials not found
    """
    creds = CredentialStore.objects.filter(service='kotakneo').first()
    if not creds:
        raise ValueError("No Kotak Neo credentials found in CredentialStore")

    # Check if we have a valid saved session token
    saved_token = creds.sid  # JWT session token stored in sid field
    otp_code = creds.session_token  # OTP code

    if saved_token and _is_token_valid(saved_token):
        logger.info("Reusing saved Kotak Neo session token for auto_login")
        # Extract sid from JWT token (we don't save it separately anymore)
        try:
            payload = jwt.decode(saved_token, options={'verify_signature': False})
            sid = payload.get('jti', 'unknown')  # JWT ID as SID
        except:
            sid = 'unknown'

        return {
            'token': saved_token,
            'sid': sid
        }

    # No valid token, perform fresh login with OTP
    logger.info("Performing fresh Kotak Neo login for auto_login")
    client = NeoAPI(
        consumer_key=creds.api_key,
        consumer_secret=creds.api_secret,
        environment='prod'
    )
    client.login(pan=creds.username, password=creds.password)
    session_2fa = client.session_2fa(OTP=otp_code)
    data = session_2fa.get('data', {})

    session_token = data.get('token')
    session_sid = data.get('sid')

    # Save token for future use
    if session_token:
        creds.sid = session_token  # Store JWT token in sid field
        creds.last_session_update = timezone.now()
        creds.save(update_fields=['sid', 'last_session_update'])

        logger.info(f"Saved new Kotak Neo session token from auto_login (valid until midnight, SID: {session_sid[:20]}...)")

    return {
        'token': session_token,
        'sid': session_sid
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


def place_option_order(
    trading_symbol: str,
    transaction_type: str,  # 'B' (BUY) or 'S' (SELL)
    quantity: int,
    product: str = 'NRML',  # 'NRML', 'MIS', 'CNC'
    order_type: str = 'MKT',  # 'MKT' (Market) or 'L' (Limit)
    price: float = 0.0,
    trigger_price: float = 0.0,
    disclosed_quantity: int = 0,
    client=None  # Optional: reuse existing client
):
    """
    Place an options order via Kotak Neo API.

    Args:
        trading_symbol (str): Trading symbol (e.g., 'NIFTY25NOV24500CE')
        transaction_type (str): 'B' for BUY, 'S' for SELL
        quantity (int): Quantity to trade (must be in multiples of lot size)
        product (str): Product type - 'NRML', 'MIS', 'CNC'
        order_type (str): 'MKT' for Market, 'L' for Limit
        price (float): Price for limit orders (0 for market orders)
        trigger_price (float): Trigger price for SL orders
        disclosed_quantity (int): Disclosed quantity (0 for no disclosure)
        client: Optional authenticated client to reuse (avoids multiple logins)

    Returns:
        dict: Order response with order_id if successful, error details if failed
            Success: {'success': True, 'order_id': 'NEO123456', 'message': '...'}
            Failure: {'success': False, 'error': '...'}

    Example:
        >>> result = place_option_order(
        ...     trading_symbol='NIFTY25NOV24500CE',
        ...     transaction_type='B',
        ...     quantity=50,  # 1 lot for NIFTY
        ...     product='NRML',
        ...     order_type='MKT'
        ... )
        >>> print(result)
        {'success': True, 'order_id': 'NEO123456', 'message': 'Order placed successfully'}
    """
    try:
        # Use provided client or get new one
        if client is None:
            client = _get_authenticated_client()

        # Log order details before placing
        logger.info(f"Placing Neo order: symbol={trading_symbol}, type={transaction_type}, qty={quantity}, product={product}, order_type={order_type}")

        # Place order using Neo API
        response = client.place_order(
            exchange_segment='nse_fo',  # NSE F&O for options
            product=product,
            price=str(price) if price > 0 else '0',
            order_type=order_type,
            quantity=str(quantity),
            validity='DAY',
            trading_symbol=trading_symbol,
            transaction_type=transaction_type,
            amo='NO',  # After Market Order - NO for regular orders
            disclosed_quantity=str(disclosed_quantity),
            market_protection='0',
            pf='N',  # PF (Price Factor) - N for normal
            trigger_price=str(trigger_price) if trigger_price > 0 else '0',
            tag=None  # Optional tag for tracking
        )

        logger.info(f"Kotak Neo order response: {response}")

        # Check response status
        if response and response.get('stat') == 'Ok':
            order_id = response.get('nOrdNo', 'UNKNOWN')
            logger.info(f"✅ Order placed successfully: {order_id} for {trading_symbol}")

            return {
                'success': True,
                'order_id': order_id,
                'message': f'Order placed successfully. Order ID: {order_id}',
                'response': response
            }
        else:
            # Handle different error response formats
            if response:
                error_msg = response.get('errMsg') or response.get('message') or response.get('description', 'Unknown error')
                error_code = response.get('stCode') or response.get('code', '')
                full_error = f"[{error_code}] {error_msg}" if error_code else error_msg
            else:
                full_error = 'No response from API'

            logger.error(f"❌ Order placement failed: {full_error}")

            return {
                'success': False,
                'error': full_error,
                'response': response
            }

    except Exception as e:
        logger.exception(f"Exception in place_option_order: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def get_kotak_neo_client():
    """
    Get authenticated Kotak Neo client for placing orders.

    Returns:
        NeoAPI: Authenticated client instance

    Raises:
        ValueError: If authentication fails
    """
    try:
        return _get_authenticated_client()
    except Exception as e:
        logger.error(f"Failed to get Kotak Neo client: {e}")
        raise


def get_lot_size_from_neo(trading_symbol: str, client=None) -> int:
    """
    Get lot size for a trading symbol using Neo API search_scrip.

    Args:
        trading_symbol (str): Trading symbol (e.g., 'NIFTY25NOV27050CE')
        client: Optional authenticated client to reuse

    Returns:
        int: Lot size for the symbol

    Raises:
        ValueError: If symbol not found or lot size cannot be determined

    Example:
        >>> lot_size = get_lot_size_from_neo('NIFTY25NOV27050CE')
        >>> print(lot_size)  # 75
    """
    try:
        # Use provided client or get new one
        if client is None:
            client = _get_authenticated_client()

        # Parse symbol to extract components
        # Format: NIFTY25NOV27050CE
        # Extract: symbol=NIFTY, expiry=25NOV, strike=27050, option_type=CE

        import re

        # Pattern: (SYMBOL)(DDMMM)(STRIKE)(CE|PE)
        pattern = r'^([A-Z]+)(\d{2}[A-Z]{3})(\d+)(CE|PE)$'
        match = re.match(pattern, trading_symbol)

        if not match:
            logger.warning(f"Unable to parse trading symbol: {trading_symbol}, using default lot size 75")
            return 75  # Default for NIFTY

        symbol_name = match.group(1)  # NIFTY
        expiry_date = match.group(2)  # 25NOV
        strike_price = match.group(3)  # 27050
        option_type = match.group(4)  # CE or PE

        # Convert expiry to Neo format: 25NOV → 25NOV2025
        # Assume current year if not specified
        from datetime import datetime
        current_year = datetime.now().year
        expiry_full = f"{expiry_date}{current_year}"  # 25NOV2025

        logger.info(f"Searching scrip: symbol={symbol_name}, expiry={expiry_full}, strike={strike_price}, type={option_type}")

        # Search using Neo API
        result = client.search_scrip(
            exchange_segment='nse_fo',
            symbol=symbol_name,
            expiry=expiry_full,
            option_type=option_type,
            strike_price=strike_price
        )

        if result and isinstance(result, list) and len(result) > 0:
            scrip = result[0]
            lot_size = scrip.get('lLotSize', scrip.get('iLotSize', 75))
            logger.info(f"✅ Found lot size for {trading_symbol}: {lot_size}")
            return int(lot_size)
        else:
            logger.warning(f"No scrip found for {trading_symbol}, using default lot size 75")
            return 75  # Default for NIFTY

    except Exception as e:
        logger.error(f"Error fetching lot size for {trading_symbol}: {e}")
        logger.warning(f"Using default lot size 75")
        return 75  # Default fallback


def get_lot_size_from_neo_with_token(trading_symbol: str, client=None) -> dict:
    """
    Get lot size AND instrument token for a trading symbol using Neo API search_scrip.

    Args:
        trading_symbol (str): Trading symbol (e.g., 'NIFTY25NOV27050CE')
        client: Optional authenticated client to reuse

    Returns:
        dict: {
            'lot_size': int,
            'token': str,
            'expiry': str,
            'exchange_segment': str,
            'symbol': str
        }

    Example:
        >>> result = get_lot_size_from_neo_with_token('NIFTY25NOV27050CE')
        >>> print(result)
        {'lot_size': 75, 'token': '12345', 'expiry': '28-NOV-2024', ...}
    """
    try:
        # Use provided client or get new one
        if client is None:
            client = _get_authenticated_client()

        # Parse symbol to extract components
        import re
        pattern = r'^([A-Z]+)(\d{2}[A-Z]{3})(\d+)(CE|PE)$'
        match = re.match(pattern, trading_symbol)

        if not match:
            logger.warning(f"Unable to parse trading symbol: {trading_symbol}, using defaults")
            return {
                'lot_size': 75,
                'token': 'N/A',
                'expiry': 'N/A',
                'exchange_segment': 'nse_fo',
                'symbol': trading_symbol
            }

        symbol_name = match.group(1)  # NIFTY
        expiry_date = match.group(2)  # 25NOV
        strike_price = match.group(3)  # 27050
        option_type = match.group(4)  # CE or PE

        # Convert expiry to Neo format
        from datetime import datetime
        current_year = datetime.now().year
        expiry_full = f"{expiry_date}{current_year}"  # 25NOV2025

        logger.info(f"Searching scrip with token: symbol={symbol_name}, expiry={expiry_full}, strike={strike_price}, type={option_type}")

        # Search using Neo API
        result = client.search_scrip(
            exchange_segment='nse_fo',
            symbol=symbol_name,
            expiry=expiry_full,
            option_type=option_type,
            strike_price=strike_price
        )

        if result and isinstance(result, list) and len(result) > 0:
            scrip = result[0]
            lot_size = scrip.get('lLotSize', scrip.get('iLotSize', 75))
            token = scrip.get('pTrdSymbol', scrip.get('pSymbol', 'N/A'))
            expiry_display = scrip.get('pExchSeg', expiry_full)

            logger.info(f"✅ Found scrip details for {trading_symbol}: lot_size={lot_size}, token={token}")

            return {
                'lot_size': int(lot_size),
                'token': str(token),
                'expiry': expiry_display,
                'exchange_segment': 'nse_fo',
                'symbol': trading_symbol
            }
        else:
            logger.warning(f"No scrip found for {trading_symbol}, using defaults")
            return {
                'lot_size': 75,
                'token': 'N/A',
                'expiry': expiry_full,
                'exchange_segment': 'nse_fo',
                'symbol': trading_symbol
            }

    except Exception as e:
        logger.error(f"Error fetching scrip details for {trading_symbol}: {e}")
        return {
            'lot_size': 75,
            'token': 'N/A',
            'expiry': 'N/A',
            'exchange_segment': 'nse_fo',
            'symbol': trading_symbol
        }


def place_strangle_orders_in_batches(
    call_symbol: str,
    put_symbol: str,
    total_lots: int,
    batch_size: int = 20,
    delay_seconds: int = 20,
    product: str = 'NRML'
):
    """
    Place strangle orders (Call SELL + Put SELL) in batches with delays.

    This function places orders in batches to avoid overwhelming the broker API
    and to provide better execution monitoring.

    Args:
        call_symbol (str): Call option trading symbol (e.g., 'NIFTY25NOV24500CE')
        put_symbol (str): Put option trading symbol (e.g., 'NIFTY25NOV24000PE')
        total_lots (int): Total number of lots to trade
        batch_size (int): Maximum lots per order (default: 20, Neo API limit)
        delay_seconds (int): Delay between orders in seconds (default: 20)
        product (str): Product type - 'NRML', 'MIS' (default: 'NRML')

    Returns:
        dict: Batch execution results
            {
                'success': True/False,
                'total_lots': int,
                'batches_completed': int,
                'call_orders': [list of order results],
                'put_orders': [list of order results],
                'summary': {
                    'call_success_count': int,
                    'put_success_count': int,
                    'call_failed_count': int,
                    'put_failed_count': int
                },
                'error': str (if failed)
            }

    Example:
        >>> # For 167 lots: Places 9 orders (8×20 lots + 1×7 lots) with 20s delays
        >>> result = place_strangle_orders_in_batches(
        ...     call_symbol='NIFTY25NOV24500CE',
        ...     put_symbol='NIFTY25NOV24000PE',
        ...     total_lots=167,
        ...     batch_size=20,
        ...     delay_seconds=20
        ... )
        >>> print(result['summary'])
        >>> # Result: 9 call orders + 9 put orders = 18 total orders
        {'call_success_count': 9, 'put_success_count': 9, 'total_orders_placed': 18}
    """
    import time
    import threading

    logger.info(f"Starting batch order placement: {total_lots} lots in batches of {batch_size}")

    # Get single authenticated session for all orders (optimization)
    try:
        client = _get_authenticated_client()
        logger.info("✅ Single Neo API session established for all orders")
    except Exception as e:
        logger.error(f"Failed to establish Neo session: {e}")
        return {
            'success': False,
            'error': f'Authentication failed: {str(e)}',
            'call_orders': [],
            'put_orders': []
        }

    # Get lot size dynamically from Neo API (using same client)
    lot_size = get_lot_size_from_neo(call_symbol, client=client)
    logger.info(f"Using lot size: {lot_size} for {call_symbol}")

    call_orders = []
    put_orders = []
    batches_completed = 0

    # Calculate number of batches
    num_batches = (total_lots + batch_size - 1) // batch_size  # Ceiling division

    try:
        for batch_num in range(1, num_batches + 1):
            # Calculate lots for this batch
            remaining_lots = total_lots - (batch_num - 1) * batch_size
            current_batch_lots = min(batch_size, remaining_lots)
            current_batch_quantity = current_batch_lots * lot_size

            logger.info(f"Batch {batch_num}/{num_batches}: Placing {current_batch_lots} lots ({current_batch_quantity} qty)")

            # Optimization: Place CALL and PUT orders in parallel using threads
            call_result = {}
            put_result = {}

            def place_call_order():
                nonlocal call_result
                call_result = place_option_order(
                    trading_symbol=call_symbol,
                    transaction_type='S',  # SELL
                    quantity=current_batch_quantity,
                    product=product,
                    order_type='MKT',
                    client=client  # Reuse session
                )

            def place_put_order():
                nonlocal put_result
                put_result = place_option_order(
                    trading_symbol=put_symbol,
                    transaction_type='S',  # SELL
                    quantity=current_batch_quantity,
                    product=product,
                    order_type='MKT',
                    client=client  # Reuse session
                )

            # Start both orders in parallel
            call_thread = threading.Thread(target=place_call_order)
            put_thread = threading.Thread(target=place_put_order)

            logger.info(f"⚡ Placing CALL and PUT orders in parallel...")
            call_thread.start()
            put_thread.start()

            # Wait for both to complete
            call_thread.join()
            put_thread.join()

            # Record results
            call_orders.append({
                'batch': batch_num,
                'lots': current_batch_lots,
                'quantity': current_batch_quantity,
                'result': call_result
            })

            put_orders.append({
                'batch': batch_num,
                'lots': current_batch_lots,
                'quantity': current_batch_quantity,
                'result': put_result
            })

            if call_result.get('success'):
                logger.info(f"✅ CALL SELL batch {batch_num}: Order ID {call_result['order_id']}")
            else:
                logger.error(f"❌ CALL SELL batch {batch_num} failed: {call_result.get('error', 'Unknown error')}")

            if put_result.get('success'):
                logger.info(f"✅ PUT SELL batch {batch_num}: Order ID {put_result['order_id']}")
            else:
                logger.error(f"❌ PUT SELL batch {batch_num} failed: {put_result.get('error', 'Unknown error')}")

            batches_completed += 1

            # Delay before next batch (except for last batch)
            # We only wait between batches, not between CALL and PUT
            if batch_num < num_batches:
                logger.info(f"⏱️  Waiting {delay_seconds} seconds before next batch...")
                time.sleep(delay_seconds)

        # Calculate summary
        call_success_count = sum(1 for order in call_orders if order['result']['success'])
        put_success_count = sum(1 for order in put_orders if order['result']['success'])
        call_failed_count = len(call_orders) - call_success_count
        put_failed_count = len(put_orders) - put_success_count

        success = (call_failed_count == 0 and put_failed_count == 0)

        logger.info(f"Batch execution complete: {batches_completed}/{num_batches} batches processed")
        logger.info(f"Summary: Call {call_success_count}/{len(call_orders)} success, Put {put_success_count}/{len(put_orders)} success")

        return {
            'success': success,
            'total_lots': total_lots,
            'batches_completed': batches_completed,
            'total_batches': num_batches,
            'call_orders': call_orders,
            'put_orders': put_orders,
            'summary': {
                'call_success_count': call_success_count,
                'put_success_count': put_success_count,
                'call_failed_count': call_failed_count,
                'put_failed_count': put_failed_count,
                'total_orders_placed': len(call_orders) + len(put_orders)
            }
        }

    except Exception as e:
        logger.exception(f"Error in batch order placement: {e}")
        return {
            'success': False,
            'error': str(e),
            'total_lots': total_lots,
            'batches_completed': batches_completed,
            'call_orders': call_orders,
            'put_orders': put_orders
        }
