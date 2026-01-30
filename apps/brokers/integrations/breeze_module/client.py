"""
ICICI Breeze API Client - Authentication & Session Management

This module provides authentication and client management for ICICI Breeze broker API.

NOTE: All authentication now goes through the centralized BreezeSessionManager.
      This module delegates to apps.brokers.services.breeze_session for consistency.
"""

import logging

from apps.brokers.utils.auth_manager import save_session_token

logger = logging.getLogger(__name__)


def get_or_prompt_breeze_token():
    """
    Check if Breeze session token is valid.

    Uses centralized BreezeSessionManager for session validation.

    Returns:
        str: 'prompt' if token needs to be entered, 'ready' if valid

    Raises:
        Exception: If credentials not found
    """
    from apps.brokers.services.breeze_session import check_breeze_session

    status = check_breeze_session()
    if status['valid']:
        return 'ready'
    return 'prompt'


def save_breeze_token(session_token):
    """
    Save Breeze session token to database.

    Uses centralized auth_manager for token saving.

    Args:
        session_token: The session token from ICICI portal

    Raises:
        Exception: If credentials not found
    """
    # Use centralized token saving
    success = save_session_token('breeze', session_token)
    if not success:
        raise Exception("Failed to save Breeze session token")


def get_breeze_client(auto_refresh: bool = True):
    """
    Get authenticated Breeze API client.

    IMPORTANT: This function delegates to the centralized BreezeSessionManager
    which handles session validation and auto-refresh.

    Args:
        auto_refresh: If True, attempt auto-login when session expired (default: True)

    Returns:
        BreezeConnect: Authenticated client instance

    Raises:
        BreezeAuthenticationError: If credentials not found or authentication fails
    """
    from apps.brokers.services.breeze_session import get_authenticated_breeze_client
    return get_authenticated_breeze_client(auto_refresh=auto_refresh)
