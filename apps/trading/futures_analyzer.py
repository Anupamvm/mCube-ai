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
import pandas as pd
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Dict, List, Tuple, Optional

from django.core.cache import cache
from apps.brokers.integrations.breeze import get_breeze_client
from apps.data.data_analyzers import (
    OpenInterestAnalyzer,
    DMAAnalyzer,
    TechnicalIndicatorAnalyzer,
    VolumeAnalyzer
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

            logger.info(f"Breeze get_names response: {names_resp}")

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

                            # Cache for 1 hour
                            cache.set(cache_key, result, 3600)
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

                    cache.set(cache_key, result, 3600)
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

    try:
        # ============================================================================
        # STEP 0: Resolve Breeze Symbol using get_names API
        # ============================================================================
        logger.info("\n" + "=" * 80)
        logger.info("STEP 0: Resolving Breeze Symbol")
        logger.info("=" * 80)

        symbol_resolution = resolve_breeze_symbol(stock_symbol, expiry_date)

        if not symbol_resolution.get('success'):
            execution_log.append({
                'step': 0,
                'action': 'Symbol Resolution',
                'status': 'FAIL',
                'message': f"Failed to resolve symbol: {symbol_resolution.get('error')}",
                'details': symbol_resolution
            })
            return {
                'success': False,
                'execution_log': execution_log,
                'metrics': metrics,
                'verdict': 'FAIL',
                'direction': 'NEUTRAL',
                'composite_score': 0,
                'error': f"Symbol resolution failed: {symbol_resolution.get('error')}"
            }

        breeze_symbol = symbol_resolution.get('stock_code', stock_symbol)
        short_name = symbol_resolution.get('short_name', stock_symbol)
        resolved_expiry = symbol_resolution.get('expiry_date', '')

        execution_log.append({
            'step': 0,
            'action': 'Symbol Resolution',
            'status': 'PASS',
            'message': f"Resolved to: {breeze_symbol} ({short_name})",
            'details': {
                'original_symbol': stock_symbol,
                'breeze_symbol': breeze_symbol,
                'short_name': short_name,
                'resolved_expiry': resolved_expiry,
                'lot_size': symbol_resolution.get('lot_size', 0),
                'note': symbol_resolution.get('note', 'Exact match found')
            }
        })

        logger.info(f"✅ Resolved symbol: {stock_symbol} → {breeze_symbol}")

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
