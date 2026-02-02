"""
Trading Patterns Analysis Service

Analyzes trading data to discover actionable patterns for traders.
Provides insights on:
- Day of week performance
- Time-based patterns
- Symbol performance
- Holding period analysis
- Streak analysis
- Risk metrics
- Behavioral patterns
"""

import logging
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Dict, List, Optional, Any
from collections import defaultdict

from django.db import models
from django.db.models import Sum, Count, Avg, Max, Min, F, Q, Case, When, Value
from django.db.models.functions import ExtractWeekDay, ExtractHour, ExtractMonth, TruncMonth, Coalesce
from django.utils import timezone

logger = logging.getLogger(__name__)


class TradingPatternsAnalyzer:
    """
    Analyzes trading patterns from BrokerContractPnL and BrokerTradeHistory data.
    """

    def __init__(self, broker: str = None, fy: str = None, segment: str = None):
        """
        Initialize analyzer with optional broker, FY, and segment filters.

        Args:
            broker: Optional broker filter ('KOTAK' or 'ICICI')
            fy: Optional financial year filter (e.g., '2024-25' for FY 2024-25)
                If None or 'ALL', includes all data
            segment: Optional segment/asset filter ('FUTURES', 'OPTIONS', 'EQUITY', 'FNO', etc.)
                If None or 'ALL', includes all data
        """
        self.broker = broker
        self.fy = fy
        self.segment = segment
        self._fy_start = None
        self._fy_end = None

        # Parse FY into date range
        if fy and fy != 'ALL':
            self._parse_fy(fy)

    def _parse_fy(self, fy: str):
        """
        Parse financial year string into start and end dates.
        FY format: '2024-25' means April 1, 2024 to March 31, 2025
        """
        try:
            parts = fy.split('-')
            if len(parts) == 2:
                start_year = int(parts[0])
                # Handle both '24-25' and '2024-25' formats
                if start_year < 100:
                    start_year += 2000
                self._fy_start = date(start_year, 4, 1)
                self._fy_end = date(start_year + 1, 3, 31)
        except (ValueError, IndexError):
            logger.warning(f"Invalid FY format: {fy}")
            self._fy_start = None
            self._fy_end = None

    def get_base_queryset(self):
        """Get base queryset with optional broker, FY, and segment filters."""
        from apps.brokers.models import BrokerContractPnL

        qs = BrokerContractPnL.objects.all()
        if self.broker:
            qs = qs.filter(broker=self.broker)
        # Filter by FY: match either the 'fy' field OR expiry_date within FY range
        if self.fy and self.fy != 'ALL':
            if self._fy_start and self._fy_end:
                # Match trades where fy field matches OR expiry_date falls within FY range
                qs = qs.filter(
                    Q(fy=self.fy) |
                    Q(expiry_date__gte=self._fy_start, expiry_date__lte=self._fy_end)
                )
            else:
                # Fallback to just fy field if date range not parsed
                qs = qs.filter(fy=self.fy)
        # Filter by segment/asset type
        if self.segment and self.segment != 'ALL':
            if self.segment == 'FNO':
                # F&O includes both Futures and Options
                qs = qs.filter(segment__in=['FUTURES', 'OPTIONS'])
            else:
                qs = qs.filter(segment=self.segment)
        return qs

    def get_trade_history_queryset(self):
        """Get trade history queryset with optional broker and FY filters."""
        from apps.brokers.models import BrokerTradeHistory

        qs = BrokerTradeHistory.objects.all()
        if self.broker:
            qs = qs.filter(broker=self.broker)
        if self._fy_start and self._fy_end:
            qs = qs.filter(trade_date__gte=self._fy_start, trade_date__lte=self._fy_end)
        return qs

    def get_overview_stats(self) -> Dict[str, Any]:
        """
        Get overall trading statistics.

        Returns:
            Dict with total trades, win rate, profit factor, etc.
        """
        qs = self.get_base_queryset()

        # Debug logging
        total_count = qs.count()
        logger.info(f"[Overview Stats] Queryset count: {total_count}, broker={self.broker}, fy={self.fy}, segment={self.segment}")

        stats = qs.aggregate(
            total_trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            total_winners=Count('id', filter=Q(net_pnl__gt=0)),
            total_losers=Count('id', filter=Q(net_pnl__lt=0)),
            total_profit=Sum('net_pnl', filter=Q(net_pnl__gt=0)),
            total_loss=Sum('net_pnl', filter=Q(net_pnl__lt=0)),
            avg_profit=Avg('net_pnl', filter=Q(net_pnl__gt=0)),
            avg_loss=Avg('net_pnl', filter=Q(net_pnl__lt=0)),
            max_profit=Max('net_pnl'),
            max_loss=Min('net_pnl'),
        )

        total_trades = stats['total_trades'] or 0
        winners = stats['total_winners'] or 0
        losers = stats['total_losers'] or 0
        total_profit = float(stats['total_profit'] or 0)
        total_loss = abs(float(stats['total_loss'] or 0))

        # Calculate metrics
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else 0
        avg_profit = float(stats['avg_profit'] or 0)
        avg_loss = abs(float(stats['avg_loss'] or 0))
        risk_reward = (avg_profit / avg_loss) if avg_loss > 0 else 0
        expectancy = (win_rate/100 * avg_profit) - ((100-win_rate)/100 * avg_loss)

        return {
            'total_trades': total_trades,
            'total_pnl': float(stats['total_pnl'] or 0),
            'winners': winners,
            'losers': losers,
            'win_rate': round(win_rate, 1),
            'profit_factor': round(profit_factor, 2),
            'avg_profit': round(avg_profit, 2),
            'avg_loss': round(avg_loss, 2),
            'risk_reward': round(risk_reward, 2),
            'expectancy': round(expectancy, 2),
            'max_profit': float(stats['max_profit'] or 0),
            'max_loss': float(stats['max_loss'] or 0),
            'breakeven': losers > 0 and winners > 0,
        }

    def get_day_of_week_analysis(self) -> List[Dict[str, Any]]:
        """
        Analyze performance by day of week.

        Returns:
            List of dicts with day name, trades, P&L, win rate
        """
        from apps.brokers.models import BrokerTradeHistory

        qs = self.get_trade_history_queryset()

        # Group by day of week
        day_stats = qs.filter(trade_date__isnull=False).annotate(
            day_of_week=ExtractWeekDay('trade_date')
        ).values('day_of_week').annotate(
            trades=Count('id'),
        ).order_by('day_of_week')

        # Get P&L by day from contracts (using expiry as proxy for trade timing)
        contract_qs = self.get_base_queryset()

        day_names = ['', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

        results = []
        for stat in day_stats:
            day_num = stat['day_of_week']
            if day_num and 1 <= day_num <= 7:
                results.append({
                    'day': day_names[day_num],
                    'day_num': day_num,
                    'trades': stat['trades'],
                })

        # Sort by day number (Monday=2 to Friday=6)
        results.sort(key=lambda x: x['day_num'] if x['day_num'] != 1 else 8)

        return results

    def get_monthly_analysis(self) -> List[Dict[str, Any]]:
        """
        Analyze performance by month.

        Returns:
            List of dicts with month, trades, P&L, win rate
        """
        qs = self.get_base_queryset()

        monthly = qs.filter(expiry_date__isnull=False).annotate(
            month=ExtractMonth('expiry_date')
        ).values('month').annotate(
            trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            winners=Count('id', filter=Q(net_pnl__gt=0)),
            losers=Count('id', filter=Q(net_pnl__lt=0)),
        ).order_by('month')

        month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        results = []
        for stat in monthly:
            month_num = stat['month']
            trades = stat['trades'] or 0
            winners = stat['winners'] or 0
            win_rate = (winners / trades * 100) if trades > 0 else 0

            results.append({
                'month': month_names[month_num] if month_num else 'Unknown',
                'month_num': month_num,
                'trades': trades,
                'total_pnl': float(stat['total_pnl'] or 0),
                'winners': winners,
                'losers': stat['losers'] or 0,
                'win_rate': round(win_rate, 1),
            })

        return results

    def get_symbol_performance(self, limit: int = 10) -> Dict[str, List[Dict]]:
        """
        Get best and worst performing symbols.

        Args:
            limit: Number of symbols to return for each category

        Returns:
            Dict with 'best' and 'worst' lists
        """
        qs = self.get_base_queryset()

        symbol_stats = qs.values('symbol').annotate(
            trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            winners=Count('id', filter=Q(net_pnl__gt=0)),
            avg_pnl=Avg('net_pnl'),
        ).filter(trades__gte=2)  # At least 2 trades

        # Best performers (by total P&L)
        best = list(symbol_stats.order_by('-total_pnl')[:limit])
        for item in best:
            item['total_pnl'] = float(item['total_pnl'] or 0)
            item['avg_pnl'] = float(item['avg_pnl'] or 0)
            item['win_rate'] = round((item['winners'] / item['trades'] * 100), 1) if item['trades'] > 0 else 0

        # Worst performers
        worst = list(symbol_stats.order_by('total_pnl')[:limit])
        for item in worst:
            item['total_pnl'] = float(item['total_pnl'] or 0)
            item['avg_pnl'] = float(item['avg_pnl'] or 0)
            item['win_rate'] = round((item['winners'] / item['trades'] * 100), 1) if item['trades'] > 0 else 0

        # Most traded
        most_traded = list(symbol_stats.order_by('-trades')[:limit])
        for item in most_traded:
            item['total_pnl'] = float(item['total_pnl'] or 0)
            item['avg_pnl'] = float(item['avg_pnl'] or 0)
            item['win_rate'] = round((item['winners'] / item['trades'] * 100), 1) if item['trades'] > 0 else 0

        return {
            'best': best,
            'worst': worst,
            'most_traded': most_traded,
        }

    def get_segment_analysis(self) -> List[Dict[str, Any]]:
        """
        Analyze performance by segment (Futures vs Options).

        Returns:
            List of dicts with segment stats
        """
        qs = self.get_base_queryset()

        segment_stats = qs.values('segment').annotate(
            trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            winners=Count('id', filter=Q(net_pnl__gt=0)),
            losers=Count('id', filter=Q(net_pnl__lt=0)),
            avg_pnl=Avg('net_pnl'),
            total_profit=Sum('net_pnl', filter=Q(net_pnl__gt=0)),
            total_loss=Sum('net_pnl', filter=Q(net_pnl__lt=0)),
        ).order_by('-total_pnl')

        results = []
        for stat in segment_stats:
            trades = stat['trades'] or 0
            winners = stat['winners'] or 0
            total_profit = float(stat['total_profit'] or 0)
            total_loss = abs(float(stat['total_loss'] or 0))

            results.append({
                'segment': stat['segment'],
                'trades': trades,
                'total_pnl': float(stat['total_pnl'] or 0),
                'winners': winners,
                'losers': stat['losers'] or 0,
                'win_rate': round((winners / trades * 100), 1) if trades > 0 else 0,
                'avg_pnl': float(stat['avg_pnl'] or 0),
                'profit_factor': round(total_profit / total_loss, 2) if total_loss > 0 else 0,
            })

        return results

    def get_broker_comparison(self) -> List[Dict[str, Any]]:
        """
        Compare performance across brokers.

        Returns:
            List of dicts with broker stats
        """
        from apps.brokers.models import BrokerContractPnL

        # Start with base queryset but without broker filter for comparison
        qs = BrokerContractPnL.objects.all()
        # Use the 'fy' field for filtering
        if self.fy and self.fy != 'ALL':
            qs = qs.filter(fy=self.fy)

        broker_stats = qs.values('broker').annotate(
            trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            winners=Count('id', filter=Q(net_pnl__gt=0)),
            losers=Count('id', filter=Q(net_pnl__lt=0)),
            avg_pnl=Avg('net_pnl'),
            total_charges=Sum('total_charges'),
        ).order_by('-total_pnl')

        broker_names = {
            'KOTAK': 'Kotak Neo',
            'ICICI': 'ICICI Breeze',
        }

        results = []
        for stat in broker_stats:
            trades = stat['trades'] or 0
            winners = stat['winners'] or 0

            results.append({
                'broker': stat['broker'],
                'broker_name': broker_names.get(stat['broker'], stat['broker']),
                'trades': trades,
                'total_pnl': float(stat['total_pnl'] or 0),
                'winners': winners,
                'losers': stat['losers'] or 0,
                'win_rate': round((winners / trades * 100), 1) if trades > 0 else 0,
                'avg_pnl': float(stat['avg_pnl'] or 0),
                'total_charges': float(stat['total_charges'] or 0),
            })

        return results

    def get_streak_analysis(self) -> Dict[str, Any]:
        """
        Analyze winning and losing streaks.

        Returns:
            Dict with streak statistics
        """
        qs = self.get_base_queryset().order_by('expiry_date', 'id')

        trades = list(qs.values('net_pnl', 'symbol', 'expiry_date'))

        if not trades:
            return {
                'current_streak': 0,
                'current_streak_type': None,
                'max_win_streak': 0,
                'max_loss_streak': 0,
                'avg_win_streak': 0,
                'avg_loss_streak': 0,
            }

        # Calculate streaks
        win_streaks = []
        loss_streaks = []
        current_streak = 0
        current_type = None

        for trade in trades:
            pnl = float(trade['net_pnl'] or 0)
            is_win = pnl > 0

            if current_type is None:
                current_type = 'win' if is_win else 'loss'
                current_streak = 1
            elif (is_win and current_type == 'win') or (not is_win and current_type == 'loss'):
                current_streak += 1
            else:
                # Streak ended
                if current_type == 'win':
                    win_streaks.append(current_streak)
                else:
                    loss_streaks.append(current_streak)

                current_type = 'win' if is_win else 'loss'
                current_streak = 1

        # Don't forget the last streak
        if current_type == 'win':
            win_streaks.append(current_streak)
        else:
            loss_streaks.append(current_streak)

        return {
            'current_streak': current_streak,
            'current_streak_type': current_type,
            'max_win_streak': max(win_streaks) if win_streaks else 0,
            'max_loss_streak': max(loss_streaks) if loss_streaks else 0,
            'avg_win_streak': round(sum(win_streaks) / len(win_streaks), 1) if win_streaks else 0,
            'avg_loss_streak': round(sum(loss_streaks) / len(loss_streaks), 1) if loss_streaks else 0,
            'total_win_streaks': len(win_streaks),
            'total_loss_streaks': len(loss_streaks),
        }

    def get_pnl_distribution(self) -> Dict[str, Any]:
        """
        Get P&L distribution for histogram.

        Returns:
            Dict with distribution data
        """
        qs = self.get_base_queryset()

        pnl_values = list(qs.values_list('net_pnl', flat=True))
        pnl_values = [float(p) for p in pnl_values if p is not None]

        if not pnl_values:
            return {'buckets': [], 'stats': {}}

        # Calculate distribution buckets
        min_pnl = min(pnl_values)
        max_pnl = max(pnl_values)

        # Create fixed buckets for better visualization
        num_buckets = 8
        bucket_size = (max_pnl - min_pnl) / num_buckets if max_pnl != min_pnl else 1

        # Initialize buckets with counts
        bucket_counts = [0] * num_buckets
        bucket_ranges = []

        for i in range(num_buckets):
            bucket_start = min_pnl + (i * bucket_size)
            bucket_end = bucket_start + bucket_size
            bucket_ranges.append((bucket_start, bucket_end))

        # Count values in each bucket
        for pnl in pnl_values:
            bucket_idx = int((pnl - min_pnl) / bucket_size) if bucket_size > 0 else 0
            bucket_idx = min(bucket_idx, num_buckets - 1)  # Cap at last bucket
            bucket_counts[bucket_idx] += 1

        # Create sorted bucket list with simple labels
        buckets = []
        for i, (start, end) in enumerate(bucket_ranges):
            # Format label based on value size
            if abs(start) >= 1000000 or abs(end) >= 1000000:
                label = f"{start/100000:.1f}L to {end/100000:.1f}L"
            elif abs(start) >= 1000 or abs(end) >= 1000:
                label = f"{start/1000:.0f}K to {end/1000:.0f}K"
            else:
                label = f"{start:.0f} to {end:.0f}"
            buckets.append({
                'label': label,
                'count': bucket_counts[i],
                'start': start,
                'end': end
            })

        # Calculate percentiles
        sorted_pnl = sorted(pnl_values)
        n = len(sorted_pnl)

        return {
            'buckets': buckets,
            'stats': {
                'median': round(sorted_pnl[n // 2], 2) if n > 0 else 0,
                'p25': round(sorted_pnl[n // 4], 2) if n >= 4 else (round(sorted_pnl[0], 2) if n > 0 else 0),
                'p75': round(sorted_pnl[3 * n // 4], 2) if n >= 4 else (round(sorted_pnl[-1], 2) if n > 0 else 0),
                'std_dev': self._calculate_std_dev(pnl_values),
            }
        }

    def _calculate_std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return round(variance ** 0.5, 2)

    def get_consistency_metrics(self) -> Dict[str, Any]:
        """
        Calculate trading consistency metrics.

        Returns:
            Dict with consistency scores
        """
        qs = self.get_base_queryset()

        # Get monthly performance
        # Use Coalesce to fall back to created_at when expiry_date is NULL
        # This ensures older FY data (which may lack expiry_date) is still included
        monthly = qs.annotate(
            month=TruncMonth(Coalesce('expiry_date', 'created_at'))
        ).values('month').annotate(
            pnl=Sum('net_pnl'),
            trades=Count('id'),
        ).order_by('month')

        monthly_list = list(monthly)

        if len(monthly_list) < 2:
            return {
                'profitable_months': 0,
                'total_months': len(monthly_list),
                'consistency_score': 0,
                'monthly_volatility': 0,
            }

        pnl_values = [float(m['pnl'] or 0) for m in monthly_list]
        profitable_months = sum(1 for p in pnl_values if p > 0)

        # Calculate volatility (standard deviation of monthly returns)
        volatility = self._calculate_std_dev(pnl_values)

        # Consistency score: % of profitable months * (1 - normalized volatility)
        consistency = (profitable_months / len(monthly_list)) * 100

        return {
            'profitable_months': profitable_months,
            'total_months': len(monthly_list),
            'consistency_score': round(consistency, 1),
            'monthly_volatility': volatility,
            'avg_monthly_pnl': round(sum(pnl_values) / len(pnl_values), 2) if pnl_values else 0,
        }

    def get_critical_trades(self, top_percent: float = 10) -> List[Dict[str, Any]]:
        """
        Identify critical/important trades for timeline visualization.

        Critical trades include:
        - Top X% biggest wins
        - Top X% biggest losses
        - Streak start/end points
        - Monthly best/worst trades

        Args:
            top_percent: Percentage of trades to consider as critical (default 10%)

        Returns:
            List of critical trade events with date, type, and details
        """
        qs = self.get_base_queryset().order_by('expiry_date', 'created_at', 'id')
        trades = list(qs.values('id', 'net_pnl', 'symbol', 'segment', 'expiry_date', 'broker', 'created_at', 'trading_symbol'))

        if not trades:
            return []

        critical_trades = []
        seen_ids = set()

        # Helper to parse expiry date from trading_symbol
        def parse_expiry_from_symbol(trading_symbol):
            """
            Try to parse expiry date from trading symbol.
            Formats:
            - Kotak new: "NIFTY 31AUG2023 PE 19200" (DDMMMYYYY - 4-digit year)
            - Kotak old: "NIFTY 02DEC25 CE 26850" (DDMMMYY - 2-digit year)
            - Breeze: "NIFTY FUT 02 NOV 2025" or "NIFTY OPT 02 NOV 2025 CE 26850"
            """
            if not trading_symbol:
                return None

            parts = trading_symbol.strip().split()
            if len(parts) < 2:
                return None

            try:
                # Try Kotak format with 4-digit year: DDMMMYYYY (e.g., 31AUG2023)
                if len(parts) >= 2:
                    expiry_str = parts[1].upper()
                    if len(expiry_str) == 9 and expiry_str[:2].isdigit():
                        return datetime.strptime(expiry_str, '%d%b%Y').date()
            except ValueError:
                pass

            try:
                # Try Kotak format with 2-digit year: DDMMMYY (e.g., 02DEC25)
                if len(parts) >= 2:
                    expiry_str = parts[1].upper()
                    if len(expiry_str) == 7 and expiry_str[:2].isdigit():
                        return datetime.strptime(expiry_str, '%d%b%y').date()
            except ValueError:
                pass

            try:
                # Try Breeze format: parts[2]=day, parts[3]=month, parts[4]=year
                if len(parts) >= 5 and parts[1].upper() in ['FUT', 'OPT']:
                    expiry_str = f"{parts[2]}-{parts[3]}-{parts[4]}"
                    return datetime.strptime(expiry_str, '%d-%b-%Y').date()
            except (ValueError, IndexError):
                pass

            return None

        # Helper to get trade date (expiry_date, parse from symbol, or fallback to created_at)
        def get_trade_date(trade):
            if trade['expiry_date']:
                return trade['expiry_date']

            # Try to parse from trading_symbol
            parsed_date = parse_expiry_from_symbol(trade.get('trading_symbol'))
            if parsed_date:
                return parsed_date

            # Last resort: use created_at
            if trade['created_at']:
                created = trade['created_at']
                if hasattr(created, 'date'):
                    return created.date()
                return created
            return None

        # Calculate P&L thresholds for top trades
        pnl_values = sorted([float(t['net_pnl'] or 0) for t in trades])
        n = len(pnl_values)
        top_n = max(1, int(n * top_percent / 100))

        # Threshold for big wins (top X%)
        win_threshold = pnl_values[-(top_n)] if n > top_n else pnl_values[-1]
        # Threshold for big losses (bottom X%)
        loss_threshold = pnl_values[top_n - 1] if n > top_n else pnl_values[0]

        # 1. Find big wins and losses
        for trade in trades:
            pnl = float(trade['net_pnl'] or 0)
            trade_date = get_trade_date(trade)

            if trade_date and trade['id'] not in seen_ids:
                if pnl >= win_threshold and pnl > 0:
                    critical_trades.append({
                        'id': trade['id'],
                        'date': trade_date.isoformat() if hasattr(trade_date, 'isoformat') else str(trade_date),
                        'type': 'big_win',
                        'label': f"Big Win: {trade['symbol']}",
                        'pnl': pnl,
                        'symbol': trade['symbol'],
                        'segment': trade['segment'],
                        'broker': trade['broker'],
                        'color': '#10b981',  # green
                        'icon': '🚀'
                    })
                    seen_ids.add(trade['id'])
                elif pnl <= loss_threshold and pnl < 0:
                    critical_trades.append({
                        'id': trade['id'],
                        'date': trade_date.isoformat() if hasattr(trade_date, 'isoformat') else str(trade_date),
                        'type': 'big_loss',
                        'label': f"Big Loss: {trade['symbol']}",
                        'pnl': pnl,
                        'symbol': trade['symbol'],
                        'segment': trade['segment'],
                        'broker': trade['broker'],
                        'color': '#ef4444',  # red
                        'icon': '💔'
                    })
                    seen_ids.add(trade['id'])

        # 2. Find streak boundaries (streaks >= 3)
        current_streak = 0
        current_type = None
        streak_start_trade = None

        for i, trade in enumerate(trades):
            pnl = float(trade['net_pnl'] or 0)
            is_win = pnl > 0
            trade_date = get_trade_date(trade)

            if current_type is None:
                current_type = 'win' if is_win else 'loss'
                current_streak = 1
                streak_start_trade = trade
            elif (is_win and current_type == 'win') or (not is_win and current_type == 'loss'):
                current_streak += 1
            else:
                # Streak ended - mark if significant (>= 3)
                if current_streak >= 3 and streak_start_trade:
                    start_date = get_trade_date(streak_start_trade)
                    if start_date and streak_start_trade['id'] not in seen_ids:
                        critical_trades.append({
                            'id': streak_start_trade['id'],
                            'date': start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date),
                            'type': f'{current_type}_streak_start',
                            'label': f"{current_streak} {'Wins' if current_type == 'win' else 'Losses'} Streak",
                            'pnl': float(streak_start_trade['net_pnl'] or 0),
                            'symbol': streak_start_trade['symbol'],
                            'segment': streak_start_trade['segment'],
                            'broker': streak_start_trade['broker'],
                            'streak_length': current_streak,
                            'color': '#10b981' if current_type == 'win' else '#ef4444',
                            'icon': '🔥' if current_type == 'win' else '❄️'
                        })
                        seen_ids.add(streak_start_trade['id'])

                current_type = 'win' if is_win else 'loss'
                current_streak = 1
                streak_start_trade = trade

        # 3. Group by month and find monthly best/worst
        from collections import defaultdict
        monthly_trades = defaultdict(list)

        for trade in trades:
            trade_date = get_trade_date(trade)
            if trade_date:
                month_key = trade_date.strftime('%Y-%m') if hasattr(trade_date, 'strftime') else str(trade_date)[:7]
                monthly_trades[month_key].append(trade)

        for month, month_trades in monthly_trades.items():
            if len(month_trades) >= 5:  # Only for months with enough trades
                sorted_trades = sorted(month_trades, key=lambda x: float(x['net_pnl'] or 0))

                # Monthly worst
                worst = sorted_trades[0]
                if worst['id'] not in seen_ids and float(worst['net_pnl'] or 0) < 0:
                    worst_date = get_trade_date(worst)
                    critical_trades.append({
                        'id': worst['id'],
                        'date': worst_date.isoformat() if hasattr(worst_date, 'isoformat') else str(worst_date),
                        'type': 'monthly_worst',
                        'label': f"Month's Worst: {worst['symbol']}",
                        'pnl': float(worst['net_pnl'] or 0),
                        'symbol': worst['symbol'],
                        'segment': worst['segment'],
                        'broker': worst['broker'],
                        'month': month,
                        'color': '#f97316',  # orange
                        'icon': '📉'
                    })
                    seen_ids.add(worst['id'])

                # Monthly best
                best = sorted_trades[-1]
                if best['id'] not in seen_ids and float(best['net_pnl'] or 0) > 0:
                    best_date = get_trade_date(best)
                    critical_trades.append({
                        'id': best['id'],
                        'date': best_date.isoformat() if hasattr(best_date, 'isoformat') else str(best_date),
                        'type': 'monthly_best',
                        'label': f"Month's Best: {best['symbol']}",
                        'pnl': float(best['net_pnl'] or 0),
                        'symbol': best['symbol'],
                        'segment': best['segment'],
                        'broker': best['broker'],
                        'month': month,
                        'color': '#22c55e',  # lighter green
                        'icon': '📈'
                    })
                    seen_ids.add(best['id'])

        # Sort by date
        critical_trades.sort(key=lambda x: x['date'])

        return critical_trades

    def get_timeline_data(self) -> Dict[str, Any]:
        """
        Get data for timeline visualization with Nifty overlay.

        Returns:
            Dict with critical trades, nifty data, and date range
        """
        from apps.brokers.models import HistoricalPrice, BrokerContractPnL

        today = date.today()

        # Use FY filter if set, otherwise determine date range from data
        if self.fy and self.fy != 'ALL':
            # Specific FY selected - use its date range
            fy_start = self._fy_start
            fy_end = self._fy_end
        else:
            # ALL selected - get date range from all data
            qs = self.get_base_queryset().filter(expiry_date__isnull=False)
            date_range = qs.aggregate(
                min_date=Min('expiry_date'),
                max_date=Max('expiry_date')
            )
            if date_range['min_date'] and date_range['max_date']:
                fy_start = date_range['min_date']
                fy_end = min(date_range['max_date'], today)
            else:
                # Fallback to current FY
                if today.month >= 4:
                    fy_start = date(today.year, 4, 1)
                    fy_end = date(today.year + 1, 3, 31)
                else:
                    fy_start = date(today.year - 1, 4, 1)
                    fy_end = date(today.year, 3, 31)

        # Get critical trades (already filtered by FY in get_base_queryset)
        critical_trades = self.get_critical_trades()

        # Get Nifty daily data for the date range
        nifty_data = list(HistoricalPrice.objects.filter(
            stock_code='NIFTY',
            exchange_code='NSE',
            product_type='cash',
            datetime__date__gte=fy_start,
            datetime__date__lte=min(today, fy_end),
        ).order_by('datetime').values('datetime', 'close'))

        # Convert to simple format for JS
        nifty_timeline = []
        seen_dates = set()
        for n in nifty_data:
            dt = n['datetime']
            date_str = dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)[:10]
            if date_str not in seen_dates:
                nifty_timeline.append({
                    'date': date_str,
                    'close': float(n['close'])
                })
                seen_dates.add(date_str)

        return {
            'critical_trades': critical_trades,
            'nifty_data': nifty_timeline,
            'fy_start': fy_start.isoformat(),
            'fy_end': fy_end.isoformat(),
            'has_nifty_data': len(nifty_timeline) > 0,
        }

    def get_all_patterns(self) -> Dict[str, Any]:
        """
        Get all pattern analysis data.

        Returns:
            Dict with all pattern data
        """
        result = {}

        # Get each section with error handling
        try:
            result['overview'] = self.get_overview_stats()
        except Exception as e:
            logger.error(f"Error getting overview stats: {e}", exc_info=True)
            result['overview'] = {}

        try:
            result['monthly'] = self.get_monthly_analysis()
        except Exception as e:
            logger.error(f"Error getting monthly analysis: {e}")
            result['monthly'] = []

        try:
            result['symbols'] = self.get_symbol_performance()
        except Exception as e:
            logger.error(f"Error getting symbol performance: {e}")
            result['symbols'] = {'best': [], 'worst': [], 'most_traded': []}

        try:
            result['segments'] = self.get_segment_analysis()
        except Exception as e:
            logger.error(f"Error getting segment analysis: {e}")
            result['segments'] = []

        try:
            result['brokers'] = self.get_broker_comparison()
        except Exception as e:
            logger.error(f"Error getting broker comparison: {e}")
            result['brokers'] = []

        try:
            result['streaks'] = self.get_streak_analysis()
        except Exception as e:
            logger.error(f"Error getting streak analysis: {e}")
            result['streaks'] = {}

        try:
            result['distribution'] = self.get_pnl_distribution()
        except Exception as e:
            logger.error(f"Error getting pnl distribution: {e}")
            result['distribution'] = {'buckets': [], 'stats': {}}

        try:
            result['consistency'] = self.get_consistency_metrics()
        except Exception as e:
            logger.error(f"Error getting consistency metrics: {e}")
            result['consistency'] = {}

        return result


def get_trading_patterns(broker: str = None, fy: str = None) -> Dict[str, Any]:
    """
    Convenience function to get all trading patterns.

    Args:
        broker: Optional broker filter
        fy: Optional financial year filter (e.g., '2024-25')

    Returns:
        Dict with all pattern analysis data
    """
    analyzer = TradingPatternsAnalyzer(broker=broker, fy=fy)
    return analyzer.get_all_patterns()


def get_available_fys() -> List[Dict[str, str]]:
    """
    Get list of available financial years from the data.

    Checks both BrokerContractPnL (CSV imports) and BrokerTradeHistory (API syncs)
    to get all available fiscal years.

    Returns:
        List of dicts with 'value' (e.g., '2024-25') and 'label' (e.g., 'FY 2024-25')
    """
    from apps.brokers.models import BrokerContractPnL, BrokerTradeHistory
    from django.db.models.functions import ExtractYear, ExtractMonth

    seen = set()

    # Get distinct FY values from BrokerContractPnL 'fy' field (CSV imports)
    fy_values = BrokerContractPnL.objects.exclude(
        fy=''
    ).values('fy').distinct().values_list('fy', flat=True)

    for fy_value in fy_values:
        if fy_value:
            seen.add(fy_value)

    # Get distinct year/month combinations from BrokerTradeHistory (API syncs)
    # This is more efficient than fetching all trade dates
    year_months = BrokerTradeHistory.objects.annotate(
        year=ExtractYear('trade_date'),
        month=ExtractMonth('trade_date')
    ).values('year', 'month').distinct()

    for ym in year_months:
        year, month = ym['year'], ym['month']
        if year and month:
            # FY runs April 1 to March 31
            if month >= 4:  # April onwards
                fy_value = f"{year}-{str(year + 1)[-2:]}"
            else:  # Jan-Mar
                fy_value = f"{year - 1}-{str(year)[-2:]}"
            seen.add(fy_value)

    # Build result list
    fys = [{'value': fy, 'label': f"FY {fy}"} for fy in seen]

    # Sort by FY value (newest first)
    fys.sort(key=lambda x: x['value'], reverse=True)

    return fys
