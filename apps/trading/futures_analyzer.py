"""
Comprehensive Futures Analysis with Breeze API Integration

9-Step Analysis Framework:
1. Real-Time Price Fetch (Breeze)
2. Basis & Cost of Carry
3. Open Interest Analysis
4. DMA Analysis (20, 50, 200)
5. Sector Strength
6. Volume & Liquidity
7. Technical Indicators (RSI, MACD, BB)
8. Support/Resistance Levels
9. Composite Scoring & Verdict
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from django.core.cache import cache
from apps.brokers.integrations.breeze import get_breeze_client
from apps.data.data_analyzers import (
    OpenInterestAnalyzer,
    DMAAnalyzer
)
from apps.strategies.filters.sector_filter import analyze_sector
from apps.data.models import ContractStockData, ContractData, TLStockData

logger = logging.getLogger(__name__)


def resolve_breeze_symbol(stock_symbol: str, expiry_date: str) -> Dict:
    """
    Resolve the correct Breeze stock code using get_names API

    Args:
        stock_symbol: Stock symbol (e.g., 'RELIANCE')
        expiry_date: Expiry date in YYYY-MM-DD format

    Returns:
        dict: {
            'success': bool,
            'stock_code': str (if found),
            'exchange_code': str,
            'error': str (if failed)
        }
    """
    try:
        # Check cache first (cache for 1 hour)
        cache_key = f"breeze_symbol_{stock_symbol}_{expiry_date}"
        cached_result = cache.get(cache_key)

        if cached_result:
            logger.info(f"Using cached Breeze symbol: {cached_result}")
            return cached_result

        breeze = get_breeze_client()

        # Format expiry for search: DD-MMM-YY (e.g., 25-NOV-24)
        expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
        expiry_search = expiry_dt.strftime('%d%b%y').upper()  # e.g., "25NOV24"

        # Search for futures contract
        # Breeze get_names expects: exchange_code, stock_code
        # First try with exact symbol
        logger.info(f"Searching Breeze for symbol: {stock_symbol}, expiry: {expiry_search}")

        try:
            # Try NFO futures search
            names_resp = breeze.get_names(
                exchange_code="NFO",
                stock_code=stock_symbol
            )

            # Log the first few results for debugging
            if names_resp and names_resp.get("Status") == 200 and names_resp.get("Success"):
                results_sample = names_resp["Success"][:3] if names_resp["Success"] else []
                logger.info(f"Breeze get_names for {stock_symbol}: found {len(names_resp['Success'])} contracts")
                for r in results_sample:
                    logger.info(f"  Sample: stock_code={r.get('stock_code')}, short_name={r.get('short_name')}, expiry={r.get('expiry_date')}")
            else:
                logger.warning(f"Breeze get_names response: {names_resp}")

            if names_resp and names_resp.get("Status") == 200 and names_resp.get("Success"):
                results = names_resp["Success"]

                # Look for futures contract matching our expiry
                for item in results:
                    # Check if it's a futures contract (not option)
                    if 'FUT' in item.get('stock_code', '') or item.get('right', '') == 'others':
                        # Check if expiry matches
                        item_expiry = item.get('expiry_date', '')
                        if expiry_search in item_expiry or expiry_date in item_expiry:
                            result = {
                                'success': True,
                                'stock_code': item.get('stock_code', stock_symbol),
                                'exchange_code': 'NFO',
                                'short_name': item.get('short_name', stock_symbol),
                                'expiry_date': item.get('expiry_date', ''),
                                'lot_size': item.get('lot_size', 0)
                            }

                            # Cache for 5 minutes (reduced for debugging)
                            cache.set(cache_key, result, 300)
                            logger.info(f"Resolved Breeze symbol: {result}")
                            return result

                # If exact match not found, try first result
                if results:
                    first_result = results[0]
                    result = {
                        'success': True,
                        'stock_code': first_result.get('stock_code', stock_symbol),
                        'exchange_code': 'NFO',
                        'short_name': first_result.get('short_name', stock_symbol),
                        'expiry_date': first_result.get('expiry_date', ''),
                        'lot_size': first_result.get('lot_size', 0),
                        'note': 'Expiry not exact match - using first available'
                    }

                    cache.set(cache_key, result, 300)  # 5 minutes for debugging
                    logger.warning(f"Using first available contract: {result}")
                    return result

            # If get_names failed, fallback to original symbol
            logger.warning(f"get_names failed for {stock_symbol}, using original symbol")
            result = {
                'success': True,
                'stock_code': stock_symbol,
                'exchange_code': 'NFO',
                'short_name': stock_symbol,
                'note': 'Fallback to original symbol'
            }
            return result

        except Exception as e:
            logger.error(f"Error in get_names API: {e}")
            # Fallback to original symbol
            result = {
                'success': True,
                'stock_code': stock_symbol,
                'exchange_code': 'NFO',
                'short_name': stock_symbol,
                'error': str(e),
                'note': 'Fallback due to API error'
            }
            return result

    except Exception as e:
        logger.error(f"Error resolving Breeze symbol: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def comprehensive_futures_analysis(
    stock_symbol: str,
    expiry_date: str,
    contract: Optional[ContractData] = None
) -> Dict:
    """
    Comprehensive 9-step futures analysis using Breeze API

    Returns:
        dict: {
            'success': bool,
            'execution_log': list of step-by-step analysis,
            'metrics': dict of all calculated metrics,
            'verdict': 'PASS' or 'FAIL',
            'direction': 'LONG', 'SHORT', or 'NEUTRAL',
            'composite_score': int (0-100),
            'analysis': detailed analysis dict
        }
    """

    logger.info("=" * 100)
    logger.info(f"COMPREHENSIVE FUTURES ANALYSIS: {stock_symbol} (Expiry: {expiry_date})")
    logger.info("=" * 100)

    execution_log = []
    metrics = {}
    scores = {}

    # ============================================================================
    # DATA FRESHNESS CHECK: Ensure Trendlyne data is not stale (>30 mins old)
    # ============================================================================
    logger.info("\n" + "=" * 80)
    logger.info("PRE-CHECK: Data Freshness Verification")
    logger.info("=" * 80)

    try:
        from apps.data.utils.data_freshness import ensure_fresh_data

        freshness_result = ensure_fresh_data(force=False)

        if freshness_result['update_triggered']:
            logger.warning("⚠️  Stale data detected! Update triggered in background.")
            logger.warning(f"    Age: {freshness_result['freshness_status']['oldest_age_minutes']:.1f} minutes")
            logger.warning("    Analysis will proceed with current data. Retry in 2-3 minutes for updated results.")

            execution_log.append({
                'step': 0,
                'action': 'Data Freshness Check',
                'status': 'WARNING',
                'message': f"Data is {freshness_result['freshness_status']['oldest_age_minutes']:.1f} min old. Update triggered.",
                'details': {
                    'update_triggered': True,
                    'age_minutes': freshness_result['freshness_status']['oldest_age_minutes'],
                    'threshold_minutes': 30,
                    'recommendation': 'Retry analysis in 2-3 minutes for fresh data'
                }
            })
        else:
            logger.info(f"✅ Data is fresh (age: {freshness_result['freshness_status']['oldest_age_minutes']:.1f} minutes)")

            execution_log.append({
                'step': 0,
                'action': 'Data Freshness Check',
                'status': 'PASS',
                'message': f"Data is fresh ({freshness_result['freshness_status']['oldest_age_minutes']:.1f} min old)",
                'details': {
                    'update_triggered': False,
                    'age_minutes': freshness_result['freshness_status']['oldest_age_minutes'],
                    'threshold_minutes': 30
                }
            })

    except Exception as freshness_error:
        logger.warning(f"Data freshness check failed: {freshness_error}")
        execution_log.append({
            'step': 0,
            'action': 'Data Freshness Check',
            'status': 'SKIP',
            'message': f'Freshness check unavailable: {str(freshness_error)[:100]}',
            'details': {'error': str(freshness_error)}
        })

    try:
        # ============================================================================
        # STEP 0: Resolve Breeze Symbol using SecurityMaster (preferred) or get_names API
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 0: Resolving Breeze Symbol")
        logger.info("=" * 80)

        from apps.brokers.utils.security_master import get_futures_instrument

        # Format expiry for SecurityMaster lookup: DD-MMM-YYYY
        expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
        expiry_formatted_sm = expiry_dt.strftime('%d-%b-%Y')

        logger.info(f"Looking up SecurityMaster for {stock_symbol} expiry {expiry_formatted_sm}")

        # Try SecurityMaster first (most reliable source for Breeze codes)
        instrument_info = get_futures_instrument(stock_symbol, expiry_formatted_sm)
        symbol_resolution = None
        breeze_symbol = stock_symbol
        lot_size = 0

        if instrument_info and instrument_info.get('short_name'):
            breeze_symbol = instrument_info['short_name']
            lot_size = instrument_info.get('lot_size', 0)
            logger.info(f"SecurityMaster: {stock_symbol} -> {breeze_symbol} (lot_size: {lot_size})")
            symbol_resolution = {
                'success': True,
                'short_name': breeze_symbol,
                'stock_code': instrument_info.get('exchange_code', stock_symbol),
                'lot_size': lot_size,
                'expiry_date': instrument_info.get('expiry_date', ''),
                'source': instrument_info.get('source', 'security_master')
            }
        else:
            # Fallback to get_names API
            logger.warning(f"SecurityMaster lookup failed, trying get_names API...")
            symbol_resolution = resolve_breeze_symbol(stock_symbol, expiry_date)

            if symbol_resolution.get('success'):
                breeze_symbol = symbol_resolution.get('short_name', stock_symbol)
                lot_size = symbol_resolution.get('lot_size', 0)
                logger.info(f"get_names API: {stock_symbol} -> {breeze_symbol}")
            else:
                logger.warning(f"All resolution methods failed, using original symbol: {stock_symbol}")
                symbol_resolution = {'success': True, 'short_name': stock_symbol, 'note': 'Fallback to original'}

        resolved_expiry = symbol_resolution.get('expiry_date', '')

        execution_log.append({
            'step': 0,
            'action': 'Symbol Resolution',
            'status': 'PASS',
            'message': f"Resolved to Breeze code: {breeze_symbol}",
            'details': {
                'original_symbol': stock_symbol,
                'breeze_symbol': breeze_symbol,
                'stock_code': symbol_resolution.get('stock_code', ''),
                'short_name': symbol_resolution.get('short_name', ''),
                'resolved_expiry': resolved_expiry,
                'lot_size': symbol_resolution.get('lot_size', 0),
                'note': symbol_resolution.get('note', 'Exact match found')
            }
        })

        logger.info(f"Resolved symbol: {stock_symbol} -> {breeze_symbol} (short_name for Breeze API)")

        # ============================================================================
        # STEP 1: Real-Time Price Fetch from Breeze API
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Fetching Real-Time Prices from Breeze API")
        logger.info("=" * 80)

        breeze = get_breeze_client()

        logger.info(f"Fetching quotes for: {breeze_symbol} (Original: {stock_symbol})")

        # Fetch spot price with error handling and fallback
        spot_price = 0.0
        spot_data = {}
        spot_error = None
        spot_source = "Breeze API (Live)"

        try:
            spot_resp = breeze.get_quotes(
                stock_code=breeze_symbol,
                exchange_code="NSE",
                product_type="cash",
                expiry_date="",
                right="",
                strike_price=""
            )

            logger.info(f"Spot response status: {spot_resp.get('Status')}")

            if spot_resp and spot_resp.get("Status") == 200 and spot_resp.get("Success"):
                spot_data = spot_resp["Success"][0] if spot_resp["Success"] else {}
                spot_price = float(spot_data.get('ltp', 0))
                logger.info(f"✅ Spot Price: ₹{spot_price:.2f}")
            else:
                spot_error = spot_resp.get('Error', 'Unknown error')
                logger.warning(f"Spot price fetch failed: {spot_error}")
        except Exception as e:
            spot_error = str(e)
            logger.error(f"Exception fetching spot price: {e}")

        # Fallback to Trendlyne/ContractStockData if Breeze fails
        if spot_price == 0:
            try:
                stock_data = ContractStockData.objects.filter(nse_code=stock_symbol).first()
                if stock_data and stock_data.current_price:
                    spot_price = float(stock_data.current_price)
                    spot_source = "Trendlyne Stock Data (Cached)"
                    logger.info(f"✅ Using Trendlyne fallback - Spot Price: ₹{spot_price:.2f}")
                elif contract and contract.price:
                    # Use contract price as spot if stock data not available
                    spot_price = float(contract.price)
                    spot_source = "Contract Data (Cached)"
                    logger.info(f"✅ Using Contract Data fallback - Spot Price: ₹{spot_price:.2f}")
            except Exception as e:
                logger.warning(f"Trendlyne fallback also failed: {e}")

        # Fetch futures price with error handling and fallback
        # Format expiry: DD-MMM-YYYY (e.g., 28-NOV-2024)
        expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
        expiry_formatted = expiry_dt.strftime('%d-%b-%Y').upper()

        futures_price = 0.0
        futures_data = {}
        futures_error = None
        futures_source = "Breeze API (Live)"

        try:
            futures_resp = breeze.get_quotes(
                stock_code=breeze_symbol,
                exchange_code="NFO",
                product_type="futures",
                expiry_date=expiry_formatted,
                right="others",
                strike_price=""
            )

            logger.info(f"Futures response status: {futures_resp.get('Status')}")

            if futures_resp and futures_resp.get("Status") == 200 and futures_resp.get("Success"):
                futures_data = futures_resp["Success"][0] if futures_resp["Success"] else {}
                futures_price = float(futures_data.get('ltp', 0))
                logger.info(f"✅ Futures Price: ₹{futures_price:.2f}")
            else:
                futures_error = futures_resp.get('Error', 'Unknown error')
                logger.warning(f"Futures price fetch failed: {futures_error}")
        except Exception as e:
            futures_error = str(e)
            logger.error(f"Exception fetching futures price: {e}")

        # Fallback to Trendlyne/ContractData if Breeze fails
        if futures_price == 0 and contract:
            try:
                if contract.price and contract.price > 0:
                    futures_price = float(contract.price)
                    futures_source = "Trendlyne (Cached)"
                    logger.info(f"✅ Using Trendlyne fallback - Futures Price: ₹{futures_price:.2f}")
            except Exception as e:
                logger.warning(f"Trendlyne futures fallback failed: {e}")

        # If still no futures price but we have spot, estimate futures price
        if futures_price == 0 and spot_price > 0:
            # Estimate futures price as spot + 1% (typical contango)
            futures_price = spot_price * 1.01
            futures_source = "Estimated from Spot"
            logger.info(f"✅ Using estimated futures price: ₹{futures_price:.2f}")

        metrics['spot_price'] = spot_price
        metrics['futures_price'] = futures_price
        metrics['breeze_symbol'] = breeze_symbol

        step1_pass = spot_price > 0 and futures_price > 0

        # Build detailed message
        if step1_pass:
            step1_message = f"Spot: ₹{spot_price:.2f} ({spot_source}), Futures: ₹{futures_price:.2f} ({futures_source})"
            step1_details = {
                'breeze_symbol': breeze_symbol,
                'spot_price': spot_price,
                'futures_price': futures_price,
                'spot_ltp': spot_price,
                'futures_ltp': futures_price,
                'expiry_formatted': expiry_formatted,
                'spot_source': spot_source,
                'futures_source': futures_source
            }
        else:
            error_parts = []
            if spot_price == 0:
                error_parts.append(f"Spot failed: {spot_error or 'No data'}")
            if futures_price == 0:
                error_parts.append(f"Futures failed: {futures_error or 'No data'}")

            step1_message = " | ".join(error_parts)
            step1_details = {
                'breeze_symbol': breeze_symbol,
                'original_symbol': stock_symbol,
                'expiry_formatted': expiry_formatted,
                'spot_error': spot_error,
                'futures_error': futures_error,
                'spot_response_status': spot_resp.get('Status') if 'spot_resp' in locals() else 'N/A',
                'futures_response_status': futures_resp.get('Status') if 'futures_resp' in locals() else 'N/A'
            }

        execution_log.append({
            'step': 1,
            'action': 'Real-Time Price Fetch',
            'status': 'PASS' if step1_pass else 'FAIL',
            'message': step1_message,
            'details': step1_details
        })

        if not step1_pass:
            logger.error(f"Price fetch failed - Spot: {spot_error}, Futures: {futures_error}")
            return {
                'success': False,
                'execution_log': execution_log,
                'metrics': metrics,
                'verdict': 'FAIL',
                'direction': 'NEUTRAL',
                'composite_score': 0,
                'error': f'Failed to fetch prices from Breeze API. {step1_message}'
            }

        # ============================================================================
        # STEP 2: Basis and Cost of Carry Analysis
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Basis and Cost of Carry Analysis")
        logger.info("=" * 80)

        basis = futures_price - spot_price
        basis_pct = (basis / spot_price) * 100 if spot_price > 0 else 0

        # Calculate days to expiry
        today = datetime.now().date()
        days_to_expiry = (expiry_dt.date() - today).days

        # Annualized cost of carry
        if days_to_expiry > 0:
            cost_of_carry_annualized = (basis_pct / days_to_expiry) * 365
        else:
            cost_of_carry_annualized = 0

        # Interpret basis
        if basis_pct > 1.0:
            basis_signal = "CONTANGO"
            basis_interpretation = "Futures at premium - Bullish market sentiment"
            basis_score = 10
        elif basis_pct < -1.0:
            basis_signal = "BACKWARDATION"
            basis_interpretation = "Futures at discount - Bearish market sentiment"
            basis_score = 5
        else:
            basis_signal = "NEUTRAL"
            basis_interpretation = "Futures near fair value - No strong directional bias"
            basis_score = 0

        metrics['basis'] = basis
        metrics['basis_pct'] = basis_pct
        metrics['cost_of_carry'] = cost_of_carry_annualized
        metrics['days_to_expiry'] = days_to_expiry
        metrics['basis_signal'] = basis_signal
        scores['basis'] = basis_score

        execution_log.append({
            'step': 2,
            'action': 'Basis & Cost of Carry',
            'status': 'PASS',
            'message': f"{basis_signal}: ₹{basis:.2f} ({basis_pct:+.2f}%), CoC: {cost_of_carry_annualized:.2f}% p.a.",
            'details': {
                'basis': round(basis, 2),
                'basis_pct': round(basis_pct, 2),
                'cost_of_carry_annualized': round(cost_of_carry_annualized, 2),
                'days_to_expiry': days_to_expiry,
                'basis_signal': basis_signal,
                'interpretation': basis_interpretation,
                'score': basis_score
            }
        })

        logger.info(f"Basis: ₹{basis:.2f} ({basis_pct:+.2f}%)")
        logger.info(f"Cost of Carry: {cost_of_carry_annualized:.2f}% annualized")
        logger.info(f"Signal: {basis_signal} - {basis_interpretation}")
        logger.info(f"Score: {basis_score}/10")

        # ============================================================================
        # STEP 3: Open Interest Analysis
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Open Interest Analysis")
        logger.info("=" * 80)

        try:
            oi_analyzer = OpenInterestAnalyzer()

            # Analyze OI buildup
            oi_buildup = oi_analyzer.analyze_oi_buildup(stock_symbol, expiry_date)

            if 'error' not in oi_buildup:
                buildup_type = oi_buildup.get('buildup_type', 'UNKNOWN')
                buildup_sentiment = oi_buildup.get('sentiment', 'NEUTRAL')
                oi_change_pct = oi_buildup.get('oi_change_pct', 0)

                # Score based on OI change strength
                if abs(oi_change_pct) > 10:
                    oi_score = 15
                elif abs(oi_change_pct) > 5:
                    oi_score = 10
                else:
                    oi_score = 5

                metrics['oi_buildup_type'] = buildup_type
                metrics['oi_sentiment'] = buildup_sentiment
                metrics['oi_change_pct'] = oi_change_pct
                scores['oi'] = oi_score

                execution_log.append({
                    'step': 3,
                    'action': 'Open Interest Analysis',
                    'status': 'PASS',
                    'message': f"{buildup_type} ({buildup_sentiment}), OI Change: {oi_change_pct:+.1f}%",
                    'details': {
                        'buildup_type': buildup_type,
                        'sentiment': buildup_sentiment,
                        'oi_change_pct': round(oi_change_pct, 2),
                        'score': oi_score
                    }
                })

                logger.info(f"✅ OI Analysis: {buildup_type} ({buildup_sentiment})")
                logger.info(f"   OI Change: {oi_change_pct:+.1f}%")
                logger.info(f"   Score: {oi_score}/15")
            else:
                # OI data not available
                scores['oi'] = 0
                execution_log.append({
                    'step': 3,
                    'action': 'Open Interest Analysis',
                    'status': 'SKIP',
                    'message': 'OI data not available',
                    'details': {'error': oi_buildup.get('error')}
                })
                logger.warning("⚠️  OI data not available")
        except Exception as e:
            logger.warning(f"OI analysis failed: {e}")
            scores['oi'] = 0
            execution_log.append({
                'step': 3,
                'action': 'Open Interest Analysis',
                'status': 'SKIP',
                'message': f'Error: {str(e)[:100]}',
                'details': {'error': str(e)}
            })

        # ============================================================================
        # STEP 4: DMA Analysis (20, 50, 200)
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: DMA Analysis (20, 50, 200)")
        logger.info("=" * 80)

        try:
            dma_analyzer = DMAAnalyzer()
            dma_analysis = dma_analyzer.get_dma_position(stock_symbol)

            if dma_analysis and 'error' not in dma_analysis:
                golden_cross = dma_analysis.get('golden_cross', False)
                death_cross = dma_analysis.get('death_cross', False)
                trend = dma_analysis.get('trend', 'UNKNOWN')
                above_sma_200 = dma_analysis.get('above_sma_200', False)
                above_sma_50 = dma_analysis.get('above_sma_50', False)

                # Score based on DMA signals and trend
                if golden_cross:
                    dma_score = 15
                    dma_signal = "GOLDEN_CROSS (Bullish)"
                elif death_cross:
                    dma_score = 10
                    dma_signal = "DEATH_CROSS (Bearish)"
                elif trend == 'STRONG_UPTREND':
                    dma_score = 12
                    dma_signal = "STRONG_UPTREND (Bullish)"
                elif trend == 'UPTREND':
                    dma_score = 10
                    dma_signal = "UPTREND (Bullish)"
                elif trend == 'STRONG_DOWNTREND':
                    dma_score = 8
                    dma_signal = "STRONG_DOWNTREND (Bearish)"
                elif trend == 'DOWNTREND':
                    dma_score = 7
                    dma_signal = "DOWNTREND (Bearish)"
                else:
                    dma_score = 5
                    dma_signal = f"{trend} (Mixed signals)"

                metrics['dma_signal'] = dma_signal
                metrics['dma_trend'] = trend
                scores['dma'] = dma_score

                execution_log.append({
                    'step': 4,
                    'action': 'DMA Analysis',
                    'status': 'PASS',
                    'message': dma_signal,
                    'details': {
                        'trend': trend,
                        'golden_cross': golden_cross,
                        'death_cross': death_cross,
                        'above_sma_200': above_sma_200,
                        'above_sma_50': above_sma_50,
                        'above_dma_count': dma_analysis.get('above_dma_count', 0),
                        'total_dmas': dma_analysis.get('total_dmas', 0),
                        'score': dma_score
                    }
                })

                logger.info(f"✅ DMA Signal: {dma_signal}")
                logger.info(f"   Trend: {trend}")
                logger.info(f"   Score: {dma_score}/15")
            else:
                scores['dma'] = 0
                execution_log.append({
                    'step': 4,
                    'action': 'DMA Analysis',
                    'status': 'SKIP',
                    'message': 'DMA data not available',
                    'details': {'error': dma_analysis.get('error') if dma_analysis else 'No data'}
                })
                logger.warning("⚠️  DMA data not available")
        except Exception as e:
            logger.warning(f"DMA analysis failed: {e}")
            scores['dma'] = 0
            execution_log.append({
                'step': 4,
                'action': 'DMA Analysis',
                'status': 'SKIP',
                'message': f'Error: {str(e)[:100]}',
                'details': {'error': str(e)}
            })

        # ============================================================================
        # STEP 5: Sector Strength Analysis
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 5: Sector Strength Analysis")
        logger.info("=" * 80)

        try:
            sector_analysis = analyze_sector(stock_symbol)

            sector_verdict = sector_analysis.get('verdict', 'MIXED')
            allow_long = sector_analysis.get('allow_long', False)
            allow_short = sector_analysis.get('allow_short', False)

            # Score based on sector alignment
            if sector_verdict in ['STRONG_BULLISH', 'STRONG_BEARISH']:
                sector_score = 20
            elif sector_verdict in ['BULLISH', 'BEARISH']:
                sector_score = 12
            else:
                sector_score = 5

            metrics['sector_verdict'] = sector_verdict
            metrics['sector_allow_long'] = allow_long
            metrics['sector_allow_short'] = allow_short
            scores['sector'] = sector_score

            execution_log.append({
                'step': 5,
                'action': 'Sector Strength',
                'status': 'PASS',
                'message': f"{sector_verdict} (Long: {'✓' if allow_long else '✗'}, Short: {'✓' if allow_short else '✗'})",
                'details': {
                    'verdict': sector_verdict,
                    'allow_long': allow_long,
                    'allow_short': allow_short,
                    'performance': sector_analysis.get('performance', {}),
                    'score': sector_score
                }
            })

            logger.info(f"✅ Sector: {sector_verdict}")
            logger.info(f"   Allow Long: {allow_long}, Allow Short: {allow_short}")
            logger.info(f"   Score: {sector_score}/20")
        except Exception as e:
            logger.warning(f"Sector analysis failed: {e}")
            scores['sector'] = 0
            execution_log.append({
                'step': 5,
                'action': 'Sector Strength',
                'status': 'SKIP',
                'message': f'Error: {str(e)[:100]}',
                'details': {'error': str(e)}
            })

        # ============================================================================
        # STEP 6: Volume & Liquidity Analysis
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 6: Volume & Liquidity Analysis")
        logger.info("=" * 80)

        try:
            # Use futures data from Breeze response
            futures_volume = futures_data.get('volume', 0) if futures_data else 0
            futures_oi = futures_data.get('open_interest', 0) if futures_data else 0

            # Get contract data for volume ranking if available
            volume_rank = 0
            if contract:
                traded_contracts = contract.traded_contracts
                if traded_contracts >= 1000:
                    volume_rank = 10
                elif traded_contracts >= 500:
                    volume_rank = 7
                elif traded_contracts >= 100:
                    volume_rank = 4

            volume_score = min(10, volume_rank)

            metrics['futures_volume'] = futures_volume
            metrics['futures_oi'] = futures_oi
            metrics['volume_rank'] = volume_rank
            scores['volume'] = volume_score

            execution_log.append({
                'step': 6,
                'action': 'Volume & Liquidity',
                'status': 'PASS',
                'message': f"Volume: {futures_volume:,}, OI: {futures_oi:,}, Rank: {volume_rank}/10",
                'details': {
                    'futures_volume': futures_volume,
                    'futures_oi': futures_oi,
                    'traded_contracts': contract.traded_contracts if contract else 0,
                    'volume_rank': volume_rank,
                    'score': volume_score
                }
            })

            logger.info(f"✅ Volume: {futures_volume:,}")
            logger.info(f"   OI: {futures_oi:,}")
            logger.info(f"   Score: {volume_score}/10")
        except Exception as e:
            logger.warning(f"Volume analysis failed: {e}")
            scores['volume'] = 0
            execution_log.append({
                'step': 6,
                'action': 'Volume & Liquidity',
                'status': 'SKIP',
                'message': f'Error: {str(e)[:100]}',
                'details': {'error': str(e)}
            })

        # ============================================================================
        # STEP 7: Multi-Factor Technical Analysis (Algo Trader Approach)
        # Components:
        #   1. Trendlyne Scores (Durability, Valuation, Momentum): 0-5 points
        #   2. Price Momentum & Trend: 0-4 points
        #   3. Volume Pattern: 0-3 points
        #   4. Volatility & Price Position: 0-3 points
        #   5. PCR (Put-Call Ratio): 0-3 points
        #   Total: 0-18 points (capped at 15)
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 7: Multi-Factor Technical Analysis (5 Components)")
        logger.info("=" * 80)

        try:
            tech_score = 0
            tech_details = {}

            # Sub-analysis 1: Trendlyne Proprietary Scores (0-5 points)
            try:
                tl_stock = TLStockData.objects.filter(nsecode=stock_symbol).first()
                if tl_stock:
                    durability = tl_stock.trendlyne_durability_score or 0
                    valuation = tl_stock.trendlyne_valuation_score or 0
                    momentum = tl_stock.trendlyne_momentum_score or 0

                    # Composite Trendlyne score
                    tl_composite = (durability + valuation + momentum) / 3

                    if tl_composite >= 70:
                        tech_score += 5
                        tl_rating = "STRONG"
                    elif tl_composite >= 60:
                        tech_score += 4
                        tl_rating = "GOOD"
                    elif tl_composite >= 50:
                        tech_score += 3
                        tl_rating = "MODERATE"
                    else:
                        tech_score += 1
                        tl_rating = "WEAK"

                    tech_details['trendlyne'] = {
                        'composite': round(tl_composite, 2),
                        'durability': durability,
                        'valuation': valuation,
                        'momentum': momentum,
                        'rating': tl_rating
                    }
                    logger.info(f"  Trendlyne: {tl_composite:.1f}/100 ({tl_rating}) → +{tech_score}")
            except Exception as e:
                logger.warning(f"  Trendlyne scores unavailable: {e}")

            # Sub-analysis 2: Price Momentum & Trend (0-4 points)
            if contract:
                price_change = contract.pct_day_change
                price_trend_score = 0

                if abs(price_change) > 3:
                    price_trend_score = 4  # Strong momentum
                    trend_strength = "STRONG"
                elif abs(price_change) > 1.5:
                    price_trend_score = 3  # Moderate momentum
                    trend_strength = "MODERATE"
                elif abs(price_change) > 0.5:
                    price_trend_score = 2  # Weak momentum
                    trend_strength = "WEAK"
                else:
                    price_trend_score = 1  # Sideways
                    trend_strength = "SIDEWAYS"

                tech_score += price_trend_score
                tech_details['price_momentum'] = {
                    'day_change_pct': round(price_change, 2),
                    'strength': trend_strength,
                    'direction': 'BULLISH' if price_change > 0 else 'BEARISH' if price_change < 0 else 'NEUTRAL'
                }
                logger.info(f"  Price Momentum: {price_change:+.2f}% ({trend_strength}) → +{price_trend_score}")

            # Sub-analysis 3: Volume Pattern (0-3 points)
            if contract:
                volume = contract.traded_contracts
                prev_vol = contract.prev_day_vol

                volume_score = 0
                if prev_vol and prev_vol > 0:
                    volume_ratio = volume / prev_vol

                    if volume_ratio > 2:
                        volume_score = 3  # High volume surge
                        volume_signal = "SURGE"
                    elif volume_ratio > 1.5:
                        volume_score = 2  # Moderate volume increase
                        volume_signal = "ELEVATED"
                    elif volume_ratio > 0.8:
                        volume_score = 1  # Normal volume
                        volume_signal = "NORMAL"
                    else:
                        volume_score = 0  # Low volume
                        volume_signal = "LOW"
                else:
                    # No previous volume data - use absolute thresholds
                    if volume >= 1000:
                        volume_score = 2
                        volume_signal = "HIGH"
                    elif volume >= 500:
                        volume_score = 1
                        volume_signal = "MODERATE"
                    else:
                        volume_score = 0
                        volume_signal = "LOW"

                tech_score += volume_score
                tech_details['volume_pattern'] = {
                    'current': volume,
                    'previous': prev_vol or 0,
                    'signal': volume_signal
                }
                logger.info(f"  Volume: {volume:,} ({volume_signal}) → +{volume_score}")

            # Sub-analysis 4: Price Range & Volatility (0-3 points)
            if contract:
                current_price = contract.price
                high = contract.high_price
                low = contract.low_price
                open_price = contract.open_price

                volatility_score = 0
                if high > 0 and low > 0:
                    day_range_pct = ((high - low) / low) * 100

                    if day_range_pct > 3:
                        volatility_score = 3  # High volatility - good for trading
                        vol_signal = "HIGH"
                    elif day_range_pct > 1.5:
                        volatility_score = 2  # Moderate volatility
                        vol_signal = "MODERATE"
                    else:
                        volatility_score = 1  # Low volatility
                        vol_signal = "LOW"

                    # Check if price is near high or low (momentum confirmation)
                    position_in_range = ((current_price - low) / (high - low)) if (high - low) > 0 else 0.5

                    tech_details['volatility'] = {
                        'day_range_pct': round(day_range_pct, 2),
                        'signal': vol_signal,
                        'position_in_range': round(position_in_range, 2),
                        'near': 'HIGH' if position_in_range > 0.75 else 'LOW' if position_in_range < 0.25 else 'MIDDLE'
                    }

                    tech_score += volatility_score
                    logger.info(f"  Volatility: {day_range_pct:.2f}% ({vol_signal}), Price @ {position_in_range*100:.0f}% of range → +{volatility_score}")

            # Sub-analysis 5: PCR (Put-Call Ratio) Analysis (0-3 points)
            # PCR provides contrarian sentiment indicator
            try:
                from django.db.models import Sum

                # Get all call and put options for this expiry
                calls = ContractData.objects.filter(
                    symbol=stock_symbol,
                    expiry=expiry_date,
                    option_type='CE'
                )

                puts = ContractData.objects.filter(
                    symbol=stock_symbol,
                    expiry=expiry_date,
                    option_type='PE'
                )

                if calls.exists() and puts.exists():
                    # Calculate total OI
                    total_call_oi = calls.aggregate(total=Sum('oi'))['total'] or 0
                    total_put_oi = puts.aggregate(total=Sum('oi'))['total'] or 0

                    # Calculate total Volume
                    total_call_vol = calls.aggregate(total=Sum('traded_contracts'))['total'] or 0
                    total_put_vol = puts.aggregate(total=Sum('traded_contracts'))['total'] or 0

                    # Calculate PCR ratios
                    pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0
                    pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else 0

                    # PCR Interpretation (Contrarian indicator)
                    # PCR > 1.2: More puts (bearish sentiment) → Contrarian BULLISH
                    # PCR < 0.8: More calls (bullish sentiment) → Contrarian BEARISH
                    # 0.8-1.2: Neutral

                    pcr_score = 0
                    if pcr_oi > 1.2:
                        pcr_score = 3  # Strong bearish sentiment = contrarian bullish
                        pcr_signal = "BULLISH"
                        pcr_interpretation = "High put OI suggests bearish sentiment (contrarian bullish)"
                    elif pcr_oi > 1.0:
                        pcr_score = 2  # Moderate bearish sentiment
                        pcr_signal = "MODERATE_BULLISH"
                        pcr_interpretation = "Elevated put OI (moderately contrarian bullish)"
                    elif pcr_oi < 0.8:
                        pcr_score = 1  # High call OI = bearish for contrarian traders
                        pcr_signal = "BEARISH"
                        pcr_interpretation = "High call OI suggests bullish sentiment (contrarian bearish)"
                    else:
                        pcr_score = 2  # Neutral is actually good - balanced market
                        pcr_signal = "NEUTRAL"
                        pcr_interpretation = "Balanced put-call ratio (neutral sentiment)"

                    tech_score += pcr_score

                    tech_details['pcr'] = {
                        'pcr_oi': round(pcr_oi, 3),
                        'pcr_vol': round(pcr_vol, 3),
                        'total_call_oi': total_call_oi,
                        'total_put_oi': total_put_oi,
                        'signal': pcr_signal,
                        'interpretation': pcr_interpretation
                    }

                    logger.info(f"  PCR: OI={pcr_oi:.3f}, Vol={pcr_vol:.3f} ({pcr_signal}) → +{pcr_score}")
                    logger.info(f"       {pcr_interpretation}")
                else:
                    logger.info(f"  PCR: Not enough options data (Calls: {calls.count()}, Puts: {puts.count()})")
            except Exception as e:
                logger.warning(f"  PCR calculation failed: {e}")

            # Ensure score is within bounds (0-15)
            tech_score = min(15, max(0, tech_score))

            metrics['technical_score'] = tech_score
            metrics['technical_details'] = tech_details
            scores['technical'] = tech_score

            # Determine overall technical signal
            if tech_score >= 12:
                tech_signal = "VERY_STRONG"
            elif tech_score >= 9:
                tech_signal = "STRONG"
            elif tech_score >= 6:
                tech_signal = "MODERATE"
            else:
                tech_signal = "WEAK"

            execution_log.append({
                'step': 7,
                'action': 'Multi-Factor Technical Analysis',
                'status': 'PASS',
                'message': f"Score: {tech_score}/15 ({tech_signal})",
                'details': {
                    'score': tech_score,
                    'signal': tech_signal,
                    'components': tech_details
                }
            })

            logger.info(f"✅ Technical Analysis Complete")
            logger.info(f"   Total Score: {tech_score}/15 ({tech_signal})")
            logger.info(f"   Components: {len(tech_details)}")

        except Exception as e:
            logger.warning(f"Technical analysis failed: {e}", exc_info=True)
            scores['technical'] = 0
            execution_log.append({
                'step': 7,
                'action': 'Multi-Factor Technical Analysis',
                'status': 'SKIP',
                'message': f'Error: {str(e)[:100]}',
                'details': {'error': str(e)}
            })

        # ============================================================================
        # STEP 8: Advanced Support/Resistance Analysis with Historical Data
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 8: Advanced Support/Resistance Analysis (1-Year Historical Data)")
        logger.info("=" * 80)

        try:
            from apps.strategies.services.support_resistance_calculator import SupportResistanceCalculator

            sr_score = 0
            sr_details = {}
            sr_data = None
            breach_risks = None

            # Use comprehensive S/R calculator with 1-year historical data
            try:
                logger.info("Calculating S/R from 1-year historical data...")
                sr_calculator = SupportResistanceCalculator(symbol=stock_symbol, lookback_days=365)

                # Ensure we have 1 year of data
                if sr_calculator.ensure_and_load_data():
                    # Calculate comprehensive S/R levels
                    sr_data = sr_calculator.calculate_comprehensive_sr()
                    pivot_points = sr_data['pivot_points']
                    moving_averages = sr_data['moving_averages']

                    support_level = pivot_points['s1']
                    support_2 = pivot_points['s2']
                    resistance_level = pivot_points['r1']
                    resistance_2 = pivot_points['r2']

                    # Calculate distances and position
                    support_distance = spot_price - support_level
                    resistance_distance = resistance_level - spot_price
                    support_distance_pct = (support_distance / spot_price) * 100 if spot_price > 0 else 0
                    resistance_distance_pct = (resistance_distance / spot_price) * 100 if spot_price > 0 else 0

                    # Score based on position and proximity to levels
                    if support_distance_pct < 0.5:
                        sr_score = 5  # Very close to support - potential bounce
                        position_signal = "NEAR_SUPPORT"
                    elif resistance_distance_pct < 0.5:
                        sr_score = 4  # Very close to resistance - watch for rejection
                        position_signal = "NEAR_RESISTANCE"
                    elif 0.5 <= abs(support_distance_pct) <= 1.5:
                        sr_score = 3  # Approaching support/resistance
                        position_signal = "APPROACHING_LEVELS"
                    else:
                        sr_score = 2  # In middle zone
                        position_signal = "MIDDLE_RANGE"

                    sr_details = {
                        'method': 'Pivot Points from 1-Year Historical Data',
                        'pivot': float(pivot_points['pivot']),
                        'support': float(support_level),
                        'support_2': float(support_2),
                        'support_3': float(pivot_points['s3']),
                        'resistance': float(resistance_level),
                        'resistance_2': float(resistance_2),
                        'resistance_3': float(pivot_points['r3']),
                        'support_distance': round(support_distance, 2),
                        'resistance_distance': round(resistance_distance, 2),
                        'support_distance_pct': round(support_distance_pct, 2),
                        'resistance_distance_pct': round(resistance_distance_pct, 2),
                        'position_signal': position_signal,
                        'score': sr_score,
                        'moving_averages': {
                            'dma_20': float(moving_averages['dma_20']) if moving_averages.get('dma_20') else None,
                            'dma_50': float(moving_averages['dma_50']) if moving_averages.get('dma_50') else None,
                            'dma_100': float(moving_averages['dma_100']) if moving_averages.get('dma_100') else None,
                        }
                    }

                    logger.info(f"✅ S/R from Historical Data - Pivot Points Method")
                    logger.info(f"   S3: ₹{pivot_points['s3']:.2f} | S2: ₹{pivot_points['s2']:.2f} | S1: ₹{pivot_points['s1']:.2f}")
                    logger.info(f"   Pivot: ₹{pivot_points['pivot']:.2f}")
                    logger.info(f"   R1: ₹{pivot_points['r1']:.2f} | R2: ₹{pivot_points['r2']:.2f} | R3: ₹{pivot_points['r3']:.2f}")
                    logger.info(f"   Current: ₹{spot_price:.2f} ({position_signal})")

                    # Calculate risk at breach levels for futures position
                    try:
                        # Determine position type based on direction
                        # We'll calculate risks for both LONG and SHORT positions
                        lot_size = symbol_resolution.get('lot_size', 1)

                        # Calculate LONG position risks
                        long_position_data = {
                            'position_type': 'long_future',
                            'spot_price': float(spot_price),
                            'entry_price': float(spot_price),
                            'lot_size': lot_size
                        }
                        breach_risks_long = sr_calculator.calculate_risk_at_breach(long_position_data, sr_data)

                        # Calculate SHORT position risks
                        short_position_data = {
                            'position_type': 'short_future',
                            'spot_price': float(spot_price),
                            'entry_price': float(spot_price),
                            'lot_size': lot_size
                        }
                        breach_risks_short = sr_calculator.calculate_risk_at_breach(short_position_data, sr_data)

                        breach_risks = {
                            'long': breach_risks_long['breach_risks'],
                            'short': breach_risks_short['breach_risks']
                        }

                        sr_details['breach_risks'] = breach_risks

                        logger.info(f"   Breach Risks Calculated:")
                        if breach_risks_long['breach_risks']['s1_breach']:
                            s1_loss = breach_risks_long['breach_risks']['s1_breach']['potential_loss']
                            logger.info(f"     LONG @ S1 Breach: ₹{abs(s1_loss):,.0f} loss")
                        if breach_risks_short['breach_risks']['r1_breach']:
                            r1_loss = breach_risks_short['breach_risks']['r1_breach']['potential_loss']
                            logger.info(f"     SHORT @ R1 Breach: ₹{abs(r1_loss):,.0f} loss")

                    except Exception as breach_err:
                        logger.warning(f"Could not calculate breach risks: {breach_err}")
                        breach_risks = None

                else:
                    raise ValueError("Insufficient historical data for S/R calculation")

            except Exception as historical_error:
                logger.warning(f"Could not use historical S/R, falling back to day high/low: {historical_error}")

                # Fallback: Use day high/low from contract data
                if contract and contract.high_price > 0 and contract.low_price > 0:
                    day_high = contract.high_price
                    day_low = contract.low_price
                    resistance_level = day_high
                    support_level = day_low
                    price_range = day_high - day_low
                    resistance_2 = day_high + (price_range * 0.5)
                    support_2 = day_low - (price_range * 0.5)
                    sr_details['method'] = 'Day High/Low (Fallback)'
                else:
                    # Ultimate fallback: percentage-based
                    support_level = spot_price * 0.98
                    resistance_level = spot_price * 1.02
                    support_2 = spot_price * 0.96
                    resistance_2 = spot_price * 1.04
                    sr_details['method'] = 'Percentage-based (Fallback)'

                support_distance = spot_price - support_level
                resistance_distance = resistance_level - spot_price
                support_distance_pct = (support_distance / spot_price) * 100 if spot_price > 0 else 0
                resistance_distance_pct = (resistance_distance / spot_price) * 100 if spot_price > 0 else 0

                if support_distance_pct < 0.5:
                    sr_score = 5
                    position_signal = "NEAR_SUPPORT"
                elif resistance_distance_pct < 0.5:
                    sr_score = 4
                    position_signal = "NEAR_RESISTANCE"
                else:
                    sr_score = 2
                    position_signal = "MIDDLE_RANGE"

                sr_details.update({
                    'support': round(support_level, 2),
                    'resistance': round(resistance_level, 2),
                    'support_2': round(support_2, 2),
                    'resistance_2': round(resistance_2, 2),
                    'support_distance': round(support_distance, 2),
                    'resistance_distance': round(resistance_distance, 2),
                    'support_distance_pct': round(support_distance_pct, 2),
                    'resistance_distance_pct': round(resistance_distance_pct, 2),
                    'position_signal': position_signal,
                    'score': sr_score
                })

            metrics['support_level'] = support_level
            metrics['resistance_level'] = resistance_level
            metrics['support_distance'] = support_distance
            metrics['resistance_distance'] = resistance_distance
            metrics['sr_position'] = position_signal
            scores['sr'] = sr_score

            execution_log.append({
                'step': 8,
                'action': 'Support/Resistance Analysis',
                'status': 'PASS',
                'message': f"S1: ₹{support_level:.2f} | S2: ₹{support_2:.2f} | R1: ₹{resistance_level:.2f} | R2: ₹{resistance_2:.2f} → {position_signal}",
                'details': sr_details
            })

            logger.info(f"   Score: {sr_score}/5")

        except Exception as e:
            logger.warning(f"S/R calculation failed: {e}")
            scores['sr'] = 0
            breach_risks = None
            execution_log.append({
                'step': 8,
                'action': 'Support/Resistance',
                'status': 'SKIP',
                'message': f'Error: {str(e)[:100]}',
                'details': {'error': str(e)}
            })

        # ============================================================================
        # STEP 9: Composite Scoring & Verdict + Broker Routing
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 9: Composite Scoring, Verdict & Broker Routing")
        logger.info("=" * 80)

        # Calculate composite score (out of 100)
        # Basis: 10, OI: 15, DMA: 15, Sector: 20, Volume: 10, Technical: 15, S/R: 5, Extra: 10
        composite_score = (
            scores.get('basis', 0) +
            scores.get('oi', 0) +
            scores.get('dma', 0) +
            scores.get('sector', 0) +
            scores.get('volume', 0) +
            scores.get('technical', 0) +
            scores.get('sr', 0)
        )

        # Determine direction based on signals
        bullish_signals = 0
        bearish_signals = 0

        # Basis signal
        if metrics.get('basis_signal') == 'CONTANGO':
            bullish_signals += 1
        elif metrics.get('basis_signal') == 'BACKWARDATION':
            bearish_signals += 1

        # OI sentiment
        if metrics.get('oi_sentiment') == 'BULLISH':
            bullish_signals += 1
        elif metrics.get('oi_sentiment') == 'BEARISH':
            bearish_signals += 1

        # DMA signal
        if 'Bullish' in metrics.get('dma_signal', ''):
            bullish_signals += 1
        elif 'Bearish' in metrics.get('dma_signal', ''):
            bearish_signals += 1

        # Sector
        if metrics.get('sector_allow_long'):
            bullish_signals += 1
        if metrics.get('sector_allow_short'):
            bearish_signals += 1

        # Determine final direction
        if bullish_signals > bearish_signals and bullish_signals >= 2:
            direction = 'LONG'
        elif bearish_signals > bullish_signals and bearish_signals >= 2:
            direction = 'SHORT'
        else:
            direction = 'NEUTRAL'

        # Verdict: PASS if score >= 50 and direction is not NEUTRAL
        if composite_score >= 50 and direction != 'NEUTRAL':
            verdict = 'PASS'
        else:
            verdict = 'FAIL'

        metrics['composite_score'] = composite_score
        metrics['direction'] = direction
        metrics['verdict'] = verdict
        metrics['bullish_signals'] = bullish_signals
        metrics['bearish_signals'] = bearish_signals

        execution_log.append({
            'step': 9,
            'action': 'Composite Scoring & Verdict',
            'status': verdict,
            'message': f"{verdict}: Score {composite_score}/100, Direction: {direction}",
            'details': {
                'composite_score': composite_score,
                'direction': direction,
                'verdict': verdict,
                'bullish_signals': bullish_signals,
                'bearish_signals': bearish_signals,
                'score_breakdown': {
                    'basis': scores.get('basis', 0),
                    'oi': scores.get('oi', 0),
                    'dma': scores.get('dma', 0),
                    'sector': scores.get('sector', 0),
                    'volume': scores.get('volume', 0),
                    'technical': scores.get('technical', 0),
                    'sr': scores.get('sr', 0)
                }
            }
        })

        logger.info(f"\n{'='*80}")
        logger.info(f"FINAL VERDICT: {verdict}")
        logger.info(f"{'='*80}")
        logger.info(f"Composite Score: {composite_score}/100")
        logger.info(f"Direction: {direction}")
        logger.info(f"Bullish Signals: {bullish_signals}, Bearish Signals: {bearish_signals}")
        logger.info(f"\nScore Breakdown:")
        for component, score in scores.items():
            logger.info(f"  {component.upper()}: {score}")

        # ============================================================================
        # BROKER ROUTING LOGIC
        # ============================================================================
        # Rule: FUTURES → ICICI Direct (Breeze)
        #       OPTIONS → NEO (Kotak)

        # This is a FUTURES analysis, so always route to ICICI
        broker_code = 'ICICI'
        transaction_code = 'ICICI_FUTURES'

        metrics['broker_code'] = broker_code
        metrics['transaction_code'] = transaction_code
        metrics['instrument_type'] = 'FUTURES'

        logger.info(f"\n{'='*80}")
        logger.info(f"BROKER ROUTING")
        logger.info(f"{'='*80}")
        logger.info(f"Instrument Type: FUTURES")
        logger.info(f"Broker: {broker_code} (ICICI Direct / Breeze API)")
        logger.info(f"Transaction Code: {transaction_code}")
        logger.info(f"Note: Options trades would be routed to NEO (Kotak)")
        logger.info(f"{'='*80}\n")

        return {
            'success': True,
            'execution_log': execution_log,
            'metrics': metrics,
            'scores': scores,
            'verdict': verdict,
            'direction': direction,
            'composite_score': composite_score,
            'breach_risks': breach_risks if 'breach_risks' in locals() else None,
            'sr_data': sr_data if 'sr_data' in locals() else None,
            'broker_code': broker_code,
            'transaction_code': transaction_code,
            'instrument_type': 'FUTURES'
        }

    except Exception as e:
        logger.error(f"Error in comprehensive analysis: {str(e)}", exc_info=True)
        execution_log.append({
            'step': len(execution_log) + 1,
            'action': 'Analysis Error',
            'status': 'FAIL',
            'message': f"Error: {str(e)}",
            'details': {'error': str(e)}
        })

        return {
            'success': False,
            'execution_log': execution_log,
            'metrics': metrics,
            'verdict': 'FAIL',
            'direction': 'NEUTRAL',
            'composite_score': 0,
            'error': str(e)
        }


# ============================================================================
# ENHANCED FUTURES ANALYSIS (Uses EnhancedFuturesAnalyzer with Breeze prices)
# ============================================================================

def enhanced_futures_analysis(
    stock_symbol: str,
    expiry_date: str,
    contract: Optional[ContractData] = None,
    regime: str = 'NORMAL',
) -> Dict:
    """
    Enhanced futures analysis using EnhancedFuturesAnalyzer with Breeze API prices.

    This function combines:
    - Real-time price fetching from Breeze API
    - EnhancedFuturesAnalyzer's 12-component scoring system
    - 7 hard reject filters (MWPL, Volatility, Piotroski, etc.)

    Returns:
        dict: {
            'success': bool,
            'execution_log': list of step-by-step analysis,
            'metrics': dict of all calculated metrics,
            'verdict': 'PASS' or 'FAIL',
            'direction': 'LONG', 'SHORT', or 'NEUTRAL',
            'composite_score': int (0-100),
            'scores': dict of component scores,
            'hard_reject': bool,
            'reject_reason': str or None,
            'analysis': detailed analysis dict
        }
    """
    from apps.strategies.analyzers.enhanced_futures_analyzer import (
        EnhancedFuturesAnalyzer
    )

    logger.info("=" * 100)
    logger.info(f"ENHANCED FUTURES ANALYSIS: {stock_symbol} (Expiry: {expiry_date})")
    logger.info("=" * 100)

    execution_log = []
    metrics = {}

    try:
        # ============================================================================
        # STEP 0: Resolve Breeze Symbol
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 0: Resolving Breeze Symbol")
        logger.info("=" * 80)

        from apps.brokers.utils.security_master import get_futures_instrument

        expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
        expiry_formatted_sm = expiry_dt.strftime('%d-%b-%Y')

        instrument_info = get_futures_instrument(stock_symbol, expiry_formatted_sm)
        breeze_symbol = stock_symbol
        lot_size = 0

        if instrument_info and instrument_info.get('short_name'):
            breeze_symbol = instrument_info['short_name']
            lot_size = instrument_info.get('lot_size', 0)
            logger.info(f"SecurityMaster: {stock_symbol} -> {breeze_symbol}")
        else:
            symbol_resolution = resolve_breeze_symbol(stock_symbol, expiry_date)
            if symbol_resolution.get('success'):
                breeze_symbol = symbol_resolution.get('short_name', stock_symbol)
                lot_size = symbol_resolution.get('lot_size', 0)

        execution_log.append({
            'step': 0,
            'action': 'Symbol Resolution',
            'status': 'PASS',
            'message': f"Resolved to Breeze code: {breeze_symbol}",
            'details': {'breeze_symbol': breeze_symbol, 'lot_size': lot_size}
        })

        # ============================================================================
        # STEP 1: Fetch Real-Time Prices from Breeze API
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Fetching Real-Time Prices from Breeze API")
        logger.info("=" * 80)

        try:
            breeze = get_breeze_client()
        except Exception as e:
            logger.warning(f"Breeze not available, using database prices: {e}")
            breeze = None

        # Fetch spot price
        spot_price = 0.0
        spot_source = "Breeze API"

        try:
            spot_resp = breeze.get_quotes(
                stock_code=breeze_symbol,
                exchange_code="NSE",
                product_type="cash",
                expiry_date="",
                right="",
                strike_price=""
            )

            if spot_resp and spot_resp.get("Status") == 200 and spot_resp.get("Success"):
                spot_data = spot_resp["Success"][0] if spot_resp["Success"] else {}
                spot_price = float(spot_data.get('ltp', 0))
                logger.info(f"✅ Spot Price: ₹{spot_price:.2f}")
        except Exception as e:
            logger.warning(f"Spot price fetch error: {e}")

        # Fallback to database
        if spot_price == 0:
            stock_data = ContractStockData.objects.filter(nse_code=stock_symbol).first()
            if stock_data and stock_data.current_price:
                spot_price = float(stock_data.current_price)
                spot_source = "Trendlyne (Cached)"
                logger.info(f"✅ Using fallback - Spot Price: ₹{spot_price:.2f}")

        # Fetch futures price
        futures_price = 0.0
        futures_source = "Breeze API"
        expiry_formatted = expiry_dt.strftime('%d-%b-%Y').upper()

        try:
            futures_resp = breeze.get_quotes(
                stock_code=breeze_symbol,
                exchange_code="NFO",
                product_type="futures",
                expiry_date=expiry_formatted,
                right="others",
                strike_price=""
            )

            if futures_resp and futures_resp.get("Status") == 200 and futures_resp.get("Success"):
                futures_data = futures_resp["Success"][0] if futures_resp["Success"] else {}
                futures_price = float(futures_data.get('ltp', 0))
                logger.info(f"✅ Futures Price: ₹{futures_price:.2f}")
        except Exception as e:
            logger.warning(f"Futures price fetch error: {e}")

        # Fallback to contract data
        if futures_price == 0 and contract and contract.price:
            futures_price = float(contract.price)
            futures_source = "Trendlyne (Cached)"
            logger.info(f"✅ Using fallback - Futures Price: ₹{futures_price:.2f}")

        # Estimate if still no futures price
        if futures_price == 0 and spot_price > 0:
            futures_price = spot_price * 1.01
            futures_source = "Estimated from Spot"

        metrics['spot_price'] = spot_price
        metrics['futures_price'] = futures_price
        metrics['breeze_symbol'] = breeze_symbol

        step1_pass = spot_price > 0 and futures_price > 0

        execution_log.append({
            'step': 1,
            'action': 'Real-Time Price Fetch',
            'status': 'PASS' if step1_pass else 'FAIL',
            'message': f"Spot: ₹{spot_price:.2f} ({spot_source}), Futures: ₹{futures_price:.2f} ({futures_source})",
            'details': {
                'spot_price': spot_price,
                'futures_price': futures_price,
                'spot_source': spot_source,
                'futures_source': futures_source
            }
        })

        if not step1_pass:
            return {
                'success': False,
                'execution_log': execution_log,
                'metrics': metrics,
                'verdict': 'FAIL',
                'direction': 'NEUTRAL',
                'composite_score': 0,
                'error': 'Could not fetch prices'
            }

        # ============================================================================
        # STEP 2: Calculate Basis & Determine Initial Direction
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Calculating Basis & Cost of Carry")
        logger.info("=" * 80)

        basis = futures_price - spot_price
        basis_pct = (basis / spot_price * 100) if spot_price > 0 else 0

        # Calculate cost of carry (annualized)
        days_to_expiry = (expiry_dt.date() - datetime.now().date()).days
        days_to_expiry = max(days_to_expiry, 1)  # Avoid division by zero
        cost_of_carry = (basis_pct * 365 / days_to_expiry) if basis_pct else 0

        # Determine initial direction from basis
        if basis_pct > 0.5:
            initial_direction = 'LONG'
            basis_signal = 'CONTANGO'
        elif basis_pct < -0.5:
            initial_direction = 'SHORT'
            basis_signal = 'BACKWARDATION'
        else:
            initial_direction = 'LONG'  # Default to LONG for neutral basis
            basis_signal = 'NEUTRAL'

        metrics['basis'] = basis
        metrics['basis_pct'] = basis_pct
        metrics['cost_of_carry'] = cost_of_carry
        metrics['basis_signal'] = basis_signal
        metrics['days_to_expiry'] = days_to_expiry

        execution_log.append({
            'step': 2,
            'action': 'Basis & Cost of Carry',
            'status': 'PASS',
            'message': f"Basis: ₹{basis:.2f} ({basis_pct:.2f}%), CoC: {cost_of_carry:.2f}% p.a.",
            'details': {
                'basis': basis,
                'basis_pct': basis_pct,
                'cost_of_carry': cost_of_carry,
                'days_to_expiry': days_to_expiry,
                'basis_signal': basis_signal,
                'initial_direction': initial_direction
            }
        })

        logger.info(f"Basis: ₹{basis:.2f} ({basis_pct:.2f}%), Initial Direction: {initial_direction}")

        # ============================================================================
        # STEP 3: Run Enhanced Futures Analyzer (12-component scoring)
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info(f"STEP 3: Enhanced Multi-Factor Analysis ({initial_direction})")
        logger.info("=" * 80)

        analyzer = EnhancedFuturesAnalyzer(
            symbol=stock_symbol,
            direction=initial_direction,
            expiry=expiry_date,
            regime=regime,
        )

        analysis_result = analyzer.analyze()

        # Extract results
        hard_reject = analysis_result.get('hard_reject', False)
        reject_reason = analysis_result.get('reject_reason')
        composite_score = analysis_result.get('composite_score', 0)
        scores = analysis_result.get('scores', {})
        details = analysis_result.get('details', {})
        recommendation = analysis_result.get('recommendation', 'NO_ENTRY')
        entry_params = analysis_result.get('entry_params')

        # Map scores to legacy format for compatibility
        legacy_scores = {
            'basis': 10 if basis_pct > 0.5 else 5 if basis_pct > 0 else 0,
            'oi': int(scores.get('oi_fno', 0) / 45 * 15),  # Scale to max 15
            'dma': int(scores.get('trend_confirmation', 0) / 30 * 15),  # Scale to max 15
            'sector': 20 if details.get('sector_aligned', False) else 0,
            'volume': int(scores.get('volume_quality', 0) / 25 * 10),  # Scale to max 10
            'technical': int(scores.get('technical_momentum', 0) / 35 * 15),  # Scale to max 15
            'sr': 5  # Default
        }

        # Log hard reject checks
        hard_reject_checks = details.get('hard_reject_checks', {})
        for check_name, check_result in hard_reject_checks.items():
            passed = check_result.get('passed', True)
            execution_log.append({
                'step': 3,
                'action': f'Hard Reject: {check_name.upper()}',
                'status': 'PASS' if passed else 'FAIL',
                'message': check_result.get('reason', ''),
                'details': check_result
            })

        if hard_reject:
            execution_log.append({
                'step': 3,
                'action': 'Enhanced Analysis',
                'status': 'FAIL',
                'message': f"HARD REJECT: {reject_reason}",
                'details': {
                    'hard_reject': True,
                    'reject_reason': reject_reason,
                    'hard_reject_checks': hard_reject_checks
                }
            })

            return {
                'success': True,  # Analysis completed successfully
                'execution_log': execution_log,
                'metrics': metrics,
                'scores': legacy_scores,
                'verdict': 'FAIL',
                'direction': initial_direction,
                'composite_score': 0,
                'hard_reject': True,
                'reject_reason': reject_reason,
                'details': details,
                'error': reject_reason
            }

        # ============================================================================
        # STEP 4: Sector Alignment Check
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: Sector Alignment Check")
        logger.info("=" * 80)

        sector_analysis = analyze_sector(stock_symbol)
        sector_aligned = False

        if sector_analysis:
            if initial_direction == 'LONG' and sector_analysis.get('allow_long', False):
                sector_aligned = True
            elif initial_direction == 'SHORT' and sector_analysis.get('allow_short', False):
                sector_aligned = True

            metrics['sector_verdict'] = sector_analysis.get('verdict', 'NEUTRAL')
            metrics['sector_allow_long'] = sector_analysis.get('allow_long', False)
            metrics['sector_allow_short'] = sector_analysis.get('allow_short', False)

        details['sector_aligned'] = sector_aligned
        legacy_scores['sector'] = 20 if sector_aligned else 0

        execution_log.append({
            'step': 4,
            'action': 'Sector Alignment',
            'status': 'PASS' if sector_aligned else 'WARNING',
            'message': f"Sector {'aligned' if sector_aligned else 'NOT aligned'} with {initial_direction}",
            'details': {
                'sector_verdict': sector_analysis.get('verdict', 'N/A') if sector_analysis else 'N/A',
                'allow_long': sector_analysis.get('allow_long', False) if sector_analysis else False,
                'allow_short': sector_analysis.get('allow_short', False) if sector_analysis else False,
                'sector_aligned': sector_aligned
            }
        })

        # ============================================================================
        # STEP 5: Final Scoring & Verdict
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 5: Final Scoring & Verdict")
        logger.info("=" * 80)

        # Determine verdict: Pass if score >= 65 and not hard rejected
        # Also consider sector alignment as a factor but not a blocker
        if composite_score >= 65:
            verdict = 'PASS'
        elif composite_score >= 50:
            verdict = 'WEAK_PASS'  # May need manual review
        else:
            verdict = 'FAIL'

        metrics['composite_score'] = composite_score
        metrics['direction'] = initial_direction
        metrics['verdict'] = verdict
        metrics['recommendation'] = recommendation

        execution_log.append({
            'step': 5,
            'action': 'Final Scoring & Verdict',
            'status': verdict,
            'message': f"{verdict}: Score {composite_score}/100, Direction: {initial_direction}, Recommendation: {recommendation}",
            'details': {
                'composite_score': composite_score,
                'raw_score': analysis_result.get('raw_score', 0),
                'max_score': analysis_result.get('max_score', 300),
                'direction': initial_direction,
                'recommendation': recommendation,
                'sector_aligned': sector_aligned,
                'component_scores': scores,
                'score_breakdown': legacy_scores
            }
        })

        logger.info(f"\n{'='*80}")
        logger.info(f"FINAL VERDICT: {verdict}")
        logger.info(f"{'='*80}")
        logger.info(f"Composite Score: {composite_score}/100")
        logger.info(f"Direction: {initial_direction}")
        logger.info(f"Recommendation: {recommendation}")
        logger.info(f"Sector Aligned: {sector_aligned}")
        logger.info(f"\nComponent Scores:")
        for component, score in scores.items():
            weight = EnhancedFuturesAnalyzer.WEIGHTS.get(component, 0)
            logger.info(f"  {component}: {score}/{weight}")

        # Add broker routing info
        metrics['broker_code'] = 'ICICI'
        metrics['transaction_code'] = 'ICICI_FUTURES'
        metrics['instrument_type'] = 'FUTURES'

        return {
            'success': True,
            'execution_log': execution_log,
            'metrics': metrics,
            'scores': legacy_scores,
            'verdict': verdict if verdict != 'WEAK_PASS' else 'PASS',  # Treat weak pass as pass for now
            'direction': initial_direction,
            'composite_score': composite_score,
            'hard_reject': False,
            'reject_reason': None,
            'details': details,
            'entry_params': entry_params,
            'component_scores': scores,
            'recommendation': recommendation,
            'broker_code': 'ICICI',
            'transaction_code': 'ICICI_FUTURES',
            'instrument_type': 'FUTURES'
        }

    except Exception as e:
        logger.error(f"Error in enhanced futures analysis: {str(e)}", exc_info=True)
        execution_log.append({
            'step': len(execution_log) + 1,
            'action': 'Analysis Error',
            'status': 'FAIL',
            'message': f"Error: {str(e)}",
            'details': {'error': str(e)}
        })

        return {
            'success': False,
            'execution_log': execution_log,
            'metrics': metrics,
            'verdict': 'FAIL',
            'direction': 'NEUTRAL',
            'composite_score': 0,
            'error': str(e)
        }


# ============================================================================
# HISTORICAL DATA COLLECTION FOR RELATED INSTRUMENTS
# ============================================================================

def get_related_instruments(stock_symbol: str, expiry_date: str) -> Dict:
    """
    Discover all related instruments for a given stock/token.

    For a futures contract, this includes:
    - The underlying equity (NSE cash)
    - Current expiry futures
    - Next expiry futures
    - Current expiry options chain (all strikes, CE/PE)
    - Next expiry options chain (all strikes, CE/PE)

    For an options contract, this includes:
    - The underlying equity
    - All futures contracts (current + next expiry)
    - Full options chain for current + next expiry

    Args:
        stock_symbol: Stock symbol (e.g., 'HDFCBANK', 'RELIANCE')
        expiry_date: Primary expiry date in YYYY-MM-DD format

    Returns:
        dict: {
            'success': bool,
            'equity': {...},  # Underlying stock info
            'futures': [...],  # List of futures contracts
            'options': [...],  # List of options contracts
            'expiries': [...],  # List of expiry dates used
            'total_instruments': int,
            'error': str (if failed)
        }
    """
    logger.info(f"Discovering instruments for: {stock_symbol}")

    try:
        breeze = get_breeze_client()

        # ===== RESOLVE BREEZE SYMBOL USING SECURITY MASTER =====
        # SecurityMaster has the correct short_name for Breeze API
        # Examples: RELIANCE -> RELIND, HDFCBANK -> HDFCBAN, SBIN -> STABAN
        from apps.brokers.utils.security_master import get_futures_instrument

        # Format expiry for SecurityMaster lookup: DD-MMM-YYYY
        expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
        expiry_formatted_sm = expiry_dt.strftime('%d-%b-%Y')  # e.g., "24-Feb-2026"

        logger.info(f"Looking up SecurityMaster for {stock_symbol} expiry {expiry_formatted_sm}")

        instrument_info = get_futures_instrument(stock_symbol, expiry_formatted_sm)

        if instrument_info and instrument_info.get('short_name'):
            breeze_stock_code = instrument_info['short_name']
            logger.info(f"SecurityMaster lookup: {stock_symbol} -> {breeze_stock_code}")
            logger.info(f"  Source: {instrument_info.get('source', 'unknown')}, Lot size: {instrument_info.get('lot_size', 'N/A')}")
        else:
            # Fallback to resolve_breeze_symbol
            logger.warning(f"SecurityMaster lookup failed for {stock_symbol}, trying get_names API...")
            symbol_resolution = resolve_breeze_symbol(stock_symbol, expiry_date)

            if symbol_resolution.get('success'):
                breeze_stock_code = symbol_resolution.get('short_name', stock_symbol)
                logger.info(f"get_names resolution: {stock_symbol} -> {breeze_stock_code}")
            else:
                # Last resort: use original symbol
                breeze_stock_code = stock_symbol
                logger.warning(f"All resolution methods failed, using original: {stock_symbol}")

        instruments = {
            'success': True,
            'stock_symbol': stock_symbol,
            'breeze_stock_code': breeze_stock_code,
            'primary_expiry': expiry_date,
            'equity': None,
            'futures': [],
            'options': [],
            'expiries': [expiry_date],
            'total_instruments': 0
        }

        # ===== 1. EQUITY (Underlying Stock) =====
        # Use the resolved Breeze stock code for API calls
        logger.info(f"Adding equity: {breeze_stock_code} NSE (original: {stock_symbol})")
        instruments['equity'] = {
            'stock_code': breeze_stock_code,  # Use resolved Breeze code
            'exchange_code': 'NSE',
            'product_type': 'cash',
            'instrument_type': 'EQUITY',
            'original_symbol': stock_symbol  # Keep original for reference
        }
        instruments['total_instruments'] += 1

        # ===== 2. GET EXPIRY DATES =====
        # Use Breeze get_names to find available expiries
        try:
            names_resp = breeze.get_names(
                exchange_code="NFO",
                stock_code=stock_symbol
            )

            expiry_dates_found = set()
            if names_resp and names_resp.get("Status") == 200 and names_resp.get("Success"):
                for item in names_resp["Success"]:
                    exp_date = item.get('expiry_date', '')
                    if exp_date:
                        # Parse various date formats from Breeze
                        try:
                            # Try DD-MMM-YYYY format
                            exp_dt = datetime.strptime(exp_date[:11], '%d-%b-%Y')
                            expiry_dates_found.add(exp_dt.strftime('%Y-%m-%d'))
                        except ValueError:
                            try:
                                # Try YYYY-MM-DD format
                                exp_dt = datetime.strptime(exp_date[:10], '%Y-%m-%d')
                                expiry_dates_found.add(exp_dt.strftime('%Y-%m-%d'))
                            except ValueError:
                                pass

            # Sort expiries and get current + next
            sorted_expiries = sorted(expiry_dates_found)
            today = datetime.now().date()

            # Filter to future expiries only
            future_expiries = [e for e in sorted_expiries if datetime.strptime(e, '%Y-%m-%d').date() >= today]

            if future_expiries:
                # Use current and next expiry
                instruments['expiries'] = future_expiries[:2]
                logger.info(f"Found expiries: {instruments['expiries']}")
            else:
                # Fallback: calculate next monthly expiry
                instruments['expiries'] = [expiry_date]
                logger.warning(f"No future expiries found, using provided: {expiry_date}")

        except Exception as e:
            logger.warning(f"Could not fetch expiries from Breeze: {e}")
            instruments['expiries'] = [expiry_date]

        # ===== 3. FUTURES CONTRACTS =====
        for exp_date in instruments['expiries']:
            exp_formatted = datetime.strptime(exp_date, '%Y-%m-%d').strftime('%d-%b-%Y').upper()
            logger.info(f"Adding futures: {breeze_stock_code} FUT {exp_date}")

            instruments['futures'].append({
                'stock_code': breeze_stock_code,  # Use resolved Breeze code
                'exchange_code': 'NFO',
                'product_type': 'futures',
                'expiry_date': exp_date,
                'expiry_formatted': exp_formatted,
                'instrument_type': 'FUTURES',
                'original_symbol': stock_symbol
            })
            instruments['total_instruments'] += 1

        # ===== 4. OPTIONS CHAIN =====
        # Fetch option chain quotes to discover available strikes
        for exp_date in instruments['expiries']:
            exp_formatted = datetime.strptime(exp_date, '%Y-%m-%d').strftime('%d-%b-%Y').upper()

            try:
                # Fetch calls using resolved Breeze symbol
                calls_resp = breeze.get_option_chain_quotes(
                    stock_code=breeze_stock_code,
                    exchange_code="NFO",
                    product_type="options",
                    expiry_date=exp_formatted,
                    right="call",
                )

                if calls_resp and calls_resp.get("Status") == 200 and calls_resp.get("Success"):
                    for call in calls_resp["Success"]:
                        strike = call.get('strike_price')
                        if strike:
                            instruments['options'].append({
                                'stock_code': breeze_stock_code,  # Use resolved Breeze code
                                'exchange_code': 'NFO',
                                'product_type': 'options',
                                'expiry_date': exp_date,
                                'expiry_formatted': exp_formatted,
                                'strike_price': float(strike),
                                'right': 'call',
                                'instrument_type': 'OPTION_CE',
                                'original_symbol': stock_symbol
                            })
                            instruments['total_instruments'] += 1

                # Fetch puts using resolved Breeze symbol
                puts_resp = breeze.get_option_chain_quotes(
                    stock_code=breeze_stock_code,
                    exchange_code="NFO",
                    product_type="options",
                    expiry_date=exp_formatted,
                    right="put",
                )

                if puts_resp and puts_resp.get("Status") == 200 and puts_resp.get("Success"):
                    for put in puts_resp["Success"]:
                        strike = put.get('strike_price')
                        if strike:
                            instruments['options'].append({
                                'stock_code': breeze_stock_code,  # Use resolved Breeze code
                                'exchange_code': 'NFO',
                                'product_type': 'options',
                                'expiry_date': exp_date,
                                'expiry_formatted': exp_formatted,
                                'strike_price': float(strike),
                                'right': 'put',
                                'instrument_type': 'OPTION_PE',
                                'original_symbol': stock_symbol
                            })
                            instruments['total_instruments'] += 1


            except Exception as e:
                logger.warning(f"Could not fetch options chain for {exp_date}: {e}")

        logger.debug(f"Discovered {instruments['total_instruments']} instruments")

        return instruments

    except Exception as e:
        logger.error(f"Error discovering related instruments: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'stock_symbol': stock_symbol
        }


def fetch_and_save_historical_data_for_instrument(
    instrument: Dict,
    lookback_days: int = 365
) -> Dict:
    """
    Fetch historical OHLC data for a single instrument and save to database.

    Args:
        instrument: Dict containing instrument details:
            - stock_code: str
            - exchange_code: str
            - product_type: str ('cash', 'futures', 'options')
            - expiry_date: str (for F&O)
            - strike_price: float (for options)
            - right: str (for options - 'call', 'put')
        lookback_days: Number of days of historical data to fetch

    Returns:
        dict: {
            'success': bool,
            'instrument': str (description),
            'records_saved': int,
            'records_deleted': int,
            'error': str (if failed)
        }
    """
    from apps.brokers.models import HistoricalPrice

    stock_code = instrument['stock_code']
    exchange_code = instrument['exchange_code']
    product_type = instrument['product_type']

    # Build instrument description
    if product_type == 'options':
        instrument_desc = f"{stock_code} {instrument.get('expiry_date')} {instrument.get('strike_price')} {instrument.get('right', '').upper()}"
    elif product_type == 'futures':
        instrument_desc = f"{stock_code} FUT {instrument.get('expiry_date')}"
    else:
        instrument_desc = f"{stock_code} {exchange_code}"

    logger.debug(f"Fetching: {instrument_desc}")

    try:
        breeze = get_breeze_client()

        # Calculate date range
        to_date = datetime.now().date()
        from_date = to_date - timedelta(days=lookback_days)

        # Convert dates to ISO format for Breeze API
        from_date_iso = from_date.strftime('%Y-%m-%dT09:15:00.000Z')
        to_date_iso = to_date.strftime('%Y-%m-%dT15:30:00.000Z')

        # Prepare API parameters - base params for all product types
        api_params = {
            'interval': '1day',
            'from_date': from_date_iso,
            'to_date': to_date_iso,
            'stock_code': stock_code,
            'exchange_code': exchange_code,
            'product_type': product_type,
        }

        # Add F&O parameters ONLY for futures/options (not for cash)
        expiry_date_obj = None
        strike_price = None
        right = ''

        if product_type == 'futures':
            expiry_date_str = instrument.get('expiry_date')
            if expiry_date_str:
                expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                api_params['expiry_date'] = expiry_date_obj.strftime('%Y-%m-%dT00:00:00.000Z')
            api_params['right'] = 'others'
            api_params['strike_price'] = ''

        elif product_type == 'options':
            expiry_date_str = instrument.get('expiry_date')
            if expiry_date_str:
                expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                api_params['expiry_date'] = expiry_date_obj.strftime('%Y-%m-%dT00:00:00.000Z')
            strike_price = instrument.get('strike_price')
            right = instrument.get('right', '')
            api_params['right'] = right
            api_params['strike_price'] = str(int(strike_price)) if strike_price else ''

        else:
            # For cash products, add empty strings for F&O params
            api_params['expiry_date'] = ''
            api_params['right'] = ''
            api_params['strike_price'] = ''

        # Call Breeze API
        # Note: get_historical_data (v1) doesn't support 'cash' product type
        # Must use get_historical_data_v2 for equity/cash data
        logger.info(f"Breeze API call: {instrument_desc} (params: stock_code={api_params.get('stock_code')}, "
                   f"exchange={api_params.get('exchange_code')}, product={api_params.get('product_type')})")
        if product_type == 'cash':
            response = breeze.get_historical_data_v2(**api_params)
        else:
            response = breeze.get_historical_data(**api_params)

        # Handle None response or None Success value
        candles_count = 0
        api_status = None
        api_error = None
        if response:
            api_status = response.get('Status')
            api_error = response.get('Error')
            success_data = response.get('Success')
            if success_data is not None:
                candles_count = len(success_data)
        logger.info(f"Breeze API response for {instrument_desc}: status={api_status}, candles={candles_count}"
                   + (f", error={api_error}" if api_error else ""))

        # Check API response
        if not response:
            return {
                'success': False,
                'instrument': instrument_desc,
                'records_saved': 0,
                'records_deleted': 0,
                'error': 'Empty response from Breeze API'
            }

        if response.get('Status') != 200:
            error_msg = response.get('Error', 'Unknown error')
            logger.error(f"API error for {instrument_desc}: {error_msg}")
            return {
                'success': False,
                'instrument': instrument_desc,
                'records_saved': 0,
                'records_deleted': 0,
                'error': f'Breeze API error: {error_msg}'
            }

        # Extract data
        candles = response.get('Success', [])

        if not candles:
            logger.error(f"Breeze API returned no data for {instrument_desc}. "
                        f"Check: stock code validity, API authentication, or Breeze service status.")
            return {
                'success': False,
                'instrument': instrument_desc,
                'records_saved': 0,
                'records_deleted': 0,
                'error': f'Breeze API returned no historical data for {instrument_desc}'
            }

        # Save to database
        from decimal import Decimal as D
        from django.db import connection

        # Check if table exists before attempting to save
        table_names = connection.introspection.table_names()
        if 'historical_prices' not in table_names:
            logger.error("HistoricalPrice table missing - run: python manage.py migrate brokers")
            return {
                'success': False,
                'instrument': instrument_desc,
                'records_saved': 0,
                'records_deleted': 0,
                'error': 'HistoricalPrice table does not exist. Run migrations.'
            }

        try:
            deleted_count, created_count = HistoricalPrice.replace_data(
                stock_code=stock_code,
                exchange_code=exchange_code,
                product_type=product_type,
                interval='1day',
                data_points=candles,
                expiry_date=expiry_date_obj,
                strike_price=D(str(strike_price)) if strike_price else None,
                right=right
            )
            logger.debug(f"Saved {created_count} records for {instrument_desc}")
        except Exception as db_error:
            logger.error(f"Database error for {instrument_desc}: {db_error}")
            return {
                'success': False,
                'instrument': instrument_desc,
                'records_saved': 0,
                'records_deleted': 0,
                'error': f'Database error: {str(db_error)}'
            }

        # ===== FETCH CURRENT LIVE QUOTE =====
        # Historical data only has completed candles (yesterday's close at best)
        # We need today's live price for real-time analysis
        current_quote = None
        try:
            # Format expiry for get_quotes API
            expiry_formatted = ''
            if product_type in ['futures', 'options'] and expiry_date_obj:
                expiry_formatted = expiry_date_obj.strftime('%d-%b-%Y').upper()

            quote_params = {
                'stock_code': stock_code,
                'exchange_code': exchange_code,
                'product_type': product_type,
                'expiry_date': expiry_formatted,
                'right': right if product_type == 'options' else ('others' if product_type == 'futures' else ''),
                'strike_price': str(int(strike_price)) if strike_price else ''
            }

            quote_resp = breeze.get_quotes(**quote_params)

            if quote_resp and quote_resp.get("Status") == 200 and quote_resp.get("Success"):
                quote_data = quote_resp["Success"][0] if quote_resp["Success"] else {}
                current_quote = {
                    'ltp': float(quote_data.get('ltp', 0)),
                    'open': float(quote_data.get('open', 0)),
                    'high': float(quote_data.get('high', 0)),
                    'low': float(quote_data.get('low', 0)),
                    'close': float(quote_data.get('previous_close', 0)),
                    'volume': int(quote_data.get('total_quantity_traded', 0) or 0),
                    'open_interest': int(quote_data.get('open_interest', 0) or 0),
                    'change': float(quote_data.get('ltp', 0)) - float(quote_data.get('previous_close', 0)),
                    'change_pct': (
                        ((float(quote_data.get('ltp', 0)) - float(quote_data.get('previous_close', 0))) /
                         float(quote_data.get('previous_close', 1))) * 100
                    ) if quote_data.get('previous_close') else 0,
                    'bid': float(quote_data.get('best_bid_price', 0) or 0),
                    'ask': float(quote_data.get('best_offer_price', 0) or 0),
                    'timestamp': datetime.now().isoformat()
                }
                logger.info(f"Current LTP for {instrument_desc}: ₹{current_quote['ltp']:.2f}")

                # ===== SAVE TODAY'S LIVE DATA TO DATABASE =====
                # Save current quote as today's record so queries include latest data
                if current_quote.get('ltp', 0) > 0:
                    try:
                        today_datetime = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)

                        # Check if today's record already exists (avoid duplicates)
                        today_filter = {
                            'stock_code': stock_code,
                            'exchange_code': exchange_code,
                            'product_type': product_type,
                            'interval': '1day',
                            'datetime__date': today_datetime.date()
                        }
                        if product_type in ['futures', 'options']:
                            today_filter['expiry_date'] = expiry_date_obj
                        if product_type == 'options':
                            today_filter['strike_price'] = D(str(strike_price)) if strike_price else None
                            today_filter['right'] = right

                        # Delete any existing today's record and create fresh one
                        HistoricalPrice.objects.filter(**today_filter).delete()

                        # Create today's record with live data
                        today_record = HistoricalPrice(
                            stock_code=stock_code,
                            exchange_code=exchange_code,
                            product_type=product_type,
                            interval='1day',
                            expiry_date=expiry_date_obj,
                            strike_price=D(str(strike_price)) if strike_price else None,
                            right=right,
                            datetime=today_datetime,
                            open=D(str(current_quote['open'])),
                            high=D(str(current_quote['high'])),
                            low=D(str(current_quote['low'])),
                            close=D(str(current_quote['ltp'])),  # Use LTP as current "close"
                            volume=current_quote['volume'],
                            open_interest=current_quote['open_interest'] or 0
                        )
                        today_record.save()
                        created_count += 1  # Increment saved count

                    except Exception as save_error:
                        logger.warning(f"Could not save today's live data for {instrument_desc}: {save_error}")

            else:
                logger.warning(f"Could not fetch live quote for {instrument_desc}: {quote_resp.get('Error', 'Unknown')}")

        except Exception as quote_error:
            logger.warning(f"Error fetching live quote for {instrument_desc}: {quote_error}")

        return {
            'success': True,
            'instrument': instrument_desc,
            'records_saved': created_count,
            'records_deleted': deleted_count,
            'date_range': {
                'from': from_date.strftime('%Y-%m-%d'),
                'to': to_date.strftime('%Y-%m-%d')
            },
            'current_quote': current_quote,
            'last_historical_close': float(candles[-1]['close']) if candles else None,
            'last_historical_date': candles[-1]['datetime'] if candles else None
        }

    except Exception as e:
        logger.error(f"Error fetching historical data for {instrument_desc}: {e}", exc_info=True)
        return {
            'success': False,
            'instrument': instrument_desc,
            'records_saved': 0,
            'records_deleted': 0,
            'error': str(e)
        }


def collect_historical_data_for_token(
    stock_symbol: str,
    expiry_date: str,
    lookback_days: int = 365,
    include_options: bool = True,
    max_options_per_expiry: int = 50
) -> Dict:
    """
    Collect and save 365 days of historical data for all instruments
    related to a given token (stock/future/option).

    This is the main entry point for historical data collection before
    running Verify Trade or Futures Algorithm.

    Args:
        stock_symbol: Stock symbol (e.g., 'HDFCBANK', 'RELIANCE')
        expiry_date: Primary expiry date in YYYY-MM-DD format
        lookback_days: Number of days of historical data to fetch (default 365)
        include_options: Whether to include options chain (default True)
        max_options_per_expiry: Maximum options to fetch per expiry (default 50)
            Set to 0 for unlimited, or reduce for faster execution

    Returns:
        dict: {
            'success': bool,
            'stock_symbol': str,
            'summary': {
                'total_instruments': int,
                'successful': int,
                'failed': int,
                'total_records_saved': int
            },
            'equity_result': {...},
            'futures_results': [...],
            'options_results': [...],
            'current_quotes': {
                'timestamp': str (ISO format),
                'equity': {ltp, open, high, low, close, volume, oi, change, change_pct, bid, ask},
                'futures': {instrument_key: {ltp, ...}, ...},
                'options': {
                    'calls': {strike: {ltp, ...}, ...},
                    'puts': {strike: {ltp, ...}, ...}
                }
            },
            'execution_time_seconds': float,
            'error': str (if failed)
        }
    """
    import time
    start_time = time.time()

    logger.info(f"Collecting historical data: {stock_symbol} ({lookback_days} days)")

    result = {
        'success': True,
        'stock_symbol': stock_symbol,
        'expiry_date': expiry_date,
        'summary': {
            'total_instruments': 0,
            'successful': 0,
            'failed': 0,
            'total_records_saved': 0
        },
        'equity_result': None,
        'futures_results': [],
        'options_results': []
    }

    try:
        # Step 1: Discover all related instruments
        instruments = get_related_instruments(stock_symbol, expiry_date)

        if not instruments.get('success'):
            return {
                'success': False,
                'stock_symbol': stock_symbol,
                'error': instruments.get('error', 'Failed to discover instruments')
            }

        result['expiries'] = instruments.get('expiries', [])

        # Step 2: Fetch historical data for equity
        if instruments.get('equity'):
            equity_result = fetch_and_save_historical_data_for_instrument(
                instruments['equity'],
                lookback_days=lookback_days
            )
            result['equity_result'] = equity_result
            result['summary']['total_instruments'] += 1

            if equity_result.get('success'):
                result['summary']['successful'] += 1
                result['summary']['total_records_saved'] += equity_result.get('records_saved', 0)
            else:
                result['summary']['failed'] += 1

        # Step 3: Fetch historical data for futures
        for futures_instrument in instruments.get('futures', []):
            futures_result = fetch_and_save_historical_data_for_instrument(
                futures_instrument,
                lookback_days=lookback_days
            )
            result['futures_results'].append(futures_result)
            result['summary']['total_instruments'] += 1

            if futures_result.get('success'):
                result['summary']['successful'] += 1
                result['summary']['total_records_saved'] += futures_result.get('records_saved', 0)
            else:
                result['summary']['failed'] += 1

        # Step 4: Fetch historical data for options (if enabled)
        if include_options:

            options_list = instruments.get('options', [])

            # Limit options per expiry if specified
            if max_options_per_expiry > 0:
                # Group by expiry and limit
                limited_options = []
                expiry_counts = {}

                for opt in options_list:
                    exp = opt.get('expiry_date')
                    if exp not in expiry_counts:
                        expiry_counts[exp] = 0

                    if expiry_counts[exp] < max_options_per_expiry:
                        limited_options.append(opt)
                        expiry_counts[exp] += 1

                options_list = limited_options
                logger.info(f"Limited to {len(options_list)} options (max {max_options_per_expiry} per expiry)")

            for options_instrument in options_list:
                options_result = fetch_and_save_historical_data_for_instrument(
                    options_instrument,
                    lookback_days=lookback_days
                )
                result['options_results'].append(options_result)
                result['summary']['total_instruments'] += 1

                if options_result.get('success'):
                    result['summary']['successful'] += 1
                    result['summary']['total_records_saved'] += options_result.get('records_saved', 0)
                else:
                    result['summary']['failed'] += 1
        else:
            pass  # Options skipped

        # Calculate execution time
        end_time = time.time()
        result['execution_time_seconds'] = round(end_time - start_time, 2)

        # ===== AGGREGATE CURRENT QUOTES (TODAY'S LIVE DATA) =====
        # Consolidate all current quotes for easy access
        current_quotes = {
            'timestamp': datetime.now().isoformat(),
            'equity': None,
            'futures': {},
            'options': {
                'calls': {},
                'puts': {}
            }
        }

        # Extract equity current quote
        if result.get('equity_result') and result['equity_result'].get('current_quote'):
            current_quotes['equity'] = {
                'instrument': result['equity_result'].get('instrument'),
                **result['equity_result']['current_quote']
            }

        # Extract futures current quotes
        for fut_result in result.get('futures_results', []):
            if fut_result.get('current_quote'):
                instrument_key = fut_result.get('instrument', 'unknown')
                current_quotes['futures'][instrument_key] = {
                    'instrument': instrument_key,
                    **fut_result['current_quote']
                }

        # Extract options current quotes (organized by strike)
        for opt_result in result.get('options_results', []):
            if opt_result.get('current_quote'):
                instrument = opt_result.get('instrument', '')
                # Parse instrument string to extract strike and type
                # Format: "HDFCBANK 2025-01-30 1700.0 CALL"
                parts = instrument.split()
                if len(parts) >= 4:
                    strike = parts[2]
                    opt_type = parts[3].upper()

                    if opt_type == 'CALL':
                        current_quotes['options']['calls'][strike] = {
                            'instrument': instrument,
                            **opt_result['current_quote']
                        }
                    elif opt_type == 'PUT':
                        current_quotes['options']['puts'][strike] = {
                            'instrument': instrument,
                            **opt_result['current_quote']
                        }

        result['current_quotes'] = current_quotes

        # Log summary
        logger.info(f"Collection done: {result['summary']['successful']}/{result['summary']['total_instruments']} instruments, {result['summary']['total_records_saved']} records ({result['execution_time_seconds']}s)")

        return result

    except Exception as e:
        logger.error(f"Error in historical data collection: {e}", exc_info=True)
        return {
            'success': False,
            'stock_symbol': stock_symbol,
            'error': str(e)
        }


# Nifty-relative tolerance bands for the 5/15/30-day price-drop checks.
# excess_pp = stock_change_pct - nifty_change_pct (positive = stock beat Nifty).
# Higher tolerance for shorter windows, tighter for longer windows.
_NIFTY_REL_HARD_REJECT_PP = {5: -4.0, 15: -3.0, 30: -2.0}   # excess ≤ this → hard reject regardless of absolute
_NIFTY_REL_OVERRIDE_MARGIN_PP = {5: 1.0, 15: 0.5, 30: 0.0}  # excess ≥ this → waive absolute fail (FAIL→WARNING)


def _evaluate_price_drop_vs_nifty(
    check: Dict,
    window_days: int,
    stock_change_pct: float,
    abs_threshold_pct: float,
    nifty_change_pct: Optional[float],
    result: Dict,
) -> None:
    """Apply absolute + Nifty-relative policy to a price-drop check.

    Decision flow:
      1. Hard reject: stock underperformed Nifty by more than the hard-reject
         band → FAIL (blocks trade) even if absolute threshold is intact.
      2. Absolute fail + strong outperformance → WARNING (allows trade).
      3. Absolute fail + insufficient outperformance → FAIL.
      4. Absolute pass → PASS.

    Mutates `check` (status/value/message/details) and `result`
    (trade_allowed, recommendations).
    """
    abs_fail = stock_change_pct < abs_threshold_pct
    abs_msg = (
        f'Stock dropped {abs(stock_change_pct):.2f}% in last {window_days} days '
        f'(threshold: {abs(abs_threshold_pct):.0f}%)'
    )
    pass_msg = f'{window_days}-day change: {stock_change_pct:+.2f}% (within acceptable range)'

    if nifty_change_pct is None:
        # Legacy absolute-only behavior when Nifty data is unavailable
        check['value'] = f"{stock_change_pct:+.2f}%"
        if abs_fail:
            check['status'] = 'FAIL'
            check['message'] = f'{abs_msg} — Nifty data unavailable, relative gate skipped'
            result['trade_allowed'] = False
            result['recommendations'].append(
                f'⚠️ Avoid trade: {abs(stock_change_pct):.2f}% loss in {window_days} days'
            )
        else:
            check['status'] = 'PASS'
            check['message'] = pass_msg
        return

    excess_pp = stock_change_pct - nifty_change_pct
    hard_limit = _NIFTY_REL_HARD_REJECT_PP.get(window_days, -2.0)
    override_margin = _NIFTY_REL_OVERRIDE_MARGIN_PP.get(window_days, 0.0)

    check['value'] = f"{stock_change_pct:+.2f}% vs Nifty {nifty_change_pct:+.2f}%"
    check['details'].update({
        'nifty_change_pct': round(nifty_change_pct, 2),
        'stock_vs_nifty_pp': round(excess_pp, 2),
        'nifty_hard_reject_pp': hard_limit,
        'nifty_override_margin_pp': override_margin,
    })

    rel_phrase = (
        f'Nifty {nifty_change_pct:+.2f}%, stock vs Nifty {excess_pp:+.2f}pp '
        f'(override ≥ {override_margin:+.1f}pp, hard-reject ≤ {hard_limit:.1f}pp)'
    )

    if excess_pp <= hard_limit:
        check['status'] = 'FAIL'
        check['message'] = (
            f'Hard reject: stock underperformed Nifty by {abs(excess_pp):.2f}pp '
            f'in {window_days}d. {rel_phrase}'
        )
        result['trade_allowed'] = False
        result['recommendations'].append(
            f'🚫 Avoid trade: stock underperformed Nifty by {abs(excess_pp):.2f}pp '
            f'in {window_days}d (hard-reject)'
        )
        return

    if abs_fail:
        if excess_pp >= override_margin:
            check['status'] = 'WARNING'
            check['message'] = (
                f'{abs_msg}, but stock outperformed Nifty by {excess_pp:+.2f}pp — highlight only. {rel_phrase}'
            )
            result['recommendations'].append(
                f'ℹ️ {abs(stock_change_pct):.2f}% loss in {window_days}d but beat Nifty by '
                f'{excess_pp:+.2f}pp — approved with caution'
            )
        else:
            check['status'] = 'FAIL'
            check['message'] = f'{abs_msg} and did not sufficiently beat Nifty. {rel_phrase}'
            result['trade_allowed'] = False
            result['recommendations'].append(
                f'⚠️ Avoid trade: {abs(stock_change_pct):.2f}% loss in {window_days}d '
                f'with no Nifty outperformance'
            )
    else:
        check['status'] = 'PASS'
        check['message'] = f'{pass_msg}. {rel_phrase}'


def verify_historical_data(
    stock_symbol: str,
    expiry_date: str
) -> Dict:
    """
    Verify historical data and perform risk assessment before suggesting a futures trade.

    Risk Checks (any failure blocks the trade):
    1. 5-Day Loss Check: Stock lost more than 3% in last 5 days (Nifty-relative gate applied)
    2. 15-Day Loss Check: Stock lost more than 5% in last 15 days (Nifty-relative gate applied)
    3. 30-Day Loss Check: Stock lost more than 10% in last 30 days (Nifty-relative gate applied)
    4. Single Day Drop Check: Stock lost more than 2% on any single day in last 5 days
    5. Volatility Check: High volatility regime detection
    6. Volume Decline Check: Declining volume trend
    7. Support Breach Check: Price broke below key support levels
    8. Trend Reversal Check: Recent trend reversal signals

    Nifty-relative gate: for checks 1–3, the absolute drop threshold is
    reconciled against Nifty's drop over the same window. A stock that breaches
    the absolute threshold but outperforms Nifty is downgraded FAIL→WARNING;
    a stock that significantly underperforms Nifty is hard-rejected even when
    the absolute threshold is intact. Tolerance bands widen for shorter windows.

    Args:
        stock_symbol: Stock symbol (e.g., 'HDFCBANK')
        expiry_date: Expiry date in YYYY-MM-DD format

    Returns:
        dict: {
            'success': bool,
            'trade_allowed': bool,  # False if any risk check fails
            'risk_checks': [...],   # List of all checks with results
            'risk_summary': {...},  # Summary statistics
            'analysis': {...},      # Detailed analysis data
            'recommendations': [...],
            'error': str (if failed)
        }
    """
    from apps.brokers.models import HistoricalPrice
    from django.db import OperationalError

    logger.debug(f"Verifying historical data: {stock_symbol}")

    result = {
        'success': True,
        'stock_symbol': stock_symbol,
        'expiry_date': expiry_date,
        'trade_allowed': True,
        'risk_checks': [],
        'risk_summary': {
            'total_checks': 0,
            'passed': 0,
            'failed': 0,
            'warnings': 0
        },
        'analysis': {},
        'recommendations': []
    }

    try:
        # ===== RESOLVE BREEZE STOCK CODE =====
        # Historical data is saved with Breeze stock code (e.g., HDFBAN), not original symbol (HDFCBANK)
        # We need to use the same code for lookup
        from apps.brokers.utils.security_master import get_futures_instrument

        expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
        expiry_formatted_sm = expiry_dt.strftime('%d-%b-%Y')

        instrument_info = get_futures_instrument(stock_symbol, expiry_formatted_sm)
        if instrument_info and instrument_info.get('short_name'):
            breeze_stock_code = instrument_info['short_name']
            logger.debug(f"Verification lookup: {stock_symbol} -> {breeze_stock_code}")
        else:
            # Fallback to original symbol
            breeze_stock_code = stock_symbol
            logger.warning(f"Could not resolve Breeze code for {stock_symbol}, using original")

        # Fetch historical data for equity from database
        try:
            historical_data = HistoricalPrice.objects.filter(
                stock_code=breeze_stock_code,  # Use Breeze stock code, not original symbol
                exchange_code='NSE',
                product_type='cash',
                interval='1day'
            ).order_by('-datetime')[:365]  # Get up to 1 year

            data_exists = historical_data.exists()
        except OperationalError as db_error:
            # Table doesn't exist yet - need to run migrations
            logger.warning(f"HistoricalPrice table not found: {db_error}")
            result['success'] = True
            result['trade_allowed'] = False  # Block trade - cannot verify without database
            result['verdict'] = 'BLOCKED'
            result['verdict_message'] = 'Historical data verification blocked - database table not created yet. Run: python manage.py migrate brokers'
            result['risk_checks'] = [{
                'id': 'database_missing',
                'name': 'Database Setup Required',
                'description': 'HistoricalPrice table needs to be created',
                'status': 'FAIL',
                'severity': 'HIGH',
                'value': 'Table Missing',
                'threshold': 'Table Required',
                'message': 'Run "python manage.py migrate brokers" to enable historical verification'
            }]
            result['risk_summary'] = {
                'total_checks': 1,
                'passed': 0,
                'failed': 1,
                'warnings': 0,
                'skipped': 0,
                'pass_rate': 0
            }
            result['recommendations'].append('Run migrations to enable historical data verification: python manage.py migrate brokers')
            return result

        if not data_exists:
            logger.error(f"No historical data found for {stock_symbol} after download attempt - this is an error")
            result['success'] = False  # This is an error condition
            result['trade_allowed'] = False  # Block trade - cannot verify without data
            result['verdict'] = 'ERROR'
            result['verdict_message'] = f'Failed to download historical data for {stock_symbol}. Check Breeze API authentication and connectivity.'
            result['risk_checks'] = [{
                'id': 'data_download_failed',
                'name': 'Historical Data Download Failed',
                'description': f'Failed to download historical price data for {stock_symbol}',
                'status': 'FAIL',
                'severity': 'HIGH',
                'value': 'Download Failed',
                'threshold': 'Data Required',
                'message': f'Breeze API did not return data for {stock_symbol}. Check API authentication or try again.'
            }]
            result['risk_summary'] = {
                'total_checks': 1,
                'passed': 0,
                'failed': 1,
                'warnings': 0,
                'skipped': 0,
                'pass_rate': 0
            }
            result['recommendations'].append(f'Check Breeze API authentication and retry. If issue persists, verify stock code {stock_symbol} is valid.')
            return result

        # Convert to list for easier processing
        data_list = list(historical_data)
        logger.info(f"Found {len(data_list)} historical records for {stock_symbol}")

        if len(data_list) < 5:
            result['success'] = False
            result['error'] = f'Insufficient historical data for {stock_symbol}. Need at least 5 days.'
            return result

        # Extract prices (most recent first)
        closes = [float(d.close) for d in data_list]
        highs = [float(d.high) for d in data_list]
        lows = [float(d.low) for d in data_list]
        opens = [float(d.open) for d in data_list]
        volumes = [d.volume for d in data_list]
        dates = [d.datetime for d in data_list]

        current_price = closes[0]
        result['analysis']['current_price'] = current_price
        result['analysis']['data_points'] = len(closes)
        result['analysis']['date_range'] = {
            'from': dates[-1].strftime('%Y-%m-%d') if dates else None,
            'to': dates[0].strftime('%Y-%m-%d') if dates else None
        }

        # ===== Fetch Nifty closes for relative comparison on 5/15/30-day checks =====
        nifty_closes: list = []
        try:
            nifty_hist = HistoricalPrice.objects.filter(
                stock_code='NIFTY',
                exchange_code='NSE',
                product_type='cash',
                interval='1day'
            ).order_by('-datetime')[:35]
            nifty_closes = [float(d.close) for d in nifty_hist]
            if len(nifty_closes) < 31:
                logger.info(
                    f"Only {len(nifty_closes)} Nifty daily records; longer-window relative gates will fall back to absolute-only"
                )
        except Exception as e:
            logger.warning(f"Could not fetch Nifty historical data for relative comparison: {e}")
            nifty_closes = []

        def _nifty_change_over(window: int) -> Optional[float]:
            if len(nifty_closes) > window:
                past = nifty_closes[window]
                if past:
                    return ((nifty_closes[0] - past) / past) * 100
            return None

        result['analysis']['nifty_data_points'] = len(nifty_closes)

        # ============================================================================
        # RISK CHECK 1: 5-Day Loss Check (> 3% absolute, Nifty-relative gate)
        # ============================================================================
        check_1 = {
            'id': 'five_day_loss',
            'name': '5-Day Price Drop',
            'description': (
                'Stock should not have lost more than 3% in last 5 trading days. '
                'Waived to WARNING if stock outperformed Nifty by ≥ +1.0pp; '
                'hard-rejected if stock underperformed Nifty by ≥ 4.0pp.'
            ),
            'threshold': '-3% (abs) · Nifty-rel override +1.0pp · hard-reject -4.0pp',
            'status': 'PASS',
            'severity': 'HIGH',
            'value': None,
            'details': {}
        }

        if len(closes) >= 5:
            price_5_days_ago = closes[4]
            change_5d = ((current_price - price_5_days_ago) / price_5_days_ago) * 100
            check_1['details'] = {
                'current_price': current_price,
                'price_5_days_ago': price_5_days_ago,
                'change_pct': round(change_5d, 2)
            }
            _evaluate_price_drop_vs_nifty(
                check_1, 5, change_5d, -3.0, _nifty_change_over(5), result
            )

        result['risk_checks'].append(check_1)

        # ============================================================================
        # RISK CHECK 2: 15-Day Loss Check (> 5% absolute, Nifty-relative gate)
        # ============================================================================
        check_2 = {
            'id': 'fifteen_day_loss',
            'name': '15-Day Price Drop',
            'description': (
                'Stock should not have lost more than 5% in last 15 trading days. '
                'Waived to WARNING if stock outperformed Nifty by ≥ +0.5pp; '
                'hard-rejected if stock underperformed Nifty by ≥ 3.0pp.'
            ),
            'threshold': '-5% (abs) · Nifty-rel override +0.5pp · hard-reject -3.0pp',
            'status': 'PASS',
            'severity': 'HIGH',
            'value': None,
            'details': {}
        }

        if len(closes) >= 15:
            price_15_days_ago = closes[14]
            change_15d = ((current_price - price_15_days_ago) / price_15_days_ago) * 100
            check_2['details'] = {
                'current_price': current_price,
                'price_15_days_ago': price_15_days_ago,
                'change_pct': round(change_15d, 2)
            }
            _evaluate_price_drop_vs_nifty(
                check_2, 15, change_15d, -5.0, _nifty_change_over(15), result
            )
        else:
            check_2['status'] = 'SKIP'
            check_2['message'] = 'Insufficient data for 15-day check'

        result['risk_checks'].append(check_2)

        # ============================================================================
        # RISK CHECK 3: 30-Day Loss Check (> 10% absolute, Nifty-relative gate)
        # ============================================================================
        check_3 = {
            'id': 'thirty_day_loss',
            'name': '30-Day Price Drop',
            'description': (
                'Stock should not have lost more than 10% in last 30 trading days. '
                'Waived to WARNING if stock outperformed Nifty by ≥ 0.0pp (any outperformance); '
                'hard-rejected if stock underperformed Nifty by ≥ 2.0pp.'
            ),
            'threshold': '-10% (abs) · Nifty-rel override +0.0pp · hard-reject -2.0pp',
            'status': 'PASS',
            'severity': 'HIGH',
            'value': None,
            'details': {}
        }

        if len(closes) >= 30:
            price_30_days_ago = closes[29]
            change_30d = ((current_price - price_30_days_ago) / price_30_days_ago) * 100
            check_3['details'] = {
                'current_price': current_price,
                'price_30_days_ago': price_30_days_ago,
                'change_pct': round(change_30d, 2)
            }
            _evaluate_price_drop_vs_nifty(
                check_3, 30, change_30d, -10.0, _nifty_change_over(30), result
            )
        else:
            check_3['status'] = 'SKIP'
            check_3['message'] = 'Insufficient data for 30-day check'

        result['risk_checks'].append(check_3)

        # ============================================================================
        # RISK CHECK 4: Single Day Drop Check (> 2% on any day in last 5 days)
        # ============================================================================
        check_4 = {
            'id': 'single_day_drop',
            'name': 'Single Day Drop',
            'description': 'No single day should have more than 2% loss in last 5 trading days',
            'threshold': '-2% per day',
            'status': 'PASS',
            'severity': 'HIGH',
            'value': None,
            'details': {'daily_changes': []}
        }

        if len(closes) >= 5:
            daily_changes = []
            worst_day = {'date': None, 'change': 0}

            for i in range(min(5, len(closes) - 1)):
                # Calculate daily change (close to close)
                prev_close = closes[i + 1]
                curr_close = closes[i]
                daily_change = ((curr_close - prev_close) / prev_close) * 100

                daily_changes.append({
                    'date': dates[i].strftime('%Y-%m-%d'),
                    'change_pct': round(daily_change, 2),
                    'close': curr_close
                })

                if daily_change < worst_day['change']:
                    worst_day = {'date': dates[i].strftime('%Y-%m-%d'), 'change': daily_change}

            check_4['details']['daily_changes'] = daily_changes
            check_4['value'] = f"Worst: {worst_day['change']:+.2f}%"
            check_4['details']['worst_day'] = worst_day

            if worst_day['change'] < -2:
                check_4['status'] = 'FAIL'
                check_4['message'] = f'Stock dropped {abs(worst_day["change"]):.2f}% on {worst_day["date"]} (threshold: 2%)'
                result['trade_allowed'] = False
                result['recommendations'].append(f'⚠️ Avoid trade: Sharp {abs(worst_day["change"]):.2f}% single-day drop on {worst_day["date"]}')
            else:
                check_4['status'] = 'PASS'
                check_4['message'] = f'No single day drop exceeded 2% (worst: {worst_day["change"]:+.2f}%)'

        result['risk_checks'].append(check_4)

        # ============================================================================
        # RISK CHECK 5: Volatility Check (High volatility regime)
        # ============================================================================
        check_5 = {
            'id': 'volatility_regime',
            'name': 'Volatility Assessment',
            'description': 'Check if stock is in high volatility regime',
            'threshold': '> 3% daily range (warning)',
            'status': 'PASS',
            'severity': 'MEDIUM',
            'value': None,
            'details': {}
        }

        if len(closes) >= 20:
            # Calculate average true range (ATR) proxy
            daily_ranges = []
            for i in range(min(20, len(highs))):
                daily_range = ((highs[i] - lows[i]) / lows[i]) * 100 if lows[i] > 0 else 0
                daily_ranges.append(daily_range)

            avg_range = sum(daily_ranges) / len(daily_ranges) if daily_ranges else 0
            max_range = max(daily_ranges) if daily_ranges else 0

            # Calculate daily returns volatility
            returns = []
            for i in range(min(20, len(closes) - 1)):
                ret = (closes[i] - closes[i + 1]) / closes[i + 1] if closes[i + 1] > 0 else 0
                returns.append(ret)

            volatility = (sum([r ** 2 for r in returns]) / len(returns)) ** 0.5 * 100 if returns else 0

            check_5['value'] = f"Avg Range: {avg_range:.2f}%, Vol: {volatility:.2f}%"
            check_5['details'] = {
                'avg_daily_range_pct': round(avg_range, 2),
                'max_daily_range_pct': round(max_range, 2),
                'daily_volatility_pct': round(volatility, 2),
                'annualized_volatility_pct': round(volatility * (252 ** 0.5), 2)
            }

            if avg_range > 4:
                check_5['status'] = 'FAIL'
                check_5['message'] = f'Extremely high volatility (avg daily range: {avg_range:.2f}%)'
                result['trade_allowed'] = False
                result['recommendations'].append(f'⚠️ Avoid trade: Extreme volatility with {avg_range:.2f}% average daily range')
            elif avg_range > 3:
                check_5['status'] = 'WARNING'
                check_5['message'] = f'High volatility detected (avg daily range: {avg_range:.2f}%)'
                result['recommendations'].append(f'⚡ Caution: High volatility - consider smaller position size')
            else:
                check_5['status'] = 'PASS'
                check_5['message'] = f'Volatility within normal range (avg daily range: {avg_range:.2f}%)'

        result['risk_checks'].append(check_5)

        # ============================================================================
        # RISK CHECK 6: Volume Decline Check
        # ============================================================================
        check_6 = {
            'id': 'volume_trend',
            'name': 'Volume Trend',
            'description': 'Check for declining volume trend (bearish signal)',
            'threshold': '< 50% of 20-day avg',
            'status': 'PASS',
            'severity': 'MEDIUM',
            'value': None,
            'details': {}
        }

        if len(volumes) >= 20 and all(v > 0 for v in volumes[:20]):
            recent_avg_vol = sum(volumes[:5]) / 5
            longer_avg_vol = sum(volumes[:20]) / 20

            vol_ratio = (recent_avg_vol / longer_avg_vol) * 100 if longer_avg_vol > 0 else 100

            check_6['value'] = f"{vol_ratio:.0f}% of avg"
            check_6['details'] = {
                'recent_5d_avg_volume': int(recent_avg_vol),
                'longer_20d_avg_volume': int(longer_avg_vol),
                'volume_ratio_pct': round(vol_ratio, 2)
            }

            if vol_ratio < 50:
                check_6['status'] = 'WARNING'
                check_6['message'] = f'Volume significantly below average ({vol_ratio:.0f}% of 20-day avg)'
                result['recommendations'].append(f'⚡ Note: Low volume may indicate lack of interest')
            else:
                check_6['status'] = 'PASS'
                check_6['message'] = f'Volume healthy ({vol_ratio:.0f}% of 20-day average)'

        result['risk_checks'].append(check_6)

        # ============================================================================
        # RISK CHECK 7: Support Level Breach Check
        # ============================================================================
        check_7 = {
            'id': 'support_breach',
            'name': 'Support Level Check',
            'description': 'Check if price has broken below key support levels',
            'threshold': 'Below 20-day low',
            'status': 'PASS',
            'severity': 'HIGH',
            'value': None,
            'details': {}
        }

        if len(lows) >= 20:
            # Calculate support levels
            low_20d = min(lows[:20])
            low_50d = min(lows[:50]) if len(lows) >= 50 else low_20d

            # Calculate moving averages as dynamic support
            sma_20 = sum(closes[:20]) / 20
            sma_50 = sum(closes[:50]) / 50 if len(closes) >= 50 else sma_20

            check_7['details'] = {
                'current_price': current_price,
                '20_day_low': round(low_20d, 2),
                '50_day_low': round(low_50d, 2),
                'sma_20': round(sma_20, 2),
                'sma_50': round(sma_50, 2),
                'below_sma_20': current_price < sma_20,
                'below_sma_50': current_price < sma_50
            }

            # Check if current price is at or near 20-day low
            proximity_to_low = ((current_price - low_20d) / low_20d) * 100 if low_20d > 0 else 0
            check_7['value'] = f"{proximity_to_low:.1f}% above 20d low"

            if current_price <= low_20d:
                check_7['status'] = 'FAIL'
                check_7['message'] = f'Price at/below 20-day low (₹{low_20d:.2f}) - major support broken'
                result['trade_allowed'] = False
                result['recommendations'].append(f'⚠️ Avoid trade: Price broke 20-day support at ₹{low_20d:.2f}')
            elif proximity_to_low < 1:
                check_7['status'] = 'WARNING'
                check_7['message'] = f'Price very close to 20-day low ({proximity_to_low:.1f}% above)'
                result['recommendations'].append(f'⚡ Caution: Price near support - wait for confirmation')
            elif current_price < sma_20 and current_price < sma_50:
                check_7['status'] = 'WARNING'
                check_7['message'] = f'Price below both 20-day and 50-day moving averages'
                result['recommendations'].append(f'⚡ Note: Price below key moving averages - bearish signal')
            else:
                check_7['status'] = 'PASS'
                check_7['message'] = f'Price {proximity_to_low:.1f}% above 20-day low - support intact'

        result['risk_checks'].append(check_7)

        # ============================================================================
        # RISK CHECK 8: Trend Reversal Check (Lower Highs Pattern)
        # ============================================================================
        check_8 = {
            'id': 'trend_reversal',
            'name': 'Trend Analysis',
            'description': 'Check for trend reversal signals (lower highs/lower lows)',
            'threshold': '3+ consecutive lower highs',
            'status': 'PASS',
            'severity': 'MEDIUM',
            'value': None,
            'details': {}
        }

        if len(highs) >= 10:
            # Check for lower highs pattern (last 5 days)
            lower_highs_count = 0
            lower_lows_count = 0

            for i in range(min(4, len(highs) - 1)):
                if highs[i] < highs[i + 1]:
                    lower_highs_count += 1
                if lows[i] < lows[i + 1]:
                    lower_lows_count += 1

            # Calculate trend direction
            if len(closes) >= 10:
                recent_trend = closes[0] - closes[9]  # Last 10 days
                trend_direction = 'UP' if recent_trend > 0 else 'DOWN' if recent_trend < 0 else 'FLAT'
            else:
                trend_direction = 'UNKNOWN'

            check_8['value'] = f"{lower_highs_count} lower highs"
            check_8['details'] = {
                'lower_highs_count': lower_highs_count,
                'lower_lows_count': lower_lows_count,
                'trend_direction': trend_direction,
                '10_day_change': round(((closes[0] - closes[min(9, len(closes) - 1)]) / closes[min(9, len(closes) - 1)]) * 100, 2) if len(closes) >= 2 else 0
            }

            if lower_highs_count >= 4 and lower_lows_count >= 3:
                check_8['status'] = 'FAIL'
                check_8['message'] = f'Strong downtrend pattern: {lower_highs_count} lower highs, {lower_lows_count} lower lows'
                result['trade_allowed'] = False
                result['recommendations'].append(f'⚠️ Avoid trade: Clear downtrend with consecutive lower highs and lows')
            elif lower_highs_count >= 3:
                check_8['status'] = 'WARNING'
                check_8['message'] = f'Potential trend weakness: {lower_highs_count} consecutive lower highs'
                result['recommendations'].append(f'⚡ Caution: {lower_highs_count} lower highs - trend may be weakening')
            else:
                check_8['status'] = 'PASS'
                check_8['message'] = f'Trend structure intact (trend: {trend_direction})'

        result['risk_checks'].append(check_8)

        # ============================================================================
        # CALCULATE SUMMARY
        # ============================================================================
        passed_count = sum(1 for c in result['risk_checks'] if c['status'] == 'PASS')
        failed_count = sum(1 for c in result['risk_checks'] if c['status'] == 'FAIL')
        warning_count = sum(1 for c in result['risk_checks'] if c['status'] == 'WARNING')
        skipped_count = sum(1 for c in result['risk_checks'] if c['status'] == 'SKIP')

        result['risk_summary'] = {
            'total_checks': len(result['risk_checks']),
            'passed': passed_count,
            'failed': failed_count,
            'warnings': warning_count,
            'skipped': skipped_count,
            'pass_rate': round((passed_count / (len(result['risk_checks']) - skipped_count)) * 100, 1) if (len(result['risk_checks']) - skipped_count) > 0 else 0
        }

        # Add price history for chart
        result['analysis']['price_history'] = [
            {
                'date': dates[i].strftime('%Y-%m-%d'),
                'close': closes[i],
                'high': highs[i],
                'low': lows[i],
                'open': opens[i],
                'volume': volumes[i]
            }
            for i in range(min(30, len(closes)))  # Last 30 days for chart
        ]

        # Final verdict
        if result['trade_allowed']:
            result['verdict'] = 'APPROVED'
            result['verdict_message'] = f'Historical data verification passed ({passed_count}/{len(result["risk_checks"])} checks passed)'
            if warning_count > 0:
                result['verdict_message'] += f' with {warning_count} warning(s)'
        else:
            result['verdict'] = 'BLOCKED'
            result['verdict_message'] = f'Trade blocked due to {failed_count} failed risk check(s)'

        logger.info(f"Historical verification complete: {result['verdict']}")
        logger.info(f"Summary: {passed_count} passed, {failed_count} failed, {warning_count} warnings")

        return result

    except Exception as e:
        logger.error(f"Error in verify_historical_data: {e}", exc_info=True)
        return {
            'success': False,
            'stock_symbol': stock_symbol,
            'error': str(e),
            'trade_allowed': True,  # Don't block trade on error
            'risk_checks': [],
            'risk_summary': {}
        }


def prepare_data_for_analysis(
    stock_symbol: str,
    expiry_date: str,
    force_refresh: bool = False,
    include_options: bool = True
) -> Dict:
    """
    Main entry point for preparing historical data before Verify Trade
    or Futures Algorithm analysis.

    This function:
    1. Collects 365 days of historical data for all related instruments
    2. Saves data to the database
    3. (Future) Runs verification analysis on the data

    Use this before calling comprehensive_futures_analysis() to ensure
    you have complete historical data for analysis.

    Args:
        stock_symbol: Stock symbol (e.g., 'HDFCBANK', 'RELIANCE')
        expiry_date: Primary expiry date in YYYY-MM-DD format
        force_refresh: Force re-fetch even if recent data exists (default False)
        include_options: Include options chain data (default True)

    Returns:
        dict: {
            'success': bool,
            'data_collection': {...},  # Results from collect_historical_data_for_token
            'verification': {...},  # Results from verify_historical_data (placeholder)
            'ready_for_analysis': bool,
            'error': str (if failed)
        }
    """
    logger.info("=" * 80)
    logger.info(f"PREPARING DATA FOR ANALYSIS: {stock_symbol}")
    logger.info("=" * 80)

    result = {
        'success': True,
        'stock_symbol': stock_symbol,
        'expiry_date': expiry_date,
        'data_collection': None,
        'verification': None,
        'ready_for_analysis': False
    }

    try:
        # ===== RESOLVE BREEZE STOCK CODE =====
        # Historical data is saved with Breeze stock code, not original symbol
        from apps.brokers.utils.security_master import get_futures_instrument

        expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
        expiry_formatted_sm = expiry_dt.strftime('%d-%b-%Y')

        instrument_info = get_futures_instrument(stock_symbol, expiry_formatted_sm)
        if instrument_info and instrument_info.get('short_name'):
            breeze_stock_code = instrument_info['short_name']
            logger.info(f"Resolved Breeze code: {stock_symbol} -> {breeze_stock_code}")
        else:
            breeze_stock_code = stock_symbol
            logger.warning(f"Could not resolve Breeze code for {stock_symbol}, using original")

        # Step 1: Check if we have recent data (skip if force_refresh)
        if not force_refresh:
            from apps.brokers.models import HistoricalPrice
            from django.utils import timezone

            # Check when equity data was last updated (use Breeze stock code)
            recent_data = HistoricalPrice.objects.filter(
                stock_code=breeze_stock_code,  # Use Breeze stock code
                exchange_code='NSE',
                product_type='cash',
                interval='1day'
            ).order_by('-created_at').first()

            if recent_data:
                data_age = timezone.now() - recent_data.created_at
                minutes_old = data_age.total_seconds() / 60

                if minutes_old < 5:  # Data less than 5 minutes old
                    logger.info(f"Recent data exists (age: {minutes_old:.1f} minutes). Skipping refresh.")
                    result['data_collection'] = {
                        'success': True,
                        'skipped': True,
                        'reason': f'Data is only {minutes_old:.1f} minutes old',
                        'last_updated': recent_data.created_at.isoformat()
                    }
                    result['ready_for_analysis'] = True

                    # Run verification on existing data
                    result['verification'] = verify_historical_data(stock_symbol, expiry_date)
                    return result

        # Step 2: Collect historical data
        logger.info("\nCollecting historical data for all instruments...")
        collection_result = collect_historical_data_for_token(
            stock_symbol=stock_symbol,
            expiry_date=expiry_date,
            lookback_days=365,
            include_options=include_options,
            max_options_per_expiry=50  # Limit to nearest 50 strikes
        )

        result['data_collection'] = collection_result

        if not collection_result.get('success'):
            result['success'] = False
            result['error'] = collection_result.get('error', 'Data collection failed')
            return result

        # Step 3: Verify the collected data
        logger.info("\nVerifying collected data...")
        result['verification'] = verify_historical_data(stock_symbol, expiry_date)

        # Determine if ready for analysis
        result['ready_for_analysis'] = (
            collection_result.get('summary', {}).get('successful', 0) > 0 and
            collection_result.get('summary', {}).get('total_records_saved', 0) > 0
        )

        logger.info(f"\nData preparation complete. Ready for analysis: {result['ready_for_analysis']}")
        return result

    except Exception as e:
        logger.error(f"Error in prepare_data_for_analysis: {e}", exc_info=True)
        return {
            'success': False,
            'stock_symbol': stock_symbol,
            'error': str(e)
        }
