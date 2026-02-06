"""
Template Views - Page Rendering

Simple views that render templates for the trading interface.
These views handle page display but delegate business logic to other modules.

Extracted from apps/trading/views.py as part of refactoring to improve
code organization and maintainability.
"""

import logging
from datetime import datetime, timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from apps.data.models import ContractData
from apps.core.models import CredentialStore

logger = logging.getLogger(__name__)


@login_required
def manual_triggers_refactored(request):
    """
    Refactored Manual Trade Triggers Page with clean tabbed interface.

    Displays three trading features in a modern UI:
    1. Run Futures Algorithm - Screen and suggest futures opportunities
    2. Nifty Options Strangle - Generate Kotak strangle position
    3. Verify Future Trade - Verify a specific futures contract

    Template: trading/manual_triggers_refactored.html
    Features: Tab-based navigation, modal dialogs, broker authentication

    Now pre-loads the latest futures algorithm results so they display immediately on page load.

    Returns:
        HttpResponse: Rendered template with data freshness info and preloaded results
    """
    import json
    from decimal import Decimal
    from django.utils import timezone
    from apps.data.models import TLStockData
    from apps.trading.models import TradeSuggestion

    # Get data freshness info
    data_freshness = {
        'contract_count': 0,
        'stock_count': 0,
        'last_updated': None,
        'last_updated_display': 'Never',
        'is_stale': True,  # Data older than 8 hours
    }

    try:
        # Get ContractData freshness
        contract_count = ContractData.objects.count()
        latest_contract = ContractData.objects.order_by('-updated_at').first()

        # Get TLStockData freshness
        stock_count = TLStockData.objects.count()
        latest_stock = TLStockData.objects.order_by('-updated_at').first()

        data_freshness['contract_count'] = contract_count
        data_freshness['stock_count'] = stock_count

        # Determine last update time (most recent of both)
        last_updated = None
        if latest_contract and latest_stock:
            last_updated = max(latest_contract.updated_at, latest_stock.updated_at)
        elif latest_contract:
            last_updated = latest_contract.updated_at
        elif latest_stock:
            last_updated = latest_stock.updated_at

        if last_updated:
            data_freshness['last_updated'] = last_updated
            # Format for display
            now = datetime.now(last_updated.tzinfo) if last_updated.tzinfo else datetime.now()
            age = now - last_updated

            if age.total_seconds() < 60:
                data_freshness['last_updated_display'] = 'Just now'
            elif age.total_seconds() < 3600:
                minutes = int(age.total_seconds() / 60)
                data_freshness['last_updated_display'] = f'{minutes} min ago'
            elif age.total_seconds() < 86400:
                hours = int(age.total_seconds() / 3600)
                data_freshness['last_updated_display'] = f'{hours} hr ago'
            else:
                days = int(age.total_seconds() / 86400)
                data_freshness['last_updated_display'] = f'{days} day(s) ago'

            # Check if stale (older than 8 hours)
            data_freshness['is_stale'] = age.total_seconds() > 28800

    except Exception as e:
        logger.warning(f"Error getting data freshness: {e}")

    # ===== PRELOAD LATEST FUTURES SUGGESTIONS =====
    # Fetch the latest futures suggestions (created within last 7 days for current view)
    # AND 30 days history for aggregation
    preloaded_results = None
    todays_results = None
    recommendation_history = {}  # symbol -> list of historical recommendations

    def _suggestion_to_contract(suggestion, rec_count=0):
        """Convert a TradeSuggestion to the contract data format expected by the frontend."""
        reasoning = suggestion.algorithm_reasoning or {}
        position_details = suggestion.position_details or {}
        return {
            'symbol': suggestion.instrument,
            'expiry': suggestion.expiry_date.strftime('%d-%b-%Y') if suggestion.expiry_date else '',
            'expiry_date': suggestion.expiry_date.strftime('%Y-%m-%d') if suggestion.expiry_date else '',
            'composite_score': reasoning.get('composite_score', 0),
            'direction': suggestion.direction,
            'verdict': 'PASS',
            'technical_verdict': 'PASS',
            'historical_passed': True,
            'success': True,
            'spot_price': float(suggestion.spot_price or 0),
            'futures_price': reasoning.get('metrics', {}).get('futures_price', 0),
            'basis': reasoning.get('metrics', {}).get('basis', 0),
            'basis_pct': reasoning.get('metrics', {}).get('basis_pct', 0),
            'volume': reasoning.get('metrics', {}).get('volume', 0),
            'lot_size': position_details.get('lot_size', 0),
            'explanation': reasoning.get('explanation', []),
            'execution_log': reasoning.get('execution_log', []),
            'metrics': reasoning.get('metrics', {}),
            'scores': reasoning.get('scores', {}),
            'sr_data': reasoning.get('sr_data'),
            'breach_risks': reasoning.get('breach_risks'),
            'historical_verification': reasoning.get('historical_verification'),
            'suggestion_id': suggestion.id,
            'recommended_lots': suggestion.recommended_lots,
            'margin_required': float(suggestion.margin_required or 0),
            'margin_per_lot': float(suggestion.margin_per_lot or 0),
            'max_profit': float(suggestion.max_profit or 0),
            'max_loss': float(suggestion.max_loss or 0),
            'recommendation_count': rec_count,
        }

    try:
        # Get 30 days of history for aggregation
        history_cutoff = timezone.now() - timedelta(days=30)
        all_history = TradeSuggestion.objects.filter(
            user=request.user,
            strategy='icici_futures',
            status__in=['SUGGESTED', 'TAKEN', 'ACTIVE', 'CLOSED', 'SUCCESSFUL', 'LOSS'],
            created_at__gte=history_cutoff
        ).order_by('-created_at')

        # Build recommendation history by symbol
        for suggestion in all_history:
            symbol = suggestion.instrument
            if symbol not in recommendation_history:
                recommendation_history[symbol] = []

            reasoning = suggestion.algorithm_reasoning or {}
            metrics = reasoning.get('metrics', {})

            recommendation_history[symbol].append({
                'id': suggestion.id,
                'date': suggestion.created_at.strftime('%Y-%m-%d %H:%M'),
                'direction': suggestion.direction,
                'score': reasoning.get('composite_score', 0),
                'entry_price': float(suggestion.spot_price or 0),
                'futures_price': metrics.get('futures_price', 0),
                'status': suggestion.status,
                'lot_size': suggestion.position_details.get('lot_size', 0) if suggestion.position_details else 0,
                'recommended_lots': suggestion.recommended_lots or 0,
                'expiry_date': suggestion.expiry_date.strftime('%Y-%m-%d') if suggestion.expiry_date else '',
            })

        # ===== TODAY'S AUTOMATED RESULTS =====
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        todays_auto_suggestions = TradeSuggestion.objects.filter(
            user=request.user,
            strategy='icici_futures',
            source='auto',
            created_at__gte=today_start
        ).order_by('-created_at')

        if todays_auto_suggestions.exists():
            todays_contracts = []
            for suggestion in todays_auto_suggestions:
                rec_count = len(recommendation_history.get(suggestion.instrument, []))
                todays_contracts.append(_suggestion_to_contract(suggestion, rec_count))

            todays_contracts.sort(key=lambda x: x['composite_score'], reverse=True)

            most_recent_auto = todays_auto_suggestions.first()
            todays_results = {
                'success': True,
                'all_contracts': todays_contracts,
                'total_passed': len(todays_contracts),
                'batch_time': most_recent_auto.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }

        # ===== PREVIOUS SUGGESTIONS (exclude today's auto to avoid duplication) =====
        cutoff_time = timezone.now() - timedelta(days=7)
        latest_suggestions = all_history.filter(created_at__gte=cutoff_time).exclude(
            source='auto', created_at__gte=today_start
        )

        if latest_suggestions.exists():
            # Get the most recent suggestion's timestamp
            most_recent = latest_suggestions.first()
            batch_start = most_recent.created_at - timedelta(minutes=5)

            # Get all suggestions from this batch
            batch_suggestions = latest_suggestions.filter(created_at__gte=batch_start)

            all_contracts = []
            for suggestion in batch_suggestions:
                rec_count = len(recommendation_history.get(suggestion.instrument, []))
                all_contracts.append(_suggestion_to_contract(suggestion, rec_count))

            # Sort by composite score descending
            all_contracts.sort(key=lambda x: x['composite_score'], reverse=True)

            preloaded_results = {
                'success': True,
                'all_contracts': all_contracts,
                'total_analyzed': len(all_contracts),
                'total_passed': len(all_contracts),
                'total_hist_fail': 0,
                'total_failed': 0,
                'total_errors': 0,
                'historical_validation_enabled': True,
                'preloaded': True,
                'batch_time': most_recent.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }

    except Exception as e:
        logger.warning(f"Error loading preloaded futures results: {e}")

    # Helper function to serialize for JSON
    def json_serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Type {type(obj)} not serializable")

    context = {
        'data_freshness': data_freshness,
        'preloaded_results': json.dumps(preloaded_results, default=json_serial) if preloaded_results else 'null',
        'todays_results': json.dumps(todays_results, default=json_serial) if todays_results else 'null',
        'recommendation_history': json.dumps(recommendation_history, default=json_serial) if recommendation_history else '{}',
    }

    return render(request, 'trading/manual_triggers_refactored.html', context)


