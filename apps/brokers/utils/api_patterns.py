"""
Common API patterns for broker integrations.

This module extracts duplicate patterns found across broker API code:
- Customer details fetching (Breeze)
- Margin data fetching
- Position data processing
- Response validation

Eliminates duplicate code in:
- breeze.py lines 643-648, 697-702 (customer details)
- breeze.py lines 651-716 (margin fetching)
- kotak_neo.py and breeze.py (position processing)
"""

import logging
import json
import hashlib
import requests
from datetime import datetime, timezone as dt_timezone
from typing import Dict, Optional, Tuple
from decimal import Decimal

from apps.core.utils.error_handlers import BrokerAPIException
from apps.brokers.utils.common import parse_float, parse_decimal

logger = logging.getLogger(__name__)


# ============================================================================
# BREEZE API PATTERNS
# ============================================================================

def get_breeze_customer_details(api_key: str, api_secret: str, session_token: str) -> Tuple[str, Dict]:
    """
    Fetch customer details and rest token from Breeze API.

    This pattern appears in breeze.py at:
    - Lines 643-648 (get_nfo_margin function)
    - Lines 697-702 (fetch_and_save_breeze_data function)

    Args:
        api_key: Breeze API key
        api_secret: Breeze API secret
        session_token: Current session token

    Returns:
        tuple: (rest_token, customer_details_response)

    Raises:
        BrokerAPIException: If API call fails

    Example:
        >>> rest_token, details = get_breeze_customer_details(api_key, secret, token)
        >>> print(f"Rest Token: {rest_token}")
    """
    try:
        # Prepare customer details request
        cd_url = "https://api.icicidirect.com/breezeapi/api/v1/customerdetails"
        time_stamp = datetime.now(dt_timezone.utc).isoformat()[:19] + '.000Z'
        cd_payload = json.dumps({"SessionToken": session_token, "AppKey": api_key})
        cd_headers = {'Content-Type': 'application/json'}

        # Make API call
        logger.debug("Fetching Breeze customer details")
        cd_resp = requests.get(cd_url, headers=cd_headers, data=cd_payload)
        cd_data = cd_resp.json()

        # Extract rest token
        rest_token = cd_data.get('Success', {}).get('session_token')

        if not rest_token:
            raise BrokerAPIException(
                "Failed to get rest token from customer details",
                broker='breeze',
                operation='get_customer_details',
                original_error=cd_data
            )

        logger.debug("Successfully fetched Breeze customer details")
        return rest_token, cd_data

    except requests.RequestException as e:
        raise BrokerAPIException(
            f"Network error fetching customer details: {str(e)}",
            broker='breeze',
            operation='get_customer_details',
            original_error=e
        )
    except Exception as e:
        raise BrokerAPIException(
            f"Error fetching customer details: {str(e)}",
            broker='breeze',
            operation='get_customer_details',
            original_error=e
        )


