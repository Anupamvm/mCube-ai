"""
Position Management API Views

Endpoints for managing trading positions - viewing active positions,
getting position details, closing positions, and position averaging analysis.
"""

import logging
import json
import time
import re
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.core.cache import cache

from apps.brokers.integrations.breeze import get_breeze_client
from apps.positions.models import Position
from apps.orders.models import Order
from apps.core.constants import POSITION_STATUS_ACTIVE
from apps.data.models import ContractData

logger = logging.getLogger(__name__)


@login_required
@require_GET
def get_active_positions(request):
    """
    Get LIVE active positions from broker API (Breeze or Neo)

    Fetches real-time open positions directly from the broker's API
    instead of reading from database. Shows only positions with non-zero quantity.

    GET params:
        - broker: 'breeze' or 'neo'

    Returns:
        JSON with live positions list including LTP and real-time P&L
    """
    try:
        broker = request.GET.get('broker', '').lower()

        if broker not in ['breeze', 'neo']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid broker. Must be "breeze" or "neo"'
            })

        positions_data = []

        if broker == 'breeze':
            positions_data = _fetch_breeze_positions()

        elif broker == 'neo':
            result = _fetch_neo_positions()
            if 'error' in result:
                return JsonResponse({
                    'success': False,
                    'error': result['error']
                })
            positions_data = result['positions']

        broker_name = 'ICICI Breeze' if broker == 'breeze' else 'Kotak Neo'

        return JsonResponse({
            'success': True,
            'broker': broker_name,
            'positions': positions_data,
            'count': len(positions_data)
        })

    except Exception as e:
        logger.error(f"Error fetching active positions: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


def _fetch_breeze_positions():
    """Fetch live positions from Breeze API"""
    positions_data = []
    breeze = get_breeze_client()
    pos_resp = breeze.get_portfolio_positions()

    if pos_resp and pos_resp.get('Status') == 200:
        raw_positions = pos_resp.get('Success', [])

        for p in raw_positions:
            quantity = int(p.get('quantity') or 0)

            # Skip positions with zero quantity (closed positions)
            if quantity == 0:
                continue

            avg_price = float(p.get('average_price') or 0)
            ltp = float(p.get('ltp') or p.get('price') or 0)

            # Calculate unrealized P&L
            if quantity > 0:  # LONG position
                unrealized_pnl = (ltp - avg_price) * quantity
                direction = 'LONG'
            else:  # SHORT position
                unrealized_pnl = (avg_price - ltp) * abs(quantity)
                direction = 'SHORT'

            # Realized P&L is typically 0 for carry-forward positions
            realized_pnl = 0.0

            symbol = p.get('stock_code', 'N/A')
            product = p.get('product_type', 'N/A')
            exchange = p.get('exchange_code', 'NFO')

            # Extract expiry date from Breeze response
            expiry_date = None
            expiry_dt_str = p.get('expiry_date', '')
            if expiry_dt_str:
                try:
                    for fmt in ['%d-%b-%Y', '%Y-%m-%d', '%d-%m-%Y']:
                        try:
                            expiry_dt = datetime.strptime(expiry_dt_str, fmt)
                            expiry_date = expiry_dt.strftime('%Y-%m-%d')
                            break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Could not parse Breeze expiry date '{expiry_dt_str}': {e}")

            positions_data.append({
                'symbol': symbol,
                'exchange': exchange,
                'product': product,
                'direction': direction,
                'quantity': abs(quantity),
                'net_quantity': quantity,
                'net_quantity_shares': quantity,
                'average_price': avg_price,
                'ltp': ltp,
                'unrealized_pnl': round(unrealized_pnl, 2),
                'realized_pnl': round(realized_pnl, 2),
                'total_pnl': round(unrealized_pnl + realized_pnl, 2),
                'pnl_percentage': round((unrealized_pnl / (avg_price * abs(quantity)) * 100), 2) if avg_price > 0 else 0,
                'expiry_date': expiry_date,
            })
    else:
        logger.warning(f"Breeze positions API returned non-200 status: {pos_resp}")

    return positions_data


def _fetch_neo_positions():
    """Fetch live positions from Neo API"""
    from apps.brokers.integrations.kotak_neo import get_kotak_neo_client, get_ltp_from_neo

    positions_data = []

    try:
        client = get_kotak_neo_client()

        logger.info("=" * 100)
        logger.info("CALLING NEO API: client.positions()")
        logger.info("=" * 100)

        resp = client.positions()

        logger.info("=" * 100)
        logger.info("RAW NEO API RESPONSE:")
        logger.info(f"Response type: {type(resp)}")
        logger.info(f"Response keys: {list(resp.keys()) if isinstance(resp, dict) else 'N/A'}")
        logger.info("=" * 100)

        raw_positions = resp.get('data', []) if isinstance(resp, dict) else []
        logger.info(f"Found {len(raw_positions)} positions in response")

        for p in raw_positions:
            symbol = p.get('trdSym', 'N/A')
            logger.info("=" * 80)
            logger.info(f"PROCESSING POSITION: {symbol}")
            logger.info("=" * 80)

            # Get lot size
            lot_sz = int(p.get('lotSz', 1))

            # QUANTITY CALCULATION - API returns quantities in SHARES
            cf_buy_qty_shares = int(p.get('cfBuyQty', 0))
            fl_buy_qty_shares = int(p.get('flBuyQty', 0))
            cf_sell_qty_shares = int(p.get('cfSellQty', 0))
            fl_sell_qty_shares = int(p.get('flSellQty', 0))

            total_buy_qty_shares = cf_buy_qty_shares + fl_buy_qty_shares
            total_sell_qty_shares = cf_sell_qty_shares + fl_sell_qty_shares
            net_qty_shares = total_buy_qty_shares - total_sell_qty_shares

            # Convert shares to LOTS for display
            total_buy_qty_lots = total_buy_qty_shares // lot_sz if lot_sz > 0 else total_buy_qty_shares
            total_sell_qty_lots = total_sell_qty_shares // lot_sz if lot_sz > 0 else total_sell_qty_shares
            net_qty_lots = total_buy_qty_lots - total_sell_qty_lots

            # Skip positions with zero quantity
            if net_qty_lots == 0:
                logger.info(f"Skipping {symbol} - zero net quantity")
                continue

            # AMOUNT FIELDS
            buy_amt = float(p.get('cfBuyAmt', 0)) + float(p.get('buyAmt', 0))
            sell_amt = float(p.get('cfSellAmt', 0)) + float(p.get('sellAmt', 0))

            # AVERAGE PRICE CALCULATION
            if net_qty_lots > 0:
                avg_price = buy_amt / total_buy_qty_shares if total_buy_qty_shares > 0 else 0
                direction = 'LONG'
            else:
                avg_price = sell_amt / total_sell_qty_shares if total_sell_qty_shares > 0 else 0
                direction = 'SHORT'

            # GET LTP
            ltp = None
            trading_symbol = p.get('trdSym')
            exchange_segment = p.get('exSeg', 'nse_fo')

            try:
                ltp = get_ltp_from_neo(
                    trading_symbol=trading_symbol,
                    exchange_segment=exchange_segment,
                    client=client
                )
            except Exception as e:
                logger.error(f"Error fetching LTP: {e}", exc_info=True)

            # P&L CALCULATION
            # REALIZED P&L
            if sell_amt == 0 and buy_amt > 0:
                realized_pnl = 0.0
            elif buy_amt == 0 and sell_amt > 0:
                realized_pnl = 0.0
            else:
                realized_pnl = sell_amt - buy_amt

            # UNREALIZED P&L
            if ltp is not None and ltp > 0:
                if direction == 'LONG':
                    unrealized_pnl = (ltp - avg_price) * net_qty_shares
                else:
                    unrealized_pnl = (avg_price - ltp) * abs(net_qty_shares)
            else:
                unrealized_pnl = 0.0

            # TOTAL P&L
            total_pnl = realized_pnl + unrealized_pnl

            # Get additional fields
            product = p.get('prod', 'N/A')
            exchange = p.get('exSeg', 'N/A')

            # Calculate P&L percentage
            investment = avg_price * abs(net_qty_shares)
            pnl_pct = (total_pnl / investment * 100) if investment > 0 else 0

            # Extract expiry date from Neo response
            expiry_date = None
            expiry_dt_str = p.get('expDt', '')
            if expiry_dt_str:
                try:
                    expiry_dt = datetime.strptime(expiry_dt_str, '%d %b, %Y')
                    expiry_date = expiry_dt.strftime('%Y-%m-%d')
                except Exception as e:
                    logger.warning(f"Could not parse expiry date '{expiry_dt_str}': {e}")

            positions_data.append({
                'symbol': symbol,
                'exchange': exchange,
                'product': product,
                'direction': direction,
                'quantity': abs(net_qty_lots),
                'net_quantity': net_qty_lots,
                'net_quantity_shares': net_qty_shares,
                'average_price': round(avg_price, 2),
                'ltp': round(ltp, 2) if ltp is not None and ltp > 0 else None,
                'unrealized_pnl': round(unrealized_pnl, 2),
                'realized_pnl': round(realized_pnl, 2),
                'total_pnl': round(total_pnl, 2),
                'pnl_percentage': round(pnl_pct, 2),
                'expiry_date': expiry_date,
            })

        return {'positions': positions_data}

    except Exception as e:
        logger.error(f"Error fetching Neo positions: {e}", exc_info=True)
        return {'error': f'Failed to fetch Neo positions: {str(e)}'}


@login_required
@require_GET
def get_position_details(request):
    """
    Get detailed information for a specific position

    GET params:
        - broker: 'breeze' or 'neo'
        - position_id: Position ID

    Returns:
        JSON with position details
    """
    try:
        broker = request.GET.get('broker', '').lower()
        position_id = request.GET.get('position_id')

        if not position_id:
            return JsonResponse({
                'success': False,
                'error': 'position_id is required'
            })

        broker_name = 'ICICI' if broker == 'breeze' else 'KOTAK'

        position = Position.objects.filter(
            id=position_id,
            account__broker=broker_name,
            account__is_active=True
        ).select_related('account').first()

        if not position:
            return JsonResponse({
                'success': False,
                'error': 'Position not found'
            })

        position_data = {
            'id': position.id,
            'instrument': position.instrument,
            'direction': position.direction,
            'quantity': position.quantity,
            'lot_size': position.lot_size,
            'entry_price': float(position.entry_price),
            'current_price': float(position.current_price),
            'stop_loss': float(position.stop_loss) if position.stop_loss else None,
            'target': float(position.target) if position.target else None,
            'unrealized_pnl': float(position.unrealized_pnl),
            'realized_pnl': float(position.realized_pnl),
            'margin_used': float(position.margin_used),
            'entry_value': float(position.entry_value),
            'expiry_date': position.expiry_date.strftime('%Y-%m-%d'),
            'entry_time': position.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
            'exit_time': position.exit_time.strftime('%Y-%m-%d %H:%M:%S') if position.exit_time else None,
            'exit_price': float(position.exit_price) if position.exit_price else None,
            'exit_reason': position.exit_reason,
            'status': position.status,
            'strategy_type': position.strategy_type,
            'call_strike': float(position.call_strike) if position.call_strike else None,
            'put_strike': float(position.put_strike) if position.put_strike else None,
            'call_premium': float(position.call_premium) if position.call_premium else None,
            'put_premium': float(position.put_premium) if position.put_premium else None,
        }

        return JsonResponse({
            'success': True,
            'position': position_data
        })

    except Exception as e:
        logger.error(f"Error fetching position details: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def close_position(request):
    """
    Close a position by placing exit orders in batches

    POST params (JSON):
        - broker: 'breeze' or 'neo'
        - position_id: Position ID

    Returns:
        JSON with order execution results
    """
    try:
        from apps.brokers.utils.security_master import get_futures_instrument
        from apps.accounts.models import BrokerAccount

        # Parse JSON body
        data = json.loads(request.body)
        broker = data.get('broker', '').lower()
        position_id = data.get('position_id')

        if not position_id:
            return JsonResponse({
                'success': False,
                'error': 'position_id is required'
            })

        broker_name = 'ICICI' if broker == 'breeze' else 'KOTAK'

        # Get position
        position = Position.objects.filter(
            id=position_id,
            account__broker=broker_name,
            account__is_active=True,
            status=POSITION_STATUS_ACTIVE
        ).select_related('account').first()

        if not position:
            return JsonResponse({
                'success': False,
                'error': 'Position not found or already closed'
            })

        # Get contract details
        contract = ContractData.objects.filter(
            symbol=position.instrument,
            option_type='FUTURE',
            expiry=position.expiry_date
        ).first()

        if not contract:
            return JsonResponse({
                'success': False,
                'error': f'Contract not found for {position.instrument}'
            })

        # Format expiry for Breeze
        expiry_dt = position.expiry_date
        if isinstance(expiry_dt, str):
            expiry_dt = datetime.strptime(expiry_dt, '%Y-%m-%d').date()
        expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()

        # Get instrument details from SecurityMaster
        logger.info(f"Looking up {position.instrument} futures in SecurityMaster for expiry {expiry_breeze}")
        instrument = get_futures_instrument(position.instrument, expiry_breeze)

        # Always use contract.lot_size as the primary source
        lot_size = contract.lot_size

        if not instrument:
            logger.warning(f"Instrument not found in SecurityMaster, using contract data")
            stock_code = position.instrument
        else:
            stock_code = instrument['short_name']
            if instrument.get('lot_size', 0) > 0:
                lot_size = instrument['lot_size']
            logger.info(f"SecurityMaster lookup successful: stock_code={stock_code}, lot_size={lot_size}")

        # Initialize Breeze
        breeze = get_breeze_client()

        # Calculate batches (10 lots per order, 20 second delay)
        BATCH_SIZE = 10
        DELAY_SECONDS = 20

        total_lots = position.quantity
        batches = []
        remaining_lots = total_lots

        while remaining_lots > 0:
            batch_lots = min(BATCH_SIZE, remaining_lots)
            batches.append(batch_lots)
            remaining_lots -= batch_lots

        total_batches = len(batches)
        logger.info(f"Closing position: Splitting {total_lots} lots into {total_batches} batches: {batches}")

        # Track all orders
        successful_orders = []
        failed_orders = []

        # Place exit orders in batches (opposite direction)
        for batch_num, batch_lots in enumerate(batches, 1):
            batch_quantity = batch_lots * lot_size

            logger.info(f"Exit Batch {batch_num}/{total_batches}: Closing {batch_lots} lots ({batch_quantity} quantity)")

            if batch_quantity <= 0:
                error_msg = f"Invalid batch quantity: {batch_quantity}"
                logger.error(error_msg)
                failed_orders.append({
                    'batch': batch_num,
                    'lots': batch_lots,
                    'error': error_msg,
                    'response': None
                })
                continue

            try:
                # Determine action (opposite of position direction)
                action = 'sell' if position.direction == 'LONG' else 'buy'

                order_params = {
                    'stock_code': stock_code,
                    'exchange_code': 'NFO',
                    'product': 'futures',
                    'action': action,
                    'order_type': 'market',
                    'quantity': str(batch_quantity),
                    'price': '0',
                    'validity': 'day',
                    'stoploss': '0',
                    'disclosed_quantity': '0',
                    'expiry_date': expiry_breeze,
                    'right': 'others',
                    'strike_price': '0'
                }

                logger.info(f"Exit Batch {batch_num} order parameters: {order_params}")

                order_response = breeze.place_order(**order_params)
                logger.info(f"Exit Batch {batch_num} Breeze API Response: {order_response}")

                if order_response and order_response.get('Status') == 200:
                    order_data = order_response.get('Success', {})
                    order_id = order_data.get('order_id', 'UNKNOWN')

                    # Create Order record
                    order = Order.objects.create(
                        account=position.account,
                        position=position,
                        broker_order_id=order_id,
                        instrument=position.instrument,
                        order_type='MARKET',
                        direction='SELL' if position.direction == 'LONG' else 'BUY',
                        quantity=batch_quantity,
                        price=position.current_price,
                        exchange='NFO',
                        status='PENDING'
                    )

                    successful_orders.append({
                        'batch': batch_num,
                        'order_id': order_id,
                        'lots': batch_lots,
                        'quantity': batch_quantity,
                        'order_record_id': order.id
                    })

                    logger.info(f"Exit Batch {batch_num} SUCCESS: Order ID {order_id}")

                else:
                    error_msg = order_response.get('Error', 'Unknown error') if order_response else 'API call failed'
                    logger.error(f"Exit Batch {batch_num} FAILED: {error_msg}")

                    failed_orders.append({
                        'batch': batch_num,
                        'lots': batch_lots,
                        'error': error_msg,
                        'response': order_response
                    })

            except Exception as e:
                logger.error(f"Exit Batch {batch_num} EXCEPTION: {e}", exc_info=True)
                failed_orders.append({
                    'batch': batch_num,
                    'lots': batch_lots,
                    'error': str(e),
                    'response': None
                })

            # Wait before next batch (except for last batch)
            if batch_num < total_batches:
                logger.info(f"Waiting {DELAY_SECONDS} seconds before next batch...")
                time.sleep(DELAY_SECONDS)

        # Update position status if all orders succeeded
        if len(successful_orders) == total_batches:
            position.close_position(
                exit_price=position.current_price,
                exit_reason='MANUAL'
            )
            logger.info(f"Position {position.id} marked as CLOSED")

        if len(successful_orders) > 0:
            return JsonResponse({
                'success': True,
                'total_batches': total_batches,
                'successful_batches': len(successful_orders),
                'failed_batches': len(failed_orders),
                'position_id': position.id,
                'message': f'{len(successful_orders)}/{total_batches} exit batches placed successfully',
                'orders': successful_orders,
                'failed_orders': failed_orders if failed_orders else None,
                'position_closed': len(successful_orders) == total_batches
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'All {total_batches} exit batches failed',
                'failed_orders': failed_orders,
                'debug_info': {
                    'total_batches': total_batches,
                    'symbol': position.instrument,
                    'lots': total_lots
                }
            })

    except Exception as e:
        logger.error(f"Error closing position: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@csrf_exempt
def close_live_position(request):
    """
    Close a live position from broker API by placing exit orders in batches.

    This is different from close_position() which works with database Position objects.
    This function works with live positions fetched directly from broker APIs.

    POST params (JSON):
        - broker: 'breeze' or 'neo'
        - symbol: Trading symbol (e.g., 'JIOFIN25DECFUT', 'NIFTY25NOV24500CE')
        - quantity: Net quantity to close (positive for LONG, negative for SHORT)
        - exchange: Exchange code (e.g., 'NFO', 'nse_fo')
        - product: Product type (e.g., 'futures', 'NRML', 'MIS')
        - direction: Position direction ('LONG' or 'SHORT')

    Returns:
        JSON with order execution results
    """
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)

    # Check if POST method
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'POST method required'
        }, status=405)

    try:
        # Parse JSON body
        data = json.loads(request.body)
        broker = data.get('broker', '').lower()
        symbol = data.get('symbol')
        quantity = data.get('quantity')
        exchange = data.get('exchange', 'NFO')
        product = data.get('product', 'NRML')
        direction = data.get('direction', 'LONG').upper()

        logger.info(f"=" * 100)
        logger.info(f"CLOSING LIVE POSITION: {broker.upper()} - {symbol}")
        logger.info(f"Direction: {direction}, Quantity: {quantity}, Product: {product}")
        logger.info(f"=" * 100)

        if broker not in ['breeze', 'neo']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid broker. Must be "breeze" or "neo"'
            })

        if not symbol or quantity is None:
            return JsonResponse({
                'success': False,
                'error': 'symbol and quantity are required'
            })

        abs_quantity = abs(int(quantity))

        if abs_quantity == 0:
            return JsonResponse({
                'success': False,
                'error': 'Position has zero quantity'
            })

        # Generate cancellation key
        cancellation_key = f"cancel_order_{request.user.id}_{broker}_{symbol.replace('/', '_')}"
        cache.set(cancellation_key, False, 600)

        # Generate progress tracking key
        progress_key = f"close_progress_{request.user.id}_{broker}_{symbol.replace('/', '_')}"

        def update_progress(batches_completed, total_batches, current_batch=None, log_message=None, log_type='info', is_complete=False, is_success=False, is_cancelled=False):
            progress = {
                'batches_completed': batches_completed,
                'total_batches': total_batches,
                'current_batch': current_batch,
                'is_cancelled': is_cancelled,
                'is_complete': is_complete,
                'is_success': is_success,
                'last_log_message': log_message,
                'last_log_type': log_type
            }
            cache.set(progress_key, progress, 600)
            return progress

        if broker == 'neo':
            return _close_neo_position(symbol, abs_quantity, direction, product, cancellation_key, progress_key, update_progress)
        elif broker == 'breeze':
            return _close_breeze_position(request, symbol, abs_quantity, direction, product, cancellation_key, progress_key, update_progress)

        return JsonResponse({
            'success': False,
            'error': 'Unknown error - broker not supported or invalid parameters'
        })

    except Exception as e:
        logger.error(f"Error closing live position: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


def _close_neo_position(symbol, abs_quantity, direction, product, cancellation_key, progress_key, update_progress):
    """Close position on Neo broker"""
    from apps.brokers.integrations.kotak_neo import close_position_in_batches

    transaction_type = 'S' if direction == 'LONG' else 'B'
    logger.info(f"Closing Neo position: {symbol} with transaction type {transaction_type}")

    update_progress(0, 0, log_message='Starting position closure on Kotak Neo...', log_type='info')

    result = close_position_in_batches(
        trading_symbol=symbol,
        total_quantity=abs_quantity,
        transaction_type=transaction_type,
        product=product if product in ['NRML', 'MIS', 'CNC'] else 'NRML',
        batch_size=10,
        delay_seconds=10,
        position_type='OPTION',
        cancellation_key=cancellation_key,
        progress_key=progress_key
    )

    if result['success']:
        logger.info(f"Neo position closed successfully: {result['summary']}")
        return JsonResponse({
            'success': True,
            'cancelled': result.get('cancelled', False),
            'broker': 'neo',
            'symbol': symbol,
            'message': result.get('message', f"Position closed: {result['summary']['success_count']}/{result['total_batches']} batches succeeded"),
            'batches_completed': result['batches_completed'],
            'total_batches': result['total_batches'],
            'successful_batches': result['summary']['success_count'],
            'summary': result['summary']
        })
    else:
        logger.error(f"Neo position close failed: {result.get('error')}")
        return JsonResponse({
            'success': False,
            'error': result.get('error', 'Failed to close position'),
            'batches_completed': result.get('batches_completed', 0),
            'orders': result.get('orders', [])
        })


def _close_breeze_position(request, symbol, abs_quantity, direction, product, cancellation_key, progress_key, update_progress):
    """Close position on Breeze broker"""
    action = 'sell' if direction == 'LONG' else 'buy'
    logger.info(f"Closing Breeze position: {symbol} with action {action}")

    breeze = get_breeze_client()

    # Get the actual position from Breeze
    try:
        pos_resp = breeze.get_portfolio_positions()
        if not pos_resp or pos_resp.get('Status') != 200:
            return JsonResponse({
                'success': False,
                'error': f'Failed to fetch positions from Breeze: {pos_resp.get("Error", "Unknown error")}'
            })

        positions = pos_resp.get('Success', [])
        matching_pos = None

        for pos in positions:
            pos_qty = int(pos.get('quantity', 0))
            if abs(pos_qty) == abs_quantity:
                if product.lower() in pos.get('product_type', '').lower():
                    matching_pos = pos
                    break

        if not matching_pos:
            match = re.match(r'^([A-Z]+)', symbol.upper())
            base_symbol = match.group(1) if match else symbol

            for pos in positions:
                if pos.get('stock_code') == base_symbol:
                    matching_pos = pos
                    break

        if not matching_pos:
            return JsonResponse({
                'success': False,
                'error': f'Could not find position for {symbol} in Breeze positions'
            })

        stock_code = matching_pos.get('stock_code')
        exchange_code = matching_pos.get('exchange_code', 'NFO')
        product_type = matching_pos.get('product_type', 'Futures')
        expiry_date = matching_pos.get('expiry_date', '')
        right = matching_pos.get('right', 'others')
        strike_price = matching_pos.get('strike_price', '0')

    except Exception as e:
        logger.error(f"Error fetching Breeze positions: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Failed to get position details: {str(e)}'
        })

    # Calculate batches
    STANDARD_LOT_SIZES = {
        'NIFTY': 25,
        'BANKNIFTY': 15,
        'FINNIFTY': 25,
        'MIDCPNIFTY': 50,
        'JIOFIN': 2350,
        'RELIANCE': 250,
        'TCS': 150,
        'INFY': 300,
    }
    lot_size = STANDARD_LOT_SIZES.get(stock_code, 1)

    BATCH_SIZE_LOTS = 10
    DELAY_SECONDS = 40

    batch_size_shares = BATCH_SIZE_LOTS * lot_size
    total_lots = abs_quantity // lot_size if lot_size > 0 else 0

    if total_lots == 0:
        return JsonResponse({
            'success': False,
            'error': f'Quantity {abs_quantity} is less than one lot (lot size: {lot_size})'
        })

    batches = []
    remaining_shares = abs_quantity

    while remaining_shares > 0:
        batch_shares = min(batch_size_shares, remaining_shares)
        batches.append(batch_shares)
        remaining_shares -= batch_shares

    total_batches = len(batches)
    update_progress(0, total_batches, log_message=f'Starting position closure on ICICI Breeze: {total_batches} batches', log_type='info')

    successful_orders = []
    failed_orders = []

    for batch_num, batch_shares in enumerate(batches, 1):
        # Check for cancellation
        if cache.get(cancellation_key):
            update_progress(
                len(successful_orders), total_batches,
                is_complete=True, is_success=False, is_cancelled=True,
                log_message=f'Cancelled at batch {batch_num}/{total_batches}.',
                log_type='warning'
            )
            return JsonResponse({
                'success': True,
                'cancelled': True,
                'broker': 'breeze',
                'symbol': symbol,
                'message': f'Order placement stopped by user. Completed {len(successful_orders)}/{total_batches} batches.',
                'successful_batches': len(successful_orders),
                'failed_batches': len(failed_orders),
                'total_batches': total_batches,
                'orders': successful_orders,
                'failed_orders': failed_orders if failed_orders else None
            })

        batch_lots = batch_shares // lot_size

        update_progress(
            len(successful_orders), total_batches,
            current_batch={'batch_num': batch_num, 'lots': batch_lots, 'quantity': batch_shares},
            log_message=f'Processing batch {batch_num}/{total_batches}: {batch_lots} lots',
            log_type='info'
        )

        try:
            order_params = {
                'stock_code': stock_code,
                'exchange_code': exchange_code,
                'product': product_type.lower(),
                'action': action,
                'order_type': 'market',
                'quantity': str(batch_shares),
                'price': '0',
                'validity': 'day',
                'stoploss': '0',
                'disclosed_quantity': '0',
                'expiry_date': expiry_date,
                'right': right,
                'strike_price': str(strike_price)
            }

            order_response = breeze.place_order(**order_params)

            if order_response and order_response.get('Status') == 200:
                order_data = order_response.get('Success', {})
                order_id = order_data.get('order_id', 'UNKNOWN')

                successful_orders.append({
                    'batch': batch_num,
                    'order_id': order_id,
                    'lots': batch_lots,
                    'quantity': batch_shares
                })

                update_progress(
                    len(successful_orders), total_batches,
                    log_message=f'Batch {batch_num}/{total_batches} completed successfully',
                    log_type='success'
                )
            else:
                error_msg = order_response.get('Error', 'Unknown error') if order_response else 'API call failed'

                failed_orders.append({
                    'batch': batch_num,
                    'lots': batch_lots,
                    'error': error_msg
                })

                update_progress(
                    len(successful_orders), total_batches,
                    is_complete=True, is_success=False,
                    log_message=f'Batch {batch_num}/{total_batches} failed. Stopping execution.',
                    log_type='error'
                )

                return JsonResponse({
                    'success': False,
                    'broker': 'breeze',
                    'symbol': symbol,
                    'error': f'Batch {batch_num} failed: {error_msg}',
                    'successful_batches': len(successful_orders),
                    'failed_batches': len(failed_orders),
                    'total_batches': total_batches,
                    'orders': successful_orders,
                    'failed_orders': failed_orders
                })

        except Exception as e:
            failed_orders.append({
                'batch': batch_num,
                'lots': batch_lots,
                'error': str(e)
            })

            update_progress(
                len(successful_orders), total_batches,
                is_complete=True, is_success=False,
                log_message=f'Batch {batch_num}/{total_batches} error: {str(e)[:50]}. Stopping execution.',
                log_type='error'
            )

            return JsonResponse({
                'success': False,
                'broker': 'breeze',
                'symbol': symbol,
                'error': f'Batch {batch_num} exception: {str(e)}',
                'successful_batches': len(successful_orders),
                'failed_batches': len(failed_orders),
                'total_batches': total_batches,
                'orders': successful_orders,
                'failed_orders': failed_orders
            })

        # Wait before next batch
        if batch_num < total_batches:
            time.sleep(DELAY_SECONDS)

            if cache.get(cancellation_key):
                update_progress(
                    len(successful_orders), total_batches,
                    is_complete=True, is_success=False, is_cancelled=True,
                    log_message=f'Cancelled during wait after batch {batch_num}/{total_batches}.',
                    log_type='warning'
                )
                return JsonResponse({
                    'success': True,
                    'cancelled': True,
                    'broker': 'breeze',
                    'symbol': symbol,
                    'message': f'Order placement stopped by user. Completed {len(successful_orders)}/{total_batches} batches.',
                    'successful_batches': len(successful_orders),
                    'failed_batches': len(failed_orders),
                    'total_batches': total_batches,
                    'orders': successful_orders,
                    'failed_orders': failed_orders if failed_orders else None
                })

    # Final progress update
    if len(successful_orders) > 0:
        update_progress(
            len(successful_orders), total_batches,
            is_complete=True,
            is_success=len(failed_orders) == 0,
            log_message=f'Completed: {len(successful_orders)}/{total_batches} batches successful',
            log_type='success' if len(failed_orders) == 0 else 'warning'
        )

        return JsonResponse({
            'success': True,
            'broker': 'breeze',
            'symbol': symbol,
            'message': f'{len(successful_orders)}/{total_batches} exit batches placed successfully',
            'successful_batches': len(successful_orders),
            'failed_batches': len(failed_orders),
            'total_batches': total_batches,
            'orders': successful_orders,
            'failed_orders': failed_orders if failed_orders else None
        })
    else:
        update_progress(
            0, total_batches,
            is_complete=True, is_success=False,
            log_message=f'All {total_batches} batches failed',
            log_type='error'
        )
        return JsonResponse({
            'success': False,
            'error': f'All {total_batches} exit batches failed',
            'failed_orders': failed_orders
        })


