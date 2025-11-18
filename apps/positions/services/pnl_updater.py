"""
P&L Updater Service

Updates P&L for all active positions by fetching fresh prices from broker APIs
"""

import logging
from decimal import Decimal
from django.utils import timezone

logger = logging.getLogger(__name__)


def update_all_position_pnl():
    """
    Update P&L for all active positions by fetching fresh prices

    Fetches current market prices from broker APIs and recalculates
    unrealized P&L for all active positions.

    Returns:
        dict: Summary of update operation
    """
    try:
        from apps.positions.models import Position

        updated_count = 0
        total_pnl = Decimal('0')

        # Get all active positions
        positions = Position.objects.filter(status='ACTIVE')

        for position in positions:
            try:
                # Fetch current price from broker API
                current_price = fetch_current_price(position)

                if current_price:
                    # Update position with new price
                    position.current_price = current_price
                    position.updated_at = timezone.now()

                    # Calculate unrealized P&L
                    unrealized_pnl = position.calculate_unrealized_pnl()
                    position.unrealized_pnl = unrealized_pnl

                    position.save()

                    total_pnl += unrealized_pnl or Decimal('0')
                    updated_count += 1

            except Exception as e:
                logger.error(f"Error updating P&L for position {position.id}: {e}")
                continue

        logger.info(f"Updated P&L for {updated_count} positions. Total P&L: ₹{total_pnl}")

        return {
            'success': True,
            'positions_updated': updated_count,
            'total_pnl': float(total_pnl)
        }

    except Exception as e:
        logger.error(f"Error in update_all_position_pnl: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def fetch_current_price(position):
    """
    Fetch current market price for a position from broker API

    Args:
        position: Position object

    Returns:
        Decimal: Current market price, or None if fetch fails
    """
    try:
        account = position.account

        if account.broker == 'KOTAK':
            # Fetch from Kotak Neo
            from apps.brokers.kotak_neo import get_quote
            quote = get_quote(position.instrument)
            return Decimal(str(quote.get('ltp', position.current_price)))

        elif account.broker == 'BREEZE':
            # Fetch from ICICI Breeze
            from apps.brokers.breeze import get_quote
            quote = get_quote(position.instrument)
            return Decimal(str(quote.get('ltp', position.current_price)))

        else:
            logger.warning(f"Unknown broker: {account.broker}")
            return position.current_price

    except Exception as e:
        logger.error(f"Error fetching price for {position.instrument}: {e}")
        return position.current_price  # Return existing price as fallback
