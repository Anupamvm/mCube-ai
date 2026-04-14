"""
Position Sync Service

Syncs position data from broker APIs (Kotak Neo & ICICI Breeze) to the unified Position model.
Includes both open positions and trade history.
"""

import logging
import re
from decimal import Decimal
from datetime import date
from django.utils import timezone

_EXPIRY_RE = re.compile(r'^([A-Z&]+)\d{2}[A-Z]{3}(FUT|CE|PE)\d*$')


def _underlying(display_name: str) -> str:
    """Extract underlying from futures/options display_name (e.g. HDFCBANK26MARFUT → HDFCBANK)."""
    m = _EXPIRY_RE.match(display_name or '')
    return m.group(1) if m else (display_name or '')

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

        # Get all active broker accounts (exclude paper trading accounts)
        accounts = BrokerAccount.objects.filter(is_active=True).exclude(is_paper_trading=True)

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


def sync_positions_from_broker_objects(account, broker_positions):
    """
    Upsert Position records from already-fetched broker position objects or dicts.

    Accepts both ORM objects (BrokerPosition) and plain dicts — reads fields with
    getattr-then-dict fallback so it works for both Kotak and Breeze data.

    Matching strategy:
    - If the broker object has an 'id' field (e.g. Breeze BrokerPosition ORM),
      use broker_position_id for exact matching — handles multiple positions
      with the same symbol (e.g. HDFBAN MAR + HDFBAN APR in Breeze).
    - Otherwise fall back to (account, instrument, OPEN) matching (Kotak).

    Also closes any DB positions that are no longer present at the broker.

    Returns:
        dict: {'created': int, 'updated': int, 'closed': int}
    """
    from apps.positions.models import Position
    from datetime import date as dt_date

    # Lot-size fallback for brokers that don't report it (e.g. Breeze reports 1)
    KNOWN_LOT_SIZES = [
        ('BANKNIFTY', 30), ('FINNIFTY', 40), ('MIDCPNIFTY', 75), ('NIFTY', 75),
        ('HDFCBANK', 550), ('HDFBAN', 550), ('ICICIBANK', 700), ('AXISBANK', 625),
        ('RELIANCE', 250), ('TCS', 150), ('INFY', 300), ('SBIN', 750),
    ]

    def _resolve_lot_size(symbol, broker_lot_size):
        if broker_lot_size and broker_lot_size > 1:
            return broker_lot_size
        sym_upper = symbol.upper()
        for key, ls in KNOWN_LOT_SIZES:
            if key in sym_upper:
                return ls
        return broker_lot_size or 1

    result = {'created': 0, 'updated': 0, 'closed': 0}
    broker_symbols = set()
    matched_db_ids = set()   # DB Position.id values matched during this sync
    now = timezone.now()

    def _get(obj, *keys, default=None):
        """Get a value from an object or dict, trying multiple key names.
        Returns the first non-None value found."""
        for key in keys:
            val = getattr(obj, key, None)
            if val is None and isinstance(obj, dict):
                val = obj.get(key)
            if val is not None:
                return val
        return default

    def _get_str(obj, *keys):
        """Get a non-empty string value, skipping blank strings."""
        for key in keys:
            val = getattr(obj, key, None)
            if val is None and isinstance(obj, dict):
                val = obj.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return ''

    for bp in broker_positions:
        net_qty = _get(bp, 'net_quantity', default=0) or 0
        if net_qty == 0:
            continue

        # instrument = original broker symbol (used for order placement)
        #   Kotak: trading_symbol e.g. HDFCBANK26MARFUT
        #   Breeze: symbol e.g. HDFBAN (trading_symbol is the display name)
        # display_name = unified human-friendly name (for UI)
        #   Kotak: same as trading_symbol
        #   Breeze: built from stock_code + expiry e.g. HDFCBANK26MARFUT
        trading_sym = _get_str(bp, 'trading_symbol')
        raw_symbol  = _get_str(bp, 'symbol')

        # For Breeze: trading_symbol is the display name, symbol is the broker code
        # For Kotak: trading_symbol is both the broker code and the display name
        if trading_sym and raw_symbol and trading_sym != raw_symbol:
            # Breeze case: trading_symbol was built by _build_trading_symbol
            symbol = raw_symbol           # broker code (HDFBAN)
            display_name = trading_sym    # clean name (HDFCBANK26MARFUT)
        elif trading_sym:
            # Kotak case: trading_symbol IS the broker code
            symbol = trading_sym
            display_name = trading_sym
        elif raw_symbol:
            symbol = raw_symbol
            display_name = raw_symbol
        else:
            continue

        broker_symbols.add(symbol)
        direction = 'LONG' if net_qty > 0 else 'SHORT'

        avg_price  = Decimal(str(_get(bp, 'average_price', default=0) or 0))
        ltp        = Decimal(str(_get(bp, 'ltp', default=0) or 0))
        unrealized = Decimal(str(_get(bp, 'unrealized_pnl', default=0) or 0))
        realized   = Decimal(str(_get(bp, 'realized_pnl', default=0) or 0))
        exchange   = _get_str(bp, 'exchange_segment', 'exchange')
        product    = _get_str(bp, 'product')
        lot_size   = _resolve_lot_size(display_name, int(_get(bp, 'lot_size', default=1) or 1))

        # Parse expiry_date (ISO string, date object, or None)
        expiry_raw = _get(bp, 'expiry_date', default=None)
        expiry_date = None
        if expiry_raw:
            try:
                if isinstance(expiry_raw, str):
                    expiry_date = dt_date.fromisoformat(expiry_raw[:10])
                elif isinstance(expiry_raw, dt_date):
                    expiry_date = expiry_raw
            except Exception:
                pass

        # ── Match existing position ──────────────────────────────────────────
        # Candidates: open positions for this (account, symbol) not yet matched
        candidates = list(Position.objects.filter(
            account=account,
            instrument=symbol,
            status=POSITION_STATUS_OPEN,
            source=POSITION_SOURCE_BROKER,
        ).exclude(id__in=matched_db_ids))

        existing = None
        if len(candidates) == 1:
            existing = candidates[0]
        elif len(candidates) > 1:
            # Multiple same-symbol positions (e.g. Breeze HDFBAN MAR + APR):
            # match by closest average_price to avoid mixing them up
            existing = min(candidates, key=lambda p: abs(float(p.entry_price) - float(avg_price)))

        if existing:
            existing.direction        = direction
            existing.quantity         = abs(net_qty)
            existing.current_price    = ltp
            existing.entry_price      = avg_price
            existing.unrealized_pnl   = unrealized
            # Don't overwrite realized_pnl — broker reports day-level trade
            # aggregates, not position-level realized P&L.  The monitor task
            # and close_position() manage this field correctly.
            existing.exchange_segment = exchange
            existing.product_type     = product
            existing.last_synced_at   = now
            existing.lot_size         = lot_size
            existing.display_name     = display_name
            if expiry_date:
                existing.expiry_date = expiry_date
            existing.save()
            matched_db_ids.add(existing.id)
            result['updated'] += 1
            logger.debug(f"Updated position: {display_name} | {direction} qty={abs(net_qty)} ltp={ltp}")
        else:
            pos = Position.objects.create(
                account=account,
                instrument=symbol,
                display_name=display_name,
                direction=direction,
                quantity=abs(net_qty),
                lot_size=lot_size,
                entry_price=avg_price,
                current_price=ltp,
                unrealized_pnl=unrealized,
                realized_pnl=Decimal('0'),  # Position-level; set by close_position()
                status=POSITION_STATUS_OPEN,
                source=POSITION_SOURCE_BROKER,
                exchange_segment=exchange,
                product_type=product,
                expiry_date=expiry_date,
                entry_time=now,
                last_synced_at=now,
            )
            matched_db_ids.add(pos.id)
            result['created'] += 1
            logger.info(f"Created position: {display_name} | {direction} qty={abs(net_qty)} avg={avg_price}")

            # Immediately initialize SL/target from structural S/R for new positions.
            # Gives downstream flows (monitoring, averaging, exit) real levels from
            # the first moment — rather than waiting for the next monitor task cycle.
            # Pass LTP only — entry price (avg_price) must never be used as SR reference.
            # If LTP is zero (e.g. after-hours sync), _init_sr_levels will skip safely.
            _init_sr_levels(pos, symbol, float(ltp or 0), direction)

    # ── Close stale: any open positions for this account not matched this sync
    stale = Position.objects.filter(
        account=account,
        source=POSITION_SOURCE_BROKER,
        status=POSITION_STATUS_OPEN,
    ).exclude(id__in=matched_db_ids)
    for pos in stale:
        pos.status = POSITION_STATUS_CLOSED
        pos.exit_time = now
        pos.exit_reason = 'BROKER_SYNC'
        pos.save()
        result['closed'] += 1
        logger.info(f"Closed stale position: {pos.instrument}")

    return result


