"""
Trade Tracking Views

Page views for trade history and performance reporting.
"""

import json
import logging
import csv
from datetime import date, datetime
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

from apps.trading.models import TakenTrade
from apps.trading.services.trade_action_service import TradeActionService
from apps.brokers.models import BrokerTradeHistory
from apps.brokers.services.trade_sync import TradeSyncService
from apps.analytics.services.fy_analytics import FYAnalyticsService
from apps.accounts.models import BrokerAccount

logger = logging.getLogger(__name__)


@login_required
def trade_history(request):
    """
    Trade History page with tabs for Active, Closed, and Broker Sync.

    GET /trading/history/

    Supports:
    - Filtering by status, date, strategy, outcome
    - Pagination for closed trades
    - CSV export
    """
    user = request.user

    # Get filter parameters
    status_filter = request.GET.get('status', '')
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    strategy = request.GET.get('strategy', '')
    outcome = request.GET.get('outcome', '')
    export_format = request.GET.get('export', '')

    # Get active trades
    active_trades = TradeActionService.get_active_trades(user=user)

    # Get closed trades with filters
    closed_trades = TakenTrade.objects.filter(
        user=user,
        status='CLOSED'
    ).select_related('account', 'suggestion', 'position')

    if from_date:
        closed_trades = closed_trades.filter(closed_at__date__gte=from_date)
    if to_date:
        closed_trades = closed_trades.filter(closed_at__date__lte=to_date)
    if strategy:
        closed_trades = closed_trades.filter(strategy=strategy)
    if outcome:
        closed_trades = closed_trades.filter(outcome=outcome)

    closed_trades = closed_trades.order_by('-closed_at')

    # Handle CSV export
    if export_format == 'csv':
        return export_trades_csv(closed_trades)

    # Paginate closed trades
    paginator = Paginator(closed_trades, 25)
    page_number = request.GET.get('page', 1)
    closed_trades_page = paginator.get_page(page_number)

    # Get summary stats
    summary = TradeActionService.get_trade_summary(user)

    # Get accounts for sync dropdown (accounts are shared, not user-specific)
    accounts = BrokerAccount.objects.filter(is_active=True)

    # Get recent broker trades (all accounts since they're shared)
    broker_trades = BrokerTradeHistory.objects.all().order_by('-trade_date', '-trade_time')[:10]

    context = {
        'active_trades': active_trades,
        'closed_trades': closed_trades_page,
        'active_count': active_trades.count(),
        'closed_count': closed_trades.count(),
        'summary': summary,
        'accounts': accounts,
        'broker_trades': broker_trades,
        'today': date.today().isoformat(),
        'from_date': from_date,
        'to_date': to_date,
        'strategy': strategy,
        'outcome': outcome,
        'is_paginated': closed_trades_page.has_other_pages(),
        'page_obj': closed_trades_page,
    }

    return render(request, 'trading/trade_history.html', context)


@login_required
def performance(request):
    """
    FY Performance Report page.

    GET /trading/performance/
    """
    user = request.user

    # Get FY year from query params
    fy_year = request.GET.get('fy_year')
    if fy_year:
        fy_year = int(fy_year)
    else:
        fy_year = FYAnalyticsService.get_current_fy_year()

    # Get account filter
    account_id = request.GET.get('account_id')
    account = None
    if account_id:
        account = get_object_or_404(BrokerAccount, id=account_id)

    # Get FY report
    report = FYAnalyticsService.get_fy_report(
        user=user,
        fy_year=fy_year,
        account=account
    )

    # Get available FY years
    available_years = FYAnalyticsService.get_available_fy_years(user)

    # Get accounts for dropdown (accounts are shared, not user-specific)
    accounts = BrokerAccount.objects.filter(is_active=True)

    # Get broker trade history stats for the FY
    fy_start, fy_end, _ = FYAnalyticsService.get_fy_dates(fy_year)
    broker_trade_stats = {}
    for acc in accounts:
        trades = BrokerTradeHistory.objects.filter(
            account=acc,
            trade_date__gte=fy_start,
            trade_date__lte=fy_end
        )
        last_trade = trades.order_by('-created_at').first()
        broker_trade_stats[acc.id] = {
            'total': trades.count(),
            'buy': trades.filter(trade_type='BUY').count(),
            'sell': trades.filter(trade_type='SELL').count(),
            'last_sync': last_trade.created_at.isoformat() if last_trade else None
        }

    # Get TakenTrade stats
    taken_trade_count = TakenTrade.objects.filter(
        user=user,
        status='CLOSED',
        closed_at__date__gte=fy_start,
        closed_at__date__lte=fy_end
    ).count()

    context = {
        'report': report,
        'current_fy_year': fy_year,
        'available_years': available_years,
        'accounts': accounts,
        'selected_account_id': int(account_id) if account_id else None,
        'broker_trade_stats': json.dumps(broker_trade_stats),
        'taken_trade_count': taken_trade_count,
        'today': date.today().isoformat(),
        'fy_start': fy_start.isoformat(),
        'fy_end': fy_end.isoformat(),
    }

    return render(request, 'trading/performance.html', context)


@login_required
def trade_detail(request, trade_id):
    """
    Trade Detail page.

    GET /trading/trades/<id>/
    """
    trade = get_object_or_404(
        TakenTrade.objects.select_related('suggestion', 'position', 'account'),
        id=trade_id,
        user=request.user
    )

    # Get related broker trades
    broker_trades = BrokerTradeHistory.objects.filter(
        taken_trade=trade
    ).order_by('-trade_date')

    context = {
        'trade': trade,
        'broker_trades': broker_trades,
    }

    return render(request, 'trading/trade_detail.html', context)


def export_trades_csv(trades_queryset):
    """
    Export trades to CSV file.

    Args:
        trades_queryset: QuerySet of TakenTrade objects

    Returns:
        HttpResponse with CSV file
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="trades_export_{date.today().isoformat()}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Date', 'Instrument', 'Strategy', 'Direction',
        'Entry Price', 'Exit Price', 'Quantity', 'Lot Size',
        'Realized P&L', 'Charges', 'Net P&L', 'ROM %',
        'Outcome', 'Account', 'Notes'
    ])

    for trade in trades_queryset:
        writer.writerow([
            trade.id,
            trade.closed_at.strftime('%Y-%m-%d %H:%M') if trade.closed_at else '',
            trade.instrument,
            trade.strategy,
            trade.direction,
            trade.entry_price or '',
            trade.exit_price or '',
            trade.quantity,
            trade.lot_size,
            trade.realized_pnl or '',
            trade.charges or '',
            trade.net_pnl or '',
            trade.return_on_margin or '',
            trade.outcome,
            trade.account.account_name if trade.account else '',
            trade.notes or ''
        ])

    return response
