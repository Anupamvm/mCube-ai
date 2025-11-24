"""
Trading API Views - Position Sizing and Order Management

AJAX endpoints for real-time position sizing, P&L calculations,
and order placement via ICICI Breeze API.
"""

import logging
from decimal import Decimal
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.db import transaction

from apps.brokers.integrations.breeze import get_breeze_client, get_nfo_margin
from apps.positions.models import Position
from apps.orders.models import Order
from apps.accounts.models import BrokerAccount
from apps.core.constants import POSITION_STATUS_ACTIVE
# from apps.positions.services.averaging_manager import AveragingManager  # TODO: Fix - class doesn't exist
from apps.data.models import ContractData

logger = logging.getLogger(__name__)


@login_required
@require_POST
def calculate_position_sizing(request):
    """
    Calculate position sizing with real-time margin from Breeze API

    Step 1: Fetch margin requirement for 1 lot
    Step 2: Fetch available F&O margin
    Step 3: Apply 50% safety rule
    Step 4: Calculate suggested lots
    Step 5: Generate averaging strategy using AveragingManager

    POST params:
        - symbol: Stock symbol (e.g., 'RELIANCE')
        - expiry: Expiry date YYYY-MM-DD
        - direction: 'LONG' or 'SHORT'
        - custom_lots: User's custom lot size (optional)
    """
    try:
        import json

        # Parse JSON body if present, otherwise use POST data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            symbol = data.get('symbol', '').upper()
            expiry_str = data.get('expiry', '')
            direction = data.get('direction', 'LONG').upper()
            custom_lots = data.get('custom_lots')
        else:
            # Get parameters from POST form data
            symbol = request.POST.get('symbol', '').upper()
            expiry_str = request.POST.get('expiry', '')
            direction = request.POST.get('direction', 'LONG').upper()
            custom_lots = request.POST.get('custom_lots')

        if not symbol or not expiry_str:
            return JsonResponse({
                'success': False,
                'error': 'Symbol and expiry are required'
            })

        # Get contract details
        contract = ContractData.objects.filter(
            symbol=symbol,
            option_type='FUTURE',
            expiry=expiry_str
        ).first()

        if not contract:
            return JsonResponse({
                'success': False,
                'error': f'Contract not found for {symbol} {expiry_str}'
            })

        lot_size = contract.lot_size
        futures_price = float(contract.price)

        # Format expiry for Breeze API
        expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d')
        expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()

        # Initialize Breeze client
        breeze = get_breeze_client()

        # STEP 1: Fetch margin for 1 lot
        logger.info(f"Fetching margin for {symbol} 1 lot")

        quantity = lot_size  # 1 lot
        action = 'buy' if direction == 'LONG' else 'sell'

        try:
            margin_response = breeze.get_margin(
                exchange_code='NFO',
                product_type='futures',
                stock_code=symbol,
                quantity=str(quantity),
                price='0',  # Market price
                action=action,
                expiry_date=expiry_breeze,
                right='others',
                strike_price='0'
            )

            if margin_response and margin_response.get('Status') == 200:
                margin_data = margin_response.get('Success', {})
                total_margin = float(margin_data.get('total', 0))
                span_margin = float(margin_data.get('span', 0))
                exposure_margin = float(margin_data.get('exposure', 0))
                margin_per_lot = total_margin
                margin_source = 'Breeze API'
            else:
                # Fallback: Estimate 12% of position value
                margin_per_lot = futures_price * lot_size * 0.12
                span_margin = margin_per_lot * 0.7
                exposure_margin = margin_per_lot * 0.3
                total_margin = margin_per_lot
                margin_source = 'Estimated (12%)'
                logger.warning(f"Margin API failed, using estimate: ₹{margin_per_lot:,.0f}")

        except Exception as e:
            logger.error(f"Error fetching margin: {e}")
            margin_per_lot = futures_price * lot_size * 0.12
            span_margin = margin_per_lot * 0.7
            exposure_margin = margin_per_lot * 0.3
            total_margin = margin_per_lot
            margin_source = 'Estimated (Error)'

        # STEP 2: Fetch available F&O margin
        try:
            funds_response = breeze.get_funds()

            if funds_response and funds_response.get('Status') == 200:
                funds_data = funds_response.get('Success', {})
                available_margin = float(funds_data.get('availablemargin', 0))
                used_margin = float(funds_data.get('usedmargin', 0))
                total_account_margin = float(funds_data.get('totalmargin', 0))
            else:
                # Get from BrokerAccount
                broker_account = BrokerAccount.objects.filter(
                    user=request.user,
                    broker_name='ICICI'
                ).first()

                if broker_account:
                    available_margin = broker_account.get_available_capital()
                else:
                    available_margin = 500000  # Default

                used_margin = 0
                total_account_margin = available_margin

        except Exception as e:
            logger.error(f"Error fetching funds: {e}")
            broker_account = BrokerAccount.objects.filter(
                user=request.user,
                broker_name='ICICI'
            ).first()

            available_margin = broker_account.get_available_capital() if broker_account else 500000
            used_margin = 0
            total_account_margin = available_margin

        # STEP 3: Apply 50% safety rule
        usable_margin = available_margin * 0.5

        # STEP 4: Calculate suggested lots (using usable_margin for both to enforce 50% rule)
        max_affordable_lots = int(usable_margin / margin_per_lot) if margin_per_lot > 0 else 0
        suggested_lots = int(usable_margin / margin_per_lot) if margin_per_lot > 0 else 0
        suggested_lots = max(1, min(suggested_lots, 10))  # Min 1, Max 10

        # Use custom lots if provided, otherwise use suggested
        if custom_lots:
            try:
                lots = int(custom_lots)
                lots = max(1, min(lots, max_affordable_lots))
            except ValueError:
                lots = suggested_lots
        else:
            lots = suggested_lots

        # Calculate margin for selected lots
        margin_required = margin_per_lot * lots
        margin_used_pct = (margin_required / available_margin * 100) if available_margin > 0 else 0
        remaining_margin = available_margin - margin_required

        # STEP 5: Generate averaging strategy using AveragingManager logic
        averaging_levels = []

        try:
            # Track cumulative position as we build averaging levels
            current_average = futures_price
            cumulative_lots = lots
            cumulative_cost = futures_price * lots * lot_size

            # Generate 3 averaging levels (1% loss from CURRENT average, not original price)
            for level_num in range(1, 4):
                # Trigger when current position is -1% from current average price
                if direction == 'LONG':
                    trigger_price = current_average * 0.99  # 1% below current average
                else:
                    trigger_price = current_average * 1.01  # 1% above current average

                # Add same lots at each level (AveragingManager logic: equal quantity adds)
                lots_to_add = lots
                cumulative_lots += lots_to_add

                # Update cumulative cost with new addition
                cumulative_cost += trigger_price * lots_to_add * lot_size

                # Calculate NEW average price after this averaging level
                average_price = cumulative_cost / (cumulative_lots * lot_size)

                # Update current_average for next iteration
                current_average = average_price

                # Calculate targets from NEW average (2%, 4%, 6%)
                if direction == 'LONG':
                    target_1 = average_price * 1.02
                    target_2 = average_price * 1.04
                    target_3 = average_price * 1.06
                    stop_loss = average_price * 0.995  # Tightened to 0.5% after averaging
                else:
                    target_1 = average_price * 0.98
                    target_2 = average_price * 0.96
                    target_3 = average_price * 0.94
                    stop_loss = average_price * 1.005  # Tightened to 0.5% after averaging

                averaging_levels.append({
                    'level': level_num,
                    'trigger_price': round(trigger_price, 2),
                    'trigger_loss_pct': 1.0,  # Always 1% from current position
                    'lots_to_add': lots_to_add,
                    'quantity_to_add': lots_to_add * lot_size,
                    'cumulative_lots': cumulative_lots,
                    'cumulative_quantity': cumulative_lots * lot_size,
                    'average_price': round(average_price, 2),
                    'targets': {
                        't1': round(target_1, 2),
                        't2': round(target_2, 2),
                        't3': round(target_3, 2)
                    },
                    'stop_loss': round(stop_loss, 2),
                    'margin_required': round(margin_per_lot * lots_to_add, 2),
                    'cumulative_margin': round(margin_per_lot * cumulative_lots, 2)
                })

        except Exception as e:
            logger.error(f"Error generating averaging strategy: {e}", exc_info=True)

        # Build response
        response_data = {
            'success': True,
            'symbol': symbol,
            'expiry': expiry_str,
            'direction': direction,
            'current_price': futures_price,
            'lot_size': lot_size,
            'margin_info': {
                'margin_per_lot': round(margin_per_lot, 2),
                'span_margin': round(span_margin, 2),
                'exposure_margin': round(exposure_margin, 2),
                'source': margin_source,
                'available_margin': round(available_margin, 2),
                'used_margin': round(used_margin, 2),
                'total_margin': round(total_account_margin, 2),
                'usable_margin_50pct': round(usable_margin, 2)
            },
            'position_sizing': {
                'suggested_lots': suggested_lots,
                'max_affordable_lots': max_affordable_lots,
                'selected_lots': lots,
                'quantity': lots * lot_size,
                'position_value': round(futures_price * lot_size * lots, 2),
                'margin_required': round(margin_required, 2),
                'margin_used_percent': round(margin_used_pct, 2),
                'remaining_margin': round(remaining_margin, 2),
                'can_afford_averaging': remaining_margin >= (margin_per_lot * lots * 3)  # 3 levels
            },
            'averaging_strategy': {
                'enabled': True,
                'max_attempts': 3,
                'trigger_type': '1% loss per level',
                'levels': averaging_levels,
                'total_margin_needed': round(margin_per_lot * lots * 4, 2)  # Initial + 3 levels
            }
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in calculate_position_sizing: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def calculate_pnl_scenarios(request):
    """
    Calculate P&L for various price scenarios

    POST params:
        - entry_price: Entry price
        - lots: Number of lots
        - lot_size: Lot size
        - direction: 'LONG' or 'SHORT'
    """
    try:
        entry_price = float(request.POST.get('entry_price', 0))
        lots = int(request.POST.get('lots', 1))
        lot_size = int(request.POST.get('lot_size', 1))
        direction = request.POST.get('direction', 'LONG').upper()

        quantity = lots * lot_size
        direction_multiplier = 1 if direction == 'LONG' else -1

        # Price scenarios: -10%, -5%, -2%, 0%, +2%, +5%, +10%
        scenarios = []
        price_changes = [-10, -5, -2, 0, 2, 5, 10]

        for change_pct in price_changes:
            exit_price = entry_price * (1 + change_pct / 100)
            price_diff = exit_price - entry_price
            pnl = price_diff * quantity * direction_multiplier
            pnl_pct = change_pct * direction_multiplier

            scenarios.append({
                'change_pct': change_pct,
                'exit_price': round(exit_price, 2),
                'pnl': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 2),
                'is_profit': pnl > 0,
                'is_loss': pnl < 0,
                'is_breakeven': pnl == 0
            })

        return JsonResponse({
            'success': True,
            'entry_price': entry_price,
            'lots': lots,
            'lot_size': lot_size,
            'quantity': quantity,
            'direction': direction,
            'scenarios': scenarios
        })

    except Exception as e:
        logger.error(f"Error calculating P&L scenarios: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


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
        import json

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
        from apps.brokers.utils.security_master import get_futures_instrument

        logger.info(f"Looking up {symbol} futures in SecurityMaster for expiry {expiry_breeze}")
        instrument = get_futures_instrument(symbol, expiry_breeze)

        if not instrument:
            logger.warning(f"Instrument not found in SecurityMaster, using contract data")
            # Fallback to contract data if SecurityMaster lookup fails
            stock_code = symbol
            lot_size = contract.lot_size
        else:
            # Use SecurityMaster data (more accurate)
            stock_code = instrument['short_name']
            lot_size = instrument['lot_size']
            logger.info(f"SecurityMaster lookup successful: stock_code={stock_code}, lot_size={lot_size}, token={instrument['token']}")

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
                import time
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


@login_required
@require_GET
def get_margin_data(request):
    """
    Get real-time margin data from Neo API

    Returns:
        JSON with margin information:
        - available_margin: Available margin/collateral
        - used_margin: Currently used margin
        - total_margin: Total margin (Net)
        - collateral: Collateral value
        - margin_utilization_pct: Percentage of margin used
        - last_updated: Timestamp
    """
    try:
        from tools.neo import NeoAPI

        # Initialize Neo API
        neo = NeoAPI()

        # Login if not already logged in
        if not neo.session_active:
            neo.login()

        # Fetch margin data
        margin_data = neo.get_margin()

        if not margin_data:
            return JsonResponse({
                'success': False,
                'error': 'Could not fetch margin data from Neo API'
            })

        # Calculate margin utilization percentage
        available = margin_data.get('available_margin', 0)
        used = margin_data.get('used_margin', 0)
        total = margin_data.get('total_margin', 0)

        margin_utilization_pct = 0
        if total > 0:
            margin_utilization_pct = (used / total) * 100

        return JsonResponse({
            'success': True,
            'data': {
                'available_margin': float(available),
                'used_margin': float(used),
                'total_margin': float(total),
                'collateral': float(margin_data.get('collateral', 0)),
                'margin_utilization_pct': round(margin_utilization_pct, 2),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'Neo API',
                'raw': margin_data.get('raw', {})
            }
        })

    except Exception as e:
        logger.error(f"Error fetching margin data: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Error fetching margin data: {str(e)}'
        })


