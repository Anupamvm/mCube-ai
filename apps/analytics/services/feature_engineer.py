"""
Feature Engineer Service for mCube Trading System

Pre-computes and stores ML features for user decisions:
- Market features (spot, vix, technical indicators)
- Time features (day of week, hour, expiry)
- User behavior features
- Recent performance features
- Outcome labels for training
"""

import logging
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

import numpy as np
from django.db import transaction
from django.db.models import Avg, Sum, Count, Q
from django.utils import timezone

from apps.analytics.models import (
    UserDecisionLog,
    MLFeatureStore,
    MarketContextSnapshot,
    UserBehaviorProfile,
)
from apps.trading.models import TakenTrade

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """
    Service for computing ML features from user decisions.
    """

    # Feature version for tracking schema changes
    FEATURE_VERSION = 'v1'

    # Ordered list of feature columns (must match feature_vector output)
    FEATURE_COLUMNS = [
        # Market features
        'spot_price',
        'vix',
        'vix_percentile_30d',
        'pcr_oi',
        'pcr_volume',
        'max_pain_distance_pct',

        # Trend features
        'spot_vs_sma20',
        'spot_vs_sma50',
        'rsi_14',
        'macd_histogram',

        # Time features
        'day_of_week',
        'hour_of_day',
        'days_to_expiry',
        'is_expiry_week',
        'is_monthly_expiry',

        # Algorithm features
        'algo_confidence',
        'algo_signal_strength',

        # User behavior features
        'user_historical_approval_rate',
        'user_avg_decision_time',
        'user_win_rate',

        # Recent performance features
        'last_5_trades_pnl',
        'last_5_trades_win_rate',
        'current_streak',
        'current_day_pnl',
    ]

    def compute_features(self, decision_log: UserDecisionLog) -> Optional[MLFeatureStore]:
        """
        Compute all features for a user decision.

        Args:
            decision_log: The user decision to compute features for

        Returns:
            MLFeatureStore: The created feature store record
        """
        try:
            # Check if features already computed
            if hasattr(decision_log, 'ml_features'):
                logger.info(f"Features already exist for decision {decision_log.id}")
                return decision_log.ml_features

            # Initialize feature store
            feature_store = MLFeatureStore(
                decision_log=decision_log,
                feature_version=self.FEATURE_VERSION,
            )

            # Compute market features
            self._compute_market_features(feature_store, decision_log)

            # Compute time features
            self._compute_time_features(feature_store, decision_log)

            # Compute algorithm features
            self._compute_algorithm_features(feature_store, decision_log)

            # Compute user behavior features
            self._compute_user_features(feature_store, decision_log)

            # Compute recent performance features
            self._compute_performance_features(feature_store, decision_log)

            # Build feature vector
            feature_store.feature_vector = self._build_feature_vector(feature_store)

            # Mark as complete if all key features present
            feature_store.is_complete = self._check_completeness(feature_store)
            feature_store.computed_at = timezone.now()

            feature_store.save()

            logger.info(
                f"Computed features for decision {decision_log.id} "
                f"(complete: {feature_store.is_complete})"
            )

            return feature_store

        except Exception as e:
            logger.error(f"Error computing features for decision {decision_log.id}: {e}", exc_info=True)
            return None

    def _compute_market_features(
        self,
        feature_store: MLFeatureStore,
        decision_log: UserDecisionLog,
    ):
        """Compute market-related features."""
        try:
            market_context = decision_log.market_context or {}
            snapshot = decision_log.market_snapshot

            # Basic market data
            feature_store.spot_price = Decimal(str(market_context.get('nifty_spot', 0))) or None
            feature_store.vix = Decimal(str(market_context.get('vix', 0))) or None

            if snapshot:
                feature_store.pcr_oi = snapshot.pcr_oi
                feature_store.rsi_14 = snapshot.rsi_14

                # Max pain distance
                if snapshot.max_pain and feature_store.spot_price:
                    distance = ((feature_store.spot_price - snapshot.max_pain) / snapshot.max_pain) * 100
                    feature_store.max_pain_distance_pct = distance

            # VIX percentile (requires historical data)
            if feature_store.vix:
                feature_store.vix_percentile_30d = self._calculate_vix_percentile(
                    float(feature_store.vix),
                    decision_log.decision_timestamp
                )

            # Trend features would require additional market data
            # Left as placeholders for now
            feature_store.spot_vs_sma20 = market_context.get('spot_vs_sma20')
            feature_store.spot_vs_sma50 = market_context.get('spot_vs_sma50')
            feature_store.macd_histogram = market_context.get('macd_histogram')

        except Exception as e:
            logger.error(f"Error computing market features: {e}")

    def _compute_time_features(
        self,
        feature_store: MLFeatureStore,
        decision_log: UserDecisionLog,
    ):
        """Compute time-related features."""
        try:
            dt = decision_log.decision_timestamp
            suggestion = decision_log.suggestion

            # Day and hour
            feature_store.day_of_week = dt.weekday()
            feature_store.hour_of_day = dt.hour

            # Expiry features
            if suggestion and suggestion.expiry_date:
                days_to_expiry = (suggestion.expiry_date - dt.date()).days
                feature_store.days_to_expiry = max(0, days_to_expiry)

                # Is expiry week (Thursday is typical expiry)
                expiry_weekday = suggestion.expiry_date.weekday()
                current_weekday = dt.weekday()

                # Same week as expiry
                days_diff = (suggestion.expiry_date - dt.date()).days
                feature_store.is_expiry_week = 0 <= days_diff <= 7

                # Is monthly expiry (last Thursday of month)
                feature_store.is_monthly_expiry = self._is_monthly_expiry(suggestion.expiry_date)

        except Exception as e:
            logger.error(f"Error computing time features: {e}")

    def _compute_algorithm_features(
        self,
        feature_store: MLFeatureStore,
        decision_log: UserDecisionLog,
    ):
        """Compute algorithm-related features."""
        try:
            feature_store.algo_confidence = decision_log.algorithm_confidence
            feature_store.algo_signal_strength = decision_log.algorithm_signal_strength

            if decision_log.suggestion:
                feature_store.strategy_type = decision_log.suggestion.strategy

        except Exception as e:
            logger.error(f"Error computing algorithm features: {e}")

    def _compute_user_features(
        self,
        feature_store: MLFeatureStore,
        decision_log: UserDecisionLog,
    ):
        """Compute user behavior features."""
        try:
            user = decision_log.user

            # Try to get user behavior profile
            try:
                profile = UserBehaviorProfile.objects.get(user=user)
                feature_store.user_historical_approval_rate = profile.approval_rate
                feature_store.user_avg_decision_time = profile.avg_decision_time_seconds
                feature_store.user_win_rate = profile.approved_trades_win_rate
            except UserBehaviorProfile.DoesNotExist:
                # Compute on the fly
                past_decisions = UserDecisionLog.objects.filter(
                    user=user,
                    decision_timestamp__lt=decision_log.decision_timestamp,
                )

                total = past_decisions.count()
                if total > 0:
                    approved = past_decisions.filter(
                        decision_type__in=['APPROVE', 'AUTO_APPROVE']
                    ).count()
                    feature_store.user_historical_approval_rate = Decimal(approved) / Decimal(total) * 100

                    avg_time = past_decisions.aggregate(
                        avg=Avg('time_to_decision_seconds')
                    )['avg']
                    feature_store.user_avg_decision_time = int(avg_time) if avg_time else None

        except Exception as e:
            logger.error(f"Error computing user features: {e}")

    def _compute_performance_features(
        self,
        feature_store: MLFeatureStore,
        decision_log: UserDecisionLog,
    ):
        """Compute recent performance features."""
        try:
            user = decision_log.user
            decision_time = decision_log.decision_timestamp

            # Get last 5 closed trades
            recent_trades = TakenTrade.objects.filter(
                user=user,
                status='CLOSED',
                closed_at__lt=decision_time,
            ).order_by('-closed_at')[:5]

            if recent_trades.exists():
                # Total P&L of last 5
                total_pnl = sum(t.net_pnl or Decimal('0') for t in recent_trades)
                feature_store.last_5_trades_pnl = total_pnl

                # Win rate of last 5
                wins = sum(1 for t in recent_trades if t.outcome == 'PROFIT')
                feature_store.last_5_trades_win_rate = Decimal(wins) / Decimal(len(recent_trades)) * 100

                # Current streak
                streak = 0
                last_outcome = None
                for trade in recent_trades:
                    if last_outcome is None:
                        last_outcome = trade.outcome
                        streak = 1 if trade.outcome == 'PROFIT' else -1
                    elif trade.outcome == last_outcome:
                        streak += 1 if trade.outcome == 'PROFIT' else -1
                    else:
                        break
                feature_store.current_streak = streak

            # Current day P&L
            today = decision_time.date()
            todays_trades = TakenTrade.objects.filter(
                user=user,
                status='CLOSED',
                closed_at__date=today,
            )
            day_pnl = todays_trades.aggregate(total=Sum('net_pnl'))['total']
            feature_store.current_day_pnl = day_pnl

        except Exception as e:
            logger.error(f"Error computing performance features: {e}")

    def _build_feature_vector(self, feature_store: MLFeatureStore) -> List[Optional[float]]:
        """Build ordered feature vector for ML model."""
        vector = []

        for col in self.FEATURE_COLUMNS:
            value = getattr(feature_store, col, None)
            if value is None:
                vector.append(None)
            elif isinstance(value, Decimal):
                vector.append(float(value))
            elif isinstance(value, bool):
                vector.append(1.0 if value else 0.0)
            else:
                vector.append(float(value))

        return vector

    def _check_completeness(self, feature_store: MLFeatureStore) -> bool:
        """Check if all required features are present."""
        # Key features that should be present
        key_features = [
            'vix',
            'day_of_week',
            'hour_of_day',
        ]

        for feat in key_features:
            if getattr(feature_store, feat, None) is None:
                return False

        return True

    def _calculate_vix_percentile(self, vix: float, as_of: datetime) -> Optional[Decimal]:
        """Calculate VIX percentile over last 30 days."""
        try:
            start_date = as_of - timedelta(days=30)

            # Get historical VIX values from snapshots
            snapshots = MarketContextSnapshot.objects.filter(
                snapshot_timestamp__gte=start_date,
                snapshot_timestamp__lt=as_of,
                india_vix__isnull=False,
            ).values_list('india_vix', flat=True)

            if len(snapshots) < 10:
                return None

            vix_values = [float(v) for v in snapshots]
            percentile = sum(1 for v in vix_values if v <= vix) / len(vix_values) * 100

            return Decimal(str(round(percentile, 2)))

        except Exception as e:
            logger.error(f"Error calculating VIX percentile: {e}")
            return None

    def _is_monthly_expiry(self, expiry_date: date) -> bool:
        """Check if date is monthly expiry (last Thursday of month)."""
        try:
            # Get last day of month
            if expiry_date.month == 12:
                next_month = date(expiry_date.year + 1, 1, 1)
            else:
                next_month = date(expiry_date.year, expiry_date.month + 1, 1)

            last_day = next_month - timedelta(days=1)

            # Find last Thursday
            days_to_thursday = (last_day.weekday() - 3) % 7
            last_thursday = last_day - timedelta(days=days_to_thursday)

            return expiry_date == last_thursday

        except Exception as e:
            logger.error(f"Error checking monthly expiry: {e}")
            return False

    @transaction.atomic
    def compute_labels(self, decision_log: UserDecisionLog) -> bool:
        """
        Compute outcome labels for a decision (after trade closes).

        Args:
            decision_log: The decision with known outcome

        Returns:
            bool: True if labels computed successfully
        """
        try:
            if not hasattr(decision_log, 'ml_features'):
                logger.warning(f"No feature store for decision {decision_log.id}")
                return False

            feature_store = decision_log.ml_features

            # Only compute if decision led to a trade
            if decision_log.decision_type not in ['APPROVE', 'AUTO_APPROVE', 'MODIFY']:
                feature_store.labels_computed = True
                feature_store.label_final_outcome = 'N/A'
                feature_store.save()
                return True

            # Check if outcome is known
            if decision_log.final_outcome == 'PENDING':
                return False

            # Set final labels
            feature_store.label_final_pnl = decision_log.final_pnl
            feature_store.label_final_outcome = decision_log.final_outcome
            feature_store.labels_computed = True
            feature_store.save()

            logger.info(f"Computed labels for decision {decision_log.id}: {decision_log.final_outcome}")
            return True

        except Exception as e:
            logger.error(f"Error computing labels: {e}", exc_info=True)
            return False

    def compute_features_batch(self, decision_ids: List[int]) -> Dict[str, int]:
        """
        Compute features for a batch of decisions.

        Args:
            decision_ids: List of UserDecisionLog IDs

        Returns:
            Dict with success/error counts
        """
        success_count = 0
        error_count = 0

        for decision_id in decision_ids:
            try:
                decision = UserDecisionLog.objects.get(id=decision_id)
                result = self.compute_features(decision)
                if result:
                    success_count += 1
                else:
                    error_count += 1
            except UserDecisionLog.DoesNotExist:
                error_count += 1
            except Exception as e:
                logger.error(f"Error processing decision {decision_id}: {e}")
                error_count += 1

        return {
            'success': success_count,
            'errors': error_count,
            'total': len(decision_ids),
        }

    def export_to_parquet(
        self,
        from_date: datetime,
        to_date: datetime,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Export feature data to Parquet format for ML training.

        Args:
            from_date: Start date
            to_date: End date
            output_path: Output file path (optional)

        Returns:
            str: Path to exported file
        """
        try:
            import pandas as pd

            # Get complete feature stores with labels
            features = MLFeatureStore.objects.filter(
                is_complete=True,
                labels_computed=True,
                decision_log__decision_timestamp__gte=from_date,
                decision_log__decision_timestamp__lte=to_date,
            ).select_related('decision_log', 'decision_log__user', 'decision_log__suggestion')

            records = []
            for fs in features:
                record = {
                    'decision_id': fs.decision_log_id,
                    'user_id': fs.decision_log.user_id,
                    'decision_timestamp': fs.decision_log.decision_timestamp,
                    'decision_type': fs.decision_log.decision_type,
                    'strategy': fs.strategy_type,
                }

                # Add all feature columns
                for col in self.FEATURE_COLUMNS:
                    value = getattr(fs, col, None)
                    record[col] = float(value) if value is not None else None

                # Add labels
                record['label_final_pnl'] = float(fs.label_final_pnl) if fs.label_final_pnl else None
                record['label_final_outcome'] = fs.label_final_outcome

                records.append(record)

            df = pd.DataFrame(records)

            # Generate output path if not provided
            if not output_path:
                output_dir = '/tmp/ml_features'
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(
                    output_dir,
                    f"features_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.parquet"
                )

            df.to_parquet(output_path, index=False)

            logger.info(f"Exported {len(records)} feature records to {output_path}")
            return output_path

        except ImportError:
            logger.error("pandas not installed for Parquet export")
            raise
        except Exception as e:
            logger.error(f"Error exporting to Parquet: {e}", exc_info=True)
            raise

    def get_feature_vector(self, decision_log: UserDecisionLog) -> Optional[List[float]]:
        """
        Get feature vector for a decision (for inference).

        Args:
            decision_log: The decision

        Returns:
            List of feature values, or None if not computed
        """
        try:
            if not hasattr(decision_log, 'ml_features'):
                # Compute on the fly
                feature_store = self.compute_features(decision_log)
                if not feature_store:
                    return None
            else:
                feature_store = decision_log.ml_features

            return feature_store.feature_vector

        except Exception as e:
            logger.error(f"Error getting feature vector: {e}")
            return None

    @classmethod
    def get_feature_columns(cls) -> List[str]:
        """Get ordered list of feature column names."""
        return cls.FEATURE_COLUMNS.copy()


# Singleton instance
_engineer = None


def get_engineer() -> FeatureEngineer:
    """Get singleton FeatureEngineer instance."""
    global _engineer
    if _engineer is None:
        _engineer = FeatureEngineer()
    return _engineer
