"""
Breeze Session Manager

Centralized session management for ICICI Breeze API with auto-login capability.

This is the SINGLE POINT OF ENTRY for all Breeze API access. It handles:
- Session validation
- Automatic session refresh when expired
- Consistent error handling

Usage:
    from apps.brokers.services.breeze_session import BreezeSessionManager

    # Get authenticated client (auto-refreshes if expired)
    manager = BreezeSessionManager()
    client = manager.get_client()  # Returns BreezeConnect or raises BreezeAuthenticationError

    # Or use the convenience function
    from apps.brokers.services.breeze_session import get_authenticated_breeze_client
    client = get_authenticated_breeze_client()
"""

import logging
from typing import Optional, Tuple
from datetime import datetime

from django.utils import timezone
from breeze_connect import BreezeConnect

from apps.core.models import CredentialStore
from apps.brokers.exceptions import BreezeAuthenticationError
from apps.brokers.utils.auth_manager import (
    get_credentials,
    save_session_token,
    is_session_valid_breeze
)

logger = logging.getLogger(__name__)


class BreezeSessionManager:
    """
    Centralized Breeze session management with auto-login.

    This class ensures:
    1. Session validation before API calls
    2. Automatic session refresh when expired
    3. Consistent error handling across the application

    Example:
        manager = BreezeSessionManager()

        # Get client with auto-refresh
        try:
            client = manager.get_client()
            positions = client.get_portfolio_positions()
        except BreezeAuthenticationError as e:
            if e.requires_otp:
                # Redirect to OTP page
                pass
    """

    _instance = None  # Singleton instance

    def __new__(cls):
        """Singleton pattern - only one manager instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize session manager."""
        if self._initialized:
            return
        self._initialized = True
        self._client = None
        self._last_validation = None

    def get_credentials(self) -> Optional[CredentialStore]:
        """Get Breeze credentials from database."""
        return get_credentials('breeze')

    def is_session_valid(self, force_check: bool = False) -> Tuple[bool, str]:
        """
        Check if current Breeze session is valid.

        Args:
            force_check: If True, validates with API call. Otherwise uses cached result.

        Returns:
            Tuple[bool, str]: (is_valid, message)
        """
        creds = self.get_credentials()

        if not creds:
            return False, "No Breeze credentials configured"

        if not creds.api_key:
            return False, "Breeze API key not configured"

        if not creds.session_token:
            return False, "No session token - login required"

        # Check if token was updated today (Breeze tokens expire daily)
        if not is_session_valid_breeze(creds):
            return False, "Session token expired (not from today)"

        # Optionally validate with API call
        if force_check:
            try:
                client = self._create_client(creds)
                # Try a simple API call to validate
                client.get_customer_details()
                return True, "Session valid (API verified)"
            except Exception as e:
                error_str = str(e).lower()
                if any(kw in error_str for kw in ['session', 'expired', 'unauthorized', 'invalid', 'login']):
                    return False, f"Session invalid: {e}"
                # Other errors don't necessarily mean session is invalid
                return True, f"Session likely valid (API error: {e})"

        return True, "Session token exists and is from today"

    def _create_client(self, creds: CredentialStore) -> BreezeConnect:
        """Create Breeze client with given credentials."""
        breeze = BreezeConnect(api_key=creds.api_key)
        breeze.generate_session(
            api_secret=creds.api_secret,
            session_token=creds.session_token
        )

        # Workaround for breeze-connect v1.0.62 bug
        if not hasattr(breeze, 'error_exception'):
            breeze.error_exception = None

        return breeze

    def _try_auto_login(self) -> Tuple[bool, str]:
        """
        Attempt automatic login using stored credentials.

        Returns:
            Tuple[bool, str]: (success, message)
        """
        creds = self.get_credentials()

        if not creds:
            return False, "No credentials configured"

        if not creds.username or not creds.password:
            return False, "Auto-login credentials (username/password) not configured"

        if not creds.api_key:
            return False, "API key not configured"

        try:
            from apps.brokers.services.breeze_auto_login import auto_login_breeze

            logger.info("Attempting Breeze auto-login...")
            success, message = auto_login_breeze(
                headless=False,  # Show browser for OTP entry
                timeout=300,
                skip_validation=True  # We know session is expired
            )

            if success:
                logger.info(f"Breeze auto-login successful: {message}")
                self._client = None  # Reset cached client
                return True, message
            else:
                logger.error(f"Breeze auto-login failed: {message}")
                return False, message

        except ImportError:
            return False, "Selenium not installed - cannot auto-login"
        except Exception as e:
            logger.error(f"Auto-login error: {e}", exc_info=True)
            return False, f"Auto-login error: {e}"

    def get_client(self, auto_refresh: bool = True) -> BreezeConnect:
        """
        Get authenticated Breeze client.

        This is the main entry point for getting a Breeze client.
        If session is expired and auto_refresh is True, attempts auto-login.

        Args:
            auto_refresh: If True, attempt auto-login when session expired

        Returns:
            BreezeConnect: Authenticated client

        Raises:
            BreezeAuthenticationError: If authentication fails
        """
        creds = self.get_credentials()

        if not creds:
            raise BreezeAuthenticationError(
                "No Breeze credentials found. Please configure in Admin.",
                requires_login=True,
                login_url='/brokers/breeze/login/'
            )

        if not creds.api_key:
            raise BreezeAuthenticationError(
                "Breeze API key not configured.",
                requires_login=True,
                login_url='/brokers/breeze/login/'
            )

        # Check session validity
        is_valid, message = self.is_session_valid()

        if not is_valid:
            logger.warning(f"Breeze session invalid: {message}")

            if auto_refresh:
                # Check if auto-login credentials are available
                if creds.username and creds.password:
                    success, login_msg = self._try_auto_login()
                    if success:
                        # Reload credentials after auto-login
                        creds = self.get_credentials()
                    else:
                        raise BreezeAuthenticationError(
                            f"Session expired. Auto-login failed: {login_msg}",
                            requires_login=True,
                            requires_otp=True,
                            login_url='/brokers/breeze/login/'
                        )
                else:
                    raise BreezeAuthenticationError(
                        "Session expired. Auto-login credentials not configured.",
                        requires_login=True,
                        login_url='/brokers/breeze/login/'
                    )

        # Create client
        try:
            client = self._create_client(creds)
            logger.info("✅ Breeze client authenticated successfully")
            return client

        except Exception as e:
            error_str = str(e).lower()

            # Check if it's a session error
            if any(kw in error_str for kw in ['session', 'expired', 'unauthorized', 'invalid', 'resource not available']):
                if auto_refresh and creds.username and creds.password:
                    # Try auto-login
                    success, login_msg = self._try_auto_login()
                    if success:
                        # Retry with new credentials
                        creds = self.get_credentials()
                        return self._create_client(creds)

                raise BreezeAuthenticationError(
                    f"Session expired: {e}",
                    requires_login=True,
                    requires_otp=True,
                    login_url='/brokers/breeze/login/'
                )

            raise BreezeAuthenticationError(f"Breeze authentication failed: {e}")

    def refresh_session(self) -> Tuple[bool, str]:
        """
        Force refresh the Breeze session.

        Returns:
            Tuple[bool, str]: (success, message)
        """
        return self._try_auto_login()

    def clear_cache(self):
        """Clear cached client."""
        self._client = None
        self._last_validation = None


