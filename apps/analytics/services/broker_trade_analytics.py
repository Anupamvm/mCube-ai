"""
Broker Trade Analytics Service

Calculates performance metrics from BrokerContractPnL records
(imported from CSV files) for accurate P&L reporting.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.db.models import Sum, Count, Avg, Q, F

from apps.accounts.models import BrokerAccount
from apps.brokers.models import BrokerContractPnL

logger = logging.getLogger(__name__)


class BrokerTradeAnalytics:
    """
    Analytics service that calculates metrics from CSV imported contract data.
    """

    def get_trade_summary(
        self,
        account: Optional[BrokerAccount] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Dict:
        """
        Get summary metrics from CSV imported contract P&L.

        Args:
            account: Filter by specific account (None for all)
            from_date: Start date filter (by expiry date)
            to_date: End date filter (by expiry date)

        Returns:
            Dict with summary metrics
        """
        queryset = BrokerContractPnL.objects.all()

        if from_date:
            queryset = queryset.filter(
                Q(expiry_date__gte=from_date) | Q(expiry_date__isnull=True)
            )

        if to_date:
            queryset = queryset.filter(
                Q(expiry_date__lte=to_date) | Q(expiry_date__isnull=True)
            )

        # Get basic counts
        total_contracts = queryset.count()

        # Aggregate P&L
        aggregates = queryset.aggregate(
            total_net_pnl=Sum('net_pnl'),
            total_gross_pnl=Sum('gross_pnl'),
            total_charges=Sum('total_charges'),
            total_buy=Sum('buy_amount'),
            total_sell=Sum('sell_amount'),
        )

        # Get segment breakdown
        segment_breakdown = queryset.values('segment').annotate(
            count=Count('id'),
            net_pnl=Sum('net_pnl'),
        )

        # Get broker breakdown
        broker_breakdown = queryset.values('broker').annotate(
            count=Count('id'),
            net_pnl=Sum('net_pnl'),
        )

        return {
            'total_contracts': total_contracts,
            'net_pnl': float(aggregates['total_net_pnl'] or 0),
            'gross_pnl': float(aggregates['total_gross_pnl'] or 0),
            'total_charges': float(aggregates['total_charges'] or 0),
            'buy_value': float(aggregates['total_buy'] or 0),
            'sell_value': float(aggregates['total_sell'] or 0),
            'segment_breakdown': list(segment_breakdown),
            'broker_breakdown': list(broker_breakdown),
            'data_source': 'csv_import',
        }

    def get_daily_pnl(
        self,
        account: Optional[BrokerAccount] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict]:
        """
        Get P&L grouped by expiry date (since CSV imports are per contract).

        Returns:
            List of P&L records grouped by expiry date
        """
        queryset = BrokerContractPnL.objects.exclude(expiry_date__isnull=True)

        if from_date:
            queryset = queryset.filter(expiry_date__gte=from_date)

        if to_date:
            queryset = queryset.filter(expiry_date__lte=to_date)

        # Group by expiry date
        daily_data = queryset.values('expiry_date').annotate(
            net_pnl=Sum('net_pnl'),
            contract_count=Count('id'),
        ).order_by('expiry_date')

        results = []
        for day in daily_data:
            results.append({
                'date': day['expiry_date'],
                'pnl': float(day['net_pnl'] or 0),
                'contract_count': day['contract_count'],
            })

        return results

    def get_symbol_performance(
        self,
        account: Optional[BrokerAccount] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        limit: int = 20,
        broker: Optional[str] = None,
    ) -> List[Dict]:
        """
        Get performance breakdown by trading symbol from CSV imports.

        Args:
            account: Filter by specific account
            from_date: Start date filter
            to_date: End date filter
            limit: Max number of symbols to return
            broker: Filter by broker ('KOTAK' or 'ICICI')

        Returns:
            List of symbol performance records
        """
        queryset = BrokerContractPnL.objects.all()

        if broker:
            queryset = queryset.filter(broker=broker)

        if from_date:
            queryset = queryset.filter(
                Q(expiry_date__gte=from_date) | Q(expiry_date__isnull=True)
            )

        if to_date:
            queryset = queryset.filter(
                Q(expiry_date__lte=to_date) | Q(expiry_date__isnull=True)
            )

        symbol_data = queryset.values('symbol').annotate(
            trade_count=Count('id'),
            net_pnl=Sum('net_pnl'),
            gross_pnl=Sum('gross_pnl'),
            total_charges=Sum('total_charges'),
            futures_pnl=Sum('net_pnl', filter=Q(segment='FUTURES')),
            options_pnl=Sum('net_pnl', filter=Q(segment='OPTIONS')),
        ).order_by('-trade_count')[:limit]

        results = []
        for item in symbol_data:
            results.append({
                'symbol': item['symbol'],
                'trade_count': item['trade_count'],
                'net_pnl': float(item['net_pnl'] or 0),
                'gross_pnl': float(item['gross_pnl'] or 0),
                'total_charges': float(item['total_charges'] or 0),
                'futures_pnl': float(item['futures_pnl'] or 0),
                'options_pnl': float(item['options_pnl'] or 0),
            })

        return results

    def get_monthly_summary(
        self,
        account: Optional[BrokerAccount] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict]:
        """
        Get monthly trading summary based on expiry months.

        Returns:
            List of monthly summary records
        """
        from django.db.models.functions import TruncMonth

        queryset = BrokerContractPnL.objects.exclude(expiry_date__isnull=True)

        if from_date:
            queryset = queryset.filter(expiry_date__gte=from_date)

        if to_date:
            queryset = queryset.filter(expiry_date__lte=to_date)

        monthly_data = queryset.annotate(
            month=TruncMonth('expiry_date')
        ).values('month').annotate(
            contract_count=Count('id'),
            net_pnl=Sum('net_pnl'),
            futures_pnl=Sum('net_pnl', filter=Q(segment='FUTURES')),
            options_pnl=Sum('net_pnl', filter=Q(segment='OPTIONS')),
        ).order_by('month')

        results = []
        for item in monthly_data:
            results.append({
                'month': item['month'].strftime('%Y-%m') if item['month'] else None,
                'contract_count': item['contract_count'],
                'net_pnl': float(item['net_pnl'] or 0),
                'futures_pnl': float(item['futures_pnl'] or 0),
                'options_pnl': float(item['options_pnl'] or 0),
            })

        return results

    def get_fy_summary(
        self,
        account: Optional[BrokerAccount] = None,
        fy_year: Optional[int] = None,
    ) -> Dict:
        """
        Get financial year summary (April to March) from CSV imports.

        Args:
            account: Filter by account
            fy_year: Financial year start year (e.g., 2024 for FY 2024-25)
                    If None, uses current FY

        Returns:
            Dict with FY summary
        """
        # Determine FY dates
        today = date.today()
        if fy_year is None:
            fy_year = today.year if today.month >= 4 else today.year - 1

        fy_start = date(fy_year, 4, 1)
        fy_end = date(fy_year + 1, 3, 31)

        # Get summary for FY
        summary = self.get_trade_summary(
            account=account,
            from_date=fy_start,
            to_date=min(fy_end, today)
        )

        # Get monthly breakdown
        monthly = self.get_monthly_summary(
            account=account,
            from_date=fy_start,
            to_date=min(fy_end, today)
        )

        # Calculate cumulative P&L
        cumulative_pnl = Decimal('0')
        monthly_with_cumulative = []
        for m in monthly:
            cumulative_pnl += Decimal(str(m['net_pnl']))
            m['cumulative_pnl'] = float(cumulative_pnl)
            monthly_with_cumulative.append(m)

        return {
            'fy_label': f"FY {fy_year}-{str(fy_year + 1)[-2:]}",
            'fy_start': fy_start.strftime('%Y-%m-%d'),
            'fy_end': fy_end.strftime('%Y-%m-%d'),
            'summary': summary,
            'monthly_breakdown': monthly_with_cumulative,
            'total_pnl': float(cumulative_pnl),
            'data_source': 'csv_import',
        }


# Singleton instance
_analytics = None


def get_broker_analytics() -> BrokerTradeAnalytics:
    """Get singleton BrokerTradeAnalytics instance."""
    global _analytics
    if _analytics is None:
        _analytics = BrokerTradeAnalytics()
    return _analytics