@login_required
@require_GET
def get_suggestion_details(request, suggestion_id):
    """
    Get detailed data for a specific trade suggestion

    URL params:
        - suggestion_id: ID of the suggestion
    """
    try:
        from apps.trading.models import TradeSuggestion

        # Get suggestion
        suggestion = TradeSuggestion.objects.filter(
            id=suggestion_id,
            user=request.user
        ).first()

        if not suggestion:
            return JsonResponse({
                'success': False,
                'error': 'Suggestion not found'
            })

        # Get position details from JSON field
        position_details = suggestion.position_details or {}

        # Return all data needed for trade execution
        return JsonResponse({
            'success': True,
            'suggestion': {
                'id': suggestion.id,
                'stock_symbol': suggestion.instrument,
                'instrument': suggestion.instrument,  # Add instrument field for modal check
                'suggestion_type': suggestion.suggestion_type,  # Add suggestion_type for OPTIONS check
                'strategy': suggestion.strategy,
                'direction': suggestion.direction,
                'spot_price': float(suggestion.spot_price) if suggestion.spot_price else 0,
                'expiry_date': suggestion.expiry_date.strftime('%Y-%m-%d') if suggestion.expiry_date else None,
                'days_to_expiry': suggestion.days_to_expiry if suggestion.days_to_expiry else 0,
                'recommended_lots': suggestion.recommended_lots,
                'margin_required': float(suggestion.margin_required) if suggestion.margin_required else 0,
                'margin_available': float(suggestion.margin_available) if suggestion.margin_available else 0,
                'margin_per_lot': float(suggestion.margin_per_lot) if suggestion.margin_per_lot else 0,
                'margin_utilization': float(suggestion.margin_utilization) if suggestion.margin_utilization else 0,
                'max_profit': float(suggestion.max_profit) if suggestion.max_profit else 0,
                'max_loss': float(suggestion.max_loss) if suggestion.max_loss else 0,
                # Strangle-specific fields
                'call_strike': float(suggestion.call_strike) if suggestion.call_strike else None,
                'put_strike': float(suggestion.put_strike) if suggestion.put_strike else None,
                'call_premium': float(suggestion.call_premium) if suggestion.call_premium else None,
                'put_premium': float(suggestion.put_premium) if suggestion.put_premium else None,
                'total_premium': float(suggestion.total_premium) if suggestion.total_premium else None,
                'vix': float(suggestion.vix) if suggestion.vix else None,
                # Position details from JSON
                'stop_loss': position_details.get('stop_loss', 0),
                'target': position_details.get('target', 0),
                'lot_size': position_details.get('lot_size', 0),
                'entry_value': position_details.get('entry_value', 0),
                'futures_price': position_details.get('margin_data', {}).get('futures_price', suggestion.spot_price),
                # Full position details for reference
                'position_details': position_details
            }
        })

    except Exception as e:
        logger.error(f"Error fetching suggestion details: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_GET
def get_trade_suggestions(request):
    """
    Get trade suggestions history for the logged-in user

    Query params:
        - status: Filter by status (SUGGESTED, TAKEN, ACTIVE, CLOSED, etc.)
        - suggestion_type: Filter by type (OPTIONS, FUTURES)
        - limit: Number of records (default: 20)
    """
    try:
        from apps.trading.models import TradeSuggestion

        # Get query parameters
        status = request.GET.get('status', None)
        suggestion_type = request.GET.get('suggestion_type', None)
        limit = int(request.GET.get('limit', 20))

        # Build query
        queryset = TradeSuggestion.objects.filter(user=request.user)

        if status:
            queryset = queryset.filter(status=status)

        if suggestion_type:
            queryset = queryset.filter(suggestion_type=suggestion_type)

        # Get suggestions ordered by created_at desc
        suggestions = queryset[:limit]

        # Serialize to JSON
        suggestions_data = []
        for suggestion in suggestions:
            suggestions_data.append({
                'id': suggestion.id,
                'strategy': suggestion.get_strategy_display(),
                'suggestion_type': suggestion.suggestion_type,
                'instrument': suggestion.instrument,
                'direction': suggestion.direction,
                'status': suggestion.status,
                'status_color': suggestion.get_status_color(),
                # Market Data
                'spot_price': float(suggestion.spot_price) if suggestion.spot_price else None,
                'vix': float(suggestion.vix) if suggestion.vix else None,
                'expiry_date': suggestion.expiry_date.strftime('%Y-%m-%d') if suggestion.expiry_date else None,
                'days_to_expiry': suggestion.days_to_expiry,
                # Strike Details (for Options)
                'call_strike': float(suggestion.call_strike) if suggestion.call_strike else None,
                'put_strike': float(suggestion.put_strike) if suggestion.put_strike else None,
                'call_premium': float(suggestion.call_premium) if suggestion.call_premium else None,
                'put_premium': float(suggestion.put_premium) if suggestion.put_premium else None,
                'total_premium': float(suggestion.total_premium) if suggestion.total_premium else None,
                # Position Sizing
                'recommended_lots': suggestion.recommended_lots,
                'margin_required': float(suggestion.margin_required) if suggestion.margin_required else None,
                'margin_available': float(suggestion.margin_available) if suggestion.margin_available else None,
                'margin_per_lot': float(suggestion.margin_per_lot) if suggestion.margin_per_lot else None,
                'margin_utilization': float(suggestion.margin_utilization) if suggestion.margin_utilization else None,
                # Risk Metrics
                'max_profit': float(suggestion.max_profit) if suggestion.max_profit else None,
                'max_loss': float(suggestion.max_loss) if suggestion.max_loss else None,
                'breakeven_upper': float(suggestion.breakeven_upper) if suggestion.breakeven_upper else None,
                'breakeven_lower': float(suggestion.breakeven_lower) if suggestion.breakeven_lower else None,
                # P&L (for closed trades)
                'realized_pnl': float(suggestion.realized_pnl) if suggestion.realized_pnl else None,
                'return_on_margin': float(suggestion.return_on_margin) if suggestion.return_on_margin else None,
                # Timestamps
                'created_at': suggestion.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'taken_timestamp': suggestion.taken_timestamp.strftime('%Y-%m-%d %H:%M:%S') if suggestion.taken_timestamp else None,
                'closed_timestamp': suggestion.closed_timestamp.strftime('%Y-%m-%d %H:%M:%S') if suggestion.closed_timestamp else None,
                # Complete Data
                'algorithm_reasoning': suggestion.algorithm_reasoning,
                'position_details': suggestion.position_details,
                'user_notes': suggestion.user_notes,
                # State
                'is_actionable': suggestion.is_actionable,
                'is_active': suggestion.is_active,
                'is_closed': suggestion.is_closed,
            })

        return JsonResponse({
            'success': True,
            'count': len(suggestions_data),
            'suggestions': suggestions_data
        })

    except Exception as e:
        logger.error(f"Error fetching trade suggestions: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def update_suggestion_status(request):
    """
    Update trade suggestion status

    POST params:
        - suggestion_id: ID of the suggestion
        - action: Action to perform (TAKE, REJECT, MARK_ACTIVE, CLOSE)
        - pnl: Realized P&L (for CLOSE action)
        - exit_value: Exit value (for CLOSE action)
        - outcome: Outcome (SUCCESSFUL, LOSS, BREAKEVEN) for CLOSE action
        - user_notes: User notes
    """
    try:
        from apps.trading.models import TradeSuggestion

        suggestion_id = request.POST.get('suggestion_id')
        action = request.POST.get('action', '').upper()
        user_notes = request.POST.get('user_notes', '')

        if not suggestion_id:
            return JsonResponse({
                'success': False,
                'error': 'suggestion_id is required'
            })

        # Get suggestion
        suggestion = TradeSuggestion.objects.filter(
            id=suggestion_id,
            user=request.user
        ).first()

        if not suggestion:
            return JsonResponse({
                'success': False,
                'error': 'Suggestion not found'
            })

        # Perform action
        if action == 'TAKE':
            suggestion.mark_taken(user_notes=user_notes)
            message = 'Suggestion marked as TAKEN'

        elif action == 'REJECT':
            suggestion.mark_rejected(user_notes=user_notes)
            message = 'Suggestion marked as REJECTED'

        elif action == 'MARK_ACTIVE':
            suggestion.mark_active()
            message = 'Trade marked as ACTIVE'

        elif action == 'CLOSE':
            pnl = request.POST.get('pnl')
            exit_value = request.POST.get('exit_value')
            outcome = request.POST.get('outcome', 'CLOSED').upper()

            if pnl:
                pnl = Decimal(pnl)
            if exit_value:
                exit_value = Decimal(exit_value)

            suggestion.mark_closed(
                pnl=pnl,
                exit_value=exit_value,
                outcome=outcome,
                user_notes=user_notes
            )
            message = f'Trade closed with outcome: {outcome}'

        else:
            return JsonResponse({
                'success': False,
                'error': f'Invalid action: {action}'
            })

        return JsonResponse({
            'success': True,
            'message': message,
            'suggestion': {
                'id': suggestion.id,
                'status': suggestion.status,
                'status_color': suggestion.get_status_color(),
            }
        })

    except Exception as e:
        logger.error(f"Error updating suggestion status: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def update_suggestion_parameters(request):
    """
    Update trade suggestion parameters (lots, strikes, expiry, etc.) from UI edits

    POST params (JSON):
        - suggestion_id: ID of the suggestion to update
        - recommended_lots: Updated number of lots
        - call_strike: Updated call strike (for strangles)
        - put_strike: Updated put strike (for strangles)
        - call_premium: Updated call premium (for strangles)
        - put_premium: Updated put premium (for strangles)
        - expiry_date: Updated expiry date (YYYY-MM-DD format)
        - entry_price: Updated entry price (for futures)
        - stop_loss: Updated stop loss
        - target: Updated target

    Returns:
        JsonResponse with success status and updated values
    """
    try:
        import json
        from apps.trading.models import TradeSuggestion
        from datetime import datetime

        # Parse JSON body
        data = json.loads(request.body)
        suggestion_id = data.get('suggestion_id')

        if not suggestion_id:
            return JsonResponse({
                'success': False,
                'error': 'suggestion_id is required'
            })

        # Get suggestion
        suggestion = TradeSuggestion.objects.filter(
            id=suggestion_id,
            user=request.user
        ).first()

        if not suggestion:
            return JsonResponse({
                'success': False,
                'error': 'Suggestion not found'
            })

        # Track what was updated
        updated_fields = []

        # Update lots
        if 'recommended_lots' in data:
            new_lots = int(data['recommended_lots'])
            if new_lots != suggestion.recommended_lots:
                suggestion.recommended_lots = new_lots
                updated_fields.append(f'lots: {new_lots}')

                # Recalculate margin_required based on new lots
                if suggestion.margin_per_lot:
                    suggestion.margin_required = suggestion.margin_per_lot * new_lots
                    updated_fields.append(f'margin_required: {suggestion.margin_required}')

        # Update strangle strikes and premiums
        if 'call_strike' in data:
            new_call_strike = Decimal(str(data['call_strike']))
            if new_call_strike != suggestion.call_strike:
                suggestion.call_strike = new_call_strike
                updated_fields.append(f'call_strike: {new_call_strike}')

        if 'put_strike' in data:
            new_put_strike = Decimal(str(data['put_strike']))
            if new_put_strike != suggestion.put_strike:
                suggestion.put_strike = new_put_strike
                updated_fields.append(f'put_strike: {new_put_strike}')

        if 'call_premium' in data:
            new_call_premium = Decimal(str(data['call_premium']))
            if new_call_premium != suggestion.call_premium:
                suggestion.call_premium = new_call_premium
                updated_fields.append(f'call_premium: {new_call_premium}')

        if 'put_premium' in data:
            new_put_premium = Decimal(str(data['put_premium']))
            if new_put_premium != suggestion.put_premium:
                suggestion.put_premium = new_put_premium
                updated_fields.append(f'put_premium: {new_put_premium}')

        # Recalculate total premium if call or put premium changed
        if suggestion.call_premium and suggestion.put_premium:
            new_total = suggestion.call_premium + suggestion.put_premium
            if new_total != suggestion.total_premium:
                suggestion.total_premium = new_total
                updated_fields.append(f'total_premium: {new_total}')

        # Update expiry date
        if 'expiry_date' in data:
            new_expiry = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
            if new_expiry != suggestion.expiry_date:
                suggestion.expiry_date = new_expiry
                updated_fields.append(f'expiry_date: {new_expiry}')

                # Recalculate days_to_expiry
                from datetime import date
                days_diff = (new_expiry - date.today()).days
                suggestion.days_to_expiry = days_diff
                updated_fields.append(f'days_to_expiry: {days_diff}')

        # Update futures-specific fields
        if 'entry_price' in data:
            new_entry = Decimal(str(data['entry_price']))
            # Store in position_details JSON field
            position_details = suggestion.position_details or {}
            if position_details.get('margin_data', {}).get('futures_price') != float(new_entry):
                if 'margin_data' not in position_details:
                    position_details['margin_data'] = {}
                position_details['margin_data']['futures_price'] = float(new_entry)
                suggestion.position_details = position_details
                updated_fields.append(f'entry_price: {new_entry}')

        if 'stop_loss' in data:
            new_sl = Decimal(str(data['stop_loss']))
            position_details = suggestion.position_details or {}
            if position_details.get('stop_loss') != float(new_sl):
                position_details['stop_loss'] = float(new_sl)
                suggestion.position_details = position_details
                updated_fields.append(f'stop_loss: {new_sl}')

        if 'target' in data:
            new_target = Decimal(str(data['target']))
            position_details = suggestion.position_details or {}
            if position_details.get('target') != float(new_target):
                position_details['target'] = float(new_target)
                suggestion.position_details = position_details
                updated_fields.append(f'target: {new_target}')

        # Save if anything changed
        if updated_fields:
            suggestion.save()
            logger.info(f"Updated TradeSuggestion #{suggestion_id} - {', '.join(updated_fields)}")

            return JsonResponse({
                'success': True,
                'message': f'Updated: {", ".join(updated_fields)}',
                'updated_fields': updated_fields,
                'suggestion': {
                    'id': suggestion.id,
                    'recommended_lots': suggestion.recommended_lots,
                    'call_strike': float(suggestion.call_strike) if suggestion.call_strike else None,
                    'put_strike': float(suggestion.put_strike) if suggestion.put_strike else None,
                    'call_premium': float(suggestion.call_premium) if suggestion.call_premium else None,
                    'put_premium': float(suggestion.put_premium) if suggestion.put_premium else None,
                    'total_premium': float(suggestion.total_premium) if suggestion.total_premium else None,
                    'expiry_date': suggestion.expiry_date.strftime('%Y-%m-%d') if suggestion.expiry_date else None,
                    'margin_required': float(suggestion.margin_required) if suggestion.margin_required else None,
                }
            })
        else:
            return JsonResponse({
                'success': True,
                'message': 'No changes detected',
                'updated_fields': []
            })

    except Exception as e:
        logger.error(f"Error updating suggestion parameters: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def create_execution_control(request):
    """Create execution control record for order tracking and cancellation"""
    try:
        import json
        from apps.trading.models import OrderExecutionControl

        data = json.loads(request.body)
        suggestion_id = data.get('suggestion_id')
        total_batches = data.get('total_batches', 0)

        if not suggestion_id:
            return JsonResponse({
                'success': False,
                'error': 'suggestion_id is required'
            })

        # Create or update execution control
        control, created = OrderExecutionControl.objects.get_or_create(
            suggestion_id=suggestion_id,
            defaults={'total_batches': total_batches}
        )

        if not created:
            # Reset if reusing
            control.is_cancelled = False
            control.cancel_reason = ''
            control.batches_completed = 0
            control.total_batches = total_batches
            control.save()

        return JsonResponse({
            'success': True,
            'message': 'Execution control created',
            'control_id': control.id
        })

    except Exception as e:
        logger.error(f"Error creating execution control: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def cancel_execution(request):
    """Cancel ongoing order execution"""
    try:
        import json
        from apps.trading.models import OrderExecutionControl

        data = json.loads(request.body)
        suggestion_id = data.get('suggestion_id')

        if not suggestion_id:
            return JsonResponse({
                'success': False,
                'error': 'suggestion_id is required'
            })

        control = OrderExecutionControl.objects.filter(
            suggestion_id=suggestion_id
        ).first()

        if not control:
            return JsonResponse({
                'success': False,
                'error': 'No ongoing execution found'
            })

        control.cancel(reason='User requested cancellation')

        return JsonResponse({
            'success': True,
            'message': 'Order execution cancelled'
        })

    except Exception as e:
        logger.error(f"Error cancelling execution: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def get_option_premiums(request):
    """
    Get option premiums (LTP) for given strikes from OptionChain database

    GET params:
        - call_strike: Call strike price
        - put_strike: Put strike price
        - expiry: Expiry date (YYYY-MM-DD)

    Returns:
        JsonResponse with call_premium and put_premium from OptionChain (fetched via Breeze)
    """
    try:
        from apps.data.models import OptionChain
        from datetime import datetime
        from decimal import Decimal

        call_strike = request.GET.get('call_strike')
        put_strike = request.GET.get('put_strike')
        expiry_str = request.GET.get('expiry')

        if not call_strike or not put_strike or not expiry_str:
            return JsonResponse({
                'success': False,
                'error': 'call_strike, put_strike, and expiry are required'
            })

        # Parse parameters
        call_strike_val = Decimal(call_strike)
        put_strike_val = Decimal(put_strike)
        expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()

        logger.info(f"[PREMIUM FETCH] Looking for: Call {call_strike_val} CE, Put {put_strike_val} PE, Expiry {expiry_date}")

        # Fetch call option data from OptionChain (populated via Breeze API)
        call_option = OptionChain.objects.filter(
            underlying='NIFTY',
            option_type='CE',
            strike=call_strike_val,
            expiry_date=expiry_date
        ).order_by('-snapshot_time').first()  # Get latest snapshot

        # Fetch put option data
        put_option = OptionChain.objects.filter(
            underlying='NIFTY',
            option_type='PE',
            strike=put_strike_val,
            expiry_date=expiry_date
        ).order_by('-snapshot_time').first()

        if not call_option or not put_option:
            logger.warning(f"[PREMIUM FETCH] ❌ Option data not found!")
            logger.warning(f"[PREMIUM FETCH] Call option found: {call_option is not None}")
            logger.warning(f"[PREMIUM FETCH] Put option found: {put_option is not None}")

            return JsonResponse({
                'success': False,
                'error': f'Option data not found in database for strikes {call_strike_val}/{put_strike_val} expiry {expiry_date}'
            })

        # Get LTP (Last Traded Price) from OptionChain
        call_premium = float(call_option.ltp) if call_option.ltp else 0.0
        put_premium = float(put_option.ltp) if put_option.ltp else 0.0

        logger.info(f"[PREMIUM FETCH] ✅ Call {call_strike_val} CE: ₹{call_premium}, Put {put_strike_val} PE: ₹{put_premium}")
        logger.info(f"[PREMIUM FETCH] Data from: {call_option.snapshot_time}")

        return JsonResponse({
            'success': True,
            'call_premium': call_premium,
            'put_premium': put_premium,
            'total_premium': call_premium + put_premium,
            'call_strike': float(call_strike_val),
            'put_strike': float(put_strike_val),
            'data_source': 'OptionChain (Breeze API)',
            'snapshot_time': call_option.snapshot_time.isoformat() if call_option.snapshot_time else None,
            'spot_price': float(call_option.spot_price) if call_option.spot_price else None
        })

    except Exception as e:
        logger.error(f"Error fetching option premiums: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def get_execution_progress(request, suggestion_id):
    """Get real-time progress of order execution"""
    try:
        from apps.trading.models import OrderExecutionControl

        control = OrderExecutionControl.objects.filter(
            suggestion_id=suggestion_id
        ).first()

        if not control:
            return JsonResponse({
                'success': False,
                'error': 'No execution found'
            })

        # For now, return basic progress
        # In future, this can be enhanced with detailed batch info
        return JsonResponse({
            'success': True,
            'progress': {
                'batches_completed': control.batches_completed,
                'total_batches': control.total_batches,
                'call_orders': control.batches_completed,  # Simplified for now
                'put_orders': control.batches_completed,   # Simplified for now
                'current_batch': {
                    'batch_num': control.batches_completed + 1,
                    'lots': None,
                    'quantity': None
                },
                'is_cancelled': control.is_cancelled
            }
        })

    except Exception as e:
        logger.error(f"Error getting execution progress: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_GET
def get_contract_details(request):
    """
    Get complete contract details including instrument token from SecurityMaster.

    GET params:
        - symbol: Stock symbol (e.g., 'TCS')
        - expiry: Expiry date in YYYY-MM-DD format (e.g., '2024-12-26')

    Returns:
        JSON with contract details and instrument token
    """
    try:
        symbol = request.GET.get('symbol', '').upper()
        expiry_str = request.GET.get('expiry', '')

        if not symbol or not expiry_str:
            return JsonResponse({
                'success': False,
                'error': 'Symbol and expiry are required'
            })

        # Get contract from database
        from apps.trading.models import ContractData
        contract = ContractData.objects.filter(
            symbol=symbol,
            option_type='FUTURE',
            expiry=expiry_str
        ).first()

        if not contract:
            return JsonResponse({
                'success': False,
                'error': f'Contract not found for {symbol} with expiry {expiry_str}'
            })

        # Format expiry for SecurityMaster lookup
        from datetime import datetime
        expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d').date()
        expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()

        # Get instrument details from SecurityMaster
        from apps.brokers.utils.security_master import get_futures_instrument
        instrument = get_futures_instrument(symbol, expiry_breeze)

        response_data = {
            'success': True,
            'symbol': symbol,
            'expiry': expiry_str,
            'expiry_formatted': expiry_breeze,
            'lot_size': contract.lot_size,
            'price': float(contract.price),
            'volume': contract.traded_contracts
        }

        if instrument:
            response_data['instrument'] = {
                'token': instrument.get('token', 'N/A'),
                'stock_code': instrument.get('short_name', symbol),
                'company_name': instrument.get('company_name', ''),
                'lot_size': instrument.get('lot_size', contract.lot_size),
                'source': 'SecurityMaster'
            }
        else:
            response_data['instrument'] = {
                'token': 'Not found in SecurityMaster',
                'stock_code': symbol,
                'company_name': '',
                'lot_size': contract.lot_size,
                'source': 'ContractData fallback'
            }

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error fetching contract details: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_GET
def get_lot_size(request):
    """
    Get lot size and instrument token for a trading symbol using Neo API.

    GET params:
        - trading_symbol: Trading symbol (e.g., 'NIFTY25NOV27050CE')

    Returns:
        JSON: {
            'success': True,
            'lot_size': 75,
            'symbol': 'NIFTY25NOV27050CE',
            'instrument_token': '12345',
            'expiry': '28-NOV-2024'
        }
    """
    try:
        trading_symbol = request.GET.get('trading_symbol', '')

        if not trading_symbol:
            return JsonResponse({
                'success': False,
                'error': 'Trading symbol is required'
            })

        from apps.brokers.integrations.kotak_neo import get_lot_size_from_neo_with_token

        # Get lot size and instrument details
        result = get_lot_size_from_neo_with_token(trading_symbol)

        return JsonResponse({
            'success': True,
            'lot_size': result.get('lot_size', 75),
            'symbol': trading_symbol,
            'instrument_token': result.get('token', 'N/A'),
            'expiry': result.get('expiry', 'N/A'),
            'exchange_segment': result.get('exchange_segment', 'N/A')
        })

    except Exception as e:
        logger.error(f"Error fetching lot size: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
