"""
Broker resolver — routes to the correct broker implementation based on account type.

Usage:
    from apps.brokers.utils.broker_resolver import get_broker_for_account

    broker = get_broker_for_account(account)
    order_id = broker.place_order(symbol='NIFTY...', action='B', quantity=50)
"""

import logging

logger = logging.getLogger(__name__)


def get_broker_for_account(account):
    """
    Return the appropriate BrokerInterface implementation for an account.

    - Paper trading accounts → PaperBroker (simulated, no real API calls)
    - Kotak accounts         → NeoAPI (real broker)
    - ICICI accounts         → BreezeClient (real broker)

    Args:
        account: BrokerAccount instance.

    Returns:
        BrokerInterface implementation.

    Raises:
        ValueError: If broker type is unknown.
    """
    if account.is_paper_trading:
        from apps.brokers.integrations.paper_broker import PaperBroker
        logger.debug(f"[PAPER] Routing to PaperBroker for account {account.account_name}")
        return PaperBroker(account)

    if account.broker == 'KOTAK':
        from tools.neo import get_neo_api
        return get_neo_api()

    if account.broker == 'ICICI':
        from apps.brokers.integrations.breeze import get_breeze_client
        return get_breeze_client()

    raise ValueError(f"Unknown broker type: {account.broker}")
