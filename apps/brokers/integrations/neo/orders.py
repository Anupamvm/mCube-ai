"""
Kotak Neo Orders - Order Placement

This module provides functions to place orders via Kotak Neo API.
"""

import logging

from .client import _get_authenticated_client

logger = logging.getLogger(__name__)


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
            logger.info(f"Order placed successfully: {order_id} for {trading_symbol}")

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

            logger.error(f"Order placement failed: {full_error}")

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
