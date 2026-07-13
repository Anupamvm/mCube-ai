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
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from apps.positions.services.sr_exit_engine import compute_initial_sl_target

logger = logging.getLogger(__name__)


def get_historical_news_analysis(stock_symbol: str, stock_name: str = None, industry_name: str = None, limit: int = 5):
    """
    Fetch historical news analysis from database for a stock.

    Returns top 5 most impactful (negative) articles that could affect trading decisions.

    Args:
        stock_symbol: Stock symbol to search for
        stock_name: Optional stock name for broader search
        industry_name: Optional industry name for sector news
        limit: Max articles to return (default: 5)

    Returns:
        Dict with historical_articles list and summary
    """
    from apps.data.models import NewsArticle
    from django.db.models import Q
    from datetime import timedelta
    from django.utils import timezone
    from django.conf import settings

    try:
        # Look back 7 days for relevant news
        cutoff_date = timezone.now() - timedelta(days=7)

        # Build query for stock-related news
        query = Q(published_at__gte=cutoff_date) & Q(processed=True)

        # Check if using PostgreSQL (supports __contains on JSONField)
        db_engine = settings.DATABASES['default']['ENGINE']
        is_postgres = 'postgresql' in db_engine

        if is_postgres:
            # PostgreSQL supports __contains on JSONField arrays
            symbol_filter = Q(symbols_mentioned__contains=[stock_symbol])
            keyword_filter = Q(search_keywords__contains=[stock_symbol])
            if stock_name:
                keyword_filter |= Q(search_keywords__contains=[stock_name])

            # Combine filters - get stock-specific news
            articles = NewsArticle.objects.filter(
                query & (symbol_filter | keyword_filter)
            ).exclude(
                sentiment_score__isnull=True
            ).order_by('sentiment_score')[:limit * 2]

            # If not enough stock-specific news, include industry news
            if len(articles) < limit and industry_name:
                industry_articles = NewsArticle.objects.filter(
                    query & Q(sectors_mentioned__contains=[industry_name])
                ).exclude(
                    sentiment_score__isnull=True
                ).exclude(
                    id__in=[a.id for a in articles]
                ).order_by('sentiment_score')[:limit]

                articles = list(articles) + list(industry_articles)
        else:
            # SQLite fallback: use __icontains on text representation
            # This searches for the symbol as a substring in the JSON field
            symbol_filter = Q(symbols_mentioned__icontains=stock_symbol)
            keyword_filter = Q(search_keywords__icontains=stock_symbol)
            if stock_name:
                keyword_filter |= Q(search_keywords__icontains=stock_name)

            # Combine filters - get stock-specific news
            articles = NewsArticle.objects.filter(
                query & (symbol_filter | keyword_filter)
            ).exclude(
                sentiment_score__isnull=True
            ).order_by('sentiment_score')[:limit * 2]

            # If not enough stock-specific news, include industry news
            if len(articles) < limit and industry_name:
                industry_articles = NewsArticle.objects.filter(
                    query & Q(sectors_mentioned__icontains=industry_name)
                ).exclude(
                    sentiment_score__isnull=True
                ).exclude(
                    id__in=[a.id for a in articles]
                ).order_by('sentiment_score')[:limit]

                articles = list(articles) + list(industry_articles)

        # Also include high-impact market news
        market_articles = NewsArticle.objects.filter(
            query & Q(news_type='MARKET') & Q(sentiment_score__lt=-0.3)
        ).exclude(
            id__in=[a.id for a in articles]
        ).order_by('sentiment_score')[:3]

        articles = list(articles) + list(market_articles)

        # Sort by impact (most negative first) and take top N
        articles = sorted(articles, key=lambda x: x.sentiment_score or 0)[:limit]

        # Build response
        historical_articles = []
        for article in articles:
            historical_articles.append({
                'title': article.title,
                'url': article.url,
                'source': article.source,
                'published_at': article.published_at.isoformat() if article.published_at else None,
                'impact_score': article.sentiment_score or 0,
                'impact_label': article.impact_analysis.get('impact_label', 'NEUTRAL') if article.impact_analysis else 'NEUTRAL',
                'impact_reasoning': article.impact_reasoning or article.impact_analysis.get('impact_reasoning', '') if article.impact_analysis else '',
                'market_direction': article.market_direction or 'NEUTRAL',
                'news_type': article.news_type or 'STOCK',
                'category': article.impact_category or article.category or '',
                'could_block_trade': (article.sentiment_score or 0) <= -0.6
            })

        # Calculate summary
        blocking_count = len([a for a in historical_articles if a['could_block_trade']])
        negative_count = len([a for a in historical_articles if a['impact_score'] < -0.3])
        avg_score = sum(a['impact_score'] for a in historical_articles) / len(historical_articles) if historical_articles else 0

        return {
            'success': True,
            'articles': historical_articles,
            'summary': {
                'total_articles': len(historical_articles),
                'blocking_count': blocking_count,
                'negative_count': negative_count,
                'average_score': round(avg_score, 3),
                'days_analyzed': 7
            }
        }

    except Exception as e:
        logger.warning(f"[Historical News] Error fetching historical news: {e}")
        return {
            'success': False,
            'articles': [],
            'summary': {},
            'error': str(e)
        }


