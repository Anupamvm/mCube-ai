"""
Kotak Neo API Client - Authentication & Session Management

This module provides authentication and session management for Kotak Neo broker API.
Authentication follows the same pattern as verify_kotak_login in apps/core/views.py:
always create a fresh NeoAPI instance and call login(), which reads from DB first.
"""

import logging

logger = logging.getLogger(__name__)


def _get_authenticated_client():
    """
    Get authenticated Kotak Neo API client (the underlying neo_api_client instance).

    Always creates a fresh NeoAPI wrapper and calls login() — which tries to restore
    the session from DB first (fast, no network). Only performs TOTP+MPIN when the DB
    has no valid session. This mirrors verify_kotak_login (apps/core/views.py) and
    ensures all gunicorn workers share the same session state via the DB, rather than
    each worker's private _cached_instance (which can be stale without the other
    workers knowing).

    Returns:
        neo_api_client.NeoAPI: Authenticated client instance

    Raises:
        ValueError: If authentication fails
    """
    from tools.neo import NeoAPI as NeoAPIWrapper, _cache_lock
    import tools.neo as neo_module
    from apps.brokers.utils.auth_manager import reset_auto_login_status

    reset_auto_login_status('kotakneo')
    neo_wrapper = NeoAPIWrapper()
    success = neo_wrapper.login(manual=True)

    if success and neo_wrapper.session_active:
        with _cache_lock:
            neo_module._cached_instance = neo_wrapper
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
