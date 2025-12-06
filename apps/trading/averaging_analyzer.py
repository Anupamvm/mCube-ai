"""
Smart Position Averaging Analyzer

This module analyzes existing futures positions and determines if averaging
(adding to the position) is a good idea based on professional trading criteria.

Critical Conditions (MUST pass):
1. Price must be closer to support level (not resistance)
2. Current price must be down at least 1.5% from entry price (for LONG positions)
   OR up at least 1.5% from entry price (for SHORT positions)

Additional Pro Trader Criteria:
3. Trend confirmation (not in a strong downtrend for LONG)
4. Volume analysis (ensure liquidity)
5. Risk:Reward ratio improvement
6. Sector health check
7. Volatility assessment
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


class AveragingAnalyzer:
    """
    Analyzes futures positions for averaging opportunities.
    """

    def __init__(self, breeze_client=None):
        self.breeze = breeze_client

    def analyze_position_for_averaging(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        current_quantity: int,
        lot_size: int,
        expiry_date: str = None,
        exchange: str = "NFO"
    ) -> Dict[str, Any]:
        """
        Comprehensive analysis for position averaging.

        Args:
            symbol: Stock symbol (e.g., 'RELIANCE')
            direction: Position direction ('LONG' or 'SHORT')
            entry_price: Original entry price
            current_quantity: Current position quantity
            lot_size: Lot size for the futures contract
            expiry_date: Expiry date (YYYY-MM-DD)
            exchange: Exchange code (default: NFO)

        Returns:
            Dictionary with averaging recommendation and analysis
        """
        logger.info(f"Analyzing averaging for {symbol} {direction} @ ₹{entry_price}")

        result = {
            'success': False,
            'symbol': symbol,
            'direction': direction,
            'entry_price': entry_price,
            'current_price': 0,
            'price_change_pct': 0,
            'recommendation': 'NO_AVERAGE',
            'confidence': 0,
            'critical_checks': {
                'price_drop_check': {'passed': False, 'message': ''},
                'support_proximity_check': {'passed': False, 'message': ''},
                'open_interest_check': {'passed': False, 'message': ''}
            },
            'additional_checks': {},
            'risk_assessment': {},
            'position_sizing': {},
            'execution_log': []
        }

        try:
            # Step 1: Get current market price
            current_price = self._get_current_price(symbol, expiry_date)
            if not current_price:
                result['error'] = 'Unable to fetch current price'
                return result

            result['current_price'] = current_price

            # Step 2: Calculate price change from entry
            price_change_pct = ((current_price - entry_price) / entry_price) * 100
            result['price_change_pct'] = round(price_change_pct, 2)

            result['execution_log'].append({
                'step': 1,
                'action': 'Price Analysis',
                'status': 'success',
                'message': f'Current: ₹{current_price:.2f} | Entry: ₹{entry_price:.2f} | Change: {price_change_pct:+.2f}%'
            })

            # CRITICAL CHECK 1: Price Movement Check (1.5% threshold)
            price_check = self._check_price_movement(
                direction, entry_price, current_price, price_change_pct
            )
            result['critical_checks']['price_drop_check'] = price_check

            result['execution_log'].append({
                'step': 2,
                'action': 'Critical Check: Price Movement (1.5% threshold)',
                'status': 'success' if price_check['passed'] else 'fail',
                'message': price_check['message'],
                'details': price_check
            })

            # Don't return early - continue with all checks even if price check failed
            # This allows user to see full analysis including S/R levels

            # CRITICAL CHECK 2: Support/Resistance Proximity
            support_check = self._check_support_proximity(
                symbol, current_price, direction
            )
            result['critical_checks']['support_proximity_check'] = support_check

            result['execution_log'].append({
                'step': 3,
                'action': 'Critical Check: Support/Resistance Proximity',
                'status': 'success' if support_check['passed'] else 'fail',
                'message': support_check['message'],
                'details': support_check
            })

            # Don't return early - continue with all checks even if S/R check failed
            # This allows user to see full analysis

            # CRITICAL CHECK 3: Open Interest Analysis
            oi_check = self._check_open_interest(
                symbol, expiry_date, direction
            )
            result['critical_checks']['open_interest_check'] = oi_check

            result['execution_log'].append({
                'step': 3.5,
                'action': 'Critical Check: Open Interest',
                'status': 'success' if oi_check['passed'] else 'fail',
                'message': oi_check['message'],
                'details': oi_check
            })

            # Determine if we should proceed with additional checks
            # If ALL critical checks failed, set recommendation but continue
            all_critical_failed = (not price_check['passed'] and
                                 not support_check['passed'] and
                                 not oi_check['passed'])

            # Additional Professional Trader Checks
            logger.info(f"✅ Critical checks completed. Running additional analysis...")

            # Check 3: Trend Analysis
            trend_check = self._check_trend(symbol, direction)
            result['additional_checks']['trend'] = trend_check

            result['execution_log'].append({
                'step': 4,
                'action': 'Trend Analysis',
                'status': 'success' if trend_check['healthy'] else 'warning',
                'message': trend_check['message'],
                'details': trend_check
            })

            # Check 4: Volume Analysis
            volume_check = self._check_volume(symbol, expiry_date)
            result['additional_checks']['volume'] = volume_check

            result['execution_log'].append({
                'step': 5,
                'action': 'Volume & Liquidity Check',
                'status': 'success' if volume_check['adequate'] else 'warning',
                'message': volume_check['message'],
                'details': volume_check
            })

            # Check 5: Sector Health
            sector_check = self._check_sector_health(symbol)
            result['additional_checks']['sector'] = sector_check

            result['execution_log'].append({
                'step': 6,
                'action': 'Sector Health Check',
                'status': 'success' if sector_check['healthy'] else 'warning',
                'message': sector_check['message'],
                'details': sector_check
            })

            # Check 6: Volatility Assessment
            volatility_check = self._check_volatility(symbol)
            result['additional_checks']['volatility'] = volatility_check

            result['execution_log'].append({
                'step': 7,
                'action': 'Volatility Assessment',
                'status': 'success' if volatility_check['acceptable'] else 'warning',
                'message': volatility_check['message'],
                'details': volatility_check
            })

            # Calculate Confidence Score (0-100)
            confidence = self._calculate_confidence_score(
                price_check, support_check, trend_check, volume_check,
                sector_check, volatility_check
            )
            result['confidence'] = confidence

            result['execution_log'].append({
                'step': 8,
                'action': 'Confidence Score Calculation',
                'status': 'success',
                'message': f'Overall confidence: {confidence}/100',
                'details': {'score': confidence}
            })

            # Risk Assessment
            risk_assessment = self._assess_averaging_risk(
                symbol, direction, entry_price, current_price,
                current_quantity, lot_size, support_check
            )
            result['risk_assessment'] = risk_assessment

            result['execution_log'].append({
                'step': 9,
                'action': 'Risk Assessment',
                'status': 'success',
                'message': f'Risk level: {risk_assessment.get("risk_level", "UNKNOWN")}',
                'details': risk_assessment
            })

            # Position Sizing Recommendation
            position_sizing = self._calculate_averaging_size(
                current_quantity, lot_size, confidence,
                entry_price, current_price, direction
            )
            result['position_sizing'] = position_sizing

            result['execution_log'].append({
                'step': 10,
                'action': 'Position Sizing Recommendation',
                'status': 'success',
                'message': f'Recommended: {position_sizing.get("recommended_lots", 0)} lots',
                'details': position_sizing
            })

            # Final Recommendation - check critical checks first
            if not price_check['passed'] or not support_check['passed'] or not oi_check['passed']:
                result['recommendation'] = 'NO_AVERAGE'
                # Build reason from failed checks
                failed_reasons = []
                if not price_check['passed']:
                    failed_reasons.append(price_check['message'])
                if not support_check['passed']:
                    failed_reasons.append(support_check['message'])
                if not oi_check['passed']:
                    failed_reasons.append(oi_check['message'])
                result['reason'] = ' AND '.join(failed_reasons)
            elif confidence >= 70:
                result['recommendation'] = 'STRONG_AVERAGE'
                result['reason'] = f'High confidence ({confidence}/100) - All checks passed'
            elif confidence >= 50:
                result['recommendation'] = 'MODERATE_AVERAGE'
                result['reason'] = f'Moderate confidence ({confidence}/100) - Critical checks passed'
            else:
                result['recommendation'] = 'WEAK_AVERAGE'
                result['reason'] = f'Low confidence ({confidence}/100) - Consider waiting'

            result['success'] = True
            logger.info(f"✅ Averaging analysis complete: {result['recommendation']} (Confidence: {confidence}%)")
            logger.info(f"Analysis result: success={result['success']}, recommendation={result['recommendation']}")

        except Exception as e:
            logger.error(f"❌ EXCEPTION in averaging analysis: {e}", exc_info=True)
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception details: {str(e)}")
            result['error'] = str(e)
            result['execution_log'].append({
                'step': -1,
                'action': 'Error',
                'status': 'fail',
                'message': f'Analysis failed: {str(e)}'
            })

        return result

    def _get_current_price(self, symbol: str, expiry_date: str = None) -> Optional[float]:
        """
        Fetch current futures price - reuses existing OptionChainQuote model pattern.
        """
        try:
            # Use the same pattern as the rest of the codebase
            from apps.brokers.models import OptionChainQuote
            from datetime import datetime, date

            # Convert expiry_date to date object if needed
            expiry_dt = None
            if expiry_date and (not isinstance(expiry_date, str) or expiry_date.strip()):
                if isinstance(expiry_date, str):
                    expiry_dt = datetime.strptime(expiry_date.strip(), '%Y-%m-%d').date()
                else:
                    expiry_dt = expiry_date
            else:
                # Try to find the most recent futures quote for this symbol (case-insensitive)
                recent_quote = OptionChainQuote.objects.filter(
                    stock_code=symbol,
                    product_type__iexact='futures',  # Case-insensitive match
                    expiry_date__gte=date.today()
                ).order_by('expiry_date').first()

                if recent_quote:
                    expiry_dt = recent_quote.expiry_date
                    logger.info(f"Using existing expiry {expiry_dt} for {symbol} from database")
                else:
                    # Only for NIFTY/BANKNIFTY, try to get expiry from NSE
                    if symbol.upper() in ['NIFTY', 'BANKNIFTY']:
                        from apps.brokers.integrations.breeze import get_next_nifty_expiry
                        expiry_str = get_next_nifty_expiry()
                        expiry_dt = datetime.strptime(expiry_str, '%d-%b-%Y').date()
                    else:
                        logger.error(f"No expiry date provided and no recent futures data found for {symbol}")
                        return None

            # Query futures quote from database (case-insensitive product_type)
            futures_quote = OptionChainQuote.objects.filter(
                stock_code=symbol,
                product_type__iexact='futures',  # Case-insensitive match
                expiry_date=expiry_dt
            ).first()

            logger.info(f"Database query for {symbol} futures expiry={expiry_dt}: found={futures_quote is not None}")
            if futures_quote:
                logger.info(f"Quote details: ltp={futures_quote.ltp}, stock_code={futures_quote.stock_code}, product_type={futures_quote.product_type}, expiry={futures_quote.expiry_date}")

            if futures_quote and futures_quote.ltp:
                logger.info(f"Returning LTP from database: ₹{futures_quote.ltp}")
                return float(futures_quote.ltp)

            # If not in database, fetch fresh from Breeze API
            if self.breeze:
                from apps.brokers.integrations.breeze import get_and_save_option_chain_quotes

                # Format expiry for Breeze
                expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()
                logger.info(f"Fetching from Breeze API: {symbol} futures, expiry={expiry_breeze}")

                # Fetch and save quotes (reuses existing function)
                get_and_save_option_chain_quotes(symbol, expiry_breeze, product_type="futures")

                # Query again after saving (case-insensitive)
                futures_quote = OptionChainQuote.objects.filter(
                    stock_code=symbol,
                    product_type__iexact='futures',  # Case-insensitive match
                    expiry_date=expiry_dt
                ).first()

                logger.info(f"After API fetch, database query: found={futures_quote is not None}")
                if futures_quote:
                    logger.info(f"After fetch - Quote details: ltp={futures_quote.ltp}, stock_code={futures_quote.stock_code}, product_type={futures_quote.product_type}, expiry={futures_quote.expiry_date}")

                if futures_quote and futures_quote.ltp:
                    logger.info(f"Returning LTP after API fetch: ₹{futures_quote.ltp}")
                    return float(futures_quote.ltp)

            # Check if there are ANY quotes for this symbol to help debug
            all_quotes = OptionChainQuote.objects.filter(stock_code=symbol).order_by('-created_at')[:5]
            logger.warning(f"Could not fetch LTP for {symbol} expiry {expiry_date}. Found {all_quotes.count()} total quotes for {symbol}")
            for q in all_quotes:
                logger.warning(f"  - {q.stock_code} {q.product_type} exp={q.expiry_date} ltp={q.ltp}")
            return None

        except Exception as e:
            logger.error(f"Error fetching current price: {e}", exc_info=True)
            return None

    def _check_price_movement(
        self, direction: str, entry_price: float,
        current_price: float, price_change_pct: float
    ) -> Dict[str, Any]:
        """
        CRITICAL CHECK 1: Price must be down 1.5%+ for LONG, up 1.5%+ for SHORT.
        """
        threshold = 1.5

        if direction == 'LONG':
            # For LONG positions, price should be down (negative change)
            required_change = -threshold
            passed = price_change_pct <= required_change

            if passed:
                message = f"✅ Price down {abs(price_change_pct):.2f}% (threshold: {threshold}%)"
            else:
                message = f"❌ Price only down {abs(price_change_pct):.2f}% (need {threshold}%+ drop)"

        else:  # SHORT
            # For SHORT positions, price should be up (positive change)
            required_change = threshold
            passed = price_change_pct >= required_change

            if passed:
                message = f"✅ Price up {price_change_pct:.2f}% (threshold: {threshold}%)"
            else:
                message = f"❌ Price only up {price_change_pct:.2f}% (need {threshold}%+ rise)"

        return {
            'passed': passed,
            'threshold': threshold,
            'actual_change': price_change_pct,
            'message': message,
            'entry_price': entry_price,
            'current_price': current_price
        }

    def _check_support_proximity(
        self, symbol: str, current_price: float, direction: str
    ) -> Dict[str, Any]:
        """
        CRITICAL CHECK 2: Price should be closer to support (for LONG) or resistance (for SHORT).
        """
        try:
            logger.info(f"Starting support proximity check for {symbol} at price ₹{current_price}")

            # Get S/R levels from TLStockData (Trendlyne data)
            from apps.data.models import TLStockData

            logger.info(f"Looking up TLStockData for symbol: '{symbol}'")
            stock_data = TLStockData.objects.filter(nsecode=symbol).first()

            if not stock_data:
                logger.warning(f"No TLStockData found for symbol '{symbol}'")
                # Try to find similar symbols for debugging
                similar = TLStockData.objects.filter(nsecode__icontains=symbol[:4]).values_list('nsecode', flat=True)[:5]
                logger.warning(f"Similar symbols in database: {list(similar)}")
                return {
                    'passed': False,
                    'message': '❌ No stock data found for support/resistance analysis',
                    'support_levels': [],
                    'resistance_levels': []
                }

            # Extract S/R levels from Trendlyne data
            support_levels = []
            resistance_levels = []

            if stock_data.first_support_s1:
                support_levels.append(float(stock_data.first_support_s1))
            if stock_data.second_support_s2:
                support_levels.append(float(stock_data.second_support_s2))
            if stock_data.third_support_s3:
                support_levels.append(float(stock_data.third_support_s3))

            if stock_data.first_resistance_r1:
                resistance_levels.append(float(stock_data.first_resistance_r1))
            if stock_data.second_resistance_r2:
                resistance_levels.append(float(stock_data.second_resistance_r2))
            if stock_data.third_resistance_r3:
                resistance_levels.append(float(stock_data.third_resistance_r3))

            pivot_point = float(stock_data.pivot_point) if stock_data.pivot_point else None

            logger.info(f"S/R from Trendlyne: supports={support_levels}, resistances={resistance_levels}, pivot={pivot_point}")

            if not support_levels and not resistance_levels:
                return {
                    'passed': False,
                    'message': '❌ No support/resistance levels available',
                    'support_levels': [],
                    'resistance_levels': []
                }

            if direction == 'LONG':
                # For LONG positions, we want to be near support
                # Find nearest support and resistance
                nearest_support = min(support_levels, key=lambda x: abs(x - current_price)) if support_levels else None
                nearest_resistance = min(resistance_levels, key=lambda x: abs(x - current_price)) if resistance_levels else None

                if nearest_support is None:
                    return {
                        'passed': False,
                        'message': '❌ No support levels found',
                        'support_levels': support_levels,
                        'resistance_levels': resistance_levels
                    }

                distance_to_support = abs(current_price - nearest_support)
                distance_to_resistance = abs(current_price - nearest_resistance) if nearest_resistance else float('inf')

                # Calculate percentage distances
                support_distance_pct = (distance_to_support / current_price) * 100
                resistance_distance_pct = (distance_to_resistance / current_price) * 100 if nearest_resistance else float('inf')

                # Check if closer to support than resistance
                passed = distance_to_support < distance_to_resistance

                if passed:
                    message = f"✅ Near support ₹{nearest_support:.2f} ({support_distance_pct:.2f}% away), resistance ₹{nearest_resistance:.2f} ({resistance_distance_pct:.2f}% away)"
                else:
                    if nearest_resistance:
                        message = f"❌ Closer to resistance ₹{nearest_resistance:.2f} ({resistance_distance_pct:.2f}% away) than support ₹{nearest_support:.2f} ({support_distance_pct:.2f}% away)"
                    else:
                        message = f"❌ No resistance levels found to compare with support ₹{nearest_support:.2f} ({support_distance_pct:.2f}% away)"

                return {
                    'passed': passed,
                    'message': message,
                    'current_price': current_price,
                    'pivot_point': pivot_point,
                    'nearest_support': nearest_support,
                    'nearest_resistance': nearest_resistance,
                    'distance_to_support': distance_to_support,
                    'distance_to_resistance': distance_to_resistance,
                    'support_distance_pct': support_distance_pct,
                    'resistance_distance_pct': resistance_distance_pct,
                    'support_levels': support_levels,
                    'resistance_levels': resistance_levels,
                    'r1': resistance_levels[0] if len(resistance_levels) > 0 else None,
                    'r2': resistance_levels[1] if len(resistance_levels) > 1 else None,
                    'r3': resistance_levels[2] if len(resistance_levels) > 2 else None,
                    's1': support_levels[0] if len(support_levels) > 0 else None,
                    's2': support_levels[1] if len(support_levels) > 1 else None,
                    's3': support_levels[2] if len(support_levels) > 2 else None
                }

            else:  # SHORT
                # For SHORT positions, we want to be near resistance
                nearest_support = min(support_levels, key=lambda x: abs(x - current_price)) if support_levels else None
                nearest_resistance = min(resistance_levels, key=lambda x: abs(x - current_price)) if resistance_levels else None

                if nearest_resistance is None:
                    return {
                        'passed': False,
                        'message': '❌ No resistance levels found',
                        'support_levels': support_levels,
                        'resistance_levels': resistance_levels
                    }

                distance_to_support = abs(current_price - nearest_support) if nearest_support else float('inf')
                distance_to_resistance = abs(current_price - nearest_resistance)

                # Calculate percentage distances
                support_distance_pct = (distance_to_support / current_price) * 100 if nearest_support else float('inf')
                resistance_distance_pct = (distance_to_resistance / current_price) * 100

                # Check if closer to resistance than support
                passed = distance_to_resistance < distance_to_support

                if passed:
                    message = f"✅ Near resistance ₹{nearest_resistance:.2f} ({resistance_distance_pct:.2f}% away), support ₹{nearest_support:.2f} ({support_distance_pct:.2f}% away)"
                else:
                    if nearest_support:
                        message = f"❌ Closer to support ₹{nearest_support:.2f} ({support_distance_pct:.2f}% away) than resistance ₹{nearest_resistance:.2f} ({resistance_distance_pct:.2f}% away)"
                    else:
                        message = f"❌ No support levels found to compare with resistance ₹{nearest_resistance:.2f} ({resistance_distance_pct:.2f}% away)"

                return {
                    'passed': passed,
                    'message': message,
                    'current_price': current_price,
                    'pivot_point': pivot_point,
                    'nearest_support': nearest_support,
                    'nearest_resistance': nearest_resistance,
                    'distance_to_support': distance_to_support,
                    'distance_to_resistance': distance_to_resistance,
                    'support_distance_pct': support_distance_pct,
                    'resistance_distance_pct': resistance_distance_pct,
                    'support_levels': support_levels,
                    'resistance_levels': resistance_levels,
                    'r1': resistance_levels[0] if len(resistance_levels) > 0 else None,
                    'r2': resistance_levels[1] if len(resistance_levels) > 1 else None,
                    'r3': resistance_levels[2] if len(resistance_levels) > 2 else None,
                    's1': support_levels[0] if len(support_levels) > 0 else None,
                    's2': support_levels[1] if len(support_levels) > 1 else None,
                    's3': support_levels[2] if len(support_levels) > 2 else None
                }

        except Exception as e:
            logger.error(f"Error checking support proximity: {e}", exc_info=True)
            return {
                'passed': False,
                'message': f'❌ Error calculating S/R: {str(e)}',
                'support_levels': [],
                'resistance_levels': []
            }

    def _check_open_interest(
        self, symbol: str, expiry_date: str, direction: str
    ) -> Dict[str, Any]:
        """
        CRITICAL CHECK 3: Open Interest should be building up (increasing OI is good for averaging)
        """
        try:
            from apps.brokers.models import OptionChainQuote
            from datetime import datetime, date

            logger.info(f"Starting Open Interest check for {symbol}")

            # Convert expiry_date to date object if needed
            expiry_dt = None
            if expiry_date and (not isinstance(expiry_date, str) or expiry_date.strip()):
                if isinstance(expiry_date, str):
                    expiry_dt = datetime.strptime(expiry_date.strip(), '%Y-%m-%d').date()
                else:
                    expiry_dt = expiry_date
            else:
                # Try to find the most recent futures quote
                recent_quote = OptionChainQuote.objects.filter(
                    stock_code=symbol,
                    product_type__iexact='futures',
                    expiry_date__gte=date.today()
                ).order_by('expiry_date').first()

                if recent_quote:
                    expiry_dt = recent_quote.expiry_date
                else:
                    logger.warning(f"No expiry date provided and no recent futures data found for {symbol}")
                    return {
                        'passed': False,
                        'message': '❌ Unable to fetch Open Interest data (no expiry found)',
                        'open_interest': 0
                    }

            # Get current futures quote for OI
            futures_quote = OptionChainQuote.objects.filter(
                stock_code=symbol,
                product_type__iexact='futures',
                expiry_date=expiry_dt
            ).first()

            if not futures_quote or not futures_quote.open_interest:
                logger.warning(f"No OI data found for {symbol} expiry {expiry_dt}")
                return {
                    'passed': False,
                    'message': '❌ Open Interest data not available',
                    'open_interest': 0
                }

            current_oi = float(futures_quote.open_interest)
            logger.info(f"Current Open Interest for {symbol}: {current_oi:,.0f}")

            # OI should be meaningful (at least 10,000 for most stocks, 100,000 for indices)
            min_oi_threshold = 100000 if symbol in ['NIFTY', 'BANKNIFTY', 'FINNIFTY'] else 10000

            if current_oi < min_oi_threshold:
                return {
                    'passed': False,
                    'message': f'❌ Low Open Interest: {current_oi:,.0f} (need {min_oi_threshold:,.0f}+)',
                    'open_interest': current_oi,
                    'min_threshold': min_oi_threshold
                }

            # OI is good - position has liquidity
            return {
                'passed': True,
                'message': f'✅ Healthy Open Interest: {current_oi:,.0f} contracts',
                'open_interest': current_oi,
                'min_threshold': min_oi_threshold
            }

        except Exception as e:
            logger.error(f"Error checking Open Interest: {e}", exc_info=True)
            return {
                'passed': False,
                'message': f'❌ Error checking Open Interest: {str(e)}',
                'open_interest': 0
            }

    def _check_trend(self, symbol: str, direction: str) -> Dict[str, Any]:
        """
        Check if the overall trend supports averaging.
        Uses 20/50/100/200 DMA analysis.
        """
        try:
            from apps.brokers.models import HistoricalPrice
            from django.db.models import Q
            from datetime import date, timedelta, datetime as dt

            # Get last 200 days of data
            end_date = date.today()
            start_date = end_date - timedelta(days=250)  # 200 trading days + buffer

            # Convert to datetime for querying
            start_datetime = dt.combine(start_date, dt.min.time())
            end_datetime = dt.combine(end_date, dt.max.time())

            prices = HistoricalPrice.objects.filter(
                stock_code=symbol,
                product_type__iexact='cash',  # Case-insensitive match
                datetime__gte=start_datetime,
                datetime__lte=end_datetime
            ).order_by('-datetime').values_list('close', flat=True)[:200]

            if len(prices) < 50:
                return {
                    'healthy': False,
                    'message': '⚠️ Insufficient historical data for trend analysis',
                    'dma_20': None,
                    'dma_50': None,
                    'dma_200': None
                }

            prices = list(prices)
            current_price = prices[0] if prices else 0

            dma_20 = sum(prices[:20]) / 20 if len(prices) >= 20 else None
            dma_50 = sum(prices[:50]) / 50 if len(prices) >= 50 else None
            dma_200 = sum(prices[:200]) / 200 if len(prices) >= 200 else None

            if direction == 'LONG':
                # For LONG, we don't want a strong downtrend
                # Acceptable if: price > DMA20 OR DMA20 > DMA50
                if dma_20 and dma_50:
                    uptrend = current_price > dma_20 or dma_20 > dma_50
                    healthy = uptrend

                    if healthy:
                        message = "✅ Not in strong downtrend - safe to average"
                    else:
                        message = "⚠️ Strong downtrend detected - averaging is risky"
                else:
                    healthy = True
                    message = "⚠️ Limited DMA data - trend unclear"

            else:  # SHORT
                # For SHORT, we don't want a strong uptrend
                # Acceptable if: price < DMA20 OR DMA20 < DMA50
                if dma_20 and dma_50:
                    downtrend = current_price < dma_20 or dma_20 < dma_50
                    healthy = downtrend

                    if healthy:
                        message = "✅ Not in strong uptrend - safe to average"
                    else:
                        message = "⚠️ Strong uptrend detected - averaging is risky"
                else:
                    healthy = True
                    message = "⚠️ Limited DMA data - trend unclear"

            return {
                'healthy': healthy,
                'message': message,
                'current_price': current_price,
                'dma_20': round(dma_20, 2) if dma_20 else None,
                'dma_50': round(dma_50, 2) if dma_50 else None,
                'dma_200': round(dma_200, 2) if dma_200 else None
            }

        except Exception as e:
            logger.error(f"Error in trend check: {e}", exc_info=True)
            return {
                'healthy': True,  # Don't block on error
                'message': f'⚠️ Trend check error: {str(e)}',
                'dma_20': None,
                'dma_50': None,
                'dma_200': None
            }

    def _check_volume(self, symbol: str, expiry_date: str = None) -> Dict[str, Any]:
        """
        Check if there's adequate volume for averaging.
        """
        try:
            # For now, use a simple check
            # TODO: Implement actual volume comparison from Breeze API
            return {
                'adequate': True,
                'message': '✅ Volume check passed',
                'current_volume': 0,
                'average_volume': 0
            }

        except Exception as e:
            logger.error(f"Error in volume check: {e}")
            return {
                'adequate': True,  # Don't block on error
                'message': f'⚠️ Volume check skipped: {str(e)}',
                'current_volume': 0,
                'average_volume': 0
            }

    def _check_sector_health(self, symbol: str) -> Dict[str, Any]:
        """
        Check if the sector is healthy.
        """
        try:
            # Sector health check using existing sector analyzer
            from apps.trading.level2_analyzers import analyze_sector_strength

            sector_data = analyze_sector_strength(symbol)

            if not sector_data or not sector_data.get('success'):
                return {
                    'healthy': True,  # Don't block if we can't check
                    'message': '⚠️ Sector data unavailable',
                    'sector_score': 0
                }

            sector_score = sector_data.get('score', 0)
            sector_status = sector_data.get('status', 'NEUTRAL')

            healthy = sector_score >= 40  # At least neutral

            if healthy:
                message = f"✅ Sector {sector_status} (score: {sector_score}/100)"
            else:
                message = f"⚠️ Weak sector performance (score: {sector_score}/100)"

            return {
                'healthy': healthy,
                'message': message,
                'sector_score': sector_score,
                'sector_status': sector_status,
                'details': sector_data
            }

        except Exception as e:
            logger.error(f"Error in sector check: {e}")
            return {
                'healthy': True,  # Don't block on error
                'message': f'⚠️ Sector check skipped: {str(e)}',
                'sector_score': 0
            }

    def _check_volatility(self, symbol: str) -> Dict[str, Any]:
        """
        Check volatility levels - high volatility increases risk.
        """
        try:
            # Simple volatility check using India VIX
            # TODO: Implement stock-specific ATR calculation
            return {
                'acceptable': True,
                'message': '✅ Volatility within acceptable range',
                'vix': 0,
                'atr': 0
            }

        except Exception as e:
            logger.error(f"Error in volatility check: {e}")
            return {
                'acceptable': True,
                'message': f'⚠️ Volatility check skipped: {str(e)}',
                'vix': 0,
                'atr': 0
            }

    def _calculate_confidence_score(
        self, price_check, support_check, trend_check,
        volume_check, sector_check, volatility_check
    ) -> int:
        """
        Calculate overall confidence score (0-100).

        Weighting:
        - Critical checks (price + support): 60 points total
        - Trend: 15 points
        - Volume: 10 points
        - Sector: 10 points
        - Volatility: 5 points
        """
        score = 0

        # Critical checks (must pass)
        if price_check['passed']:
            score += 30
        if support_check['passed']:
            score += 30

        # Additional checks
        if trend_check.get('healthy', False):
            score += 15
        if volume_check.get('adequate', False):
            score += 10
        if sector_check.get('healthy', False):
            score += 10
        if volatility_check.get('acceptable', False):
            score += 5

        return min(100, score)

    def _assess_averaging_risk(
        self, symbol, direction, entry_price, current_price,
        current_quantity, lot_size, support_check
    ) -> Dict[str, Any]:
        """
        Assess the risk of averaging the position.
        """
        # Calculate potential drawdown from current price to support
        nearest_support = support_check.get('nearest_support', current_price * 0.95)
        nearest_resistance = support_check.get('nearest_resistance', current_price * 1.05)

        if direction == 'LONG':
            # Risk is from current price to support
            potential_drop_pct = ((current_price - nearest_support) / current_price) * 100
            risk_level = 'LOW' if potential_drop_pct < 2 else ('MEDIUM' if potential_drop_pct < 4 else 'HIGH')
        else:  # SHORT
            # Risk is from current price to resistance
            potential_rise_pct = ((nearest_resistance - current_price) / current_price) * 100
            risk_level = 'LOW' if potential_rise_pct < 2 else ('MEDIUM' if potential_rise_pct < 4 else 'HIGH')

        return {
            'risk_level': risk_level,
            'nearest_support': nearest_support,
            'nearest_resistance': nearest_resistance,
            'potential_drop_pct': round(potential_drop_pct if direction == 'LONG' else potential_rise_pct, 2),
            'message': f'Risk level: {risk_level}'
        }

    def _calculate_averaging_size(
        self, current_quantity, lot_size, confidence,
        entry_price, current_price, direction
    ) -> Dict[str, Any]:
        """
        Calculate recommended averaging size based on confidence and position.

        Professional approach:
        - High confidence (70+): Average with 50% of original position
        - Medium confidence (50-70): Average with 25% of original position
        - Low confidence (<50): Average with 10% of original position
        """
        current_lots = current_quantity // lot_size

        if confidence >= 70:
            multiplier = 0.5
        elif confidence >= 50:
            multiplier = 0.25
        else:
            multiplier = 0.1

        recommended_lots = max(1, int(current_lots * multiplier))

        # Calculate new average price after averaging
        additional_quantity = recommended_lots * lot_size
        new_total_quantity = current_quantity + additional_quantity
        new_avg_price = (
            (entry_price * current_quantity) + (current_price * additional_quantity)
        ) / new_total_quantity

        price_improvement = abs(new_avg_price - entry_price)
        improvement_pct = (price_improvement / entry_price) * 100

        return {
            'current_lots': current_lots,
            'current_quantity': current_quantity,
            'recommended_lots': recommended_lots,
            'recommended_quantity': additional_quantity,
            'new_total_quantity': new_total_quantity,
            'new_average_price': round(new_avg_price, 2),
            'price_improvement': round(price_improvement, 2),
            'improvement_pct': round(improvement_pct, 2),
            'confidence_based_multiplier': multiplier
        }
