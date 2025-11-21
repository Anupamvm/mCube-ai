"""
Trading Algorithm Views - Futures and Options Strategy Execution

This module contains views for triggering automated trading algorithms:
- Futures screening algorithm with volume filtering
- Nifty options strangle strategy with delta-based strike selection

Both algorithms integrate with Breeze API for real-time market data and margin calculations.
"""

import logging
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse

logger = logging.getLogger(__name__)


@login_required
@require_POST
def trigger_futures_algorithm(request):
    """
    Manually trigger the futures screening algorithm with volume filtering.

    Analyzes futures contracts based on volume criteria:
    - This month contracts: volume >= threshold (default 1000)
    - Next month contracts: volume >= threshold (default 800)

    For each contract that passes volume filter:
    1. Runs comprehensive 9-step technical analysis
    2. Calculates composite score from multiple factors
    3. Determines trading direction (LONG/SHORT/NEUTRAL)
    4. Fetches real margin requirements from Breeze API
    5. Calculates position sizing with 50% margin rule
    6. Saves trade suggestions to database

    Request Body (JSON):
        {
            "this_month_volume": 1000,  # Volume threshold for current month contracts
            "next_month_volume": 800,   # Volume threshold for next month contracts
            "confirmed": false          # User confirmation if >15 contracts found
        }

    Returns:
        JsonResponse: {
            'success': bool,
            'all_contracts': [...],     # All analyzed contracts sorted by score
            'total_analyzed': int,
            'total_passed': int,
            'total_failed': int,
            'total_errors': int,
            'execution_summary': [...],
            'volume_filters': {...},
            'suggestion_ids': [...]     # IDs of saved TradeSuggestion records
        }

    Error Responses:
        - 400: Invalid request body or no contracts match criteria
        - 401: Breeze authentication required
        - 500: Internal server error during analysis

    Side Effects:
        - Creates TradeSuggestion records for PASS contracts
        - Fetches real-time margin data from Breeze API
        - Logs analysis results for each contract

    Notes:
        - Uses 50% margin rule: recommended position = 50% of available margin
        - Remaining 50% reserved for averaging (2 additional positions)
        - Applies stop loss (2%) and target (4%) based on direction
        - Breeze API required for margin and futures price data
    """
    import json
    from apps.trading.futures_analyzer import comprehensive_futures_analysis
    from apps.data.models import ContractData
    from django.db.models import Q
    from datetime import datetime, timedelta

    try:
        # Parse volume thresholds from request
        body = json.loads(request.body)
        this_month_volume = int(body.get('this_month_volume', 1000))
        next_month_volume = int(body.get('next_month_volume', 800))
        confirmed = body.get('confirmed', False)

        logger.info(f"Manual trigger: Futures algorithm with volume filters (this_month≥{this_month_volume}, next_month≥{next_month_volume})")

        # Get filtered contracts based on volume criteria
        today = datetime.now().date()
        this_month_end = today + timedelta(days=30)
        next_month_start = today + timedelta(days=30)
        next_month_end = today + timedelta(days=60)

        futures_contracts = ContractData.objects.filter(
            option_type='FUTURE',
            expiry__gte=str(today),
            expiry__lte=str(next_month_end)
        ).filter(
            Q(expiry__lte=str(this_month_end), traded_contracts__gte=this_month_volume) |
            Q(expiry__gte=str(next_month_start), expiry__lte=str(next_month_end), traded_contracts__gte=next_month_volume)
        ).order_by('-traded_contracts')  # Order by volume descending

        contract_count = futures_contracts.count()

        if contract_count == 0:
            return JsonResponse({
                'success': False,
                'error': f'No futures contracts found matching volume criteria (this_month≥{this_month_volume}, next_month≥{next_month_volume})'
            })

        logger.info(f"Found {contract_count} contracts matching volume criteria")

        # If more than 15 contracts and not yet confirmed, ask for user confirmation
        if contract_count > 15 and not confirmed:
            return JsonResponse({
                'success': False,
                'requires_confirmation': True,
                'contract_count': contract_count,
                'message': f'Found {contract_count} contracts to analyze. This may take a while (estimated {contract_count * 3} seconds). Do you want to proceed?'
            })

        # Run comprehensive analysis on all contracts (no limit)
        analyzed_results = []
        execution_summary = []

        for contract in futures_contracts:  # Analyze ALL contracts
            try:
                logger.info(f"Analyzing {contract.symbol} (expiry: {contract.expiry})")

                analysis_result = comprehensive_futures_analysis(
                    stock_symbol=contract.symbol,
                    expiry_date=contract.expiry,
                    contract=contract
                )

                # Extract metrics regardless of pass/fail
                metrics = analysis_result.get('metrics', {})
                composite_score = analysis_result.get('composite_score', 0)
                direction = analysis_result.get('direction', 'NEUTRAL')
                verdict = analysis_result.get('verdict', 'FAIL')
                success = analysis_result.get('success', False)

                # Format expiry
                expiry_dt = datetime.strptime(contract.expiry, '%Y-%m-%d')
                expiry_formatted = expiry_dt.strftime('%d-%b-%Y')

                # Build explanation using execution log
                explanation_parts = []
                execution_log = analysis_result.get('execution_log', [])

                # Extract key analysis points (both pass and fail)
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

                # Add to results regardless of pass/fail
                analyzed_results.append({
                    'symbol': contract.symbol,
                    'expiry': expiry_formatted,
                    'expiry_date': contract.expiry,
                    'composite_score': composite_score,
                    'direction': direction,
                    'verdict': verdict,
                    'success': success,
                    'spot_price': metrics.get('spot_price', 0),
                    'futures_price': metrics.get('futures_price', 0),
                    'basis': metrics.get('basis', 0),
                    'basis_pct': metrics.get('basis_pct', 0),
                    'volume': contract.traded_contracts,
                    'lot_size': contract.lot_size,
                    'explanation': explanation_parts,
                    'execution_log': execution_log,
                    'metrics': metrics,
                    'scores': analysis_result.get('scores', {}),
                    'sr_data': metrics.get('sr_details', None),  # Support/Resistance data
                    'breach_risks': analysis_result.get('breach_risks', None),  # Breach risk calculations
                    'error': analysis_result.get('error', None) if not success else None
                })

                execution_summary.append({
                    'symbol': contract.symbol,
                    'status': verdict,
                    'score': composite_score,
                    'success': success
                })

            except Exception as e:
                logger.error(f"Error analyzing {contract.symbol}: {e}")

                # Add failed contract to results
                try:
                    expiry_dt = datetime.strptime(contract.expiry, '%Y-%m-%d')
                    expiry_formatted = expiry_dt.strftime('%d-%b-%Y')
                except:
                    expiry_formatted = contract.expiry

                analyzed_results.append({
                    'symbol': contract.symbol,
                    'expiry': expiry_formatted,
                    'expiry_date': contract.expiry,
                    'composite_score': 0,
                    'direction': 'NEUTRAL',
                    'verdict': 'ERROR',
                    'success': False,
                    'spot_price': 0,
                    'futures_price': 0,
                    'basis': 0,
                    'basis_pct': 0,
                    'volume': contract.traded_contracts,
                    'lot_size': contract.lot_size,
                    'explanation': [f"Analysis failed: {str(e)[:200]}"],
                    'execution_log': [],
                    'metrics': {},
                    'scores': {},
                    'error': str(e)
                })

                execution_summary.append({
                    'symbol': contract.symbol,
                    'status': 'ERROR',
                    'error': str(e),
                    'score': 0,
                    'success': False
                })
                continue

        # Sort by verdict priority (PASS first, then FAIL, then ERROR) and then by score
        def sort_key(contract):
            verdict = contract['verdict']
            score = contract['composite_score']

            # Priority: PASS=0, FAIL=1, ERROR=2 (lower is better)
            priority = 0 if verdict == 'PASS' else (1 if verdict == 'FAIL' else 2)

            # Return tuple: (priority, negative_score) so PASS comes first, then sorted by score descending
            return (priority, -score)

        analyzed_results.sort(key=sort_key)

        # Count passed contracts
        passed_results = [r for r in analyzed_results if r['verdict'] == 'PASS']

        if not analyzed_results:
            return JsonResponse({
                'success': False,
                'error': 'No contracts could be analyzed',
                'execution_summary': execution_summary,
                'total_analyzed': 0
            })

        logger.info(f"Analysis complete: {len(analyzed_results)} contracts analyzed, {len(passed_results)} passed")

        # Save trade suggestions for top 3 PASS results with real Breeze margin
        suggestion_ids = []
        if passed_results:
            from apps.trading.models import TradeSuggestion
            from django.utils import timezone
            from apps.trading.position_sizer import PositionSizer
            from apps.brokers.integrations.breeze import get_breeze_client
            from apps.data.models import ContractData
            import json
            from datetime import date, datetime, timedelta
            from decimal import Decimal

            # Helper to serialize dates and decimals for JSON
            def json_serial(obj):
                if isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                if isinstance(obj, Decimal):
                    return float(obj)
                raise TypeError(f"Type {type(obj)} not serializable")

            # Initialize Breeze client for margin fetching
            try:
                breeze = get_breeze_client()
            except Exception as e:
                logger.warning(f"Could not initialize Breeze client for position sizing: {e}")
                breeze = None

            # Fetch available F&O margin from Breeze API (same logic as verify_future_trade)
            available_margin = 5000000  # Default 50 lakh
            if breeze:
                try:
                    margin_response = breeze.get_margin(exchange_code="NFO")
                    if margin_response and margin_response.get('Status') == 200:
                        margin_data = margin_response.get('Success', {})
                        cash_limit = float(margin_data.get('cash_limit', 0))
                        block_by_trade = float(margin_data.get('block_by_trade', 0))
                        available_margin = cash_limit - block_by_trade
                        logger.info(f"Available F&O margin from Breeze: ₹{available_margin:,.0f}")
                    else:
                        logger.warning("Could not fetch F&O margin, using default: ₹50,00,000")
                except Exception as e:
                    logger.warning(f"Error fetching F&O margin: {e}, using default")
            else:
                logger.warning("Breeze client not available, using default margin: ₹50,00,000")

            # Save ALL PASS results with real position sizing (not just top 3)
            # This allows the collapsible UI to work for all passed contracts
            for result in passed_results:
                try:
                    symbol = result['symbol']
                    expiry_date_str = result['expiry_date']
                    direction = result['direction']
                    futures_price = Decimal(str(result['futures_price']))
                    spot_price = Decimal(str(result['spot_price']))
                    composite_score = result['composite_score']

                    # Get contract details
                    contract = ContractData.objects.filter(
                        symbol=symbol,
                        option_type='FUTURE',
                        expiry=expiry_date_str
                    ).first()

                    if not contract:
                        continue

                    lot_size = contract.lot_size
                    expiry_dt = datetime.strptime(expiry_date_str, '%Y-%m-%d')

                    # Format expiry for Breeze API
                    expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()

                    # Calculate position sizing using same logic as verify_future_trade
                    # Step 1: Get margin per lot from Breeze API
                    margin_per_lot = 0
                    if breeze:
                        try:
                            # Estimate quantity for margin call (1 lot)
                            quantity = lot_size
                            action = 'buy' if direction == 'LONG' else 'sell'

                            margin_resp = breeze.get_margin(
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

                            if margin_resp and margin_resp.get('Status') == 200:
                                margin_data_resp = margin_resp.get('Success', {})
                                margin_per_lot = float(margin_data_resp.get('total', 0))
                                logger.info(f"Breeze margin for {symbol}: ₹{margin_per_lot:,.0f} per lot")
                            else:
                                # Fallback: Estimate 17% of contract value
                                margin_per_lot = float(futures_price * lot_size) * 0.17
                                logger.warning(f"Margin API failed for {symbol}, estimating: ₹{margin_per_lot:,.0f}")
                        except Exception as e:
                            logger.warning(f"Error fetching margin for {symbol}: {e}")
                            margin_per_lot = float(futures_price * lot_size) * 0.17
                    else:
                        # Fallback: Estimate 17% of contract value
                        margin_per_lot = float(futures_price * lot_size) * 0.17

                    # Step 2: Apply 50% rule for initial position
                    # Initial position should use 50% of available margin
                    # Remaining 50% is reserved for averaging (2 more positions)
                    safe_margin = available_margin * 0.5

                    # Step 3: Calculate recommended lots to use 50% margin
                    recommended_lots = max(1, int(safe_margin / margin_per_lot)) if margin_per_lot > 0 else 1

                    # Step 4: Calculate max lots possible with full available margin (for slider limit)
                    max_lots_possible = int(available_margin / margin_per_lot) if margin_per_lot > 0 else 1

                    # Step 5: Calculate position metrics
                    margin_required = Decimal(str(margin_per_lot * recommended_lots))
                    margin_per_lot_decimal = Decimal(str(margin_per_lot))
                    margin_available_decimal = Decimal(str(available_margin))

                    # Calculate margin utilization
                    margin_utilization = 0
                    if available_margin > 0:
                        margin_utilization = (margin_required / margin_available_decimal) * 100

                    logger.info(f"Position sizing for {symbol}: {recommended_lots} lots (50% of ₹{available_margin:,.0f} = ₹{margin_required:,.0f}, {margin_utilization:.1f}% used)")

                    # Build position sizing data for saving
                    position_sizing_data = {
                        'position': {
                            'recommended_lots': recommended_lots,
                            'total_margin_required': float(margin_required),
                            'entry_value': float(futures_price * lot_size * recommended_lots),
                            'margin_utilization_percent': float(margin_utilization)
                        },
                        'margin_data': {
                            'available_margin': available_margin,
                            'used_margin': float(margin_required),
                            'total_margin': available_margin,
                            'margin_per_lot': margin_per_lot,
                            'max_lots_possible': max_lots_possible,
                            'futures_price': float(futures_price),
                            'source': 'Breeze API' if breeze else 'Estimated'
                        },
                        'stop_loss': 0,  # Will be calculated below
                        'target': 0,  # Will be calculated below
                        'direction': direction
                    }

                    # Calculate stop loss and target
                    if direction == 'LONG':
                        stop_loss_price = futures_price * Decimal('0.98')
                        target_price = futures_price * Decimal('1.04')
                    elif direction == 'SHORT':
                        stop_loss_price = futures_price * Decimal('1.02')
                        target_price = futures_price * Decimal('0.96')
                    else:
                        stop_loss_price = futures_price * Decimal('0.98')
                        target_price = futures_price * Decimal('1.02')

                    # Update position_sizing_data with stop loss and target
                    position_sizing_data['stop_loss'] = float(stop_loss_price)
                    position_sizing_data['target'] = float(target_price)

                    # Calculate max profit and loss
                    max_loss_value = abs(futures_price - stop_loss_price) * lot_size * recommended_lots
                    max_profit_value = abs(target_price - futures_price) * lot_size * recommended_lots

                    # Convert data to JSON-safe format
                    # Use .get() for all keys to avoid KeyError
                    algorithm_reasoning_safe = json.loads(
                        json.dumps({
                            'metrics': result.get('metrics', {}),
                            'execution_log': result.get('execution_log', []),
                            'composite_score': composite_score,
                            'scores': result.get('scores', {}),
                            'explanation': result.get('explanation', ''),
                            'sr_data': result.get('sr_data'),
                            'breach_risks': result.get('breach_risks')
                        }, default=json_serial)
                    )

                    logger.info(f"About to create suggestion for {symbol}: lots={recommended_lots}, margin={margin_required}, score={composite_score}")

                    suggestion = TradeSuggestion.objects.create(
                        user=request.user,
                        strategy='icici_futures',
                        suggestion_type='FUTURES',
                        instrument=symbol,
                        direction=direction.upper(),
                        # Market Data
                        spot_price=spot_price,
                        expiry_date=expiry_dt.date(),
                        days_to_expiry=(expiry_dt.date() - datetime.now().date()).days,
                        # Position Sizing (with real Breeze margin - 50% rule)
                        recommended_lots=recommended_lots,
                        margin_required=margin_required,
                        margin_available=margin_available_decimal,
                        margin_per_lot=margin_per_lot_decimal,
                        margin_utilization=Decimal(str(margin_utilization)),
                        # Risk Metrics
                        max_profit=max_profit_value,
                        max_loss=max_loss_value,
                        breakeven_upper=target_price if direction == 'LONG' else None,
                        breakeven_lower=stop_loss_price if direction == 'LONG' else None,
                        # Complete Data (includes real position sizing with 50% rule)
                        algorithm_reasoning=algorithm_reasoning_safe,
                        position_details=json.loads(json.dumps(position_sizing_data, default=json_serial)),
                        # Expiry: 24 hours from now
                        expires_at=timezone.now() + timedelta(hours=24)
                    )

                    suggestion_ids.append(suggestion.id)
                    logger.info(f"Saved futures suggestion #{suggestion.id} for {symbol}")

                except Exception as e:
                    logger.error(f"Error saving suggestion for {result.get('symbol')}: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    suggestion_ids.append(None)  # Append None to keep indices aligned
                    continue

        # Prepare response - return ALL analyzed results
        response_data = {
            'success': True,
            'all_contracts': analyzed_results,  # All contracts sorted by score
            'total_analyzed': len(analyzed_results),
            'total_passed': len(passed_results),
            'total_failed': len([r for r in analyzed_results if r['verdict'] == 'FAIL']),
            'total_errors': len([r for r in analyzed_results if r['verdict'] == 'ERROR']),
            'execution_summary': execution_summary,
            'volume_filters': {
                'this_month': this_month_volume,
                'next_month': next_month_volume
            },
            'suggestion_ids': suggestion_ids  # IDs of saved suggestions
        }

        return JsonResponse(response_data)

    except Exception as e:
        from apps.brokers.exceptions import BreezeAuthenticationError

        # Check if it's an authentication error
        if isinstance(e, BreezeAuthenticationError):
            logger.warning(f"Breeze authentication failed: {e}")
            return JsonResponse({
                'success': False,
                'auth_required': True,
                'error': str(e),
                'message': 'Breeze session expired. Please re-login to continue.'
            })

        logger.error(f"Error in trigger_futures_algorithm: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def trigger_nifty_strangle(request):
    """
    Manually trigger Nifty options strangle strategy with real Breeze option chain data.

    Implements a sophisticated delta-based strike selection algorithm:
    1. Fetches fresh NIFTY option chain from Breeze API
    2. Gets current Nifty price and India VIX
    3. Selects optimal expiry (weekly/monthly based on days remaining)
    4. Validates market conditions (NO TRADE DAY checks)
    5. Runs technical analysis (Support/Resistance, Moving Averages)
    6. Calculates strikes using smart delta algorithm
    7. Adjusts strikes to avoid psychological levels (50, 100, 250, 500, 1000)
    8. Checks Support/Resistance proximity and adjusts if needed
    9. Fetches real option premiums from database
    10. Calculates position sizing with margin and risk metrics

    The algorithm uses asymmetric strike selection based on:
    - Market volatility (VIX levels)
    - Technical indicators (S/R position, MA crossovers)
    - Put-Call Ratio (PCR)
    - Open Interest distribution

    Request Body: None required (POST only)

    Returns:
        JsonResponse: {
            'success': bool,
            'strangle': {
                'strategy': 'Short Strangle (Delta-Based)',
                'underlying': 'NIFTY',
                'current_price': float,
                'expiry_date': 'YYYY-MM-DD',
                'days_to_expiry': int,
                'vix': float,
                'call_strike': int,
                'put_strike': int,
                'call_premium': float,
                'put_premium': float,
                'total_premium': float,
                'margin_required': float,
                'max_profit': float,
                'breakeven_upper': float,
                'breakeven_lower': float,
                'position_sizing': {...},
                'reasoning': {...},
                'execution_log': [...],
                'delta_details': {...},
                'validation_report': {...},
                'breach_risks': {...},
                'sr_levels': {...},
                'suggestion_id': int
            }
        }

    Error Responses:
        - 400: Market conditions invalid (NO TRADE DAY)
        - 401: Breeze authentication required
        - 404: No active Kotak account found
        - 500: Internal server error

    NO TRADE DAY Conditions (trade blocked):
        - VIX > 25 (high volatility)
        - VIX < 10 (too low volatility)
        - Expiry within 2 days
        - Nifty near 52-week high/low
        - Recent large moves (>2% in one day)

    Psychological Level Adjustment:
        Strikes are adjusted away from round numbers to avoid high gamma risk:
        - 50s: 24650 → 24625 or 24675
        - 100s: 24700 → 24675 or 24725
        - 250s: 24750 → 24725 or 24775
        - 500s: 24500 → 24475 or 24525
        - 1000s: 25000 → 24975 or 25025

    Support/Resistance Adjustment:
        Strikes within 100 points of S/R levels are moved to safer zones:
        - Call near resistance → move further OTM
        - Put near support → move further OTM

    Position Sizing:
        - Uses real margin from Kotak Neo API
        - Implements 3-stage averaging plan
        - Initial position: 33% of margin
        - Stage 2: 33% if breach occurs
        - Stage 3: 34% final defense

    Side Effects:
        - Creates TradeSuggestion record with complete strategy details
        - Fetches and saves option chain data to database
        - Logs detailed execution steps for debugging

    Notes:
        - Requires active Kotak broker account
        - Breeze API used for option chain and VIX data
        - Neo API used for margin calculations
        - Strategy is market-neutral (sells both call and put)
        - Exit target: 50% profit or expiry, whichever comes first
    """
    try:
        from apps.brokers.integrations.breeze import (
            fetch_and_save_nifty_option_chain_all_expiries,
            get_nifty_quote,
            get_india_vix
        )
        from apps.core.services.expiry_selector import select_expiry_for_options
        from apps.accounts.models import BrokerAccount
        from apps.data.models import OptionChain
        from apps.strategies.services.strangle_delta_algorithm import StrangleDeltaAlgorithm
        from decimal import Decimal

        execution_log = []

        # Get Kotak account
        account = BrokerAccount.objects.filter(
            broker='KOTAK',
            is_active=True
        ).first()

        if not account:
            return JsonResponse({
                'success': False,
                'error': 'No active Kotak broker account found'
            })

        logger.info("Manual trigger: Nifty strangle strategy with real Breeze data")

        # STEP 1: Fetch fresh option chain data from Breeze
        try:
            logger.info("Fetching fresh NIFTY option chain from Breeze...")
            total_saved = fetch_and_save_nifty_option_chain_all_expiries()
            execution_log.append({
                'step': 1,
                'action': 'Option Chain Data Fetch',
                'status': 'success',
                'message': f'Fetched {total_saved} option records from Breeze API'
            })
        except Exception as e:
            logger.warning(f"Could not fetch fresh option chain: {e}")
            execution_log.append({
                'step': 1,
                'action': 'Option Chain Data Fetch',
                'status': 'warning',
                'message': f'Using cached data (fetch failed: {str(e)[:100]})'
            })

        # STEP 2: Get current Nifty price and VIX from Breeze
        try:
            nifty_quote = get_nifty_quote()
            nifty_price = Decimal(str(nifty_quote.get('ltp', 0)))
            execution_log.append({
                'step': 2,
                'action': 'Nifty Spot Price',
                'status': 'success',
                'message': f'₹{nifty_price:,.2f}'
            })
        except Exception as e:
            from apps.brokers.exceptions import BreezeAuthenticationError
            logger.error(f"Failed to get Nifty price: {e}")

            # Check if authentication error
            if isinstance(e, BreezeAuthenticationError) or 'Session key is expired' in str(e):
                return JsonResponse({
                    'success': False,
                    'auth_required': True,
                    'error': 'Breeze session expired. Please re-authenticate.',
                    'execution_log': execution_log
                })

            return JsonResponse({
                'success': False,
                'error': f'Could not fetch Nifty price: {str(e)}',
                'execution_log': execution_log
            })

        try:
            vix = get_india_vix()
            execution_log.append({
                'step': 3,
                'action': 'India VIX',
                'status': 'success',
                'message': f'{float(vix):.2f}'
            })
        except Exception as e:
            from apps.brokers.exceptions import BreezeAuthenticationError
            from decimal import Decimal
            logger.warning(f"Failed to get VIX, using default 15.0: {e}")

            # Check if authentication error
            if isinstance(e, BreezeAuthenticationError) or 'Session key is expired' in str(e):
                return JsonResponse({
                    'success': False,
                    'auth_required': True,
                    'error': 'Breeze session expired. Please re-authenticate.',
                    'execution_log': execution_log
                })

            # Use default VIX value and continue
            vix = Decimal('15.0')
            execution_log.append({
                'step': 3,
                'action': 'India VIX',
                'status': 'warning',
                'message': f'Using default: 15.0 (API failed: {str(e)[:50]}...)'
            })

        # STEP 3: Select expiry
        try:
            expiry_date, expiry_details = select_expiry_for_options(instrument='NIFTY', min_days=1)
            days_to_expiry = expiry_details['days_remaining']
            execution_log.append({
                'step': 4,
                'action': 'Expiry Selection',
                'status': 'success',
                'message': f'{expiry_details["expiry_type"]} - {expiry_date.strftime("%d-%b-%Y")} ({days_to_expiry} days)',
                'details': expiry_details
            })
        except Exception as e:
            logger.error(f"Failed to select expiry: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Could not select expiry: {str(e)}',
                'execution_log': execution_log
            })

        # STEP 3.5: Validate market conditions (NO TRADE DAY checks)
        try:
            from apps.strategies.services.market_condition_validator import validate_market_conditions

            logger.info("Validating market conditions for strangle entry")
            validation_report = validate_market_conditions(nifty_price, vix, days_to_expiry)

            # Add validation summary to execution log
            verdict = validation_report['overall_verdict']
            verdict_status = 'success' if validation_report['trade_allowed'] else 'fail'
            if validation_report['warnings'] and validation_report['trade_allowed']:
                verdict_status = 'warning'

            execution_log.append({
                'step': 5,
                'action': 'Market Condition Validation',
                'status': verdict_status,
                'message': f'{verdict}: {validation_report["verdict_reason"]}',
                'details': {
                    'checks_passed': validation_report['status_summary']['PASS'],
                    'warnings': validation_report['status_summary']['WARNING'],
                    'checks_failed': validation_report['status_summary']['FAIL'],
                    'total_warnings': len(validation_report['warnings'])
                }
            })

            # If NO TRADE DAY, stop here and return the report with market data
            if not validation_report['trade_allowed']:
                logger.warning(f"NO TRADE DAY detected: {validation_report['verdict_reason']}")
                return JsonResponse({
                    'success': False,
                    'error': f'NO TRADE DAY: {validation_report["verdict_reason"]}',
                    'execution_log': execution_log,
                    'validation_report': validation_report,
                    'is_no_trade_day': True,
                    'strangle': {
                        'current_price': float(nifty_price),
                        'spot_price': float(nifty_price),  # Include both for compatibility
                        'vix': float(vix),
                        'expiry_date': expiry_date.strftime('%Y-%m-%d'),
                        'days_to_expiry': days_to_expiry
                    }
                })

        except Exception as e:
            logger.warning(f"Market validation failed: {e}, continuing anyway")
            execution_log.append({
                'step': 5,
                'action': 'Market Condition Validation',
                'status': 'warning',
                'message': f'Validation skipped: {str(e)[:100]}'
            })
            validation_report = None

        # STEP 4: Run technical analysis (Support/Resistance, Moving Averages)
        try:
            from apps.strategies.services.technical_analysis import analyze_technical_indicators

            logger.info(f"Running technical analysis for strike optimization")
            technical_analysis = analyze_technical_indicators(
                symbol='NIFTY',
                current_price=float(nifty_price)
            )

            ta_verdict = technical_analysis.get('technical_verdict', 'SYMMETRIC')
            ta_status = 'success' if technical_analysis.get('delta_adjustments', {}).get('is_asymmetric') else 'warning'

            execution_log.append({
                'step': 6,
                'action': 'Technical Analysis (S/R & MA)',
                'status': ta_status,
                'message': ta_verdict,
                'details': {
                    'sr_position': technical_analysis.get('sr_position', {}).get('position'),
                    'trend': technical_analysis.get('trend_analysis', {}).get('bias'),
                    'call_multiplier': technical_analysis.get('delta_adjustments', {}).get('call_multiplier'),
                    'put_multiplier': technical_analysis.get('delta_adjustments', {}).get('put_multiplier'),
                }
            })

        except Exception as e:
            logger.warning(f"Technical analysis failed: {e}, continuing with symmetric strikes")
            execution_log.append({
                'step': 6,
                'action': 'Technical Analysis (S/R & MA)',
                'status': 'warning',
                'message': f'Skipped: {str(e)[:100]}'
            })
            technical_analysis = None

        # STEP 5: Calculate strikes using smart delta algorithm with technical analysis
        try:
            logger.info(f"Calculating strikes using delta algorithm (spot={nifty_price}, days={days_to_expiry}, vix={vix})")

            # Initialize delta algorithm
            algo = StrangleDeltaAlgorithm(
                spot_price=nifty_price,
                days_to_expiry=days_to_expiry,
                vix=vix
            )

            # Calculate market conditions from option chain data
            # Get available option chain data for PCR and OI analysis
            option_data = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=expiry_date
            )

            market_conditions = {}

            # Calculate PCR from real data
            if option_data.exists():
                total_call_oi = sum(option_data.filter(option_type='CE').values_list('oi', flat=True))
                total_put_oi = sum(option_data.filter(option_type='PE').values_list('oi', flat=True))

                if total_call_oi > 0:
                    pcr = Decimal(total_put_oi) / Decimal(total_call_oi)
                    market_conditions['pcr'] = pcr
                    logger.info(f"Calculated PCR from real data: {float(pcr):.2f}")

            # Calculate adjusted strikes with technical analysis
            strike_result = algo.calculate_strikes(market_conditions, technical_analysis)

            call_strike = strike_result['call_strike']
            put_strike = strike_result['put_strike']

            strike_message = f'CE {call_strike} | PE {put_strike} (Δ={strike_result["adjusted_delta"]:.3f}%)'
            if strike_result.get('is_asymmetric'):
                strike_message += f' [ASYMMETRIC: Call ×{strike_result["call_multiplier"]:.2f}, Put ×{strike_result["put_multiplier"]:.2f}]'

            execution_log.append({
                'step': 7,
                'action': 'Delta-Based Strike Calculation',
                'status': 'success',
                'message': strike_message,
                'details': {
                    'base_delta': strike_result['base_delta'],
                    'adjusted_delta': strike_result['adjusted_delta'],
                    'strike_distance': strike_result['strike_distance'],
                    'call_distance': strike_result.get('call_distance'),
                    'put_distance': strike_result.get('put_distance'),
                    'is_asymmetric': strike_result.get('is_asymmetric'),
                    'delta_breakdown': strike_result['delta_breakdown'],
                    'calculation_log': strike_result['calculation_log']
                }
            })

        except Exception as e:
            logger.error(f"Failed to calculate strikes: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': f'Strike calculation failed: {str(e)}',
                'execution_log': execution_log
            })

        # STEP 5.5: Check for psychological levels and adjust strikes if needed
        try:
            from apps.strategies.services.psychological_levels import check_psychological_levels

            logger.info(f"Checking strikes for psychological levels (CE {call_strike}, PE {put_strike})")
            psych_analysis = check_psychological_levels(call_strike, put_strike, float(nifty_price))

            # Update strikes if adjustments were made
            if psych_analysis['any_adjustments']:
                original_call = call_strike
                original_put = put_strike
                call_strike = psych_analysis['adjusted_call']
                put_strike = psych_analysis['adjusted_put']

                psych_message = f"ADJUSTED: {', '.join(psych_analysis['adjustments_made'])}"
                psych_status = 'warning'

                logger.warning(f"Psychological level adjustments: CE {original_call}→{call_strike}, PE {original_put}→{put_strike}")
            else:
                psych_message = "Strikes clear of psychological levels - No adjustment needed"
                psych_status = 'success'

            execution_log.append({
                'step': 8,
                'action': 'Psychological Level Check',
                'status': psych_status,
                'message': psych_message,
                'details': {
                    'original_call': psych_analysis['original_call'],
                    'original_put': psych_analysis['original_put'],
                    'final_call': call_strike,
                    'final_put': put_strike,
                    'adjustments_made': psych_analysis['adjustments_made'],
                    'safety_verdict': psych_analysis['safety_verdict'],
                    'call_dangers': psych_analysis['call_analysis']['danger_analysis']['dangers'] if psych_analysis['call_analysis']['danger_analysis']['in_danger_zone'] else [],
                    'put_dangers': psych_analysis['put_analysis']['danger_analysis']['dangers'] if psych_analysis['put_analysis']['danger_analysis']['in_danger_zone'] else [],
                }
            })

        except Exception as e:
            logger.warning(f"Psychological level check failed: {e}, continuing with original strikes")
            execution_log.append({
                'step': 8,
                'action': 'Psychological Level Check',
                'status': 'warning',
                'message': f'Skipped: {str(e)[:100]}'
            })

        # STEP 8.5: Check for Support/Resistance proximity and adjust strikes if needed
        try:
            from apps.strategies.services.support_resistance_calculator import SupportResistanceCalculator

            logger.info("Calculating Support/Resistance levels from 1-year historical data")
            sr_calculator = SupportResistanceCalculator(symbol='NIFTY', lookback_days=365)

            # Ensure we have 1 year of data
            if not sr_calculator.ensure_and_load_data():
                raise ValueError("Could not load sufficient historical data for S/R calculation")

            # Calculate S/R levels
            sr_data = sr_calculator.calculate_comprehensive_sr()
            pivot_points = sr_data['pivot_points']
            moving_averages = sr_data['moving_averages']

            # Log S/R levels
            execution_log.append({
                'step': 8.5,
                'action': 'Support/Resistance Calculation',
                'status': 'success',
                'message': f"S1: {pivot_points['s1']:.0f} | S2: {pivot_points['s2']:.0f} | R1: {pivot_points['r1']:.0f} | R2: {pivot_points['r2']:.0f}",
                'details': {
                    'pivot': float(pivot_points['pivot']),
                    'resistances': {
                        'r1': float(pivot_points['r1']),
                        'r2': float(pivot_points['r2']),
                        'r3': float(pivot_points['r3'])
                    },
                    'supports': {
                        's1': float(pivot_points['s1']),
                        's2': float(pivot_points['s2']),
                        's3': float(pivot_points['s3'])
                    },
                    'moving_averages': {
                        'dma_20': float(moving_averages['dma_20']) if moving_averages.get('dma_20') else None,
                        'dma_50': float(moving_averages['dma_50']) if moving_averages.get('dma_50') else None,
                        'dma_100': float(moving_averages['dma_100']) if moving_averages.get('dma_100') else None,
                    }
                }
            })

            # Check if strikes are within 100 points of S/R levels
            original_call_before_sr = call_strike
            original_put_before_sr = put_strike

            call_proximity = sr_calculator.check_strike_proximity_to_sr(
                strike=call_strike,
                option_type='CALL',
                sr_data=sr_data
            )

            put_proximity = sr_calculator.check_strike_proximity_to_sr(
                strike=put_strike,
                option_type='PUT',
                sr_data=sr_data
            )

            adjustments_made = []

            # Adjust CALL if near resistance
            if call_proximity['needs_adjustment']:
                call_strike = call_proximity['recommended_strike']
                adjustments_made.append(
                    f"CE {original_call_before_sr}→{call_strike} (near {call_proximity['proximity_reason']})"
                )
                logger.warning(f"S/R Adjustment: CE {original_call_before_sr}→{call_strike} ({call_proximity['proximity_reason']})")

            # Adjust PUT if near support
            if put_proximity['needs_adjustment']:
                put_strike = put_proximity['recommended_strike']
                adjustments_made.append(
                    f"PE {original_put_before_sr}→{put_strike} (near {put_proximity['proximity_reason']})"
                )
                logger.warning(f"S/R Adjustment: PE {original_put_before_sr}→{put_strike} ({put_proximity['proximity_reason']})")

            # Log S/R proximity check results
            if adjustments_made:
                sr_message = f"ADJUSTED: {', '.join(adjustments_made)}"
                sr_status = 'warning'
            else:
                sr_message = "Strikes clear of S/R levels - No adjustment needed"
                sr_status = 'success'

            execution_log.append({
                'step': 8.6,
                'action': 'S/R Proximity Check',
                'status': sr_status,
                'message': sr_message,
                'details': {
                    'original_call': original_call_before_sr,
                    'original_put': original_put_before_sr,
                    'final_call': call_strike,
                    'final_put': put_strike,
                    'call_proximity': call_proximity,
                    'put_proximity': put_proximity
                }
            })

        except Exception as e:
            logger.warning(f"S/R proximity check failed: {e}, continuing with current strikes")
            execution_log.append({
                'step': 8.5,
                'action': 'Support/Resistance Check',
                'status': 'warning',
                'message': f'Skipped: {str(e)[:150]}'
            })
            sr_data = None

        # STEP 9: Get real option premiums from database
        # Find nearest available strikes since calculated strikes might not exist
        # IMPORTANT: Use the psychologically-adjusted strikes (call_strike, put_strike are already adjusted at this point)
        try:
            from django.db.models import F, Func
            from django.db.models.functions import Abs

            # Get all available call strikes for this expiry
            available_call_strikes = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=expiry_date,
                option_type='CE',
                ltp__gt=0  # Only strikes with valid prices
            ).values_list('strike', flat=True)

            # Get all available put strikes for this expiry
            available_put_strikes = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=expiry_date,
                option_type='PE',
                ltp__gt=0  # Only strikes with valid prices
            ).values_list('strike', flat=True)

            if not available_call_strikes or not available_put_strikes:
                raise ValueError(f"No option data available for expiry {expiry_date}")

            # IMPORTANT: Check if psychologically-adjusted strikes exist in database
            # We should NOT compromise on psychological safety by using non-adjusted strikes
            logger.info(f"Psychologically-adjusted strikes: CE {call_strike}, PE {put_strike}")

            # Check if adjusted call strike exists
            call_option = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=expiry_date,
                strike=call_strike,
                option_type='CE',
                ltp__gt=0
            ).first()

            if not call_option:
                # Adjusted strike doesn't exist - find nearest
                logger.warning(f"Adjusted CE {call_strike} not found in database, finding nearest...")
                call_strike_actual = min(available_call_strikes, key=lambda x: abs(float(x) - call_strike))
                call_option = OptionChain.objects.filter(
                    underlying='NIFTY',
                    expiry_date=expiry_date,
                    strike=call_strike_actual,
                    option_type='CE'
                ).first()
                call_strike = int(call_strike_actual)
                logger.warning(f"Using nearest available CE {call_strike}")

            # Check if adjusted put strike exists
            put_option = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=expiry_date,
                strike=put_strike,
                option_type='PE',
                ltp__gt=0
            ).first()

            if not put_option:
                # Adjusted strike doesn't exist - find nearest
                logger.warning(f"Adjusted PE {put_strike} not found in database, finding nearest...")
                put_strike_actual = min(available_put_strikes, key=lambda x: abs(float(x) - put_strike))
                put_option = OptionChain.objects.filter(
                    underlying='NIFTY',
                    expiry_date=expiry_date,
                    strike=put_strike_actual,
                    option_type='PE'
                ).first()
                put_strike = int(put_strike_actual)
                logger.warning(f"Using nearest available PE {put_strike}")

            if not call_option or not put_option:
                raise ValueError(f"Option data not found for strikes CE {call_strike}, PE {put_strike}")

            call_premium = call_option.ltp or Decimal('0')
            put_premium = put_option.ltp or Decimal('0')
            total_premium = call_premium + put_premium

            logger.info(f"Strikes from database: CE {call_strike}, PE {put_strike}")

            # FINAL SAFETY CHECK: Verify strikes are not at psychological levels
            # This catches cases where database only has round number strikes
            final_psych_check = check_psychological_levels(call_strike, put_strike, float(nifty_price))

            if final_psych_check['any_adjustments']:
                logger.warning(f"⚠️ FINAL SAFETY CHECK: Database strikes are at psychological levels!")
                logger.warning(f"Database returned: CE {call_strike}, PE {put_strike}")
                logger.warning(f"Required adjustment: CE {call_strike}→{final_psych_check['adjusted_call']}, PE {put_strike}→{final_psych_check['adjusted_put']}")

                # Update to safe strikes
                call_strike = final_psych_check['adjusted_call']
                put_strike = final_psych_check['adjusted_put']

                # Re-fetch premiums for adjusted strikes
                call_option = OptionChain.objects.filter(
                    underlying='NIFTY',
                    expiry_date=expiry_date,
                    strike=call_strike,
                    option_type='CE'
                ).first()

                put_option = OptionChain.objects.filter(
                    underlying='NIFTY',
                    expiry_date=expiry_date,
                    strike=put_strike,
                    option_type='PE'
                ).first()

                if call_option and put_option:
                    call_premium = call_option.ltp or Decimal('0')
                    put_premium = put_option.ltp or Decimal('0')
                    total_premium = call_premium + put_premium
                    logger.info(f"✓ Adjusted to safe strikes: CE {call_strike}, PE {put_strike}")
                else:
                    # If adjusted strikes don't exist, we have a problem
                    logger.error(f"Adjusted strikes CE {call_strike}, PE {put_strike} not available in database!")
                    return JsonResponse({
                        'success': False,
                        'error': f'Cannot find safe strikes. Database has CE {final_psych_check["original_call"]}, PE {final_psych_check["original_put"]} but adjusted strikes CE {call_strike}, PE {put_strike} not available.',
                        'execution_log': execution_log
                    })

            logger.info(f"Final SAFE strikes: CE {call_strike}, PE {put_strike}")

            execution_log.append({
                'step': 9,
                'action': 'Real Premium Fetch',
                'status': 'success',
                'message': f'CE {call_strike}: ₹{float(call_premium):.2f} | PE {put_strike}: ₹{float(put_premium):.2f} | Total: ₹{float(total_premium):.2f}',
                'details': {
                    'call_strike_calculated': strike_result['call_strike'],
                    'call_strike_adjusted_by_psych': psych_analysis['adjusted_call'] if 'psych_analysis' in locals() else call_strike,
                    'call_strike_final': call_strike,
                    'call_ltp': float(call_premium),
                    'call_volume': call_option.volume,
                    'call_oi': call_option.oi,
                    'put_strike_calculated': strike_result['put_strike'],
                    'put_strike_adjusted_by_psych': psych_analysis['adjusted_put'] if 'psych_analysis' in locals() else put_strike,
                    'put_strike_final': put_strike,
                    'put_ltp': float(put_premium),
                    'put_volume': put_option.volume,
                    'put_oi': put_option.oi
                }
            })

        except Exception as e:
            logger.error(f"Failed to get option premiums: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Could not fetch option premiums: {str(e)}',
                'execution_log': execution_log
            })

        # STEP 6: Calculate margins and risk
        try:
            # Approximate margin for short strangle (15% of notional)
            margin_required = float(nifty_price * 50 * Decimal('0.15'))

            # Calculate breakeven points
            breakeven_upper = call_strike + float(total_premium)
            breakeven_lower = put_strike - float(total_premium)

            # Calculate S/R breach risks if S/R data is available
            breach_risks = None
            if 'sr_data' in locals() and sr_data is not None:
                try:
                    position_data = {
                        'position_type': 'short_strangle',
                        'spot_price': float(nifty_price),
                        'call_strike': call_strike,
                        'put_strike': put_strike,
                        'call_premium': float(call_premium),
                        'put_premium': float(put_premium),
                        'total_premium': float(total_premium),
                        'lot_size': 50  # NIFTY lot size
                    }

                    breach_risks = sr_calculator.calculate_risk_at_breach(position_data, sr_data)
                    logger.info(f"Calculated breach risks: {breach_risks}")

                except Exception as breach_err:
                    logger.warning(f"Could not calculate breach risks: {breach_err}")
                    breach_risks = None

            risk_details = {
                'margin_required': margin_required,
                'breakeven_upper': breakeven_upper,
                'breakeven_lower': breakeven_lower,
                'max_profit': float(total_premium),
                'profit_pct': (float(total_premium) / margin_required * 100) if margin_required > 0 else 0
            }

            # Add breach risks if available
            if breach_risks:
                risk_details['breach_risks'] = breach_risks['breach_risks']
                risk_message = f"Margin: ₹{margin_required:,.0f} | Breakeven: {breakeven_lower:.0f} - {breakeven_upper:.0f}"

                # Add most critical risk to message
                if breach_risks['breach_risks']['r1_breach']:
                    r1_loss = breach_risks['breach_risks']['r1_breach']['potential_loss']
                    risk_message += f" | Risk@R1: ₹{abs(r1_loss):,.0f}"
            else:
                risk_message = f'Margin: ₹{margin_required:,.0f} | Breakeven: {breakeven_lower:.0f} - {breakeven_upper:.0f}'

            execution_log.append({
                'step': 9,
                'action': 'Risk Calculation',
                'status': 'success',
                'message': risk_message,
                'details': risk_details
            })

        except Exception as e:
            logger.warning(f"Risk calculation issue: {e}")
            margin_required = 0
            breakeven_upper = call_strike
            breakeven_lower = put_strike
            breach_risks = None

        # STEP 10: Calculate Position Sizing with Averaging Logic
        position_sizing = None
        try:
            from apps.trading.services.strangle_position_sizer import StranglePositionSizer

            # Extract S/R levels from sr_data if available
            support_levels = []
            resistance_levels = []

            if 'sr_data' in locals() and sr_data is not None:
                pivot_points = sr_data.get('pivot_points', {})
                support_levels = [
                    Decimal(str(pivot_points.get('s1', 0))),
                    Decimal(str(pivot_points.get('s2', 0))),
                    Decimal(str(pivot_points.get('s3', 0)))
                ]
                resistance_levels = [
                    Decimal(str(pivot_points.get('r1', 0))),
                    Decimal(str(pivot_points.get('r2', 0))),
                    Decimal(str(pivot_points.get('r3', 0)))
                ]

            # Fallback S/R if not available
            if not support_levels or all(s == 0 for s in support_levels):
                support_levels = [
                    nifty_price * Decimal('0.98'),  # 2% below
                    nifty_price * Decimal('0.96'),  # 4% below
                    nifty_price * Decimal('0.94'),  # 6% below
                ]
                resistance_levels = [
                    nifty_price * Decimal('1.02'),  # 2% above
                    nifty_price * Decimal('1.04'),  # 4% above
                    nifty_price * Decimal('1.06'),  # 6% above
                ]

            # Calculate position sizing
            sizer = StranglePositionSizer(request.user)
            position_sizing = sizer.calculate_strangle_position_size(
                call_strike=call_strike,
                put_strike=put_strike,
                call_premium=call_premium,
                put_premium=put_premium,
                spot_price=nifty_price,
                support_levels=support_levels,
                resistance_levels=resistance_levels,
                vix=vix
            )

            logger.info(f"Position sizing calculated: Call {position_sizing['position']['call_lots']} lots, "
                       f"Put {position_sizing['position']['put_lots']} lots")

            execution_log.append({
                'step': 10,
                'action': 'Position Sizing',
                'status': 'success',
                'message': f"Call: {position_sizing['position']['call_lots']} lots | "
                          f"Put: {position_sizing['position']['put_lots']} lots | "
                          f"Premium: ₹{position_sizing['position']['total_premium_collected']:,.2f}",
                'details': {
                    'call_lots': position_sizing['position']['call_lots'],
                    'put_lots': position_sizing['position']['put_lots'],
                    'total_premium': position_sizing['position']['total_premium_collected'],
                    'margin_utilization': position_sizing['position']['margin_utilization_percent'],
                    'margin_source': position_sizing['margin_data']['source'],
                    'total_margin': position_sizing['margin_data']['total_margin'],
                    'used_margin': position_sizing['margin_data']['used_margin'],
                    'available_margin': position_sizing['margin_data']['available_margin'],
                    'margin_per_lot': position_sizing['margin_data']['margin_per_lot']
                }
            })

        except Exception as e:
            from apps.brokers.exceptions import BreezeAuthenticationError
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Position sizing calculation failed: {e}\n{error_traceback}")

            # Check if authentication error
            if isinstance(e, BreezeAuthenticationError) or 'Session key is expired' in str(e):
                return JsonResponse({
                    'success': False,
                    'auth_required': True,
                    'error': 'Breeze session expired. Please re-authenticate.',
                    'execution_log': execution_log
                })

            # Check if it's a margin fetch error
            if 'Margin not found' in str(e):
                execution_log.append({
                    'step': 10,
                    'action': 'Position Sizing',
                    'status': 'error',
                    'message': str(e),
                    'details': {
                        'error_type': 'MarginNotAvailable',
                        'full_error': str(e),
                        'action_required': 'Please ensure Neo API credentials are configured and session is active'
                    }
                })
            else:
                execution_log.append({
                    'step': 10,
                    'action': 'Position Sizing',
                    'status': 'warning',
                    'message': f'Could not calculate position sizing: {str(e)}',
                    'details': {
                        'error_type': type(e).__name__,
                        'full_error': str(e)
                    }
                })

        # Prepare final response
        explanation = {
            'strategy': 'Short Strangle (Delta-Based)',
            'underlying': 'NIFTY',
            'current_price': float(nifty_price),
            'expiry_date': expiry_date.strftime('%Y-%m-%d'),
            'days_to_expiry': days_to_expiry,
            'vix': float(vix),
            'call_strike': call_strike,
            'put_strike': put_strike,
            'call_premium': float(call_premium),
            'put_premium': float(put_premium),
            'total_premium': float(total_premium),
            'margin_required': margin_required,
            'max_profit': float(total_premium),
            'breakeven_upper': breakeven_upper,
            'breakeven_lower': breakeven_lower,
            'position_sizing': position_sizing,  # Add position sizing data
            'reasoning': {
                'strike_selection': f"Smart delta-based selection: Base Δ={strike_result['base_delta']:.2f}% → Adjusted Δ={strike_result['adjusted_delta']:.3f}%",
                'risk_profile': 'Market-neutral short strangle collecting premium with multi-factor delta adjustment',
                'entry_logic': f'Selling {days_to_expiry}-day OTM options at {float(strike_result["strike_distance"]):.0f} points from spot',
                'exit_strategy': '50% profit target or expiry, whichever comes first',
                'delta_analysis': strike_result['calculation_log'],
            },
            'execution_log': execution_log,
            'delta_details': strike_result,
            'validation_report': validation_report,  # Include validation report in response
            'breach_risks': breach_risks['breach_risks'] if breach_risks else None,  # Include S/R breach risks
            'sr_levels': {
                'pivot_points': sr_data['pivot_points'] if 'sr_data' in locals() and sr_data else None,
                'moving_averages': sr_data['moving_averages'] if 'sr_data' in locals() and sr_data else None
            }
        }

        # Save trade suggestion to database
        from apps.trading.models import TradeSuggestion
        from datetime import timedelta
        from django.utils import timezone
        import json
        from datetime import date, datetime

        # Helper to serialize dates and decimals for JSON
        def json_serial(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError(f"Type {type(obj)} not serializable")

        # Convert algorithm reasoning to JSON-safe format
        algorithm_reasoning_safe = json.loads(
            json.dumps({
                'delta_details': strike_result,
                'validation_report': validation_report,
                'breach_risks': breach_risks['breach_risks'] if breach_risks else None,
                'sr_levels': {
                    'pivot_points': sr_data['pivot_points'] if 'sr_data' in locals() and sr_data else None,
                    'moving_averages': sr_data['moving_averages'] if 'sr_data' in locals() and sr_data else None
                },
                'execution_log': execution_log
            }, default=json_serial)
        )

        # Convert position details to JSON-safe format
        position_details_safe = json.loads(
            json.dumps(position_sizing, default=json_serial)
        )

        suggestion = TradeSuggestion.objects.create(
            user=request.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='NEUTRAL',
            # Market Data
            spot_price=nifty_price,
            vix=vix,
            expiry_date=expiry_date,
            days_to_expiry=days_to_expiry,
            # Strike Details
            call_strike=Decimal(str(call_strike)),
            put_strike=Decimal(str(put_strike)),
            call_premium=call_premium,
            put_premium=put_premium,
            total_premium=total_premium,
            # Position Sizing
            recommended_lots=position_sizing['position']['call_lots'],
            margin_required=Decimal(str(position_sizing['position']['total_margin_required'])),
            margin_available=Decimal(str(position_sizing['margin_data']['available_margin'])),
            margin_per_lot=Decimal(str(position_sizing['margin_data']['margin_per_lot'])),
            margin_utilization=Decimal(str(position_sizing['position']['margin_utilization_percent'])),
            # Risk Metrics
            max_profit=total_premium,
            breakeven_upper=Decimal(str(breakeven_upper)),
            breakeven_lower=Decimal(str(breakeven_lower)),
            # Complete Data
            algorithm_reasoning=algorithm_reasoning_safe,
            position_details=position_details_safe,
            # Expiry: 24 hours from now
            expires_at=timezone.now() + timedelta(hours=24)
        )

        logger.info(f"Saved trade suggestion #{suggestion.id} for {request.user.username}")

        # Add suggestion_id to response
        explanation['suggestion_id'] = suggestion.id

        return JsonResponse({
            'success': True,
            'strangle': explanation
        })

    except Exception as e:
        from apps.brokers.exceptions import BreezeAuthenticationError
        logger.error(f"Error in trigger_nifty_strangle: {e}", exc_info=True)

        # Check if authentication error
        if isinstance(e, BreezeAuthenticationError) or 'Session key is expired' in str(e):
            return JsonResponse({
                'success': False,
                'auth_required': True,
                'error': 'Breeze session expired. Please re-authenticate.',
                'execution_log': execution_log if 'execution_log' in locals() else []
            })

        return JsonResponse({
            'success': False,
            'error': str(e),
            'execution_log': execution_log if 'execution_log' in locals() else []
        })
