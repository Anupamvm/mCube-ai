"""
Parameter Optimizer for mCube Trading System

Suggests parameter adjustments based on learned patterns to improve performance.

Example Suggestions:
- Adjust base_delta_pct from 0.5% to 0.6% (5% improvement expected)
- Change exit_time from 15:15 to 15:00 (8% improvement expected)
- Modify stop_loss_pct from 100% to 80% (risk reduction)
"""

import logging
from decimal import Decimal
from django.utils import timezone

from apps.analytics.models import LearningPattern, ParameterAdjustment, TradePerformance
from apps.core.constants import KOTAK_STRANGLE_PARAMS, ICICI_FUTURES_PARAMS

logger = logging.getLogger(__name__)


class ParameterOptimizer:
    """
    Optimizes trading parameters based on learned patterns.

    Usage:
        optimizer = ParameterOptimizer(session)
        suggestions = optimizer.generate_suggestions()
    """

    def __init__(self, session, confidence_threshold=70.0):
        """
        Initialize optimizer.

        Args:
            session: LearningSession to associate suggestions with
            confidence_threshold: Minimum confidence % to suggest changes
        """
        self.session = session
        self.confidence_threshold = Decimal(str(confidence_threshold))

    def generate_suggestions(self):
        """
        Generate all parameter adjustment suggestions.

        Returns:
            int: Number of suggestions created
        """
        suggestions_count = 0

        suggestions_count += self.suggest_timing_adjustments()
        suggestions_count += self.suggest_strike_adjustments()
        suggestions_count += self.suggest_risk_adjustments()

        return suggestions_count

    def suggest_timing_adjustments(self):
        """
        Suggest timing-related parameter adjustments.

        Example:
        - Adjust exit_time based on successful exit patterns
        - Adjust entry window based on successful entry times
        """
        logger.info("⏰ Analyzing timing parameters...")

        suggestions_count = 0

        # Find entry timing patterns with high success rates
        entry_patterns = LearningPattern.objects.filter(
            session=self.session,
            pattern_type='ENTRY_TIMING',
            is_actionable=True,
            confidence_score__gte=self.confidence_threshold
        ).order_by('-success_rate')

        if entry_patterns.exists():
            best_pattern = entry_patterns.first()
            conditions = best_pattern.conditions

            # Suggest adjusting entry window
            suggestion = ParameterAdjustment.objects.create(
                session=self.session,
                parameter_name='entry_window_start',
                parameter_category='strategy',
                current_value='09:00',
                suggested_value=f"{conditions.get('hour_range', [9])[0]}:00",
                reason=f"Pattern shows {best_pattern.success_rate}% success rate for this time window",
                supporting_data={
                    'pattern_id': best_pattern.id,
                    'pattern_name': best_pattern.name,
                    'occurrences': best_pattern.occurrences,
                },
                expected_improvement_pct=Decimal(str(best_pattern.success_rate - 50.0)),
                confidence=best_pattern.confidence_score,
                risk_level='LOW',
                status='SUGGESTED',
            )
            suggestions_count += 1
            logger.info(f"  ✅ Suggested: {suggestion}")

        # Find exit timing patterns
        exit_patterns = LearningPattern.objects.filter(
            session=self.session,
            pattern_type='EXIT_TIMING',
            is_actionable=True,
            confidence_score__gte=self.confidence_threshold
        ).order_by('-success_rate')

        if exit_patterns.exists():
            best_pattern = exit_patterns.first()

            # Suggest exit day adjustment
            suggestion = ParameterAdjustment.objects.create(
                session=self.session,
                parameter_name='exit_day',
                parameter_category='strategy',
                current_value='THURSDAY',
                suggested_value=best_pattern.conditions.get('exit_day', 'THURSDAY'),
                reason=f"Pattern shows {best_pattern.success_rate}% success rate for exits on this day",
                supporting_data={
                    'pattern_id': best_pattern.id,
                    'pattern_name': best_pattern.name,
                },
                expected_improvement_pct=Decimal(str(best_pattern.success_rate - 50.0)),
                confidence=best_pattern.confidence_score,
                risk_level='LOW',
                status='SUGGESTED',
            )
            suggestions_count += 1
            logger.info(f"  ✅ Suggested: {suggestion}")

        return suggestions_count

    def suggest_strike_adjustments(self):
        """
        Suggest strike selection parameter adjustments.

        Example:
        - Adjust base_delta_pct based on successful strikes
        """
        logger.info("🎯 Analyzing strike selection parameters...")

        suggestions_count = 0

        # Find strike selection patterns
        strike_patterns = LearningPattern.objects.filter(
            session=self.session,
            pattern_type='STRIKE_SELECTION',
            is_actionable=True,
            confidence_score__gte=self.confidence_threshold
        ).order_by('-success_rate')

        # TODO: Implement strike-based suggestions when we have strike patterns

        return suggestions_count

    def suggest_risk_adjustments(self):
        """
        Suggest risk management parameter adjustments.

        Example:
        - Adjust stop_loss_pct based on observed loss patterns
        - Adjust target_pct based on observed profit patterns
        """
        logger.info("⚠️  Analyzing risk parameters...")

        suggestions_count = 0

        # Analyze average losses
        performances = TradePerformance.objects.filter(
            position__realized_pnl__lt=0
        )

        if performances.count() >= 10:
            avg_loss_pct = self._calculate_average_loss_percentage(performances)

            # If average loss is significantly different from current stop loss
            current_stop_loss = Decimal('100.0')  # 100% of premium
            if abs(avg_loss_pct - current_stop_loss) > 10:
                # Suggest adjustment
                suggested_stop_loss = avg_loss_pct * Decimal('0.9')  # 10% buffer

                suggestion = ParameterAdjustment.objects.create(
                    session=self.session,
                    parameter_name='stop_loss_pct',
                    parameter_category='risk',
                    current_value=str(current_stop_loss),
                    suggested_value=str(suggested_stop_loss),
                    reason=f"Historical average loss is {avg_loss_pct}%. Adjust stop loss to match reality.",
                    supporting_data={
                        'avg_loss_pct': float(avg_loss_pct),
                        'sample_size': performances.count(),
                    },
                    expected_improvement_pct=Decimal('5.0'),  # Conservative estimate
                    confidence=Decimal('65.0'),
                    risk_level='MEDIUM',
                    status='SUGGESTED',
                )
                suggestions_count += 1
                logger.info(f"  ✅ Suggested: {suggestion}")

        return suggestions_count

    def _calculate_average_loss_percentage(self, loss_performances):
        """Calculate average loss as percentage of entry value."""
        total_loss_pct = Decimal('0.0')
        count = 0

        for perf in loss_performances:
            if perf.position.entry_price and perf.position.quantity:
                entry_value = abs(perf.position.entry_price * perf.position.quantity)
                if entry_value > 0:
                    loss_pct = (abs(perf.position.realized_pnl) / entry_value) * 100
                    total_loss_pct += loss_pct
                    count += 1

        return total_loss_pct / Decimal(count) if count > 0 else Decimal('0.0')

    def apply_suggestion(self, suggestion, reviewed_by):
        """
        Apply a parameter suggestion (mark as approved).

        Args:
            suggestion: ParameterAdjustment to apply
            reviewed_by: User who is approving this

        Returns:
            bool: True if successfully applied
        """
        if suggestion.status not in ['SUGGESTED', 'TESTING']:
            logger.warning(f"Cannot apply suggestion {suggestion.id} - status is {suggestion.status}")
            return False

        suggestion.status = 'APPROVED'
        suggestion.reviewed_by = reviewed_by
        suggestion.reviewed_at = timezone.now()
        suggestion.save()

        logger.info(f"✅ Parameter suggestion approved: {suggestion.parameter_name}")

        # TODO: Actually apply the parameter change to the system
        # This might involve updating strategy configurations

        return True

    def reject_suggestion(self, suggestion, reviewed_by, reason=""):
        """
        Reject a parameter suggestion.

        Args:
            suggestion: ParameterAdjustment to reject
            reviewed_by: User who is rejecting this
            reason: Reason for rejection
        """
        suggestion.status = 'REJECTED'
        suggestion.reviewed_by = reviewed_by
        suggestion.reviewed_at = timezone.now()
        suggestion.review_notes = reason
        suggestion.save()

        logger.info(f"❌ Parameter suggestion rejected: {suggestion.parameter_name}")
