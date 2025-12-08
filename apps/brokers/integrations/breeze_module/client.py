"""
ICICI Breeze API Client - Authentication & Session Management

This module provides authentication and client management for ICICI Breeze broker API.
"""

import logging

from breeze_connect import BreezeConnect

from apps.brokers.exceptions import BreezeAuthenticationError
from apps.brokers.utils.auth_manager import (
    get_credentials,
    save_session_token,
    is_session_valid_breeze
)

logger = logging.getLogger(__name__)


def get_or_prompt_breeze_token():
    """
    Check if Breeze session token is valid.

    Uses centralized auth_manager for session validation.

    Returns:
        str: 'prompt' if token needs to be entered, 'ready' if valid

    Raises:
        Exception: If credentials not found
    """
    # Use centralized credential loading
    creds = get_credentials('breeze')
    if not creds:
        raise Exception("No Breeze credentials found in DB")

    # Use centralized session validation
    if is_session_valid_breeze(creds):
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


def get_breeze_client():
    """
    Get authenticated Breeze API client.

    Uses centralized auth_manager for credential management.

    Returns:
        BreezeConnect: Authenticated client instance

    Raises:
        BreezeAuthenticationError: If credentials not found or authentication fails
    """
    try:
        # Use centralized credential loading
        creds = get_credentials('breeze')
        if not creds:
            raise BreezeAuthenticationError("No Breeze credentials found in database")

        if not creds.session_token:
            raise BreezeAuthenticationError("Breeze session token not found. Please login to continue.")

        logger.info(f"Attempting Breeze authentication with token from {creds.last_session_update}")
        logger.info(f"Using API Key: {creds.api_key[:10]}... Session Token: {creds.session_token[:20]}...")

        breeze = BreezeConnect(api_key=creds.api_key)
        breeze.generate_session(
            api_secret=creds.api_secret,
            session_token=creds.session_token
        )

        logger.info("Breeze authentication successful")
        return breeze
    except BreezeAuthenticationError:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"Breeze client error: {str(e)}")

        # Provide specific guidance for common errors
        if 'resource not available' in error_msg or 'customer details' in error_msg:
            raise BreezeAuthenticationError(
                "Breeze session token validation failed - 'Resource not available' error.\n\n"
                "This usually means:\n"
                "1. The session token doesn't match your API key\n"
                "2. The session token has expired (tokens expire daily)\n"
                "3. You need to get a fresh token from the Breeze portal\n\n"
                "Steps to fix:\n"
                "1. Go to: https://api.icicidirect.com/apiuser/login?api_key=YOUR_API_KEY\n"
                "2. Login with your ICICI Direct credentials\n"
                "3. Copy the NEW session token\n"
                "4. Update it in the database\n"
                "5. Ensure the API key in the URL matches the one in your database\n\n"
                f"Original error: {str(e)}",
                original_error=e
            )
        elif any(keyword in error_msg for keyword in ['session', 'authentication', 'unauthorized', 'invalid token', 'expired', 'login']):
            raise BreezeAuthenticationError(f"Breeze authentication failed: {str(e)}", original_error=e)
        raise
