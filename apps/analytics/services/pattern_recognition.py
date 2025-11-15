"""
Pattern Recognition Service for mCube Trading System

Discovers patterns in trade data that correlate with profitable or unprofitable outcomes.

Pattern Types:
- Entry Timing: What times of day work best
- Strike Selection: Which strikes are most profitable
- Market Conditions: What market states favor our strategies
- Delta Behavior: How delta movements affect outcomes
- Exit Timing: Optimal exit times
- VIX Patterns: How VIX levels affect trades
"""

import logging
from decimal import Decimal
from datetime import timedelta
from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.analytics.models import TradePerformance, LearningPattern
from apps.positions.models import Position

logger = logging.getLogger(__name__)


class PatternRecognizer:
    """
    Recognizes patterns in trade performance data.

    Usage:
        recognizer = PatternRecognizer(session)
        patterns_found = recognizer.discover_all_patterns()
    """

    def __init__(self, session, min_occurrences=5):
        """
        Initialize pattern recognizer.

        Args:
            session: LearningSession to associate patterns with
            min_occurrences: Minimum times a pattern must occur to be significant
        """
        self.session = session
        self.min_occurrences = min_occurrences

    def discover_all_patterns(self):
        """
        Run all pattern discovery algorithms.

        Returns:
            int: Total number of patterns discovered
        """
        patterns_found = 0

        patterns_found += self.discover_entry_timing_patterns()
        patterns_found += self.discover_strike_selection_patterns()
        patterns_found += self.discover_market_condition_patterns()
        patterns_found += self.discover_exit_timing_patterns()

        return patterns_found

    def discover_entry_timing_patterns(self):
        """
        Discover patterns related to entry timing.

        Example patterns:
        - Trades entered 9:15-10:00 AM have 75% win rate
        - Trades entered after 2:30 PM have 40% win rate
        """
        logger.info("🕐 Discovering entry timing patterns...")

        patterns_found = 0

        # Analyze by hour of day
        performances = TradePerformance.objects.select_related('position').all()

        hour_stats = {}
        for perf in performances:
            if not perf.position.entry_time:
                continue

            hour = perf.position.entry_time.hour
            if hour not in hour_stats:
                hour_stats[hour] = {'profitable': 0, 'unprofitable': 0, 'total': 0}

            hour_stats[hour]['total'] += 1
            if perf.position.realized_pnl > 0:
                hour_stats[hour]['profitable'] += 1
            else:
                hour_stats[hour]['unprofitable'] += 1

        # Create patterns for significant hours
        for hour, stats in hour_stats.items():
            if stats['total'] < self.min_occurrences:
                continue

            success_rate = (stats['profitable'] / stats['total']) * 100
            confidence = min(100.0, stats['total'] * 10)  # More data = more confidence

            # Only create pattern if statistically interesting (>60% or <40%)
            if success_rate > 60 or success_rate < 40:
                is_actionable = success_rate > 65  # High success rate = actionable

                recommendation = self._generate_timing_recommendation(hour, success_rate)

                pattern, created = LearningPattern.objects.update_or_create(
                    session=self.session,
                    pattern_type='ENTRY_TIMING',
                    name=f"Entry at {hour}:00-{hour+1}:00",
                    defaults={
                        'description': f"Trades entered between {hour}:00 and {hour+1}:00",
                        'conditions': {'hour_range': [hour, hour+1]},
                        'occurrences': stats['total'],
                        'profitable_occurrences': stats['profitable'],
                        'unprofitable_occurrences': stats['unprofitable'],
                        'success_rate': Decimal(str(success_rate)),
                        'confidence_score': Decimal(str(confidence)),
                        'is_actionable': is_actionable,
                        'recommendation': recommendation,
                        'validation_status': 'ACTIVE' if is_actionable else 'TESTING',
                    }
                )

                if created:
                    patterns_found += 1
                    logger.info(f"  Found pattern: {pattern.name} ({success_rate:.1f}% success)")

        return patterns_found

    def discover_strike_selection_patterns(self):
        """
        Discover patterns in strike selection for options.

        Example patterns:
        - Strikes 0.5% OTM have 70% success
        - Strikes ATM have 50% success
        """
        logger.info("🎯 Discovering strike selection patterns...")
        patterns_found = 0

        # TODO: Implement strike selection pattern discovery
        # This requires analyzing option positions and their strikes relative to spot

        return patterns_found

    def discover_market_condition_patterns(self):
        """
        Discover patterns related to market conditions.

        Example patterns:
        - When VIX < 15, win rate is 65%
        - When Nifty trending up, long positions have 80% success
        """
        logger.info("📊 Discovering market condition patterns...")
        patterns_found = 0

        # TODO: Implement market condition pattern discovery
        # This requires market data (VIX, trends, etc.) to be stored with trades

        return patterns_found

    def discover_exit_timing_patterns(self):
        """
        Discover patterns related to exit timing.

        Example patterns:
        - Exits on Thursday at 3:15 PM have 70% success
        - Holding for 2+ days reduces success to 50%
        """
        logger.info("🚪 Discovering exit timing patterns...")
        patterns_found = 0

        # Analyze by day of week
        performances = TradePerformance.objects.select_related('position').all()

        day_stats = {}
        for perf in performances:
            if not perf.position.exit_time:
                continue

            day = perf.position.exit_time.strftime('%A')  # Monday, Tuesday, etc.
            if day not in day_stats:
                day_stats[day] = {'profitable': 0, 'unprofitable': 0, 'total': 0}

            day_stats[day]['total'] += 1
            if perf.position.realized_pnl > 0:
                day_stats[day]['profitable'] += 1
            else:
                day_stats[day]['unprofitable'] += 1

        # Create patterns for significant days
        for day, stats in day_stats.items():
            if stats['total'] < self.min_occurrences:
                continue

            success_rate = (stats['profitable'] / stats['total']) * 100
            confidence = min(100.0, stats['total'] * 10)

            if success_rate > 60 or success_rate < 40:
                is_actionable = success_rate > 65

                pattern, created = LearningPattern.objects.update_or_create(
                    session=self.session,
                    pattern_type='EXIT_TIMING',
                    name=f"Exit on {day}",
                    defaults={
                        'description': f"Positions exited on {day}",
                        'conditions': {'exit_day': day},
                        'occurrences': stats['total'],
                        'profitable_occurrences': stats['profitable'],
                        'unprofitable_occurrences': stats['unprofitable'],
                        'success_rate': Decimal(str(success_rate)),
                        'confidence_score': Decimal(str(confidence)),
                        'is_actionable': is_actionable,
                        'recommendation': f"{'Favor' if success_rate > 60 else 'Avoid'} exits on {day}",
                        'validation_status': 'ACTIVE' if is_actionable else 'TESTING',
                    }
                )

                if created:
                    patterns_found += 1
                    logger.info(f"  Found pattern: {pattern.name} ({success_rate:.1f}% success)")

        return patterns_found

    def _generate_timing_recommendation(self, hour, success_rate):
        """Generate timing recommendation based on success rate."""
        if success_rate > 70:
            return f"STRONG BUY: Highly favorable entry time (hour {hour})"
        elif success_rate > 60:
            return f"BUY: Favorable entry time (hour {hour})"
        elif success_rate < 40:
            return f"AVOID: Poor entry time (hour {hour})"
        else:
            return f"NEUTRAL: Average entry time (hour {hour})"

    def validate_pattern(self, pattern, new_trades_count=10):
        """
        Validate an existing pattern with new data.

        Args:
            pattern: LearningPattern to validate
            new_trades_count: Number of recent trades to test against

        Returns:
            bool: True if pattern is still valid
        """
        # TODO: Implement pattern validation
        # Test pattern against recent trades to see if it still holds

        return True
