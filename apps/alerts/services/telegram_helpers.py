"""
Helper functions for Telegram bot with proper async/sync handling
"""

import logging
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


@sync_to_async
def get_position_by_id(position_id):
    """Get a single position by ID"""
    from apps.positions.models import Position
    return Position.objects.select_related('account').get(id=position_id)


@sync_to_async
def get_active_positions_list():
    """Get list of all active positions"""
    from apps.positions.models import Position
    return list(Position.objects.filter(status='ACTIVE').select_related('account'))


@sync_to_async
def get_risk_data():
    """Get risk limits and circuit breakers for all accounts"""
    from apps.risk.models import RiskLimit, CircuitBreaker
    from apps.accounts.models import BrokerAccount

    accounts = list(BrokerAccount.objects.filter(is_active=True))
    today = timezone.now().date()

    result = []
    for acc in accounts:
        limits = list(RiskLimit.objects.filter(
            account=acc,
            period_start=today
        ))
        result.append((acc, limits))

    active_breakers = list(CircuitBreaker.objects.filter(is_active=True))

    return result, active_breakers


@sync_to_async
def get_pnl_data(today=None):
    """Get P&L data for today"""
    from apps.positions.models import Position

    if today is None:
        today = timezone.now().date()

    today_positions = Position.objects.filter(
        status='CLOSED',
        exit_time__date=today
    )

    if not today_positions.exists():
        return None, 0, 0, 0

    total_pnl = today_positions.aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0.00')
    winners = today_positions.filter(realized_pnl__gt=0).count()
    losers = today_positions.filter(realized_pnl__lt=0).count()
    total_trades = today_positions.count()

    return total_pnl, winners, losers, total_trades


@sync_to_async
def get_week_pnl_data():
    """Get P&L data for this week"""
    from apps.positions.models import Position

    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())

    week_positions = Position.objects.filter(
        status='CLOSED',
        exit_time__date__gte=week_start,
        exit_time__date__lte=today
    )

    if not week_positions.exists():
        return None, 0, 0, 0, week_start

    total_pnl = week_positions.aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0.00')
    winners = week_positions.filter(realized_pnl__gt=0).count()
    losers = week_positions.filter(realized_pnl__lt=0).count()
    total_trades = week_positions.count()

    return total_pnl, winners, losers, total_trades, week_start


@sync_to_async
def close_position_sync(position, exit_price, exit_reason):
    """Close a position (sync wrapper)"""
    from apps.positions.services.position_manager import close_position
    return close_position(position=position, exit_price=exit_price, exit_reason=exit_reason)


@sync_to_async
def close_all_positions_sync():
    """Close all active positions (sync wrapper)"""
    from apps.positions.models import Position
    from apps.positions.services.position_manager import close_position

    active_positions = Position.objects.filter(status='ACTIVE')

    closed_count = 0
    failed_count = 0
    total_pnl = Decimal('0.00')

    for pos in active_positions:
        success, closed_pos, msg = close_position(
            position=pos,
            exit_price=pos.current_price,
            exit_reason="EMERGENCY_CLOSEALL_TELEGRAM_BOT"
        )

        if success:
            closed_count += 1
            total_pnl += closed_pos.realized_pnl
        else:
            failed_count += 1

    return closed_count, failed_count, total_pnl


@sync_to_async
def fetch_live_positions():
    """
    Fetch live positions from all broker accounts (Kotak and ICICI)
    and sync them to Position model for tracking

    Returns:
        tuple: (breeze_positions, kotak_positions, errors)
            - breeze_positions: list of BrokerPosition objects from ICICI Breeze
            - kotak_positions: list of BrokerPosition objects from Kotak Neo
            - errors: dict with any error messages per broker
    """
    from apps.brokers.integrations.breeze import fetch_and_save_breeze_data
    from apps.brokers.integrations.kotak_neo import fetch_and_save_kotakneo_data
    from apps.accounts.models import BrokerAccount
    from apps.positions.models import Position
    from django.utils import timezone
    from decimal import Decimal

    breeze_positions = []
    kotak_positions = []
    errors = {}

    # Check if accounts are active
    breeze_active = BrokerAccount.objects.filter(broker='ICICI', is_active=True).exists()
    kotak_active = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).exists()

    # Fetch ICICI Breeze positions
    if breeze_active:
        try:
            limit_record, pos_objs = fetch_and_save_breeze_data()
            breeze_positions = pos_objs

            # Sync to Position model
            _sync_broker_positions_to_app(pos_objs, 'ICICI')
        except Exception as e:
            errors['ICICI Breeze'] = str(e)

    # Fetch Kotak Neo positions
    if kotak_active:
        try:
            limit_record, pos_objs = fetch_and_save_kotakneo_data()
            kotak_positions = pos_objs

            # Sync to Position model
            _sync_broker_positions_to_app(pos_objs, 'KOTAK')
        except Exception as e:
            import traceback
            error_detail = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Kotak Neo fetch failed: {error_detail}\n{traceback.format_exc()}")
            errors['Kotak Neo'] = error_detail

    return breeze_positions, kotak_positions, errors


