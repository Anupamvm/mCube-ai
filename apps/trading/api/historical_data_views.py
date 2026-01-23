"""
Historical Data API Views

Endpoints for fetching historical OHLC data from Breeze API
and storing it in the database.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.brokers.models import HistoricalPrice
from apps.brokers.integrations.breeze import get_breeze_client
from apps.brokers.exceptions import BreezeAuthenticationError, BreezeAPIError

logger = logging.getLogger(__name__)


@login_required
@csrf_exempt
@require_http_methods(["POST", "GET"])
def get_breeze_historical_data(request):
    """
    Fetch historical OHLC data from Breeze API and save to database.

    This endpoint fetches historical data for stocks, futures, or options,
    deletes any existing data for the same instrument, and saves fresh data.

    Request Parameters:
        stock_code (str, required): Stock/instrument code (e.g., 'ITC', 'RELIND', 'NIFTY')
        exchange_code (str, optional): Exchange code - 'NSE', 'NFO', 'BSE' (default: 'NSE')
        from_date (str, required): Start date in YYYY-MM-DD format
        to_date (str, required): End date in YYYY-MM-DD format
        interval (str, optional): Candle interval - '1minute', '5minute', '30minute', '1day' (default: '1day')
        product_type (str, optional): 'cash', 'futures', 'options', 'btst', 'margin' (default: 'cash')

        # F&O Specific (required for futures/options):
        expiry_date (str, optional): Expiry date in YYYY-MM-DD format (required for futures/options)

        # Options Specific (required for options):
        strike_price (float, optional): Strike price (required for options)
        right (str, optional): 'call', 'put', 'others' (required for options)

    Response Format:
        Success:
        {
            "success": true,
            "message": "Successfully fetched and saved 100 candles",
            "data": {
                "stock_code": "ITC",
                "exchange_code": "NSE",
                "product_type": "cash",
                "interval": "1day",
                "from_date": "2025-01-01",
                "to_date": "2025-01-23",
                "deleted_count": 95,
                "created_count": 100,
                "candles": [...]  # Array of OHLC data
            }
        }

        Error:
        {
            "success": false,
            "error": "Error message describing what went wrong",
            "details": {...}  # Additional error context
        }

    Examples:
        1. Fetch stock data (cash):
        POST /api/get-breeze-historical-data/
        {
            "stock_code": "ITC",
            "exchange_code": "NSE",
            "from_date": "2025-01-01",
            "to_date": "2025-01-23",
            "interval": "1day"
        }

        2. Fetch futures data:
        POST /api/get-breeze-historical-data/
        {
            "stock_code": "NIFTY",
            "exchange_code": "NFO",
            "product_type": "futures",
            "expiry_date": "2025-01-30",
            "from_date": "2025-01-01",
            "to_date": "2025-01-23",
            "interval": "5minute"
        }

        3. Fetch options data:
        POST /api/get-breeze-historical-data/
        {
            "stock_code": "NIFTY",
            "exchange_code": "NFO",
            "product_type": "options",
            "expiry_date": "2025-01-30",
            "strike_price": 24500,
            "right": "call",
            "from_date": "2025-01-20",
            "to_date": "2025-01-23",
            "interval": "1minute"
        }
    """
    try:
        # Get parameters from request (support both POST and GET)
        if request.method == 'POST':
            import json
            try:
                params = json.loads(request.body)
            except json.JSONDecodeError:
                params = request.POST.dict()
        else:
            params = request.GET.dict()

        # ===== PARAMETER VALIDATION =====

        # Required parameters
        stock_code = params.get('stock_code', '').strip().upper()
        from_date_str = params.get('from_date', '').strip()
        to_date_str = params.get('to_date', '').strip()

        if not stock_code:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: stock_code',
                'details': 'Please provide the stock/instrument code (e.g., ITC, NIFTY)'
            }, status=400)

        if not from_date_str:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: from_date',
                'details': 'Please provide from_date in YYYY-MM-DD format'
            }, status=400)

        if not to_date_str:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: to_date',
                'details': 'Please provide to_date in YYYY-MM-DD format'
            }, status=400)

        # Optional parameters with defaults
        exchange_code = params.get('exchange_code', 'NSE').strip().upper()
        interval = params.get('interval', '1day').strip().lower()
        product_type = params.get('product_type', 'cash').strip().lower()

        # Validate interval
        valid_intervals = ['1minute', '5minute', '30minute', '1day']
        if interval not in valid_intervals:
            return JsonResponse({
                'success': False,
                'error': f'Invalid interval: {interval}',
                'details': f'Allowed values: {", ".join(valid_intervals)}'
            }, status=400)

        # Validate product_type
        valid_product_types = ['cash', 'futures', 'options', 'btst', 'margin']
        if product_type not in valid_product_types:
            return JsonResponse({
                'success': False,
                'error': f'Invalid product_type: {product_type}',
                'details': f'Allowed values: {", ".join(valid_product_types)}'
            }, status=400)

        # Parse dates
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'error': 'Invalid date format',
                'details': 'Dates must be in YYYY-MM-DD format (e.g., 2025-01-23)'
            }, status=400)

        # Validate date range
        if from_date > to_date:
            return JsonResponse({
                'success': False,
                'error': 'Invalid date range',
                'details': 'from_date must be before or equal to to_date'
            }, status=400)

        # Check if date range is too large (limit to 365 days for minute intervals)
        if interval in ['1minute', '5minute', '30minute']:
            max_days = 365
            if (to_date - from_date).days > max_days:
                return JsonResponse({
                    'success': False,
                    'error': f'Date range too large for {interval} interval',
                    'details': f'Maximum {max_days} days allowed for minute intervals'
                }, status=400)

        # F&O specific parameters
        expiry_date = None
        strike_price = None
        right = ''

        if product_type in ['futures', 'options']:
            expiry_date_str = params.get('expiry_date', '').strip()
            if not expiry_date_str:
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required parameter for {product_type}: expiry_date',
                    'details': 'Please provide expiry_date in YYYY-MM-DD format'
                }, status=400)

            try:
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid expiry_date format',
                    'details': 'expiry_date must be in YYYY-MM-DD format (e.g., 2025-01-30)'
                }, status=400)

        if product_type == 'options':
            strike_price_str = params.get('strike_price', '').strip()
            right = params.get('right', '').strip().lower()

            if not strike_price_str:
                return JsonResponse({
                    'success': False,
                    'error': 'Missing required parameter for options: strike_price',
                    'details': 'Please provide strike_price (e.g., 24500)'
                }, status=400)

            if not right:
                return JsonResponse({
                    'success': False,
                    'error': 'Missing required parameter for options: right',
                    'details': 'Please provide right: "call", "put", or "others"'
                }, status=400)

            if right not in ['call', 'put', 'others']:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid right value: {right}',
                    'details': 'Allowed values: "call", "put", "others"'
                }, status=400)

            try:
                strike_price = Decimal(strike_price_str)
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid strike_price',
                    'details': 'strike_price must be a valid number'
                }, status=400)

        # ===== FETCH DATA FROM BREEZE API =====

        logger.info(f"Fetching historical data: {stock_code} {exchange_code} {product_type} "
                   f"{interval} from {from_date} to {to_date}")

        try:
            breeze = get_breeze_client()
        except BreezeAuthenticationError as e:
            return JsonResponse({
                'success': False,
                'error': 'Breeze authentication failed',
                'details': str(e)
            }, status=401)

        # Convert dates to ISO format for Breeze API
        from_date_iso = from_date.strftime('%Y-%m-%dT09:15:00.000Z')
        to_date_iso = to_date.strftime('%Y-%m-%dT15:30:00.000Z')

        # Prepare API parameters
        api_params = {
            'interval': interval,
            'from_date': from_date_iso,
            'to_date': to_date_iso,
            'stock_code': stock_code,
            'exchange_code': exchange_code,
            'product_type': product_type,
        }

        # Add F&O parameters
        if product_type in ['futures', 'options']:
            api_params['expiry_date'] = expiry_date.strftime('%Y-%m-%dT00:00:00.000Z')
        else:
            api_params['expiry_date'] = ''

        if product_type == 'options':
            api_params['right'] = right
            api_params['strike_price'] = str(int(strike_price))
        else:
            api_params['right'] = 'others' if product_type == 'futures' else ''
            api_params['strike_price'] = ''

        logger.info(f"Breeze API parameters: {api_params}")

        # Call Breeze API
        # Note: get_historical_data (v1) doesn't support 'cash' product type
        # Must use get_historical_data_v2 for equity/cash data
        try:
            if product_type == 'cash':
                response = breeze.get_historical_data_v2(**api_params)
            else:
                response = breeze.get_historical_data(**api_params)
        except Exception as e:
            logger.error(f"Breeze API call failed: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to fetch data from Breeze API',
                'details': str(e)
            }, status=500)

        # Check API response
        if not response:
            return JsonResponse({
                'success': False,
                'error': 'Empty response from Breeze API',
                'details': 'No data returned from API'
            }, status=500)

        if response.get('Status') != 200:
            error_msg = response.get('Error', 'Unknown error')
            return JsonResponse({
                'success': False,
                'error': f'Breeze API error: {error_msg}',
                'details': {
                    'status': response.get('Status'),
                    'error': error_msg
                }
            }, status=500)

        # Extract data
        candles = response.get('Success', [])

        if not candles:
            return JsonResponse({
                'success': False,
                'error': 'No data available for the specified parameters',
                'details': 'The API returned no candles for this time period. This could mean:\n'
                          '- Market was closed during this period\n'
                          '- No trades occurred for this instrument\n'
                          '- Invalid instrument/expiry combination'
            }, status=404)

        logger.info(f"Received {len(candles)} candles from Breeze API")

        # ===== SAVE TO DATABASE =====

        try:
            deleted_count, created_count = HistoricalPrice.replace_data(
                stock_code=stock_code,
                exchange_code=exchange_code,
                product_type=product_type,
                interval=interval,
                data_points=candles,
                expiry_date=expiry_date,
                strike_price=strike_price,
                right=right
            )

            logger.info(f"Database update: deleted {deleted_count}, created {created_count} records")

        except Exception as e:
            logger.error(f"Error saving to database: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to save data to database',
                'details': str(e)
            }, status=500)

        # ===== PREPARE RESPONSE =====

        # Build instrument description
        instrument_desc = f"{stock_code} {exchange_code}"
        if product_type == 'options':
            instrument_desc = f"{stock_code} {expiry_date} {strike_price} {right.upper()}"
        elif product_type == 'futures':
            instrument_desc = f"{stock_code} FUT {expiry_date}"

        return JsonResponse({
            'success': True,
            'message': f'Successfully fetched and saved {created_count} candles for {instrument_desc}',
            'data': {
                'instrument': instrument_desc,
                'stock_code': stock_code,
                'exchange_code': exchange_code,
                'product_type': product_type,
                'interval': interval,
                'from_date': from_date_str,
                'to_date': to_date_str,
                'expiry_date': expiry_date.strftime('%Y-%m-%d') if expiry_date else None,
                'strike_price': float(strike_price) if strike_price else None,
                'right': right if right else None,
                'deleted_count': deleted_count,
                'created_count': created_count,
                'candles': candles[:10],  # Return first 10 candles as sample
                'total_candles': len(candles),
                'date_range': {
                    'first': candles[0]['datetime'] if candles else None,
                    'last': candles[-1]['datetime'] if candles else None
                }
            }
        })

    except Exception as e:
        logger.error(f"Unexpected error in get_breeze_historical_data: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'details': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_stored_historical_data(request):
    """
    Retrieve historical data from database.

    Request Parameters:
        stock_code (str, required): Stock/instrument code
        exchange_code (str, optional): Exchange code (default: 'NSE')
        product_type (str, optional): Product type (default: 'cash')
        interval (str, optional): Candle interval (default: '1day')
        limit (int, optional): Number of candles to return (default: 100)

        # F&O parameters (if applicable)
        expiry_date (str, optional): Expiry date in YYYY-MM-DD format
        strike_price (float, optional): Strike price
        right (str, optional): 'call', 'put', 'others'

    Response:
        Success:
        {
            "success": true,
            "data": {
                "candles": [...],
                "count": 100,
                "instrument": "ITC NSE"
            }
        }

        Error:
        {
            "success": false,
            "error": "Error message"
        }
    """
    try:
        stock_code = request.GET.get('stock_code', '').strip().upper()
        exchange_code = request.GET.get('exchange_code', 'NSE').strip().upper()
        product_type = request.GET.get('product_type', 'cash').strip().lower()
        interval = request.GET.get('interval', '1day').strip().lower()
        limit = int(request.GET.get('limit', 100))

        if not stock_code:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: stock_code'
            }, status=400)

        # Parse F&O parameters if provided
        expiry_date = None
        strike_price = None
        right = ''

        if request.GET.get('expiry_date'):
            try:
                expiry_date = datetime.strptime(request.GET.get('expiry_date'), '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid expiry_date format'
                }, status=400)

        if request.GET.get('strike_price'):
            try:
                strike_price = Decimal(request.GET.get('strike_price'))
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid strike_price'
                }, status=400)

        if request.GET.get('right'):
            right = request.GET.get('right').strip().lower()

        # Fetch from database
        queryset = HistoricalPrice.get_latest_data(
            stock_code=stock_code,
            exchange_code=exchange_code,
            product_type=product_type,
            interval=interval,
            expiry_date=expiry_date,
            strike_price=strike_price,
            right=right,
            limit=limit
        )

        candles = []
        for record in queryset:
            candles.append({
                'datetime': record.datetime.strftime('%Y-%m-%d %H:%M:%S'),
                'open': float(record.open),
                'high': float(record.high),
                'low': float(record.low),
                'close': float(record.close),
                'volume': record.volume,
                'open_interest': record.open_interest,
            })

        instrument_desc = f"{stock_code} {exchange_code}"
        if product_type == 'options':
            instrument_desc = f"{stock_code} {expiry_date} {strike_price} {right.upper()}"
        elif product_type == 'futures':
            instrument_desc = f"{stock_code} FUT {expiry_date}"

        return JsonResponse({
            'success': True,
            'data': {
                'instrument': instrument_desc,
                'candles': candles,
                'count': len(candles),
                'stock_code': stock_code,
                'exchange_code': exchange_code,
                'product_type': product_type,
                'interval': interval
            }
        })

    except Exception as e:
        logger.error(f"Error retrieving stored data: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve data',
            'details': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def prepare_historical_data(request):
    """
    Prepare historical data for all instruments related to a token
    before running Verify Trade or Futures Algorithm.

    This endpoint:
    1. Discovers all related instruments (equity, futures, options)
    2. Fetches 365 days of historical data for each
    3. Saves data to the database
    4. Returns a summary of collected data

    Request Parameters:
        stock_symbol (str, required): Stock symbol (e.g., 'HDFCBANK', 'RELIANCE')
        expiry_date (str, required): Expiry date in YYYY-MM-DD format
        force_refresh (bool, optional): Force re-fetch even if recent data exists (default: false)
        include_options (bool, optional): Include options chain data (default: true)

    Response Format:
        Success:
        {
            "success": true,
            "message": "Historical data prepared successfully",
            "data": {
                "stock_symbol": "HDFCBANK",
                "expiry_date": "2025-01-30",
                "data_collection": {
                    "summary": {
                        "total_instruments": 50,
                        "successful": 48,
                        "failed": 2,
                        "total_records_saved": 15000
                    },
                    ...
                },
                "verification": {...},
                "ready_for_analysis": true,
                "execution_time_seconds": 45.2
            }
        }

        Error:
        {
            "success": false,
            "error": "Error message"
        }

    Examples:
        1. Prepare data for HDFCBANK futures:
        POST /api/prepare-historical-data/
        {
            "stock_symbol": "HDFCBANK",
            "expiry_date": "2025-01-30"
        }

        2. Force refresh without options:
        POST /api/prepare-historical-data/
        {
            "stock_symbol": "RELIANCE",
            "expiry_date": "2025-01-30",
            "force_refresh": true,
            "include_options": false
        }
    """
    try:
        import json
        from apps.trading.futures_analyzer import prepare_data_for_analysis

        # Parse request body
        try:
            params = json.loads(request.body)
        except json.JSONDecodeError:
            params = request.POST.dict()

        # Required parameters
        stock_symbol = params.get('stock_symbol', '').strip().upper()
        expiry_date = params.get('expiry_date', '').strip()

        if not stock_symbol:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: stock_symbol',
                'details': 'Please provide the stock symbol (e.g., HDFCBANK, RELIANCE)'
            }, status=400)

        if not expiry_date:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: expiry_date',
                'details': 'Please provide expiry_date in YYYY-MM-DD format'
            }, status=400)

        # Validate expiry_date format
        try:
            datetime.strptime(expiry_date, '%Y-%m-%d')
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid expiry_date format',
                'details': 'expiry_date must be in YYYY-MM-DD format (e.g., 2025-01-30)'
            }, status=400)

        # Optional parameters
        force_refresh = params.get('force_refresh', False)
        if isinstance(force_refresh, str):
            force_refresh = force_refresh.lower() in ('true', '1', 'yes')

        include_options = params.get('include_options', True)
        if isinstance(include_options, str):
            include_options = include_options.lower() in ('true', '1', 'yes')

        logger.info(f"Preparing historical data for {stock_symbol} (expiry: {expiry_date})")
        logger.info(f"Options: force_refresh={force_refresh}, include_options={include_options}")

        # Call the main data preparation function
        result = prepare_data_for_analysis(
            stock_symbol=stock_symbol,
            expiry_date=expiry_date,
            force_refresh=force_refresh,
            include_options=include_options
        )

        if not result.get('success'):
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Data preparation failed'),
                'details': result
            }, status=500)

        # Build response
        response_data = {
            'success': True,
            'message': 'Historical data prepared successfully',
            'data': {
                'stock_symbol': stock_symbol,
                'expiry_date': expiry_date,
                'ready_for_analysis': result.get('ready_for_analysis', False),
                'data_collection': result.get('data_collection'),
                'verification': result.get('verification'),
            }
        }

        # Add execution time if available
        if result.get('data_collection') and result['data_collection'].get('execution_time_seconds'):
            response_data['data']['execution_time_seconds'] = result['data_collection']['execution_time_seconds']

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Unexpected error in prepare_historical_data: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Internal server error',
            'details': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_related_instruments(request):
    """
    Discover all related instruments for a given stock/token.

    This endpoint returns a list of all instruments that would be
    affected by or correlated with the given token, including:
    - Underlying equity
    - Futures contracts (current + next expiry)
    - Options chain (all strikes for current + next expiry)

    Request Parameters:
        stock_symbol (str, required): Stock symbol (e.g., 'HDFCBANK')
        expiry_date (str, required): Expiry date in YYYY-MM-DD format

    Response:
        {
            "success": true,
            "data": {
                "stock_symbol": "HDFCBANK",
                "equity": {...},
                "futures": [...],
                "options": [...],
                "expiries": ["2025-01-30", "2025-02-27"],
                "total_instruments": 150
            }
        }
    """
    try:
        from apps.trading.futures_analyzer import get_related_instruments as discover_instruments

        stock_symbol = request.GET.get('stock_symbol', '').strip().upper()
        expiry_date = request.GET.get('expiry_date', '').strip()

        if not stock_symbol:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: stock_symbol'
            }, status=400)

        if not expiry_date:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: expiry_date'
            }, status=400)

        # Validate expiry_date format
        try:
            datetime.strptime(expiry_date, '%Y-%m-%d')
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid expiry_date format (use YYYY-MM-DD)'
            }, status=400)

        result = discover_instruments(stock_symbol, expiry_date)

        if not result.get('success'):
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Failed to discover instruments')
            }, status=500)

        return JsonResponse({
            'success': True,
            'data': result
        })

    except Exception as e:
        logger.error(f"Error in get_related_instruments: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to discover instruments',
            'details': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def verify_historical_data(request):
    """
    Verify and analyze collected historical data for a token.

    NOTE: This is currently a placeholder that will be implemented
    to perform analysis on the collected historical data.

    Request Parameters:
        stock_symbol (str, required): Stock symbol
        expiry_date (str, required): Expiry date in YYYY-MM-DD format

    Response:
        {
            "success": true,
            "data": {
                "status": "PLACEHOLDER",
                "planned_features": [...]
            }
        }
    """
    try:
        import json
        from apps.trading.futures_analyzer import verify_historical_data as verify_data

        try:
            params = json.loads(request.body)
        except json.JSONDecodeError:
            params = request.POST.dict()

        stock_symbol = params.get('stock_symbol', '').strip().upper()
        expiry_date = params.get('expiry_date', '').strip()

        if not stock_symbol:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: stock_symbol'
            }, status=400)

        if not expiry_date:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameter: expiry_date'
            }, status=400)

        result = verify_data(stock_symbol, expiry_date)

        return JsonResponse({
            'success': True,
            'data': result
        })

    except Exception as e:
        logger.error(f"Error in verify_historical_data: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Verification failed',
            'details': str(e)
        }, status=500)
