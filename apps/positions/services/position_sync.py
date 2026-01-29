"""
Position Sync Service

Syncs position data from broker APIs (Kotak Neo & ICICI Breeze) to the unified Position model.
Includes both open positions and trade history.
"""

import logging
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone

from apps.core.constants import (
    POSITION_STATUS_OPEN,
    POSITION_STATUS_CLOSED,
    POSITION_SOURCE_BROKER,
    BROKER_KOTAK,
    BROKER_ICICI,
)

logger = logging.getLogger(__name__)


def get_financial_year_start():
    """Get the start date of current Indian financial year (April 1)."""
    today = date.today()
    if today.month >= 4:
        return date(today.year, 4, 1)
    else:
        return date(today.year - 1, 4, 1)


def sync_positions_from_brokers(clear_existing=False, include_history=True):
    """
    Sync positions from all active broker accounts.

    Args:
        clear_existing: If True, clears existing BROKER positions before sync
        include_history: If True, also syncs trade history for current FY

    Returns:
        dict: Summary of sync operation
    """
    from apps.accounts.models import BrokerAccount
    from apps.positions.models import Position

    results = {
        'success': True,
        'accounts_synced': 0,
        'positions_created': 0,
        'positions_updated': 0,
        'positions_closed': 0,
        'history_synced': 0,
        'errors': []
    }

    try:
        # Optionally clear existing broker positions
        if clear_existing:
            deleted_count = Position.objects.filter(
                source=POSITION_SOURCE_BROKER
            ).delete()[0]
            logger.info(f"Cleared {deleted_count} existing broker positions")

        # Get all active broker accounts
        accounts = BrokerAccount.objects.filter(is_active=True)

        for account in accounts:
            try:
                # Sync open positions
                if account.broker == BROKER_KOTAK:
                    synced = sync_kotak_positions(account)
                elif account.broker == BROKER_ICICI:
                    synced = sync_breeze_positions(account)
                else:
                    logger.warning(f"Unknown broker: {account.broker}")
                    continue

                results['accounts_synced'] += 1
                results['positions_created'] += synced.get('created', 0)
                results['positions_updated'] += synced.get('updated', 0)
                results['positions_closed'] += synced.get('closed', 0)

                # Sync trade history
                if include_history:
                    history_result = sync_trade_history(account)
                    results['history_synced'] += history_result.get('synced', 0)

            except Exception as e:
                error_msg = f"Error syncing {account.broker} ({account.account_name}): {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)

        logger.info(f"Sync complete: {results}")
        return results

    except Exception as e:
        logger.error(f"Fatal error in sync_positions_from_brokers: {e}")
        results['success'] = False
        results['errors'].append(str(e))
        return results


def sync_kotak_positions(account):
    """Sync positions from Kotak Neo API."""
    from apps.positions.models import Position
    from apps.brokers.models import BrokerPosition

    result = {'created': 0, 'updated': 0, 'closed': 0}

    try:
        from apps.brokers.integrations.neo.data_fetcher import fetch_and_save_kotakneo_data
        limit_record, broker_positions = fetch_and_save_kotakneo_data()

        broker_symbols = set()

        for bp in broker_positions:
            if bp.net_quantity == 0:
                continue

            broker_symbols.add(bp.symbol)
            direction = 'LONG' if bp.net_quantity > 0 else 'SHORT'

            existing = Position.objects.filter(
                account=account,
                instrument=bp.symbol,
                status=POSITION_STATUS_OPEN,
                source=POSITION_SOURCE_BROKER
            ).first()

            if existing:
                existing.quantity = abs(bp.net_quantity)
                existing.current_price = bp.ltp
                existing.entry_price = bp.average_price
                existing.unrealized_pnl = bp.unrealized_pnl
                existing.realized_pnl = bp.realized_pnl
                existing.exchange_segment = bp.exchange_segment
                existing.product_type = bp.product
                existing.last_synced_at = timezone.now()
                existing.save()
                result['updated'] += 1
            else:
                Position.objects.create(
                    account=account,
                    instrument=bp.symbol,
                    direction=direction,
                    quantity=abs(bp.net_quantity),
                    lot_size=1,
                    entry_price=bp.average_price,
                    current_price=bp.ltp,
                    unrealized_pnl=bp.unrealized_pnl,
                    realized_pnl=bp.realized_pnl,
                    status=POSITION_STATUS_OPEN,
                    source=POSITION_SOURCE_BROKER,
                    exchange_segment=bp.exchange_segment,
                    product_type=bp.product,
                    entry_time=timezone.now(),
                    last_synced_at=timezone.now(),
                )
                result['created'] += 1

        # Close stale positions
        stale = Position.objects.filter(
            account=account,
            source=POSITION_SOURCE_BROKER,
            status=POSITION_STATUS_OPEN
        ).exclude(instrument__in=broker_symbols)

        for pos in stale:
            pos.status = POSITION_STATUS_CLOSED
            pos.exit_time = timezone.now()
            pos.exit_reason = 'BROKER_SYNC'
            pos.save()
            result['closed'] += 1

        logger.info(f"Kotak sync: {result}")
        return result

    except Exception as e:
        logger.error(f"Error syncing Kotak positions: {e}")
        raise


