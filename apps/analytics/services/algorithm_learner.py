"""
Algorithm Learner Service

Learns from trade outcomes to improve future suggestions.
Records entry conditions, tracks outcomes, and identifies patterns.

This is a minimal implementation focusing on:
1. Recording trade entry conditions (already in algorithm_reasoning)
2. Tracking trade outcomes (P&L, exit reason, duration)
3. Basic pattern identification
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from django.db.models import Avg, Sum, Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class AlgorithmLearner:
    """
    Learn from trade outcomes to improve future suggestions.

    Records conditions at entry, outcomes at exit, and generates insights.
    """

    def analyze_closed_trade(self, position) -> Dict:
        """
        Called when a futures/options position is closed.
        Records outcome for algorithm learning.

        Args:
            position: Position model instance that was just closed

        Returns:
            Dict with analysis results
        """
        try:
            from apps.analytics.models import TradePerformance

            # Create or get TradePerformance record
            performance, created = TradePerformance.objects.get_or_create(
                position=position,
                defaults={
                    'entry_score': Decimal(str(position.algorithm_score or 0)),
                    'entry_conditions': position.entry_analysis or {},
                }
            )

            # Update with exit information
            performance.final_pnl = position.realized_pnl or Decimal('0')
            performance.exit_reason = getattr(position, 'close_reason', 'UNKNOWN')
            performance.hold_duration_minutes = self._calculate_hold_duration(position)

            # Track max profit/loss during trade (if available)
            if hasattr(position, 'max_profit_during_trade'):
                performance.max_profit_during_trade = position.max_profit_during_trade
            if hasattr(position, 'max_drawdown_during_trade'):
                performance.max_drawdown_during_trade = position.max_drawdown_during_trade

            # Check if averaging was used and if it helped
            performance.was_averaged = getattr(position, 'was_averaged', False)
            if performance.was_averaged:
                # Averaging helped if final P&L is positive
                performance.averaging_helped = (performance.final_pnl or 0) > 0

            performance.save()

            logger.info(
                f"Recorded trade outcome for position {position.id}: "
                f"P&L={performance.final_pnl}, Reason={performance.exit_reason}"
            )

            return {
                'success': True,
                'position_id': position.id,
                'final_pnl': float(performance.final_pnl),
                'exit_reason': performance.exit_reason,
                'hold_minutes': performance.hold_duration_minutes,
            }

        except Exception as e:
            logger.error(f"Error analyzing closed trade: {e}")
            return {'success': False, 'error': str(e)}

    def get_win_rate_by_score(self, min_trades: int = 10) -> Dict:
        """
        Calculate win rate grouped by entry score ranges.

        Returns:
            Dict with score ranges and corresponding win rates
        """
        try:
            from apps.analytics.models import TradePerformance

            ranges = [
                ('60-70', 60, 70),
                ('70-80', 70, 80),
                ('80-90', 80, 90),
                ('90+', 90, 100),
            ]

            results = {}
            for label, min_score, max_score in ranges:
                trades = TradePerformance.objects.filter(
                    entry_score__gte=min_score,
                    entry_score__lt=max_score,
                    final_pnl__isnull=False
                )

                if trades.count() >= min_trades:
                    winners = trades.filter(final_pnl__gt=0).count()
                    total = trades.count()
                    avg_pnl = trades.aggregate(avg=Avg('final_pnl'))['avg'] or 0

                    results[label] = {
                        'trades': total,
                        'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
                        'avg_pnl': round(float(avg_pnl), 2),
                    }

            return results

        except Exception as e:
            logger.error(f"Error calculating win rate by score: {e}")
            return {}

    def get_best_performing_conditions(self, days: int = 30) -> Dict:
        """
        Identify which entry conditions led to best outcomes.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with insights about best-performing conditions
        """
        try:
            from apps.analytics.models import TradePerformance

            cutoff = timezone.now() - timedelta(days=days)

            # Get all closed trades in period
            trades = TradePerformance.objects.filter(
                created_at__gte=cutoff,
                final_pnl__isnull=False
            )

            if trades.count() < 5:
                return {'message': 'Insufficient data for analysis'}

            # Calculate overall stats
            total_trades = trades.count()
            winners = trades.filter(final_pnl__gt=0).count()
            total_pnl = trades.aggregate(total=Sum('final_pnl'))['total'] or 0
            avg_pnl = trades.aggregate(avg=Avg('final_pnl'))['avg'] or 0

            return {
                'period_days': days,
                'total_trades': total_trades,
                'win_rate': round(winners / total_trades * 100, 1) if total_trades > 0 else 0,
                'total_pnl': round(float(total_pnl), 2),
                'avg_pnl': round(float(avg_pnl), 2),
            }

        except Exception as e:
            logger.error(f"Error getting best conditions: {e}")
            return {'error': str(e)}

    def generate_weekly_insights(self) -> Dict:
        """
        Generate insights from last week's trades.
        Called by weekly performance report task.

        Returns:
            Dict with weekly insights
        """
        try:
            from apps.analytics.models import TradePerformance

            week_ago = timezone.now() - timedelta(days=7)

            trades = TradePerformance.objects.filter(
                created_at__gte=week_ago,
                final_pnl__isnull=False
            )

            if trades.count() == 0:
                return {'message': 'No closed trades this week'}

            # Basic stats
            total = trades.count()
            winners = trades.filter(final_pnl__gt=0).count()
            losers = trades.filter(final_pnl__lt=0).count()
            total_pnl = trades.aggregate(total=Sum('final_pnl'))['total'] or 0

            # By exit reason
            by_exit_reason = {}
            for reason in ['STOP_LOSS_HIT', 'TARGET_HIT', 'TIME_EXIT', 'MANUAL']:
                reason_trades = trades.filter(exit_reason=reason)
                if reason_trades.exists():
                    by_exit_reason[reason] = {
                        'count': reason_trades.count(),
                        'avg_pnl': round(float(reason_trades.aggregate(avg=Avg('final_pnl'))['avg'] or 0), 2),
                    }

            # Averaging effectiveness
            avg_trades = trades.filter(was_averaged=True)
            averaging_stats = None
            if avg_trades.exists():
                helped = avg_trades.filter(averaging_helped=True).count()
                averaging_stats = {
                    'trades_with_averaging': avg_trades.count(),
                    'averaging_helped_pct': round(helped / avg_trades.count() * 100, 1),
                }

            return {
                'week_ending': timezone.now().date().isoformat(),
                'total_trades': total,
                'winners': winners,
                'losers': losers,
                'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
                'total_pnl': round(float(total_pnl), 2),
                'by_exit_reason': by_exit_reason,
                'averaging_stats': averaging_stats,
            }

        except Exception as e:
            logger.error(f"Error generating weekly insights: {e}")
            return {'error': str(e)}

    def _calculate_hold_duration(self, position) -> int:
        """Calculate how long a position was held in minutes."""
        if hasattr(position, 'closed_at') and position.closed_at:
            if hasattr(position, 'created_at') and position.created_at:
                delta = position.closed_at - position.created_at
                return int(delta.total_seconds() // 60)
        return 0


# Module-level instance
_learner = None


def get_algorithm_learner() -> AlgorithmLearner:
    """Get or create global AlgorithmLearner instance."""
    global _learner
    if _learner is None:
        _learner = AlgorithmLearner()
    return _learner