@csrf_exempt
def get_close_position_progress(request, broker, symbol):
    """
    Get progress of an ongoing close position operation.

    URL params:
        - broker: 'breeze' or 'neo'
        - symbol: Trading symbol

    Returns:
        JSON with progress information
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)

    try:
        progress_key = f"close_progress_{request.user.id}_{broker}_{symbol.replace('/', '_')}"

        progress = cache.get(progress_key, {
            'batches_completed': 0,
            'total_batches': 0,
            'current_batch': None,
            'is_cancelled': False,
            'is_complete': False,
            'is_success': False,
            'last_log_message': None,
            'last_log_type': None
        })

        return JsonResponse({
            'success': True,
            'progress': progress
        })

    except Exception as e:
        logger.error(f"Error getting close position progress: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@csrf_exempt
def cancel_order_placement(request):
    """
    Cancel an ongoing batch order placement.

    POST params (JSON):
        - broker: 'breeze' or 'neo'
        - symbol: Trading symbol

    Returns:
        JSON with cancellation status
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'POST method required'
        }, status=405)

    try:
        data = json.loads(request.body)
        broker = data.get('broker', '').lower()
        symbol = data.get('symbol')

        if not broker or not symbol:
            return JsonResponse({
                'success': False,
                'error': 'broker and symbol are required'
            })

        cancellation_key = f"cancel_order_{request.user.id}_{broker}_{symbol.replace('/', '_')}"
        cache.set(cancellation_key, True, 600)
        logger.info(f"Cancellation requested for key: {cancellation_key}")

        return JsonResponse({
            'success': True,
            'message': 'Cancellation requested. Remaining batches will be skipped.'
        })

    except Exception as e:
        logger.error(f"Error cancelling order placement: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@require_http_methods(["POST"])
def analyze_position_averaging(request):
    """
    Analyze an existing futures position for averaging opportunities.

    CRITICAL CONDITIONS (must pass):
    1. Price movement: Down 1.5%+ from entry (LONG) or Up 1.5%+ (SHORT)
    2. Support/Resistance: Near support (LONG) or resistance (SHORT)

    ADDITIONAL CHECKS:
    3. Trend analysis (not in strong opposite trend)
    4. Volume & liquidity
    5. Sector health
    6. Volatility assessment

    POST params (JSON):
        - broker: 'breeze' or 'neo'
        - symbol: Trading symbol (e.g., 'RELIANCE-I')
        - direction: Position direction ('LONG' or 'SHORT')
        - entry_price: Original entry price
        - quantity: Current position quantity
        - expiry_date: Futures expiry (YYYY-MM-DD format)

    Returns:
        JSON with averaging recommendation and analysis
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)

    try:
        from apps.trading.averaging_analyzer import AveragingAnalyzer
        from apps.brokers.integrations.kotak_neo import get_kotak_neo_client

        data = json.loads(request.body)
        broker = data.get('broker', '').lower()
        symbol = data.get('symbol', '')
        direction = data.get('direction', 'LONG').upper()
        entry_price = float(data.get('entry_price', 0))
        quantity = int(data.get('quantity', 0))
        expiry_date = data.get('expiry_date', '')

        if not all([broker, symbol, entry_price, quantity]):
            return JsonResponse({
                'success': False,
                'error': 'broker, symbol, entry_price, and quantity are required'
            })

        logger.info(f"Analyzing averaging for {symbol} {direction} @ {entry_price} ({quantity} qty)")

        # Extract base symbol
        if '-' in symbol:
            base_symbol = symbol.split('-')[0]
        else:
            match = re.match(r'^([A-Z]+)', symbol.upper())
            base_symbol = match.group(1) if match else symbol

        logger.info(f"Extracted base symbol: '{base_symbol}' from '{symbol}'")

        # Get lot size from ContractData
        lot_size = 0
        if expiry_date:
            contract = ContractData.objects.filter(
                symbol=base_symbol,
                option_type='FUTURE',
                expiry=expiry_date
            ).first()

            if contract:
                lot_size = contract.lot_size

        # Fallback lot sizes
        if not lot_size:
            fallback_lot_sizes = {
                'RELIANCE': 250, 'TCS': 150, 'INFY': 300, 'HDFCBANK': 550,
                'ICICIBANK': 1375, 'SBIN': 1500, 'NIFTY': 50, 'BANKNIFTY': 15,
            }
            lot_size = fallback_lot_sizes.get(base_symbol, 500)

        # Initialize analyzer with Breeze client
        breeze = get_breeze_client()
        analyzer = AveragingAnalyzer(breeze_client=breeze)

        # Run averaging analysis
        analysis_result = analyzer.analyze_position_for_averaging(
            symbol=base_symbol,
            direction=direction,
            entry_price=entry_price,
            current_quantity=quantity,
            lot_size=lot_size,
            expiry_date=expiry_date,
            exchange='NFO'
        )

        if not analysis_result.get('success'):
            return JsonResponse({
                'success': False,
                'error': analysis_result.get('error', 'Analysis failed'),
                'execution_log': analysis_result.get('execution_log', [])
            })

        # Add margin information
        position_sizing = analysis_result.get('position_sizing', {})
        recommended_lots = position_sizing.get('recommended_lots', 0)

        if recommended_lots > 0 and broker == 'breeze':
            from apps.trading.position_sizer import PositionSizer

            sizer = PositionSizer(breeze_client=breeze)

            if expiry_date:
                expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
                expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()
            else:
                expiry_breeze = None

            margin_response = sizer.fetch_margin_requirement(
                stock_code=base_symbol,
                expiry=expiry_breeze,
                quantity=lot_size * recommended_lots,
                direction=direction,
                futures_price=analysis_result.get('current_price', 0)
            )

            if margin_response.get('success'):
                try:
                    margin_data = breeze.get_margin(exchange_code="NFO")
                    if margin_data and margin_data.get('Status') == 200:
                        margin_info = margin_data.get('Success', {})
                        available_margin = float(margin_info.get('cash_limit', 0)) - float(margin_info.get('block_by_trade', 0))
                    else:
                        available_margin = 5000000
                except:
                    available_margin = 5000000

                position_sizing['margin_per_lot'] = margin_response.get('margin_per_lot', 0)
                position_sizing['total_margin_required'] = margin_response.get('total_margin', 0)
                position_sizing['available_margin'] = available_margin
                position_sizing['margin_utilization_pct'] = (
                    margin_response.get('total_margin', 0) / available_margin * 100
                ) if available_margin > 0 else 0

        response_data = {
            'success': True,
            'symbol': base_symbol,
            'direction': direction,
            'entry_price': entry_price,
            'current_price': analysis_result.get('current_price', 0),
            'price_change_pct': analysis_result.get('price_change_pct', 0),
            'recommendation': analysis_result.get('recommendation', 'NO_AVERAGE'),
            'confidence': analysis_result.get('confidence', 0),
            'reason': analysis_result.get('reason', ''),
            'critical_checks': analysis_result.get('critical_checks', {}),
            'additional_checks': analysis_result.get('additional_checks', {}),
            'risk_assessment': analysis_result.get('risk_assessment', {}),
            'position_sizing': position_sizing,
            'execution_log': analysis_result.get('execution_log', []),
            'lot_size': lot_size,
            'expiry_date': expiry_date
        }

        logger.info(f"Averaging analysis complete: {response_data['recommendation']} (Confidence: {response_data['confidence']}%)")

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in averaging analysis: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