def sync_kotak_positions(account):
    """Sync positions from Kotak Neo API."""
    try:
        from apps.brokers.integrations.kotak_neo import fetch_and_save_kotakneo_data
        limit_record, broker_positions, *_ = fetch_and_save_kotakneo_data()
        result = sync_positions_from_broker_objects(account, broker_positions)
        logger.info(f"Kotak sync: {result}")
        return result
    except Exception as e:
        logger.error(f"Error syncing Kotak positions: {e}")
        raise


def sync_breeze_positions(account):
    """Sync positions from ICICI Breeze API."""
    try:
        from apps.brokers.integrations.breeze_module.data_fetcher import fetch_and_save_breeze_data
        limit_record, broker_positions = fetch_and_save_breeze_data()
        result = sync_positions_from_broker_objects(account, broker_positions)
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


def _init_sr_levels(position, symbol: str, price: float, direction: str):
    """
    Compute structural S/R-based SL/target for a freshly created position and
    save both fields in a single DB write.

    Uses display_name to extract the underlying symbol (e.g. HDFCBANK26MARFUT →
    HDFCBANK) so that positions across different brokers (which may use different
    instrument codes like HDFBAN vs HDFCBANK) are correctly grouped together.

    If any existing sibling already has SL/Target, the new position inherits
    those exact values — no recomputation — ensuring consistency across brokers
    and expiry contracts for the same underlying.

    Never raises — all errors are silently logged so the sync itself never fails.
    """
    # Only proceed if we have a live LTP — entry/buying price must never be used
    # as a reference for SR computation; SR depends only on CMP and market structure.
    if not price or price <= 0 or direction == 'NEUTRAL':
        return
    try:
        from apps.positions.services.sr_exit_engine import compute_initial_sl_target
        from apps.positions.models import Position

        # Derive the underlying (HDFCBANK26MARFUT → HDFCBANK) so the sibling
        # query groups across brokers that use different instrument codes.
        underlying = _underlying(position.display_name or symbol)

        existing_siblings = list(Position.objects.filter(
            display_name__startswith=underlying,
            direction=direction,
            status=POSITION_STATUS_OPEN,
        ).exclude(id=position.id))

        # If any existing sibling already has SL/Target (from a prior computation),
        # inherit those exact values for the new position — no recomputation.
        # This guarantees consistency: all positions of the same instrument always
        # share identical SR levels regardless of when each was synced.
        existing_sl  = next((sib.stop_loss for sib in existing_siblings if sib.stop_loss),  None)
        existing_tgt = next((sib.target    for sib in existing_siblings if sib.target),     None)

        if existing_sl or existing_tgt:
            new_fields = []
            if existing_sl and not position.stop_loss:
                position.stop_loss = existing_sl
                new_fields.append('stop_loss')
            if existing_tgt and not position.target:
                position.target = existing_tgt
                new_fields.append('target')
            if new_fields:
                position.save(update_fields=new_fields)
                logger.info(
                    f"SR init (inherited from sibling): {position.display_name} {direction} "
                    f"SL={position.stop_loss} Target={position.target}"
                )
            return

        # No existing sibling has values — compute fresh SR levels.
        all_prices = [float(p.current_price or p.entry_price or 0) for p in existing_siblings]
        all_prices.append(price)
        ref_price = max(p for p in all_prices if p > 0)

        sr = compute_initial_sl_target(underlying, ref_price, direction)
        if not sr['stop_loss'] and not sr['target']:
            return

        sl_dec  = Decimal(str(round(sr['stop_loss'], 2))) if sr['stop_loss'] else None
        tgt_dec = Decimal(str(round(sr['target'],    2))) if sr['target']    else None

        # Apply to the new position
        new_fields = []
        if sl_dec and not position.stop_loss:
            position.stop_loss = sl_dec
            new_fields.append('stop_loss')
        if tgt_dec and not position.target:
            position.target = tgt_dec
            new_fields.append('target')
        if new_fields:
            position.save(update_fields=new_fields)
            logger.info(
                f"SR init: {position.display_name} {direction} "
                f"SL={position.stop_loss} Target={position.target}"
            )

        # Propagate to existing siblings that are missing levels
        for sib in existing_siblings:
            fields = []
            if sl_dec and not sib.stop_loss:
                sib.stop_loss = sl_dec
                fields.append('stop_loss')
            if tgt_dec and not sib.target:
                sib.target = tgt_dec
                fields.append('target')
            if fields:
                sib.save(update_fields=fields)
                logger.info(
                    f"SR init propagated to sibling id={sib.id} {sib.display_name}: "
                    f"SL={sib.stop_loss} Target={sib.target}"
                )

    except Exception as e:
        logger.debug(f"SR init skipped for {symbol}: {e}")


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
