"""
Order Management API Views

Endpoints for placing orders, checking order status,
and managing order execution for futures trading.
"""

import logging
import json
import time
from decimal import Decimal
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.db import transaction
from django.core.cache import cache

from apps.brokers.integrations.breeze import get_breeze_client, get_nfo_margin
from apps.brokers.utils.security_master import get_futures_instrument
from apps.positions.models import Position
from apps.brokers.models import Order
from apps.accounts.models import BrokerAccount
from apps.core.constants import POSITION_STATUS_ACTIVE
from apps.data.models import ContractData

logger = logging.getLogger(__name__)


@login_required
@require_POST
def place_futures_order(request):
    """
    Place futures order via ICICI Breeze API

    Creates Position and Order records, executes trade

    POST params (JSON or form):
        - stock_symbol: Stock symbol
        - direction: 'buy' or 'sell'
        - lots: Number of lots
        - price: Current futures price
        - stop_loss: Stop loss price
        - target: Target price
        - enable_averaging: Boolean (optional)
    """
    try:
        # Parse JSON body if present, otherwise use POST data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            logger.info(f"📥 place_futures_order received JSON data: {data}")
            symbol = data.get('symbol', data.get('stock_symbol', '')).upper()
            expiry_param = data.get('expiry')  # Get expiry from request
            direction = data.get('direction', 'buy').lower()
            lots = int(data.get('lots', 1))
            futures_price = float(data.get('entry_price', data.get('price', 0)))
            stop_loss = float(data.get('stop_loss', 0))
            target = float(data.get('target', 0))
            enable_averaging = data.get('enable_averaging', False)
        else:
            symbol = request.POST.get('stock_symbol', request.POST.get('symbol', '')).upper()
            expiry_param = request.POST.get('expiry')  # Get expiry from request
            direction = request.POST.get('direction', 'buy').lower()
            lots = int(request.POST.get('lots', 1))
            futures_price = float(request.POST.get('price', 0))
            stop_loss = float(request.POST.get('stop_loss', 0))
            target = float(request.POST.get('target', 0))
            enable_averaging = request.POST.get('enable_averaging', 'false').lower() == 'true'

        logger.info(f"🔍 Extracted params: symbol={symbol}, expiry_param={expiry_param}, direction={direction}, lots={lots}")

        # Normalize direction to LONG/SHORT
        if direction in ['buy', 'long']:
            direction = 'LONG'
        elif direction in ['sell', 'short']:
            direction = 'SHORT'

        # Get contract - use expiry from request if provided, otherwise use latest
        contract_filter = ContractData.objects.filter(
            symbol=symbol,
            option_type='FUTURE'
        )

        if expiry_param:
            # Use the specific expiry provided in the request
            # expiry_param could be in format '2024-12-26' (preferred) or '26-Dec-2024'
            try:
                # Try parsing as YYYY-MM-DD format first (database format)
                if '-' in expiry_param and expiry_param[0].isdigit() and len(expiry_param) == 10:
                    # Already in YYYY-MM-DD format
                    expiry_str = expiry_param
                    logger.info(f"✅ Using expiry from request (YYYY-MM-DD): {expiry_str}")
                elif '-' in expiry_param:
                    # DD-MMM-YYYY format (e.g., '26-Dec-2024')
                    expiry_dt = datetime.strptime(expiry_param, '%d-%b-%Y').date()
                    expiry_str = expiry_dt.strftime('%Y-%m-%d')
                    logger.info(f"✅ Using expiry from request (DD-MMM-YYYY): {expiry_param} -> {expiry_str}")
                else:
                    raise ValueError(f"Unknown expiry format: {expiry_param}")

                contract = contract_filter.filter(expiry=expiry_str).first()

                if not contract:
                    logger.error(f"❌ No contract found for {symbol} with expiry {expiry_str}")
                else:
                    logger.info(f"📋 Found contract: {symbol} expiry={contract.expiry} lot_size={contract.lot_size} price={contract.price}")
            except Exception as e:
                logger.warning(f"⚠️ Could not parse expiry '{expiry_param}': {e}, falling back to latest")
                contract = contract_filter.order_by('-expiry').first()
        else:
            # No expiry specified, use latest available
            contract = contract_filter.order_by('-expiry').first()
            logger.warning(f"⚠️ No expiry specified for {symbol}, using latest: {contract.expiry if contract else 'N/A'}")

        if not contract:
            return JsonResponse({
                'success': False,
                'error': f'Contract not found for {symbol}' + (f' with expiry {expiry_param}' if expiry_param else '')
            })

        # Use provided price or contract price
        entry_price_float = futures_price if futures_price > 0 else float(contract.price)
        entry_price = Decimal(str(entry_price_float))
        stop_loss_decimal = Decimal(str(stop_loss)) if stop_loss > 0 else Decimal('0.00')
        target_decimal = Decimal(str(target)) if target > 0 else Decimal('0.00')

        # Format expiry for Breeze
        expiry_dt = contract.expiry
        if isinstance(expiry_dt, str):
            expiry_dt = datetime.strptime(expiry_dt, '%Y-%m-%d').date()
        expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()

        # Get instrument details from SecurityMaster
        logger.info(f"Looking up {symbol} futures in SecurityMaster for expiry {expiry_breeze}")
        instrument = get_futures_instrument(symbol, expiry_breeze)

        # Always use contract.lot_size as the primary source (most reliable)
        lot_size = contract.lot_size

        if not instrument:
            logger.warning(f"Instrument not found in SecurityMaster, using contract data")
            # Fallback to contract data if SecurityMaster lookup fails
            stock_code = symbol
        else:
            # Use SecurityMaster data for stock_code (more accurate)
            stock_code = instrument['short_name']
            # Only override lot_size if SecurityMaster has a valid non-zero value
            if instrument.get('lot_size', 0) > 0:
                lot_size = instrument['lot_size']
            logger.info(f"SecurityMaster lookup successful: stock_code={stock_code}, lot_size={lot_size}, token={instrument['token']}")

        logger.info(f"Using lot_size={lot_size} from contract data (primary source)")

        quantity = lots * lot_size

        # Initialize Breeze
        breeze = get_breeze_client()

        # Validate margin availability using NFO margin API (includes pledged stocks)
        try:
            # Get NFO margin (includes pledged stocks and collateral)
            margin_data = get_nfo_margin()
            logger.info(f"NFO Margin response from Breeze: {margin_data}")

            if margin_data:
                # cash_limit is the total available margin including pledged stocks
                available_margin = float(margin_data.get('cash_limit', 0))
                # amount_allocated is the margin already used
                used_margin = float(margin_data.get('amount_allocated', 0))
                # Calculate actual available margin
                actual_available = available_margin - used_margin

                # Estimate margin needed (roughly 12% of contract value)
                margin_needed = entry_price_float * lot_size * lots * 0.12

                logger.info(f"Margin check: Need ₹{margin_needed:,.2f}, Available ₹{actual_available:,.2f} (Total: ₹{available_margin:,.2f}, Used: ₹{used_margin:,.2f})")

                if margin_needed > actual_available:
                    logger.warning(f"Insufficient margin detected: Need ₹{margin_needed:,.2f}, Available ₹{actual_available:,.2f}")
                    return JsonResponse({
                        'success': False,
                        'error': f'Insufficient margin. Need: ₹{margin_needed:,.0f}, Available: ₹{actual_available:,.0f}',
                        'debug_info': {
                            'margin_needed': margin_needed,
                            'available_margin': actual_available,
                            'total_cash_limit': available_margin,
                            'used_margin': used_margin,
                            'margin_response': margin_data
                        }
                    })
            else:
                logger.warning("Could not fetch NFO margin data, proceeding without validation")
        except Exception as e:
            logger.warning(f"Could not validate margin: {e}", exc_info=True)

        # Get broker account
        broker_account = BrokerAccount.objects.filter(broker='ICICI', is_active=True).first()
        if not broker_account:
            return JsonResponse({
                'success': False,
                'error': 'No active ICICI broker account found'
            })

        # Calculate batches (10 lots per order, 20 second delay between orders)
        BATCH_SIZE = 10  # lots per order
        DELAY_SECONDS = 20  # seconds between orders

        batches = []
        remaining_lots = lots
        while remaining_lots > 0:
            batch_lots = min(BATCH_SIZE, remaining_lots)
            batches.append(batch_lots)
            remaining_lots -= batch_lots

        total_batches = len(batches)
        logger.info(f"Splitting {lots} lots into {total_batches} batches: {batches}")

        # Track all orders
        successful_orders = []
        failed_orders = []
        position = None

        # Place orders in batches
        for batch_num, batch_lots in enumerate(batches, 1):
            batch_quantity = batch_lots * lot_size

            logger.info(f"{'='*80}")
            logger.info(f"Batch {batch_num}/{total_batches}: Placing order for {batch_lots} lots ({batch_quantity} quantity)")
            logger.info(f"{'='*80}")

            # Safety check: ensure batch_quantity is valid
            if batch_quantity <= 0:
                error_msg = f"Invalid batch quantity: {batch_quantity} (batch_lots={batch_lots}, lot_size={lot_size})"
                logger.error(f"❌ {error_msg}")
                failed_orders.append({
                    'batch': batch_num,
                    'lots': batch_lots,
                    'error': error_msg,
                    'response': None
                })
                continue

            try:
                # Create Position for this batch (or use existing for subsequent batches)
                with transaction.atomic():
                    if position is None:
                        # First batch - create main position
                        position = Position.objects.create(
                            account=broker_account,
                            strategy_type='LLM_VALIDATED_FUTURES',
                            instrument=symbol,
                            direction=direction,
                            quantity=lots,  # Total lots
                            lot_size=lot_size,
                            entry_price=entry_price,
                            current_price=entry_price,
                            stop_loss=stop_loss_decimal,
                            target=target_decimal,
                            expiry_date=expiry_dt,
                            margin_used=Decimal(str(entry_price_float * lot_size * lots * 0.12)),
                            entry_value=Decimal(str(entry_price_float * lot_size * lots)),
                            status=POSITION_STATUS_ACTIVE,
                            averaging_count=0,
                            original_entry_price=entry_price
                        )

                    # Place order via Breeze
                    action = 'buy' if direction == 'LONG' else 'sell'

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

                    logger.info(f"Batch {batch_num} order parameters: {order_params}")
                    if instrument:
                        logger.info(f"Using SecurityMaster: Symbol={symbol} -> StockCode={stock_code}, Token={instrument['token']}")

                    order_response = breeze.place_order(**order_params)
                    logger.info(f"Batch {batch_num} Breeze API Response: {order_response}")

                    if order_response and order_response.get('Status') == 200:
                        order_data = order_response.get('Success', {})
                        order_id = order_data.get('order_id', 'UNKNOWN')

                        # Create Order record
                        order = Order.objects.create(
                            account=broker_account,
                            position=position,
                            broker_order_id=order_id,
                            instrument=symbol,
                            order_type='MARKET',
                            direction=direction,
                            quantity=batch_quantity,
                            price=entry_price,
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

                        logger.info(f"✅ Batch {batch_num} SUCCESS: Order ID {order_id}")

                    else:
                        error_msg = order_response.get('Error', 'Unknown error') if order_response else 'API call failed'
                        logger.error(f"❌ Batch {batch_num} FAILED: {error_msg}")

                        failed_orders.append({
                            'batch': batch_num,
                            'lots': batch_lots,
                            'error': error_msg,
                            'response': order_response
                        })

            except Exception as e:
                logger.error(f"❌ Batch {batch_num} EXCEPTION: {e}", exc_info=True)
                failed_orders.append({
                    'batch': batch_num,
                    'lots': batch_lots,
                    'error': str(e),
                    'response': None
                })

            # Wait 20 seconds before next batch (except for last batch)
            if batch_num < total_batches:
                logger.info(f"⏸️  Waiting {DELAY_SECONDS} seconds before next batch...")
                time.sleep(DELAY_SECONDS)

        # Prepare summary response
        logger.info(f"{'='*80}")
        logger.info(f"ORDER PLACEMENT SUMMARY: {len(successful_orders)} successful, {len(failed_orders)} failed")
        logger.info(f"{'='*80}")

        if len(successful_orders) > 0:
            # At least some orders succeeded
            response_data = {
                'success': True,
                'total_batches': total_batches,
                'successful_batches': len(successful_orders),
                'failed_batches': len(failed_orders),
                'position_id': position.id if position else None,
                'message': f'{len(successful_orders)}/{total_batches} batches placed successfully',
                'orders': successful_orders,
                'failed_orders': failed_orders if failed_orders else None,
                'order_details': {
                    'symbol': symbol,
                    'stock_code': stock_code,
                    'direction': direction,
                    'total_lots': lots,
                    'lot_size': lot_size,
                    'total_quantity': quantity,
                    'entry_price': float(entry_price),
                    'expiry_date': expiry_breeze,
                    'batch_size': BATCH_SIZE,
                    'delay_seconds': DELAY_SECONDS
                }
            }

            # Add SecurityMaster info
            if instrument:
                response_data['security_master'] = {
                    'token': instrument['token'],
                    'stock_code': instrument['short_name'],
                    'lot_size': instrument['lot_size'],
                    'company_name': instrument['company_name'],
                    'source': instrument.get('source', 'security_master')
                }

            return JsonResponse(response_data)
        else:
            # All batches failed
            return JsonResponse({
                'success': False,
                'error': f'All {total_batches} batches failed',
                'failed_orders': failed_orders,
                'debug_info': {
                    'total_batches': total_batches,
                    'symbol': symbol,
                    'lots': lots
                }
            })

    except Exception as e:
        logger.error(f"Error placing order: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_GET
def check_order_status(request, order_id):
    """
    Check order status from Breeze API

    Polls order status and updates Order record

    URL params:
        - order_id: Broker order ID
    """
    try:
        # Get Order record
        order = Order.objects.filter(
            user=request.user,
            broker_order_id=order_id
        ).first()

        if not order:
            return JsonResponse({
                'success': False,
                'error': 'Order not found'
            })

        # Check status via Breeze
        breeze = get_breeze_client()

        status_response = breeze.get_order_detail(
            exchange_code='NFO',
            order_id=order_id
        )

        if status_response and status_response.get('Status') == 200:
            order_data = status_response.get('Success', {})

            status = order_data.get('status', 'UNKNOWN')
            filled_qty = int(order_data.get('filled_quantity', 0))
            avg_price = float(order_data.get('average_price', 0))

            # Update Order record
            with transaction.atomic():
                if status in ['COMPLETE', 'EXECUTED']:
                    order.status = 'COMPLETED'
                    order.filled_quantity = filled_qty
                    order.average_price = avg_price
                    order.save()

                    # Update Position
                    position = order.position
                    if position and order.order_type == 'ENTRY':
                        position.entry_price = avg_price
                        position.current_price = avg_price
                        position.save()

                elif status in ['CANCELLED', 'REJECTED']:
                    order.status = 'FAILED'
                    order.save()

                    # Close position
                    position = order.position
                    if position:
                        position.status = 'CANCELLED'
                        position.save()

            return JsonResponse({
                'success': True,
                'order_id': order_id,
                'status': status,
                'filled_quantity': filled_qty,
                'average_price': avg_price,
                'is_complete': status in ['COMPLETE', 'EXECUTED'],
                'is_failed': status in ['CANCELLED', 'REJECTED']
            })

        else:
            return JsonResponse({
                'success': False,
                'error': 'Could not fetch order status'
            })

    except Exception as e:
        logger.error(f"Error checking order status: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


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

        # Generate the same cancellation key used by close_live_position
        cancellation_key = f"cancel_order_{request.user.id}_{broker}_{symbol.replace('/', '_')}"

        # Set the cancellation flag
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
