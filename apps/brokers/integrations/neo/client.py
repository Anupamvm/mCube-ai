"""
Kotak Neo API Client - Authentication & Session Management

This module provides authentication and session management for Kotak Neo broker API.
All authentication is delegated to tools.neo.NeoAPI via a process-level cached instance.
"""

import logging

logger = logging.getLogger(__name__)


def _get_authenticated_client():
    """
    Get authenticated Kotak Neo API client (the underlying neo_api_client instance).

    Uses the process-level cached NeoAPI wrapper from tools.neo.get_neo_api().
    First call per process creates the client and logs in (session restore or full login).
    Subsequent calls return the same cached client — no repeated API calls.

    Returns:
        neo_api_client.NeoAPI: Authenticated client instance

    Raises:
        ValueError: If authentication fails
    """
    from tools.neo import get_neo_api

    neo_wrapper = get_neo_api()
    if neo_wrapper.session_active:
        return neo_wrapper.neo

    last_error = neo_wrapper.get_last_error() or "Unknown authentication error"
    logger.error(f"Neo API login failed: {last_error}")
    raise ValueError(f"Neo API login failed: {last_error}")


def get_kotak_neo_client():
    """
    Get authenticated Kotak Neo client for placing orders.

    Returns:
        neo_api_client.NeoAPI: Authenticated client instance

    Raises:
        ValueError: If authentication fails
    """
    return _get_authenticated_client()
