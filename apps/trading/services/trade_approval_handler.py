"""
Trade Approval Handler

Handles approval/rejection of trade suggestions via Telegram and executes approved trades
"""

import logging
from decimal import Decimal
from typing import Dict, Optional, Tuple
from django.utils import timezone
from django.db import transaction

from apps.trading.models import TradeSuggestion, TradeSuggestionLog
from apps.positions.models import Position
from apps.brokers.models import Order
from apps.accounts.models import BrokerAccount
from apps.brokers.integrations.breeze import BreezeAPIClient
from apps.brokers.integrations.kotak import KotakNeoAPIClient

logger = logging.getLogger(__name__)


class TradeApprovalHandler:
    """
    Handles trade approval workflow and order execution
    """

    @staticmethod
    def approve_trade(suggestion_id: int, approved_by_user) -> Tuple[bool, str, Optional[Position]]:
        """
        Approve a trade suggestion and execute it

        Args:
            suggestion_id: Trade suggestion ID
            approved_by_user: User who approved (from Telegram)

        Returns:
            tuple: (success: bool, message: str, position: Position or None)
        """

        logger.info(f"Approving trade suggestion #{suggestion_id}")

        try:
            with transaction.atomic():
                # Get suggestion
                suggestion = TradeSuggestion.objects.select_for_update().get(id=suggestion_id)

                # Check if already processed
                if suggestion.status in ['APPROVED', 'AUTO_APPROVED', 'EXECUTED', 'REJECTED']:
                    return False, f"Trade already {suggestion.status}", None

                # Check if expired
                if suggestion.is_expired:
                    return False, "Trade suggestion has expired", None

                # Update suggestion status
                suggestion.status = 'APPROVED'
                suggestion.approved_by = approved_by_user
                suggestion.approval_timestamp = timezone.now()
                suggestion.save()

                # Log approval
                TradeSuggestionLog.objects.create(
                    suggestion=suggestion,
                    action='APPROVED',
                    notes=f"Approved by {approved_by_user.username} via Telegram"
                )

                logger.info(f"Trade #{suggestion_id} approved by {approved_by_user.username}")

                # Execute the trade
                success, message, position = TradeApprovalHandler._execute_approved_trade(suggestion)

                return success, message, position

        except TradeSuggestion.DoesNotExist:
            return False, f"Trade suggestion #{suggestion_id} not found", None
        except Exception as e:
            logger.error(f"Error approving trade #{suggestion_id}: {e}", exc_info=True)
            return False, f"Error approving trade: {str(e)}", None

    @staticmethod
    def reject_trade(suggestion_id: int, rejected_by_user) -> Tuple[bool, str]:
        """
        Reject a trade suggestion

        Args:
            suggestion_id: Trade suggestion ID
            rejected_by_user: User who rejected

        Returns:
            tuple: (success: bool, message: str)
        """

        logger.info(f"Rejecting trade suggestion #{suggestion_id}")

        try:
            with transaction.atomic():
                # Get suggestion
                suggestion = TradeSuggestion.objects.select_for_update().get(id=suggestion_id)

                # Check if already processed
                if suggestion.status in ['APPROVED', 'AUTO_APPROVED', 'EXECUTED']:
                    return False, f"Trade already {suggestion.status}, cannot reject"

                # Update suggestion status
                suggestion.status = 'REJECTED'
                suggestion.save()

                # Log rejection
                TradeSuggestionLog.objects.create(
                    suggestion=suggestion,
                    action='REJECTED',
                    notes=f"Rejected by {rejected_by_user.username} via Telegram"
                )

                logger.info(f"Trade #{suggestion_id} rejected by {rejected_by_user.username}")

                return True, "Trade suggestion rejected"

        except TradeSuggestion.DoesNotExist:
            return False, f"Trade suggestion #{suggestion_id} not found"
        except Exception as e:
            logger.error(f"Error rejecting trade #{suggestion_id}: {e}", exc_info=True)
            return False, f"Error rejecting trade: {str(e)}"

    @staticmethod
    def _execute_approved_trade(suggestion: TradeSuggestion) -> Tuple[bool, str, Optional[Position]]:
        """
        Execute an approved trade suggestion

        Args:
            suggestion: Approved TradeSuggestion instance

        Returns:
            tuple: (success: bool, message: str, position: Position or None)
        """

        logger.info(f"Executing approved trade #{suggestion.id}")
        logger.info(f"Strategy: {suggestion.strategy}")
        logger.info(f"Symbol: {suggestion.instrument}")
        logger.info(f"Direction: {suggestion.direction}")

        try:
            # Get position details from suggestion
            pos_details = suggestion.position_details
            algo_reasoning = suggestion.algorithm_reasoning

            # Determine account based on strategy
            if suggestion.strategy == 'icici_futures':
                account = BrokerAccount.objects.get(broker='ICICI', is_active=True)
                broker_client = BreezeAPIClient()
            elif suggestion.strategy == 'kotak_strangle':
                account = BrokerAccount.objects.get(broker='KOTAK', is_active=True)
                broker_client = KotakNeoAPIClient()
            else:
                return False, f"Unknown strategy: {suggestion.strategy}", None

            # Check ONE POSITION RULE
            if Position.has_active_position(account):
                return False, "ONE POSITION RULE: Active position already exists", None

            # Extract trade parameters
            symbol = suggestion.instrument
            direction = suggestion.direction
            entry_price = Decimal(str(pos_details.get('entry_price', 0)))
            quantity = int(pos_details.get('quantity', 0))
            lot_size = int(pos_details.get('lot_size', 1))
            stop_loss = Decimal(str(pos_details.get('stop_loss', 0)))
            target = Decimal(str(pos_details.get('target', 0)))
            expiry_date = pos_details.get('expiry_date', timezone.now().date())
            margin_required = Decimal(str(pos_details.get('margin_required', 0)))

            # Place order with broker
            logger.info(f"Placing order with {account.broker} broker...")

            if suggestion.suggestion_type == 'FUTURES':
                order_result = broker_client.place_futures_order(
                    symbol=symbol,
                    direction=direction,
                    quantity=quantity,
                    order_type='MARKET',  # Market order for immediate execution
                    price=None  # Market order has no limit price
                )
            else:  # OPTIONS
                # For options (strangle), need special handling
                call_strike = Decimal(str(pos_details.get('call_strike', 0)))
                put_strike = Decimal(str(pos_details.get('put_strike', 0)))

                order_result = broker_client.place_strangle_order(
                    symbol=symbol,
                    call_strike=call_strike,
                    put_strike=put_strike,
                    quantity=quantity,
                    expiry=expiry_date
                )

            # Check order result
            if not order_result.get('success', False):
                error_msg = order_result.get('message', 'Order placement failed')
                logger.error(f"Order placement failed: {error_msg}")

                # Log failure
                TradeSuggestionLog.objects.create(
                    suggestion=suggestion,
                    action='EXECUTION_FAILED',
                    notes=f"Order placement failed: {error_msg}"
                )

                return False, f"Order placement failed: {error_msg}", None

            # Order successful - get execution price
            executed_price = Decimal(str(order_result.get('executed_price', entry_price)))
            broker_order_id = order_result.get('order_id', 'UNKNOWN')

            logger.info(f"Order executed successfully: {broker_order_id}")
            logger.info(f"Executed price: ₹{executed_price:,.2f}")

            # Create Position record
            position = Position.objects.create(
                account=account,
                strategy_type=suggestion.strategy,
                instrument=symbol,
                direction=direction,
                quantity=quantity // lot_size,  # Number of lots
                lot_size=lot_size,
                entry_price=executed_price,
                current_price=executed_price,
                stop_loss=stop_loss,
                target=target,
                expiry_date=expiry_date,
                margin_used=margin_required,
                entry_value=executed_price * quantity,
                status='ACTIVE',
                notes=f"Created from trade suggestion #{suggestion.id}"
            )

            logger.info(f"Position #{position.id} created successfully")

            # Create Order record
            Order.objects.create(
                account=account,
                position=position,
                order_type='MARKET',
                symbol=symbol,
                direction=direction,
                quantity=quantity,
                price=executed_price,
                status='FILLED',
                broker_order_id=broker_order_id,
                notes=f"Initial entry from suggestion #{suggestion.id}"
            )

            # Update suggestion status
            suggestion.status = 'EXECUTED'
            suggestion.executed_at = timezone.now()
            suggestion.executed_position_id = position.id
            suggestion.save()

            # Log execution
            TradeSuggestionLog.objects.create(
                suggestion=suggestion,
                action='EXECUTED',
                notes=(
                    f"Order executed successfully. "
                    f"Order ID: {broker_order_id}, "
                    f"Position ID: {position.id}, "
                    f"Executed Price: ₹{executed_price:,.2f}"
                )
            )

            logger.info(f"Trade #{suggestion.id} executed successfully")

            return True, f"Order executed: {broker_order_id}", position

        except BrokerAccount.DoesNotExist:
            return False, f"Active {suggestion.strategy} account not found", None
        except Exception as e:
            logger.error(f"Error executing trade: {e}", exc_info=True)

            # Log execution failure
            try:
                TradeSuggestionLog.objects.create(
                    suggestion=suggestion,
                    action='EXECUTION_FAILED',
                    notes=f"Execution error: {str(e)}"
                )
            except:
                pass

            return False, f"Execution error: {str(e)}", None
