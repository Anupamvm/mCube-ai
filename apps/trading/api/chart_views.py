"""
Chart Data API Views

Provides API endpoints for fetching chart data:
1. Suggestion-based: /api/chart-data/<suggestion_id>/
2. Contract-based: /api/chart-data/contract/ (POST with symbol, price, markers)

Used by suggestion detail page and manual triggers (Verify Trade, Strangle, Iron Condor).
"""

import json
import logging
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

from apps.trading.services.chart_data_service import (
    get_chart_data_for_suggestion,
    get_chart_data_for_contract
)

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def get_chart_data(request, suggestion_id: int):
    """
    Get chart data for a trade suggestion.

    Query params:
    - days: Number of days (1, 5, 30, 90, 180, 365, 1825). Default: 90

    Returns JSON with:
    - historical: OHLCV data (daily or intraday based on days param)
    - moving_averages: 20/50/100/200 DMA series (only for daily data)
    - support_resistance: S1-S3, R1-R3 from ConsolidatedSRCalculator
    - oi_distribution: OI by strike from ContractData
    - trade_markers: entry/SL/target for futures, strikes/breakeven for strangle
    - vix: current India VIX with status

    Args:
        request: HTTP request
        suggestion_id: ID of the TradeSuggestion

    Returns:
        JsonResponse with chart data
    """
    try:
        # Get days parameter from query string
        days = request.GET.get('days', 90)
        try:
            days = int(days)
        except (ValueError, TypeError):
            days = 90

        # Map days to appropriate intervals
        duration_config = {
            1: {'interval': '5minute', 'label': '1D'},
            5: {'interval': '5minute', 'label': '5D'},
            30: {'interval': '5minute', 'label': '1M'},
            90: {'interval': '1day', 'label': '3M'},
            180: {'interval': '1day', 'label': '6M'},
            365: {'interval': '1day', 'label': '1Y'},
            1825: {'interval': '1day', 'label': '5Y'},
        }

        if days not in duration_config:
            days = 90

        interval = duration_config[days]['interval']

        logger.info(f"Chart data requested for suggestion {suggestion_id}, days={days}, interval={interval}")

        chart_data = get_chart_data_for_suggestion(suggestion_id, days=days, interval=interval)

        if not chart_data.get('success'):
            return JsonResponse(chart_data, status=404)

        return JsonResponse(chart_data)

    except Exception as e:
        logger.error(f"Error in get_chart_data: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def get_contract_chart_data(request):
    """
    Get chart data for a contract (without suggestion).

    Used by manual triggers (Verify Trade, Strangle, Iron Condor).

    Request body (JSON):
        {
            "symbol": "NIFTY",
            "current_price": 23456.50,
            "chart_type": "futures" | "strangle" | "iron_condor",
            "trade_markers": {
                // For futures:
                "entry_price": 23456,
                "stop_loss": 23200,
                "target": 23800,
                "direction": "LONG"

                // For strangle:
                "entry_price": 23456,
                "call_strike": 23600,
                "put_strike": 23000,
                "breakeven_upper": 23700,
                "breakeven_lower": 22900

                // For iron_condor:
                "entry_price": 23456,
                "sold_call": 23600,
                "bought_call": 23800,
                "sold_put": 23000,
                "bought_put": 22800,
                "breakeven_upper": 23700,
                "breakeven_lower": 22900
            }
        }

    Returns:
        JsonResponse with chart data
    """
    try:
        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body'
            }, status=400)

        # Validate required fields
        symbol = data.get('symbol')
        current_price = data.get('current_price')

        if not symbol:
            return JsonResponse({
                'success': False,
                'error': 'symbol is required'
            }, status=400)

        if not current_price:
            return JsonResponse({
                'success': False,
                'error': 'current_price is required'
            }, status=400)

        chart_type = data.get('chart_type', 'futures')
        trade_markers = data.get('trade_markers', {})
        days = data.get('days', 90)  # Default 3 months

        # Map days to appropriate intervals
        # Short durations (1D, 5D, 1M) use 5-minute intervals for intraday data
        # Longer durations use daily intervals
        duration_config = {
            1: {'interval': '5minute', 'label': '1D'},      # 1 day - 5 min candles
            5: {'interval': '5minute', 'label': '5D'},      # 5 days - 5 min candles
            30: {'interval': '5minute', 'label': '1M'},     # 1 month - 5 min candles
            90: {'interval': '1day', 'label': '3M'},        # 3 months - daily candles
            180: {'interval': '1day', 'label': '6M'},       # 6 months - daily candles
            365: {'interval': '1day', 'label': '1Y'},       # 1 year - daily candles
            1825: {'interval': '1day', 'label': '5Y'},      # 5 years - daily candles
        }

        # Validate and get interval
        if days not in duration_config:
            days = 90  # Default to 3 months if invalid

        interval = duration_config[days]['interval']

        logger.info(f"Contract chart data requested for {symbol} ({chart_type}), days={days}, interval={interval}")

        chart_data = get_chart_data_for_contract(
            symbol=symbol,
            current_price=float(current_price),
            chart_type=chart_type,
            trade_markers=trade_markers,
            days=days,
            interval=interval
        )

        if not chart_data.get('success'):
            return JsonResponse(chart_data, status=400)

        return JsonResponse(chart_data)

    except Exception as e:
        logger.error(f"Error in get_contract_chart_data: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
