"""
Kotak Neo API Client - Authentication & Session Management

This module provides authentication and session management for Kotak Neo broker API.
"""

import logging
import jwt
from neo_api_client import NeoAPI

from apps.brokers.utils.auth_manager import (
    get_credentials,
    validate_jwt_token as _is_token_valid,
    save_session_token,
    extract_sid_from_jwt
)

logger = logging.getLogger(__name__)


def _get_authenticated_client():
    """
    Get authenticated Kotak Neo API client using tools.neo.NeoAPI wrapper.

    Uses the NeoAPI wrapper from tools.neo which handles authentication properly.

    Returns:
        NeoAPI: Authenticated Neo API client (the .neo attribute from tools.neo.NeoAPI)

    Raises:
        ValueError: If credentials not found or authentication fails
    """
    try:
        from tools.neo import NeoAPI as NeoAPIWrapper

        logger.info("Using NeoAPI wrapper from tools.neo for authentication")

        # Create NeoAPI wrapper instance (loads creds from database automatically)
        neo_wrapper = NeoAPIWrapper()

        # Perform login (handles 2FA automatically)
        login_result = neo_wrapper.login()
        logger.info(f"Neo login result: {login_result}, session_active: {neo_wrapper.session_active}")

        if login_result and neo_wrapper.session_active:
            logger.info("Neo API authentication successful via tools.neo wrapper")
            # Return the underlying neo_api_client instance
            logger.info(f"Returning Neo client: {neo_wrapper.neo}")
            return neo_wrapper.neo
        else:
            logger.error(f"Neo API login failed: result={login_result}, session_active={neo_wrapper.session_active}")
            raise ValueError("Neo API login failed via tools.neo wrapper")

    except Exception as e:
        logger.error(f"Failed to get authenticated Neo client: {e}")
        raise


def get_kotak_neo_client():
    """
    Get authenticated Kotak Neo client for placing orders.

    Returns:
        NeoAPI: Authenticated client instance

    Raises:
        ValueError: If authentication fails
    """
    try:
        return _get_authenticated_client()
    except Exception as e:
        logger.error(f"Failed to get Kotak Neo client: {e}")
        raise


def auto_login_kotak_neo():
    """
    Perform Kotak Neo login and 2FA, returning session token and sid.

    This function uses centralized auth_manager for session management,
    reusing saved tokens when available to avoid OTP requirement.

    Returns:
        dict: {'token': str, 'sid': str}

    Raises:
        ValueError: If credentials not found
    """
    # Use centralized credential loading
    creds = get_credentials('kotakneo')
    if not creds:
        raise ValueError("No Kotak Neo credentials found in CredentialStore")

    # Check if we have a valid saved session token
    saved_token = creds.sid  # JWT session token stored in sid field
    otp_code = creds.session_token  # OTP code

    # Use centralized token validation
    if saved_token and _is_token_valid(saved_token):
        logger.info("Reusing saved Kotak Neo session token for auto_login")

        # Use centralized SID extraction
        sid = extract_sid_from_jwt(saved_token)

        return {
            'token': saved_token,
            'sid': sid
        }

    # No valid token, perform fresh login with OTP
    logger.info("Performing fresh Kotak Neo login for auto_login")
    client = NeoAPI(
        consumer_key=creds.api_key,
        consumer_secret=creds.api_secret,
        environment='prod'
    )
    client.login(pan=creds.username, password=creds.password)
    session_2fa = client.session_2fa(OTP=otp_code)
    data = session_2fa.get('data', {})

    session_token = data.get('token')
    session_sid = data.get('sid')

    # Use centralized token saving with additional sid field
    if session_token:
        save_session_token('kotakneo', session_token, additional_data={'sid': session_token})
        logger.info(f"Saved new Kotak Neo session token from auto_login (valid until midnight, SID: {session_sid[:20]}...)")

    return {
        'token': session_token,
        'sid': session_sid
    }
