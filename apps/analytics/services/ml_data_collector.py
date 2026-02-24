"""
ML Data Collector Service for mCube Trading System

Collects and logs user decisions on trade suggestions for ML training.
Provides functions to:
- Log user decisions with market context
- Capture market state snapshots
- Link trade outcomes back to decisions
- Compute user behavior profiles
- Export training data
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone
from django.contrib.auth.models import User

from apps.analytics.models import (
    UserDecisionLog,
    MarketContextSnapshot,
    UserBehaviorProfile,
)
from apps.trading.models import TradeSuggestion

logger = logging.getLogger(__name__)


class MLDataCollector:
    """
    Service for collecting ML training data from user decisions.
    """

    # VIX threshold for high/low classification
    VIX_THRESHOLD = Decimal('18.00')

    def log_user_decision(
        self,
        user: User,
        suggestion: TradeSuggestion,
        decision_type: str,
        decision_notes: str = '',
        modified_parameters: Optional[Dict] = None,
    ) -> UserDecisionLog:
        """
        Log a user's decision on a trade suggestion.

        Args:
            user: The user making the decision
            suggestion: The trade suggestion being acted upon
            decision_type: One of APPROVE, REJECT, MODIFY, IGNORE, AUTO_APPROVE
            decision_notes: Optional notes explaining the decision
            modified_parameters: For MODIFY decisions, the changed parameters

        Returns:
            UserDecisionLog: The created decision log
        """
        try:
            # Calculate time to decision
            time_to_decision = None
            if suggestion.created_at:
                delta = timezone.now() - suggestion.created_at
                time_to_decision = int(delta.total_seconds())

            # Capture current market context
            market_snapshot = self.capture_market_context()

            # Build market context dict
            market_context = {}
            if market_snapshot:
                market_context = {
                    'nifty_spot': float(market_snapshot.nifty_spot) if market_snapshot.nifty_spot else None,
                    'banknifty_spot': float(market_snapshot.banknifty_spot) if market_snapshot.banknifty_spot else None,
                    'vix': float(market_snapshot.india_vix) if market_snapshot.india_vix else None,
                    'pcr_oi': float(market_snapshot.pcr_oi) if market_snapshot.pcr_oi else None,
                    'trend': market_snapshot.nifty_trend,
                    'rsi': float(market_snapshot.rsi_14) if market_snapshot.rsi_14 else None,
                }

            # Extract original parameters from suggestion
            original_parameters = {
                'strategy': suggestion.strategy,
                'instrument': suggestion.instrument,
                'direction': suggestion.direction,
                'spot_price': float(suggestion.spot_price) if suggestion.spot_price else None,
                'vix': float(suggestion.vix) if suggestion.vix else None,
                'call_strike': float(suggestion.call_strike) if suggestion.call_strike else None,
                'put_strike': float(suggestion.put_strike) if suggestion.put_strike else None,
                'recommended_lots': suggestion.recommended_lots,
                'margin_required': float(suggestion.margin_required) if suggestion.margin_required else None,
            }

            # Extract algorithm confidence
            algorithm_confidence = None
            algorithm_signal_strength = None
            if suggestion.algorithm_reasoning:
                reasoning = suggestion.algorithm_reasoning
                algorithm_confidence = reasoning.get('confidence_score') or reasoning.get('llm_confidence')
                algorithm_signal_strength = reasoning.get('signal_strength') or reasoning.get('composite_score')

            # Create decision log
            decision_log = UserDecisionLog.objects.create(
                user=user,
                suggestion=suggestion,
                decision_type=decision_type,
                time_to_decision_seconds=time_to_decision,
                market_context=market_context,
                market_snapshot=market_snapshot,
                algorithm_confidence=algorithm_confidence,
                algorithm_signal_strength=algorithm_signal_strength,
                original_parameters=original_parameters,
                modified_parameters=modified_parameters or {},
                decision_notes=decision_notes,
                final_outcome='PENDING' if decision_type in ['APPROVE', 'AUTO_APPROVE', 'MODIFY'] else 'N/A',
            )

            logger.info(
                f"Logged decision: {user.username} {decision_type} suggestion #{suggestion.id} "
                f"(took {time_to_decision}s)"
            )

            return decision_log

        except Exception as e:
            logger.error(f"Error logging user decision: {e}", exc_info=True)
            raise

    def capture_market_context(self) -> Optional[MarketContextSnapshot]:
        """
        Capture current market state snapshot.

        Returns:
            MarketContextSnapshot: The created snapshot, or None if data unavailable
        """
        try:
            from apps.data.services.market_data import get_current_market_data

            # Get current market data
            market_data = get_current_market_data()
            if not market_data:
                logger.warning("No market data available for snapshot")
                return None

            # Determine trend
            trend = self._calculate_trend(market_data)

            # Create snapshot
            snapshot = MarketContextSnapshot.objects.create(
                snapshot_timestamp=timezone.now(),
                nifty_spot=market_data.get('nifty_spot'),
                banknifty_spot=market_data.get('banknifty_spot'),
                india_vix=market_data.get('vix'),
                nifty_day_change_pct=market_data.get('nifty_change_pct'),
                nifty_trend=trend,
                total_call_oi=market_data.get('total_call_oi'),
                total_put_oi=market_data.get('total_put_oi'),
                pcr_oi=market_data.get('pcr_oi'),
                max_pain=market_data.get('max_pain'),
                rsi_14=market_data.get('rsi_14'),
                macd_signal=market_data.get('macd_signal', ''),
                raw_data=market_data,
            )

            return snapshot

        except ImportError:
            logger.warning("Market data service not available")
            return None
        except Exception as e:
            logger.error(f"Error capturing market context: {e}", exc_info=True)
            return None

    def _calculate_trend(self, market_data: Dict) -> str:
        """Determine market trend from market data."""
        change_pct = market_data.get('nifty_change_pct')
        if change_pct is None:
            return ''

        try:
            change = float(change_pct)
            if change > 1.0:
                return 'STRONG_UP'
            elif change > 0.3:
                return 'UP'
            elif change < -1.0:
                return 'STRONG_DOWN'
            elif change < -0.3:
                return 'DOWN'
            else:
                return 'SIDEWAYS'
        except (TypeError, ValueError):
            return ''

    @transaction.atomic
    def link_outcome_to_decision(
        self,
        decision_log_id: int,
        pnl: Decimal,
        outcome: str,
    ) -> bool:
        """
        Link trade outcome back to the user decision log.

        Args:
            decision_log_id: ID of the UserDecisionLog
            pnl: Final P&L of the trade
            outcome: One of PROFIT, LOSS, BREAKEVEN

        Returns:
            bool: True if successful
        """
        try:
            decision_log = UserDecisionLog.objects.get(id=decision_log_id)

            decision_log.final_pnl = pnl
            decision_log.final_outcome = outcome
            decision_log.outcome_linked_at = timezone.now()
            decision_log.save()

            logger.info(
                f"Linked outcome to decision #{decision_log_id}: "
                f"{outcome} with P&L Rs.{pnl:,.2f}"
            )

            return True

        except UserDecisionLog.DoesNotExist:
            logger.error(f"Decision log {decision_log_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error linking outcome: {e}", exc_info=True)
            return False

    def link_outcomes_for_closed_trades(self) -> Dict[str, int]:
        """
        Batch process to link outcomes for all closed trades.

        Returns:
            Dict with counts of processed records
        """
        try:
            # Find decision logs with PENDING outcome where trade has closed
            pending_logs = UserDecisionLog.objects.filter(
                final_outcome='PENDING',
                decision_type__in=['APPROVE', 'AUTO_APPROVE', 'MODIFY'],
            ).select_related('suggestion')

            linked_count = 0
            error_count = 0

            for log in pending_logs:
                try:
                    suggestion = log.suggestion

                    # Check if suggestion has a taken trade that's closed
                    if hasattr(suggestion, 'taken_trade'):
                        taken_trade = suggestion.taken_trade
                        if taken_trade.status == 'CLOSED':
                            # Determine outcome
                            if taken_trade.outcome == 'PROFIT':
                                outcome = 'PROFIT'
                            elif taken_trade.outcome == 'LOSS':
                                outcome = 'LOSS'
                            else:
                                outcome = 'BREAKEVEN'

                            pnl = taken_trade.net_pnl or taken_trade.realized_pnl or Decimal('0.00')
                            self.link_outcome_to_decision(log.id, pnl, outcome)
                            linked_count += 1

                    # Also check suggestion status directly
                    elif suggestion.status in ['SUCCESSFUL', 'LOSS', 'BREAKEVEN', 'CLOSED']:
                        if suggestion.status == 'SUCCESSFUL':
                            outcome = 'PROFIT'
                        elif suggestion.status == 'LOSS':
                            outcome = 'LOSS'
                        else:
                            outcome = 'BREAKEVEN'

                        pnl = suggestion.realized_pnl or Decimal('0.00')
                        self.link_outcome_to_decision(log.id, pnl, outcome)
                        linked_count += 1

                except Exception as e:
                    logger.error(f"Error linking outcome for log {log.id}: {e}")
                    error_count += 1

            logger.info(f"Linked outcomes: {linked_count} successful, {error_count} errors")

            return {
                'linked': linked_count,
                'errors': error_count,
                'pending_checked': pending_logs.count(),
            }

        except Exception as e:
            logger.error(f"Error in batch outcome linking: {e}", exc_info=True)
            return {'linked': 0, 'errors': 1}

    @transaction.atomic
    def compute_user_behavior_profile(self, user: User) -> UserBehaviorProfile:
        """
        Compute aggregated behavior profile for a user.

        Args:
            user: The user to compute profile for

        Returns:
            UserBehaviorProfile: Updated or created profile
        """
        try:
            # Get or create profile
            profile, created = UserBehaviorProfile.objects.get_or_create(user=user)

            # Get all decision logs for user
            logs = UserDecisionLog.objects.filter(user=user)

            if not logs.exists():
                logger.info(f"No decision logs for user {user.username}")
                return profile

            # Count by decision type
            decision_counts = logs.values('decision_type').annotate(count=Count('id'))
            counts_dict = {item['decision_type']: item['count'] for item in decision_counts}

            profile.total_suggestions_received = logs.count()
            profile.suggestions_approved = counts_dict.get('APPROVE', 0) + counts_dict.get('AUTO_APPROVE', 0)
            profile.suggestions_rejected = counts_dict.get('REJECT', 0)
            profile.suggestions_modified = counts_dict.get('MODIFY', 0)
            profile.suggestions_ignored = counts_dict.get('IGNORE', 0)

            # Calculate rates
            total = profile.total_suggestions_received
            if total > 0:
                profile.approval_rate = Decimal(profile.suggestions_approved) / Decimal(total) * 100
                profile.modification_rate = Decimal(profile.suggestions_modified) / Decimal(total) * 100

            # Calculate timing metrics
            timing_logs = logs.exclude(time_to_decision_seconds__isnull=True)
            if timing_logs.exists():
                avg_time = timing_logs.aggregate(avg=Avg('time_to_decision_seconds'))['avg']
                profile.avg_decision_time_seconds = int(avg_time) if avg_time else 0

                # Median (approximate - use 50th percentile)
                times = list(timing_logs.values_list('time_to_decision_seconds', flat=True))
                times.sort()
                mid = len(times) // 2
                profile.median_decision_time_seconds = times[mid] if times else 0

            # Strategy-specific approval rates
            strategy_rates = {}
            strategies = logs.values_list('suggestion__strategy', flat=True).distinct()
            for strategy in strategies:
                if strategy:
                    strategy_logs = logs.filter(suggestion__strategy=strategy)
                    strategy_total = strategy_logs.count()
                    strategy_approved = strategy_logs.filter(
                        decision_type__in=['APPROVE', 'AUTO_APPROVE']
                    ).count()
                    if strategy_total > 0:
                        strategy_rates[strategy] = float(
                            Decimal(strategy_approved) / Decimal(strategy_total) * 100
                        )
            profile.strategy_approval_rates = strategy_rates

            # VIX-based approval rates
            high_vix_logs = logs.filter(
                market_context__vix__gt=float(self.VIX_THRESHOLD)
            )
            if high_vix_logs.exists():
                high_vix_approved = high_vix_logs.filter(
                    decision_type__in=['APPROVE', 'AUTO_APPROVE']
                ).count()
                profile.high_vix_approval_rate = Decimal(high_vix_approved) / Decimal(high_vix_logs.count()) * 100

            low_vix_logs = logs.filter(
                market_context__vix__lte=float(self.VIX_THRESHOLD)
            )
            if low_vix_logs.exists():
                low_vix_approved = low_vix_logs.filter(
                    decision_type__in=['APPROVE', 'AUTO_APPROVE']
                ).count()
                profile.low_vix_approval_rate = Decimal(low_vix_approved) / Decimal(low_vix_logs.count()) * 100

            # Win rate of approved trades
            approved_logs = logs.filter(
                decision_type__in=['APPROVE', 'AUTO_APPROVE'],
                final_outcome__in=['PROFIT', 'LOSS', 'BREAKEVEN'],
            )
            if approved_logs.exists():
                wins = approved_logs.filter(final_outcome='PROFIT').count()
                profile.approved_trades_win_rate = Decimal(wins) / Decimal(approved_logs.count()) * 100

            # Would-have-won rate for rejected trades (if we track this)
            # This requires backtesting rejected suggestions, left as TODO

            profile.decisions_included = logs.count()
            profile.save()

            logger.info(
                f"Computed behavior profile for {user.username}: "
                f"{profile.approval_rate:.1f}% approval rate, "
                f"{profile.avg_decision_time_seconds}s avg decision time"
            )

            return profile

        except Exception as e:
            logger.error(f"Error computing behavior profile for {user.username}: {e}", exc_info=True)
            raise

    def export_training_data(
        self,
        from_date: datetime,
        to_date: datetime,
        output_format: str = 'dict',
        include_incomplete: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Export training data for ML models.

        Args:
            from_date: Start date for data
            to_date: End date for data
            output_format: 'dict' for list of dicts, 'parquet' for Parquet file path
            include_incomplete: Whether to include decisions without outcome

        Returns:
            List of training data records, or path to Parquet file
        """
        try:
            # Query decision logs with their features
            queryset = UserDecisionLog.objects.filter(
                decision_timestamp__gte=from_date,
                decision_timestamp__lte=to_date,
            ).select_related('suggestion', 'market_snapshot', 'user')

            if not include_incomplete:
                queryset = queryset.exclude(final_outcome='PENDING')

            records = []
            for log in queryset:
                record = self._decision_log_to_training_record(log)
                if record:
                    records.append(record)

            logger.info(f"Exported {len(records)} training records from {from_date} to {to_date}")

            if output_format == 'parquet':
                return self._save_to_parquet(records, from_date, to_date)

            return records

        except Exception as e:
            logger.error(f"Error exporting training data: {e}", exc_info=True)
            return []

    def _decision_log_to_training_record(self, log: UserDecisionLog) -> Optional[Dict[str, Any]]:
        """Convert a decision log to a training record."""
        try:
            suggestion = log.suggestion
            market = log.market_context or {}

            record = {
                # Identifiers
                'decision_id': log.id,
                'user_id': log.user_id,
                'suggestion_id': suggestion.id if suggestion else None,
                'decision_timestamp': log.decision_timestamp.isoformat(),

                # Target
                'decision_type': log.decision_type,
                'final_outcome': log.final_outcome,
                'final_pnl': float(log.final_pnl) if log.final_pnl else None,

                # Market Features
                'spot_price': market.get('nifty_spot'),
                'vix': market.get('vix'),
                'pcr_oi': market.get('pcr_oi'),
                'trend': market.get('trend'),

                # Algorithm Features
                'algo_confidence': float(log.algorithm_confidence) if log.algorithm_confidence else None,
                'algo_signal_strength': float(log.algorithm_signal_strength) if log.algorithm_signal_strength else None,

                # Suggestion Features
                'strategy': suggestion.strategy if suggestion else None,
                'instrument': suggestion.instrument if suggestion else None,
                'direction': suggestion.direction if suggestion else None,
                'days_to_expiry': suggestion.days_to_expiry if suggestion else None,

                # Behavioral Features
                'time_to_decision_seconds': log.time_to_decision_seconds,
            }

            return record

        except Exception as e:
            logger.error(f"Error converting log {log.id} to record: {e}")
            return None

    def _save_to_parquet(
        self,
        records: List[Dict],
        from_date: datetime,
        to_date: datetime,
    ) -> str:
        """Save records to Parquet file."""
        try:
            import pandas as pd
            import os

            df = pd.DataFrame(records)

            # Create output directory if needed
            output_dir = '/tmp/ml_training_data'
            os.makedirs(output_dir, exist_ok=True)

            # Generate filename
            filename = f"training_data_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.parquet"
            filepath = os.path.join(output_dir, filename)

            df.to_parquet(filepath, index=False)

            logger.info(f"Saved training data to {filepath}")
            return filepath

        except ImportError:
            logger.error("pandas not installed for Parquet export")
            raise
        except Exception as e:
            logger.error(f"Error saving Parquet: {e}")
            raise


