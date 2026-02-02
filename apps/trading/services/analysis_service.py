"""
Analysis Service - Unified analysis orchestrator for futures trading

This module provides a unified entry point for running enhanced
futures analysis, combining:
- enhanced_futures_analysis() from futures_analyzer (12-component scoring)
- prepare_data_for_analysis() for historical data
- News verification
- Analyst report verification

This eliminates code duplication between algorithm_views.py and
verification_views.py by providing a single run_full_analysis() function.

The enhanced analysis includes:
- 12 scoring components (OI, Technical, Trend, Volume, Institutional, etc.)
- 7 hard reject filters (MWPL, Volatility, Piotroski, etc.)
- Pass threshold: 65/100 (vs legacy 50/100)
"""

import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, Union
import json

logger = logging.getLogger(__name__)


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def clean_numeric_value(obj):
    """Convert NaN and Infinity to None for JSON compatibility."""
    import math
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
    """Recursively clean dictionary to remove NaN and Infinity values."""
    if isinstance(data, dict):
        return {k: clean_dict_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_dict_for_json(item) for item in data]
    else:
        return clean_numeric_value(data)


def run_basic_analysis(
    stock_symbol: str,
    expiry_date: str,
    contract=None
) -> Dict[str, Any]:
    """
    Run enhanced 12-component analysis on a contract.

    This is the core analysis used by both futures algorithm and verify trade.
    It runs enhanced_futures_analysis() which includes:
    - 12 scoring components (vs legacy 7)
    - 7 hard reject filters (MWPL, Volatility, Piotroski, etc.)
    - Pass threshold: 65/100

    Args:
        stock_symbol: Stock symbol (e.g., 'RELIANCE')
        expiry_date: Expiry date in YYYY-MM-DD format
        contract: Optional ContractData model instance

    Returns:
        dict: {
            'success': bool,
            'verdict': 'PASS'|'FAIL'|'ERROR',
            'direction': 'LONG'|'SHORT'|'NEUTRAL',
            'composite_score': float,
            'metrics': dict,
            'scores': dict,
            'execution_log': list,
            'explanation': list,
            'error': str (if failed)
        }
    """
    from apps.trading.futures_analyzer import enhanced_futures_analysis

    try:
        logger.info(f"Running basic analysis for {stock_symbol} (expiry: {expiry_date})")

        analysis_result = enhanced_futures_analysis(
            stock_symbol=stock_symbol,
            expiry_date=expiry_date,
            contract=contract
        )

        # Extract metrics
        metrics = analysis_result.get('metrics', {})
        composite_score = analysis_result.get('composite_score', 0)
        direction = analysis_result.get('direction', 'NEUTRAL')
        verdict = analysis_result.get('verdict', 'FAIL')
        success = analysis_result.get('success', False)
        execution_log = analysis_result.get('execution_log', [])
        scores = analysis_result.get('scores', {})

        # Build explanation from execution log
        explanation_parts = []
        for log in execution_log:
            if log['action'] == 'Open Interest Analysis' and log['status'] != 'SKIP':
                explanation_parts.append(f"OI: {log['message']}")
            elif log['action'] == 'Sector Strength' and log['status'] != 'SKIP':
                explanation_parts.append(f"Sector: {log['message']}")
            elif log['action'] == 'Multi-Factor Technical Analysis' and log['status'] != 'SKIP':
                explanation_parts.append(f"Technical: {log['message']}")
            elif log['action'] == 'DMA Analysis' and log['status'] != 'SKIP':
                explanation_parts.append(f"DMA: {log['message']}")
            elif log['action'] == 'Composite Scoring & Verdict':
                explanation_parts.append(f"Final: {log['message']}")

        return {
            'success': success,
            'verdict': verdict,
            'direction': direction,
            'composite_score': composite_score,
            'metrics': metrics,
            'scores': scores,
            'execution_log': execution_log,
            'explanation': explanation_parts,
            'sr_data': metrics.get('sr_details'),
            'breach_risks': analysis_result.get('breach_risks'),
            'error': analysis_result.get('error') if not success else None
        }

    except Exception as e:
        logger.error(f"Error in basic analysis for {stock_symbol}: {e}", exc_info=True)
        return {
            'success': False,
            'verdict': 'ERROR',
            'direction': 'NEUTRAL',
            'composite_score': 0,
            'metrics': {},
            'scores': {},
            'execution_log': [],
            'explanation': [f"Analysis failed: {str(e)[:200]}"],
            'error': str(e)
        }


