"""
Centralized authentication management for all broker integrations.

This module consolidates duplicate authentication patterns across different
broker APIs (Kotak Neo, ICICI Breeze, etc.) into reusable functions.

Functions:
    - get_credentials: Load broker credentials from database
    - validate_jwt_token: Check if JWT token is valid and not expired
    - save_session_token: Save session token to database
    - is_session_valid: Check if broker session is still valid

Benefits:
    - Eliminates duplicate credential loading code
    - Centralized token validation logic
    - Consistent session management across brokers
    - Easier to add new brokers

Example:
    >>> from apps.brokers.utils.auth_manager import get_credentials, validate_jwt_token
    >>> creds = get_credentials('kotakneo')
    >>> if creds and validate_jwt_token(creds.sid):
    ...     print("Session valid, reusing token")
"""

import logging
import jwt
from datetime import datetime, timedelta
from typing import Optional
from django.utils import timezone
from apps.core.models import CredentialStore

logger = logging.getLogger(__name__)


def get_credentials(service: str) -> Optional[CredentialStore]:
    """
    Load broker credentials from database.

    This replaces duplicate credential loading code found in:
    - kotak_neo.py (_get_authenticated_client)
    - breeze.py (get_breeze_client)

    Args:
        service: Service name ('kotakneo', 'breeze', etc.)

    Returns:
        CredentialStore object or None if not found

    Raises:
        ValueError: If service name is invalid

    Example:
        >>> creds = get_credentials('kotakneo')
        >>> if creds:
        ...     print(f"API Key: {creds.api_key}")
    """
    if not service:
        raise ValueError("Service name cannot be empty")

    try:
        creds = CredentialStore.objects.filter(service=service).first()

        if not creds:
            logger.warning(f"No credentials found for service: {service}")
            return None

        logger.debug(f"Loaded credentials for service: {service}")
        return creds

    except Exception as e:
        logger.error(f"Error loading credentials for {service}: {e}")
        return None


def validate_jwt_token(token: str, min_validity_seconds: int = 300) -> bool:
    """
    Check if a JWT token is still valid (not expired).

    Replaces duplicate token validation in:
    - kotak_neo.py (_is_token_valid)

    Args:
        token: JWT token string to validate
        min_validity_seconds: Minimum remaining validity in seconds (default: 300 = 5 minutes)

    Returns:
        bool: True if token is valid and has sufficient remaining time

    Example:
        >>> token = "eyJhbGc..."
        >>> if validate_jwt_token(token):
        ...     print("Token valid, reusing session")
        >>> else:
        ...     print("Token expired, need fresh login")

    Notes:
        - Does not verify signature (only checks expiration)
        - Returns False if token is None, empty, or malformed
        - Checks for minimum validity buffer (default 5 minutes)
    """
    if not token:
        return False

    try:
        # Decode without verification to check expiration only
        # (we trust our own saved tokens)
        payload = jwt.decode(token, options={'verify_signature': False})

        # Get expiration timestamp from token
        exp_timestamp = payload.get('exp')

        if not exp_timestamp:
            logger.warning("JWT token has no expiration field")
            return False

        # Convert to datetime
        exp_datetime = datetime.fromtimestamp(exp_timestamp)
        now = datetime.now()

        # Calculate remaining validity
        time_until_expiry = exp_datetime - now

        # Check if token has enough remaining validity
        if time_until_expiry.total_seconds() > min_validity_seconds:
            logger.debug(f"JWT token valid for {time_until_expiry.total_seconds():.0f} more seconds")
            return True
        else:
            logger.info(f"JWT token expires in {time_until_expiry.total_seconds():.0f} seconds (below {min_validity_seconds}s threshold)")
            return False

    except jwt.ExpiredSignatureError:
        logger.info("JWT token has expired")
        return False
    except jwt.DecodeError as e:
        logger.warning(f"JWT token decode error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error validating JWT token: {e}")
        return False


