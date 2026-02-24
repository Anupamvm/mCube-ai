"""
Broker Analytics Service

Computes financial year performance from BrokerContractPnL data.
Uses aggregated contract-level P&L from broker CSV imports.
"""

import logging
from datetime import date
from decimal import Decimal
from django.db.models import Sum, Count, Q, Max

from apps.brokers.models import BrokerContractPnL

logger = logging.getLogger(__name__)

# Month name mapping for monthly breakdown
MONTH_NAMES = ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
               'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar']


class BrokerAnalyticsService:
    """
    Service for computing FY analytics from broker contract P&L data.

    Uses BrokerContractPnL model which contains aggregated P&L per contract
    imported from broker CSV statements.
    """

    @staticmethod
    def get_fy_label(fy_year):
        """
        Get FY label for display.

        Args:
            fy_year: Start year of FY (e.g., 2024)

        Returns:
            str: FY label like 'FY2024-25' or '2024-25'
        """
        return f"{fy_year}-{str(fy_year + 1)[-2:]}"

    @staticmethod
    def get_fy_dates(fy_year):
        """
        Get FY start and end dates.

        Args:
            fy_year: Start year of FY (e.g., 2024)

        Returns:
            Tuple: (fy_start: date, fy_end: date, fy_label: str)
        """
        fy_start = date(fy_year, 4, 1)
        fy_end = date(fy_year + 1, 3, 31)
        fy_label = f"FY{fy_year}-{str(fy_year + 1)[-2:]}"
        return fy_start, fy_end, fy_label

    @staticmethod
    def get_current_fy_year():
        """Get current FY start year."""
        today = date.today()
        if today.month >= 4:
            return today.year
        return today.year - 1

    @staticmethod
    def get_available_fy_years():
        """
        Get list of FY years that have data.

        Returns:
            list: [2024, 2023, ...] sorted descending
        """
        # Get distinct FY values from BrokerContractPnL
        fy_values = BrokerContractPnL.objects.values_list('fy', flat=True).distinct()

        fy_years = set()
        for fy in fy_values:
            if fy and '-' in fy:
                try:
                    # Parse '2024-25' format
                    start_year = int(fy.split('-')[0])
                    fy_years.add(start_year)
                except ValueError:
                    continue

        # Always include current FY
        fy_years.add(BrokerAnalyticsService.get_current_fy_year())

        return sorted(fy_years, reverse=True)

    @staticmethod
    def get_fy_report(fy_year=None, broker=None, segment=None):
        """
        Get FY performance report from broker contract P&L data.

        Args:
            fy_year: FY start year (default: current FY)
            broker: Optional broker filter ('KOTAK', 'ICICI')
            segment: Optional segment filter ('OPTIONS', 'FUTURES')

        Returns:
            dict: Complete FY report with all metrics
        """
        if fy_year is None:
            fy_year = BrokerAnalyticsService.get_current_fy_year()

        fy_label = BrokerAnalyticsService.get_fy_label(fy_year)
        fy_start, fy_end, _ = BrokerAnalyticsService.get_fy_dates(fy_year)

        # Build queryset
        contracts = BrokerContractPnL.objects.filter(fy=fy_label)

        if broker:
            contracts = contracts.filter(broker=broker)
        if segment:
            contracts = contracts.filter(segment=segment)

        # Aggregate statistics
        stats = contracts.aggregate(
            total_trades=Count('id'),
            winning_trades=Count('id', filter=Q(net_pnl__gt=0)),
            losing_trades=Count('id', filter=Q(net_pnl__lt=0)),
            breakeven_trades=Count('id', filter=Q(net_pnl=0)),
            gross_profit=Sum('net_pnl', filter=Q(net_pnl__gt=0)),
            gross_loss=Sum('net_pnl', filter=Q(net_pnl__lt=0)),
            total_charges=Sum('total_charges'),
            largest_win=Max('net_pnl', filter=Q(net_pnl__gt=0)),
            largest_loss=Min('net_pnl', filter=Q(net_pnl__lt=0)),
        )

        # Calculate derived metrics
        total_trades = stats['total_trades'] or 0
        winning_trades = stats['winning_trades'] or 0
        losing_trades = stats['losing_trades'] or 0
        gross_profit = stats['gross_profit'] or Decimal('0.00')
        gross_loss = abs(stats['gross_loss'] or Decimal('0.00'))
        net_pnl = gross_profit - gross_loss
        total_charges = stats['total_charges'] or Decimal('0.00')

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

        # Segment breakdown
        segment_breakdown = BrokerAnalyticsService._get_segment_breakdown(contracts)

        # Symbol breakdown (top performers)
        symbol_breakdown = BrokerAnalyticsService._get_symbol_breakdown(contracts)

        # Monthly breakdown (if expiry dates available)
        monthly_pnl = BrokerAnalyticsService._get_monthly_breakdown(contracts)

        # Find best/worst months
        best_month = ''
        best_month_pnl = 0.0
        worst_month = ''
        worst_month_pnl = 0.0

        for month, pnl in monthly_pnl.items():
            if pnl > best_month_pnl or not best_month:
                best_month = month
                best_month_pnl = pnl
            if pnl < worst_month_pnl or not worst_month:
                worst_month = month
                worst_month_pnl = pnl

        # Chart data (use 'data' key for template compatibility)
        chart_data = {
            'labels': MONTH_NAMES,
            'data': [float(monthly_pnl.get(m, 0)) for m in MONTH_NAMES]
        }

        # Calculate max drawdown (simplified - based on monthly P&L)
        max_drawdown, max_drawdown_pct = BrokerAnalyticsService._calculate_drawdown(monthly_pnl)

        return {
            'fy_label': f"FY{fy_label}",
            'fy_year': fy_year,
            'fy_start': fy_start.isoformat(),
            'fy_end': fy_end.isoformat(),
            # Core metrics
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'breakeven_trades': stats['breakeven_trades'] or 0,
            # P&L
            'gross_profit': float(gross_profit),
            'gross_loss': float(gross_loss),
            'net_pnl': float(net_pnl),
            'total_charges': float(total_charges),
            # Ratios
            'win_rate': float(round(win_rate, 2)),
            'profit_factor': float(round(profit_factor, 2)),
            'average_win': float(round(average_win, 2)),
            'average_loss': float(round(average_loss, 2)),
            # Extremes
            'largest_win': float(stats['largest_win'] or 0),
            'largest_loss': float(abs(stats['largest_loss'] or 0)),
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            # Best/Worst months
            'best_month': best_month,
            'best_month_pnl': best_month_pnl,
            'worst_month': worst_month,
            'worst_month_pnl': worst_month_pnl,
            # Breakdowns
            'segment_breakdown': segment_breakdown,
            'symbol_breakdown': symbol_breakdown,
            'strategy_breakdown': segment_breakdown,  # Alias for template compatibility
            'monthly_pnl': monthly_pnl,
            'chart_data': chart_data,
            # For template compatibility
            'active_trades_count': 0,
        }

    @staticmethod
    def _get_segment_breakdown(contracts):
        """Get P&L breakdown by segment (OPTIONS, FUTURES, etc)."""
        segments = contracts.values('segment').annotate(
            total_trades=Count('id'),
            winning_trades=Count('id', filter=Q(net_pnl__gt=0)),
            net_pnl=Sum('net_pnl'),
        ).order_by('-net_pnl')

        breakdown = []
        for seg in segments:
            total = seg['total_trades'] or 0
            wins = seg['winning_trades'] or 0
            win_rate = (wins / total * 100) if total > 0 else 0

            # Map segment to display name
            segment_names = {
                'OPTIONS': 'Options',
                'FUTURES': 'Futures',
                'EQUITY': 'Equity',
                'MUTUAL_FUND': 'Mutual Funds',
                'ETF': 'ETFs',
            }

            breakdown.append({
                'strategy': seg['segment'],
                'display_name': segment_names.get(seg['segment'], seg['segment']),
                'total_trades': total,
                'net_pnl': float(seg['net_pnl'] or 0),
                'win_rate': round(win_rate, 1),
            })

        return breakdown

    @staticmethod
    def _get_symbol_breakdown(contracts, limit=10):
        """Get top symbols by P&L."""
        symbols = contracts.values('symbol').annotate(
            total_trades=Count('id'),
            net_pnl=Sum('net_pnl'),
        ).order_by('-net_pnl')[:limit]

        return [
            {
                'symbol': s['symbol'],
                'total_trades': s['total_trades'],
                'net_pnl': float(s['net_pnl'] or 0),
            }
            for s in symbols
        ]

    @staticmethod
    def _get_monthly_breakdown(contracts):
        """
        Get monthly P&L breakdown based on expiry dates.

        Returns:
            dict: {'Apr': 1000.0, 'May': -500.0, ...}
        """
        monthly_pnl = {month: 0.0 for month in MONTH_NAMES}

        # Month to FY month index mapping
        month_to_fy_index = {
            4: 0, 5: 1, 6: 2, 7: 3, 8: 4, 9: 5,
            10: 6, 11: 7, 12: 8, 1: 9, 2: 10, 3: 11
        }

        # Aggregate by expiry month
        for contract in contracts.filter(expiry_date__isnull=False):
            if contract.expiry_date and contract.net_pnl:
                month_num = contract.expiry_date.month
                month_name = MONTH_NAMES[month_to_fy_index[month_num]]
                monthly_pnl[month_name] += float(contract.net_pnl)

        return monthly_pnl

    @staticmethod
    def _calculate_drawdown(monthly_pnl):
        """
        Calculate max drawdown from monthly P&L data.

        Returns:
            Tuple: (max_drawdown: float, max_drawdown_pct: float)
        """
        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0

        for month in MONTH_NAMES:
            pnl = monthly_pnl.get(month, 0.0)
            cumulative += pnl

            if cumulative > peak:
                peak = cumulative

            drawdown = peak - cumulative
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Calculate percentage
        max_drawdown_pct = 0.0
        if peak > 0:
            max_drawdown_pct = (max_drawdown / peak) * 100

        return round(max_drawdown, 2), round(max_drawdown_pct, 2)

    @staticmethod
    def get_broker_summary(fy_year=None):
        """
        Get summary by broker for comparison.

        Returns:
            dict: {'KOTAK': {...}, 'ICICI': {...}}
        """
        if fy_year is None:
            fy_year = BrokerAnalyticsService.get_current_fy_year()

        fy_label = BrokerAnalyticsService.get_fy_label(fy_year)

        brokers = BrokerContractPnL.objects.filter(fy=fy_label).values('broker').annotate(
            total_trades=Count('id'),
            net_pnl=Sum('net_pnl'),
            total_charges=Sum('total_charges'),
        )

        return {
            b['broker']: {
                'total_trades': b['total_trades'],
                'net_pnl': float(b['net_pnl'] or 0),
                'total_charges': float(b['total_charges'] or 0),
            }
            for b in brokers
        }