def manual_triggers(request):
    """
    Manual Trade Triggers Page (Original Version).

    Displays three trading features:
    1. Run Futures Algorithm - Screen and suggest futures opportunities
    2. Nifty Options Strangle - Generate Kotak strangle position
    3. Verify Future Trade - Verify a specific futures contract

    Pre-loads futures contracts from Trendlyne data based on volume criteria:
    - This month expiry (d30 days): Volume e 1000 traded contracts
    - Next month expiry (30-60 days): Volume e 800 traded contracts

    Template: trading/manual_triggers.html

    Context:
        futures_contracts (list): List of contract dicts with:
            - value: "SYMBOL|YYYY-MM-DD" format for form submission
            - display: "SYMBOL - DD-MMM-YYYY" for UI display
            - volume: Traded contracts volume
            - price: Current price
            - lot_size: Lot size
        page_title (str): Page title
        total_contracts (int): Total contracts found
        breeze_api_key (str): Breeze API key for login link

    Returns:
        HttpResponse: Rendered template with contract list

    Note:
        Falls back to hardcoded list of 10 stocks if no Trendlyne data available
    """
    today = datetime.now().date()

    # Calculate date ranges for filtering
    # This month: expiry within next 30 days
    this_month_end = today + timedelta(days=30)
    # Next month: expiry between 30-60 days
    next_month_start = today + timedelta(days=30)
    next_month_end = today + timedelta(days=60)

    # Query futures contracts meeting volume criteria
    # Using OR logic: (this month >= 1000) OR (next month >= 800)
    futures_contracts = ContractData.objects.filter(
        option_type='FUTURE',  # Futures only (stored as 'FUTURE' in DB)
        expiry__gte=str(today),
        expiry__lte=str(next_month_end)
    ).filter(
        Q(expiry__lte=str(this_month_end), traded_contracts__gte=1000) |  # This month
        Q(expiry__gte=str(next_month_start), expiry__lte=str(next_month_end), traded_contracts__gte=800)  # Next month
    ).order_by('symbol', 'expiry').values(
        'symbol',
        'expiry',
        'traded_contracts',
        'price',
        'lot_size'
    )

    # Format contracts for template display
    contract_list = []
    for contract in futures_contracts:
        expiry_date = datetime.strptime(contract['expiry'], '%Y-%m-%d').strftime('%d-%b-%Y')
        display_name = f"{contract['symbol']} - {expiry_date}"
        contract_value = f"{contract['symbol']}|{contract['expiry']}"  # Format: SYMBOL|YYYY-MM-DD

        contract_list.append({
            'value': contract_value,
            'display': display_name,
            'volume': contract['traded_contracts'],
            'price': contract['price'],
            'lot_size': contract['lot_size']
        })

    logger.info(f"Found {len(contract_list)} futures contracts with sufficient volume")

    # Fallback if no contracts found in Trendlyne data
    if not contract_list:
        logger.warning("No contracts found in Trendlyne data, using fallback list")

        # Calculate approximate expiry dates
        current_month_expiry = (today + timedelta(days=25)).strftime('%d-%b-%Y')
        next_month_expiry = (today + timedelta(days=55)).strftime('%d-%b-%Y')

        # Top 10 liquid stocks for fallback
        fallback_stocks = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
            'HINDUNILVR', 'ITC', 'SBIN', 'BHARTIARTL', 'KOTAKBANK'
        ]

        for stock in fallback_stocks:
            # Current month contract
            contract_list.append({
                'value': f"{stock}|{(today + timedelta(days=25)).strftime('%Y-%m-%d')}",
                'display': f"{stock} - {current_month_expiry}",
                'volume': 1000,
                'price': 0,
                'lot_size': 0
            })
            # Next month contract
            contract_list.append({
                'value': f"{stock}|{(today + timedelta(days=55)).strftime('%Y-%m-%d')}",
                'display': f"{stock} - {next_month_expiry}",
                'volume': 800,
                'price': 0,
                'lot_size': 0
            })

    # Get Breeze API key for login link
    breeze_creds = CredentialStore.objects.filter(service='breeze').first()
    breeze_api_key = breeze_creds.api_key if breeze_creds else ''

    context = {
        'futures_contracts': contract_list,
        'page_title': 'Manual Trade Triggers',
        'total_contracts': len(contract_list),
        'breeze_api_key': breeze_api_key,
    }

    return render(request, 'trading/manual_triggers.html', context)


@login_required
def view_trades(request):
    """
    View all active trades across Breeze and Neo accounts
    """
    return render(request, 'trading/view_trades.html')
