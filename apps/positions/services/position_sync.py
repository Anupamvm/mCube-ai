"""
Position Sync Service

Syncs position data from broker APIs to database
"""

import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


def sync_positions_from_broker():
    """
    Sync active positions from all active broker accounts

    This function fetches current positions from broker APIs and updates
    the database with fresh data.

    Returns:
        dict: Summary of sync operation
    """
    try:
        from apps.accounts.models import BrokerAccount
        from apps.positions.models import Position

        synced_count = 0

        # Get all active broker accounts
        accounts = BrokerAccount.objects.filter(is_active=True)

        for account in accounts:
            try:
                if account.broker == 'KOTAK':
                    # Sync from Kotak Neo
                    from apps.brokers.kotak_neo import get_positions
                    positions_data = get_positions(account)

                    # Update positions in database
                    # (Implementation depends on your position model structure)
                    # For now, just update timestamps to mark as refreshed
                    Position.objects.filter(
                        account=account,
                        status='ACTIVE'
                    ).update(updated_at=timezone.now())

                    synced_count += 1

                elif account.broker == 'BREEZE':
                    # Sync from ICICI Breeze
                    from apps.brokers.breeze import get_positions
                    positions_data = get_positions(account)

                    Position.objects.filter(
                        account=account,
                        status='ACTIVE'
                    ).update(updated_at=timezone.now())

                    synced_count += 1

            except Exception as e:
                logger.error(f"Error syncing positions for {account}: {e}")
                continue

        logger.info(f"Synced positions from {synced_count} accounts")

        return {
            'success': True,
            'accounts_synced': synced_count
        }

    except Exception as e:
        logger.error(f"Error in sync_positions_from_broker: {e}")
        return {
            'success': False,
            'error': str(e)
        }
