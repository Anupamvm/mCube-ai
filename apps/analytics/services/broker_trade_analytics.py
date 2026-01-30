"""
Broker Trade Analytics Service

Calculates performance metrics directly from BrokerTradeHistory records
(synced from broker APIs) rather than internal Position/TakenTrade records.

This provides the authoritative view of actual broker performance.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.db.models import Sum, Count, Avg, Q, F
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth

from apps.accounts.models import BrokerAccount
from apps.brokers.models import BrokerTradeHistory

logger = logging.getLogger(__name__)


class BrokerTradeAnalytics:
    """
    Analytics service that calculates metrics from actual broker trade data.
    """

    def get_trade_summary(
        self,
        account: Optional[BrokerAccount] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Dict:
        """
        Get summary metrics from broker trade history.

        Args:
            account: Filter by specific account (None for all)
            from_date: Start date filter
            to_date: End date filter

        Returns:
            Dict with summary metrics
        """
        queryset = BrokerTradeHistory.objects.all()

        if account:
            queryset = queryset.filter(account=account)

        if from_date:
            queryset = queryset.filter(trade_date__gte=from_date)

        if to_date:
            queryset = queryset.filter(trade_date__lte=to_date)

        # Get basic counts
        total_trades = queryset.count()
        buy_trades = queryset.filter(trade_type='BUY').count()
        sell_trades = queryset.filter(trade_type='SELL').count()

        # Calculate total value traded
        buy_value = queryset.filter(trade_type='BUY').aggregate(
            total=Sum(F('quantity') * F('price'))
        )['total'] or Decimal('0')

        sell_value = queryset.filter(trade_type='SELL').aggregate(
            total=Sum(F('quantity') * F('price'))
        )['total'] or Decimal('0')

        # Get unique trading days
        trading_days = queryset.values('trade_date').distinct().count()

        # Get segment breakdown
        segment_breakdown = queryset.values('segment').annotate(
            count=Count('id'),
            value=Sum(F('quantity') * F('price'))
        )

        return {
            'total_trades': total_trades,
            'buy_trades': buy_trades,
            'sell_trades': sell_trades,
            'buy_value': float(buy_value),
            'sell_value': float(sell_value),
            'total_value': float(buy_value + sell_value),
            'net_value': float(sell_value - buy_value),
            'trading_days': trading_days,
            'avg_trades_per_day': round(total_trades / trading_days, 2) if trading_days > 0 else 0,
            'segment_breakdown': list(segment_breakdown),
        }

    def get_daily_pnl(
        self,
        account: Optional[BrokerAccount] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict]:
        """
        Calculate daily P&L from matched buy/sell trades.

        This is a simplified calculation that pairs buys and sells
        for the same symbol on the same day.

        Returns:
            List of daily P&L records
        """
        queryset = BrokerTradeHistory.objects.all()

        if account:
            queryset = queryset.filter(account=account)

        if from_date:
            queryset = queryset.filter(trade_date__gte=from_date)

        if to_date:
            queryset = queryset.filter(trade_date__lte=to_date)

        # Group by date and calculate net P&L
        daily_data = queryset.annotate(
            date=TruncDate('trade_date')
        ).values('date').annotate(
            buy_value=Sum(
                F('quantity') * F('price'),
                filter=Q(trade_type='BUY')
            ),
            sell_value=Sum(
                F('quantity') * F('price'),
                filter=Q(trade_type='SELL')
            ),
            trade_count=Count('id'),
        ).order_by('date')

        results = []
        for day in daily_data:
            buy_val = day['buy_value'] or Decimal('0')
            sell_val = day['sell_value'] or Decimal('0')

            # Simple P&L calculation: sell value - buy value
            # This works for intraday/closed positions
            pnl = sell_val - buy_val

            results.append({
                'date': day['date'],
                'buy_value': float(buy_val),
                'sell_value': float(sell_val),
                'pnl': float(pnl),
                'trade_count': day['trade_count'],
            })

        return results

    def get_symbol_performance(
        self,
        account: Optional[BrokerAccount] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """
        Get performance breakdown by trading symbol.

        Returns:
            List of symbol performance records
        """
        queryset = BrokerTradeHistory.objects.all()

        if account:
            queryset = queryset.filter(account=account)

        if from_date:
            queryset = queryset.filter(trade_date__gte=from_date)

        if to_date:
            queryset = queryset.filter(trade_date__lte=to_date)

        symbol_data = queryset.values('symbol').annotate(
            trade_count=Count('id'),
            buy_value=Sum(
                F('quantity') * F('price'),
                filter=Q(trade_type='BUY')
            ),
            sell_value=Sum(
                F('quantity') * F('price'),
                filter=Q(trade_type='SELL')
            ),
            buy_qty=Sum('quantity', filter=Q(trade_type='BUY')),
            sell_qty=Sum('quantity', filter=Q(trade_type='SELL')),
        ).order_by('-trade_count')[:limit]

        results = []
        for item in symbol_data:
            buy_val = item['buy_value'] or Decimal('0')
            sell_val = item['sell_value'] or Decimal('0')
            buy_qty = item['buy_qty'] or 0
            sell_qty = item['sell_qty'] or 0

            # Net P&L (positive = profit)
            net_pnl = sell_val - buy_val

            # Average prices
            avg_buy = buy_val / buy_qty if buy_qty > 0 else Decimal('0')
            avg_sell = sell_val / sell_qty if sell_qty > 0 else Decimal('0')

            results.append({
                'symbol': item['symbol'],
                'trade_count': item['trade_count'],
                'buy_qty': buy_qty,
                'sell_qty': sell_qty,
                'buy_value': float(buy_val),
                'sell_value': float(sell_val),
                'net_pnl': float(net_pnl),
                'avg_buy_price': float(avg_buy),
                'avg_sell_price': float(avg_sell),
            })

        return results

    def get_monthly_summary(
        self,
        account: Optional[BrokerAccount] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict]:
        """
        Get monthly trading summary.

        Returns:
            List of monthly summary records
        """
        queryset = BrokerTradeHistory.objects.all()

        if account:
            queryset = queryset.filter(account=account)

        if from_date:
            queryset = queryset.filter(trade_date__gte=from_date)

        if to_date:
            queryset = queryset.filter(trade_date__lte=to_date)

        monthly_data = queryset.annotate(
            month=TruncMonth('trade_date')
        ).values('month').annotate(
            trade_count=Count('id'),
            buy_value=Sum(
                F('quantity') * F('price'),
                filter=Q(trade_type='BUY')
            ),
            sell_value=Sum(
                F('quantity') * F('price'),
                filter=Q(trade_type='SELL')
            ),
            trading_days=Count('trade_date', distinct=True),
        ).order_by('month')

        results = []
        for item in monthly_data:
            buy_val = item['buy_value'] or Decimal('0')
            sell_val = item['sell_value'] or Decimal('0')
            net_pnl = sell_val - buy_val

            results.append({
                'month': item['month'].strftime('%Y-%m') if item['month'] else None,
                'trade_count': item['trade_count'],
                'buy_value': float(buy_val),
                'sell_value': float(sell_val),
                'net_pnl': float(net_pnl),
                'trading_days': item['trading_days'],
            })

        return results

    def get_fy_summary(
        self,
        account: Optional[BrokerAccount] = None,
        fy_year: Optional[int] = None,
    ) -> Dict:
        """
        Get financial year summary (April to March).

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
            to_date=min(fy_end, today)  # Don't go beyond today
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
        }

    def reconcile_with_positions(
        self,
        account: BrokerAccount,
    ) -> Dict:
        """
        Reconcile broker trade history with Position records.

        Returns:
            Dict with reconciliation results
        """
        from apps.brokers.services.trade_sync import TradeSyncService

        result = TradeSyncService.reconcile_with_taken_trades(account)
        return result


# Singleton instance
_analytics = None


def get_broker_analytics() -> BrokerTradeAnalytics:
    """Get singleton BrokerTradeAnalytics instance."""
    global _analytics
    if _analytics is None:
        _analytics = BrokerTradeAnalytics()
    return _analytics