def get_historical_market_news(limit: int = 5):
    """
    Fetch historical market news analysis from database.

    Returns top 5 most impactful market news articles that could affect trading decisions.

    Args:
        limit: Max articles to return (default: 5)

    Returns:
        Dict with articles list and summary
    """
    from apps.data.models import NewsArticle
    from datetime import timedelta
    from django.utils import timezone

    try:
        # Look back 7 days for relevant market news
        cutoff_date = timezone.now() - timedelta(days=7)

        # Get market news with impact analysis
        articles = NewsArticle.objects.filter(
            published_at__gte=cutoff_date,
            news_type='MARKET',
            processed=True
        ).exclude(
            sentiment_score__isnull=True
        ).order_by('sentiment_score')[:limit]

        # Build response
        historical_articles = []
        for article in articles:
            historical_articles.append({
                'title': article.title,
                'url': article.url,
                'source': article.source,
                'published_at': article.published_at.isoformat() if article.published_at else None,
                'impact_score': article.sentiment_score or 0,
                'impact_label': article.impact_analysis.get('impact_label', 'NEUTRAL') if article.impact_analysis else 'NEUTRAL',
                'impact_reasoning': article.impact_reasoning or '',
                'market_direction': article.market_direction or 'NEUTRAL',
                'category': article.impact_category or '',
                'could_block_trade': (article.sentiment_score or 0) <= -0.6
            })

        # Calculate summary
        blocking_count = len([a for a in historical_articles if a['could_block_trade']])
        negative_count = len([a for a in historical_articles if a['impact_score'] < -0.3])
        avg_score = sum(a['impact_score'] for a in historical_articles) / len(historical_articles) if historical_articles else 0

        return {
            'success': True,
            'articles': historical_articles,
            'summary': {
                'total_articles': len(historical_articles),
                'blocking_count': blocking_count,
                'negative_count': negative_count,
                'average_score': round(avg_score, 3),
                'days_analyzed': 7
            }
        }

    except Exception as e:
        logger.warning(f"[Historical Market News] Error: {e}")
        return {
            'success': False,
            'articles': [],
            'summary': {}
        }


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

        # Calculate date ranges — use 65 days to ensure the far-month expiry (last Thursday of
        # the month after next) always falls within the window regardless of month length.
        this_month_end = today + timedelta(days=30)
        next_month_start = today + timedelta(days=30)
        next_month_end = today + timedelta(days=65)

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
        from apps.trading.futures_analyzer import enhanced_futures_analysis
        from apps.data.models import ContractData
        from apps.brokers.utils.security_master import update_security_master

        # Ensure SecurityMaster is current before verification
        sm_update = update_security_master(force=False)
        if sm_update.get('updated'):
            logger.info(f"SecurityMaster updated before verification: {sm_update.get('message')}")
        elif sm_update.get('error'):
            logger.warning(f"SecurityMaster update failed: {sm_update.get('error')} - continuing with existing file")

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

        # ===== RESULT CACHE & IN-PROGRESS LOCK =====
        # Caching prevents duplicate simultaneous analyses for the same contract
        # (parallel tabs, concurrent API calls, SQLite write contention).
        from django.core.cache import cache as _ac
        _result_key = f'analysis_result_{stock_symbol}_{expiry_date}'
        _lock_key = f'analysis_in_progress_{stock_symbol}_{expiry_date}'

        _cached = _ac.get(_result_key)
        if _cached:
            logger.info(f"Returning cached analysis for {stock_symbol} {expiry_date}")
            return JsonResponse({**_cached, 'from_cache': True})

        # atomic add() — succeeds only once; prevents second identical request from
        # spawning a duplicate 90-second analysis while the first is still running
        if not _ac.add(_lock_key, '1', timeout=180):
            logger.info(f"Analysis in progress for {stock_symbol} {expiry_date}, polling for result...")
            import time as _sleep_mod
            for _ in range(18):
                _sleep_mod.sleep(5)
                _cached = _ac.get(_result_key)
                if _cached:
                    return JsonResponse({**_cached, 'from_cache': True})
            return JsonResponse({
                'success': False,
                'error': 'Analysis already in progress for this contract. Please retry in a moment.',
                'symbol': stock_symbol,
                'expiry_date': expiry_date,
            })

        logger.info(f"Manual verification: {stock_symbol} expiry {expiry_date}")

        # Get contract details from Trendlyne
        contract = ContractData.objects.filter(
            symbol=stock_symbol,
            option_type='FUTURE',
            expiry=expiry_date
        ).first()

        # Detect market regime before analysis so it feeds into scoring
        try:
            from apps.strategies.services.market_regime import get_market_regime
            regime_data = get_market_regime('NIFTY')
            regime = regime_data.get('regime', 'NORMAL')
        except Exception:
            logger.warning("Market regime detection failed, using NORMAL")
            regime = 'NORMAL'

        # Run enhanced futures analysis (13-component scoring with hard reject filters)
        analysis_result = enhanced_futures_analysis(
            stock_symbol=stock_symbol,
            expiry_date=expiry_date,
            contract=contract,
            regime=regime,
        )

        if not analysis_result.get('success'):
            # Remove failed recommendations so they don't appear on next page load
            removed_count = 0
            try:
                from apps.trading.models import TradeSuggestion
                removed_count, _ = TradeSuggestion.objects.filter(
                    user=request.user,
                    instrument=stock_symbol,
                    strategy='icici_futures',
                    expiry_date=expiry_date,
                    status='SUGGESTED',
                ).delete()
                if removed_count:
                    logger.info(f"Removed {removed_count} failed TradeSuggestion(s) for {stock_symbol} expiry {expiry_date}")
            except Exception as del_err:
                logger.warning(f"Failed to remove TradeSuggestion for {stock_symbol}: {del_err}")

            return JsonResponse({
                'success': False,
                'error': analysis_result.get('error', f'Unable to analyze {stock_symbol}. Stock may not be available for F&O or data is missing.'),
                'execution_log': analysis_result.get('execution_log', []),
                'removed': removed_count > 0,
                'symbol': stock_symbol,
                'expiry_date': expiry_date,
            })

        # ===== HISTORICAL DATA COLLECTION & VERIFICATION =====
        # Use prepare_data_for_analysis which handles the complete flow:
        # 1. Check if recent data exists (< 5 minutes old)
        # 2. If not, discover related instruments and fetch historical data
        # 3. Save data to HistoricalPrice model
        # 4. Run verification/risk checks on the data
        from apps.trading.futures_analyzer import prepare_data_for_analysis

        logger.info(f"Preparing historical data for {stock_symbol} (expiry: {expiry_date})")

        try:
            data_prep_result = prepare_data_for_analysis(
                stock_symbol=stock_symbol,
                expiry_date=expiry_date,
                force_refresh=False,  # Use cached data if < 5 minutes old
                include_options=False  # Skip options for faster verification
            )

            if data_prep_result.get('success'):
                # Log collection summary
                data_collection = data_prep_result.get('data_collection', {})
                if data_collection.get('skipped'):
                    logger.info(f"Historical data: Using cached data ({data_collection.get('reason', 'recent')})")
                else:
                    summary = data_collection.get('summary', {})
                    logger.info(f"Historical data collected: {summary.get('total_records_saved', 0)} records "
                               f"({summary.get('successful', 0)}/{summary.get('total_instruments', 0)} instruments)")

                    # Log equity result for debugging
                    equity_result = data_collection.get('equity_result', {})
                    if equity_result:
                        if equity_result.get('success'):
                            logger.info(f"Equity: {equity_result.get('records_saved', 0)} records")
                        else:
                            logger.warning(f"Equity failed: {equity_result.get('error', equity_result.get('note', 'Unknown'))}")

                # Get verification result
                historical_verification = data_prep_result.get('verification', {})
                logger.info(f"Historical verification: {historical_verification.get('verdict', 'N/A')} "
                           f"(ready_for_analysis={data_prep_result.get('ready_for_analysis', False)})")
            else:
                logger.error(f"Data preparation failed: {data_prep_result.get('error')}")
                # Create a blocked verification result
                historical_verification = {
                    'success': False,
                    'trade_allowed': False,
                    'verdict': 'BLOCKED',
                    'verdict_message': f"Data preparation failed: {data_prep_result.get('error', 'Unknown error')}",
                    'risk_checks': [{
                        'id': 'data_prep_failed',
                        'name': 'Data Preparation Failed',
                        'description': 'Failed to prepare historical data for analysis',
                        'status': 'FAIL',
                        'severity': 'HIGH',
                        'value': 'Failed',
                        'threshold': 'Success Required',
                        'message': data_prep_result.get('error', 'Unknown error')
                    }],
                    'risk_summary': {'total_checks': 1, 'passed': 0, 'failed': 1, 'warnings': 0, 'pass_rate': 0},
                    'recommendations': ['Check Breeze API connectivity and try again']
                }

        except Exception as prep_error:
            logger.error(f"Error in data preparation: {prep_error}", exc_info=True)
            historical_verification = {
                'success': False,
                'trade_allowed': False,
                'verdict': 'BLOCKED',
                'verdict_message': f"Data preparation error: {str(prep_error)}",
                'risk_checks': [{
                    'id': 'data_prep_error',
                    'name': 'Data Preparation Error',
                    'description': 'Exception during historical data preparation',
                    'status': 'FAIL',
                    'severity': 'HIGH',
                    'value': 'Error',
                    'threshold': 'No Errors',
                    'message': str(prep_error)
                }],
                'risk_summary': {'total_checks': 1, 'passed': 0, 'failed': 1, 'warnings': 0, 'pass_rate': 0},
                'recommendations': ['Check server logs for details']
            }

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

        # Determine pass/fail based on analysis verdict AND historical verification
        analysis_passed = analysis_result.get('verdict') == 'PASS'
        historical_passed = historical_verification.get('trade_allowed', True)

        direction = analysis_result.get('direction', 'NEUTRAL')
        composite_score = analysis_result.get('composite_score', 0)

        # Log if historical verification blocked the trade
        if analysis_passed and not historical_passed:
            logger.warning(f"Trade blocked by historical verification for {stock_symbol}")

        # ===== NEWS IMPACT VERIFICATION =====
        # Fetch and analyze news for the stock to check for negative news that could block the trade
        news_verification = {
            'success': False,
            'trade_allowed': True,
            'blocking_articles': [],
            'warning_articles': [],
            'summary': {}
        }

        try:
            from apps.data.services.gnews_client import get_gnews_client
            from apps.data.models import TLStockData
            from apps.llm.services.news_impact_analyzer import get_news_impact_analyzer

            logger.info(f"[Verify Trade] Fetching news for {stock_symbol} ({direction} trade)")

            # Get stock details for news search
            stock_data = TLStockData.objects.filter(nsecode=stock_symbol).first()
            stock_name = stock_data.stock_name if stock_data else stock_symbol
            industry_name = stock_data.industry_name if stock_data else None

            # Fetch stock news (limit to 5 for speed during verification)
            gnews = get_gnews_client()
            stock_news_result = gnews.fetch_stock_news(
                stock_symbol=stock_symbol,
                stock_name=stock_name,
                max_results=5
            )

            # Analyze news impact
            if stock_news_result.get('articles'):
                analyzer = get_news_impact_analyzer()
                impact_result = analyzer.analyze_news_for_trade(
                    stock_news={'articles': stock_news_result.get('articles', [])},
                    industry_news={'articles': []},  # Skip industry/competitor for speed
                    competitor_news={'articles': []},
                    stock_symbol=stock_symbol,
                    stock_name=stock_name,
                    trade_direction=direction,
                    industry_name=industry_name,
                    max_articles_per_category=5
                )

                news_verification = {
                    'success': True,
                    'trade_allowed': impact_result['trade_allowed'],
                    'blocking_articles': impact_result['blocking_articles'],
                    'warning_articles': impact_result['warning_articles'],
                    'summary': impact_result['summary'],
                    'stock_news': impact_result['stock_news']
                }

                logger.info(f"[Verify Trade] News impact: trade_allowed={impact_result['trade_allowed']}, "
                           f"blocking={len(impact_result['blocking_articles'])}, warnings={len(impact_result['warning_articles'])}")
            else:
                logger.info(f"[Verify Trade] No news articles found for {stock_symbol}")
                news_verification['success'] = True

        except Exception as news_error:
            logger.warning(f"[Verify Trade] News verification failed: {news_error}")
            # Don't block trade if news check fails - just log and continue
            news_verification['error'] = str(news_error)

        # Check if news blocks the trade
        news_passed = news_verification.get('trade_allowed', True)
        if analysis_passed and historical_passed and not news_passed:
            logger.warning(f"Trade BLOCKED by negative news for {stock_symbol}")

        # ===== HISTORICAL NEWS ANALYSIS =====
        # Fetch previously analyzed news from database (top 5 most impactful)
        historical_news = get_historical_news_analysis(
            stock_symbol=stock_symbol,
            stock_name=stock_name if 'stock_name' in dir() else None,
            industry_name=industry_name if 'industry_name' in dir() else None,
            limit=5
        )
        logger.info(f"[Verify Trade] Historical news: {len(historical_news.get('articles', []))} articles, "
                   f"blocking={historical_news.get('summary', {}).get('blocking_count', 0)}")

        # ===== ANALYST REPORT VERIFICATION =====
        # Check analyst price targets and recommendations
        # On-demand fetch: If no data or data > 24 hours old, fetch fresh from Trendlyne
        analyst_verification = {
            'success': False,
            'trade_allowed': True,
            'blocking_reasons': [],
            'warnings': [],
            'price_target': None,
            'reports_summary': None,
            'top_blocking_reports': [],
            'recommendation': 'PROCEED',
            'data_source': 'none',
            'fetch_status': 'not_started',
            'debug_info': []
        }

        try:
            from apps.data.models import AnalystPriceTarget, AnalystReport, TLStockData
            from apps.llm.services.analyst_report_aggregator import get_analyst_report_aggregator
            from datetime import timedelta
            from django.utils import timezone

            logger.info(f"[Verify Trade] Checking analyst data for {stock_symbol}")

            # Check if we have fresh analyst data (< 24 hours old)
            stale_cutoff = timezone.now() - timedelta(hours=24)
            existing_price_target = AnalystPriceTarget.objects.filter(
                nse_code__iexact=stock_symbol,
                fetch_timestamp__gte=stale_cutoff
            ).first()

            if existing_price_target:
                # Check if the cached data actually has useful values
                has_useful_data = (
                    existing_price_target.avg_target_price is not None or
                    existing_price_target.analyst_count > 0
                )

                if has_useful_data:
                    logger.info(f"[Verify Trade] Found fresh analyst data for {stock_symbol} (fetched: {existing_price_target.fetch_timestamp})")
                    analyst_verification['data_source'] = 'cache'
                    analyst_verification['fetch_status'] = 'using_cache'
                    analyst_verification['debug_info'].append(f"Using cached data from {existing_price_target.fetch_timestamp}")
                    analyst_verification['debug_info'].append(f"Target: {existing_price_target.avg_target_price}, Analysts: {existing_price_target.analyst_count}")

                    # Sanity-check cached upside against the live spot price.
                    # The scraper sometimes latches onto a non-LTP value for current_price
                    # (e.g. ₹180,000 instead of ₹1,800 for Divis Labs), producing a bogus
                    # stored upside like -99%.  When the cached current_price diverges >20%
                    # from the live spot, recompute upside from avg_target_price + spot and
                    # persist the correction so the aggregator (below) reads the right value.
                    if (spot_price and existing_price_target.avg_target_price and
                            existing_price_target.current_price):
                        stored_current = float(existing_price_target.current_price)
                        target_price_f = float(existing_price_target.avg_target_price)
                        spot_f = float(spot_price)
                        if spot_f > 0:
                            cached_divergence = abs(stored_current - spot_f) / spot_f
                            if cached_divergence > 0.20:
                                corrected_upside = round((target_price_f - spot_f) / spot_f * 100, 2)
                                old_upside = float(existing_price_target.upside_pct) if existing_price_target.upside_pct else None
                                existing_price_target.current_price = spot_f
                                existing_price_target.upside_pct = corrected_upside
                                existing_price_target.save(update_fields=['current_price', 'upside_pct'])
                                logger.warning(
                                    f"[Verify Trade] {stock_symbol}: cached current ₹{stored_current:.0f} "
                                    f"diverges {cached_divergence*100:.0f}% from spot ₹{spot_f:.0f}; "
                                    f"corrected upside {old_upside}% → {corrected_upside}%"
                                )
                                analyst_verification['debug_info'].append(
                                    f"Corrected stale current ₹{stored_current:.0f} → spot ₹{spot_f:.0f}, "
                                    f"upside: {old_upside}% → {corrected_upside}%"
                                )
                else:
                    # Cached record exists but has no useful data - treat as no data
                    logger.warning(f"[Verify Trade] Cached data for {stock_symbol} has no useful values, will re-fetch")
                    analyst_verification['debug_info'].append("Cached record has empty values, treating as no data")
                    existing_price_target = None  # Force re-fetch
            else:
                # No fresh data - fetch from Trendlyne
                logger.info(f"[Verify Trade] No fresh analyst data for {stock_symbol}, fetching from Trendlyne...")
                analyst_verification['data_source'] = 'fresh_fetch'
                analyst_verification['fetch_status'] = 'fetching'
                analyst_verification['debug_info'].append("No cached data found, fetching from Trendlyne")

                # Get trendlyne_id from TLStockData if available
                tl_stock = TLStockData.objects.filter(nsecode__iexact=stock_symbol).first()
                trendlyne_id = tl_stock.trendlyne_id if tl_stock else None
                analyst_verification['debug_info'].append(f"TLStockData found: {tl_stock is not None}, trendlyne_id: {trendlyne_id}")

                try:
                    from apps.data.providers.trendlyne import TrendlyneProvider

                    analyst_verification['debug_info'].append("Initializing TrendlyneProvider...")
                    logger.info(f"[Verify Trade] Initializing TrendlyneProvider for {stock_symbol}")

                    with TrendlyneProvider() as provider:
                        # Initialize driver and login
                        analyst_verification['debug_info'].append("Initializing Chrome driver...")
                        provider.init_driver()
                        analyst_verification['debug_info'].append("Chrome driver initialized, attempting login...")
                        logger.info(f"[Verify Trade] Chrome driver initialized, attempting Trendlyne login...")

                        login_success = provider.login()
                        analyst_verification['debug_info'].append(f"Login result: {login_success}")
                        logger.info(f"[Verify Trade] Trendlyne login result: {login_success}")

                        if login_success:
                            logger.info(f"[Verify Trade] Logged into Trendlyne, fetching analyst data for {stock_symbol}")

                            # Fetch analyst data (price targets + reports)
                            fetch_result = provider.fetch_analyst_data(
                                symbol=stock_symbol,
                                trendlyne_id=trendlyne_id,
                                months_back=3,
                                download_pdfs=False  # Skip PDF download for speed during verification
                            )

                            analyst_verification['debug_info'].append(f"Fetch result success: {fetch_result.get('success')}")
                            if fetch_result.get('success'):
                                analyst_verification['fetch_status'] = 'fetch_success'
                                # Extract trendlyne_id if we got it
                                extracted_id = fetch_result.get('trendlyne_id')

                                # Update TLStockData with trendlyne_id if found
                                if extracted_id and tl_stock and not tl_stock.trendlyne_id:
                                    tl_stock.trendlyne_id = extracted_id
                                    tl_stock.save()
                                    logger.info(f"[Verify Trade] Saved trendlyne_id {extracted_id} for {stock_symbol}")

                                # Save price target data
                                price_target_data = fetch_result.get('price_target', {})
                                logger.info(f"[Verify Trade] Price target fetch result: {price_target_data}")
                                analyst_verification['debug_info'].append(
                                    f"Fetched price target: Current=₹{price_target_data.get('current_price')}, "
                                    f"Target=₹{price_target_data.get('avg_target_price')}, "
                                    f"Upside={price_target_data.get('upside_pct')}%, "
                                    f"Analysts={price_target_data.get('analyst_count')} "
                                    f"(SB:{price_target_data.get('strong_buy_count')}, B:{price_target_data.get('buy_count')}, "
                                    f"H:{price_target_data.get('hold_count')}, S:{price_target_data.get('sell_count')}, SS:{price_target_data.get('strong_sell_count')})"
                                )

                                # Check if we have any useful data
                                has_price_data = price_target_data.get('avg_target_price') is not None
                                has_analyst_data = price_target_data.get('analyst_count', 0) > 0
                                has_upside_data = price_target_data.get('upside_pct') is not None

                                if has_price_data or has_analyst_data or has_upside_data:
                                    # Trust live broker spot over scraped LTP. If scraped current
                                    # diverges >20% from spot, the scraper latched onto a non-LTP
                                    # rupee value (market cap, 52W high, etc.). When that happens
                                    # and the scraped target was internally derived from the bogus
                                    # current (i.e. target ≈ current × (1+upside/100)), target is
                                    # bogus too — reconstruct from spot × (1+upside) instead.
                                    scraped_current = price_target_data.get('current_price')
                                    scraped_target = price_target_data.get('avg_target_price')
                                    scraped_upside = price_target_data.get('upside_pct')
                                    final_current = scraped_current
                                    final_target = scraped_target
                                    final_upside = scraped_upside

                                    spot_f = float(spot_price) if spot_price else None
                                    if spot_f and scraped_current:
                                        divergence = abs(scraped_current - spot_f) / spot_f
                                        if divergence > 0.20:
                                            # Detect whether scraped target was derived from the
                                            # bogus current (internally consistent scrape).
                                            target_derived_from_current = False
                                            if scraped_target and scraped_upside is not None and scraped_current:
                                                implied_upside = (scraped_target - scraped_current) / scraped_current * 100
                                                if abs(implied_upside - scraped_upside) < 2.0:
                                                    target_derived_from_current = True

                                            final_current = spot_f
                                            if target_derived_from_current and scraped_upside is not None:
                                                # Scraped upside ("upside is X%") is still the
                                                # trustworthy signal — rebuild target from it.
                                                final_target = round(spot_f * (1 + scraped_upside / 100), 2)
                                                final_upside = scraped_upside
                                                logger.warning(
                                                    f"[Verify Trade] {stock_symbol}: scraped current ₹{scraped_current} "
                                                    f"diverges {divergence*100:.1f}% from spot ₹{spot_f}; scraped target "
                                                    f"was derived from bogus current — rebuilding target from spot × "
                                                    f"(1+{scraped_upside}%) = ₹{final_target}"
                                                )
                                            elif scraped_target:
                                                # Target appears independent — keep it, recompute upside.
                                                final_upside = round((scraped_target - spot_f) / spot_f * 100, 2)
                                                logger.warning(
                                                    f"[Verify Trade] {stock_symbol}: scraped current ₹{scraped_current} "
                                                    f"diverges {divergence*100:.1f}% from spot ₹{spot_f}; keeping scraped "
                                                    f"target ₹{scraped_target}, recomputing upside to {final_upside}%"
                                                )
                                            else:
                                                logger.warning(
                                                    f"[Verify Trade] {stock_symbol}: scraped current ₹{scraped_current} "
                                                    f"diverges {divergence*100:.1f}% from spot ₹{spot_f}; no target to rebuild"
                                                )
                                    elif not scraped_current and spot_f:
                                        final_current = spot_f

                                    AnalystPriceTarget.objects.update_or_create(
                                        nse_code=stock_symbol,
                                        defaults={
                                            'symbol': stock_symbol,
                                            'trendlyne_id': extracted_id,
                                            'stock_name': tl_stock.stock_name if tl_stock else '',
                                            'current_price': final_current,
                                            'avg_target_price': final_target,
                                            'upside_pct': final_upside,
                                            'analyst_count': price_target_data.get('analyst_count', 0),
                                            'strong_buy_count': price_target_data.get('strong_buy_count', 0),
                                            'buy_count': price_target_data.get('buy_count', 0),
                                            'hold_count': price_target_data.get('hold_count', 0),
                                            'sell_count': price_target_data.get('sell_count', 0),
                                            'strong_sell_count': price_target_data.get('strong_sell_count', 0),
                                            'source_url': price_target_data.get('source_url', ''),
                                            'scrape_success': True,
                                        }
                                    )
                                    logger.info(f"[Verify Trade] Saved price target for {stock_symbol}: Current=₹{final_current}, Target=₹{final_target}, Upside={final_upside}%")
                                else:
                                    # No useful data found from scraping
                                    logger.warning(f"[Verify Trade] Trendlyne scraping returned no useful analyst data for {stock_symbol}")
                                    analyst_verification['warnings'].append("Trendlyne page did not contain parseable analyst data")
                                    analyst_verification['debug_info'].append("Scraping returned empty values - page structure may have changed")

                                # Save reports
                                reports_data = fetch_result.get('reports', {})
                                reports_saved = 0
                                for report in reports_data.get('reports', []):
                                    try:
                                        AnalystReport.objects.update_or_create(
                                            symbol=stock_symbol,
                                            report_date=report.get('report_date'),
                                            author=report.get('author', '')[:200],
                                            defaults={
                                                'nse_code': stock_symbol,
                                                'trendlyne_id': extracted_id,
                                                'report_title': report.get('report_title', ''),
                                                'ltp_at_report': report.get('ltp_at_report'),
                                                'target_price': report.get('target_price'),
                                                'upside_pct': report.get('upside_pct'),
                                                'recommendation_type': report.get('recommendation_type', 'UNKNOWN'),
                                                'pdf_url': report.get('pdf_url', ''),
                                                'pdf_local_path': report.get('pdf_local_path', ''),
                                                'pdf_download_success': bool(report.get('pdf_local_path')),
                                            }
                                        )
                                        reports_saved += 1
                                    except Exception as re:
                                        logger.warning(f"[Verify Trade] Error saving report: {re}")

                                logger.info(f"[Verify Trade] Saved {reports_saved} analyst reports for {stock_symbol}")

                                # Download PDFs for top 3 reports (for LLM summaries)
                                # Using S3 redirect approach - navigate to PDF URL to get pre-signed S3 URL
                                try:
                                    import requests as req_lib
                                    from django.db.models import Q

                                    reports_to_download = AnalystReport.objects.filter(
                                        nse_code__iexact=stock_symbol
                                    ).filter(
                                        Q(pdf_local_path__isnull=True) | Q(pdf_local_path='')
                                    ).exclude(pdf_url='').order_by('-report_date')[:3]

                                    import os
                                    import re as regex
                                    reports_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata', 'analyst_reports', stock_symbol.upper())
                                    os.makedirs(reports_dir, exist_ok=True)

                                    pdfs_downloaded = 0
                                    for rpt in reports_to_download:
                                        if rpt.pdf_url:
                                            try:
                                                safe_author = regex.sub(r'[^\w\-]', '_', rpt.author or 'unknown')[:50]
                                                safe_date = str(rpt.report_date).replace('-', '_')
                                                filename = f"{stock_symbol}_{safe_date}_{safe_author}.pdf"
                                                local_path = os.path.join(reports_dir, filename)

                                                # Skip if valid PDF exists
                                                if os.path.exists(local_path) and os.path.getsize(local_path) > 5000:
                                                    with open(local_path, 'rb') as f:
                                                        if f.read(5) == b'%PDF-':
                                                            rpt.pdf_local_path = local_path
                                                            rpt.pdf_download_success = True
                                                            rpt.save(update_fields=['pdf_local_path', 'pdf_download_success'])
                                                            pdfs_downloaded += 1
                                                            continue

                                                # Navigate to PDF URL to get S3 redirect
                                                provider.driver.get(rpt.pdf_url)
                                                time.sleep(2)
                                                s3_url = provider.driver.current_url

                                                # Download from S3 (pre-signed URL, no auth needed)
                                                resp = req_lib.get(s3_url, timeout=30)
                                                if resp.status_code == 200 and len(resp.content) > 5000 and resp.content[:5] == b'%PDF-':
                                                    with open(local_path, 'wb') as f:
                                                        f.write(resp.content)
                                                    rpt.pdf_local_path = local_path
                                                    rpt.pdf_download_success = True
                                                    rpt.save(update_fields=['pdf_local_path', 'pdf_download_success'])
                                                    pdfs_downloaded += 1
                                                    logger.info(f"[Verify Trade] Downloaded PDF: {filename}")
                                            except Exception as pdf_err:
                                                logger.warning(f"[Verify Trade] PDF download failed for {rpt.author}: {pdf_err}")

                                    analyst_verification['debug_info'].append(f"Downloaded {pdfs_downloaded} PDFs for LLM summaries")
                                except Exception as pdf_batch_err:
                                    logger.warning(f"[Verify Trade] PDF batch download error: {pdf_batch_err}")
                                    analyst_verification['debug_info'].append(f"PDF download error: {str(pdf_batch_err)}")
                            else:
                                logger.warning(f"[Verify Trade] Failed to fetch analyst data: {fetch_result.get('error')}")
                                analyst_verification['warnings'].append(f"Could not fetch analyst data: {fetch_result.get('error', 'Unknown error')}")
                                analyst_verification['fetch_status'] = 'fetch_failed'
                                analyst_verification['debug_info'].append(f"Fetch failed: {fetch_result.get('error')}")
                        else:
                            logger.warning(f"[Verify Trade] Could not login to Trendlyne")
                            analyst_verification['warnings'].append("Could not login to Trendlyne for analyst data")
                            analyst_verification['fetch_status'] = 'login_failed'
                            analyst_verification['debug_info'].append("Trendlyne login failed")

                except Exception as fetch_error:
                    import traceback
                    error_trace = traceback.format_exc()
                    logger.error(f"[Verify Trade] Error fetching analyst data: {fetch_error}\n{error_trace}")
                    analyst_verification['warnings'].append(f"Error fetching analyst data: {str(fetch_error)}")
                    analyst_verification['fetch_status'] = 'exception'
                    analyst_verification['debug_info'].append(f"Exception: {str(fetch_error)}")
                    analyst_verification['debug_info'].append(f"Traceback: {error_trace[:500]}")

            # Now run aggregation with whatever data we have
            aggregator = get_analyst_report_aggregator()
            analyst_result = aggregator.aggregate_for_trade(
                symbol=stock_symbol,
                direction=direction,
                current_price=float(futures_price) if futures_price else None,
                nse_code=stock_symbol,
                refresh_if_stale=False  # We already handled refresh above
            )

            # Preserve debug info and fetch status collected during fetch
            preserved_debug_info = analyst_verification.get('debug_info', [])
            preserved_fetch_status = analyst_verification.get('fetch_status', 'unknown')
            preserved_data_source = analyst_verification.get('data_source', 'unknown')
            preserved_warnings = analyst_verification.get('warnings', [])

            # Add aggregation result info to debug
            preserved_debug_info.append(f"Aggregation result: trade_allowed={analyst_result.get('trade_allowed')}")
            if analyst_result.get('price_target'):
                pt = analyst_result['price_target']
                preserved_debug_info.append(f"Price target data: Current=₹{pt.get('current_price')}, Target=₹{pt.get('avg_target_price')}, Upside={pt.get('upside_pct')}%, Analysts={pt.get('analyst_count')}")
            else:
                preserved_debug_info.append("No price target data in aggregation result")

            # Get quick LLM summaries for latest 3 reports
            report_summaries = []
            try:
                from apps.llm.services.analyst_report_analyzer import get_quick_summaries_for_reports
                from django.db.models import Q
                import os
                import re as regex

                # Get latest 3 reports from database
                recent_reports = AnalystReport.objects.filter(
                    nse_code__iexact=stock_symbol
                ).order_by('-report_date')[:3]

                if recent_reports.exists():
                    # Check if any reports need PDF download
                    reports_needing_pdf = [r for r in recent_reports if not r.pdf_local_path and r.pdf_url]

                    if reports_needing_pdf:
                        preserved_debug_info.append(f"Need to download {len(reports_needing_pdf)} PDFs for summaries")

                        # Download PDFs using authenticated session
                        # Navigate to PDF URL to get S3 redirect, then download from S3
                        try:
                            from apps.data.providers.trendlyne import TrendlyneProvider
                            import requests as req_lib
                            import time

                            with TrendlyneProvider(headless=True) as provider:
                                provider.init_driver()
                                if provider.login():
                                    reports_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata', 'analyst_reports', stock_symbol.upper())
                                    os.makedirs(reports_dir, exist_ok=True)

                                    pdfs_downloaded = 0
                                    for rpt in reports_needing_pdf:
                                        try:
                                            # Navigate to PDF URL to get S3 redirect
                                            provider.driver.get(rpt.pdf_url)
                                            time.sleep(2)

                                            # Get the redirected S3 URL
                                            s3_url = provider.driver.current_url

                                            # Download from S3 (pre-signed URL, no auth needed)
                                            resp = req_lib.get(s3_url, timeout=30)

                                            if resp.status_code == 200 and len(resp.content) > 5000 and resp.content[:5] == b'%PDF-':
                                                safe_author = regex.sub(r'[^\w\-]', '_', rpt.author or 'unknown')[:50]
                                                safe_date = str(rpt.report_date).replace('-', '_')
                                                filename = f"{stock_symbol}_{safe_date}_{safe_author}.pdf"
                                                local_path = os.path.join(reports_dir, filename)

                                                with open(local_path, 'wb') as f:
                                                    f.write(resp.content)
                                                rpt.pdf_local_path = local_path
                                                rpt.pdf_download_success = True
                                                rpt.save(update_fields=['pdf_local_path', 'pdf_download_success'])
                                                pdfs_downloaded += 1
                                                logger.info(f"[Verify Trade] Downloaded PDF for summary: {filename}")
                                        except Exception as pdf_err:
                                            logger.warning(f"[Verify Trade] PDF download error for {rpt.author}: {pdf_err}")

                                    preserved_debug_info.append(f"Downloaded {pdfs_downloaded} PDFs for summaries")
                                else:
                                    preserved_debug_info.append("Could not login to Trendlyne for PDF download")
                        except Exception as pdf_batch_err:
                            logger.warning(f"[Verify Trade] PDF batch download error: {pdf_batch_err}")
                            preserved_debug_info.append(f"PDF download error: {str(pdf_batch_err)}")

                        # Refresh reports from DB after download
                        recent_reports = AnalystReport.objects.filter(
                            nse_code__iexact=stock_symbol
                        ).order_by('-report_date')[:3]

                    preserved_debug_info.append(f"Fetching quick summaries for {recent_reports.count()} reports...")
                    report_summaries = get_quick_summaries_for_reports(
                        reports=list(recent_reports),
                        symbol=stock_symbol,
                        max_reports=3
                    )
                    preserved_debug_info.append(f"Got {len([s for s in report_summaries if s.get('success')])} successful summaries")
                else:
                    preserved_debug_info.append("No reports found for quick summaries")
            except Exception as summary_error:
                logger.warning(f"[Verify Trade] Could not get quick summaries: {summary_error}")
                preserved_debug_info.append(f"Quick summary error: {str(summary_error)}")

            analyst_verification = {
                'success': True,
                'trade_allowed': analyst_result.get('trade_allowed', True),
                'blocking_reasons': analyst_result.get('blocking_reasons', []),
                'warnings': analyst_result.get('warnings', []) + preserved_warnings,
                'price_target': analyst_result.get('price_target'),
                'reports_summary': analyst_result.get('reports_summary'),
                'top_blocking_reports': analyst_result.get('top_blocking_reports', []),
                'recommendation': analyst_result.get('recommendation', 'PROCEED'),
                'rules_checked': analyst_result.get('rules_checked', []),
                'data_source': preserved_data_source,
                'fetch_status': preserved_fetch_status,
                'debug_info': preserved_debug_info,
                'report_quick_summaries': report_summaries  # LLM summaries of latest 3 reports
            }

            logger.info(f"[Verify Trade] Analyst verification: trade_allowed={analyst_result.get('trade_allowed')}, "
                       f"blocking_reasons={len(analyst_result.get('blocking_reasons', []))}, "
                       f"warnings={len(analyst_result.get('warnings', []))}, "
                       f"data_source={analyst_verification.get('data_source')}")

        except Exception as analyst_error:
            logger.warning(f"[Verify Trade] Analyst verification failed: {analyst_error}", exc_info=True)
            # Don't block trade if analyst check fails - just log and continue
            analyst_verification['error'] = str(analyst_error)
            analyst_verification['warnings'].append(f"Analyst verification unavailable: {str(analyst_error)}")

        # Check if analyst data blocks the trade
        analyst_passed = analyst_verification.get('trade_allowed', True)
        if analysis_passed and historical_passed and news_passed and not analyst_passed:
            logger.warning(f"Trade BLOCKED by analyst data for {stock_symbol}: {analyst_verification.get('blocking_reasons', [])}")

        # Trade only passes if analysis, historical checks, news checks, AND analyst checks pass
        passed = analysis_passed and historical_passed and news_passed and analyst_passed

        # Calculate position sizing with 50% margin rule using shared services
        position_details = {}
        position_sizing = {}

        if futures_price > 0:
            from apps.brokers.integrations.breeze import get_breeze_client
            from apps.trading.services.position_service import calculate_position_sizing, build_position_sizing_response

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

            # Calculate position sizing using shared service
            try:
                breeze = get_breeze_client()

                position_sizing_result = calculate_position_sizing(
                    breeze=breeze,
                    symbol=stock_symbol,
                    expiry=expiry_breeze,
                    lot_size=lot_size,
                    futures_price=futures_price,
                    direction=direction
                )

                # Build standardized response
                sizing_response = build_position_sizing_response(
                    position_sizing=position_sizing_result,
                    lot_size=lot_size,
                    direction=direction
                )

                position_sizing = {
                    'position': position_sizing_result['position'],
                    'margin_data': position_sizing_result['margin_data']
                }

                position_details = sizing_response['position_details']

                logger.info(f"Position sizing: {position_details['recommended_lots']} lots "
                           f"(50% rule: {position_details['max_lots_possible']} max → {position_details['recommended_lots']} recommended)")

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

        # Build verdict message considering analysis, historical verification, news verification, AND analyst verification
        # Check for hard reject from enhanced analyzer
        hard_reject = analysis_result.get('hard_reject', False)
        reject_reason = analysis_result.get('reject_reason', None)

        if passed:
            verdict_text = f'PASS - Score: {composite_score}/100'
            reason_text = f'Composite score: {composite_score}/100. Direction: {direction}'
        elif not analysis_passed:
            if hard_reject and reject_reason:
                # Hard reject from enhanced analyzer (MWPL, Volatility, Piotroski, etc.)
                verdict_text = f'HARD REJECT'
                reason_text = f'Failed hard reject filter: {reject_reason}'
            else:
                verdict_text = f'FAIL - Score: {composite_score}/100'
                reason_text = f'Analysis failed: Composite score {composite_score}/100 below threshold (65 required)'
        elif not historical_passed:
            # Analysis passed but historical verification failed
            hist_verdict = historical_verification.get('verdict', 'BLOCKED')
            hist_failures = [c['name'] for c in historical_verification.get('risk_checks', []) if c.get('status') == 'FAIL']

            if hist_verdict == 'ERROR':
                # Data download error
                verdict_text = f'ERROR - Historical Data Download Failed'
                reason_text = f'Analysis passed (score: {composite_score}) but historical data could not be downloaded. Check Breeze API.'
            else:
                # Risk check failure
                verdict_text = f'BLOCKED - Historical Risk Check Failed'
                reason_text = f'Analysis passed (score: {composite_score}) but blocked by: {", ".join(hist_failures)}'
        elif not news_passed:
            # Analysis and historical passed but news verification failed (HARD BLOCK)
            blocking_count = len(news_verification.get('blocking_articles', []))
            blocking_titles = [a.get('title', 'Unknown')[:50] for a in news_verification.get('blocking_articles', [])[:2]]
            verdict_text = f'BLOCKED - Negative News Detected'
            reason_text = f'Analysis passed (score: {composite_score}) but {blocking_count} highly negative news article(s) detected: {"; ".join(blocking_titles)}'
        else:
            # All others passed but analyst verification failed
            analyst_blocking_reasons = analyst_verification.get('blocking_reasons', [])
            verdict_text = f'BLOCKED - Analyst Reports'
            reason_text = f'Analysis passed (score: {composite_score}) but blocked by analyst data: {"; ".join(analyst_blocking_reasons[:2])}'

        response_data = {
            'success': True,
            'symbol': stock_symbol,
            'expiry': expiry_formatted,
            'contract_display': f"{stock_symbol} - {expiry_formatted}",
            'passed': passed,
            'analysis': analysis_summary,
            'execution_log': execution_log,
            'llm_validation': {'approved': False, 'confidence': 0, 'reasoning': 'LLM validation skipped (Phase 2)'},
            'verdict': verdict_text,
            'reason': reason_text,
            'position_sizing': position_sizing,  # Add comprehensive position sizing data
            # Historical Data Verification Results
            'historical_verification': {
                'success': historical_verification.get('success', False),
                'trade_allowed': historical_verification.get('trade_allowed', True),
                'verdict': historical_verification.get('verdict', 'N/A'),
                'verdict_message': historical_verification.get('verdict_message', ''),
                'risk_checks': historical_verification.get('risk_checks', []),
                'risk_summary': historical_verification.get('risk_summary', {}),
                'recommendations': historical_verification.get('recommendations', []),
                'analysis': historical_verification.get('analysis', {})
            },
            # News Impact Verification Results
            'news_verification': {
                'success': news_verification.get('success', False),
                'trade_allowed': news_verification.get('trade_allowed', True),
                'blocking_articles': news_verification.get('blocking_articles', []),
                'warning_articles': news_verification.get('warning_articles', []),
                'summary': news_verification.get('summary', {}),
                'stock_news': news_verification.get('stock_news', {})
            },
            # Historical News Analysis (from database)
            'historical_news': {
                'success': historical_news.get('success', False),
                'articles': historical_news.get('articles', []),
                'summary': historical_news.get('summary', {})
            },
            # Analyst Report Verification Results
            'analyst_verification': {
                'success': analyst_verification.get('success', False),
                'trade_allowed': analyst_verification.get('trade_allowed', True),
                'blocking_reasons': analyst_verification.get('blocking_reasons', []),
                'warnings': analyst_verification.get('warnings', []),
                'price_target': analyst_verification.get('price_target'),
                'reports_summary': analyst_verification.get('reports_summary'),
                'top_blocking_reports': analyst_verification.get('top_blocking_reports', []),
                'recommendation': analyst_verification.get('recommendation', 'PROCEED'),
                'rules_checked': analyst_verification.get('rules_checked', []),
                'data_source': analyst_verification.get('data_source', 'none'),
                'fetch_status': analyst_verification.get('fetch_status', 'unknown'),
                'debug_info': analyst_verification.get('debug_info', []),
                'report_quick_summaries': analyst_verification.get('report_quick_summaries', [])
            },
            # Enhanced Analysis Results (13-component scoring)
            'enhanced_analysis': {
                'hard_reject': hard_reject,
                'reject_reason': reject_reason,
                'news_warning': analysis_result.get('news_warning'),
                'composite_score': analysis_result.get('composite_score', 0),
                'recommendation': analysis_result.get('recommendation', 'N/A'),
                'scores': analysis_result.get('scores', {}),
                'component_scores': analysis_result.get('component_scores', {}),
                'details': analysis_result.get('details', {}),
                'entry_params': analysis_result.get('entry_params'),
                'regime': regime,
            }
        }

        # Save trade suggestion to database (only if PASS)
        if passed:
            from apps.trading.models import TradeSuggestion
            from apps.brokers.integrations.breeze import get_india_vix
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

            # Calculate stop loss and target using adaptive SL/target engine
            futures_price_decimal = Decimal(str(futures_price))
            try:
                from apps.strategies.services.adaptive_sl_target import compute_adaptive_sl_target

                # Get ATR and S/R levels if available
                from apps.data.models import TLStockData
                tl = TLStockData.objects.filter(nsecode=stock_symbol).first()
                atr_val = float(tl.day_atr) if tl and tl.day_atr else None
                vol_val = None
                s1_val = float(tl.first_support_s1) if tl and tl.first_support_s1 else None
                r1_val = float(tl.first_resistance_r1) if tl and tl.first_resistance_r1 else None

                sl_result = compute_adaptive_sl_target(
                    symbol=stock_symbol,
                    price=float(futures_price),
                    direction=direction,
                    atr=atr_val,
                    volatility_pct=vol_val,
                    composite_score=int(composite_score),
                    regime=regime,
                    support_s1=s1_val,
                    resistance_r1=r1_val,
                )
                stop_loss_price = Decimal(str(round(sl_result['stop_loss'], 2)))
                target_price = Decimal(str(round(sl_result['target_1'], 2)))
            except Exception as sl_err:
                logger.warning(f"Adaptive SL/target failed, using SR fallback: {sl_err}")
                _sr = compute_initial_sl_target(stock_symbol, float(futures_price), direction)
                if direction == 'LONG':
                    stop_loss_price = Decimal(str(round(_sr['stop_loss'] or float(futures_price_decimal) * 0.98, 2)))
                    target_price = Decimal(str(round(_sr['target'] or float(futures_price_decimal) * 1.04, 2)))
                elif direction == 'SHORT':
                    stop_loss_price = Decimal(str(round(_sr['stop_loss'] or float(futures_price_decimal) * 1.02, 2)))
                    target_price = Decimal(str(round(_sr['target'] or float(futures_price_decimal) * 0.96, 2)))
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

            # Calculate risk/reward ratio
            risk_reward_ratio_value = Decimal('0')
            if max_loss_value > 0:
                risk_reward_ratio_value = max_profit_value / max_loss_value

            # Apply post-score trade validation gate
            trade_validation = None
            try:
                from apps.strategies.services.trade_validation import TradeValidationLayer
                # Enrich analysis_result with computed entry params for validation
                validation_input = dict(analysis_result)
                validation_input['entry_params'] = {
                    'entry_price': float(futures_price),
                    'stop_loss': float(stop_loss_price),
                    'target_1': float(target_price),
                    'risk_reward_ratio': float(risk_reward_ratio_value),
                    'days_to_expiry': (expiry_dt.date() - datetime.now().date()).days,
                }
                validator = TradeValidationLayer()
                trade_validation = validator.validate(validation_input, regime=regime)
            except Exception as val_err:
                logger.warning(f"Trade validation gate error: {val_err}")

            # Fetch VIX for the suggestion record
            try:
                vix_value = get_india_vix()
            except Exception as vix_err:
                logger.warning(f"Could not fetch VIX for suggestion: {vix_err}")
                vix_value = None

            suggestion = TradeSuggestion.objects.create(
                user=request.user,
                strategy='icici_futures',
                suggestion_type='FUTURES',
                instrument=stock_symbol,
                direction=direction.upper(),
                # Market Data
                spot_price=Decimal(str(spot_price)),
                vix=vix_value,
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
                risk_reward_ratio=risk_reward_ratio_value,
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

        # Cache the complete result for 5 minutes so parallel/repeat requests
        # return instantly without re-running the 90-second analysis.
        response_data['from_cache'] = False
        try:
            _ac.set(_result_key, response_data, timeout=300)
            _ac.delete(_lock_key)
        except Exception as _cache_err:
            logger.warning(f"Failed to cache analysis result: {_cache_err}")

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in verify_future_trade: {e}", exc_info=True)
        # Release in-progress lock on error (TTL of 180s is the backstop if this fails)
        try:
            from django.core.cache import cache as _ac_exc
            contract_v = request.POST.get('contract', '').strip()
            if '|' in contract_v:
                _s, _e = contract_v.split('|', 1)
                _ac_exc.delete(f'analysis_in_progress_{_s.upper()}_{_e}')
        except Exception:
            pass
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def refresh_analyst_data(request):
    """
    Refresh analyst data for a specific stock by re-fetching from Trendlyne.
    Clears stale data and forces a fresh scrape.
    """
    stock_symbol = request.POST.get('symbol', '').strip().upper()
    if not stock_symbol:
        return JsonResponse({'success': False, 'error': 'No symbol provided'})

    try:
        from apps.data.models import AnalystPriceTarget, AnalystReport, TLStockData
        from apps.data.providers.trendlyne import TrendlyneProvider

        debug_info = []

        # Get trendlyne_id from TLStockData if available
        tl_stock = TLStockData.objects.filter(nsecode__iexact=stock_symbol).first()
        trendlyne_id = tl_stock.trendlyne_id if tl_stock else None
        debug_info.append(f"TLStockData found: {tl_stock is not None}, trendlyne_id: {trendlyne_id}")

        with TrendlyneProvider(headless=True) as provider:
            debug_info.append("Initializing Chrome driver...")
            provider.init_driver()

            debug_info.append("Attempting Trendlyne login...")
            login_success = provider.login()
            debug_info.append(f"Login result: {login_success}")

            if not login_success:
                return JsonResponse({
                    'success': False,
                    'error': 'Could not login to Trendlyne',
                    'debug_info': debug_info
                })

            # Fetch analyst data
            fetch_result = provider.fetch_analyst_data(
                symbol=stock_symbol,
                trendlyne_id=trendlyne_id,
                months_back=3,
                download_pdfs=False
            )

            debug_info.append(f"Fetch result success: {fetch_result.get('success')}")

            if not fetch_result.get('success'):
                return JsonResponse({
                    'success': False,
                    'error': fetch_result.get('error', 'Fetch failed'),
                    'debug_info': debug_info
                })

            extracted_id = fetch_result.get('trendlyne_id')

            # Update TLStockData with trendlyne_id if found
            if extracted_id and tl_stock and not tl_stock.trendlyne_id:
                tl_stock.trendlyne_id = extracted_id
                tl_stock.save()
                debug_info.append(f"Saved trendlyne_id {extracted_id}")

            # Save price target data
            price_target_data = fetch_result.get('price_target', {})
            has_price_data = price_target_data.get('avg_target_price') is not None
            has_analyst_data = price_target_data.get('analyst_count', 0) > 0
            has_upside_data = price_target_data.get('upside_pct') is not None

            if has_price_data or has_analyst_data or has_upside_data:
                AnalystPriceTarget.objects.update_or_create(
                    nse_code=stock_symbol,
                    defaults={
                        'symbol': stock_symbol,
                        'trendlyne_id': extracted_id,
                        'stock_name': tl_stock.stock_name if tl_stock else '',
                        'current_price': price_target_data.get('current_price'),
                        'avg_target_price': price_target_data.get('avg_target_price'),
                        'upside_pct': price_target_data.get('upside_pct'),
                        'analyst_count': price_target_data.get('analyst_count', 0),
                        'strong_buy_count': price_target_data.get('strong_buy_count', 0),
                        'buy_count': price_target_data.get('buy_count', 0),
                        'hold_count': price_target_data.get('hold_count', 0),
                        'sell_count': price_target_data.get('sell_count', 0),
                        'strong_sell_count': price_target_data.get('strong_sell_count', 0),
                        'source_url': price_target_data.get('source_url', ''),
                        'scrape_success': True,
                    }
                )
                debug_info.append(f"Saved price target: ₹{price_target_data.get('avg_target_price')}, {price_target_data.get('analyst_count')} analysts")

            # Save reports
            reports_data = fetch_result.get('reports', {})
            reports_saved = 0
            for report in reports_data.get('reports', []):
                try:
                    AnalystReport.objects.update_or_create(
                        symbol=stock_symbol,
                        report_date=report.get('report_date'),
                        author=report.get('author', '')[:200],
                        defaults={
                            'nse_code': stock_symbol,
                            'trendlyne_id': extracted_id,
                            'report_title': report.get('report_title', ''),
                            'ltp_at_report': report.get('ltp_at_report'),
                            'target_price': report.get('target_price'),
                            'upside_pct': report.get('upside_pct'),
                            'recommendation_type': report.get('recommendation_type', 'UNKNOWN'),
                            'pdf_url': report.get('pdf_url', ''),
                            'pdf_local_path': report.get('pdf_local_path', ''),
                            'pdf_download_success': bool(report.get('pdf_local_path')),
                        }
                    )
                    reports_saved += 1
                except Exception as re:
                    logger.warning(f"[Refresh Analyst] Error saving report: {re}")

            debug_info.append(f"Saved {reports_saved} reports")

            # Build response with fresh data
            price_target_response = None
            fresh_pt = AnalystPriceTarget.objects.filter(nse_code__iexact=stock_symbol).first()
            if fresh_pt:
                price_target_response = {
                    'current_price': float(fresh_pt.current_price) if fresh_pt.current_price else None,
                    'avg_target_price': float(fresh_pt.avg_target_price) if fresh_pt.avg_target_price else None,
                    'upside_pct': float(fresh_pt.upside_pct) if fresh_pt.upside_pct else None,
                    'analyst_count': fresh_pt.analyst_count,
                    'strong_buy_count': fresh_pt.strong_buy_count,
                    'buy_count': fresh_pt.buy_count,
                    'hold_count': fresh_pt.hold_count,
                    'sell_count': fresh_pt.sell_count,
                    'strong_sell_count': fresh_pt.strong_sell_count,
                }

            return JsonResponse({
                'success': True,
                'symbol': stock_symbol,
                'price_target': price_target_response,
                'reports_saved': reports_saved,
                'trendlyne_id': extracted_id,
                'debug_info': debug_info,
            })

    except Exception as e:
        logger.error(f"[Refresh Analyst] Error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def fetch_trade_news(request):
    """
    Fetch news related to a stock, its industry, and competitors.

    This endpoint fetches news from GNews.io API for:
    1. The stock itself
    2. The industry/sector the stock belongs to
    3. Competitor companies in the same sector

    Request Body (POST form data):
        stock_symbol: "SYMBOL"  # Example: "RELIANCE"

    Returns:
        JsonResponse: {
            'success': bool,
            'stock_news': {
                'articles': [...],  # List of news articles for the stock
                'totalArticles': int
            },
            'industry_news': {
                'articles': [...],  # List of news articles for the industry
                'totalArticles': int,
                'industry_name': str
            },
            'competitor_news': {
                'articles': [...],  # List of news articles for competitors
                'totalArticles': int,
                'competitors': [str]  # List of competitor names
            },
            'error': str (only if success=False)
        }

    Article structure:
        {
            'title': str,
            'description': str,
            'content': str,
            'url': str,
            'image': str,
            'publishedAt': str,  # ISO format datetime
            'source': {'name': str, 'url': str}
        }

    Error Responses:
        - 400: Missing stock_symbol parameter
        - 404: Stock not found in database
        - 500: News fetch error

    Example:
        POST /trading/trigger/fetch-news/
        Body: stock_symbol=RELIANCE

        Response:
        {
            'success': true,
            'stock_news': {
                'articles': [...],
                'totalArticles': 3
            },
            'industry_news': {
                'articles': [...],
                'totalArticles': 3,
                'industry_name': 'Oil and Gas'
            },
            'competitor_news': {
                'articles': [...],
                'totalArticles': 3,
                'competitors': ['BPCL', 'IOCL', 'ONGC']
            }
        }
    """
    try:
        from apps.data.services.gnews_client import get_gnews_client
        from apps.data.models import TLStockData, ContractStockData
        import json

        # Parse JSON body
        try:
            body = json.loads(request.body)
            stock_symbol = body.get('stock_symbol', '').strip().upper()
        except (ValueError, json.JSONDecodeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid request format'
            })

        if not stock_symbol:
            return JsonResponse({
                'success': False,
                'error': 'Stock symbol is required'
            })

        logger.info(f"[Trade News] Fetching news for {stock_symbol}")

        # Initialize GNews client
        gnews = get_gnews_client()

        # Step 1: Fetch stock details from Trendlyne data
        stock_data = TLStockData.objects.filter(nsecode=stock_symbol).first()

        if not stock_data:
            # Try ContractStockData as fallback
            contract_stock = ContractStockData.objects.filter(nse_code=stock_symbol).first()
            if contract_stock:
                stock_name = contract_stock.stock_name
                industry_name = contract_stock.industry_name
            else:
                # If not found, use symbol as name
                stock_name = stock_symbol
                industry_name = None
                logger.warning(f"[Trade News] Stock data not found for {stock_symbol}, using symbol as name")
        else:
            stock_name = stock_data.stock_name
            industry_name = stock_data.industry_name
            logger.info(f"[Trade News] Found stock: {stock_name}, Industry: {industry_name}")

        # Step 2: Fetch news for the stock
        logger.info(f"[Trade News] Fetching stock news for {stock_symbol}")
        stock_news_result = gnews.fetch_stock_news(
            stock_symbol=stock_symbol,
            stock_name=stock_name,
            max_results=10  # Fetch more for database
        )

        # Step 3: Fetch news for the industry
        industry_news_result = {'articles': [], 'totalArticles': 0}
        if industry_name:
            logger.info(f"[Trade News] Fetching industry news for {industry_name}")
            industry_news_result = gnews.fetch_industry_news(
                industry_name=industry_name,
                max_results=10  # Fetch more for database
            )
            industry_news_result['industry_name'] = industry_name
        else:
            logger.warning(f"[Trade News] No industry name found for {stock_symbol}")

        # Step 4: Fetch competitors in the same industry AND sector
        competitors = []
        competitor_names = []
        if industry_name and stock_data and stock_data.sector_name:
            sector_name = stock_data.sector_name
            current_market_cap = stock_data.market_capitalization or 0

            # Find other stocks in the same industry AND sector
            competitor_stocks = TLStockData.objects.filter(
                industry_name=industry_name,
                sector_name=sector_name,
                market_capitalization__isnull=False
            ).exclude(
                nsecode=stock_symbol
            )

            # If more than 5, filter by closest market cap
            if competitor_stocks.count() > 5:
                # Calculate market cap difference and sort by absolute difference
                competitors_with_diff = []
                for comp in competitor_stocks:
                    diff = abs((comp.market_capitalization or 0) - current_market_cap)
                    competitors_with_diff.append((comp, diff))

                # Sort by difference and take top 5
                competitors_with_diff.sort(key=lambda x: x[1])
                competitor_stocks = [comp for comp, diff in competitors_with_diff[:5]]
            else:
                # If 5 or fewer, just order by market cap descending
                competitor_stocks = list(competitor_stocks.order_by('-market_capitalization')[:5])

            competitors = competitor_stocks
            competitor_names = [stock.stock_name for stock in competitors if stock.stock_name]
            logger.info(f"[Trade News] Found {len(competitor_names)} competitors in {sector_name} sector: {competitor_names}")
        elif industry_name and stock_data:
            # Fallback: just industry if no sector
            competitor_stocks = TLStockData.objects.filter(
                industry_name=industry_name
            ).exclude(
                nsecode=stock_symbol
            ).order_by('-market_capitalization')[:5]

            competitors = list(competitor_stocks)
            competitor_names = [stock.stock_name for stock in competitors if stock.stock_name]
            logger.info(f"[Trade News] Found {len(competitor_names)} competitors (industry only): {competitor_names}")

        # Step 5: Fetch news for competitors
        competitor_news_result = {'articles': [], 'totalArticles': 0}
        if competitor_names:
            logger.info(f"[Trade News] Fetching competitor news")
            competitor_news_result = gnews.fetch_competitor_news(
                competitors=competitor_names,
                max_results=10  # Fetch more for database
            )
            competitor_news_result['competitors'] = competitor_names[:3]  # Return top 3 names
        else:
            competitor_news_result['competitors'] = []
            logger.warning(f"[Trade News] No competitors found for {stock_symbol}")

        # Step 6: Save articles to database
        from apps.data.models import NewsArticle
        from datetime import datetime
        from django.utils import timezone as django_timezone

        def save_articles_to_db(articles, category, news_type, symbols=None, sectors=None, search_keywords=None):
            """Save articles to NewsArticle model with extended fields"""
            saved_count = 0
            for article in articles:
                try:
                    # Parse published date
                    published_at = article.get('publishedAt')
                    if published_at:
                        # GNews returns ISO format
                        published_dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    else:
                        published_dt = django_timezone.now()

                    # Check if article already exists
                    if NewsArticle.objects.filter(url=article['url']).exists():
                        logger.debug(f"[Trade News] Article already exists: {article['url']}")
                        continue

                    # Create article with extended fields
                    NewsArticle.objects.create(
                        title=article.get('title', '')[:500],
                        source=article.get('source', {}).get('name', 'GNews')[:100],
                        author='',
                        published_at=published_dt,
                        url=article['url'],
                        image_url=article.get('image', ''),
                        summary=article.get('description', '')[:1000],
                        content=article.get('content', ''),
                        category=category,
                        news_type=news_type,
                        tags=[],
                        symbols_mentioned=symbols or [],
                        sectors_mentioned=sectors or [],
                        search_keywords=search_keywords or [],
                        processed=False
                    )
                    saved_count += 1
                except Exception as e:
                    logger.error(f"[Trade News] Error saving article: {e}")
                    continue

            return saved_count

        def update_article_with_analysis(article_url, impact_data):
            """Update an existing article with LLM analysis results"""
            try:
                article = NewsArticle.objects.filter(url=article_url).first()
                if article:
                    article.sentiment_score = impact_data.get('impact_score', 0)
                    article.sentiment_label = 'NEGATIVE' if impact_data.get('impact_score', 0) < -0.3 else ('POSITIVE' if impact_data.get('impact_score', 0) > 0.3 else 'NEUTRAL')
                    article.sentiment_confidence = impact_data.get('impact_confidence', 0)
                    article.impact_reasoning = impact_data.get('impact_reasoning', '')
                    article.market_direction = impact_data.get('market_direction') or ('BEARISH' if impact_data.get('impact_score', 0) < -0.3 else ('BULLISH' if impact_data.get('impact_score', 0) > 0.3 else 'NEUTRAL'))
                    article.relevance_score = impact_data.get('relevance', 1.0)
                    article.impact_category = impact_data.get('impact_category', '')
                    article.impact_analysis = {
                        'impact_score': impact_data.get('impact_score', 0),
                        'impact_label': impact_data.get('impact_label', 'NEUTRAL'),
                        'impact_reasoning': impact_data.get('impact_reasoning', ''),
                        'trade_recommendation': impact_data.get('trade_recommendation', 'PROCEED'),
                        'blocks_trade': impact_data.get('blocks_trade', False),
                        'analyzed_at': django_timezone.now().isoformat()
                    }
                    article.processed = True
                    article.processed_at = django_timezone.now()
                    article.save()
                    return True
            except Exception as e:
                logger.error(f"[Trade News] Error updating article analysis: {e}")
            return False

        # Save stock news
        stock_articles_saved = save_articles_to_db(
            stock_news_result.get('articles', []),
            category='Stock',
            news_type='STOCK',
            symbols=[stock_symbol],
            sectors=[industry_name] if industry_name else [],
            search_keywords=[stock_symbol, stock_name] if stock_name else [stock_symbol]
        )
        logger.info(f"[Trade News] Saved {stock_articles_saved} stock articles to database")

        # Save industry news
        industry_articles_saved = save_articles_to_db(
            industry_news_result.get('articles', []),
            category='Industry',
            news_type='INDUSTRY',
            symbols=[],
            sectors=[industry_name] if industry_name else [],
            search_keywords=[industry_name] if industry_name else []
        )
        logger.info(f"[Trade News] Saved {industry_articles_saved} industry articles to database")

        # Save competitor news
        competitor_articles_saved = save_articles_to_db(
            competitor_news_result.get('articles', []),
            category='Competitor',
            news_type='COMPETITOR',
            symbols=[comp.nsecode for comp in competitors if hasattr(comp, 'nsecode')],
            sectors=[industry_name] if industry_name else [],
            search_keywords=competitor_names[:3] if competitor_names else []
        )
        logger.info(f"[Trade News] Saved {competitor_articles_saved} competitor articles to database")

        # Step 7: Retrieve saved articles from database (to ensure consistency)
        from django.db.models import Q

        # Stock news: GNews articles (category='Stock') + exchange filings (NSE/BSE).
        # Exchange filings stored before the category fix may have category='' so we
        # use an OR query to catch both old and new records.
        all_stock_articles = NewsArticle.objects.filter(
            Q(category='Stock') | Q(source__in=['NSE', 'BSE'], news_type='STOCK')
        ).order_by('-published_at')[:100]

        # Filter for this specific stock symbol, then surface exchange filings first
        # (source_quality_score=1.0 = highest authority).
        matched_stock = [
            a for a in all_stock_articles
            if stock_symbol in (a.symbols_mentioned or [])
        ]
        matched_stock.sort(
            key=lambda a: (0 if a.source in ('NSE', 'BSE') else 1, -a.published_at.timestamp())
        )
        stock_articles_db = matched_stock[:10]

        # Get industry news from DB
        all_industry_articles = NewsArticle.objects.filter(
            category='Industry'
        ).order_by('-published_at')[:50] if industry_name else []

        # Filter for this specific industry
        industry_articles_db = [
            article for article in all_industry_articles
            if industry_name in (article.sectors_mentioned or [])
        ][:10] if industry_name else []

        # Get competitor news from DB
        all_competitor_articles = NewsArticle.objects.filter(
            category='Competitor'
        ).order_by('-published_at')[:50] if industry_name else []

        # Filter for this industry's competitors
        competitor_articles_db = [
            article for article in all_competitor_articles
            if industry_name in (article.sectors_mentioned or [])
        ][:10] if industry_name else []

        def _to_5label(score, label_3):
            """Map 3-value DB label → 5-value UI label using score for HIGHLY_ variants."""
            if score is None:
                return 'NEUTRAL'
            if label_3 == 'POSITIVE':
                return 'HIGHLY_POSITIVE' if score >= 0.6 else 'POSITIVE'
            if label_3 == 'NEGATIVE':
                return 'HIGHLY_NEGATIVE' if score <= -0.6 else 'NEGATIVE'
            return 'NEUTRAL'

        # Build articles list from DB — include pre-computed sentiment so exchange
        # filings (which already have LLM scores from fetch_exchange_filings) render
        # with impact badges and reasoning in the UI without re-analysis.
        def db_articles_to_dict(articles):
            result = []
            for article in articles:
                is_filing = article.source in ('NSE', 'BSE')
                result.append({
                    'title': article.title,
                    'description': article.summary,
                    'content': article.content,
                    'url': article.url,
                    'image': article.image_url,
                    'publishedAt': article.published_at.isoformat(),
                    'source': {'name': article.source, 'url': ''},
                    # Pre-computed sentiment (always present for exchange filings)
                    'impact_score': article.sentiment_score,
                    'impact_label': _to_5label(article.sentiment_score, article.sentiment_label),
                    'impact_reasoning': article.impact_reasoning or '',
                    'event_type': getattr(article, 'event_type', '') or '',
                    'is_exchange_filing': is_filing,
                })
            return result

        # Build initial response from database
        stock_news_data = {
            'articles': db_articles_to_dict(stock_articles_db),
            'totalArticles': len(stock_articles_db),
            'stock_name': stock_name,
            'stock_symbol': stock_symbol
        }
        industry_news_data = {
            'articles': db_articles_to_dict(industry_articles_db),
            'totalArticles': len(industry_articles_db),
            'industry_name': industry_name or 'Unknown'
        }
        competitor_news_data = {
            'articles': db_articles_to_dict(competitor_articles_db),
            'totalArticles': len(competitor_articles_db),
            'competitors': competitor_news_result.get('competitors', [])
        }

        # Step 8: Analyze news impact using LLM
        # Get trade direction from request (default to LONG for news display)
        trade_direction = body.get('trade_direction', 'LONG').upper()
        logger.info(f"[Trade News] Analyzing news impact for {stock_symbol} ({trade_direction} trade)")

        try:
            from apps.llm.services.news_impact_analyzer import get_news_impact_analyzer

            analyzer = get_news_impact_analyzer()
            impact_result = analyzer.analyze_news_for_trade(
                stock_news=stock_news_data,
                industry_news=industry_news_data,
                competitor_news=competitor_news_data,
                stock_symbol=stock_symbol,
                stock_name=stock_name,
                trade_direction=trade_direction,
                industry_name=industry_name,
                max_articles_per_category=5  # Limit for speed
            )

            # Use impact-analyzed and sorted news data
            response_data = {
                'success': True,
                'stock_news': impact_result['stock_news'],
                'industry_news': impact_result['industry_news'],
                'competitor_news': impact_result['competitor_news'],
                'news_verification': {
                    'trade_allowed': impact_result['trade_allowed'],
                    'blocking_articles': impact_result['blocking_articles'],
                    'warning_articles': impact_result['warning_articles'],
                    'summary': impact_result['summary']
                }
            }

            logger.info(f"[Trade News] Impact analysis complete: trade_allowed={impact_result['trade_allowed']}, "
                       f"blocking={len(impact_result['blocking_articles'])}, warnings={len(impact_result['warning_articles'])}")

            # Step 9: Update articles in database with LLM analysis results
            updated_count = 0
            for category_key in ['stock_news', 'industry_news', 'competitor_news']:
                for article in impact_result.get(category_key, {}).get('articles', []):
                    if update_article_with_analysis(article.get('url'), article):
                        updated_count += 1
            logger.info(f"[Trade News] Updated {updated_count} articles with LLM analysis")

        except Exception as impact_error:
            logger.warning(f"[Trade News] Impact analysis failed: {impact_error}, returning unanalyzed news")
            # Fallback: return news without impact analysis
            response_data = {
                'success': True,
                'stock_news': stock_news_data,
                'industry_news': industry_news_data,
                'competitor_news': competitor_news_data,
                'generic_news': {'articles': [], 'totalArticles': 0},
                'news_verification': {
                    'trade_allowed': True,
                    'blocking_articles': [],
                    'warning_articles': [],
                    'summary': {
                        'total_analyzed': 0,
                        'error': str(impact_error)
                    }
                }
            }

        # Step 10: Fetch top 2 most impactful market news from database (last 10 days)
        try:
            from datetime import timedelta
            cutoff_date = django_timezone.now() - timedelta(days=10)

            # Fetch all market articles from last 10 days
            market_articles = list(NewsArticle.objects.filter(
                news_type='MARKET',
                processed=True,
                published_at__gte=cutoff_date
            ).order_by('-published_at')[:20])  # Get recent 20, then sort by impact

            # Sort by absolute impact score (most impactful first, regardless of +/-)
            market_articles.sort(key=lambda x: abs(x.sentiment_score or 0), reverse=True)

            # Take top 2 most impactful articles
            top_articles = market_articles[:2]

            # Count total available for "View All" badge
            total_market_articles = NewsArticle.objects.filter(
                news_type='MARKET',
                processed=True,
                published_at__gte=cutoff_date
            ).count()

            generic_news_articles = []
            for article in top_articles:
                generic_news_articles.append({
                    'title': article.title,
                    'description': article.summary,
                    'url': article.url,
                    'image': article.image_url,
                    'publishedAt': article.published_at.isoformat() if article.published_at else None,
                    'source': {'name': article.source, 'url': ''},
                    'impact_score': article.sentiment_score or 0,
                    'impact_label': article.impact_analysis.get('impact_label', 'NEUTRAL') if article.impact_analysis else 'NEUTRAL',
                    'impact_reasoning': article.impact_reasoning or '',
                    'market_direction': article.market_direction or 'NEUTRAL',
                    'impact_category': article.impact_category or ''
                })

            response_data['generic_news'] = {
                'articles': generic_news_articles,
                'totalArticles': total_market_articles  # Total in DB for "View All" count
            }
            logger.info(f"[Trade News] Generic market news: {len(generic_news_articles)} top impact articles (total in DB: {total_market_articles})")

        except Exception as generic_error:
            logger.warning(f"[Trade News] Error fetching generic news: {generic_error}")
            response_data['generic_news'] = {'articles': [], 'totalArticles': 0}

        logger.info(f"[Trade News] Successfully fetched news for {stock_symbol}")
        logger.info(f"[Trade News] Stock: {len(response_data['stock_news']['articles'])} articles")
        logger.info(f"[Trade News] Industry: {len(response_data['industry_news']['articles'])} articles")
        logger.info(f"[Trade News] Competitors: {len(response_data['competitor_news']['articles'])} articles")

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"[Trade News] Error fetching news: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def news_details_page(request):
    """
    Display detailed news page.

    When called without parameters: Shows Market News Dashboard with top impactful news
    When called with parameters: Shows specific category news (stock/industry/competitor)

    Query Parameters (for specific category):
        category: 'stock', 'industry', or 'competitor'
        identifier: Stock symbol, industry name, or competitor names
        title: Display title

    Returns:
        Rendered HTML page with news articles
    """
    from apps.data.models import NewsArticle

    category = request.GET.get('category', '')
    identifier = request.GET.get('identifier', '')
    title = request.GET.get('title', '')

    # If no category specified, show Market News Dashboard
    if not category:
        return market_news_dashboard(request)

    # Fetch articles from database based on category
    # SQLite-compatible approach: filter by category, then filter in Python
    articles = []

    if category == 'stock':
        from django.db.models import Q as _Q
        # Include GNews articles (category='Stock') + exchange filings (NSE/BSE).
        # Old filings stored before the category fix may have category='' so use OR.
        all_articles = NewsArticle.objects.filter(
            _Q(category='Stock') | _Q(source__in=['NSE', 'BSE'], news_type='STOCK')
        ).order_by('-published_at')[:500]

        matched = [
            a for a in all_articles
            if identifier in (a.symbols_mentioned or [])
        ]
        # Exchange filings first (authority = 1.0), then by date
        matched.sort(
            key=lambda a: (0 if a.source in ('NSE', 'BSE') else 1, -a.published_at.timestamp())
        )
        articles = matched
    elif category == 'industry':
        # Industry news - filter by sector
        all_articles = NewsArticle.objects.filter(
            category='Industry'
        ).order_by('-published_at')

        # Filter for this specific industry
        articles = [
            article for article in all_articles
            if identifier in (article.sectors_mentioned or [])
        ]
    elif category == 'competitor':
        # Competitor news - all competitor articles
        articles = list(NewsArticle.objects.filter(
            category='Competitor'
        ).order_by('-published_at'))
    elif category == 'market':
        # Market intelligence news - from database (last 10 days)
        from datetime import timedelta
        from django.utils import timezone as django_timezone

        cutoff_date = django_timezone.now() - timedelta(days=10)
        articles = list(NewsArticle.objects.filter(
            news_type='MARKET',
            processed=True,
            published_at__gte=cutoff_date
        ).exclude(
            sentiment_score__isnull=True
        ).order_by('-relevance_score', 'sentiment_score')[:20])

    context = {
        'category': category,
        'identifier': identifier,
        'title': title or ('Market Intelligence - Top Impact News' if category == 'market' else ''),
        'articles': articles,
        'total_count': len(articles)
    }

    return render(request, 'trading/news_details.html', context)


@login_required
def market_news_dashboard(request):
    """
    Display Market News Dashboard with top impactful news for Indian markets.

    Fetches global market news using keywords like:
    - US Fed, interest rates
    - Global market movements (Dow, Nasdaq, S&P)
    - Asian markets (Nikkei, Hang Seng)
    - Crude oil, gold prices
    - Economic data (jobs, GDP, inflation)

    Each article is analyzed by LLM for impact on Indian markets.
    Top 10-20 most impactful articles are displayed.

    Returns:
        Rendered HTML page with market news dashboard
    """
    from apps.data.services.gnews_client import get_gnews_client
    from apps.llm.services.news_impact_analyzer import get_news_impact_analyzer
    from apps.data.models import NewsArticle
    from datetime import datetime, timedelta
    from django.utils import timezone as django_timezone

    context = {
        'articles': [],
        'summary': {},
        'category_breakdown': {},
        'error': None,
        'loading': False
    }

    # Check if this is an AJAX request for news data
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            # Check if we have recent market news in database (within 8 hours)
            cache_hours = 8
            cache_cutoff = django_timezone.now() - timedelta(hours=cache_hours)

            cached_articles = NewsArticle.objects.filter(
                news_type='MARKET',
                processed=True,
                processed_at__gte=cache_cutoff
            ).exclude(
                sentiment_score__isnull=True
            ).order_by('-relevance_score', 'sentiment_score')[:20]

            if cached_articles.exists():
                logger.info(f"[Market News] Using {cached_articles.count()} cached articles (processed within {cache_hours} hours)")

                # Convert database articles to response format
                articles_data = []
                category_counts = {}

                for article in cached_articles:
                    impact_category = article.impact_category or 'Other'
                    category_counts[impact_category] = category_counts.get(impact_category, 0) + 1

                    articles_data.append({
                        'title': article.title,
                        'description': article.summary,
                        'content': article.content,
                        'url': article.url,
                        'image': article.image_url,
                        'publishedAt': article.published_at.isoformat() if article.published_at else None,
                        'source': {'name': article.source, 'url': ''},
                        'impact_score': article.sentiment_score,
                        'impact_label': article.sentiment_label,
                        'impact_reasoning': article.impact_reasoning,
                        'market_direction': article.market_direction,
                        'relevance': article.relevance_score,
                        'impact_category': impact_category,
                    })

                # Calculate summary
                scores = [a.sentiment_score for a in cached_articles if a.sentiment_score is not None]
                avg_score = sum(scores) / len(scores) if scores else 0
                positive_count = sum(1 for s in scores if s > 0.3)
                negative_count = sum(1 for s in scores if s < -0.3)

                historical_market_news = get_historical_market_news(limit=5)

                return JsonResponse({
                    'success': True,
                    'articles': articles_data,
                    'summary': {
                        'total_analyzed': len(articles_data),
                        'average_impact_score': round(avg_score, 2),
                        'positive_count': positive_count,
                        'negative_count': negative_count,
                        'neutral_count': len(scores) - positive_count - negative_count,
                    },
                    'category_breakdown': category_counts,
                    'historical_news': historical_market_news,
                    'cached': True,
                    'cache_age_hours': cache_hours
                })

            # No cached articles, fetch fresh ones
            logger.info("[Market News] No cached articles found, fetching fresh market news")

            # Fetch market news from GNews API
            gnews = get_gnews_client()
            news_result = gnews.fetch_market_news(
                max_results_per_keyword=8,
                use_cache=True
            )

            if not news_result.get('success'):
                return JsonResponse({
                    'success': False,
                    'error': news_result.get('error', 'Failed to fetch news')
                })

            articles = news_result.get('articles', [])
            keywords_used = news_result.get('keywords_used', [])
            logger.info(f"[Market News] Fetched {len(articles)} articles, analyzing with LLM...")

            # Analyze articles with LLM
            analyzer = get_news_impact_analyzer()
            analysis_result = analyzer.analyze_market_news(
                articles=articles,
                top_n=20
            )

            # Save analyzed articles to database
            saved_count = 0
            for article in analysis_result['articles']:
                try:
                    # Parse published date
                    published_at = article.get('publishedAt')
                    if published_at:
                        published_dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    else:
                        published_dt = django_timezone.now()

                    # Check if article already exists
                    existing = NewsArticle.objects.filter(url=article.get('url', '')).first()
                    if existing:
                        # Update existing article with new analysis
                        existing.sentiment_score = article.get('impact_score', 0)
                        existing.sentiment_label = 'NEGATIVE' if article.get('impact_score', 0) < -0.3 else ('POSITIVE' if article.get('impact_score', 0) > 0.3 else 'NEUTRAL')
                        existing.impact_reasoning = article.get('impact_reasoning', '')
                        existing.market_direction = article.get('market_direction', 'NEUTRAL')
                        existing.relevance_score = article.get('relevance', 0)
                        existing.impact_category = article.get('impact_category', '')
                        existing.impact_analysis = {
                            'impact_score': article.get('impact_score', 0),
                            'impact_label': article.get('impact_label', 'NEUTRAL'),
                            'impact_reasoning': article.get('impact_reasoning', ''),
                            'market_direction': article.get('market_direction', 'NEUTRAL'),
                            'relevance': article.get('relevance', 0),
                            'analyzed_at': django_timezone.now().isoformat()
                        }
                        existing.processed = True
                        existing.processed_at = django_timezone.now()
                        existing.save()
                    else:
                        # Create new article with analysis
                        NewsArticle.objects.create(
                            title=article.get('title', '')[:500],
                            source=article.get('source', {}).get('name', 'GNews')[:100],
                            author='',
                            published_at=published_dt,
                            url=article.get('url', ''),
                            image_url=article.get('image', ''),
                            summary=article.get('description', '')[:1000],
                            content=article.get('content', ''),
                            category='Market',
                            news_type='MARKET',
                            tags=[],
                            symbols_mentioned=[],
                            sectors_mentioned=[],
                            search_keywords=[article.get('search_keyword', '')] if article.get('search_keyword') else keywords_used[:3],
                            sentiment_score=article.get('impact_score', 0),
                            sentiment_label='NEGATIVE' if article.get('impact_score', 0) < -0.3 else ('POSITIVE' if article.get('impact_score', 0) > 0.3 else 'NEUTRAL'),
                            impact_reasoning=article.get('impact_reasoning', ''),
                            market_direction=article.get('market_direction', 'NEUTRAL'),
                            relevance_score=article.get('relevance', 0),
                            impact_category=article.get('impact_category', ''),
                            impact_analysis={
                                'impact_score': article.get('impact_score', 0),
                                'impact_label': article.get('impact_label', 'NEUTRAL'),
                                'impact_reasoning': article.get('impact_reasoning', ''),
                                'market_direction': article.get('market_direction', 'NEUTRAL'),
                                'relevance': article.get('relevance', 0),
                                'analyzed_at': django_timezone.now().isoformat()
                            },
                            processed=True,
                            processed_at=django_timezone.now()
                        )
                    saved_count += 1
                except Exception as save_error:
                    logger.warning(f"[Market News] Error saving article: {save_error}")
                    continue

            logger.info(f"[Market News] Saved/updated {saved_count} articles to database")

            # Fetch historical market news from database (top 5 most impactful)
            historical_market_news = get_historical_market_news(limit=5)

            return JsonResponse({
                'success': True,
                'articles': analysis_result['articles'],
                'summary': analysis_result['summary'],
                'category_breakdown': analysis_result['category_breakdown'],
                'historical_news': historical_market_news
            })

        except Exception as e:
            logger.error(f"[Market News] Error: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    # For regular page load, render the template (data will be loaded via AJAX)
    return render(request, 'trading/market_news_dashboard.html', context)


@login_required
def stream_market_news(request):
    """
    Stream market news analysis using Server-Sent Events (SSE).

    Articles are analyzed in batches and sent to the client progressively,
    allowing the UI to display results as they become available.

    Returns:
        StreamingHttpResponse with SSE events
    """
    from apps.data.services.gnews_client import get_gnews_client
    from apps.llm.services.news_impact_analyzer import get_news_impact_analyzer
    from apps.data.models import NewsArticle
    from datetime import datetime, timedelta
    from django.utils import timezone as django_timezone

    def generate_events():
        try:
            logger.info("[Market News Stream] Starting streaming news analysis")

            # Check if we have recent market news in database (within 8 hours)
            cache_hours = 8
            cache_cutoff = django_timezone.now() - timedelta(hours=cache_hours)

            cached_articles = NewsArticle.objects.filter(
                news_type='MARKET',
                processed=True,
                processed_at__gte=cache_cutoff
            ).exclude(
                sentiment_score__isnull=True
            ).order_by('-relevance_score', 'sentiment_score')[:20]

            if cached_articles.exists():
                logger.info(f"[Market News Stream] Using {cached_articles.count()} cached articles (processed within {cache_hours} hours)")

                yield f"data: {json.dumps({'type': 'status', 'message': 'Loading cached news analysis...'})}\n\n"

                # Convert database articles to response format
                articles_data = []
                category_counts = {}

                for article in cached_articles:
                    impact_category = article.impact_category or 'Other'
                    category_counts[impact_category] = category_counts.get(impact_category, 0) + 1

                    articles_data.append({
                        'title': article.title,
                        'description': article.summary,
                        'content': article.content,
                        'url': article.url,
                        'image': article.image_url,
                        'publishedAt': article.published_at.isoformat() if article.published_at else None,
                        'source': {'name': article.source, 'url': ''},
                        'impact_score': article.sentiment_score,
                        'impact_label': article.sentiment_label,
                        'impact_reasoning': article.impact_reasoning,
                        'market_direction': article.market_direction,
                        'relevance': article.relevance_score,
                        'impact_category': impact_category,
                    })

                # Calculate summary
                scores = [a.sentiment_score for a in cached_articles if a.sentiment_score is not None]
                avg_score = sum(scores) / len(scores) if scores else 0
                positive_count = sum(1 for s in scores if s > 0.3)
                negative_count = sum(1 for s in scores if s < -0.3)

                # Determine market outlook
                if avg_score > 0.2:
                    market_outlook = 'BULLISH'
                elif avg_score < -0.2:
                    market_outlook = 'BEARISH'
                else:
                    market_outlook = 'NEUTRAL'

                historical_market_news = get_historical_market_news(limit=5)

                # Send complete event with cached data
                yield f"data: {json.dumps({'type': 'complete', 'articles': articles_data, 'summary': {'total_analyzed': len(articles_data), 'average_impact_score': round(avg_score, 2), 'positive_count': positive_count, 'negative_count': negative_count, 'neutral_count': len(scores) - positive_count - negative_count, 'bullish_count': positive_count, 'bearish_count': negative_count, 'market_outlook': market_outlook}, 'category_breakdown': category_counts, 'historical_news': historical_market_news, 'cached': True, 'cache_age_hours': cache_hours})}\n\n"
                return

            # No cached articles, fetch fresh ones
            logger.info("[Market News Stream] No cached articles found, fetching fresh market news")

            # Send initial status
            yield f"data: {json.dumps({'type': 'status', 'message': 'Fetching market news...'})}\n\n"

            # Fetch market news from GNews API
            gnews = get_gnews_client()
            news_result = gnews.fetch_market_news(
                max_results_per_keyword=8,
                use_cache=True
            )

            if not news_result.get('success'):
                yield f"data: {json.dumps({'type': 'error', 'error': news_result.get('error', 'Failed to fetch news')})}\n\n"
                return

            articles = news_result.get('articles', [])
            keywords_used = news_result.get('keywords_used', [])
            logger.info(f"[Market News Stream] Fetched {len(articles)} articles, starting analysis...")

            yield f"data: {json.dumps({'type': 'status', 'message': f'Analyzing {len(articles)} articles...', 'total': len(articles)})}\n\n"

            # Analyze articles with streaming
            analyzer = get_news_impact_analyzer()
            all_analyzed = []

            for batch_result in analyzer.analyze_market_news_streaming(
                articles=articles,
                batch_size=5,
                top_n=20
            ):
                if batch_result['type'] == 'batch':
                    # Send batch of articles
                    all_analyzed.extend(batch_result['articles'])
                    yield f"data: {json.dumps(batch_result)}\n\n"

                elif batch_result['type'] == 'complete':
                    # Save articles to database
                    saved_count = 0
                    for article in batch_result['articles']:
                        try:
                            published_at = article.get('publishedAt')
                            if published_at:
                                published_dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                            else:
                                published_dt = django_timezone.now()

                            existing = NewsArticle.objects.filter(url=article.get('url', '')).first()
                            if existing:
                                existing.sentiment_score = article.get('impact_score', 0)
                                existing.sentiment_label = 'NEGATIVE' if article.get('impact_score', 0) < -0.3 else ('POSITIVE' if article.get('impact_score', 0) > 0.3 else 'NEUTRAL')
                                existing.impact_reasoning = article.get('impact_reasoning', '')
                                existing.market_direction = article.get('market_direction', 'NEUTRAL')
                                existing.relevance_score = article.get('relevance', 0)
                                existing.impact_category = article.get('impact_category', '')
                                existing.impact_analysis = {
                                    'impact_score': article.get('impact_score', 0),
                                    'impact_label': article.get('impact_label', 'NEUTRAL'),
                                    'impact_reasoning': article.get('impact_reasoning', ''),
                                    'market_direction': article.get('market_direction', 'NEUTRAL'),
                                    'relevance': article.get('relevance', 0),
                                    'analyzed_at': django_timezone.now().isoformat()
                                }
                                existing.processed = True
                                existing.processed_at = django_timezone.now()
                                existing.save()
                            else:
                                NewsArticle.objects.create(
                                    title=article.get('title', '')[:500],
                                    source=article.get('source', {}).get('name', 'GNews')[:100],
                                    author='',
                                    published_at=published_dt,
                                    url=article.get('url', ''),
                                    image_url=article.get('image', ''),
                                    summary=article.get('description', '')[:1000],
                                    content=article.get('content', ''),
                                    category='Market',
                                    news_type='MARKET',
                                    tags=[],
                                    symbols_mentioned=[],
                                    sectors_mentioned=[],
                                    search_keywords=[article.get('search_keyword', '')] if article.get('search_keyword') else keywords_used[:3],
                                    sentiment_score=article.get('impact_score', 0),
                                    sentiment_label='NEGATIVE' if article.get('impact_score', 0) < -0.3 else ('POSITIVE' if article.get('impact_score', 0) > 0.3 else 'NEUTRAL'),
                                    impact_reasoning=article.get('impact_reasoning', ''),
                                    market_direction=article.get('market_direction', 'NEUTRAL'),
                                    relevance_score=article.get('relevance', 0),
                                    impact_category=article.get('impact_category', ''),
                                    impact_analysis={
                                        'impact_score': article.get('impact_score', 0),
                                        'impact_label': article.get('impact_label', 'NEUTRAL'),
                                        'impact_reasoning': article.get('impact_reasoning', ''),
                                        'market_direction': article.get('market_direction', 'NEUTRAL'),
                                        'relevance': article.get('relevance', 0),
                                        'analyzed_at': django_timezone.now().isoformat()
                                    },
                                    processed=True,
                                    processed_at=django_timezone.now()
                                )
                            saved_count += 1
                        except Exception as save_error:
                            logger.warning(f"[Market News Stream] Error saving article: {save_error}")
                            continue

                    logger.info(f"[Market News Stream] Saved/updated {saved_count} articles to database")

                    # Fetch historical market news
                    historical_market_news = get_historical_market_news(limit=5)

                    # Send complete result
                    yield f"data: {json.dumps({'type': 'complete', 'articles': batch_result['articles'], 'summary': batch_result['summary'], 'category_breakdown': batch_result['category_breakdown'], 'historical_news': historical_market_news})}\n\n"

            logger.info("[Market News Stream] Stream complete")

        except Exception as e:
            logger.error(f"[Market News Stream] Error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    response = StreamingHttpResponse(
        generate_events(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
