"""
P&L Aggregation Utility for mCube Trading System

This module provides functions for aggregating P&L data at multiple levels:
- Account-level P&L
- Position-level P&L
- Strategy-level P&L
- Daily/Weekly/Monthly summaries
"""

from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Any
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone


def get_account_pnl_summary(account) -> Dict[str, Any]:
    """
    Get comprehensive P&L summary for an account

    Args:
        account: BrokerAccount instance

    Returns:
        dict: Account P&L summary including realized, unrealized, total
    """
    from apps.positions.models import Position
    from apps.core.constants import POSITION_STATUS_ACTIVE, POSITION_STATUS_CLOSED

    # Get realized P&L (closed positions)
    closed_positions = Position.objects.filter(
        account=account,
        status=POSITION_STATUS_CLOSED
    )

    realized_stats = closed_positions.aggregate(
        total_realized=Sum('realized_pnl'),
        closed_count=Count('id')
    )

    # Get unrealized P&L (active positions)
    active_positions = Position.objects.filter(
        account=account,
        status=POSITION_STATUS_ACTIVE
    )

    unrealized_stats = active_positions.aggregate(
        total_unrealized=Sum('unrealized_pnl'),
        active_count=Count('id')
    )

    # Calculate totals
    total_realized = realized_stats['total_realized'] or Decimal('0.00')
    total_unrealized = unrealized_stats['total_unrealized'] or Decimal('0.00')
    total_pnl = total_realized + total_unrealized

    # Get today's P&L
    today = timezone.now().date()
    todays_closed = closed_positions.filter(exit_time__date=today)
    todays_realized = todays_closed.aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0.00')
    todays_pnl = todays_realized + total_unrealized

    # Calculate win rate
    winning_trades = closed_positions.filter(realized_pnl__gt=0).count()
    losing_trades = closed_positions.filter(realized_pnl__lt=0).count()
    total_trades = winning_trades + losing_trades
    win_rate = (Decimal(winning_trades) / Decimal(total_trades) * 100) if total_trades > 0 else Decimal('0.00')

    return {
        'account_name': account.account_name,
        'broker': account.broker,
        'total_pnl': total_pnl,
        'realized_pnl': total_realized,
        'unrealized_pnl': total_unrealized,
        'todays_pnl': todays_pnl,
        'todays_realized': todays_realized,
        'active_positions_count': unrealized_stats['active_count'] or 0,
        'closed_positions_count': realized_stats['closed_count'] or 0,
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'win_rate': win_rate,
        'allocated_capital': account.allocated_capital,
        'available_capital': account.get_available_capital() if hasattr(account, 'get_available_capital') else Decimal('0.00'),
    }


def get_position_level_pnl(account, status=None) -> List[Dict[str, Any]]:
    """
    Get position-level P&L details

    Args:
        account: BrokerAccount instance
        status: Optional filter by status (ACTIVE or CLOSED)

    Returns:
        list: List of position P&L details
    """
    from apps.positions.models import Position

    positions = Position.objects.filter(account=account)

    if status:
        positions = positions.filter(status=status)

    position_list = []
    for pos in positions.select_related('account'):
        pnl = pos.unrealized_pnl if pos.status == 'ACTIVE' else pos.realized_pnl
        pnl_pct = (pnl / pos.entry_value * 100) if pos.entry_value > 0 else Decimal('0.00')

        position_list.append({
            'id': pos.id,
            'instrument': pos.instrument,
            'strategy_type': pos.strategy_type,
            'direction': pos.direction,
            'status': pos.status,
            'quantity': pos.quantity,
            'lot_size': pos.lot_size,
            'entry_price': pos.entry_price,
            'current_price': pos.current_price if pos.status == 'ACTIVE' else pos.exit_price,
            'exit_price': pos.exit_price,
            'stop_loss': pos.stop_loss,
            'target': pos.target,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'entry_time': pos.entry_time,
            'exit_time': pos.exit_time,
            'exit_reason': pos.exit_reason,
            'margin_used': pos.margin_used,
        })

    return position_list


def get_strategy_level_pnl(account) -> List[Dict[str, Any]]:
    """
    Get P&L aggregated by strategy type

    Args:
        account: BrokerAccount instance

    Returns:
        list: List of strategy P&L summaries
    """
    from apps.positions.models import Position
    from apps.core.constants import POSITION_STATUS_CLOSED, POSITION_STATUS_ACTIVE

    # Get all unique strategy types
    strategies = Position.objects.filter(
        account=account
    ).values('strategy_type').distinct()

    strategy_list = []

    for strategy in strategies:
        strategy_type = strategy['strategy_type']

        # Closed positions stats
        closed = Position.objects.filter(
            account=account,
            strategy_type=strategy_type,
            status=POSITION_STATUS_CLOSED
        )

        closed_stats = closed.aggregate(
            total_realized=Sum('realized_pnl'),
            count=Count('id'),
            winning=Count('id', filter=Q(realized_pnl__gt=0)),
            losing=Count('id', filter=Q(realized_pnl__lt=0))
        )

        # Active positions stats
        active = Position.objects.filter(
            account=account,
            strategy_type=strategy_type,
            status=POSITION_STATUS_ACTIVE
        )

        active_stats = active.aggregate(
            total_unrealized=Sum('unrealized_pnl'),
            count=Count('id')
        )

        total_realized = closed_stats['total_realized'] or Decimal('0.00')
        total_unrealized = active_stats['total_unrealized'] or Decimal('0.00')
        total_pnl = total_realized + total_unrealized

        total_trades = closed_stats['count'] or 0
        winning_trades = closed_stats['winning'] or 0
        losing_trades = closed_stats['losing'] or 0
        win_rate = (Decimal(winning_trades) / Decimal(total_trades) * 100) if total_trades > 0 else Decimal('0.00')

        strategy_list.append({
            'strategy_type': strategy_type,
            'total_pnl': total_pnl,
            'realized_pnl': total_realized,
            'unrealized_pnl': total_unrealized,
            'active_positions': active_stats['count'] or 0,
            'closed_positions': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
        })

    # Sort by total P&L descending
    strategy_list.sort(key=lambda x: x['total_pnl'], reverse=True)

    return strategy_list