def save_session_token(service: str, session_token: str, additional_data: Optional[dict] = None) -> bool:
    """
    Save session token to database for a broker service.

    Replaces duplicate save patterns in:
    - kotak_neo.py (auto_login_kotak_neo)
    - breeze.py (save_breeze_token)

    Args:
        service: Service name ('kotakneo', 'breeze', etc.)
        session_token: Session token to save
        additional_data: Optional dict with additional fields to update (e.g., {'sid': '...'})

    Returns:
        bool: True if save successful, False otherwise

    Example:
        >>> success = save_session_token('kotakneo', 'new_token_here')
        >>> if success:
        ...     print("Token saved successfully")

    Notes:
        - Updates last_session_update timestamp automatically
        - Can save additional broker-specific data via additional_data parameter
    """
    try:
        creds = get_credentials(service)

        if not creds:
            logger.error(f"Cannot save token - no credentials found for {service}")
            return False

        # Update session token
        creds.session_token = session_token
        creds.last_session_update = timezone.now()

        # Update additional fields if provided
        if additional_data:
            for key, value in additional_data.items():
                if hasattr(creds, key):
                    setattr(creds, key, value)
                else:
                    logger.warning(f"CredentialStore has no field '{key}', skipping")

        # Save to database
        fields_to_update = ['session_token', 'last_session_update']
        if additional_data:
            fields_to_update.extend(additional_data.keys())

        creds.save(update_fields=fields_to_update)

        logger.info(f"Saved session token for {service} (updated at {creds.last_session_update})")
        return True

    except Exception as e:
        logger.error(f"Error saving session token for {service}: {e}")
        return False


def is_session_valid_breeze(creds: CredentialStore) -> bool:
    """
    Check if Breeze session token is still valid.

    Breeze tokens expire daily and must be refreshed from the portal.
    Replaces logic from breeze.py (get_or_prompt_breeze_token).

    Args:
        creds: CredentialStore object for Breeze

    Returns:
        bool: True if session token exists and was updated today

    Example:
        >>> creds = get_credentials('breeze')
        >>> if is_session_valid_breeze(creds):
        ...     print("Breeze session valid")
        >>> else:
        ...     print("Need to refresh Breeze token from portal")

    Notes:
        - Breeze tokens are valid for the current day only
        - Must be refreshed daily from ICICI portal
        - Does not validate with API (only checks timestamp)
    """
    if not creds:
        return False

    # Check if token exists
    if not creds.session_token:
        logger.debug("Breeze session token is empty")
        return False

    # Check if last update was today
    if not creds.last_session_update:
        logger.debug("Breeze session token has no last_session_update timestamp")
        return False

    # Breeze tokens are valid for current day only
    today = timezone.now().date()
    last_update_date = creds.last_session_update.date()

    if last_update_date == today:
        logger.debug(f"Breeze session token is valid (last updated: {creds.last_session_update})")
        return True
    else:
        logger.info(f"Breeze session token expired (last updated: {last_update_date}, today: {today})")
        return False


def extract_sid_from_jwt(token: str) -> Optional[str]:
    """
    Extract session ID (sid) from JWT token.

    Useful for Kotak Neo which stores multiple session identifiers.

    Args:
        token: JWT token string

    Returns:
        str: Session ID from token or 'unknown' if not found

    Example:
        >>> sid = extract_sid_from_jwt(token)
        >>> print(f"Session ID: {sid}")

    Notes:
        - Returns 'unknown' rather than None for backward compatibility
        - Does not verify signature
        - Extracts 'jti' (JWT ID) field as session ID
    """
    if not token:
        return 'unknown'

    try:
        payload = jwt.decode(token, options={'verify_signature': False})
        sid = payload.get('jti', 'unknown')  # JWT ID field
        return sid
    except Exception as e:
        logger.warning(f"Could not extract SID from JWT: {e}")
        return 'unknown'


def should_refresh_session(service: str) -> tuple[bool, str]:
    """
    Determine if broker session should be refreshed.

    Centralizes session validation logic for all brokers.

    Args:
        service: Service name ('kotakneo', 'breeze', etc.)

    Returns:
        tuple: (should_refresh: bool, reason: str)

    Example:
        >>> should_refresh, reason = should_refresh_session('breeze')
        >>> if should_refresh:
        ...     print(f"Refresh needed: {reason}")
        ...     # Trigger refresh logic

    Notes:
        - For Breeze: checks if token is from today
        - For Neo: validates JWT expiration
        - Returns reason string for logging/debugging
    """
    creds = get_credentials(service)

    if not creds:
        return True, f"No credentials found for {service}"

    if not creds.session_token:
        return True, "No session token saved"

    # Service-specific validation
    if service == 'breeze':
        if is_session_valid_breeze(creds):
            return False, "Breeze token is valid for today"
        else:
            return True, "Breeze token expired (not from today)"

    elif service == 'kotakneo':
        # For Neo, check JWT expiration (stored in 'sid' field)
        saved_token = creds.sid if hasattr(creds, 'sid') else None

        if saved_token and validate_jwt_token(saved_token):
            return False, "Neo JWT token is valid"
        else:
            return True, "Neo JWT token expired or missing"

    else:
        # Unknown service - refresh to be safe
        logger.warning(f"Unknown service '{service}' - recommending refresh")
        return True, f"Unknown service: {service}"
