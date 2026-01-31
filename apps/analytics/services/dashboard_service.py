"""
Dashboard Service for mCube Trading System

Provides data for the analytics dashboard:
- Summary metrics
- P&L charts
- Equity curves
- Win/loss distributions
- Performance heatmaps
- Benchmark comparisons
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from django.db.models import Avg, Sum, Count, Max, Min, Q
from django.utils import timezone
from django.contrib.auth.models import User

from apps.accounts.models import BrokerAccount
from apps.analytics.models import (
    DailyEquityCurve,
    AccountReturns,
    DailyPnL,
    BenchmarkData,
    PortfolioBeta,
    UserDecisionLog,
)
from apps.trading.models import TakenTrade, TradeSuggestion
from apps.positions.models import Position

logger = logging.getLogger(__name__)


class DashboardService:
    """
    Service for providing dashboard data and metrics.
    """

    def get_summary_metrics(
        self,
        user: User,
        account: Optional[BrokerAccount] = None,
        period: str = 'FY',
        fy: str = None,
    ) -> Dict[str, Any]:
        """
        Get summary metrics for dashboard header.

        Args:
            user: The user
            account: Optional specific account (None for all accounts)
            period: Period for metrics (1D, 1W, 1M, 3M, 6M, 1Y, FY, YTD, ALL)
            fy: Optional specific financial year (e.g., '2024-25')

        Returns:
            Dict with summary metrics
        """
        try:
            # Determine date range
            start_date, end_date = self._get_period_dates(period, fy)

            # Build trade query
            trades_query = TakenTrade.objects.filter(
                user=user,
                status='CLOSED',
                closed_at__date__gte=start_date,
                closed_at__date__lte=end_date,
            )

            if account:
                trades_query = trades_query.filter(account=account)

            # Basic counts
            total_trades = trades_query.count()
            winning_trades = trades_query.filter(outcome='PROFIT').count()
            losing_trades = trades_query.filter(outcome='LOSS').count()

            # P&L metrics
            total_pnl = trades_query.aggregate(total=Sum('net_pnl'))['total'] or Decimal('0.00')
            gross_profit = trades_query.filter(net_pnl__gt=0).aggregate(
                total=Sum('net_pnl')
            )['total'] or Decimal('0.00')
            gross_loss = abs(trades_query.filter(net_pnl__lt=0).aggregate(
                total=Sum('net_pnl')
            )['total'] or Decimal('0.00'))

            # Win rate
            win_rate = Decimal('0.00')
            if total_trades > 0:
                win_rate = Decimal(winning_trades) / Decimal(total_trades) * 100

            # Profit factor
            profit_factor = None
            if gross_loss > 0:
                profit_factor = gross_profit / gross_loss

            # Average metrics
            avg_win = trades_query.filter(outcome='PROFIT').aggregate(
                avg=Avg('net_pnl')
            )['avg'] or Decimal('0.00')
            avg_loss = trades_query.filter(outcome='LOSS').aggregate(
                avg=Avg('net_pnl')
            )['avg'] or Decimal('0.00')

            # Best and worst trades
            best_trade = trades_query.order_by('-net_pnl').first()
            worst_trade = trades_query.order_by('net_pnl').first()

            # Get account returns if available
            returns_data = {}
            if account:
                returns = AccountReturns.objects.filter(
                    account=account,
                    period_type=self._period_to_type(period),
                ).order_by('-period_end').first()

                if returns:
                    returns_data = {
                        'sharpe_ratio': float(returns.sharpe_ratio) if returns.sharpe_ratio else None,
                        'sortino_ratio': float(returns.sortino_ratio) if returns.sortino_ratio else None,
                        'max_drawdown': float(returns.max_drawdown),
                        'max_drawdown_pct': float(returns.max_drawdown_pct),
                        'volatility': float(returns.volatility) if returns.volatility else None,
                    }

            # Get beta/alpha if available
            beta_alpha = {}
            if account:
                beta = PortfolioBeta.objects.filter(
                    account=account,
                    benchmark='NIFTY50',
                ).order_by('-calculation_date').first()

                if beta:
                    beta_alpha = {
                        'beta': float(beta.beta),
                        'alpha': float(beta.alpha),
                        'correlation': float(beta.correlation) if beta.correlation else None,
                    }

            return {
                'period': period,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),

                # Trade counts
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'breakeven_trades': total_trades - winning_trades - losing_trades,

                # P&L
                'total_pnl': float(total_pnl),
                'gross_profit': float(gross_profit),
                'gross_loss': float(gross_loss),

                # Rates
                'win_rate': float(win_rate),
                'profit_factor': float(profit_factor) if profit_factor else None,

                # Averages
                'avg_win': float(avg_win),
                'avg_loss': float(avg_loss),
                'expectancy': float((win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * abs(avg_loss))),

                # Best/Worst
                'best_trade_pnl': float(best_trade.net_pnl) if best_trade else None,
                'best_trade_id': best_trade.id if best_trade else None,
                'worst_trade_pnl': float(worst_trade.net_pnl) if worst_trade else None,
                'worst_trade_id': worst_trade.id if worst_trade else None,

                # Risk metrics
                **returns_data,
                **beta_alpha,
            }

        except Exception as e:
            logger.error(f"Error getting summary metrics: {e}", exc_info=True)
            return {'error': str(e)}

    def get_pnl_chart_data(
        self,
        user: User,
        account: Optional[BrokerAccount] = None,
        period: str = '1M',
        granularity: str = 'daily',
        fy: str = None,
    ) -> Dict[str, Any]:
        """
        Get P&L chart data for visualization.

        Args:
            user: The user
            account: Optional specific account
            period: Time period
            granularity: 'daily', 'weekly', or 'monthly'
            fy: Optional specific financial year (e.g., '2024-25')

        Returns:
            Dict with chart data
        """
        try:
            start_date, end_date = self._get_period_dates(period, fy)

            if granularity == 'daily':
                return self._get_daily_pnl_data(user, account, start_date, end_date)
            elif granularity == 'weekly':
                return self._get_weekly_pnl_data(user, account, start_date, end_date)
            else:  # monthly
                return self._get_monthly_pnl_data(user, account, start_date, end_date)

        except Exception as e:
            logger.error(f"Error getting P&L chart data: {e}", exc_info=True)
            return {'error': str(e)}

    def _get_daily_pnl_data(
        self,
        user: User,
        account: Optional[BrokerAccount],
        start_date: date,
        end_date: date,
    ) -> Dict:
        """Get daily P&L data."""
        query = DailyPnL.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
        ).order_by('date')

        if account:
            query = query.filter(account=account)

        data = {
            'labels': [],
            'realized_pnl': [],
            'cumulative_pnl': [],
            'colors': [],
        }

        cumulative = Decimal('0.00')
        for record in query:
            data['labels'].append(record.date.isoformat())
            data['realized_pnl'].append(float(record.realized_pnl))
            cumulative += record.realized_pnl
            data['cumulative_pnl'].append(float(cumulative))
            data['colors'].append('green' if record.realized_pnl >= 0 else 'red')

        return data

    def _get_weekly_pnl_data(
        self,
        user: User,
        account: Optional[BrokerAccount],
        start_date: date,
        end_date: date,
    ) -> Dict:
        """Get weekly aggregated P&L data."""
        from django.db.models.functions import TruncWeek

        query = TakenTrade.objects.filter(
            user=user,
            status='CLOSED',
            closed_at__date__gte=start_date,
            closed_at__date__lte=end_date,
        )

        if account:
            query = query.filter(account=account)

        weekly_data = query.annotate(
            week=TruncWeek('closed_at')
        ).values('week').annotate(
            total_pnl=Sum('net_pnl'),
            trades=Count('id'),
        ).order_by('week')

        data = {
            'labels': [],
            'realized_pnl': [],
            'cumulative_pnl': [],
            'trade_counts': [],
        }

        cumulative = Decimal('0.00')
        for record in weekly_data:
            data['labels'].append(record['week'].strftime('%Y-W%W'))
            pnl = record['total_pnl'] or Decimal('0.00')
            data['realized_pnl'].append(float(pnl))
            cumulative += pnl
            data['cumulative_pnl'].append(float(cumulative))
            data['trade_counts'].append(record['trades'])

        return data

    def _get_monthly_pnl_data(
        self,
        user: User,
        account: Optional[BrokerAccount],
        start_date: date,
        end_date: date,
    ) -> Dict:
        """Get monthly aggregated P&L data."""
        from django.db.models.functions import TruncMonth

        query = TakenTrade.objects.filter(
            user=user,
            status='CLOSED',
            closed_at__date__gte=start_date,
            closed_at__date__lte=end_date,
        )

        if account:
            query = query.filter(account=account)

        monthly_data = query.annotate(
            month=TruncMonth('closed_at')
        ).values('month').annotate(
            total_pnl=Sum('net_pnl'),
            trades=Count('id'),
            wins=Count('id', filter=Q(outcome='PROFIT')),
        ).order_by('month')

        data = {
            'labels': [],
            'realized_pnl': [],
            'cumulative_pnl': [],
            'trade_counts': [],
            'win_rates': [],
        }

        cumulative = Decimal('0.00')
        for record in monthly_data:
            data['labels'].append(record['month'].strftime('%b %Y'))
            pnl = record['total_pnl'] or Decimal('0.00')
            data['realized_pnl'].append(float(pnl))
            cumulative += pnl
            data['cumulative_pnl'].append(float(cumulative))
            data['trade_counts'].append(record['trades'])

            win_rate = 0
            if record['trades'] > 0:
                win_rate = record['wins'] / record['trades'] * 100
            data['win_rates'].append(round(win_rate, 1))

        return data

    def get_cumulative_returns(
        self,
        user: User,
        account: Optional[BrokerAccount] = None,
        period: str = 'FY',
        fy: str = None,
    ) -> Dict[str, Any]:
        """
        Get cumulative returns data for equity curve chart.

        Args:
            user: The user
            account: Optional specific account
            period: Time period
            fy: Optional specific financial year (e.g., '2024-25')

        Returns:
            Dict with equity curve data
        """
        try:
            start_date, end_date = self._get_period_dates(period, fy)

            query = DailyEquityCurve.objects.filter(
                date__gte=start_date,
                date__lte=end_date,
            ).order_by('date')

            if account:
                query = query.filter(account=account)

            data = {
                'labels': [],
                'equity': [],
                'returns_pct': [],
                'drawdown_pct': [],
            }

            for curve in query:
                data['labels'].append(curve.date.isoformat())
                data['equity'].append(float(curve.closing_capital))
                data['returns_pct'].append(float(curve.cumulative_return_pct))
                data['drawdown_pct'].append(float(curve.drawdown_pct))

            return data

        except Exception as e:
            logger.error(f"Error getting cumulative returns: {e}", exc_info=True)
            return {'error': str(e)}

    def get_win_loss_distribution(
        self,
        user: User,
        account: Optional[BrokerAccount] = None,
        period: str = 'FY',
        fy: str = None,
    ) -> Dict[str, Any]:
        """
        Get win/loss distribution data for histogram.

        Args:
            user: The user
            account: Optional specific account
            period: Time period
            fy: Optional specific financial year (e.g., '2024-25')

        Returns:
            Dict with distribution data
        """
        try:
            start_date, end_date = self._get_period_dates(period, fy)

            query = TakenTrade.objects.filter(
                user=user,
                status='CLOSED',
                closed_at__date__gte=start_date,
                closed_at__date__lte=end_date,
            )

            if account:
                query = query.filter(account=account)

            # Get all P&L values
            pnl_values = list(query.values_list('net_pnl', flat=True))

            if not pnl_values:
                return {'error': 'No trades in period'}

            pnl_floats = [float(p or 0) for p in pnl_values]

            # Create histogram buckets
            min_pnl = min(pnl_floats)
            max_pnl = max(pnl_floats)

            # Create 10 buckets
            num_buckets = 10
            bucket_size = (max_pnl - min_pnl) / num_buckets if max_pnl != min_pnl else 1

            buckets = [0] * num_buckets
            bucket_labels = []

            for i in range(num_buckets):
                lower = min_pnl + (i * bucket_size)
                upper = lower + bucket_size
                bucket_labels.append(f"{int(lower)}-{int(upper)}")

                for pnl in pnl_floats:
                    if lower <= pnl < upper or (i == num_buckets - 1 and pnl == max_pnl):
                        buckets[i] += 1

            # Win/Loss breakdown
            wins = query.filter(outcome='PROFIT')
            losses = query.filter(outcome='LOSS')

            return {
                'histogram': {
                    'labels': bucket_labels,
                    'counts': buckets,
                },
                'summary': {
                    'total_trades': len(pnl_values),
                    'wins': wins.count(),
                    'losses': losses.count(),
                    'avg_win': float(wins.aggregate(avg=Avg('net_pnl'))['avg'] or 0),
                    'avg_loss': float(losses.aggregate(avg=Avg('net_pnl'))['avg'] or 0),
                    'max_win': float(max(p for p in pnl_floats if p > 0)) if any(p > 0 for p in pnl_floats) else 0,
                    'max_loss': float(min(p for p in pnl_floats if p < 0)) if any(p < 0 for p in pnl_floats) else 0,
                },
            }

        except Exception as e:
            logger.error(f"Error getting win/loss distribution: {e}", exc_info=True)
            return {'error': str(e)}

    def get_strategy_performance(
        self,
        user: User,
        account: Optional[BrokerAccount] = None,
        period: str = 'FY',
        fy: str = None,
    ) -> Dict[str, Any]:
        """
        Get performance breakdown by strategy.

        Args:
            user: The user
            account: Optional specific account
            period: Time period
            fy: Optional specific financial year (e.g., '2024-25')

        Returns:
            Dict with strategy performance data
        """
        try:
            start_date, end_date = self._get_period_dates(period, fy)

            query = TakenTrade.objects.filter(
                user=user,
                status='CLOSED',
                closed_at__date__gte=start_date,
                closed_at__date__lte=end_date,
            )

            if account:
                query = query.filter(account=account)

            # Group by strategy
            strategy_data = query.values('strategy').annotate(
                total_trades=Count('id'),
                wins=Count('id', filter=Q(outcome='PROFIT')),
                losses=Count('id', filter=Q(outcome='LOSS')),
                total_pnl=Sum('net_pnl'),
                avg_pnl=Avg('net_pnl'),
            ).order_by('-total_pnl')

            strategies = []
            for data in strategy_data:
                win_rate = 0
                if data['total_trades'] > 0:
                    win_rate = data['wins'] / data['total_trades'] * 100

                strategies.append({
                    'strategy': data['strategy'],
                    'total_trades': data['total_trades'],
                    'wins': data['wins'],
                    'losses': data['losses'],
                    'win_rate': round(win_rate, 1),
                    'total_pnl': float(data['total_pnl'] or 0),
                    'avg_pnl': float(data['avg_pnl'] or 0),
                })

            return {
                'strategies': strategies,
                'period': period,
            }

        except Exception as e:
            logger.error(f"Error getting strategy performance: {e}", exc_info=True)
            return {'error': str(e)}

    def get_performance_heatmap(
        self,
        user: User,
        account: Optional[BrokerAccount] = None,
        period: str = 'FY',
        fy: str = None,
    ) -> Dict[str, Any]:
        """
        Get performance heatmap data by day/hour.

        Args:
            user: The user
            account: Optional specific account
            period: Time period
            fy: Optional specific financial year (e.g., '2024-25')

        Returns:
            Dict with heatmap data
        """
        try:
            start_date, end_date = self._get_period_dates(period, fy)
            from django.db.models.functions import ExtractHour, ExtractWeekDay

            query = TakenTrade.objects.filter(
                user=user,
                status='CLOSED',
                closed_at__date__gte=start_date,
                closed_at__date__lte=end_date,
            )

            if account:
                query = query.filter(account=account)

            # Group by day of week and hour
            heatmap_data = query.annotate(
                day=ExtractWeekDay('closed_at'),
                hour=ExtractHour('closed_at'),
            ).values('day', 'hour').annotate(
                total_pnl=Sum('net_pnl'),
                trades=Count('id'),
                wins=Count('id', filter=Q(outcome='PROFIT')),
            ).order_by('day', 'hour')

            # Initialize 7x10 grid (days x trading hours 9-18)
            days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
            hours = list(range(9, 16))  # 9 AM to 3 PM

            grid = [[0 for _ in hours] for _ in days]

            for data in heatmap_data:
                day_idx = data['day'] - 1  # 1=Sunday in Django
                if data['hour'] in hours:
                    hour_idx = hours.index(data['hour'])
                    grid[day_idx][hour_idx] = float(data['total_pnl'] or 0)

            return {
                'days': days,
                'hours': [f"{h}:00" for h in hours],
                'data': grid,
            }

        except Exception as e:
            logger.error(f"Error getting performance heatmap: {e}", exc_info=True)
            return {'error': str(e)}

    def get_best_worst_trades(
        self,
        user: User,
        account: Optional[BrokerAccount] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Get best and worst trades.

        Args:
            user: The user
            account: Optional specific account
            limit: Number of trades to return

        Returns:
            Dict with best/worst trades
        """
        try:
            query = TakenTrade.objects.filter(
                user=user,
                status='CLOSED',
            )

            if account:
                query = query.filter(account=account)

            best_trades = list(query.order_by('-net_pnl')[:limit].values(
                'id', 'instrument', 'strategy', 'direction', 'net_pnl',
                'entry_price', 'exit_price', 'closed_at'
            ))

            worst_trades = list(query.order_by('net_pnl')[:limit].values(
                'id', 'instrument', 'strategy', 'direction', 'net_pnl',
                'entry_price', 'exit_price', 'closed_at'
            ))

            # Convert Decimal to float
            for trade in best_trades + worst_trades:
                trade['net_pnl'] = float(trade['net_pnl'] or 0)
                trade['entry_price'] = float(trade['entry_price'] or 0)
                trade['exit_price'] = float(trade['exit_price'] or 0)
                if trade['closed_at']:
                    trade['closed_at'] = trade['closed_at'].isoformat()

            return {
                'best_trades': best_trades,
                'worst_trades': worst_trades,
            }

        except Exception as e:
            logger.error(f"Error getting best/worst trades: {e}", exc_info=True)
            return {'error': str(e)}

    def get_benchmark_comparison(
        self,
        user: User,
        account: Optional[BrokerAccount] = None,
        benchmark: str = 'NIFTY50',
        period: str = 'FY',
        fy: str = None,
    ) -> Dict[str, Any]:
        """
        Get performance comparison vs benchmark.

        Args:
            user: The user
            account: Optional specific account
            benchmark: Benchmark to compare against
            period: Time period
            fy: Optional specific financial year (e.g., '2024-25')

        Returns:
            Dict with comparison data
        """
        try:
            from apps.analytics.services.benchmark_analyzer import get_analyzer

            analyzer = get_analyzer()

            if account:
                return analyzer.get_performance_vs_benchmark(account, benchmark, period)
            else:
                # Aggregate across all accounts
                accounts = BrokerAccount.objects.filter(is_active=True)
                combined_data = {
                    'portfolio_return': 0,
                    'benchmark_return': 0,
                    'excess_return': 0,
                    'portfolio_series': [],
                    'benchmark_series': [],
                }

                for acc in accounts:
                    data = analyzer.get_performance_vs_benchmark(acc, benchmark, period)
                    if 'error' not in data:
                        combined_data['portfolio_return'] += data.get('portfolio_return', 0)
                        combined_data['benchmark_return'] = data.get('benchmark_return', 0)

                combined_data['excess_return'] = (
                    combined_data['portfolio_return'] - combined_data['benchmark_return']
                )
                combined_data['outperformed'] = combined_data['excess_return'] > 0

                return combined_data

        except Exception as e:
            logger.error(f"Error getting benchmark comparison: {e}", exc_info=True)
            return {'error': str(e)}

    def get_decision_patterns(
        self,
        user: User,
        period: str = 'FY',
        fy: str = None,
    ) -> Dict[str, Any]:
        """
        Get ML insights on decision patterns.

        Args:
            user: The user
            period: Time period
            fy: Optional specific financial year (e.g., '2024-25')

        Returns:
            Dict with decision pattern analysis
        """
        try:
            start_date, end_date = self._get_period_dates(period, fy)

            logs = UserDecisionLog.objects.filter(
                user=user,
                decision_timestamp__date__gte=start_date,
                decision_timestamp__date__lte=end_date,
            )

            # Decision type breakdown
            decision_breakdown = logs.values('decision_type').annotate(
                count=Count('id')
            )

            # Outcome by decision type (for approved trades)
            outcome_by_decision = logs.filter(
                decision_type__in=['APPROVE', 'AUTO_APPROVE'],
                final_outcome__in=['PROFIT', 'LOSS', 'BREAKEVEN'],
            ).values('decision_type', 'final_outcome').annotate(
                count=Count('id')
            )

            # Decision time analysis
            timing_analysis = logs.exclude(
                time_to_decision_seconds__isnull=True
            ).aggregate(
                avg_time=Avg('time_to_decision_seconds'),
                min_time=Min('time_to_decision_seconds'),
                max_time=Max('time_to_decision_seconds'),
            )

            return {
                'decision_breakdown': list(decision_breakdown),
                'outcome_by_decision': list(outcome_by_decision),
                'timing': {
                    'avg_seconds': timing_analysis['avg_time'],
                    'min_seconds': timing_analysis['min_time'],
                    'max_seconds': timing_analysis['max_time'],
                },
                'total_decisions': logs.count(),
            }

        except Exception as e:
            logger.error(f"Error getting decision patterns: {e}", exc_info=True)
            return {'error': str(e)}

    def get_recommendation_accuracy(
        self,
        user: User,
        period: str = 'FY',
        fy: str = None,
    ) -> Dict[str, Any]:
        """
        Get accuracy analysis of algorithm recommendations.

        Args:
            user: The user
            period: Time period
            fy: Optional specific financial year (e.g., '2024-25')

        Returns:
            Dict with recommendation accuracy data
        """
        try:
            start_date, end_date = self._get_period_dates(period, fy)

            # Get suggestions with outcomes
            suggestions = TradeSuggestion.objects.filter(
                user=user,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
                status__in=['SUCCESSFUL', 'LOSS', 'BREAKEVEN'],
            )

            # Accuracy by strategy
            accuracy_by_strategy = suggestions.values('strategy').annotate(
                total=Count('id'),
                successful=Count('id', filter=Q(status='SUCCESSFUL')),
            )

            # Accuracy by confidence level
            high_confidence = suggestions.filter(
                algorithm_reasoning__llm_confidence__gte=90
            )
            medium_confidence = suggestions.filter(
                algorithm_reasoning__llm_confidence__gte=70,
                algorithm_reasoning__llm_confidence__lt=90,
            )
            low_confidence = suggestions.filter(
                algorithm_reasoning__llm_confidence__lt=70
            )

            return {
                'by_strategy': [
                    {
                        'strategy': s['strategy'],
                        'total': s['total'],
                        'accuracy': (s['successful'] / s['total'] * 100) if s['total'] > 0 else 0,
                    }
                    for s in accuracy_by_strategy
                ],
                'by_confidence': {
                    'high': {
                        'count': high_confidence.count(),
                        'accuracy': self._calculate_accuracy(high_confidence),
                    },
                    'medium': {
                        'count': medium_confidence.count(),
                        'accuracy': self._calculate_accuracy(medium_confidence),
                    },
                    'low': {
                        'count': low_confidence.count(),
                        'accuracy': self._calculate_accuracy(low_confidence),
                    },
                },
                'overall_accuracy': self._calculate_accuracy(suggestions),
            }

        except Exception as e:
            logger.error(f"Error getting recommendation accuracy: {e}", exc_info=True)
            return {'error': str(e)}

    def _calculate_accuracy(self, queryset) -> float:
        """Calculate accuracy from queryset."""
        total = queryset.count()
        if total == 0:
            return 0.0
        successful = queryset.filter(status='SUCCESSFUL').count()
        return round((successful / total) * 100, 1)

    def _get_period_dates(self, period: str, fy: str = None) -> tuple:
        """
        Get start and end dates for a period.

        Args:
            period: Period string (1D, 1W, 1M, 3M, 6M, 1Y, FY, YTD, ALL)
            fy: Optional specific financial year like '2024-25'

        Returns:
            Tuple of (start_date, end_date)
        """
        today = date.today()

        # If specific FY is provided, use that
        if fy:
            try:
                start_year = int(fy.split('-')[0])
                end_year = start_year + 1
                start_date = date(start_year, 4, 1)  # April 1
                end_date = date(end_year, 3, 31)  # March 31
                # If FY is current or future, cap at today
                if end_date > today:
                    end_date = today
                return start_date, end_date
            except (ValueError, IndexError):
                pass  # Fall through to regular period handling

        if period == '1D':
            return today, today
        elif period == '1W':
            return today - timedelta(days=7), today
        elif period == '1M':
            return today - timedelta(days=30), today
        elif period == '3M':
            return today - timedelta(days=90), today
        elif period == '6M':
            return today - timedelta(days=180), today
        elif period == '1Y':
            return today - timedelta(days=365), today
        elif period == 'YTD':
            return date(today.year, 1, 1), today
        elif period == 'FY':
            if today.month >= 4:
                return date(today.year, 4, 1), today
            else:
                return date(today.year - 1, 4, 1), today
        else:  # ALL
            return date(2020, 1, 1), today

    def _period_to_type(self, period: str) -> str:
        """Convert period string to AccountReturns period type."""
        mapping = {
            '1D': 'DAILY',
            '1W': 'WEEKLY',
            '1M': 'MONTHLY',
            '3M': 'QUARTERLY',
            'FY': 'FY',
            'YTD': 'YTD',
            'ALL': 'ALL_TIME',
        }
        return mapping.get(period, 'MONTHLY')


# Singleton instance
_service = None


def get_dashboard_service() -> DashboardService:
    """Get singleton DashboardService instance."""
    global _service
    if _service is None:
        _service = DashboardService()
    return _service