def fetch_breeze_margin_data(
    api_key: str,
    api_secret: str,
    rest_token: str,
    exchange_code: str = "NFO"
) -> Dict:
    """
    Fetch margin data from Breeze API for given exchange.

    This pattern appears in breeze.py at:
    - Lines 651-674 (get_nfo_margin function)
    - Lines 705-716 (fetch_and_save_breeze_data function)

    Args:
        api_key: Breeze API key
        api_secret: Breeze API secret
        rest_token: Rest token from customer details
        exchange_code: Exchange code (default: "NFO")

    Returns:
        dict: Margin data from Breeze API

    Raises:
        BrokerAPIException: If API call fails

    Example:
        >>> margin = fetch_breeze_margin_data(api_key, secret, rest_token)
        >>> print(f"Available: {margin.get('cash_limit')}")
    """
    try:
        # Prepare margin request
        margin_url = "https://api.icicidirect.com/breezeapi/api/v1/margin"
        time_stamp = datetime.now(dt_timezone.utc).isoformat()[:19] + '.000Z'
        payload = json.dumps({"exchange_code": exchange_code}, separators=(',', ':'))

        # Calculate checksum
        checksum = hashlib.sha256((time_stamp + payload + api_secret).encode()).hexdigest()

        # Prepare headers
        headers = {
            'Content-Type': 'application/json',
            'X-Checksum': 'token ' + checksum,
            'X-Timestamp': time_stamp,
            'X-AppKey': api_key,
            'X-SessionToken': rest_token,
        }

        # Make API call
        logger.debug(f"Fetching Breeze margin data for {exchange_code}")
        margin_resp = requests.get(margin_url, headers=headers, data=payload)
        margin_data = margin_resp.json()

        # Validate response
        if margin_data.get('Status') != 200:
            raise BrokerAPIException(
                f"Margin API returned error: {margin_data.get('Error')}",
                broker='breeze',
                operation='fetch_margin',
                original_error=margin_data
            )

        margins = margin_data.get('Success', {})
        logger.info(f"Breeze margin fetched: cash_limit={margins.get('cash_limit')}, "
                   f"amount_allocated={margins.get('amount_allocated')}")

        return margins

    except requests.RequestException as e:
        raise BrokerAPIException(
            f"Network error fetching margin data: {str(e)}",
            broker='breeze',
            operation='fetch_margin',
            original_error=e
        )
    except Exception as e:
        raise BrokerAPIException(
            f"Error fetching margin data: {str(e)}",
            broker='breeze',
            operation='fetch_margin',
            original_error=e
        )


# ============================================================================
# POSITION PROCESSING PATTERNS
# ============================================================================

def calculate_position_pnl(
    quantity: int,
    avg_price: float,
    ltp: float
) -> Tuple[Decimal, Decimal]:
    """
    Calculate unrealized and realized P&L for a position.

    Common pattern across:
    - kotak_neo.py (lines 194-214)
    - breeze.py (lines 744-752)

    Formula:
    - For LONG (quantity > 0): (LTP - Avg) * quantity
    - For SHORT (quantity < 0): (Avg - LTP) * abs(quantity)

    Args:
        quantity: Net quantity (positive = long, negative = short)
        avg_price: Average execution price
        ltp: Last traded price

    Returns:
        tuple: (unrealized_pnl, realized_pnl)

    Example:
        >>> unrealized, realized = calculate_position_pnl(50, 100.0, 105.0)
        >>> print(f"Unrealized P&L: ₹{unrealized}")
        Unrealized P&L: ₹250.00
    """
    try:
        # Parse values safely
        qty = int(quantity) if quantity else 0
        avg = parse_float(avg_price)
        current = parse_float(ltp)

        # Calculate unrealized P&L based on position direction
        if qty > 0:
            # LONG position: profit if LTP > avg_price
            unrealized = (current - avg) * qty
        elif qty < 0:
            # SHORT position: profit if LTP < avg_price
            unrealized = (avg - current) * abs(qty)
        else:
            unrealized = 0.0

        # Realized P&L is 0 for open positions (only matters when closing)
        realized = 0.0

        # Convert to Decimal for precision
        unrealized_decimal = parse_decimal(unrealized, decimal_places=2)
        realized_decimal = parse_decimal(realized, decimal_places=2)

        return unrealized_decimal, realized_decimal

    except Exception as e:
        logger.error(f"Error calculating P&L: {e}")
        return Decimal('0.00'), Decimal('0.00')


