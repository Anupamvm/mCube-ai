"""
Position Sizing and P&L Analysis API Views

Endpoints for calculating position sizes, margin requirements,
P&L scenarios, and averaging analysis for futures trading.
"""

import logging
import re
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.http import JsonResponse

from apps.brokers.integrations.breeze import get_breeze_client, get_nfo_margin
from apps.brokers.integrations.kotak_neo import get_kotak_neo_client
from apps.accounts.models import BrokerAccount
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


@require_http_methods(["POST"])
def analyze_position_averaging(request):
    """
    Analyze an existing futures position for averaging opportunities.

    This endpoint runs a comprehensive analysis to determine if adding to an
    existing position (averaging) is a good idea based on:

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

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'POST method required'
        }, status=405)

    try:
        import json
        from apps.trading.averaging_analyzer import AveragingAnalyzer

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

        logger.info(f"Analyzing averaging for {symbol} {direction} @ ₹{entry_price} ({quantity} qty)")

        # Extract base symbol from both Breeze and Neo formats
        # Breeze: JIOFIN-I -> JIOFIN
        # Neo: JIOFIN25DECFUT -> JIOFIN, NIFTY26JANFUT -> NIFTY
        if '-' in symbol:
            # Breeze format with hyphen
            base_symbol = symbol.split('-')[0]
        else:
            # Neo format - extract alphabetic characters from the start
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
                logger.info(f"Found lot size from ContractData: {lot_size}")

        # Fallback lot sizes if not found
        if not lot_size:
            fallback_lot_sizes = {
                'RELIANCE': 250,
                'TCS': 150,
                'INFY': 300,
                'HDFCBANK': 550,
                'ICICIBANK': 1375,
                'SBIN': 1500,
                'NIFTY': 50,
                'BANKNIFTY': 15,
            }
            lot_size = fallback_lot_sizes.get(base_symbol, 500)
            logger.warning(f"Using fallback lot size for {base_symbol}: {lot_size}")

        # Initialize analyzer with Breeze client (always use Breeze for LTP fetching)
        breeze = get_breeze_client()
        analyzer = AveragingAnalyzer(breeze_client=breeze)

        # Get Neo client if needed (for future margin calculations)
        if broker == 'neo':
            neo = get_kotak_neo_client()

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

        logger.info(f"Analysis result received: success={analysis_result.get('success')}, recommendation={analysis_result.get('recommendation')}")
        logger.info(f"Analysis result keys: {list(analysis_result.keys())}")
        if 'error' in analysis_result:
            logger.error(f"Analysis error: {analysis_result.get('error')}")
        if 'reason' in analysis_result:
            logger.info(f"Analysis reason: {analysis_result.get('reason')}")
        logger.info(f"Execution log length: {len(analysis_result.get('execution_log', []))}")
        for i, log_entry in enumerate(analysis_result.get('execution_log', [])):
            logger.info(f"  Execution log [{i}]: {log_entry}")

        # Log critical checks details
        critical_checks = analysis_result.get('critical_checks', {})
        logger.info(f"Price drop check: {critical_checks.get('price_drop_check')}")
        logger.info(f"Support proximity check: {critical_checks.get('support_proximity_check')}")

        if not analysis_result.get('success'):
            logger.warning(f"Analysis failed - returning error response")
            return JsonResponse({
                'success': False,
                'error': analysis_result.get('error', 'Analysis failed'),
                'execution_log': analysis_result.get('execution_log', [])
            })

        # Add margin information
        position_sizing = analysis_result.get('position_sizing', {})
        recommended_lots = position_sizing.get('recommended_lots', 0)

        if recommended_lots > 0:
            # Fetch margin requirements
            from apps.trading.position_sizer import PositionSizer

            if broker == 'breeze':
                sizer = PositionSizer(breeze_client=breeze)

                # Format expiry for Breeze
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
                    # Get available margin
                    try:
                        margin_data = breeze.get_margin(exchange_code="NFO")
                        if margin_data and margin_data.get('Status') == 200:
                            margin_info = margin_data.get('Success', {})
                            available_margin = float(margin_info.get('cash_limit', 0)) - float(margin_info.get('block_by_trade', 0))
                        else:
                            available_margin = 5000000  # Default 50L
                    except:
                        available_margin = 5000000

                    position_sizing['margin_per_lot'] = margin_response.get('margin_per_lot', 0)
                    position_sizing['total_margin_required'] = margin_response.get('total_margin', 0)
                    position_sizing['available_margin'] = available_margin
                    position_sizing['margin_utilization_pct'] = (
                        margin_response.get('total_margin', 0) / available_margin * 100
                    ) if available_margin > 0 else 0

        # Format response similar to verify_future_trade
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

        logger.info(f"✅ Averaging analysis complete: {response_data['recommendation']} (Confidence: {response_data['confidence']}%)")

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in averaging analysis: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