def sync_breeze_positions(account):
    """Sync positions from ICICI Breeze API."""
    from apps.positions.models import Position
    from apps.brokers.models import BrokerPosition

    result = {'created': 0, 'updated': 0, 'closed': 0}

    try:
        from apps.brokers.integrations.breeze_module.data_fetcher import fetch_and_save_breeze_data
        limit_record, broker_positions = fetch_and_save_breeze_data()

        broker_symbols = set()

        for bp in broker_positions:
            if bp.net_quantity == 0:
                continue

            broker_symbols.add(bp.symbol)
            direction = 'LONG' if bp.net_quantity > 0 else 'SHORT'

            existing = Position.objects.filter(
                account=account,
                instrument=bp.symbol,
                status=POSITION_STATUS_OPEN,
                source=POSITION_SOURCE_BROKER
            ).first()

            if existing:
                existing.quantity = abs(bp.net_quantity)
                existing.current_price = bp.ltp
                existing.entry_price = bp.average_price
                existing.unrealized_pnl = bp.unrealized_pnl
                existing.realized_pnl = bp.realized_pnl
                existing.exchange_segment = bp.exchange_segment
                existing.product_type = bp.product
                existing.last_synced_at = timezone.now()
                existing.save()
                result['updated'] += 1
            else:
                Position.objects.create(
                    account=account,
                    instrument=bp.symbol,
                    direction=direction,
                    quantity=abs(bp.net_quantity),
                    lot_size=1,
                    entry_price=bp.average_price,
                    current_price=bp.ltp,
                    unrealized_pnl=bp.unrealized_pnl,
                    realized_pnl=bp.realized_pnl,
                    status=POSITION_STATUS_OPEN,
                    source=POSITION_SOURCE_BROKER,
                    exchange_segment=bp.exchange_segment,
                    product_type=bp.product,
                    entry_time=timezone.now(),
                    last_synced_at=timezone.now(),
                )
                result['created'] += 1

        # Close stale positions
        stale = Position.objects.filter(
            account=account,
            source=POSITION_SOURCE_BROKER,
            status=POSITION_STATUS_OPEN
        ).exclude(instrument__in=broker_symbols)

        for pos in stale:
            pos.status = POSITION_STATUS_CLOSED
            pos.exit_time = timezone.now()
            pos.exit_reason = 'BROKER_SYNC'
            pos.save()
            result['closed'] += 1

        logger.info(f"Breeze sync: {result}")
        return result

    except Exception as e:
        logger.error(f"Error syncing Breeze positions: {e}")
        raise