# Singleton instance
_session_manager = None


def get_session_manager() -> BreezeSessionManager:
    """Get the singleton BreezeSessionManager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = BreezeSessionManager()
    return _session_manager


def get_authenticated_breeze_client(auto_refresh: bool = True) -> BreezeConnect:
    """
    Convenience function to get authenticated Breeze client.

    This is the recommended way to get a Breeze client throughout the application.
    It handles session validation and auto-refresh automatically.

    Args:
        auto_refresh: If True, attempt auto-login when session expired

    Returns:
        BreezeConnect: Authenticated client

    Raises:
        BreezeAuthenticationError: If authentication fails

    Example:
        from apps.brokers.services.breeze_session import get_authenticated_breeze_client

        try:
            client = get_authenticated_breeze_client()
            positions = client.get_portfolio_positions()
        except BreezeAuthenticationError as e:
            # Handle auth error - redirect to login
            pass
    """
    manager = get_session_manager()
    return manager.get_client(auto_refresh=auto_refresh)


def check_breeze_session() -> dict:
    """
    Check Breeze session status.

    Returns:
        dict: {
            'valid': bool,
            'message': str,
            'auto_login_available': bool,
            'login_url': str
        }
    """
    manager = get_session_manager()
    creds = manager.get_credentials()

    is_valid, message = manager.is_session_valid()

    return {
        'valid': is_valid,
        'message': message,
        'auto_login_available': bool(creds and creds.username and creds.password),
        'login_url': '/brokers/breeze/login/',
        'last_update': creds.last_session_update if creds else None
    }
