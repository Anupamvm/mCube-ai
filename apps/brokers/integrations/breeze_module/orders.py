"""
ICICI Breeze Orders - Order Placement with SecurityMaster

This module provides order placement functions using SecurityMaster for correct instrument codes.
"""

import logging
from typing import Dict, Optional

from .client import get_breeze_client
from .expiry import get_next_nifty_expiry

logger = logging.getLogger(__name__)


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
            logger.info(f"Order placed successfully! Order ID: {order_id}")
        else:
            error = order_response.get('Error', 'Unknown error')
            logger.error(f"Order placement failed: {error}")
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
            logger.info(f"Order placed successfully! Order ID: {order_id}")
        else:
            error = order_response.get('Error', 'Unknown error')
            logger.error(f"Order placement failed: {error}")
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