def sync_trade_history(account):
    """
    Sync trade history from broker to Position model as CLOSED positions.

    Fetches trades from current financial year start to today.
    """
    from apps.positions.models import Position
    from apps.brokers.models import BrokerTradeHistory
    from apps.brokers.services.trade_sync import TradeSyncService

    result = {'synced': 0, 'errors': []}

    try:
        # Get date range for current FY
        fy_start = get_financial_year_start()
        today = date.today()

        logger.info(f"Syncing trade history for {account.account_name}: {fy_start} to {today}")

        # First sync trades to BrokerTradeHistory
        sync_result = TradeSyncService.sync_trades_for_date_range(
            account, fy_start, today
        )

        if not sync_result.get('success'):
            result['errors'] = sync_result.get('errors', [])
            return result

        # Now convert BrokerTradeHistory to Position records
        # Group trades by symbol and create aggregated closed positions
        trades = BrokerTradeHistory.objects.filter(
            account=account,
            trade_date__gte=fy_start,
            trade_date__lte=today
        ).order_by('trade_date', 'trade_time')

        # Group trades into positions (entry + exit pairs)
        symbol_trades = {}
        for trade in trades:
            symbol = trade.symbol or trade.trading_symbol
            if symbol not in symbol_trades:
                symbol_trades[symbol] = []
            symbol_trades[symbol].append(trade)

        for symbol, trades_list in symbol_trades.items():
            try:
                # Check if position already exists
                existing = Position.objects.filter(
                    account=account,
                    instrument=symbol,
                    status=POSITION_STATUS_CLOSED,
                    source=POSITION_SOURCE_BROKER,
                    broker_position_id=f"history_{symbol}"
                ).first()

                if existing:
                    continue  # Skip if already synced

                # Calculate aggregated position data
                buy_qty = sum(t.quantity for t in trades_list if t.trade_type == 'BUY')
                sell_qty = sum(t.quantity for t in trades_list if t.trade_type == 'SELL')
                buy_value = sum(t.quantity * float(t.price) for t in trades_list if t.trade_type == 'BUY')
                sell_value = sum(t.quantity * float(t.price) for t in trades_list if t.trade_type == 'SELL')

                if buy_qty == 0 and sell_qty == 0:
                    continue

                # Determine direction based on first trade
                first_trade = trades_list[0]
                direction = 'LONG' if first_trade.trade_type == 'BUY' else 'SHORT'

                # Calculate entry/exit prices
                entry_price = buy_value / buy_qty if buy_qty > 0 else 0
                exit_price = sell_value / sell_qty if sell_qty > 0 else 0

                # Calculate realized P&L
                if direction == 'LONG':
                    realized_pnl = sell_value - buy_value
                else:
                    realized_pnl = buy_value - sell_value

                # Only create if position is closed (equal buy/sell)
                if buy_qty == sell_qty:
                    first_date = trades_list[0].trade_date
                    last_date = trades_list[-1].trade_date

                    Position.objects.create(
                        account=account,
                        instrument=symbol,
                        direction=direction,
                        quantity=buy_qty,
                        lot_size=1,
                        entry_price=Decimal(str(entry_price)),
                        exit_price=Decimal(str(exit_price)),
                        current_price=Decimal(str(exit_price)),
                        realized_pnl=Decimal(str(realized_pnl)),
                        unrealized_pnl=Decimal('0'),
                        status=POSITION_STATUS_CLOSED,
                        source=POSITION_SOURCE_BROKER,
                        exchange_segment=first_trade.segment or '',
                        product_type=first_trade.product_type or '',
                        entry_time=timezone.make_aware(
                            timezone.datetime.combine(first_date, timezone.datetime.min.time())
                        ) if first_date else None,
                        exit_time=timezone.make_aware(
                            timezone.datetime.combine(last_date, timezone.datetime.min.time())
                        ) if last_date else None,
                        exit_reason='CLOSED',
                        broker_position_id=f"history_{symbol}",
                        last_synced_at=timezone.now(),
                    )
                    result['synced'] += 1
                    logger.info(f"Created closed position for {symbol}: P&L={realized_pnl:.2f}")

            except Exception as e:
                error_msg = f"Error processing trades for {symbol}: {e}"
                logger.error(error_msg)
                result['errors'].append(error_msg)

        logger.info(f"Trade history sync: {result['synced']} positions created")
        return result

    except Exception as e:
        logger.error(f"Error syncing trade history: {e}")
        result['errors'].append(str(e))
        return result


def get_position_summary():
    """Get summary of all positions by status and source."""
    from apps.positions.models import Position
    from apps.core.constants import (
        POSITION_STATUS_SUGGESTED,
        POSITION_SOURCE_SYSTEM,
    )

    return {
        'open_positions': Position.objects.filter(
            status=POSITION_STATUS_OPEN
        ).select_related('account').order_by('-entry_time'),

        'suggestions': Position.objects.filter(
            source=POSITION_SOURCE_SYSTEM,
            status=POSITION_STATUS_SUGGESTED
        ).order_by('-created_at'),

        'trade_history': Position.objects.filter(
            status=POSITION_STATUS_CLOSED
        ).select_related('account').order_by('-exit_time')[:50],

        'counts': {
            'open': Position.objects.filter(status=POSITION_STATUS_OPEN).count(),
            'suggested': Position.objects.filter(status=POSITION_STATUS_SUGGESTED).count(),
            'closed': Position.objects.filter(status=POSITION_STATUS_CLOSED).count(),
        }
    }
