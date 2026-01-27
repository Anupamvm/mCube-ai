"""
Trade Action Service

Handles user actions on trade suggestions including:
- Accept/reject suggestions
- Status synchronization between TakenTrade, Position, and TradeSuggestion
- Logging of all trade actions
"""

import logging
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

from apps.trading.models import TradeSuggestion, TakenTrade, TradeSuggestionLog

logger = logging.getLogger(__name__)


class TradeActionService:
    """
    Service for handling user actions on trade suggestions.

    This service manages the lifecycle of trade suggestions and taken trades,
    ensuring proper status synchronization across all related models.
    """

    @staticmethod
    @transaction.atomic
    def accept_suggestion(suggestion, user, account, notes=''):
        """
        Accept a trade suggestion and create a TakenTrade record.

        Args:
            suggestion: TradeSuggestion instance to accept
            user: User accepting the suggestion
            account: BrokerAccount to use for the trade
            notes: Optional notes from user

        Returns:
            dict: {
                'success': bool,
                'taken_trade': TakenTrade instance (if successful),
                'error': str (if failed)
            }
        """
        try:
            # Validate suggestion is still actionable
            if not suggestion.is_actionable:
                return {
                    'success': False,
                    'error': f'Suggestion is no longer actionable (status: {suggestion.status})'
                }

            # Check for existing TakenTrade (prevent duplicates)
            existing = TakenTrade.objects.filter(
                user=user,
                suggestion=suggestion
            ).first()

            if existing:
                return {
                    'success': False,
                    'error': 'Trade already taken for this suggestion',
                    'taken_trade': existing
                }

            # Create TakenTrade record
            taken_trade = TakenTrade.objects.create(
                user=user,
                suggestion=suggestion,
                account=account,
                strategy=suggestion.strategy,
                trade_type=suggestion.suggestion_type,
                instrument=suggestion.instrument,
                direction=suggestion.direction,
                entry_price=suggestion.total_premium or suggestion.spot_price,
                quantity=suggestion.recommended_lots or 1,
                lot_size=25 if suggestion.instrument == 'NIFTY' else 15,  # Default lot sizes
                call_strike=suggestion.call_strike,
                put_strike=suggestion.put_strike,
                expiry_date=suggestion.expiry_date,
                margin_used=suggestion.margin_required,
                status='PENDING_EXECUTION',
                outcome='PENDING',
                notes=notes
            )

            # Update suggestion status
            suggestion.mark_taken(user_notes=notes)

            # Log the action
            TradeSuggestionLog.objects.create(
                suggestion=suggestion,
                action='APPROVED',
                user=user,
                notes=notes or f'Trade accepted by {user.username}'
            )

            logger.info(f"Trade suggestion {suggestion.id} accepted by {user.username}, "
                       f"TakenTrade {taken_trade.id} created")

            return {
                'success': True,
                'taken_trade': taken_trade
            }

        except Exception as e:
            logger.exception(f"Error accepting suggestion {suggestion.id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    @transaction.atomic
    def reject_suggestion(suggestion, user, reason=''):
        """
        Reject a trade suggestion.

        Args:
            suggestion: TradeSuggestion instance to reject
            user: User rejecting the suggestion
            reason: Optional reason for rejection

        Returns:
            dict: {
                'success': bool,
                'error': str (if failed)
            }
        """
        try:
            # Validate suggestion is still actionable
            if not suggestion.is_actionable:
                return {
                    'success': False,
                    'error': f'Suggestion is no longer actionable (status: {suggestion.status})'
                }

            # Update suggestion status
            suggestion.mark_rejected(user_notes=reason)

            # Log the action
            TradeSuggestionLog.objects.create(
                suggestion=suggestion,
                action='REJECTED',
                user=user,
                notes=reason or f'Trade rejected by {user.username}'
            )

            logger.info(f"Trade suggestion {suggestion.id} rejected by {user.username}")

            return {'success': True}

        except Exception as e:
            logger.exception(f"Error rejecting suggestion {suggestion.id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    @transaction.atomic
    def sync_trade_status(taken_trade):
        """
        Synchronize status between TakenTrade, Position, and TradeSuggestion.

        This method should be called periodically to keep all related models
        in sync, especially when positions are being monitored.

        Args:
            taken_trade: TakenTrade instance to sync

        Returns:
            dict: {
                'success': bool,
                'status_changed': bool,
                'old_status': str,
                'new_status': str,
                'error': str (if failed)
            }
        """
        try:
            old_status = taken_trade.status
            status_changed = False

            # Sync from Position if available
            if taken_trade.position:
                position = taken_trade.position

                # Update status based on position status
                if position.status == 'ACTIVE' and taken_trade.status in ['PENDING_EXECUTION', 'EXECUTED']:
                    taken_trade.status = 'ACTIVE'
                    status_changed = True

                elif position.status == 'CLOSED' and taken_trade.status != 'CLOSED':
                    taken_trade.status = 'CLOSED'
                    taken_trade.closed_at = position.closed_at or timezone.now()
                    taken_trade.exit_price = position.exit_price
                    taken_trade.realized_pnl = position.realized_pnl

                    # Determine outcome based on P&L
                    if position.realized_pnl:
                        if position.realized_pnl > Decimal('100'):
                            taken_trade.outcome = 'PROFIT'
                        elif position.realized_pnl < Decimal('-100'):
                            taken_trade.outcome = 'LOSS'
                        else:
                            taken_trade.outcome = 'BREAKEVEN'

                    status_changed = True

            # Sync status back to suggestion
            if status_changed and taken_trade.suggestion:
                TradeActionService._sync_to_suggestion(taken_trade)

            if status_changed:
                taken_trade.save()

            logger.info(f"TakenTrade {taken_trade.id} sync: {old_status} -> {taken_trade.status}")

            return {
                'success': True,
                'status_changed': status_changed,
                'old_status': old_status,
                'new_status': taken_trade.status
            }

        except Exception as e:
            logger.exception(f"Error syncing trade status for TakenTrade {taken_trade.id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'status_changed': False,
                'old_status': taken_trade.status,
                'new_status': taken_trade.status
            }

    @staticmethod
    def _sync_to_suggestion(taken_trade):
        """
        Internal method to sync TakenTrade status back to TradeSuggestion.

        Args:
            taken_trade: TakenTrade instance
        """
        suggestion = taken_trade.suggestion
        if not suggestion:
            return

        if taken_trade.status == 'ACTIVE':
            suggestion.status = 'ACTIVE'
        elif taken_trade.status == 'CLOSED':
            if taken_trade.outcome == 'PROFIT':
                suggestion.status = 'SUCCESSFUL'
            elif taken_trade.outcome == 'LOSS':
                suggestion.status = 'LOSS'
            else:
                suggestion.status = 'BREAKEVEN'

            suggestion.realized_pnl = taken_trade.realized_pnl
            suggestion.exit_value = taken_trade.exit_price
            suggestion.closed_timestamp = taken_trade.closed_at

            # Calculate ROM if margin is available
            if suggestion.margin_required and taken_trade.realized_pnl:
                suggestion.return_on_margin = (
                    taken_trade.realized_pnl / suggestion.margin_required
                ) * 100

        suggestion.save()

    @staticmethod
    def link_position_to_trade(taken_trade, position):
        """
        Link an executed Position to a TakenTrade.

        This should be called after a position is successfully created
        from an order execution.

        Args:
            taken_trade: TakenTrade instance
            position: Position instance to link

        Returns:
            dict: {
                'success': bool,
                'error': str (if failed)
            }
        """
        try:
            taken_trade.position = position
            taken_trade.status = 'EXECUTED'
            taken_trade.executed_at = timezone.now()

            # Copy entry details from position
            if position.entry_price:
                taken_trade.entry_price = position.entry_price
            if position.margin_used:
                taken_trade.margin_used = position.margin_used

            taken_trade.save()

            # Update suggestion
            if taken_trade.suggestion:
                taken_trade.suggestion.executed_position = position
                taken_trade.suggestion.status = 'ACTIVE'
                taken_trade.suggestion.save()

            logger.info(f"Position {position.id} linked to TakenTrade {taken_trade.id}")

            return {'success': True}

        except Exception as e:
            logger.exception(f"Error linking position to trade: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    def get_active_trades(user=None, account=None):
        """
        Get all active (non-closed) taken trades.

        Args:
            user: Optional user filter
            account: Optional account filter

        Returns:
            QuerySet: TakenTrade objects
        """
        queryset = TakenTrade.objects.filter(
            status__in=['PENDING_EXECUTION', 'EXECUTED', 'ACTIVE']
        ).select_related('suggestion', 'position', 'account')

        if user:
            queryset = queryset.filter(user=user)
        if account:
            queryset = queryset.filter(account=account)

        return queryset.order_by('-taken_at')

    @staticmethod
    def get_closed_trades(user=None, account=None, from_date=None, to_date=None):
        """
        Get closed taken trades with optional filters.

        Args:
            user: Optional user filter
            account: Optional account filter
            from_date: Optional start date filter
            to_date: Optional end date filter

        Returns:
            QuerySet: TakenTrade objects
        """
        queryset = TakenTrade.objects.filter(
            status='CLOSED'
        ).select_related('suggestion', 'position', 'account')

        if user:
            queryset = queryset.filter(user=user)
        if account:
            queryset = queryset.filter(account=account)
        if from_date:
            queryset = queryset.filter(closed_at__date__gte=from_date)
        if to_date:
            queryset = queryset.filter(closed_at__date__lte=to_date)

        return queryset.order_by('-closed_at')

    @staticmethod
    def get_trade_summary(user, account=None):
        """
        Get summary statistics for a user's trades.

        Args:
            user: User to get summary for
            account: Optional account filter

        Returns:
            dict: Summary statistics
        """
        from django.db.models import Sum, Count, Avg, Q

        queryset = TakenTrade.objects.filter(user=user)
        if account:
            queryset = queryset.filter(account=account)

        closed_trades = queryset.filter(status='CLOSED')

        # Aggregate statistics
        stats = closed_trades.aggregate(
            total_trades=Count('id'),
            winning_trades=Count('id', filter=Q(outcome='PROFIT')),
            losing_trades=Count('id', filter=Q(outcome='LOSS')),
            breakeven_trades=Count('id', filter=Q(outcome='BREAKEVEN')),
            total_pnl=Sum('net_pnl'),
            total_charges=Sum('charges'),
            avg_pnl=Avg('net_pnl'),
        )

        # Calculate win rate
        total = stats.get('total_trades') or 0
        wins = stats.get('winning_trades') or 0
        win_rate = (wins / total * 100) if total > 0 else 0

        # Active trades count
        active_count = queryset.filter(
            status__in=['PENDING_EXECUTION', 'EXECUTED', 'ACTIVE']
        ).count()

        return {
            'total_trades': total,
            'winning_trades': wins,
            'losing_trades': stats.get('losing_trades') or 0,
            'breakeven_trades': stats.get('breakeven_trades') or 0,
            'active_trades': active_count,
            'win_rate': round(win_rate, 2),
            'total_pnl': stats.get('total_pnl') or Decimal('0.00'),
            'total_charges': stats.get('total_charges') or Decimal('0.00'),
            'avg_pnl': stats.get('avg_pnl') or Decimal('0.00'),
        }

    @staticmethod
    @transaction.atomic
    def create_trades_from_broker_history(user, account, from_date=None, to_date=None):
        """
        Create TakenTrade records from BrokerTradeHistory by matching buy/sell pairs.

        This method:
        1. Groups broker trades by trading_symbol and expiry_date
        2. Matches opening (buy for long, sell for short) with closing trades
        3. Creates TakenTrade records for fully closed positions
        4. Links broker trades to the created TakenTrade

        Args:
            user: User creating the trades
            account: BrokerAccount to process
            from_date: Optional start date filter
            to_date: Optional end date filter

        Returns:
            dict: {
                'success': bool,
                'created_count': int,
                'skipped_count': int,
                'errors': list of error messages,
                'created_trades': list of TakenTrade objects
            }
        """
        from apps.brokers.models import BrokerTradeHistory
        from django.db.models import Sum
        from collections import defaultdict
        from datetime import datetime

        created_trades = []
        errors = []
        skipped_count = 0

        try:
            # Get unreconciled broker trades
            queryset = BrokerTradeHistory.objects.filter(
                account=account,
                is_reconciled=False
            ).order_by('trade_date', 'trade_time')

            if from_date:
                queryset = queryset.filter(trade_date__gte=from_date)
            if to_date:
                queryset = queryset.filter(trade_date__lte=to_date)

            logger.info(f"Processing {queryset.count()} unreconciled broker trades for account {account.id}")

            # Group trades by trading_symbol (same instrument)
            grouped_trades = defaultdict(list)
            for trade in queryset:
                # Key by trading_symbol to match same instrument
                key = (trade.trading_symbol, trade.expiry_date)
                grouped_trades[key].append(trade)

            # Process each group
            for (trading_symbol, expiry_date), trades in grouped_trades.items():
                try:
                    result = TradeActionService._process_trade_group(
                        user=user,
                        account=account,
                        trading_symbol=trading_symbol,
                        expiry_date=expiry_date,
                        trades=trades
                    )

                    if result.get('created'):
                        created_trades.append(result['taken_trade'])
                    elif result.get('skipped'):
                        skipped_count += 1
                    elif result.get('error'):
                        errors.append(result['error'])

                except Exception as e:
                    error_msg = f"Error processing {trading_symbol}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            logger.info(f"Created {len(created_trades)} TakenTrades, skipped {skipped_count}, errors: {len(errors)}")

            return {
                'success': True,
                'created_count': len(created_trades),
                'skipped_count': skipped_count,
                'errors': errors,
                'created_trades': created_trades
            }

        except Exception as e:
            logger.exception(f"Error creating trades from broker history: {e}")
            return {
                'success': False,
                'created_count': 0,
                'skipped_count': 0,
                'errors': [str(e)],
                'created_trades': []
            }

    @staticmethod
    def _process_trade_group(user, account, trading_symbol, expiry_date, trades):
        """
        Process a group of trades for the same instrument.

        Returns:
            dict: {
                'created': bool,
                'taken_trade': TakenTrade (if created),
                'skipped': bool,
                'error': str (if error)
            }
        """
        # Calculate net position
        total_buy_qty = sum(t.quantity for t in trades if t.trade_type == 'BUY')
        total_sell_qty = sum(t.quantity for t in trades if t.trade_type == 'SELL')
        net_qty = total_buy_qty - total_sell_qty

        # If position is not fully closed, skip
        if net_qty != 0:
            logger.debug(f"Skipping {trading_symbol}: position not closed (net qty: {net_qty})")
            return {'skipped': True, 'reason': f'Position not closed (net qty: {net_qty})'}

        # Calculate P&L
        buy_value = sum(t.quantity * t.price for t in trades if t.trade_type == 'BUY')
        sell_value = sum(t.quantity * t.price for t in trades if t.trade_type == 'SELL')
        total_charges = sum(t.total_charges for t in trades)

        # For options sold (premium collected), P&L = sell_value - buy_value
        # For options bought, P&L = sell_value - buy_value (same formula)
        realized_pnl = sell_value - buy_value
        net_pnl = realized_pnl - total_charges

        # Determine trade type and direction
        first_trade = min(trades, key=lambda t: (t.trade_date, t.trade_time or datetime.min.time()))
        last_trade = max(trades, key=lambda t: (t.trade_date, t.trade_time or datetime.max.time()))

        # Determine if this is options or futures
        is_option = bool(first_trade.option_type)
        trade_type = 'OPTIONS' if is_option else 'FUTURES'

        # Determine direction based on first trade
        if first_trade.trade_type == 'SELL':
            direction = 'SHORT'  # Sold first (premium collection for options)
        else:
            direction = 'LONG'  # Bought first

        # Determine strategy based on broker
        if account.broker == 'KOTAK':
            strategy = 'kotak_strangle' if is_option else 'kotak_broken_iron_condor'
        else:
            strategy = 'icici_futures'

        # Calculate entry and exit prices
        if direction == 'SHORT':
            entry_price = sell_value / total_sell_qty if total_sell_qty else Decimal('0')
            exit_price = buy_value / total_buy_qty if total_buy_qty else Decimal('0')
        else:
            entry_price = buy_value / total_buy_qty if total_buy_qty else Decimal('0')
            exit_price = sell_value / total_sell_qty if total_sell_qty else Decimal('0')

        # Determine outcome
        if net_pnl > Decimal('100'):
            outcome = 'PROFIT'
        elif net_pnl < Decimal('-100'):
            outcome = 'LOSS'
        else:
            outcome = 'BREAKEVEN'

        # Extract symbol from trading_symbol
        symbol = first_trade.symbol or trading_symbol.split()[0]

        # Create TakenTrade
        taken_trade = TakenTrade.objects.create(
            user=user,
            account=account,
            strategy=strategy,
            trade_type=trade_type,
            instrument=symbol,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=total_buy_qty,
            lot_size=first_trade.quantity,  # Assuming single lot per trade
            expiry_date=expiry_date,
            status='CLOSED',
            outcome=outcome,
            taken_at=timezone.make_aware(datetime.combine(first_trade.trade_date, first_trade.trade_time or datetime.min.time())) if first_trade.trade_date else timezone.now(),
            executed_at=timezone.make_aware(datetime.combine(first_trade.trade_date, first_trade.trade_time or datetime.min.time())) if first_trade.trade_date else timezone.now(),
            closed_at=timezone.make_aware(datetime.combine(last_trade.trade_date, last_trade.trade_time or datetime.max.time())) if last_trade.trade_date else timezone.now(),
            realized_pnl=realized_pnl,
            charges=total_charges,
            net_pnl=net_pnl,
            notes=f"Auto-created from {len(trades)} broker trades"
        )

        # Link broker trades to TakenTrade
        for trade in trades:
            trade.taken_trade = taken_trade
            trade.is_reconciled = True
            trade.save()

        logger.info(f"Created TakenTrade {taken_trade.id} from {len(trades)} broker trades: {trading_symbol}, P&L: {net_pnl}")

        return {
            'created': True,
            'taken_trade': taken_trade
        }