def _sync_broker_positions_to_app(broker_positions, broker_name):
    """
    Sync broker positions to app's Position model with 5-minute caching

    If a position was updated within the last 5 minutes, we update the same record
    instead of creating a new one.

    Args:
        broker_positions: List of BrokerPosition objects
        broker_name: 'ICICI' or 'KOTAK'
    """
    from apps.positions.models import Position
    from apps.accounts.models import BrokerAccount
    from django.utils import timezone
    from decimal import Decimal
    from datetime import timedelta

    # Get the broker account
    account = BrokerAccount.objects.filter(broker=broker_name, is_active=True).first()
    if not account:
        return

    # Track which positions exist in broker
    broker_symbols = set()
    now = timezone.now()
    five_mins_ago = now - timedelta(minutes=5)

    for bp in broker_positions:
        # Skip if net quantity is 0
        if bp.net_quantity == 0:
            continue

        broker_symbols.add(bp.symbol)

        # Check if we already have this position in our system
        # Look for positions updated within last 5 minutes first (caching)
        position = Position.objects.filter(
            account=account,
            instrument=bp.symbol,
            status='ACTIVE',
            updated_at__gte=five_mins_ago  # Within last 5 minutes
        ).first()

        if not position:
            # No recent position, check for any active position
            position = Position.objects.filter(
                account=account,
                instrument=bp.symbol,
                status='ACTIVE'
            ).first()

        if position:
            # Update existing position (respects 5-minute caching)
            position.current_price = Decimal(str(bp.ltp))
            position.unrealized_pnl = Decimal(str(bp.unrealized_pnl or 0))
            position.quantity = abs(bp.net_quantity)  # Update quantity if changed
            position.entry_price = Decimal(str(bp.average_price))  # Update avg price if changed
            position.save(update_fields=['current_price', 'unrealized_pnl', 'quantity', 'entry_price', 'updated_at'])
        else:
            # Create new position from broker data
            # Determine direction based on net quantity
            if bp.net_quantity > 0:
                direction = 'LONG'
            elif bp.net_quantity < 0:
                direction = 'SHORT'
            else:
                continue  # Skip flat positions

            # Create position
            Position.objects.create(
                account=account,
                strategy_type='BROKER_SYNC',  # Mark as synced from broker
                instrument=bp.symbol,
                direction=direction,
                quantity=abs(bp.net_quantity),
                lot_size=1,  # Default, adjust if needed
                entry_price=Decimal(str(bp.average_price)),
                current_price=Decimal(str(bp.ltp)),
                stop_loss=Decimal('0.00'),  # Unknown from broker
                target=Decimal('0.00'),  # Unknown from broker
                expiry_date=timezone.now().date() + timedelta(days=7),  # Default
                margin_used=Decimal('0.00'),  # Calculate if needed
                entry_value=Decimal(str(bp.average_price)) * abs(bp.net_quantity),
                status='ACTIVE',
                unrealized_pnl=Decimal(str(bp.unrealized_pnl or 0)),
                notes=f'Auto-synced from {broker_name} broker at {timezone.now()}'
            )

    # Close positions that no longer exist in broker
    active_positions = Position.objects.filter(
        account=account,
        status='ACTIVE',
        strategy_type='BROKER_SYNC'
    )

    for position in active_positions:
        if position.instrument not in broker_symbols:
            # Position was closed at broker, close it here
            position.close_position(
                exit_price=position.current_price,
                exit_reason='BROKER_SYNC_CLOSED'
            )
