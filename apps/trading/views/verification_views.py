"""
Trading Verification Views - Contract Analysis and Data Management

This module contains views for verifying futures contracts and managing market data:
- Trendlyne data fetching with real-time log streaming (SSE)
- Fetch contracts with volume filtering
- Verify futures contract for trading with comprehensive analysis

All views integrate with Breeze API for real-time market data and analysis.
"""

import json
import logging
import time
import uuid
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, StreamingHttpResponse

logger = logging.getLogger(__name__)


def ajax_login_required(view_func):
    """
    Decorator that returns JSON response for unauthenticated AJAX requests
    instead of redirecting to login page.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required. Please log in.',
                'auth_required': True
            }, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


@ajax_login_required
@require_POST
def start_trendlyne_fetch(request):
    """
    Start a Trendlyne data fetch and return a session ID for SSE streaming.

    This initiates the Selenium-based data fetch in a background thread and
    returns a session ID that can be used to connect to the SSE log stream.

    Request Body (JSON):
        {} (empty or any data)

    Returns:
        JsonResponse: {
            'success': bool,
            'session_id': str,  # UUID for SSE connection
            'message': str
        }

    Error Responses:
        - 500: Failed to start fetch process

    Usage:
        1. POST to this endpoint to start the fetch
        2. Use session_id to connect to /trigger/trendlyne-logs/<session_id>/
        3. Listen for SSE events until 'complete' or 'error' type received
    """
    try:
        session_id = str(uuid.uuid4())

        # Start the fetch in background
        from apps.data.services.trendlyne_fetcher import start_trendlyne_fetch as start_fetch
        start_fetch(session_id)

        logger.info(f"Started Trendlyne fetch session: {session_id}")

        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'message': 'Trendlyne data fetch started'
        })

    except Exception as e:
        logger.error(f"Error starting Trendlyne fetch: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@ajax_login_required
def stream_trendlyne_logs(request, session_id):
    """
    Server-Sent Events (SSE) endpoint for streaming Trendlyne fetch logs.

    Streams real-time log messages from the Trendlyne data fetch process.
    Each log message includes timestamp, level, and message content.

    URL Parameters:
        session_id: UUID returned from start_trendlyne_fetch

    SSE Event Format:
        data: {"type": "log|connected|complete|error", "timestamp": "HH:MM:SS", "level": "info|success|warning|error", "message": "..."}

    Event Types:
        - connected: Initial connection established
        - log: Regular log message with level and content
        - complete: Fetch process finished successfully
        - error: Error occurred during fetch

    Usage (JavaScript):
        const eventSource = new EventSource('/trading/trigger/trendlyne-logs/<session_id>/');
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'log') {
                console.log(`[${data.level}] ${data.message}`);
            } else if (data.type === 'complete') {
                eventSource.close();
            }
        };

    Notes:
        - Stream times out after 5 minutes
        - Session is cleaned up after stream ends
        - 10 second idle timeout for detecting completion
    """
    from apps.data.services.trendlyne_fetcher import get_active_session, cleanup_session

    def event_stream():
        """Generator that yields SSE formatted events"""
        callback = get_active_session(session_id)

        if not callback:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Session not found'})}\n\n"
            return

        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected', 'message': 'Connected to log stream'})}\n\n"

        max_wait_time = 300  # 5 minutes max
        start_time = time.time()
        last_activity = time.time()
        idle_timeout = 30  # 30 seconds of no logs means completion (Selenium downloads take time)

        while callback.is_running and (time.time() - start_time) < max_wait_time:
            logs = callback.get_logs(timeout=0.5)

            if logs:
                last_activity = time.time()
                for log in logs:
                    event_data = {
                        'type': 'log',
                        'timestamp': log['timestamp'],
                        'level': log['level'],
                        'message': log['message']
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
            else:
                # Check for idle timeout (process might be done)
                if (time.time() - last_activity) > idle_timeout:
                    break

            # Small sleep to prevent tight loop
            time.sleep(0.1)

        # Send completion message
        yield f"data: {json.dumps({'type': 'complete', 'message': 'Fetch process completed'})}\n\n"

        # Cleanup session
        cleanup_session(session_id)

    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
@require_POST
def get_contracts(request):
    """
    AJAX endpoint to fetch futures contracts based on dynamic volume thresholds.

    Filters futures contracts by volume criteria:
    - This month: traded_contracts >= this_month_volume
    - Next month: traded_contracts >= next_month_volume

    Request Body (JSON):
        {
            "this_month_volume": 1000,  # Volume threshold for contracts expiring in next 30 days
            "next_month_volume": 800    # Volume threshold for contracts expiring 30-60 days out
        }

    Returns:
        JsonResponse: {
            'success': bool,
            'contracts': [
                {
                    'value': 'SYMBOL|YYYY-MM-DD',  # For form submission
                    'display': 'SYMBOL - DD-MMM-YYYY',  # For UI display
                    'volume': int,
                    'price': float,
                    'lot_size': int
                },
                ...
            ],
            'total_contracts': int
        }

    Error Responses:
        - 400: Invalid request body
        - 500: Database query error

    Notes:
        - Results sorted by symbol then expiry date
        - Date ranges calculated relative to current date
        - This month: today to today+30 days
        - Next month: today+30 to today+60 days
    """
    import json
    from apps.data.models import ContractData
    from django.db.models import Q
    from datetime import datetime, timedelta

    try:
        # Parse JSON body
        body = json.loads(request.body)
        this_month_volume = int(body.get('this_month_volume', 1000))
        next_month_volume = int(body.get('next_month_volume', 800))

        logger.info(f"Fetching contracts with volume thresholds: this_month={this_month_volume}, next_month={next_month_volume}")

        today = datetime.now().date()

        # Calculate date ranges
        this_month_end = today + timedelta(days=30)
        next_month_start = today + timedelta(days=30)
        next_month_end = today + timedelta(days=60)

        # Get futures contracts that meet volume criteria
        futures_contracts = ContractData.objects.filter(
            option_type='FUTURE',
            expiry__gte=str(today),
            expiry__lte=str(next_month_end)
        ).filter(
            Q(expiry__lte=str(this_month_end), traded_contracts__gte=this_month_volume) |
            Q(expiry__gte=str(next_month_start), expiry__lte=str(next_month_end), traded_contracts__gte=next_month_volume)
        ).order_by('symbol', 'expiry').values(
            'symbol',
            'expiry',
            'traded_contracts',
            'price',
            'lot_size'
        )

        # Format contracts
        contract_list = []
        for contract in futures_contracts:
            expiry_date = datetime.strptime(contract['expiry'], '%Y-%m-%d').strftime('%d-%b-%Y')
            display_name = f"{contract['symbol']} - {expiry_date}"
            contract_value = f"{contract['symbol']}|{contract['expiry']}"

            contract_list.append({
                'value': contract_value,
                'display': display_name,
                'volume': contract['traded_contracts'],
                'price': contract['price'],
                'lot_size': contract['lot_size']
            })

        logger.info(f"Found {len(contract_list)} contracts matching volume criteria")

        return JsonResponse({
            'success': True,
            'contracts': contract_list,
            'total_contracts': len(contract_list),
        })

    except Exception as e:
        logger.error(f"Error fetching contracts: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def verify_future_trade(request):
    """
    Verify a specific futures contract for trading with comprehensive 9-step analysis.

    Runs the complete futures analysis algorithm on a single contract:
    1. Spot price fetch (Breeze API)
    2. Futures price fetch (Breeze API)
    3. Open Interest analysis
    4. Sector strength check
    5. Multi-factor technical analysis (RSI, MACD, Bollinger Bands)
    6. DMA (50/100/200) analysis
    7. Support/Resistance levels
    8. Composite scoring (0-100)
    9. Position sizing with real Breeze margin

    Request Body (POST form data):
        contract: "SYMBOL|YYYY-MM-DD"  # Example: "RELIANCE|2024-01-25"

    Returns:
        JsonResponse: {
            'success': bool,
            'symbol': str,
            'expiry': 'DD-MMM-YYYY',
            'contract_display': 'SYMBOL - DD-MMM-YYYY',
            'passed': bool,  # True if composite score >= passing threshold
            'analysis': {
                'direction': 'LONG'|'SHORT'|'NEUTRAL',
                'entry_price': float,
                'stop_loss': float,
                'target': float,
                'composite_score': int,  # 0-100
                'contract_price': float,
                'spot_price': float,
                'lot_size': int,
                'traded_volume': int,
                'basis': float,
                'basis_pct': float,
                'cost_of_carry': float,
                'position_details': {
                    'lot_size': int,
                    'recommended_lots': int,
                    'entry_value': float,
                    'risk_amount': float,
                    'reward_amount': float,
                    'risk_reward_ratio': float,
                    'margin_required': float,
                    'margin_per_lot': float,
                    'available_margin': float,
                    'margin_utilization_pct': float,
                    'max_lots_possible': int,
                    'stop_loss': float,
                    'target': float
                },
                'expiry_date': 'YYYY-MM-DD',
                'breeze_token': str,  # Instrument token for order placement
                'breeze_stock_code': str,  # Breeze stock code
                'score_breakdown': {
                    'oi_score': int,
                    'sector_score': int,
                    'technical_score': int,
                    'dma_score': int,
                    'sr_score': int
                }
            },
            'execution_log': [
                {
                    'step': int,
                    'action': str,
                    'status': 'success'|'warning'|'fail',
                    'message': str,
                    'details': dict
                },
                ...
            ],
            'llm_validation': {
                'approved': bool,
                'confidence': float,
                'reasoning': str
            },
            'verdict': str,  # "PASS - Score: 78/100"
            'reason': str,
            'position_sizing': {
                'position': {
                    'recommended_lots': int,
                    'total_margin_required': float,
                    'entry_value': float,
                    'margin_utilization_percent': float
                },
                'margin_data': {
                    'available_margin': float,
                    'used_margin': float,
                    'total_margin': float,
                    'margin_per_lot': float,
                    'max_lots_possible': int,
                    'futures_price': float,
                    'source': 'Breeze API'|'Estimated'
                }
            },
            'suggestion_id': int  # Only present if contract passed analysis
        }

    Error Responses:
        - 400: Missing or invalid contract parameter
        - 404: Contract not found or analysis failed
        - 500: Analysis error

    Side Effects:
        - Fetches real-time spot and futures prices from Breeze API
        - Fetches F&O margin data from Breeze account
        - Queries SecurityMaster for Breeze instrument token
        - Creates TradeSuggestion record if analysis passes
        - TradeSuggestion expires in 24 hours

    Position Sizing Logic:
        - Uses 50% margin rule: recommended_lots = 50% of available margin / margin_per_lot
        - Remaining 50% reserved for averaging (2 additional positions)
        - max_lots_possible shows maximum with 100% margin utilization
        - Stop loss: 2% (LONG) or +2% (SHORT)
        - Target: +4% (LONG) or -4% (SHORT)

    Notes:
        - Requires active Breeze account with valid session
        - Lot sizes hardcoded for common stocks if not in ContractData
        - Fallback margin: ₹50 lakh if Breeze API fails
        - Breeze token required for actual order placement (not execution)
        - Analysis includes support/resistance breach risk calculation
    """
    try:
        from decimal import Decimal
        from apps.trading.futures_analyzer import comprehensive_futures_analysis
        from apps.data.models import ContractData

        contract_value = request.POST.get('contract', '').strip()

        if not contract_value:
            return JsonResponse({
                'success': False,
                'error': 'Contract selection is required'
            })

        # Parse contract value: "SYMBOL|YYYY-MM-DD"
        try:
            stock_symbol, expiry_date = contract_value.split('|')
            stock_symbol = stock_symbol.upper()
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid contract format'
            })

        logger.info(f"Manual verification: {stock_symbol} expiry {expiry_date}")

        # Get contract details from Trendlyne
        contract = ContractData.objects.filter(
            symbol=stock_symbol,
            option_type='FUTURE',
            expiry=expiry_date
        ).first()

        # Run comprehensive analysis with Breeze API
        analysis_result = comprehensive_futures_analysis(
            stock_symbol=stock_symbol,
            expiry_date=expiry_date,
            contract=contract
        )

        if not analysis_result.get('success'):
            return JsonResponse({
                'success': False,
                'error': analysis_result.get('error', f'Unable to analyze {stock_symbol}. Stock may not be available for F&O or data is missing.'),
                'execution_log': analysis_result.get('execution_log', [])
            })

        # Extract metrics and prepare response
        metrics = analysis_result.get('metrics', {})
        execution_log = analysis_result.get('execution_log', [])

        # Get prices from analysis
        spot_price = metrics.get('spot_price', 0)
        futures_price = metrics.get('futures_price', 0)

        # Format expiry for display
        from datetime import datetime
        expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
        expiry_formatted = expiry_dt.strftime('%d-%b-%Y')

        # Determine pass/fail based on analysis verdict
        passed = analysis_result.get('verdict') == 'PASS'
        direction = analysis_result.get('direction', 'NEUTRAL')
        composite_score = analysis_result.get('composite_score', 0)

        # Calculate position sizing with 50% margin rule (like options)
        position_details = {}
        position_sizing = {}

        if futures_price > 0:
            from apps.trading.position_sizer import PositionSizer
            from apps.brokers.integrations.breeze import get_breeze_client

            # Get lot size from contract or use estimated fallback
            if contract and contract.lot_size:
                lot_size = contract.lot_size
            else:
                # Fallback lot sizes for common stocks (estimated)
                fallback_lot_sizes = {
                    'ASIANPAINT': 250,
                    'RELIANCE': 250,
                    'TCS': 150,
                    'INFY': 300,
                    'HDFCBANK': 550,
                    'ICICIBANK': 1375,
                    'SBIN': 1500,
                    'TATAMOTORS': 1500,
                    'TATASTEEL': 2500,
                    'WIPRO': 1200,
                }
                lot_size = fallback_lot_sizes.get(stock_symbol.upper(), 500)  # Default 500
                logger.warning(f"Using fallback lot size for {stock_symbol}: {lot_size}")

            # Format expiry for Breeze API
            expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
            expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()

            # Initialize position sizer with Breeze client
            try:
                breeze = get_breeze_client()
                sizer = PositionSizer(breeze_client=breeze)

                # Fetch margin for 1 lot (using estimation since Breeze doesn't provide per-contract margin)
                margin_response = sizer.fetch_margin_requirement(
                    stock_code=stock_symbol,
                    expiry=expiry_breeze,
                    quantity=lot_size,  # 1 lot
                    direction=direction,
                    futures_price=futures_price
                )

                if margin_response.get('success'):
                    margin_per_lot = margin_response.get('margin_per_lot', 0)
                    total_margin_for_one = margin_response.get('total_margin', 0)

                    logger.info(f"Breeze margin for {stock_symbol}: ₹{margin_per_lot:,.0f} per lot")

                    # Get available margin from Breeze account (F&O margin)
                    try:
                        # Use get_margin for F&O segment
                        margin_response = breeze.get_margin(exchange_code="NFO")
                        if margin_response and margin_response.get('Status') == 200:
                            margin_data = margin_response.get('Success', {})

                            # Breeze F&O margin fields:
                            # - cash_limit: Total margin limit
                            # - amount_allocated: Currently allocated
                            # - block_by_trade: Blocked by active trades
                            cash_limit = float(margin_data.get('cash_limit', 0))
                            amount_allocated = float(margin_data.get('amount_allocated', 0))
                            block_by_trade = float(margin_data.get('block_by_trade', 0))

                            # Available margin = cash_limit - block_by_trade
                            available_margin = cash_limit - block_by_trade

                            logger.info(f"Available F&O margin from Breeze: ₹{available_margin:,.0f} (cash_limit: ₹{cash_limit:,.0f}, blocked: ₹{block_by_trade:,.0f})")
                        else:
                            # Fallback: use estimated value
                            available_margin = 5000000  # 50 lakh default
                            logger.warning("Could not fetch F&O margin, using default: ₹50,00,000")
                    except Exception as e:
                        logger.warning(f"Error fetching F&O margin: {e}, using default available margin")
                        available_margin = 5000000

                    # Apply 50% rule for initial position
                    # Initial position should use 50% of available margin
                    # Remaining 50% is reserved for averaging (2 more positions)
                    safe_margin = available_margin * 0.5

                    # Calculate recommended lots to use 50% margin (not 25%)
                    # This is the initial position size
                    recommended_lots = max(1, int(safe_margin / margin_per_lot)) if margin_per_lot > 0 else 0

                    # Max lots possible with full available margin (for slider limit)
                    max_lots_possible = int(available_margin / margin_per_lot) if margin_per_lot > 0 else 0

                    # Calculate position metrics
                    total_margin_required = margin_per_lot * recommended_lots
                    entry_value = futures_price * lot_size * recommended_lots
                    margin_utilization = (total_margin_required / available_margin * 100) if available_margin > 0 else 0

                    # Calculate stop loss and targets
                    if direction == 'LONG':
                        stop_loss = futures_price * 0.98
                        target = futures_price * 1.04
                    elif direction == 'SHORT':
                        stop_loss = futures_price * 1.02
                        target = futures_price * 0.96
                    else:
                        stop_loss = futures_price * 0.98
                        target = futures_price * 1.02

                    risk_amount = abs(futures_price - stop_loss) * lot_size * recommended_lots
                    reward_amount = abs(target - futures_price) * lot_size * recommended_lots
                    risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0

                    # Build position sizing data
                    position_sizing = {
                        'position': {
                            'recommended_lots': recommended_lots,
                            'total_margin_required': total_margin_required,
                            'entry_value': entry_value,
                            'margin_utilization_percent': round(margin_utilization, 2)
                        },
                        'margin_data': {
                            'available_margin': available_margin,
                            'used_margin': total_margin_required,
                            'total_margin': available_margin,
                            'margin_per_lot': margin_per_lot,
                            'max_lots_possible': max_lots_possible,
                            'futures_price': futures_price,  # Add futures price for trade execution
                            'source': 'Breeze API'
                        }
                    }

                    position_details = {
                        'lot_size': lot_size,
                        'recommended_lots': recommended_lots,
                        'entry_value': entry_value,
                        'risk_amount': risk_amount,
                        'reward_amount': reward_amount,
                        'risk_reward_ratio': round(risk_reward_ratio, 2),
                        'margin_required': total_margin_required,
                        'margin_per_lot': margin_per_lot,
                        'available_margin': available_margin,
                        'margin_utilization_pct': round(margin_utilization, 2),
                        'max_lots_possible': max_lots_possible,
                        'stop_loss': stop_loss,
                        'target': target
                    }

                    logger.info(f"Position sizing: {recommended_lots} lots (50% rule: {max_lots_possible} max → {recommended_lots} recommended)")

                else:
                    # Fallback if margin fetch fails
                    logger.warning(f"Could not fetch margin: {margin_response.get('error')}")
                    position_details = {
                        'lot_size': lot_size,
                        'recommended_lots': 1,
                        'entry_value': futures_price * lot_size,
                        'margin_required': 0,
                        'error': 'Margin data unavailable'
                    }

            except Exception as e:
                logger.error(f"Error in position sizing: {e}", exc_info=True)
                # Fallback
                position_details = {
                    'lot_size': lot_size,
                    'recommended_lots': 1,
                    'entry_value': futures_price * lot_size,
                    'margin_required': 0,
                    'error': str(e)
                }

        # Fetch Breeze token from SecurityMaster for order placement verification
        breeze_token = None
        breeze_stock_code = None
        try:
            from apps.brokers.utils.security_master import get_futures_instrument

            instrument = get_futures_instrument(stock_symbol, expiry_breeze)
            if instrument:
                breeze_token = instrument.get('token')
                breeze_stock_code = instrument.get('short_name')
                logger.info(f"✅ Breeze token fetched for confirmation: {breeze_token} (stock_code: {breeze_stock_code})")
            else:
                logger.warning(f"⚠️ Could not fetch Breeze token for {stock_symbol} {expiry_breeze}")
        except Exception as e:
            logger.error(f"Error fetching Breeze token: {e}", exc_info=True)

        # Build analysis summary
        analysis_summary = {
            'direction': direction,
            'entry_price': futures_price,
            'stop_loss': position_details.get('stop_loss', futures_price * 0.98) if position_details else futures_price * 0.98,
            'target': position_details.get('target', futures_price * 1.04) if position_details else futures_price * 1.04,
            'composite_score': composite_score,
            'contract_price': futures_price,
            'spot_price': spot_price,
            'lot_size': position_details.get('lot_size') if position_details else (contract.lot_size if contract else 0),
            'traded_volume': contract.traded_contracts if contract else 0,
            'basis': metrics.get('basis', 0),
            'basis_pct': metrics.get('basis_pct', 0),
            'cost_of_carry': metrics.get('cost_of_carry', 0),
            'position_details': position_details,
            'expiry_date': expiry_date,  # Add raw expiry date (YYYY-MM-DD format)
            'breeze_token': breeze_token,  # Add Breeze instrument token
            'breeze_stock_code': breeze_stock_code,  # Add Breeze stock code
            'score_breakdown': analysis_result.get('scores', {})  # Add component scores breakdown
        }

        response_data = {
            'success': True,
            'symbol': stock_symbol,
            'expiry': expiry_formatted,
            'contract_display': f"{stock_symbol} - {expiry_formatted}",
            'passed': passed,
            'analysis': analysis_summary,
            'execution_log': execution_log,
            'llm_validation': {'approved': False, 'confidence': 0, 'reasoning': 'LLM validation skipped (Phase 2)'},
            'verdict': f'{"PASS" if passed else "FAIL"} - Score: {composite_score}/100',
            'reason': f'Composite score: {composite_score}/100. Direction: {direction}',
            'position_sizing': position_sizing  # Add comprehensive position sizing data
        }

        # Save trade suggestion to database (only if PASS)
        if passed:
            from apps.trading.models import TradeSuggestion
            from datetime import timedelta
            from django.utils import timezone
            import json
            from datetime import date, datetime

            # Helper to clean data and serialize for JSON
            import math

            def clean_numeric_value(obj):
                """Convert NaN and Infinity to None for JSON compatibility"""
                if isinstance(obj, float):
                    if math.isnan(obj) or math.isinf(obj):
                        return None
                    return obj
                if isinstance(obj, Decimal):
                    val = float(obj)
                    if math.isnan(val) or math.isinf(val):
                        return None
                    return val
                return obj

            def clean_dict_for_json(data):
                """Recursively clean dictionary to remove NaN and Infinity values"""
                if isinstance(data, dict):
                    return {k: clean_dict_for_json(v) for k, v in data.items()}
                elif isinstance(data, list):
                    return [clean_dict_for_json(item) for item in data]
                else:
                    return clean_numeric_value(data)

            def json_serial(obj):
                """Handle JSON serialization for non-standard types"""
                if isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                if isinstance(obj, Decimal):
                    return float(obj)
                # Convert any other non-serializable object to string
                try:
                    return str(obj)
                except:
                    return None

            # Convert data to JSON-safe format with error handling
            try:
                # Clean data first to remove NaN/Infinity
                cleaned_data = clean_dict_for_json({
                    'metrics': metrics,
                    'execution_log': execution_log,
                    'analysis_summary': analysis_summary,
                    'composite_score': composite_score
                })

                algorithm_reasoning_safe = json.loads(
                    json.dumps(cleaned_data, default=json_serial)
                )
            except (ValueError, TypeError) as e:
                logger.error(f"Error serializing algorithm_reasoning: {e}")
                algorithm_reasoning_safe = {
                    'metrics': {},
                    'execution_log': [],
                    'analysis_summary': {},
                    'composite_score': composite_score,
                    'error': 'Serialization error'
                }

            try:
                # Clean position sizing data
                cleaned_position = clean_dict_for_json(position_sizing)
                position_details_safe = json.loads(
                    json.dumps(cleaned_position, default=json_serial)
                )
            except (ValueError, TypeError) as e:
                logger.error(f"Error serializing position_details: {e}")
                position_details_safe = {'error': 'Serialization error'}

            # Calculate stop loss and target from position details or defaults
            # Convert futures_price to Decimal for calculations
            futures_price_decimal = Decimal(str(futures_price))
            if direction == 'LONG':
                stop_loss_price = futures_price_decimal * Decimal('0.98')
                target_price = futures_price_decimal * Decimal('1.04')
            elif direction == 'SHORT':
                stop_loss_price = futures_price_decimal * Decimal('1.02')
                target_price = futures_price_decimal * Decimal('0.96')
            else:
                stop_loss_price = futures_price_decimal * Decimal('0.98')
                target_price = futures_price_decimal * Decimal('1.02')

            # Get margin data
            margin_data = position_sizing.get('margin_data', {}) if position_sizing else {}
            sizing_data = position_sizing.get('position', {}) if position_sizing else {}

            recommended_lots = sizing_data.get('recommended_lots', 1)
            margin_required = Decimal(str(sizing_data.get('total_margin_required', 0)))
            margin_available = Decimal(str(margin_data.get('available_margin', 0)))
            margin_per_lot = Decimal(str(margin_data.get('margin_per_lot', 0)))

            # Calculate margin utilization
            margin_utilization = 0
            if margin_available > 0:
                margin_utilization = (margin_required / margin_available) * 100

            # Calculate max profit and loss
            lot_size = contract.lot_size if contract else 0
            max_loss_value = abs(futures_price_decimal - stop_loss_price) * lot_size * recommended_lots
            max_profit_value = abs(target_price - futures_price_decimal) * lot_size * recommended_lots

            suggestion = TradeSuggestion.objects.create(
                user=request.user,
                strategy='icici_futures',
                suggestion_type='FUTURES',
                instrument=stock_symbol,
                direction=direction.upper(),
                # Market Data
                spot_price=Decimal(str(spot_price)),
                expiry_date=expiry_dt.date(),
                days_to_expiry=(expiry_dt.date() - datetime.now().date()).days,
                # Position Sizing
                recommended_lots=recommended_lots,
                margin_required=margin_required,
                margin_available=margin_available,
                margin_per_lot=margin_per_lot,
                margin_utilization=Decimal(str(margin_utilization)),
                # Risk Metrics
                max_profit=max_profit_value,
                max_loss=max_loss_value,
                breakeven_upper=target_price if direction == 'LONG' else None,
                breakeven_lower=stop_loss_price if direction == 'LONG' else None,
                # Complete Data
                algorithm_reasoning=algorithm_reasoning_safe,
                position_details=position_details_safe,
                # Expiry: 24 hours from now
                expires_at=timezone.now() + timedelta(hours=24)
            )

            logger.info(f"Saved futures trade suggestion #{suggestion.id} for {request.user.username} - {stock_symbol}")

            # Add suggestion_id to response
            response_data['suggestion_id'] = suggestion.id

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in verify_future_trade: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
