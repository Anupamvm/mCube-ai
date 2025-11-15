"""
Learning Engine for mCube Trading System

This engine analyzes past trades to discover patterns, optimize parameters,
and continuously improve trading performance.

Key Features:
- Analyzes trade performance in detail
- Discovers profitable patterns
- Suggests parameter adjustments
- Tracks improvement over time
- Provides actionable insights
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Avg, Sum, Count, Q

from apps.analytics.models import (
    LearningSession,
    TradePerformance,
    LearningPattern,
    ParameterAdjustment,
    PerformanceMetric,
)
from apps.positions.models import Position

logger = logging.getLogger(__name__)


class LearningEngine:
    """
    Main learning engine that coordinates all learning activities.

    Usage:
        engine = LearningEngine()
        session = engine.start_learning("My Learning Session")
        engine.analyze_trades(session)
        engine.discover_patterns(session)
        engine.suggest_improvements(session)
        engine.stop_learning(session)
    """

    def __init__(self, min_trades=10, confidence_threshold=70.0):
        """
        Initialize the learning engine.

        Args:
            min_trades: Minimum number of trades required to start learning
            confidence_threshold: Minimum confidence percentage for suggestions
        """
        self.min_trades = min_trades
        self.confidence_threshold = Decimal(str(confidence_threshold))
        logger.info(f"Learning Engine initialized (min_trades={min_trades}, confidence={confidence_threshold}%)")

    def start_learning(self, name="Auto Learning Session"):
        """
        Start a new learning session.

        Args:
            name: Name/description for this learning session

        Returns:
            LearningSession: The created session object
        """
        # Check if there's already an active session
        active_session = LearningSession.objects.filter(status='RUNNING').first()
        if active_session:
            logger.warning(f"Learning session '{active_session.name}' is already running")
            return active_session

        # Create new session
        session = LearningSession.objects.create(
            name=name,
            status='RUNNING',
            started_at=timezone.now(),
            min_trades_required=self.min_trades,
            confidence_threshold=self.confidence_threshold,
        )

        logger.info(f"✅ Learning session started: {name}")
        return session

    def stop_learning(self, session):
        """
        Stop a learning session.

        Args:
            session: The LearningSession to stop
        """
        if not session.is_active():
            logger.warning(f"Session '{session.name}' is not running")
            return

        session.status = 'STOPPED'
        session.stopped_at = timezone.now()
        session.save()

        logger.info(f"⏸️  Learning session stopped: {session.name}")

    def pause_learning(self, session):
        """Pause a learning session."""
        if not session.is_active():
            logger.warning(f"Session '{session.name}' is not running")
            return

        session.status = 'PAUSED'
        session.save()
        logger.info(f"⏸️  Learning session paused: {session.name}")

    def resume_learning(self, session):
        """Resume a paused learning session."""
        if session.status != 'PAUSED':
            logger.warning(f"Session '{session.name}' is not paused")
            return

        session.status = 'RUNNING'
        session.save()
        logger.info(f"▶️  Learning session resumed: {session.name}")

    def analyze_trades(self, session):
        """
        Analyze all closed positions to create performance records.

        This is the first step in the learning process.

        Args:
            session: The LearningSession to analyze trades for

        Returns:
            int: Number of trades analyzed
        """
        logger.info(f"🔍 Analyzing trades for session: {session.name}")

        # Get all closed positions that don't have performance analysis yet
        positions = Position.objects.filter(
            status='CLOSED',
            performance_analysis__isnull=True
        ).select_related('account', 'strategy')

        if not positions.exists():
            logger.info("No new trades to analyze")
            return 0

        analyzed_count = 0
        for position in positions:
            try:
                self._analyze_single_trade(position)
                analyzed_count += 1
            except Exception as e:
                logger.error(f"Error analyzing trade {position.id}: {e}")

        # Update session stats
        session.trades_analyzed += analyzed_count
        session.save()

        logger.info(f"✅ Analyzed {analyzed_count} trades")
        return analyzed_count

    def _analyze_single_trade(self, position):
        """
        Analyze a single trade in detail.

        Args:
            position: The Position object to analyze
        """
        # Calculate hold duration
        if position.exit_time and position.entry_time:
            hold_duration = (position.exit_time - position.entry_time).total_seconds() / 60
        else:
            hold_duration = 0

        # Calculate max favorable/adverse excursion
        # TODO: This requires tick-by-tick data tracking
        max_favorable = position.unrealized_pnl if position.unrealized_pnl > 0 else Decimal('0.00')
        max_adverse = abs(position.unrealized_pnl) if position.unrealized_pnl < 0 else Decimal('0.00')

        # Calculate entry score (0-100)
        entry_score = self._calculate_entry_score(position)

        # Calculate exit score
        exit_score = self._calculate_exit_score(position) if position.exit_time else None

        # Determine entry time quality
        entry_time_quality = self._assess_entry_time_quality(position)

        # Create performance record
        performance = TradePerformance.objects.create(
            position=position,
            entry_conditions=self._extract_entry_conditions(position),
            entry_score=entry_score,
            exit_conditions=self._extract_exit_conditions(position),
            exit_score=exit_score,
            max_favorable_excursion=max_favorable,
            max_adverse_excursion=max_adverse,
            hold_duration_minutes=int(hold_duration),
            entry_time_quality=entry_time_quality,
            what_worked=self._identify_what_worked(position),
            what_failed=self._identify_what_failed(position),
            lessons_learned=self._generate_lessons(position),
        )

        logger.debug(f"Created performance analysis for {position.symbol}")
        return performance

    def _calculate_entry_score(self, position):
        """
        Calculate entry quality score (0-100).

        Factors:
        - Profit/loss outcome
        - Adherence to strategy rules
        - Market conditions alignment
        - Risk/reward ratio
        """
        score = Decimal('50.00')  # Start at neutral

        # Profit/loss factor (+/- 30 points)
        if position.realized_pnl > 0:
            # Profitable trade
            pnl_ratio = position.realized_pnl / abs(position.entry_price * position.quantity)
            score += min(Decimal('30.00'), pnl_ratio * Decimal('100.00'))
        else:
            # Losing trade
            pnl_ratio = abs(position.realized_pnl) / abs(position.entry_price * position.quantity)
            score -= min(Decimal('30.00'), pnl_ratio * Decimal('100.00'))

        # TODO: Add more factors:
        # - Strategy rule adherence
        # - Market condition alignment
        # - Risk/reward ratio

        # Clamp to 0-100
        return max(Decimal('0.00'), min(Decimal('100.00'), score))

    def _calculate_exit_score(self, position):
        """Calculate exit quality score (0-100)."""
        if not position.exit_time:
            return None

        score = Decimal('50.00')

        # Was it profitable?
        if position.realized_pnl > 0:
            score += Decimal('20.00')

        # Did we exit at the right time? (TODO: needs more sophisticated analysis)

        return max(Decimal('0.00'), min(Decimal('100.00'), score))

    def _assess_entry_time_quality(self, position):
        """Assess the quality of entry timing."""
        entry_hour = position.entry_time.hour if position.entry_time else 9

        # Market hours: 9:15 AM to 3:30 PM
        if 9 <= entry_hour < 10:
            return 'GOOD'  # Early morning often good
        elif 10 <= entry_hour < 14:
            return 'AVERAGE'
        elif 14 <= entry_hour < 16:
            return 'POOR'  # Late entries risky
        else:
            return 'POOR'

    def _extract_entry_conditions(self, position):
        """Extract market conditions at entry time."""
        # TODO: Fetch actual market data from entry time
        return {
            'entry_time': position.entry_time.isoformat() if position.entry_time else None,
            'entry_price': float(position.entry_price),
            'strategy': position.strategy.name if position.strategy else 'Unknown',
            'account': position.account.broker,
            # Add more conditions: VIX, trend, indicators, etc.
        }

    def _extract_exit_conditions(self, position):
        """Extract market conditions at exit time."""
        if not position.exit_time:
            return {}

        return {
            'exit_time': position.exit_time.isoformat(),
            'exit_price': float(position.exit_price) if position.exit_price else 0.0,
            'hold_duration_hours': (position.exit_time - position.entry_time).total_seconds() / 3600,
            # Add more conditions
        }

    def _identify_what_worked(self, position):
        """Identify what aspects of the trade worked well."""
        insights = []

        if position.realized_pnl > 0:
            insights.append(f"Profitable trade: +₹{position.realized_pnl:,.2f}")

        # TODO: Add more sophisticated analysis
        # - Good entry timing
        # - Good strike selection
        # - Good market conditions

        return " | ".join(insights) if insights else "Analysis pending"

    def _identify_what_failed(self, position):
        """Identify what aspects of the trade didn't work."""
        insights = []

        if position.realized_pnl < 0:
            insights.append(f"Lost ₹{abs(position.realized_pnl):,.2f}")

        # TODO: Add more analysis

        return " | ".join(insights) if insights else "Analysis pending"

    def _generate_lessons(self, position):
        """Generate key lessons from this trade."""
        lessons = []

        # TODO: Implement sophisticated lesson generation
        # - Pattern matching with historical trades
        # - Correlation analysis
        # - Statistical insights

        return " | ".join(lessons) if lessons else "Learning in progress"

    def discover_patterns(self, session):
        """
        Discover patterns in trade performance.

        This analyzes all TradePerformance records to find patterns
        that correlate with profitable or unprofitable trades.

        Args:
            session: The LearningSession

        Returns:
            int: Number of patterns discovered
        """
        logger.info(f"🔎 Discovering patterns for session: {session.name}")

        # Import here to avoid circular dependency
        from apps.analytics.services.pattern_recognition import PatternRecognizer

        recognizer = PatternRecognizer(session)
        patterns_found = recognizer.discover_all_patterns()

        session.patterns_discovered = patterns_found
        session.save()

        logger.info(f"✅ Discovered {patterns_found} patterns")
        return patterns_found

    def suggest_improvements(self, session):
        """
        Suggest parameter improvements based on learned patterns.

        Args:
            session: The LearningSession

        Returns:
            int: Number of suggestions created
        """
        logger.info(f"💡 Generating improvement suggestions for session: {session.name}")

        # Import here to avoid circular dependency
        from apps.analytics.services.parameter_optimizer import ParameterOptimizer

        optimizer = ParameterOptimizer(session, confidence_threshold=self.confidence_threshold)
        suggestions_count = optimizer.generate_suggestions()

        session.parameters_adjusted = suggestions_count
        session.save()

        logger.info(f"✅ Created {suggestions_count} parameter suggestions")
        return suggestions_count

    def calculate_metrics(self, session, time_period='all'):
        """
        Calculate performance metrics for the session.

        Args:
            session: The LearningSession
            time_period: 'all', 'last_7_days', 'last_30_days', etc.

        Returns:
            dict: Dictionary of calculated metrics
        """
        logger.info(f"📊 Calculating metrics for {time_period}")

        # Get positions based on time period
        positions = Position.objects.filter(status='CLOSED')

        if time_period == 'last_7_days':
            cutoff = timezone.now() - timedelta(days=7)
            positions = positions.filter(exit_time__gte=cutoff)
        elif time_period == 'last_30_days':
            cutoff = timezone.now() - timedelta(days=30)
            positions = positions.filter(exit_time__gte=cutoff)

        if not positions.exists():
            return {}

        # Calculate metrics
        total_trades = positions.count()
        winning_trades = positions.filter(realized_pnl__gt=0).count()
        losing_trades = positions.filter(realized_pnl__lt=0).count()

        win_rate = (Decimal(winning_trades) / Decimal(total_trades)) * 100 if total_trades > 0 else Decimal('0.00')

        total_profit = positions.filter(realized_pnl__gt=0).aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0.00')
        total_loss = abs(positions.filter(realized_pnl__lt=0).aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0.00'))

        profit_factor = total_profit / total_loss if total_loss > 0 else Decimal('0.00')

        avg_profit = total_profit / Decimal(winning_trades) if winning_trades > 0 else Decimal('0.00')
        avg_loss = total_loss / Decimal(losing_trades) if losing_trades > 0 else Decimal('0.00')

        metrics = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': float(win_rate),
            'profit_factor': float(profit_factor),
            'avg_profit': float(avg_profit),
            'avg_loss': float(avg_loss),
            'total_pnl': float(total_profit - total_loss),
        }

        # Save metrics to database
        PerformanceMetric.objects.create(
            session=session,
            metric_type='WIN_RATE',
            metric_value=win_rate,
            time_period=time_period,
        )

        PerformanceMetric.objects.create(
            session=session,
            metric_type='PROFIT_FACTOR',
            metric_value=profit_factor,
            time_period=time_period,
        )

        logger.info(f"✅ Metrics calculated: Win Rate={win_rate:.2f}%, Profit Factor={profit_factor:.2f}")
        return metrics

    def get_session_summary(self, session):
        """
        Get a comprehensive summary of the learning session.

        Args:
            session: The LearningSession

        Returns:
            dict: Summary dictionary
        """
        patterns = LearningPattern.objects.filter(session=session)
        adjustments = ParameterAdjustment.objects.filter(session=session)

        return {
            'session_name': session.name,
            'status': session.status,
            'started_at': session.started_at,
            'stopped_at': session.stopped_at,
            'duration_hours': (
                (session.stopped_at - session.started_at).total_seconds() / 3600
                if session.stopped_at and session.started_at else 0
            ),
            'trades_analyzed': session.trades_analyzed,
            'patterns_discovered': session.patterns_discovered,
            'parameters_adjusted': session.parameters_adjusted,
            'actionable_patterns': patterns.filter(is_actionable=True).count(),
            'pending_suggestions': adjustments.filter(status='SUGGESTED').count(),
            'approved_suggestions': adjustments.filter(status='APPROVED').count(),
            'improvement_pct': float(session.improvement_pct),
        }
