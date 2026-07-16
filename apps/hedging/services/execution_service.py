"""
Order placement / roll / close orchestration for Cover Position.

Every place_*/execute_* function requires an authenticated `user` argument
and writes a HedgeAuditLog row carrying that user — this is the concrete,
auditable enforcement point for "no hedge action ever fires unattended".
No Celery task, cron, or signal handler is permitted to import and call
these functions in v1 (see the plan's Phase 2 note on automated exit
rules) — that is enforced by code-review discipline, not by anything in
this file itself.
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import BrokerAccount
from apps.hedging.models import (
    HEDGE_STATUS_ACTIVE,
    HEDGE_STATUS_CLOSED,
    HedgeAuditLog,
    HedgeLeg,
    HedgePosition,
)
from apps.hedging.services import chain_service, payoff_engine
from apps.hedging.services.charges_calculator import calculate_option_transaction_charges
from apps.hedging.services.recommendation_engine import CoveredCallRecommendationEngine
from apps.hedging.services.validators import (
    HedgeValidationError,
    acquire_placement_lock,
    assess_liquidity_warnings,
    find_existing_active_hedge,
    release_placement_lock,
    validate_expiry_alignment,
    validate_lot_size_match,
    validate_margin,
    validate_quantity_cap,
)

logger = logging.getLogger(__name__)

BATCH_THRESHOLD_LOTS = 10
BATCH_SIZE_LOTS = 10
NEO_BATCH_DELAY_SECONDS = 10
BREEZE_BATCH_DELAY_SECONDS = 40

# Maps the hedging app's 'breeze'/'neo' execution-routing string to the
# apps.core.constants BROKER_CHOICES vocabulary used by BrokerAccount —
# these are two different, legitimate vocabularies in this codebase (see
# plan Context section); do not merge them.
BROKER_ACCOUNT_MAP = {'breeze': 'ICICI', 'neo': 'KOTAK'}


# ─────────────────────────────────────────────────────────────────────────
# Live data lookups (never trust client-supplied numbers for hard checks)
# ─────────────────────────────────────────────────────────────────────────

def _get_broker_account(broker: str) -> BrokerAccount:
    account_broker = BROKER_ACCOUNT_MAP.get(broker)
    account = BrokerAccount.objects.filter(broker=account_broker, is_active=True).first()
    if not account:
        raise HedgeValidationError('NO_ACCOUNT', f"No active BrokerAccount found for broker={broker!r}")
    return account


def _fetch_live_futures_position(broker: str, underlying_symbol: str, futures_expiry_date: date) -> dict:
    """
    Re-fetch the live futures position from the broker at request time —
    mirrors the parsing done by apps.trading.api_views.get_active_positions
    (same data sources, same lot-size resolution) so the hedging app never
    silently drifts from what the Open Trades page itself shows. Only the
    FUTURES leg is returned (trading_symbol containing 'FUT'), matching the
    same classification the Open Trades page template uses
    (deriveInstrumentType() in view_trades.html).
    """
    positions_data = []

    if broker == 'breeze':
        from apps.brokers.integrations.breeze import fetch_and_save_breeze_data
        from apps.trading.api_views import _resolve_lot_size

        _, positions = fetch_and_save_breeze_data()
        for pos in positions or []:
            trading_symbol = (pos.trading_symbol or pos.symbol or '').upper()
            if 'FUT' not in trading_symbol:
                continue
            if pos.symbol != underlying_symbol:
                continue
            if pos.expiry_date != futures_expiry_date:
                continue
            avg_price = float(pos.average_price or 0)
            ltp = float(pos.ltp or 0)
            net_qty = pos.net_quantity
            lot_size = _resolve_lot_size(pos.symbol, pos.lot_size or 1)
            lots = abs(net_qty) // lot_size if lot_size > 1 else abs(net_qty)
            positions_data.append({
                'direction': 'LONG' if net_qty > 0 else 'SHORT',
                'lots': lots,
                'lot_size': lot_size,
                'average_price': avg_price,
                'ltp': ltp,
            })

    elif broker == 'neo':
        from apps.brokers.integrations.kotak_neo import get_neo_open_positions

        result = get_neo_open_positions(include_raw=True)
        for pos in (result.get('positions') or []):
            trading_symbol = (pos.get('trading_symbol') or pos.get('symbol') or '').upper()
            if 'FUT' not in trading_symbol:
                continue
            if pos.get('symbol') != underlying_symbol:
                continue
            pos_expiry = pos.get('expiry_date')
            if pos_expiry and str(pos_expiry) != futures_expiry_date.strftime('%Y-%m-%d'):
                continue
            positions_data.append({
                'direction': pos.get('direction', 'LONG'),
                'lots': int(pos.get('quantity') or 0),
                'lot_size': int(pos.get('lot_size') or 1),
                'average_price': float(pos.get('average_price') or 0),
                'ltp': float(pos.get('ltp') or 0),
            })
    else:
        raise HedgeValidationError('UNKNOWN_BROKER', f"Unknown broker: {broker!r}")

    if not positions_data:
        raise HedgeValidationError(
            'FUTURES_POSITION_NOT_FOUND',
            f"No live LONG futures position found for {underlying_symbol} "
            f"expiring {futures_expiry_date} on {broker}.",
        )
    return positions_data[0]


def _already_covered_lots(broker: str, underlying_symbol: str, futures_expiry_date: date) -> int:
    hedge = find_existing_active_hedge(broker, underlying_symbol, futures_expiry_date)
    if not hedge:
        return 0
    return hedge.futures_lots_covered - hedge.uncovered_lots


def is_lot_size_unconfirmed(lot_size: int) -> bool:
    """
    apps.trading.api_views._resolve_lot_size (and this module's mirror of
    it) fall back to lot_size=1 when it can't find a real lot size for a
    symbol — at which point the futures "lots" figure is actually a raw
    share/unit count, not a true lot count. No real NSE F&O contract has a
    lot size of 1. This is surfaced as a non-blocking warning (not a hard
    block) wherever futures context is shown or used for sizing — the
    numbers on screen may be wrong, but the user can still proceed and
    manually verify before placing an order.
    """
    return lot_size <= 1


def get_futures_context(broker: str, underlying_symbol: str, futures_expiry_date: date) -> dict:
    """
    Public wrapper combining the live futures position with current hedge
    coverage state — the one call api_views needs for both the chain
    endpoint and the active-status badge, without reaching into this
    module's private helpers directly.
    """
    futures_pos = _fetch_live_futures_position(broker, underlying_symbol, futures_expiry_date)
    already_covered = _already_covered_lots(broker, underlying_symbol, futures_expiry_date)
    return {
        **futures_pos,
        'already_covered_lots': already_covered,
        'uncovered_lots': futures_pos['lots'] - already_covered,
        'lot_size_unconfirmed': is_lot_size_unconfirmed(futures_pos['lot_size']),
    }


def _estimate_option_sell_margin(premium: float, strike: float, spot: float, lot_size: int, lots: int) -> Decimal:
    """
    Approximate exchange-style minimum margin for a short option:
    Premium + MAX(10% of underlying - OTM amount, 5% of underlying), per
    lot, scaled by quantity. This is a conservative ESTIMATE for the
    preview panel, not a broker SPAN+exposure quote — Breeze/Neo margin
    APIs for a covered short-call leg were not confirmed to behave the
    same way as the futures-only margin_service.get_margin_per_lot()
    during design (flagged as a verify-in-implementation item in the
    plan). Replace with a real broker margin call if/when confirmed.
    """
    otm_amount = max(strike - spot, 0.0)
    span_estimate = max(0.10 * spot - otm_amount, 0.05 * spot)
    per_share = premium + span_estimate
    return Decimal(str(round(per_share * lot_size * lots, 2)))


def _find_chain_row(chain_rows: list, strike) -> Optional[dict]:
    target = Decimal(str(strike))
    for row in chain_rows:
        if Decimal(str(row['strike'])) == target:
            return row
    return None


# ─────────────────────────────────────────────────────────────────────────
# Progress polling (cache-based, mirrors apps.trading.api_views'
# close-position progress convention exactly, in a separate key namespace)
# ─────────────────────────────────────────────────────────────────────────

def _progress_key(user_id: int, broker: str, symbol: str) -> str:
    return f"hedge_progress_{user_id}_{broker}_{symbol.replace('/', '_')}"


def _init_progress(user_id: int, broker: str, symbol: str, total_batches: int) -> None:
    cache.set(_progress_key(user_id, broker, symbol), {
        'batches_completed': 0,
        'total_batches': total_batches,
        'current_batch': None,
        'is_cancelled': False,
        'is_complete': False,
        'is_success': False,
        'last_log_message': 'Starting execution...',
        'last_log_type': 'info',
    }, timeout=600)


def _update_progress(user_id: int, broker: str, symbol: str, **kwargs) -> None:
    key = _progress_key(user_id, broker, symbol)
    progress = cache.get(key, {})
    progress.update(kwargs)
    cache.set(key, progress, timeout=600)


def get_order_progress(user_id: int, broker: str, symbol: str) -> dict:
    return cache.get(_progress_key(user_id, broker, symbol), {
        'batches_completed': 0, 'total_batches': 0, 'current_batch': None,
        'is_cancelled': False, 'is_complete': False, 'is_success': False,
        'last_log_message': None, 'last_log_type': None,
    })


# ─────────────────────────────────────────────────────────────────────────
# Preview
# ─────────────────────────────────────────────────────────────────────────

def preview_cover_order(
    broker: str,
    underlying_symbol: str,
    futures_expiry_date: date,
    option_expiry_date: date,
    strike,
    lots: int,
    order_type: str = 'MARKET',
    limit_price: Optional[float] = None,
) -> dict:
    """
    No order placed. Runs the same validations `place_cover_order` will
    hard-enforce, but collects failures as `blocking_issues` instead of
    raising, plus non-blocking liquidity `warnings`, so the UI can render
    a fully-populated preview panel with the Place Order button disabled
    if anything blocking is present.
    """
    blocking_issues: list = []
    warnings: list = []

    futures_pos = _fetch_live_futures_position(broker, underlying_symbol, futures_expiry_date)
    live_lots, lot_size, futures_avg_price, spot_price = (
        futures_pos['lots'], futures_pos['lot_size'], futures_pos['average_price'], futures_pos['ltp'],
    )
    already_covered = _already_covered_lots(broker, underlying_symbol, futures_expiry_date)

    if is_lot_size_unconfirmed(lot_size):
        warnings.append({
            'code': 'LOT_SIZE_UNCONFIRMED',
            'message': (
                f"Could not resolve a confirmed F&O lot size for {underlying_symbol} — the "
                f"'lots' figures on this page may actually be raw units. Verify the real lot "
                f"size before relying on the quantity cap or breakeven numbers shown here."
            ),
        })

    try:
        validate_quantity_cap(live_lots, already_covered, lots)
    except HedgeValidationError as exc:
        blocking_issues.append({'code': exc.code, 'message': exc.message})

    try:
        validate_expiry_alignment(option_expiry_date, futures_expiry_date)
    except HedgeValidationError as exc:
        blocking_issues.append({'code': exc.code, 'message': exc.message})

    chain_rows = chain_service.fetch_covered_call_chain(underlying_symbol, option_expiry_date, Decimal(str(spot_price)))
    chain_row = _find_chain_row(chain_rows, strike)
    if not chain_row:
        blocking_issues.append({'code': 'STRIKE_NOT_FOUND', 'message': f"Strike {strike} not found in the fetched chain."})
        premium = 0.0
    else:
        premium = float(chain_row['ltp'] or 0)
        warnings += [{'code': 'LIQUIDITY', 'message': w} for w in assess_liquidity_warnings(chain_row)]

        try:
            resolved = chain_service.resolve_execution_symbol(broker, underlying_symbol, option_expiry_date, strike, 'CE')
            validate_lot_size_match(resolved['lot_size'], lot_size)
        except HedgeValidationError as exc:
            blocking_issues.append({'code': exc.code, 'message': exc.message})
        except Exception as exc:
            blocking_issues.append({'code': 'SYMBOL_RESOLUTION_FAILED', 'message': str(exc)})

    existing_hedge = find_existing_active_hedge(broker, underlying_symbol, futures_expiry_date)
    existing_net_premium = float(existing_hedge.net_premium_collected) if existing_hedge else 0.0
    total_lots_covered_after = already_covered + lots

    new_net_premium = existing_net_premium + (premium * lots * lot_size)
    effective_breakeven = payoff_engine.calculate_effective_breakeven(
        futures_avg_price, total_lots_covered_after, lot_size, new_net_premium,
    )
    max_profit = payoff_engine.calculate_max_profit(
        futures_avg_price, live_lots, lot_size, float(strike), premium, total_lots_covered_after,
    )
    protection = payoff_engine.calculate_protection_metrics(
        futures_avg_price, spot_price, new_net_premium, total_lots_covered_after, lot_size,
    )

    charges = calculate_option_transaction_charges(Decimal(str(premium)), lots, lot_size, 'SELL')
    required_margin = _estimate_option_sell_margin(premium, float(strike), spot_price, lot_size, lots)

    margin_message = None
    try:
        account = _get_broker_account(broker)
        margin_ok, margin_message = validate_margin(account, required_margin)
        if not margin_ok:
            blocking_issues.append({'code': 'INSUFFICIENT_MARGIN', 'message': margin_message})
    except HedgeValidationError as exc:
        blocking_issues.append({'code': exc.code, 'message': exc.message})
        margin_message = exc.message

    return {
        'futures_avg_price': futures_avg_price,
        'spot_price': spot_price,
        'live_futures_lots': live_lots,
        'already_covered_lots': already_covered,
        'uncovered_lots': live_lots - already_covered,
        'strike': float(strike),
        'premium_estimate': premium,
        'lots': lots,
        'lot_size': lot_size,
        'effective_breakeven': effective_breakeven,
        'max_profit': max_profit,
        'protection': protection,
        'margin_required': float(required_margin),
        'margin_message': margin_message,
        'charges': charges,
        'greeks': {k: chain_row.get(k) for k in ('delta', 'theta', 'gamma', 'vega', 'iv')} if chain_row else None,
        'warnings': warnings,
        'blocking_issues': blocking_issues,
        'can_place_order': not blocking_issues,
    }


# ─────────────────────────────────────────────────────────────────────────
# Placement
# ─────────────────────────────────────────────────────────────────────────

def _dispatch_sell_order(broker: str, underlying_symbol: str, option_expiry_date: date, strike, lots: int,
                          lot_size: int, order_type: str, limit_price: Optional[float]) -> dict:
    """Places ONE order (<= batch size) for the given broker. Returns a dict with success/order_id/error."""
    if broker == 'neo':
        from apps.brokers.integrations.kotak_neo import place_option_order

        resolved = chain_service.resolve_execution_symbol(broker, underlying_symbol, option_expiry_date, strike, 'CE')
        return place_option_order(
            trading_symbol=resolved['trading_symbol'],
            transaction_type='S',
            quantity=lots * lot_size,
            product='NRML',
            order_type='MKT' if order_type == 'MARKET' else 'L',
            price=limit_price or 0.0,
        )

    if broker == 'breeze':
        from apps.brokers.integrations.breeze import place_option_order_with_security_master

        breeze_expiry = chain_service.format_breeze_expiry(option_expiry_date)
        response = place_option_order_with_security_master(
            symbol=underlying_symbol,
            expiry_date=breeze_expiry,
            strike_price=float(strike),
            option_type='CE',
            action='sell',
            lots=lots,
            order_type='market' if order_type == 'MARKET' else 'limit',
            price=limit_price or 0.0,
        )
        if response.get('Status') == 200:
            order_id = response.get('Success', {}).get('order_id', 'UNKNOWN')
            return {'success': True, 'order_id': order_id, 'response': response}
        return {'success': False, 'error': response.get('Error', 'Unknown Breeze error'), 'response': response}

    if broker == 'paper':
        from apps.brokers.integrations.paper_broker import PaperBroker

        account = _get_broker_account('breeze')  # any account flagged is_paper_trading works for UAT
        paper_symbol = f"{underlying_symbol}{option_expiry_date.strftime('%d%b%Y').upper()}{int(strike)}CE"
        order_id = PaperBroker(account).place_order(
            symbol=paper_symbol, action='SELL', quantity=lots * lot_size,
            order_type='MKT' if order_type == 'MARKET' else 'L', price=limit_price or 0.0,
        )
        return {'success': bool(order_id), 'order_id': order_id} if order_id else {'success': False, 'error': 'Paper order rejected'}

    raise HedgeValidationError('UNKNOWN_BROKER', f"Unknown broker: {broker!r}")


def place_cover_order(
    user: User,
    broker: str,
    underlying_symbol: str,
    futures_expiry_date: date,
    option_expiry_date: date,
    strike,
    lots: int,
    order_type: str = 'MARKET',
    limit_price: Optional[float] = None,
    recommendation_snapshot: Optional[dict] = None,
) -> dict:
    """
    Hard-validates and places the SELL order for a covered call. Batches
    into BATCH_SIZE_LOTS-lot chunks (matching the existing Close Position
    batching convention) when `lots` exceeds BATCH_THRESHOLD_LOTS, writing
    progress into cache under the same shape as the existing close-position
    progress poll. Always requires an authenticated `user` — the concrete
    enforcement point for "no hedge action fires unattended".
    """
    if not (user and user.is_authenticated):
        raise HedgeValidationError('AUTH_REQUIRED', "A logged-in user is required to place a hedge order.")

    lock_acquired, lock_key = acquire_placement_lock(user.id, broker, underlying_symbol, strike, option_expiry_date)
    if not lock_acquired:
        raise HedgeValidationError('DUPLICATE_ORDER', "An identical order is already being placed — please wait.")

    try:
        futures_pos = _fetch_live_futures_position(broker, underlying_symbol, futures_expiry_date)
        live_lots, lot_size, futures_avg_price = futures_pos['lots'], futures_pos['lot_size'], futures_pos['average_price']
        already_covered = _already_covered_lots(broker, underlying_symbol, futures_expiry_date)

        validate_quantity_cap(live_lots, already_covered, lots)
        validate_expiry_alignment(option_expiry_date, futures_expiry_date)

        resolved = chain_service.resolve_execution_symbol(broker, underlying_symbol, option_expiry_date, strike, 'CE')
        validate_lot_size_match(resolved['lot_size'], lot_size)

        account = _get_broker_account(broker)
        required_margin = _estimate_option_sell_margin(
            0.0, float(strike), futures_pos['ltp'], lot_size, lots,  # premium unknown pre-fill; conservative $0 baseline handled by SPAN estimate itself
        )
        margin_ok, margin_message = validate_margin(account, required_margin)
        if not margin_ok:
            raise HedgeValidationError('INSUFFICIENT_MARGIN', margin_message)

        hedge = find_existing_active_hedge(broker, underlying_symbol, futures_expiry_date)
        if not hedge:
            hedge = HedgePosition.objects.create(
                account=account,
                broker=broker,
                underlying_symbol=underlying_symbol,
                futures_expiry_date=futures_expiry_date,
                status=HEDGE_STATUS_ACTIVE,
                futures_direction='LONG',
                futures_lots_covered=live_lots,
                futures_lot_size=lot_size,
                futures_avg_price=Decimal(str(futures_avg_price)),
                created_by=user,
            )
            HedgeAuditLog.objects.create(
                hedge_position=hedge, action=HedgeAuditLog.ACTION_CREATED, user=user,
            )

        total_batches = -(-lots // BATCH_SIZE_LOTS)  # ceiling division
        is_batched = lots > BATCH_THRESHOLD_LOTS
        if is_batched:
            _init_progress(user.id, broker, underlying_symbol, total_batches)

        remaining_lots = lots
        batch_num = 0
        filled_legs = []
        while remaining_lots > 0:
            batch_num += 1
            batch_lots = min(BATCH_SIZE_LOTS, remaining_lots)

            leg = HedgeLeg.objects.create(
                hedge_position=hedge,
                leg_type=HedgeLeg.LEG_TYPE_CALL,
                direction=HedgeLeg.DIRECTION_SELL,
                leg_role=HedgeLeg.ROLE_OPEN,
                option_trading_symbol=resolved['trading_symbol'] or '',
                breeze_source_symbol=f"{underlying_symbol}{option_expiry_date}{int(strike)}CE",
                strike_price=Decimal(str(strike)),
                option_type=HedgeLeg.OPTION_TYPE_CE,
                expiry_date=option_expiry_date,
                lots=batch_lots,
                lot_size=lot_size,
                order_type=order_type,
                limit_price=Decimal(str(limit_price)) if limit_price else None,
                status=HedgeLeg.STATUS_PENDING,
            )

            if is_batched:
                _update_progress(
                    user.id, broker, underlying_symbol,
                    current_batch={'batch_number': batch_num, 'lots': batch_lots},
                    last_log_message=f"Placing batch {batch_num}/{total_batches} ({batch_lots} lots)...",
                    last_log_type='info',
                )

            result = _dispatch_sell_order(broker, underlying_symbol, option_expiry_date, strike, batch_lots, lot_size, order_type, limit_price)

            if result.get('success'):
                leg.status = HedgeLeg.STATUS_PLACED
                leg.placed_at = timezone.now()
                leg.save(update_fields=['status', 'placed_at'])
                HedgeAuditLog.objects.create(
                    hedge_position=hedge, leg=leg, action=HedgeAuditLog.ACTION_PLACED, user=user,
                    notes=f"Batch {batch_num}/{total_batches}", snapshot={'broker_response': result},
                )
                filled_legs.append(leg)
                if is_batched:
                    _update_progress(
                        user.id, broker, underlying_symbol,
                        batches_completed=batch_num,
                        last_log_message=f"Batch {batch_num}/{total_batches} placed successfully.",
                        last_log_type='success',
                    )
            else:
                leg.status = HedgeLeg.STATUS_FAILED
                leg.save(update_fields=['status'])
                HedgeAuditLog.objects.create(
                    hedge_position=hedge, leg=leg, action=HedgeAuditLog.ACTION_VALIDATION_BLOCKED, user=user,
                    notes=f"Order placement failed: {result.get('error')}", snapshot={'broker_response': result},
                )
                if is_batched:
                    _update_progress(
                        user.id, broker, underlying_symbol,
                        is_complete=True, is_success=False,
                        last_log_message=f"Batch {batch_num} failed: {result.get('error')}",
                        last_log_type='error',
                    )
                raise HedgeValidationError('ORDER_FAILED', f"Batch {batch_num} failed: {result.get('error')}")

            remaining_lots -= batch_lots

        hedge.futures_lots_covered = max(hedge.futures_lots_covered, already_covered + lots)
        if recommendation_snapshot:
            hedge.recommendation_snapshot = recommendation_snapshot
        hedge.save(update_fields=['futures_lots_covered', 'recommendation_snapshot'])

        if is_batched:
            _update_progress(user.id, broker, underlying_symbol, is_complete=True, is_success=True,
                              last_log_message="All batches placed successfully.", last_log_type='success')

        return {
            'success': True,
            'hedge_position_id': hedge.id,
            'legs_placed': len(filled_legs),
            'total_batches': total_batches,
            'is_batched': is_batched,
        }
    finally:
        release_placement_lock(lock_key)


# ─────────────────────────────────────────────────────────────────────────
# Roll
# ─────────────────────────────────────────────────────────────────────────

def preview_roll(hedge_leg_id: int, new_strike, new_expiry: Optional[date] = None) -> dict:
    leg = HedgeLeg.objects.select_related('hedge_position').get(id=hedge_leg_id)
    hedge = leg.hedge_position
    option_expiry_date = new_expiry or leg.expiry_date

    futures_pos = _fetch_live_futures_position(hedge.broker, hedge.underlying_symbol, hedge.futures_expiry_date)
    spot_price = futures_pos['ltp']

    chain_rows = chain_service.fetch_covered_call_chain(hedge.underlying_symbol, option_expiry_date, Decimal(str(spot_price)))
    buyback_row = _find_chain_row(chain_rows, leg.strike_price) or {'ltp': leg.premium_per_share or 0}
    new_row = _find_chain_row(chain_rows, new_strike)

    buyback_cost = float(buyback_row['ltp'] or 0) * leg.lots * leg.lot_size
    new_premium = float(new_row['ltp']) if new_row else 0.0
    new_premium_total = new_premium * leg.lots * leg.lot_size
    net_credit_debit = new_premium_total - buyback_cost

    new_net_premium = float(hedge.net_premium_collected) + net_credit_debit
    new_breakeven = payoff_engine.calculate_effective_breakeven(
        float(hedge.futures_avg_price), hedge.futures_lots_covered, hedge.futures_lot_size, new_net_premium,
    )

    return {
        'current_strike': float(leg.strike_price),
        'new_strike': float(new_strike),
        'buyback_cost': buyback_cost,
        'new_premium': new_premium_total,
        'net_credit_debit': net_credit_debit,
        'new_effective_breakeven': new_breakeven,
        'new_option_expiry': option_expiry_date.isoformat(),
    }


def execute_roll(user: User, hedge_leg_id: int, new_strike, new_expiry: Optional[date] = None,
                  order_type: str = 'MARKET') -> dict:
    """Buy back the current short call, then sell the new strike — two sequential, user-clicked steps."""
    if not (user and user.is_authenticated):
        raise HedgeValidationError('AUTH_REQUIRED', "A logged-in user is required to roll a hedge.")

    leg = HedgeLeg.objects.select_related('hedge_position').get(id=hedge_leg_id)
    hedge = leg.hedge_position
    option_expiry_date = new_expiry or leg.expiry_date

    HedgeAuditLog.objects.create(hedge_position=hedge, leg=leg, action=HedgeAuditLog.ACTION_ROLL_INITIATED, user=user)

    # Step 1: buy back the existing short call.
    if hedge.broker == 'neo':
        from apps.brokers.integrations.kotak_neo import place_option_order
        resolved = chain_service.resolve_execution_symbol(hedge.broker, hedge.underlying_symbol, leg.expiry_date, leg.strike_price, 'CE')
        result = place_option_order(
            trading_symbol=resolved['trading_symbol'], transaction_type='B',
            quantity=leg.lots * leg.lot_size, product='NRML',
            order_type='MKT' if order_type == 'MARKET' else 'L',
        )
    elif hedge.broker == 'breeze':
        from apps.brokers.integrations.breeze import place_option_order_with_security_master
        breeze_expiry = chain_service.format_breeze_expiry(leg.expiry_date)
        response = place_option_order_with_security_master(
            symbol=hedge.underlying_symbol, expiry_date=breeze_expiry, strike_price=float(leg.strike_price),
            option_type='CE', action='buy', lots=leg.lots,
            order_type='market' if order_type == 'MARKET' else 'limit',
        )
        result = {'success': response.get('Status') == 200, 'order_id': response.get('Success', {}).get('order_id'), 'response': response}
    else:
        raise HedgeValidationError('UNKNOWN_BROKER', f"Unknown broker: {hedge.broker!r}")

    if not result.get('success'):
        HedgeAuditLog.objects.create(hedge_position=hedge, leg=leg, action=HedgeAuditLog.ACTION_VALIDATION_BLOCKED,
                                      user=user, notes=f"Roll buy-back failed: {result.get('error')}")
        raise HedgeValidationError('ROLL_BUYBACK_FAILED', f"Roll buy-back failed: {result.get('error')}")

    buyback_leg = HedgeLeg.objects.create(
        hedge_position=hedge, leg_type=HedgeLeg.LEG_TYPE_CALL, direction=HedgeLeg.DIRECTION_BUY,
        leg_role=HedgeLeg.ROLE_ROLL_CLOSE, option_trading_symbol=leg.option_trading_symbol,
        breeze_source_symbol=leg.breeze_source_symbol, strike_price=leg.strike_price,
        option_type=HedgeLeg.OPTION_TYPE_CE, expiry_date=leg.expiry_date, lots=leg.lots, lot_size=leg.lot_size,
        order_type=order_type, status=HedgeLeg.STATUS_PLACED, placed_at=timezone.now(), rolled_from=leg,
    )
    leg.status = HedgeLeg.STATUS_CANCELLED
    leg.save(update_fields=['status'])

    # Step 2: sell the new strike.
    sell_result = _dispatch_sell_order(hedge.broker, hedge.underlying_symbol, option_expiry_date, new_strike, leg.lots, leg.lot_size, order_type, None)
    if not sell_result.get('success'):
        HedgeAuditLog.objects.create(hedge_position=hedge, leg=buyback_leg, action=HedgeAuditLog.ACTION_VALIDATION_BLOCKED,
                                      user=user, notes=f"Roll new-sell failed: {sell_result.get('error')}")
        raise HedgeValidationError('ROLL_SELL_FAILED', f"Bought back old call but failed to sell new strike: {sell_result.get('error')}")

    new_leg = HedgeLeg.objects.create(
        hedge_position=hedge, leg_type=HedgeLeg.LEG_TYPE_CALL, direction=HedgeLeg.DIRECTION_SELL,
        leg_role=HedgeLeg.ROLE_ROLL_OPEN, strike_price=Decimal(str(new_strike)), option_type=HedgeLeg.OPTION_TYPE_CE,
        expiry_date=option_expiry_date, lots=leg.lots, lot_size=leg.lot_size, order_type=order_type,
        status=HedgeLeg.STATUS_PLACED, placed_at=timezone.now(), rolled_from=buyback_leg,
    )

    HedgeAuditLog.objects.create(hedge_position=hedge, leg=new_leg, action=HedgeAuditLog.ACTION_ROLL_COMPLETED, user=user)

    return {'success': True, 'buyback_leg_id': buyback_leg.id, 'new_leg_id': new_leg.id}


# ─────────────────────────────────────────────────────────────────────────
# Manual close (buy back the short call, undoing the hedge)
# ─────────────────────────────────────────────────────────────────────────

def preview_close_leg(hedge_leg_id: int) -> dict:
    leg = HedgeLeg.objects.select_related('hedge_position').get(id=hedge_leg_id)
    hedge = leg.hedge_position
    futures_pos = _fetch_live_futures_position(hedge.broker, hedge.underlying_symbol, hedge.futures_expiry_date)
    spot_price = futures_pos['ltp']

    chain_rows = chain_service.fetch_covered_call_chain(hedge.underlying_symbol, leg.expiry_date, Decimal(str(spot_price)))
    row = _find_chain_row(chain_rows, leg.strike_price)
    buyback_price = float(row['ltp']) if row else float(leg.premium_per_share or 0)
    buyback_cost = buyback_price * leg.lots * leg.lot_size

    remaining_lots_covered = hedge.futures_lots_covered - leg.lots
    resulting_breakeven = payoff_engine.calculate_effective_breakeven(
        float(hedge.futures_avg_price), max(remaining_lots_covered, 0), hedge.futures_lot_size,
        float(hedge.net_premium_collected) - buyback_cost,
    )
    return {'buyback_price': buyback_price, 'buyback_cost': buyback_cost, 'resulting_breakeven_of_underlying_future': resulting_breakeven}


def execute_close_leg(user: User, hedge_leg_id: int, order_type: str = 'MARKET') -> dict:
    if not (user and user.is_authenticated):
        raise HedgeValidationError('AUTH_REQUIRED', "A logged-in user is required to close a hedge leg.")

    leg = HedgeLeg.objects.select_related('hedge_position').get(id=hedge_leg_id)
    hedge = leg.hedge_position

    if hedge.broker == 'neo':
        from apps.brokers.integrations.kotak_neo import place_option_order
        resolved = chain_service.resolve_execution_symbol(hedge.broker, hedge.underlying_symbol, leg.expiry_date, leg.strike_price, 'CE')
        result = place_option_order(
            trading_symbol=resolved['trading_symbol'], transaction_type='B',
            quantity=leg.lots * leg.lot_size, product='NRML',
            order_type='MKT' if order_type == 'MARKET' else 'L',
        )
    elif hedge.broker == 'breeze':
        from apps.brokers.integrations.breeze import place_option_order_with_security_master
        breeze_expiry = chain_service.format_breeze_expiry(leg.expiry_date)
        response = place_option_order_with_security_master(
            symbol=hedge.underlying_symbol, expiry_date=breeze_expiry, strike_price=float(leg.strike_price),
            option_type='CE', action='buy', lots=leg.lots,
            order_type='market' if order_type == 'MARKET' else 'limit',
        )
        result = {'success': response.get('Status') == 200, 'order_id': response.get('Success', {}).get('order_id'), 'response': response}
    else:
        raise HedgeValidationError('UNKNOWN_BROKER', f"Unknown broker: {hedge.broker!r}")

    if not result.get('success'):
        HedgeAuditLog.objects.create(hedge_position=hedge, leg=leg, action=HedgeAuditLog.ACTION_VALIDATION_BLOCKED,
                                      user=user, notes=f"Buy-back failed: {result.get('error')}")
        raise HedgeValidationError('CLOSE_LEG_FAILED', f"Buy-back failed: {result.get('error')}")

    leg.status = HedgeLeg.STATUS_FILLED
    leg.filled_at = timezone.now()
    leg.save(update_fields=['status', 'filled_at'])
    HedgeAuditLog.objects.create(hedge_position=hedge, leg=leg, action=HedgeAuditLog.ACTION_MANUAL_CLOSE, user=user)

    if hedge.uncovered_lots >= hedge.futures_lots_covered:
        hedge.status = HEDGE_STATUS_CLOSED
        hedge.closed_at = timezone.now()
        hedge.save(update_fields=['status', 'closed_at'])

    return {'success': True, 'hedge_position_status': hedge.status}
