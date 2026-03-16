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
from apps.core.utils import json_serial

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

    # ===== BUILD UNIFIED FUTURES OPPORTUNITIES =====
    unified_opportunities = []
    recommendation_history = {}  # symbol -> list of historical recommendations

    def _suggestion_to_contract(suggestion, rec_count=0, source='historical'):
        """Convert a TradeSuggestion to the contract data format expected by the frontend."""
        reasoning = suggestion.algorithm_reasoning or {}
        position_details = suggestion.position_details or {}
        analyzed_at_str = timezone.localtime(suggestion.created_at).strftime('%d %b %H:%M') if suggestion.created_at else None
        analyzed_at_iso = timezone.localtime(suggestion.created_at).isoformat() if suggestion.created_at else None
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
            'analyzed_at': analyzed_at_str,
            'analyzed_at_iso': analyzed_at_iso,
            'source': source,
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
                'date': timezone.localtime(suggestion.created_at).strftime('%Y-%m-%d %H:%M'),
                'direction': suggestion.direction,
                'score': reasoning.get('composite_score', 0),
                'entry_price': float(suggestion.spot_price or 0),
                'futures_price': metrics.get('futures_price', 0),
                'status': suggestion.status,
                'lot_size': suggestion.position_details.get('lot_size', 0) if suggestion.position_details else 0,
                'recommended_lots': suggestion.recommended_lots or 0,
                'expiry_date': suggestion.expiry_date.strftime('%Y-%m-%d') if suggestion.expiry_date else '',
            })

        # ===== COLLECT ALL SUGGESTIONS WITH SOURCE TAGS =====
        today_start = timezone.localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
        timezone.localtime(timezone.now())

        # Today's automated results
        todays_auto = TradeSuggestion.objects.filter(
            user=request.user,
            strategy='icici_futures',
            source='auto',
            created_at__gte=today_start
        ).order_by('-created_at')

        # Historical results (last 7 days, excluding today's auto)
        cutoff_7d = timezone.now() - timedelta(days=7)
        historical = all_history.filter(created_at__gte=cutoff_7d).exclude(
            source='auto', created_at__gte=today_start
        )

        # Build per-suggestion contract dicts with source tag
        all_tagged_contracts = []
        for suggestion in todays_auto:
            rec_count = len(recommendation_history.get(suggestion.instrument, []))
            contract = _suggestion_to_contract(suggestion, rec_count, source='auto')
            all_tagged_contracts.append(contract)

        for suggestion in historical:
            rec_count = len(recommendation_history.get(suggestion.instrument, []))
            source_tag = 'historical'
            # Today's manual triggers are tagged 'manual' (not auto, but created today)
            if suggestion.created_at >= today_start and suggestion.source != 'auto':
                source_tag = 'manual'
            contract = _suggestion_to_contract(suggestion, rec_count, source=source_tag)
            all_tagged_contracts.append(contract)

        # ===== CONSOLIDATE BY (symbol, expiry_date) =====
        consolidated = {}  # key: "SYMBOL|EXPIRY_DATE" -> merged entry
        for contract in all_tagged_contracts:
            key = f"{contract['symbol']}|{contract['expiry_date']}"
            source = contract['source']

            if key not in consolidated:
                # First occurrence — use as base
                contract['sources'] = [source]
                contract['source_details'] = {
                    source: {
                        'analyzed_at': contract['analyzed_at'],
                        'score': contract['composite_score'],
                    }
                }
                consolidated[key] = contract
            else:
                existing = consolidated[key]
                # Add source if not already present
                if source not in existing['sources']:
                    existing['sources'].append(source)
                    existing['source_details'][source] = {
                        'analyzed_at': contract['analyzed_at'],
                        'score': contract['composite_score'],
                    }
                # Keep highest score and most recent data
                if contract['composite_score'] > existing['composite_score']:
                    # Update base data with higher-scoring entry (preserve sources/source_details)
                    sources = existing['sources']
                    source_details = existing['source_details']
                    existing.update(contract)
                    existing['sources'] = sources
                    existing['source_details'] = source_details

        # ===== COMPUTE CONVICTION SCORE =====
        for entry in consolidated.values():
            freq = len(recommendation_history.get(entry['symbol'], []))
            entry['frequency'] = freq
            entry['recommendation_count'] = freq

            # Conviction: score * 0.6 + frequency_normalized * 0.25 + source_diversity * 0.15
            freq_normalized = min(freq / 10.0, 1.0) * 100  # cap at 10 appearances
            source_diversity = len(entry['sources']) / 3.0 * 100  # max 3 sources
            entry['conviction_score'] = round(
                entry['composite_score'] * 0.6 +
                freq_normalized * 0.25 +
                source_diversity * 0.15,
                1
            )

            # Determine latest_analyzed_at for sorting by recency
            entry['latest_analyzed_at'] = entry.get('analyzed_at_iso', '')

        unified_opportunities = sorted(
            consolidated.values(),
            key=lambda x: x['conviction_score'],
            reverse=True
        )

    except Exception as e:
        logger.warning(f"Error loading unified futures opportunities: {e}")


    context = {
        'data_freshness': data_freshness,
        'unified_opportunities': json.dumps(unified_opportunities, default=json_serial) if unified_opportunities else '[]',
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
    from apps.core.models import TradingSchedule
    from django.utils import timezone

    today = timezone.localdate()
    schedule = TradingSchedule.objects.filter(date=today).first()

    # Defaults from model if no schedule exists for today
    import datetime as dt
    market_open = schedule.open_time.strftime('%H:%M') if schedule else '09:15'
    market_close = schedule.mkt_close_time.strftime('%H:%M') if schedule else '15:32'

    return render(request, 'trading/view_trades.html', {
        'market_open': market_open,
        'market_close': market_close,
    })
