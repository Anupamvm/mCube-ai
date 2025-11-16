"""
Trading Services - Trade Suggestion Generation and Auto-Approval Logic
"""

from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import logging

from apps.trading.models import TradeSuggestion, AutoTradeConfig, TradeSuggestionLog

logger = logging.getLogger(__name__)


class TradeSuggestionService:
    """
    Service for creating trade suggestions from algorithm analysis
    """

    @staticmethod
    def create_suggestion(
        user: User,
        strategy: str,
        suggestion_type: str,
        instrument: str,
        direction: str,
        algorithm_reasoning: dict,
        position_details: dict
    ) -> TradeSuggestion:
        """
        Create a new trade suggestion from algorithm output

        Args:
            user: User who owns the account
            strategy: Strategy code (kotak_strangle, icici_futures)
            suggestion_type: OPTIONS or FUTURES
            instrument: NIFTY, RELIANCE, etc.
            direction: LONG, SHORT, NEUTRAL
            algorithm_reasoning: Complete algorithm analysis (calculations, filters, scores)
            position_details: Recommended position parameters

        Returns:
            TradeSuggestion instance
        """

        # Create suggestion
        suggestion = TradeSuggestion.objects.create(
            user=user,
            strategy=strategy,
            suggestion_type=suggestion_type,
            instrument=instrument,
            direction=direction,
            algorithm_reasoning=algorithm_reasoning,
            position_details=position_details,
            expires_at=timezone.now() + timedelta(hours=1)  # Expires in 1 hour
        )

        # Log creation
        TradeSuggestionLog.objects.create(
            suggestion=suggestion,
            action='CREATED',
            notes=f"Suggestion created by {strategy} algorithm"
        )

        # Check if should auto-approve
        should_auto_approve = TradeSuggestionService.should_auto_approve(user, strategy, algorithm_reasoning)

        if should_auto_approve:
            TradeSuggestionService.auto_approve(suggestion)

        logger.info(f"Trade suggestion created: {suggestion.id} - {instrument} {direction}")

        return suggestion

    @staticmethod
    def should_auto_approve(user: User, strategy: str, reasoning: dict) -> bool:
        """
        Determine if suggestion should be auto-approved based on configuration
        """
        try:
            config = AutoTradeConfig.objects.get(user=user, strategy=strategy)

            if not config.is_enabled:
                return False

            # Check daily position limit
            daily_suggestions = TradeSuggestion.objects.filter(
                user=user,
                strategy=strategy,
                status__in=['APPROVED', 'AUTO_APPROVED', 'EXECUTED'],
                created_at__date=timezone.now().date()
            ).count()

            if daily_suggestions >= config.max_daily_positions:
                logger.warning(f"Daily position limit reached for {user.username} - {strategy}")
                return False

            # Strategy-specific checks
            if strategy == 'kotak_strangle':
                # For options: check LLM confidence
                llm_confidence = reasoning.get('filters', {}).get('llm_validation', {}).get('confidence', 0)
                if llm_confidence >= float(config.auto_approve_threshold):
                    return True

            elif strategy == 'icici_futures':
                # For futures: check composite score
                composite_score = reasoning.get('scoring', {}).get('composite', {}).get('total', 0)
                if composite_score >= float(config.auto_approve_threshold):
                    return True

            return False

        except AutoTradeConfig.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error checking auto-approval: {e}")
            return False

    @staticmethod
    def auto_approve(suggestion: TradeSuggestion):
        """
        Automatically approve a suggestion
        """
        try:
            suggestion.status = 'AUTO_APPROVED'
            suggestion.approved_by = suggestion.user  # System auto-approved
            suggestion.approval_timestamp = timezone.now()
            suggestion.is_auto_trade = True
            suggestion.save()

            # Log auto-approval
            TradeSuggestionLog.objects.create(
                suggestion=suggestion,
                action='AUTO_APPROVED',
                notes="Auto-approved by system based on configuration"
            )

            logger.info(f"Suggestion {suggestion.id} auto-approved")

        except Exception as e:
            logger.error(f"Error auto-approving suggestion: {e}")


class OptionsSuggestionFormatter:
    """
    Format options algorithm output for display as trade suggestion
    """

    @staticmethod
    def format_reasoning(calculator_result: dict) -> dict:
        """
        Convert OptionsAlgorithmCalculator output to human-readable reasoning
        """
        return {
            'title': 'Kotak Strangle Strategy',
            'summary': 'Short Strangle position to collect premium',
            'calculations': calculator_result.get('calculations', {}),
            'filters': calculator_result.get('filters', {}),
            'final_decision': calculator_result.get('final_decision', {}),
        }

    @staticmethod
    def format_position_details(calculator_result: dict) -> dict:
        """
        Extract position sizing details from algorithm result
        """
        position_details = calculator_result.get('final_decision', {}).get('position_details', {})

        return {
            'instrument': position_details.get('instrument', 'NIFTY'),
            'strategy': position_details.get('strategy', 'Short Strangle'),
            'call_strike': position_details.get('call_strike'),
            'put_strike': position_details.get('put_strike'),
            'quantity': position_details.get('total_quantity', 50),
            'lot_size': position_details.get('quantity_per_lot', 50),
            'entry_price': None,  # Will be fetched from market
            'premium_collected': position_details.get('premium_collected'),
            'margin_required': position_details.get('margin_used'),
            'stop_loss': position_details.get('stop_loss'),
            'target': position_details.get('target'),
        }


class FuturesSuggestionFormatter:
    """
    Format futures algorithm output for display as trade suggestion
    """

    @staticmethod
    def format_reasoning(calculator_result: dict) -> dict:
        """
        Convert FuturesAlgorithmCalculator output to human-readable reasoning
        """
        return {
            'title': 'ICICI Futures Strategy',
            'summary': 'Multi-factor scoring for directional trade',
            'scoring': calculator_result.get('scoring', {}),
            'llm_validation': calculator_result.get('llm_validation', {}),
            'final_decision': calculator_result.get('final_decision', {}),
        }

    @staticmethod
    def format_position_details(calculator_result: dict) -> dict:
        """
        Extract position sizing details from algorithm result
        """
        position_details = calculator_result.get('final_decision', {}).get('position_details', {})

        return {
            'symbol': position_details.get('symbol'),
            'direction': position_details.get('direction'),
            'entry_price': position_details.get('entry_price'),
            'quantity': int(position_details.get('quantity', 1000)),
            'lot_size': 250,  # Typical futures lot size
            'stop_loss': position_details.get('stop_loss'),
            'target': position_details.get('target'),
            'margin_required': position_details.get('margin_required'),
            'max_loss': position_details.get('max_loss'),
            'expected_profit': position_details.get('expected_profit'),
        }
