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
from django.db.models import Q

from apps.data.models import ContractData
from apps.core.models import CredentialStore

logger = logging.getLogger(__name__)


def manual_triggers_refactored(request):
    """
    Refactored Manual Trade Triggers Page with clean tabbed interface.

    Displays three trading features in a modern UI:
    1. Run Futures Algorithm - Screen and suggest futures opportunities
    2. Nifty Options Strangle - Generate Kotak strangle position
    3. Verify Future Trade - Verify a specific futures contract

    Template: trading/manual_triggers_refactored.html
    Features: Tab-based navigation, modal dialogs, broker authentication

    Returns:
        HttpResponse: Rendered template
    """
    return render(request, 'trading/manual_triggers_refactored.html')


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
