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
    Get authenticated Kotak Neo API client using credentials from database.

    Session Management:
    - First checks if a valid session token exists in the database
    - If valid token exists, reuses it to avoid OTP requirement
    - If no valid token, performs full login with OTP and saves new token
    - Token is valid until midnight (approximately 9-10 hours)

    Returns:
        NeoAPI: Authenticated client instance

    Raises:
        ValueError: If credentials not found or authentication fails
    """
    creds = CredentialStore.objects.filter(service='kotakneo').first()
    if not creds:
        raise ValueError("No Kotak Neo credentials found in CredentialStore")

    # Check if we have a valid saved session token (stored in creds.session_token field)
    # Note: session_token field was used for OTP, now repurposed for storing JWT session token
    # OTP is now stored in creds.neo_password field
    saved_token = creds.sid  # Using sid field to store the JWT session token
    otp_code = creds.session_token  # OTP code

    if saved_token and _is_token_valid(saved_token):
        logger.info("Reusing saved Kotak Neo session token (no OTP required)")
        try:
            # Create client with existing token
            client = NeoAPI(
                access_token=saved_token,
                environment='prod'
            )
            # Test the token by making a simple API call
            client.limits(segment="ALL", exchange="ALL", product="ALL")
            return client
        except Exception as e:
            logger.warning(f"Saved token failed, will re-authenticate: {e}")
            # Token is invalid, proceed with fresh login

    # No valid token, perform full login with OTP
    logger.info("Performing fresh Kotak Neo login with OTP")
    client = NeoAPI(
        consumer_key=creds.api_key,
        consumer_secret=creds.api_secret,
        environment='prod'
    )

    # Perform login
    client.login(pan=creds.username, password=creds.password)

    # Complete 2FA with OTP
    session_response = client.session_2fa(OTP=otp_code)

    # Save session token for future use
    if session_response and 'data' in session_response:
        jwt_session_token = session_response['data'].get('token')
        session_sid = session_response['data'].get('sid')

        if jwt_session_token:
            # Save JWT session token to sid field for reuse
            # Save session ID to username field (as it's not used for Kotak Neo)
            creds.sid = jwt_session_token  # Store JWT token in sid field
            creds.last_session_update = timezone.now()
            creds.save(update_fields=['sid', 'last_session_update'])

            logger.info(f"Saved new Kotak Neo session token (valid until midnight, SID: {session_sid[:20]}...)")

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
