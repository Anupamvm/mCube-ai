"""
Suggestion Service - Shared logic for saving futures TradeSuggestion records

Called from both:
- Background task (execute_futures_algorithm in strategies/tasks.py)
- UI trigger (trigger_futures_algorithm in trading/views/algorithm_views.py)

Extracts the save logic so both paths produce identical TradeSuggestion records.
"""

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from apps.core.utils import json_serial as _json_serial

logger = logging.getLogger(__name__)


def save_futures_suggestions(passed_results, user=None, source='manual'):
    """
    Save PASS results as TradeSuggestion records with real Breeze margin data.

    DEDUPLICATION: Skips creating suggestions for (symbol, expiry_date) combinations
    that already have a TradeSuggestion created today. This prevents duplicate records
    when both Celery task (8:30 AM) and web trigger run on the same day.

    Args:
        passed_results: list of analysis result dicts with verdict='PASS'.
            Required keys per result:
                symbol, direction, expiry_date, spot_price, futures_price,
                composite_score, scores, metrics, execution_log, explanation
            Optional keys:
                sr_data, breach_risks
        user: Django User instance. If None, uses first superuser.
        source: 'manual' or 'auto' - used for logging only, not deduplication

    Returns:
        list of saved suggestion IDs (None entries for failures or skipped duplicates)
    """
    from apps.trading.models import TradeSuggestion
    from apps.data.models import ContractData

    if not passed_results:
        return []

    today = date.today()

    # Get existing full-algo suggestions for today (exclude lightweight screening records,
    # which should be overwritten by the full algorithm run).
    existing_suggestions = set(
        TradeSuggestion.objects.filter(
            created_at__date=today,
            suggestion_type='FUTURES'
        ).exclude(
            algorithm_reasoning__source='screening'
        ).values_list('instrument', 'expiry_date')
    )
    logger.info(f"Found {len(existing_suggestions)} existing full-algo futures suggestions for today")

    # Resolve user
    if user is None:
        user = User.objects.filter(is_superuser=True).first()
        if user is None:
            logger.error("No superuser found for background task suggestions")
            return []

    # Initialize Breeze client
    breeze = None
    try:
        from apps.brokers.integrations.breeze import get_breeze_client, get_india_vix
        breeze = get_breeze_client()
    except Exception as e:
        logger.warning(f"Could not initialize Breeze client for position sizing: {e}")

    # Fetch VIX once
    vix_value = None
    try:
        from apps.brokers.integrations.breeze import get_india_vix
        vix_value = get_india_vix()
        logger.info(f"Fetched VIX for futures suggestions: {vix_value}")
    except Exception as vix_err:
        logger.warning(f"Could not fetch VIX for suggestions: {vix_err}")

    # Fetch available F&O margin
    try:
        from apps.trading.services.margin_service import get_available_margin
        available_margin = get_available_margin(breeze)
    except Exception as e:
        logger.warning(f"Could not fetch available margin: {e}")
        available_margin = 5000000  # 50 lakh fallback

    suggestion_ids = []

    for result in passed_results:
        try:
            from apps.trading.services.position_service import calculate_position_sizing

            symbol = result['symbol']
            expiry_date_raw = result['expiry_date']
            direction = result['direction']
            futures_price = Decimal(str(result['futures_price']))
            spot_price = Decimal(str(result['spot_price']))
            composite_score = result['composite_score']

            # Parse expiry date for deduplication check (handle both string and date objects)
            if isinstance(expiry_date_raw, str):
                expiry_dt = datetime.strptime(expiry_date_raw, '%Y-%m-%d')
                expiry_date_str = expiry_date_raw
            elif isinstance(expiry_date_raw, date):
                expiry_dt = datetime.combine(expiry_date_raw, datetime.min.time())
                expiry_date_str = expiry_date_raw.strftime('%Y-%m-%d')
            else:
                expiry_dt = datetime.strptime(str(expiry_date_raw), '%Y-%m-%d')
                expiry_date_str = str(expiry_date_raw)

            # DEDUPLICATION: Skip if already saved today by full-algo (screening records are overwritten)
            if (symbol, expiry_dt.date()) in existing_suggestions:
                logger.info(f"Skipping duplicate suggestion for {symbol} (expiry: {expiry_date_str}) - already exists today")
                suggestion_ids.append(None)
                continue

            # Delete any lightweight screening record so it gets replaced by this full-algo result
            TradeSuggestion.objects.filter(
                created_at__date=today,
                strategy='icici_futures',
                instrument=symbol,
                expiry_date=expiry_dt.date(),
                algorithm_reasoning__source='screening',
            ).delete()

            # Get contract details
            contract = ContractData.objects.filter(
                symbol=symbol,
                option_type='FUTURE',
                expiry=expiry_date_str
            ).first()

            if not contract:
                logger.warning(f"No contract found for {symbol} expiry {expiry_date_str}")
                suggestion_ids.append(None)
                continue

            lot_size = contract.lot_size

            # Format expiry for Breeze API (expiry_dt already parsed above)
            expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()

            # Calculate position sizing using shared service
            position_sizing = calculate_position_sizing(
                breeze=breeze,
                symbol=symbol,
                expiry=expiry_breeze,
                lot_size=lot_size,
                futures_price=futures_price,
                direction=direction,
                available_margin=available_margin
            )

            # Extract values from position sizing result
            position = position_sizing['position']
            margin_data = position_sizing['margin_data']
            risk_metrics = position_sizing['risk_metrics']

            recommended_lots = position['recommended_lots']
            margin_required = Decimal(str(position['total_margin_required']))
            margin_per_lot_decimal = Decimal(str(margin_data['margin_per_lot']))
            margin_available_decimal = Decimal(str(margin_data['available_margin']))
            margin_utilization = position['margin_utilization_percent']

            stop_loss_price = Decimal(str(position_sizing['stop_loss']))
            target_price = Decimal(str(position_sizing['target']))

            max_loss_value = Decimal(str(risk_metrics['max_loss']))
            max_profit_value = Decimal(str(risk_metrics['max_profit']))
            risk_reward_ratio_value = Decimal(str(risk_metrics['risk_reward_ratio']))

            # Build position sizing data for saving
            position_sizing_data = {
                'position': position,
                'margin_data': margin_data,
                'stop_loss': position_sizing['stop_loss'],
                'target': position_sizing['target'],
                'direction': direction,
                'entry_price': float(futures_price),
                'expiry_date': expiry_date_str,
            }

            # Convert data to JSON-safe format
            algorithm_reasoning_safe = json.loads(
                json.dumps({
                    'metrics': result.get('metrics', {}),
                    'execution_log': result.get('execution_log', []),
                    'composite_score': composite_score,
                    'scores': result.get('scores', {}),
                    'explanation': result.get('explanation', ''),
                    'sr_data': result.get('sr_data'),
                    'breach_risks': result.get('breach_risks')
                }, default=_json_serial)
            )

            logger.info(f"Creating suggestion for {symbol}: lots={recommended_lots}, margin={margin_required}, score={composite_score}")

            suggestion = TradeSuggestion.objects.create(
                user=user,
                source=source,
                strategy='icici_futures',
                suggestion_type='FUTURES',
                instrument=symbol,
                direction=direction.upper(),
                # Market Data
                spot_price=spot_price,
                vix=vix_value,
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
                risk_reward_ratio=risk_reward_ratio_value,
                breakeven_upper=target_price if direction == 'LONG' else None,
                breakeven_lower=stop_loss_price if direction == 'LONG' else None,
                # Complete Data (includes real position sizing with 50% rule)
                algorithm_reasoning=algorithm_reasoning_safe,
                position_details=json.loads(json.dumps(position_sizing_data, default=_json_serial)),
                # Expiry: 24 hours from now
                expires_at=timezone.now() + timedelta(hours=24)
            )

            suggestion_ids.append(suggestion.id)
            logger.info(f"Saved futures suggestion #{suggestion.id} for {symbol}")

        except Exception as e:
            logger.error(f"Error saving suggestion for {result.get('symbol')}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            suggestion_ids.append(None)
            continue

    return suggestion_ids
