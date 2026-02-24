"""
Financial Year Analytics Service

Computes and manages financial year performance summaries for trading.
Handles FY date calculations (April 1 - March 31) and aggregates
trade statistics for reporting.
"""

import logging
from datetime import date
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Count, Avg, Max, Min, Q

from apps.analytics.models import FinancialYearSummary
from apps.trading.models import TakenTrade

logger = logging.getLogger(__name__)

# Month name mapping for monthly breakdown
MONTH_NAMES = ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
               'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar']

# Month to FY month index mapping (Apr=0, Mar=11)
MONTH_TO_FY_INDEX = {
    4: 0, 5: 1, 6: 2, 7: 3, 8: 4, 9: 5,
    10: 6, 11: 7, 12: 8, 1: 9, 2: 10, 3: 11
}


class FYAnalyticsService:
    """
    Service for computing financial year analytics.

    Provides methods for:
    - Computing/updating FY summaries
    - Generating FY reports for dashboard display
    - Monthly P&L breakdowns
    - Strategy-wise performance analysis
    """

    @staticmethod
    def get_fy_dates(fy_year):
        """
        Get FY start and end dates for a given FY year.

        Args:
            fy_year: Start year of FY (e.g., 2024 for FY2024-25)

        Returns:
            Tuple: (fy_start: date, fy_end: date, fy_label: str)

        Example:
            >>> FYAnalyticsService.get_fy_dates(2024)
            (date(2024, 4, 1), date(2025, 3, 31), 'FY2024-25')
        """
        fy_start = date(fy_year, 4, 1)  # April 1
        fy_end = date(fy_year + 1, 3, 31)  # March 31
        fy_label = f"FY{fy_year}-{str(fy_year + 1)[-2:]}"
        return fy_start, fy_end, fy_label

    @staticmethod
    def get_current_fy_year():
        """
        Get the current financial year's start year.

        Returns:
            int: FY start year (e.g., 2024 if current date is in FY2024-25)
        """
        today = date.today()
        if today.month >= 4:  # April onwards is current FY
            return today.year
        else:  # Jan-Mar belongs to previous FY
            return today.year - 1

    @staticmethod
    def get_fy_for_date(target_date):
        """
        Get the FY year for a specific date.

        Args:
            target_date: date object

        Returns:
            int: FY start year
        """
        if target_date.month >= 4:
            return target_date.year
        return target_date.year - 1

    @staticmethod
    @transaction.atomic
    def compute_fy_summary(user, fy_year, account=None, strategy='', trade_type=''):
        """
        Compute or update FY summary with all metrics.

        Uses update_or_create pattern to ensure unique constraints are respected.

        Args:
            user: User instance
            fy_year: Start year of FY (e.g., 2024)
            account: Optional BrokerAccount filter
            strategy: Optional strategy filter (e.g., 'kotak_strangle')
            trade_type: Optional trade type filter ('OPTIONS' or 'FUTURES')

        Returns:
            FinancialYearSummary: The computed/updated summary
        """
        fy_start, fy_end, fy_label = FYAnalyticsService.get_fy_dates(fy_year)

        logger.info(f"Computing FY summary for {user.username}: {fy_label}, "
                   f"account={account}, strategy={strategy or 'all'}, type={trade_type or 'all'}")

        # Build base queryset for closed trades in FY
        trades = TakenTrade.objects.filter(
            user=user,
            status='CLOSED',
            closed_at__date__gte=fy_start,
            closed_at__date__lte=fy_end
        )

        if account:
            trades = trades.filter(account=account)
        if strategy:
            trades = trades.filter(strategy=strategy)
        if trade_type:
            trades = trades.filter(trade_type=trade_type)

        # Aggregate base statistics
        stats = trades.aggregate(
            total_trades=Count('id'),
            winning_trades=Count('id', filter=Q(outcome='PROFIT')),
            losing_trades=Count('id', filter=Q(outcome='LOSS')),
            breakeven_trades=Count('id', filter=Q(outcome='BREAKEVEN')),
            gross_profit=Sum('net_pnl', filter=Q(net_pnl__gt=0)),
            gross_loss=Sum('net_pnl', filter=Q(net_pnl__lt=0)),
            total_charges=Sum('charges'),
            largest_win=Max('net_pnl', filter=Q(net_pnl__gt=0)),
            largest_loss=Min('net_pnl', filter=Q(net_pnl__lt=0)),
            avg_margin_used=Avg('margin_used'),
            avg_rom=Avg('return_on_margin'),
        )

        # Calculate derived metrics
        total_trades = stats['total_trades'] or 0
        winning_trades = stats['winning_trades'] or 0
        losing_trades = stats['losing_trades'] or 0
        gross_profit = stats['gross_profit'] or Decimal('0.00')
        gross_loss = abs(stats['gross_loss'] or Decimal('0.00'))
        net_pnl = gross_profit - gross_loss

        # Win rate
        win_rate = Decimal('0.00')
        if total_trades > 0:
            win_rate = Decimal(winning_trades) / Decimal(total_trades) * 100

        # Profit factor
        profit_factor = Decimal('0.00')
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss

        # Average win/loss
        average_win = Decimal('0.00')
        average_loss = Decimal('0.00')
        if winning_trades > 0:
            average_win = gross_profit / winning_trades
        if losing_trades > 0:
            average_loss = gross_loss / losing_trades

        # Compute monthly breakdown
        monthly_pnl = FYAnalyticsService._compute_monthly_breakdown(trades, fy_year)

        # Find best/worst months
        best_month = ''
        best_month_pnl = None
        worst_month = ''
        worst_month_pnl = None

        for month, pnl in monthly_pnl.items():
            pnl_val = Decimal(str(pnl))
            if best_month_pnl is None or pnl_val > best_month_pnl:
                best_month = month
                best_month_pnl = pnl_val
            if worst_month_pnl is None or pnl_val < worst_month_pnl:
                worst_month = month
                worst_month_pnl = pnl_val

        # Compute drawdown
        max_drawdown, max_drawdown_pct = FYAnalyticsService._compute_drawdown(trades)

        # Get latest trade timestamp
        latest_trade = trades.order_by('-closed_at').first()
        trades_included_until = latest_trade.closed_at if latest_trade else None

        # Compute average trade duration
        avg_duration = FYAnalyticsService._compute_avg_duration(trades)

        # Create or update summary
        summary, created = FinancialYearSummary.objects.update_or_create(
            user=user,
            account=account,
            fy_start=fy_start,
            strategy=strategy,
            trade_type=trade_type,
            defaults={
                'fy_end': fy_end,
                'fy_label': fy_label,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'breakeven_trades': stats['breakeven_trades'] or 0,
                'gross_profit': gross_profit,
                'gross_loss': gross_loss,
                'net_pnl': net_pnl,
                'total_charges': stats['total_charges'] or Decimal('0.00'),
                'win_rate': round(win_rate, 2),
                'profit_factor': round(profit_factor, 2),
                'average_win': round(average_win, 2),
                'average_loss': round(average_loss, 2),
                'largest_win': stats['largest_win'] or Decimal('0.00'),
                'largest_loss': abs(stats['largest_loss'] or Decimal('0.00')),
                'max_drawdown': max_drawdown,
                'max_drawdown_pct': max_drawdown_pct,
                'monthly_pnl': monthly_pnl,
                'best_month': best_month,
                'best_month_pnl': best_month_pnl,
                'worst_month': worst_month,
                'worst_month_pnl': worst_month_pnl,
                'avg_trade_duration_hours': avg_duration,
                'avg_margin_used': stats['avg_margin_used'],
                'avg_return_on_margin': stats['avg_rom'],
                'trades_included_until': trades_included_until,
            }
        )

        action = 'Created' if created else 'Updated'
        logger.info(f"{action} FY summary for {user.username}: {fy_label} - "
                   f"{total_trades} trades, Net P&L: {net_pnl}")

        return summary

    @staticmethod
    def _compute_monthly_breakdown(trades, fy_year):
        """
        Compute monthly P&L breakdown for FY.

        Returns:
            dict: {'Apr': 1000, 'May': -500, ...}
        """
        monthly_pnl = {month: 0.0 for month in MONTH_NAMES}

        # Get monthly aggregates
        for trade in trades:
            if trade.closed_at and trade.net_pnl:
                month_num = trade.closed_at.month
                month_name = MONTH_NAMES[MONTH_TO_FY_INDEX[month_num]]
                monthly_pnl[month_name] += float(trade.net_pnl)

        return monthly_pnl

    @staticmethod
    def _compute_drawdown(trades):
        """
        Compute maximum drawdown from trade sequence.

        Returns:
            Tuple: (max_drawdown: Decimal, max_drawdown_pct: Decimal)
        """
        # Order trades by close date
        ordered_trades = trades.order_by('closed_at')

        cumulative_pnl = Decimal('0.00')
        peak_pnl = Decimal('0.00')
        max_drawdown = Decimal('0.00')

        for trade in ordered_trades:
            if trade.net_pnl:
                cumulative_pnl += trade.net_pnl

                if cumulative_pnl > peak_pnl:
                    peak_pnl = cumulative_pnl

                drawdown = peak_pnl - cumulative_pnl
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

        # Calculate drawdown percentage relative to peak
        max_drawdown_pct = Decimal('0.00')
        if peak_pnl > 0:
            max_drawdown_pct = (max_drawdown / peak_pnl) * 100

        return round(max_drawdown, 2), round(max_drawdown_pct, 2)

    @staticmethod
    def _compute_avg_duration(trades):
        """
        Compute average trade duration in hours.

        Returns:
            Decimal or None: Average duration in hours
        """
        total_duration = 0
        count = 0

        for trade in trades:
            if trade.taken_at and trade.closed_at:
                duration = trade.closed_at - trade.taken_at
                total_duration += duration.total_seconds() / 3600  # Convert to hours
                count += 1

        if count > 0:
            return Decimal(str(round(total_duration / count, 2)))
        return None

    @staticmethod
    def get_fy_report(user, fy_year=None, account=None):
        """
        Get FY report dict for dashboard display.

        If summary doesn't exist, computes it first.

        Args:
            user: User instance
            fy_year: FY start year (default: current FY)
            account: Optional account filter

        Returns:
            dict: Complete FY report with all metrics
        """
        if fy_year is None:
            fy_year = FYAnalyticsService.get_current_fy_year()

        fy_start, fy_end, fy_label = FYAnalyticsService.get_fy_dates(fy_year)

        # Try to get existing summary
        summary = FinancialYearSummary.objects.filter(
            user=user,
            account=account,
            fy_start=fy_start,
            strategy='',  # Overall summary
            trade_type=''  # All types
        ).first()

        # Compute if not exists or stale (older than 1 hour)
        from django.utils import timezone
        if not summary or (timezone.now() - summary.last_computed_at).seconds > 3600:
            summary = FYAnalyticsService.compute_fy_summary(
                user=user,
                fy_year=fy_year,
                account=account
            )

        # Build report dict
        report = summary.get_summary_dict()

        # Add chart data
        report['chart_data'] = summary.get_monthly_chart_data()

        # Add strategy breakdown
        report['strategy_breakdown'] = FYAnalyticsService.get_strategy_breakdown(
            user, fy_year, account
        )

        # Add active trades count
        from apps.trading.services.trade_action_service import TradeActionService
        active_trades = TradeActionService.get_active_trades(user=user, account=account)
        report['active_trades_count'] = active_trades.count()

        return report

    @staticmethod
    def get_strategy_breakdown(user, fy_year, account=None):
        """
        Get P&L breakdown by strategy for FY.

        Returns:
            list: [{
                'strategy': str,
                'display_name': str,
                'total_trades': int,
                'net_pnl': float,
                'win_rate': float
            }, ...]
        """

        fy_start, fy_end, _ = FYAnalyticsService.get_fy_dates(fy_year)

        strategies = [
            ('kotak_strangle', 'Kotak Strangle'),
            ('kotak_broken_iron_condor', 'Kotak Iron Condor'),
            ('icici_futures', 'ICICI Futures'),
        ]

        breakdown = []

        for strategy_code, display_name in strategies:
            trades = TakenTrade.objects.filter(
                user=user,
                status='CLOSED',
                strategy=strategy_code,
                closed_at__date__gte=fy_start,
                closed_at__date__lte=fy_end
            )

            if account:
                trades = trades.filter(account=account)

            stats = trades.aggregate(
                total_trades=Count('id'),
                winning_trades=Count('id', filter=Q(outcome='PROFIT')),
                net_pnl=Sum('net_pnl'),
            )

            total = stats['total_trades'] or 0
            wins = stats['winning_trades'] or 0
            win_rate = (wins / total * 100) if total > 0 else 0

            breakdown.append({
                'strategy': strategy_code,
                'display_name': display_name,
                'total_trades': total,
                'net_pnl': float(stats['net_pnl'] or 0),
                'win_rate': round(win_rate, 1),
            })

        return breakdown

    @staticmethod
    def get_available_fy_years(user):
        """
        Get list of FY years that have data for a user.

        Returns:
            list: [2024, 2023, ...] sorted descending
        """
        # Get distinct years from closed trades
        trades = TakenTrade.objects.filter(
            user=user,
            status='CLOSED',
            closed_at__isnull=False
        ).values_list('closed_at', flat=True)

        fy_years = set()
        for closed_at in trades:
            if closed_at:
                fy_years.add(FYAnalyticsService.get_fy_for_date(closed_at.date()))

        # Always include current FY
        fy_years.add(FYAnalyticsService.get_current_fy_year())

        return sorted(fy_years, reverse=True)

    @staticmethod
    def refresh_all_summaries(user):
        """
        Refresh all FY summaries for a user.

        Useful for batch updates after data corrections.

        Args:
            user: User instance

        Returns:
            int: Number of summaries refreshed
        """
        fy_years = FYAnalyticsService.get_available_fy_years(user)
        count = 0

        for fy_year in fy_years:
            try:
                FYAnalyticsService.compute_fy_summary(user, fy_year)
                count += 1
            except Exception as e:
                logger.error(f"Error refreshing FY{fy_year} summary for {user}: {e}")

        logger.info(f"Refreshed {count} FY summaries for {user.username}")
        return count
