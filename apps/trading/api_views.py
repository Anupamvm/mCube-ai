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

from apps.brokers.integrations.breeze import get_breeze_client
from apps.positions.models import Position
from apps.orders.models import Order
from apps.accounts.models import BrokerAccount
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
            symbol = data.get('stock_symbol', '').upper()
            direction = data.get('direction', 'buy').lower()
            lots = int(data.get('lots', 1))
            futures_price = float(data.get('price', 0))
            stop_loss = float(data.get('stop_loss', 0))
            target = float(data.get('target', 0))
            enable_averaging = data.get('enable_averaging', False)
        else:
            symbol = request.POST.get('stock_symbol', request.POST.get('symbol', '')).upper()
            direction = request.POST.get('direction', 'buy').lower()
            lots = int(request.POST.get('lots', 1))
            futures_price = float(request.POST.get('price', 0))
            stop_loss = float(request.POST.get('stop_loss', 0))
            target = float(request.POST.get('target', 0))
            enable_averaging = request.POST.get('enable_averaging', 'false').lower() == 'true'

        # Normalize direction to LONG/SHORT
        if direction in ['buy', 'long']:
            direction = 'LONG'
        elif direction in ['sell', 'short']:
            direction = 'SHORT'

        # Get contract - use latest expiry if not specified
        contract = ContractData.objects.filter(
            symbol=symbol,
            option_type='FUTURE'
        ).order_by('expiry').first()

        if not contract:
            return JsonResponse({
                'success': False,
                'error': f'Contract not found for {symbol}'
            })

        lot_size = contract.lot_size
        quantity = lots * lot_size
        # Use provided price or contract price
        entry_price = futures_price if futures_price > 0 else float(contract.price)

        # Format expiry for Breeze
        expiry_dt = contract.expiry
        expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()

        # Initialize Breeze
        breeze = get_breeze_client()

        # Validate margin availability
        try:
            funds_response = breeze.get_funds()
            if funds_response and funds_response.get('Status') == 200:
                available_margin = float(funds_response.get('Success', {}).get('availablemargin', 0))

                # Estimate margin needed
                margin_needed = entry_price * lot_size * lots * 0.12

                if margin_needed > available_margin:
                    return JsonResponse({
                        'success': False,
                        'error': f'Insufficient margin. Need: ₹{margin_needed:,.0f}, Available: ₹{available_margin:,.0f}'
                    })
        except Exception as e:
            logger.warning(f"Could not validate margin: {e}")

        # Atomic transaction for database operations
        with transaction.atomic():
            # Create Position
            position = Position.objects.create(
                user=request.user,
                broker_account=BrokerAccount.objects.filter(user=request.user, broker_name='ICICI').first(),
                symbol=symbol,
                instrument_type='FUTURES',
                option_type=None,
                strike_price=None,
                expiry_date=expiry_dt,
                direction=direction,
                quantity=quantity,
                entry_price=entry_price,
                current_price=entry_price,
                stop_loss=stop_loss,
                target=target,
                status='OPEN',
                enable_averaging=enable_averaging,
                averaging_count=0,
                original_entry_price=entry_price
            )

            # Place order via Breeze
            action = 'buy' if direction == 'LONG' else 'sell'

            order_response = breeze.place_order(
                stock_code=symbol,
                exchange_code='NFO',
                product='futures',
                action=action,
                order_type='market',
                quantity=str(quantity),
                price='0',
                validity='day',
                stoploss='0',
                disclosed_quantity='0',
                expiry_date=expiry_breeze,
                right='others',
                strike_price='0'
            )

            if order_response and order_response.get('Status') == 200:
                order_data = order_response.get('Success', {})
                order_id = order_data.get('order_id', 'UNKNOWN')

                # Create Order record
                order = Order.objects.create(
                    user=request.user,
                    position=position,
                    broker_order_id=order_id,
                    symbol=symbol,
                    order_type='ENTRY',
                    action=action.upper(),
                    quantity=quantity,
                    price=entry_price,
                    status='PENDING',
                    purpose='ENTRY'
                )

                logger.info(f"Order placed successfully: {order_id} for {symbol}")

                return JsonResponse({
                    'success': True,
                    'order_id': order_id,
                    'position_id': position.id,
                    'message': f'Order placed successfully! Order ID: {order_id}',
                    'status': 'PENDING'
                })

            else:
                # Order failed - rollback position creation
                error_msg = order_response.get('Error', 'Unknown error') if order_response else 'API call failed'
                logger.error(f"Order placement failed: {error_msg}")

                # Transaction will auto-rollback due to exception
                raise Exception(error_msg)

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
                'direction': suggestion.direction,
                'spot_price': float(suggestion.spot_price) if suggestion.spot_price else 0,
                'expiry_date': suggestion.expiry_date.strftime('%Y-%m-%d') if suggestion.expiry_date else None,
                'recommended_lots': suggestion.recommended_lots,
                'margin_required': float(suggestion.margin_required) if suggestion.margin_required else 0,
                'margin_available': float(suggestion.margin_available) if suggestion.margin_available else 0,
                'margin_per_lot': float(suggestion.margin_per_lot) if suggestion.margin_per_lot else 0,
                'margin_utilization': float(suggestion.margin_utilization) if suggestion.margin_utilization else 0,
                'max_profit': float(suggestion.max_profit) if suggestion.max_profit else 0,
                'max_loss': float(suggestion.max_loss) if suggestion.max_loss else 0,
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