def run_historical_verification(
    stock_symbol: str,
    expiry_date: str,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Run historical data verification for a contract.

    This prepares historical data and runs risk checks:
    1. Checks if recent data exists (< 5 minutes old)
    2. If not, discovers instruments and fetches historical data
    3. Saves data to HistoricalPrice model
    4. Runs verification/risk checks

    Args:
        stock_symbol: Stock symbol
        expiry_date: Expiry date in YYYY-MM-DD format
        force_refresh: Force data refresh even if cached

    Returns:
        dict: {
            'success': bool,
            'trade_allowed': bool,
            'verdict': 'PASS'|'WARNING'|'BLOCKED',
            'verdict_message': str,
            'risk_checks': list,
            'risk_summary': dict,
            'recommendations': list,
            'data_collection': dict
        }
    """
    from apps.trading.futures_analyzer import prepare_data_for_analysis

    try:
        logger.info(f"Running historical verification for {stock_symbol} (expiry: {expiry_date})")

        data_prep_result = prepare_data_for_analysis(
            stock_symbol=stock_symbol,
            expiry_date=expiry_date,
            force_refresh=force_refresh,
            include_options=False  # Skip options for faster verification
        )

        if data_prep_result.get('success'):
            # Log collection summary
            data_collection = data_prep_result.get('data_collection', {})
            if data_collection.get('skipped'):
                logger.info(f"Historical data: Using cached data ({data_collection.get('reason', 'recent')})")
            else:
                summary = data_collection.get('summary', {})
                logger.info(f"Historical data collected: {summary.get('total_records_saved', 0)} records")

            # Get verification result
            historical_verification = data_prep_result.get('verification', {})
            logger.info(f"Historical verification: {historical_verification.get('verdict', 'N/A')}")

            return {
                'success': True,
                'trade_allowed': historical_verification.get('trade_allowed', True),
                'verdict': historical_verification.get('verdict', 'N/A'),
                'verdict_message': historical_verification.get('verdict_message', ''),
                'risk_checks': historical_verification.get('risk_checks', []),
                'risk_summary': historical_verification.get('risk_summary', {}),
                'recommendations': historical_verification.get('recommendations', []),
                'analysis': historical_verification.get('analysis', {}),
                'data_collection': data_collection
            }
        else:
            logger.error(f"Historical data preparation failed: {data_prep_result.get('error')}")
            return {
                'success': False,
                'trade_allowed': False,
                'verdict': 'BLOCKED',
                'verdict_message': f"Data preparation failed: {data_prep_result.get('error', 'Unknown error')}",
                'risk_checks': [{
                    'id': 'data_prep_failed',
                    'name': 'Data Preparation Failed',
                    'status': 'FAIL',
                    'severity': 'HIGH',
                    'message': data_prep_result.get('error', 'Unknown error')
                }],
                'risk_summary': {'total_checks': 1, 'passed': 0, 'failed': 1},
                'recommendations': ['Check Breeze API connectivity and try again']
            }

    except Exception as e:
        logger.error(f"Error in historical verification for {stock_symbol}: {e}", exc_info=True)
        return {
            'success': False,
            'trade_allowed': False,
            'verdict': 'BLOCKED',
            'verdict_message': f"Historical verification error: {str(e)}",
            'risk_checks': [{
                'id': 'data_prep_error',
                'name': 'Data Preparation Error',
                'status': 'FAIL',
                'severity': 'HIGH',
                'message': str(e)
            }],
            'risk_summary': {'total_checks': 1, 'passed': 0, 'failed': 1},
            'recommendations': ['Check server logs for details']
        }


def run_news_verification(
    stock_symbol: str,
    direction: str,
    stock_name: Optional[str] = None,
    industry_name: Optional[str] = None,
    max_articles: int = 5
) -> Dict[str, Any]:
    """
    Run news impact verification for a stock.

    Fetches and analyzes news to detect potential trade blockers.

    Args:
        stock_symbol: Stock symbol
        direction: Trade direction ('LONG' or 'SHORT')
        stock_name: Full stock name for broader search
        industry_name: Industry name for sector news
        max_articles: Maximum articles to analyze

    Returns:
        dict: {
            'success': bool,
            'trade_allowed': bool,
            'blocking_articles': list,
            'warning_articles': list,
            'summary': dict,
            'stock_news': dict
        }
    """
    news_verification = {
        'success': False,
        'trade_allowed': True,
        'blocking_articles': [],
        'warning_articles': [],
        'summary': {},
        'stock_news': {}
    }

    try:
        from apps.data.services.gnews_client import get_gnews_client
        from apps.data.models import TLStockData
        from apps.llm.services.news_impact_analyzer import get_news_impact_analyzer

        logger.info(f"Running news verification for {stock_symbol} ({direction} trade)")

        # Get stock details if not provided
        if not stock_name or not industry_name:
            stock_data = TLStockData.objects.filter(nsecode=stock_symbol).first()
            stock_name = stock_name or (stock_data.stock_name if stock_data else stock_symbol)
            industry_name = industry_name or (stock_data.industry_name if stock_data else None)

        # Fetch stock news
        gnews = get_gnews_client()
        stock_news_result = gnews.fetch_stock_news(
            stock_symbol=stock_symbol,
            stock_name=stock_name,
            max_results=max_articles
        )

        # Analyze news impact
        if stock_news_result.get('articles'):
            analyzer = get_news_impact_analyzer()
            impact_result = analyzer.analyze_news_for_trade(
                stock_news={'articles': stock_news_result.get('articles', [])},
                industry_news={'articles': []},
                competitor_news={'articles': []},
                stock_symbol=stock_symbol,
                stock_name=stock_name,
                trade_direction=direction,
                industry_name=industry_name,
                max_articles_per_category=max_articles
            )

            news_verification = {
                'success': True,
                'trade_allowed': impact_result['trade_allowed'],
                'blocking_articles': impact_result['blocking_articles'],
                'warning_articles': impact_result['warning_articles'],
                'summary': impact_result['summary'],
                'stock_news': impact_result['stock_news']
            }

            logger.info(f"News impact: trade_allowed={impact_result['trade_allowed']}, "
                       f"blocking={len(impact_result['blocking_articles'])}")
        else:
            logger.info(f"No news articles found for {stock_symbol}")
            news_verification['success'] = True

    except Exception as e:
        logger.warning(f"News verification failed: {e}")
        news_verification['error'] = str(e)

    return news_verification


def run_analyst_verification(
    stock_symbol: str,
    direction: str,
    current_price: Optional[float] = None
) -> Dict[str, Any]:
    """
    Run analyst report verification for a stock.

    Checks analyst price targets and recommendations.

    Args:
        stock_symbol: Stock symbol
        direction: Trade direction
        current_price: Current price for upside calculation

    Returns:
        dict: {
            'success': bool,
            'trade_allowed': bool,
            'blocking_reasons': list,
            'warnings': list,
            'price_target': dict,
            'reports_summary': dict,
            'recommendation': str
        }
    """
    analyst_verification = {
        'success': False,
        'trade_allowed': True,
        'blocking_reasons': [],
        'warnings': [],
        'price_target': None,
        'reports_summary': None,
        'recommendation': 'PROCEED',
        'data_source': 'none'
    }

    try:
        from apps.llm.services.analyst_report_aggregator import get_analyst_report_aggregator

        logger.info(f"Running analyst verification for {stock_symbol}")

        aggregator = get_analyst_report_aggregator()
        analyst_result = aggregator.aggregate_for_trade(
            symbol=stock_symbol,
            direction=direction,
            current_price=current_price,
            nse_code=stock_symbol,
            refresh_if_stale=False
        )

        analyst_verification = {
            'success': True,
            'trade_allowed': analyst_result.get('trade_allowed', True),
            'blocking_reasons': analyst_result.get('blocking_reasons', []),
            'warnings': analyst_result.get('warnings', []),
            'price_target': analyst_result.get('price_target'),
            'reports_summary': analyst_result.get('reports_summary'),
            'top_blocking_reports': analyst_result.get('top_blocking_reports', []),
            'recommendation': analyst_result.get('recommendation', 'PROCEED'),
            'rules_checked': analyst_result.get('rules_checked', []),
            'data_source': 'database'
        }

        logger.info(f"Analyst verification: trade_allowed={analyst_result.get('trade_allowed')}")

    except Exception as e:
        logger.warning(f"Analyst verification failed: {e}")
        analyst_verification['error'] = str(e)
        analyst_verification['warnings'].append(f"Analyst verification unavailable: {str(e)}")

    return analyst_verification


def run_full_analysis(
    stock_symbol: str,
    expiry_date: str,
    contract=None,
    include_historical: bool = True,
    include_news: bool = True,
    include_analyst: bool = True,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Run complete analysis for a futures contract.

    This is the unified analysis function that combines all verification steps:
    1. Basic 9-step technical analysis
    2. Historical data verification (optional)
    3. News impact analysis (optional)
    4. Analyst report verification (optional)

    Args:
        stock_symbol: Stock symbol
        expiry_date: Expiry date in YYYY-MM-DD format
        contract: Optional ContractData model instance
        include_historical: Run historical verification
        include_news: Run news verification
        include_analyst: Run analyst verification
        force_refresh: Force data refresh

    Returns:
        dict: {
            'success': bool,
            'passed': bool,  # Overall pass/fail
            'verdict': str,
            'direction': str,
            'composite_score': float,
            'analysis': dict,  # Basic analysis results
            'historical_verification': dict,
            'news_verification': dict,
            'analyst_verification': dict,
            'execution_log': list
        }
    """
    logger.info(f"Running full analysis for {stock_symbol} (expiry: {expiry_date})")

    # Step 1: Basic technical analysis
    basic_analysis = run_basic_analysis(stock_symbol, expiry_date, contract)

    if not basic_analysis['success']:
        return {
            'success': False,
            'passed': False,
            'verdict': 'ERROR',
            'direction': 'NEUTRAL',
            'composite_score': 0,
            'analysis': basic_analysis,
            'error': basic_analysis.get('error', 'Analysis failed')
        }

    analysis_passed = basic_analysis['verdict'] == 'PASS'
    direction = basic_analysis['direction']
    composite_score = basic_analysis['composite_score']

    # Initialize verification results
    historical_verification = {'success': True, 'trade_allowed': True}
    news_verification = {'success': True, 'trade_allowed': True}
    analyst_verification = {'success': True, 'trade_allowed': True}

    # Step 2: Historical verification (if enabled and analysis passed)
    if include_historical and analysis_passed:
        historical_verification = run_historical_verification(
            stock_symbol, expiry_date, force_refresh
        )

    # Step 3: News verification (if enabled and previous checks passed)
    historical_passed = historical_verification.get('trade_allowed', True)
    if include_news and analysis_passed and historical_passed:
        news_verification = run_news_verification(
            stock_symbol=stock_symbol,
            direction=direction
        )

    # Step 4: Analyst verification (if enabled and previous checks passed)
    news_passed = news_verification.get('trade_allowed', True)
    if include_analyst and analysis_passed and historical_passed and news_passed:
        futures_price = basic_analysis['metrics'].get('futures_price', 0)
        analyst_verification = run_analyst_verification(
            stock_symbol=stock_symbol,
            direction=direction,
            current_price=float(futures_price) if futures_price else None
        )

    # Determine overall pass/fail
    analyst_passed = analyst_verification.get('trade_allowed', True)
    passed = analysis_passed and historical_passed and news_passed and analyst_passed

    # Build verdict message
    if passed:
        verdict_text = f'PASS - Score: {composite_score}/100'
    elif not analysis_passed:
        verdict_text = f'FAIL - Score: {composite_score}/100'
    elif not historical_passed:
        verdict_text = 'BLOCKED - Historical Risk Check Failed'
    elif not news_passed:
        verdict_text = 'BLOCKED - Negative News Detected'
    else:
        verdict_text = 'BLOCKED - Analyst Reports'

    logger.info(f"Full analysis complete for {stock_symbol}: {verdict_text}")

    return {
        'success': True,
        'passed': passed,
        'verdict': verdict_text,
        'direction': direction,
        'composite_score': composite_score,
        'analysis': basic_analysis,
        'metrics': basic_analysis['metrics'],
        'scores': basic_analysis['scores'],
        'execution_log': basic_analysis['execution_log'],
        'explanation': basic_analysis['explanation'],
        'historical_verification': historical_verification,
        'news_verification': news_verification,
        'analyst_verification': analyst_verification,
        'sr_data': basic_analysis.get('sr_data'),
        'breach_risks': basic_analysis.get('breach_risks')
    }


def format_analysis_for_response(
    analysis_result: Dict[str, Any],
    contract,
    position_sizing: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Format analysis results for API response.

    Converts analysis results to the standardized response format
    used by both algorithm_views.py and verification_views.py.

    Args:
        analysis_result: Result from run_full_analysis()
        contract: ContractData model instance
        position_sizing: Optional position sizing data

    Returns:
        dict: Formatted response for frontend
    """
    basic_analysis = analysis_result.get('analysis', {})
    metrics = analysis_result.get('metrics', {})

    # Format expiry
    expiry_dt = datetime.strptime(contract.expiry, '%Y-%m-%d')
    expiry_formatted = expiry_dt.strftime('%d-%b-%Y')

    response = {
        'symbol': contract.symbol,
        'expiry': expiry_formatted,
        'expiry_date': contract.expiry,
        'verdict': analysis_result['verdict'],
        'passed': analysis_result['passed'],
        'direction': analysis_result['direction'],
        'composite_score': analysis_result['composite_score'],
        'analysis': {
            'spot_price': metrics.get('spot_price', 0),
            'contract_price': metrics.get('futures_price', 0),
            'stop_loss': position_sizing['stop_loss'] if position_sizing else 0,
            'target': position_sizing['target'] if position_sizing else 0,
            'score_breakdown': analysis_result.get('scores', {}),
            'position_details': position_sizing.get('position_details') if position_sizing else {}
        },
        'historical_verification': analysis_result.get('historical_verification', {}),
        'news_verification': analysis_result.get('news_verification', {}),
        'analyst_verification': analysis_result.get('analyst_verification', {}),
        'execution_log': analysis_result.get('execution_log', [])
    }

    if position_sizing:
        response['position_sizing'] = position_sizing

    return response