def get_daily_pnl_summary(account, days=30) -> List[Dict[str, Any]]:
    """
    Get daily P&L summary for the last N days

    Args:
        account: BrokerAccount instance
        days: Number of days to retrieve (default 30)

    Returns:
        list: List of daily P&L summaries
    """
    from apps.analytics.models import DailyPnL

    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)

    daily_pnls = DailyPnL.objects.filter(
        account=account,
        date__gte=start_date,
        date__lte=end_date
    ).order_by('-date')

    daily_list = []
    for dpnl in daily_pnls:
        daily_list.append({
            'date': dpnl.date.isoformat(),
            'realized_pnl': dpnl.realized_pnl,
            'unrealized_pnl': dpnl.unrealized_pnl,
            'total_pnl': dpnl.total_pnl,
            'trades_count': dpnl.trades_count,
            'winning_trades': dpnl.winning_trades,
            'losing_trades': dpnl.losing_trades,
            'win_rate': dpnl.calculate_win_rate(),
        })

    return daily_list


def get_weekly_pnl_summary(account, weeks=12) -> List[Dict[str, Any]]:
    """
    Get weekly P&L summary

    Args:
        account: BrokerAccount instance
        weeks: Number of weeks to retrieve (default 12)

    Returns:
        list: List of weekly P&L summaries
    """
    from apps.analytics.models import Performance

    end_date = timezone.now().date()
    start_date = end_date - timedelta(weeks=weeks)

    weekly_perfs = Performance.objects.filter(
        account=account,
        period_type='WEEKLY',
        period_end__gte=start_date,
        period_end__lte=end_date
    ).order_by('-period_end')

    weekly_list = []
    for perf in weekly_perfs:
        weekly_list.append({
            'period_start': perf.period_start.isoformat(),
            'period_end': perf.period_end.isoformat(),
            'total_pnl': perf.total_pnl,
            'total_trades': perf.total_trades,
            'winning_trades': perf.winning_trades,
            'losing_trades': perf.losing_trades,
            'win_rate': perf.win_rate,
            'profit_factor': perf.profit_factor,
            'sharpe_ratio': perf.sharpe_ratio,
        })

    return weekly_list


def get_monthly_pnl_summary(account, months=12) -> List[Dict[str, Any]]:
    """
    Get monthly P&L summary

    Args:
        account: BrokerAccount instance
        months: Number of months to retrieve (default 12)

    Returns:
        list: List of monthly P&L summaries
    """
    from apps.analytics.models import Performance

    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=months * 30)  # Approximate

    monthly_perfs = Performance.objects.filter(
        account=account,
        period_type='MONTHLY',
        period_end__gte=start_date,
        period_end__lte=end_date
    ).order_by('-period_end')

    monthly_list = []
    for perf in monthly_perfs:
        monthly_list.append({
            'period_start': perf.period_start.isoformat(),
            'period_end': perf.period_end.isoformat(),
            'total_pnl': perf.total_pnl,
            'total_trades': perf.total_trades,
            'winning_trades': perf.winning_trades,
            'losing_trades': perf.losing_trades,
            'win_rate': perf.win_rate,
            'profit_factor': perf.profit_factor,
            'sharpe_ratio': perf.sharpe_ratio,
        })

    return monthly_list


def get_comprehensive_pnl_data(account) -> Dict[str, Any]:
    """
    Get all P&L data in one comprehensive dictionary

    Args:
        account: BrokerAccount instance

    Returns:
        dict: Comprehensive P&L data at all levels
    """
    return {
        'account_summary': get_account_pnl_summary(account),
        'active_positions': get_position_level_pnl(account, status='ACTIVE'),
        'recent_closed_positions': get_position_level_pnl(account, status='CLOSED')[:10],  # Last 10
        'strategy_summary': get_strategy_level_pnl(account),
        'daily_pnl': get_daily_pnl_summary(account, days=30),
        'weekly_pnl': get_weekly_pnl_summary(account, weeks=12),
        'monthly_pnl': get_monthly_pnl_summary(account, months=12),
    }
