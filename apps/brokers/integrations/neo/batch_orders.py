"""
Kotak Neo Batch Orders - Batch Order Placement and Position Closing

This module provides functions to place orders in batches with delays.
"""

import logging
import time
import threading

from django.core.cache import cache

from .client import _get_authenticated_client
from .orders import place_option_order
from .quotes import get_lot_size_from_neo

logger = logging.getLogger(__name__)


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
    """
    logger.info(f"Starting batch order placement: {total_lots} lots in batches of {batch_size}")

    # Get single authenticated session for all orders (optimization)
    try:
        client = _get_authenticated_client()
        logger.info("Single Neo API session established for all orders")
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

            logger.info(f"Placing CALL and PUT orders in parallel...")
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
                logger.info(f"CALL SELL batch {batch_num}: Order ID {call_result['order_id']}")
            else:
                logger.error(f"CALL SELL batch {batch_num} failed: {call_result.get('error', 'Unknown error')}")

            if put_result.get('success'):
                logger.info(f"PUT SELL batch {batch_num}: Order ID {put_result['order_id']}")
            else:
                logger.error(f"PUT SELL batch {batch_num} failed: {put_result.get('error', 'Unknown error')}")

            batches_completed += 1

            # Delay before next batch (except for last batch)
            if batch_num < num_batches:
                logger.info(f"Waiting {delay_seconds} seconds before next batch...")
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


def close_position_in_batches(
    trading_symbol: str,
    total_quantity: int,
    transaction_type: str,  # 'B' (BUY to close SHORT) or 'S' (SELL to close LONG)
    product: str = 'NRML',
    batch_size: int = 20,
    delay_seconds: int = 20,
    position_type: str = 'OPTION',  # 'OPTION' or 'FUTURE'
    cancellation_key: str = None,  # Cache key to check for cancellation between batches
    progress_key: str = None  # Cache key for progress tracking
):
    """
    Close a position (futures or options) in batches with delays.

    Args:
        trading_symbol (str): Trading symbol (e.g., 'NIFTY25DECFUT', 'NIFTY25NOV24500CE')
        total_quantity (int): Total quantity to close (in shares/contracts)
        transaction_type (str): 'B' to close SHORT position, 'S' to close LONG position
        product (str): Product type - 'NRML', 'MIS' (default: 'NRML')
        batch_size (int): Maximum lots per order (default: 20, Neo API limit)
        delay_seconds (int): Delay between orders in seconds (default: 20)
        position_type (str): 'OPTION' or 'FUTURE' (default: 'OPTION')
        cancellation_key (str): Cache key to check for cancellation
        progress_key (str): Cache key for progress tracking

    Returns:
        dict: Batch execution results
    """
    logger.info(f"Starting batch position closing: {total_quantity} qty in batches")

    # Get single authenticated session for all orders
    try:
        client = _get_authenticated_client()
        logger.info("Single Neo API session established for closing position")
    except Exception as e:
        logger.error(f"Failed to establish Neo session: {e}")
        return {
            'success': False,
            'error': f'Authentication failed: {str(e)}',
            'orders': []
        }

    # Get lot size dynamically from Neo API
    lot_size = get_lot_size_from_neo(trading_symbol, client=client)
    logger.info(f"Using lot size: {lot_size} for {trading_symbol}")

    # Calculate total lots
    total_lots = total_quantity // lot_size if lot_size > 0 else 0
    logger.info(f"Total quantity: {total_quantity} shares = {total_lots} lots")

    orders = []
    batches_completed = 0

    # Calculate number of batches
    num_batches = (total_lots + batch_size - 1) // batch_size  # Ceiling division

    # Initialize progress
    if progress_key:
        cache.set(progress_key, {
            'batches_completed': 0,
            'total_batches': num_batches,
            'current_batch': None,
            'is_cancelled': False,
            'is_complete': False,
            'is_success': False,
            'last_log_message': f'Calculated {num_batches} batches for {total_lots} lots',
            'last_log_type': 'info'
        }, 600)

    try:
        for batch_num in range(1, num_batches + 1):
            # Check for cancellation before processing batch
            if cancellation_key and cache.get(cancellation_key):
                logger.warning(f"Order placement cancelled by user at batch {batch_num}/{num_batches}")

                # Update progress
                if progress_key:
                    cache.set(progress_key, {
                        'batches_completed': batches_completed,
                        'total_batches': num_batches,
                        'current_batch': None,
                        'is_cancelled': True,
                        'is_complete': True,
                        'is_success': False,
                        'last_log_message': f'Cancelled at batch {batch_num}/{num_batches}',
                        'last_log_type': 'warning'
                    }, 600)

                success_count = sum(1 for o in orders if o['result'].get('success'))
                failed_count = len(orders) - success_count
                return {
                    'success': True,
                    'cancelled': True,
                    'total_quantity': total_quantity,
                    'batches_completed': batches_completed,
                    'total_batches': num_batches,
                    'orders': orders,
                    'summary': {
                        'success_count': success_count,
                        'failed_count': failed_count,
                        'total_orders_placed': len(orders)
                    },
                    'message': f'Order placement stopped by user. Completed {batches_completed}/{num_batches} batches.'
                }

            # Calculate lots for this batch
            remaining_lots = total_lots - (batch_num - 1) * batch_size
            current_batch_lots = min(batch_size, remaining_lots)
            current_batch_quantity = current_batch_lots * lot_size

            logger.info(f"Batch {batch_num}/{num_batches}: Closing {current_batch_lots} lots ({current_batch_quantity} qty)")

            # Update progress - starting batch
            if progress_key:
                cache.set(progress_key, {
                    'batches_completed': batches_completed,
                    'total_batches': num_batches,
                    'current_batch': {
                        'batch_num': batch_num,
                        'lots': current_batch_lots,
                        'quantity': current_batch_quantity
                    },
                    'is_cancelled': False,
                    'is_complete': False,
                    'is_success': False,
                    'last_log_message': f'Processing batch {batch_num}/{num_batches}: {current_batch_lots} lots',
                    'last_log_type': 'info'
                }, 600)

            # Place exit order
            order_result = place_option_order(
                trading_symbol=trading_symbol,
                transaction_type=transaction_type,
                quantity=current_batch_quantity,
                product=product,
                order_type='MKT',
                client=client  # Reuse session
            )

            # Record result
            orders.append({
                'batch': batch_num,
                'lots': current_batch_lots,
                'quantity': current_batch_quantity,
                'result': order_result
            })

            batches_completed += 1

            if order_result.get('success'):
                logger.info(f"Exit batch {batch_num}: Order ID {order_result['order_id']}")
                # Update progress - batch succeeded
                if progress_key:
                    cache.set(progress_key, {
                        'batches_completed': batches_completed,
                        'total_batches': num_batches,
                        'current_batch': None,
                        'is_cancelled': False,
                        'is_complete': False,
                        'is_success': False,
                        'last_log_message': f'Batch {batch_num}/{num_batches} completed successfully',
                        'last_log_type': 'success'
                    }, 600)
            else:
                # Batch failed - STOP immediately
                error_msg = order_result.get('error', 'Unknown error')
                logger.error(f"Exit batch {batch_num} failed: {error_msg}")

                # Update progress - batch failed and STOP
                if progress_key:
                    cache.set(progress_key, {
                        'batches_completed': batches_completed,
                        'total_batches': num_batches,
                        'current_batch': None,
                        'is_cancelled': False,
                        'is_complete': True,
                        'is_success': False,
                        'last_log_message': f'Batch {batch_num}/{num_batches} failed. Stopping execution.',
                        'last_log_type': 'error'
                    }, 600)

                # Return immediately with failure
                success_count = sum(1 for o in orders if o['result'].get('success'))
                failed_count = len(orders) - success_count
                return {
                    'success': False,
                    'error': f'Batch {batch_num} failed: {error_msg}',
                    'total_quantity': total_quantity,
                    'total_lots': total_lots,
                    'batches_completed': batches_completed,
                    'total_batches': num_batches,
                    'orders': orders,
                    'summary': {
                        'success_count': success_count,
                        'failed_count': failed_count,
                        'total_orders_placed': len(orders)
                    },
                    'message': f'Stopped at batch {batch_num}/{num_batches} due to failure.'
                }

            # Check for cancellation after batch completes
            if cancellation_key and cache.get(cancellation_key):
                logger.warning(f"Order placement cancelled by user after batch {batch_num}/{num_batches}")

                if progress_key:
                    cache.set(progress_key, {
                        'batches_completed': batches_completed,
                        'total_batches': num_batches,
                        'current_batch': None,
                        'is_cancelled': True,
                        'is_complete': True,
                        'is_success': False,
                        'last_log_message': f'Cancelled after batch {batch_num}/{num_batches}. Completed {batches_completed} batches.',
                        'last_log_type': 'warning'
                    }, 600)

                success_count = sum(1 for o in orders if o['result'].get('success'))
                failed_count = len(orders) - success_count
                return {
                    'success': True,
                    'cancelled': True,
                    'total_quantity': total_quantity,
                    'batches_completed': batches_completed,
                    'total_batches': num_batches,
                    'orders': orders,
                    'summary': {
                        'success_count': success_count,
                        'failed_count': failed_count,
                        'total_orders_placed': len(orders)
                    },
                    'message': f'Order placement stopped by user. Completed {batches_completed}/{num_batches} batches.'
                }

            # Delay before next batch (except for last batch)
            if batch_num < num_batches:
                logger.info(f"Waiting {delay_seconds} seconds before next batch...")
                time.sleep(delay_seconds)

                # Check for cancellation after sleep
                if cancellation_key and cache.get(cancellation_key):
                    logger.warning(f"Order placement cancelled by user during wait after batch {batch_num}/{num_batches}")

                    if progress_key:
                        cache.set(progress_key, {
                            'batches_completed': batches_completed,
                            'total_batches': num_batches,
                            'current_batch': None,
                            'is_cancelled': True,
                            'is_complete': True,
                            'is_success': False,
                            'last_log_message': f'Cancelled during wait after batch {batch_num}/{num_batches}. Completed {batches_completed} batches.',
                            'last_log_type': 'warning'
                        }, 600)

                    success_count = sum(1 for o in orders if o['result'].get('success'))
                    failed_count = len(orders) - success_count
                    return {
                        'success': True,
                        'cancelled': True,
                        'total_quantity': total_quantity,
                        'batches_completed': batches_completed,
                        'total_batches': num_batches,
                        'orders': orders,
                        'summary': {
                            'success_count': success_count,
                            'failed_count': failed_count,
                            'total_orders_placed': len(orders)
                        },
                        'message': f'Order placement stopped by user. Completed {batches_completed}/{num_batches} batches.'
                    }

        # Calculate summary
        success_count = sum(1 for order in orders if order['result']['success'])
        failed_count = len(orders) - success_count

        success = (failed_count == 0)

        logger.info(f"Batch execution complete: {batches_completed}/{num_batches} batches processed")
        logger.info(f"Summary: {success_count}/{len(orders)} success")

        # Final progress update
        if progress_key:
            cache.set(progress_key, {
                'batches_completed': batches_completed,
                'total_batches': num_batches,
                'current_batch': None,
                'is_cancelled': False,
                'is_complete': True,
                'is_success': success,
                'last_log_message': f'Completed: {success_count}/{len(orders)} orders successful' if success else f'Completed with {failed_count} failures',
                'last_log_type': 'success' if success else 'warning'
            }, 600)

        return {
            'success': success,
            'total_quantity': total_quantity,
            'total_lots': total_lots,
            'batches_completed': batches_completed,
            'total_batches': num_batches,
            'orders': orders,
            'summary': {
                'success_count': success_count,
                'failed_count': failed_count,
                'total_orders_placed': len(orders)
            }
        }

    except Exception as e:
        logger.exception(f"Error in batch position closing: {e}")
        return {
            'success': False,
            'error': str(e),
            'total_quantity': total_quantity,
            'batches_completed': batches_completed,
            'orders': orders
        }


def close_strangle_positions_in_batches(
    call_symbol: str,
    put_symbol: str,
    total_lots: int,
    batch_size: int = 20,
    delay_seconds: int = 20,
    product: str = 'NRML'
):
    """
    Close strangle positions (Call BUY + Put BUY) in batches with delays.

    Args:
        call_symbol (str): Call option trading symbol (e.g., 'NIFTY25NOV24500CE')
        put_symbol (str): Put option trading symbol (e.g., 'NIFTY25NOV24000PE')
        total_lots (int): Total number of lots to close
        batch_size (int): Maximum lots per order (default: 20, Neo API limit)
        delay_seconds (int): Delay between orders in seconds (default: 20)
        product (str): Product type - 'NRML', 'MIS' (default: 'NRML')

    Returns:
        dict: Batch execution results
    """
    logger.info(f"Starting batch strangle closing: {total_lots} lots in batches of {batch_size}")

    # Get single authenticated session for all orders
    try:
        client = _get_authenticated_client()
        logger.info("Single Neo API session established for all orders")
    except Exception as e:
        logger.error(f"Failed to establish Neo session: {e}")
        return {
            'success': False,
            'error': f'Authentication failed: {str(e)}',
            'call_orders': [],
            'put_orders': []
        }

    # Get lot size dynamically from Neo API
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

            logger.info(f"Batch {batch_num}/{num_batches}: Closing {current_batch_lots} lots ({current_batch_quantity} qty)")

            # Optimization: Place CALL and PUT exit orders in parallel using threads
            call_result = {}
            put_result = {}

            def place_call_exit_order():
                nonlocal call_result
                call_result = place_option_order(
                    trading_symbol=call_symbol,
                    transaction_type='B',  # BUY to close SELL
                    quantity=current_batch_quantity,
                    product=product,
                    order_type='MKT',
                    client=client  # Reuse session
                )

            def place_put_exit_order():
                nonlocal put_result
                put_result = place_option_order(
                    trading_symbol=put_symbol,
                    transaction_type='B',  # BUY to close SELL
                    quantity=current_batch_quantity,
                    product=product,
                    order_type='MKT',
                    client=client  # Reuse session
                )

            # Start both orders in parallel
            call_thread = threading.Thread(target=place_call_exit_order)
            put_thread = threading.Thread(target=place_put_exit_order)

            logger.info(f"Placing CALL and PUT exit orders in parallel...")
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
                logger.info(f"CALL EXIT batch {batch_num}: Order ID {call_result['order_id']}")
            else:
                logger.error(f"CALL EXIT batch {batch_num} failed: {call_result.get('error', 'Unknown error')}")

            if put_result.get('success'):
                logger.info(f"PUT EXIT batch {batch_num}: Order ID {put_result['order_id']}")
            else:
                logger.error(f"PUT EXIT batch {batch_num} failed: {put_result.get('error', 'Unknown error')}")

            batches_completed += 1

            # Delay before next batch (except for last batch)
            if batch_num < num_batches:
                logger.info(f"Waiting {delay_seconds} seconds before next batch...")
                time.sleep(delay_seconds)

        # Calculate summary
        call_success_count = sum(1 for order in call_orders if order['result']['success'])
        put_success_count = sum(1 for order in put_orders if order['result']['success'])
        call_failed_count = len(call_orders) - call_success_count
        put_failed_count = len(put_orders) - put_success_count

        success = (call_failed_count == 0 and put_failed_count == 0)

        logger.info(f"Batch strangle closing complete: {batches_completed}/{num_batches} batches processed")
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
        logger.exception(f"Error in batch strangle closing: {e}")
        return {
            'success': False,
            'error': str(e),
            'total_lots': total_lots,
            'batches_completed': batches_completed,
            'call_orders': call_orders,
            'put_orders': put_orders
        }
