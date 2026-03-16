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
import threading
import time
from typing import Optional, Tuple

from breeze_connect import BreezeConnect

from apps.core.models import CredentialStore
from apps.brokers.exceptions import BreezeAuthenticationError
from apps.brokers.utils.auth_manager import (
    get_credentials,
    is_session_valid_breeze,
    can_attempt_auto_login,
    mark_auto_login_started,
    mark_auto_login_success,
    mark_auto_login_failed,
    reset_auto_login_status,
)

logger = logging.getLogger(__name__)

# Cross-process lock flag for auto-login (prevents multiple processes from
# opening browsers simultaneously)
AUTO_LOGIN_LOCK_FLAG = 'breeze_auto_login_lock'
AUTO_LOGIN_LOCK_TIMEOUT = 300  # seconds - max time an auto-login should take


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
    _auto_login_lock = threading.Lock()  # Thread-level lock for auto-login

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

        # Workaround for breeze-connect v1.0.62 bug:
        # SDK methods call self.error_exception(method_name, e) on failure,
        # but error_exception is never defined in __init__.
        # Setting it to None causes "'NoneType' object is not callable".
        # Fix: set it to a callable that re-raises the original exception.
        if not hasattr(breeze, 'error_exception') or breeze.error_exception is None:
            def _error_handler(method_name, exception):
                logger.error(f"Breeze API error in {method_name}: {exception}")
                raise exception
            breeze.error_exception = _error_handler

        return breeze

    def _is_auto_login_locked(self) -> bool:
        """Check if another process is already running auto-login (cross-process lock via NseFlag)."""
        try:
            from apps.core.models import NseFlag
            lock_value = NseFlag.get(AUTO_LOGIN_LOCK_FLAG, '')
            if lock_value:
                lock_time = float(lock_value)
                if time.time() - lock_time < AUTO_LOGIN_LOCK_TIMEOUT:
                    return True
                logger.warning("Found stale auto-login lock - ignoring")
        except Exception:
            pass
        return False

    def _set_auto_login_lock(self):
        """Set cross-process auto-login lock."""
        try:
            from apps.core.models import NseFlag
            NseFlag.set(AUTO_LOGIN_LOCK_FLAG, str(time.time()), "Auto-login in progress")
        except Exception:
            pass

    def _clear_auto_login_lock(self):
        """Clear cross-process auto-login lock."""
        try:
            from apps.core.models import NseFlag
            NseFlag.set(AUTO_LOGIN_LOCK_FLAG, '', "Auto-login completed")
        except Exception:
            pass

    def _wait_for_concurrent_auto_login(self, timeout: int = 90) -> bool:
        """
        Wait for another process/thread's auto-login to complete,
        then check if session is now valid.

        Returns:
            True if session became valid while waiting
        """
        logger.info("Another auto-login is in progress - waiting for it to complete...")
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(3)
            if not self._is_auto_login_locked():
                break

        is_valid, msg = self.is_session_valid()
        if is_valid:
            logger.info("Session is now valid after waiting for concurrent auto-login")
            return True
        logger.warning("Concurrent auto-login finished but session is still invalid")
        return False

    def _try_auto_login(self, task_name: str = "") -> Tuple[bool, str]:
        """
        Attempt automatic login using stored credentials.

        Uses both thread-level and cross-process locking to prevent
        concurrent auto-login attempts (which would open multiple browsers
        and send multiple OTPs).

        Note: Daily limit and market hours checks are done by the CALLER
        (get_client, refresh_session) before calling this method. This method
        focuses on locking and executing the login itself.

        Args:
            task_name: Description of what triggered this login (shown in Telegram OTP request)

        Returns:
            Tuple[bool, str]: (success, message)
        """
        # Thread-level lock: prevent concurrent auto-login within the same process
        acquired = self._auto_login_lock.acquire(blocking=False)
        if not acquired:
            logger.info("Auto-login already in progress in another thread - waiting...")
            # Block until the other thread's auto-login finishes
            with self._auto_login_lock:
                pass
            # Check if session is now valid after the other thread finished
            is_valid, msg = self.is_session_valid()
            if is_valid:
                self._client = None
                return True, "Session refreshed by concurrent auto-login"
            return False, "Concurrent auto-login completed but session still invalid"

        try:
            # Cross-process lock: prevent concurrent auto-login across processes
            if self._is_auto_login_locked():
                if self._wait_for_concurrent_auto_login():
                    self._client = None
                    return True, "Session refreshed by another process's auto-login"
                # Other process's login failed or timed out, we'll try ourselves

            self._set_auto_login_lock()

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
                    skip_validation=True,  # We know session is expired
                    task_name=task_name or "session auto-refresh",
                    caller_holds_lock=True  # We hold the lock, don't re-acquire
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

        finally:
            self._clear_auto_login_lock()
            self._auto_login_lock.release()

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
        auto_login_attempted = False

        if not is_valid:
            logger.warning(f"Breeze session invalid: {message}")

            if auto_refresh:
                # Check if auto-login credentials are available
                if creds.username and creds.password:
                    # Daily tracking: only one auto-login attempt per day
                    can_login, reason = can_attempt_auto_login('breeze')
                    if not can_login:
                        logger.warning(f"Breeze auto-login blocked: {reason}")
                        raise BreezeAuthenticationError(
                            f"Session expired. {reason}. Please login manually.",
                            requires_login=True,
                            login_url='/brokers/breeze/login/'
                        )

                    mark_auto_login_started('breeze')
                    auto_login_attempted = True
                    success, login_msg = self._try_auto_login(task_name="session validation refresh")
                    if success:
                        mark_auto_login_success('breeze')
                        # Reload credentials after auto-login
                        creds = self.get_credentials()
                    else:
                        mark_auto_login_failed('breeze')
                        self._notify_login_failed('breeze')
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

            # Check if it's a session/auth error
            if any(kw in error_str for kw in ['session', 'expired', 'unauthorized', 'invalid', 'resource not available', 'authenticate', 'credential']):
                logger.warning(f"Breeze session token rejected by API: {e}")

                # Token is invalid — clear it from DB to prevent future false-valid checks
                try:
                    creds.session_token = ''
                    creds.last_session_update = None
                    creds.save(update_fields=['session_token', 'last_session_update'])
                    logger.info("Cleared invalid Breeze session token from DB")
                except Exception as clear_err:
                    logger.error(f"Failed to clear invalid token from DB: {clear_err}")

                # Attempt auto-login recovery
                if auto_refresh and not auto_login_attempted:
                    if creds.username and creds.password:
                        # Token is proven invalid — reset daily limit to allow a fresh attempt
                        # regardless of whether previous auto-login succeeded or failed
                        prev_status = getattr(creds, 'auto_login_status', '')
                        if prev_status in ('success', 'failed'):
                            logger.info(f"Resetting auto-login status (was '{prev_status}'): token invalid, need fresh login")
                            reset_auto_login_status('breeze')

                        can_login, reason = can_attempt_auto_login('breeze')
                        if can_login:
                            mark_auto_login_started('breeze')
                            success, login_msg = self._try_auto_login(task_name="session error recovery")
                            if success:
                                mark_auto_login_success('breeze')
                                # Retry with new credentials
                                creds = self.get_credentials()
                                return self._create_client(creds)
                            else:
                                mark_auto_login_failed('breeze')
                                self._notify_login_failed('breeze')
                        else:
                            logger.warning(f"Auto-login blocked after session error: {reason}")
                    else:
                        logger.warning("Cannot attempt auto-login: Breeze username/password not configured")

                raise BreezeAuthenticationError(
                    f"Session expired: {e}",
                    requires_login=True,
                    requires_otp=True,
                    login_url='/brokers/breeze/login/'
                )

            raise BreezeAuthenticationError(f"Breeze authentication failed: {e}")

    def _notify_login_failed(self, service: str):
        """Send Telegram notification that auto-login failed."""
        try:
            from apps.alerts.services.notification_service import notify
            name = 'Breeze' if service == 'breeze' else service.title()
            notify('BROKER_HEALTH',
                title='Auto-Login Failed',
                instrument=name,
                task='breeze_session_get_client',
                context=[
                    "No more auto-login attempts today",
                    "Please login manually via the web UI",
                ],
                collapsible=False,
            )
        except Exception as e:
            logger.warning(f"Failed to send login-failed notification: {e}")

    def refresh_session(self) -> Tuple[bool, str]:
        """
        Force refresh the Breeze session.

        Returns:
            Tuple[bool, str]: (success, message)
        """
        return self._try_auto_login(task_name="manual session refresh")

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