# Module-level convenience functions
_collector = None


def get_collector() -> MLDataCollector:
    """Get singleton MLDataCollector instance."""
    global _collector
    if _collector is None:
        _collector = MLDataCollector()
    return _collector


def log_user_decision(
    user: User,
    suggestion: TradeSuggestion,
    decision_type: str,
    decision_notes: str = '',
    modified_parameters: Optional[Dict] = None,
) -> UserDecisionLog:
    """
    Log a user's decision on a trade suggestion.
    Convenience wrapper for MLDataCollector.log_user_decision.
    """
    return get_collector().log_user_decision(
        user, suggestion, decision_type, decision_notes, modified_parameters
    )


def capture_market_context() -> Optional[MarketContextSnapshot]:
    """
    Capture current market state snapshot.
    Convenience wrapper for MLDataCollector.capture_market_context.
    """
    return get_collector().capture_market_context()


def link_outcome_to_decision(decision_log_id: int, pnl: Decimal, outcome: str) -> bool:
    """
    Link trade outcome back to the user decision log.
    Convenience wrapper for MLDataCollector.link_outcome_to_decision.
    """
    return get_collector().link_outcome_to_decision(decision_log_id, pnl, outcome)


def compute_user_behavior_profile(user: User) -> UserBehaviorProfile:
    """
    Compute aggregated behavior profile for a user.
    Convenience wrapper for MLDataCollector.compute_user_behavior_profile.
    """
    return get_collector().compute_user_behavior_profile(user)


def export_training_data(
    from_date: datetime,
    to_date: datetime,
    output_format: str = 'dict',
    include_incomplete: bool = False,
) -> List[Dict[str, Any]]:
    """
    Export training data for ML models.
    Convenience wrapper for MLDataCollector.export_training_data.
    """
    return get_collector().export_training_data(
        from_date, to_date, output_format, include_incomplete
    )