def normalize_position_data(
    symbol: str,
    exchange: str,
    product: str,
    quantity: int,
    avg_price: float,
    ltp: float,
    buy_qty: int = 0,
    sell_qty: int = 0,
    buy_amount: float = 0.0,
    sell_amount: float = 0.0
) -> Dict:
    """
    Normalize position data into standard format.

    Different brokers return different field names and formats.
    This function standardizes them for consistent processing.

    Args:
        symbol: Trading symbol
        exchange: Exchange segment
        product: Product type
        quantity: Net quantity
        avg_price: Average price
        ltp: Last traded price
        buy_qty: Total buy quantity
        sell_qty: Total sell quantity
        buy_amount: Total buy amount
        sell_amount: Total sell amount

    Returns:
        dict: Normalized position data

    Example:
        >>> position = normalize_position_data(
        ...     symbol='NIFTY25DEC24500CE',
        ...     exchange='NSE_FO',
        ...     product='NRML',
        ...     quantity=50,
        ...     avg_price=150.50,
        ...     ltp=155.00
        ... )
        >>> print(position['unrealized_pnl'])
        Decimal('225.00')
    """
    # Calculate P&L
    unrealized_pnl, realized_pnl = calculate_position_pnl(quantity, avg_price, ltp)

    # Parse all numeric values
    return {
        'symbol': symbol,
        'exchange': exchange,
        'product': product,
        'quantity': int(quantity) if quantity else 0,
        'avg_price': parse_decimal(avg_price, 2),
        'ltp': parse_decimal(ltp, 2),
        'buy_qty': int(buy_qty) if buy_qty else 0,
        'sell_qty': int(sell_qty) if sell_qty else 0,
        'buy_amount': parse_decimal(buy_amount, 2),
        'sell_amount': parse_decimal(sell_amount, 2),
        'unrealized_pnl': unrealized_pnl,
        'realized_pnl': realized_pnl,
    }


# ============================================================================
# API RESPONSE VALIDATION
# ============================================================================

def validate_broker_response(
    response: Dict,
    broker: str,
    operation: str,
    required_fields: Optional[list] = None
) -> Dict:
    """
    Validate broker API response and extract success data.

    Common validation pattern across all broker APIs:
    - Check if response exists
    - Check status code
    - Extract success data
    - Validate required fields

    Args:
        response: API response dict
        broker: Broker name ('neo', 'breeze')
        operation: Operation name (for error messages)
        required_fields: List of fields that must exist in response

    Returns:
        dict: Validated success data

    Raises:
        BrokerAPIException: If response is invalid

    Example:
        >>> response = {'Status': 200, 'Success': {'order_id': '123'}}
        >>> data = validate_broker_response(
        ...     response,
        ...     broker='breeze',
        ...     operation='place_order',
        ...     required_fields=['order_id']
        ... )
        >>> print(data['order_id'])
        123
    """
    if not response:
        raise BrokerAPIException(
            f"Empty response from {broker} API",
            broker=broker,
            operation=operation
        )

    # Check status code
    status = response.get('Status')
    if status != 200:
        error_msg = response.get('Error', 'Unknown error')
        raise BrokerAPIException(
            f"{broker} API error: {error_msg}",
            broker=broker,
            operation=operation,
            original_error=response
        )

    # Extract success data
    success_data = response.get('Success')
    if success_data is None:
        raise BrokerAPIException(
            f"No success data in {broker} API response",
            broker=broker,
            operation=operation,
            original_error=response
        )

    # Validate required fields
    if required_fields:
        missing_fields = [f for f in required_fields if f not in success_data]
        if missing_fields:
            raise BrokerAPIException(
                f"Missing required fields in {broker} response: {', '.join(missing_fields)}",
                broker=broker,
                operation=operation,
                original_error=response
            )

    return success_data


# ============================================================================
# CONFIGURATION URLS (to be moved to config module in Phase 4)
# ============================================================================

BREEZE_API_URLS = {
    'customer_details': 'https://api.icicidirect.com/breezeapi/api/v1/customerdetails',
    'margin': 'https://api.icicidirect.com/breezeapi/api/v1/margin',
    'orders': 'https://api.icicidirect.com/breezeapi/api/v1/orders',
}

NSE_URLS = {
    'base': 'https://www.nseindia.com',
    'option_chain': 'https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY',
}
