"""
Breeze Auto Login Service

Automates the ICICI Breeze login process using Selenium.
First validates existing token - only opens browser if token is invalid.

Flow:
1. Check if saved session token is valid (make API call)
2. If valid, return success without opening browser
3. If invalid/expired, open browser for OTP-based login:
   a. Fill username and password
   b. Check Terms & Conditions checkbox
   c. Click Login
   d. Request OTP via Telegram (if available)
   e. Wait for OTP from EITHER Telegram reply OR manual browser entry
   f. If Telegram OTP arrives, enter it into the browser automatically
   g. Capture redirect URL with apisession parameter
   h. Save session token to database

OTP Dual-Path:
- Sends Telegram message requesting OTP (if bot is configured)
- Simultaneously monitors browser for manual OTP entry
- Whichever path delivers OTP first wins
- Falls back to browser-only if Telegram is unavailable

Requirements:
- selenium>=4.15.2
- Chrome browser installed
- ChromeDriver (auto-managed by selenium-manager)
"""

import logging
import time
import re
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple

from apps.brokers.utils.auth_manager import get_credentials, save_session_token, is_session_valid_breeze

logger = logging.getLogger(__name__)

# NseFlag keys for OTP cross-process communication
OTP_FLAG_REQUEST = 'breeze_otp_request'
OTP_FLAG_VALUE = 'breeze_otp_value'
OTP_FLAG_TASK = 'breeze_otp_task'

# Login lock flag - same as breeze_session.py for consistency
# Prevents concurrent login attempts across processes
LOGIN_LOCK_FLAG = 'breeze_auto_login_lock'
LOGIN_LOCK_TIMEOUT = 300  # seconds - matches breeze_session.py

# OTP request states
OTP_STATE_PENDING = 'pending'
OTP_STATE_FULFILLED = 'fulfilled'

# Telegram OTP polling config
TELEGRAM_OTP_TIMEOUT = 120   # seconds to wait for Telegram OTP reply
TELEGRAM_OTP_POLL_INTERVAL = 2  # seconds between NseFlag checks


def _is_login_locked() -> bool:
    """
    Check if a login is currently in progress (locked by another process).

    Uses the same lock format as breeze_session.py for compatibility.

    Returns:
        True if login is locked, False otherwise
    """
    try:
        from apps.core.models import NseFlag

        lock_value = NseFlag.get(LOGIN_LOCK_FLAG, "")
        if not lock_value:
            return False

        # Lock format: just a timestamp (same as breeze_session.py)
        try:
            lock_time = float(lock_value)
            elapsed = time.time() - lock_time

            # Check if lock has expired
            if elapsed > LOGIN_LOCK_TIMEOUT:
                logger.info(f"Login lock expired (held for {elapsed:.0f}s), releasing")
                NseFlag.set(LOGIN_LOCK_FLAG, "", "Lock expired and released")
                return False

            return True
        except ValueError:
            return False

    except Exception as e:
        logger.warning(f"Error checking login lock: {e}")
        return False


def _acquire_login_lock() -> bool:
    """
    Attempt to acquire the login lock.

    Uses the same lock format as breeze_session.py for compatibility.

    Returns:
        True if lock acquired, False if already locked by another process.
    """
    try:
        from apps.core.models import NseFlag

        if _is_login_locked():
            logger.info("Login already in progress, cannot acquire lock")
            return False

        # Acquire the lock (same format as breeze_session.py)
        NseFlag.set(LOGIN_LOCK_FLAG, str(time.time()), "Auto-login in progress")
        logger.info("Login lock acquired")
        return True

    except Exception as e:
        logger.warning(f"Error acquiring login lock: {e}")
        return True  # Allow login to proceed if we can't check


def _release_login_lock():
    """Release the login lock."""
    try:
        from apps.core.models import NseFlag
        NseFlag.set(LOGIN_LOCK_FLAG, "", "Login completed")
        logger.info("Login lock released")
    except Exception as e:
        logger.warning(f"Error releasing login lock: {e}")


def _wait_for_login_completion(max_wait: int = LOGIN_LOCK_TIMEOUT) -> Tuple[bool, str]:
    """
    Wait for another login process to complete, then recheck session.

    Returns:
        Tuple of (session_valid: bool, message: str)
    """
    start_time = time.time()

    while time.time() - start_time < max_wait:
        if not _is_login_locked():
            # Lock released - check if session is now valid
            logger.info("Login lock released, rechecking session...")
            time.sleep(1)  # Brief pause for DB to sync

            # Recheck session validity
            creds = get_credentials('breeze')
            if creds and is_session_valid_breeze(creds):
                return True, "Session now valid (refreshed by another process)"
            else:
                return False, "Session still invalid after other login completed"

        logger.debug("Waiting for login to complete...")
        time.sleep(3)

    return False, f"Timeout waiting for login to complete (waited {max_wait}s)"


def validate_existing_token() -> Tuple[bool, str]:
    """
    Validate the existing Breeze session token by making an API call.

    IMPORTANT: This creates the Breeze client directly without auto-refresh
    to avoid triggering a recursive login attempt.

    Returns:
        Tuple of (is_valid: bool, message: str)
    """
    try:
        creds = get_credentials('breeze')

        if not creds:
            return False, "No Breeze credentials found"

        if not creds.session_token:
            return False, "No session token saved"

        # Check if token was updated today (basic check)
        if not is_session_valid_breeze(creds):
            return False, "Session token expired (not from today)"

        # Try to actually use the token with the API
        logger.info("Validating existing session token with API...")

        # Create Breeze client directly WITHOUT auto-refresh to avoid recursion
        from breeze_connect import BreezeConnect
        breeze = BreezeConnect(api_key=creds.api_key)
        breeze.generate_session(
            api_secret=creds.api_secret,
            session_token=creds.session_token
        )

        # Workaround for breeze-connect v1.0.62 bug
        if not hasattr(breeze, 'error_exception'):
            breeze.error_exception = None

        # Make a simple API call to validate the token works
        # get_funds() is a lightweight call that validates authentication
        result = breeze.get_funds()

        if result and result.get('Success'):
            logger.info("Existing session token is valid")
            return True, "Session token is valid"
        elif result and result.get('Error'):
            error_msg = result.get('Error', 'Unknown error')
            logger.warning(f"Token validation failed: {error_msg}")
            return False, f"Token invalid: {error_msg}"
        else:
            # If we got here without error, token is likely valid
            logger.info("Session token validation successful")
            return True, "Session token is valid"

    except Exception as e:
        error_str = str(e).lower()
        logger.warning(f"Token validation failed with error: {e}")

        # Check for common authentication errors
        if any(kw in error_str for kw in ['session', 'token', 'expired', 'invalid', 'unauthorized', 'resource not available']):
            return False, f"Session token expired or invalid: {e}"

        # Other errors might be network issues, etc.
        return False, f"Validation error: {e}"


class BreezeAutoLogin:
    """
    Automates Breeze login process with token validation.

    First validates existing token - only opens browser if needed.
    Supports OTP entry via Telegram bot OR manual browser entry (both paths open).

    Usage:
        login = BreezeAutoLogin(task_name="scheduled refresh")
        success, message = login.run()
        if success:
            print(f"Login successful! {message}")
        else:
            print(f"Login failed: {message}")
    """

    # IMPORTANT: Must use /apiuser/login (not /apiuser/tradelogin)
    LOGIN_URL_TEMPLATE = "https://api.icicidirect.com/apiuser/login?api_key={api_key}"
    REDIRECT_HOST = "127.0.0.1"

    # Element selectors based on the ICICI Breeze API login form
    # The User ID field expects the registered mobile number
    SELECTORS = {
        'user_id': 'txtuid',          # Mobile number field
        'password': 'txtPass',         # Password field
        'tnc_checkbox': 'chkssTnc',    # Terms & Conditions checkbox
        'login_button': 'btnSubmit',   # Submit button
        'otp_panel': 'dvgetotp',       # OTP entry panel
    }

    def __init__(self, headless: bool = False, timeout: int = 300,
                 skip_validation: bool = False, task_name: str = ""):
        """
        Initialize the auto-login service.

        Args:
            headless: Run browser in headless mode (not recommended for OTP entry)
            timeout: Max seconds to wait for OTP entry and redirect (default: 5 minutes)
            skip_validation: Skip token validation and force browser login
            task_name: Description of what triggered this login (shown in Telegram)
        """
        self.headless = headless
        self.timeout = timeout
        self.skip_validation = skip_validation
        self.task_name = task_name or "Breeze login"
        self.driver = None
        self.credentials = None
        self._telegram_otp_sent = False

    def _load_credentials(self) -> bool:
        """Load Breeze credentials from database."""
        self.credentials = get_credentials('breeze')

        if not self.credentials:
            logger.error("No Breeze credentials found in database")
            return False

        if not self.credentials.api_key:
            logger.error("Breeze API key not configured")
            return False

        return True

    def _check_auto_login_credentials(self) -> bool:
        """Check if username/password are available for auto-login."""
        if not self.credentials.username or not self.credentials.password:
            logger.error("Breeze username/password not configured in CredentialStore")
            return False
        return True

    def _setup_driver(self) -> bool:
        """Setup Chrome WebDriver."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.common.exceptions import WebDriverException

            options = Options()

            if self.headless:
                options.add_argument('--headless=new')

            # Common options for stability
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1280,800')

            # Disable automation flags to avoid detection
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)

            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(10)

            logger.info("Chrome WebDriver initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Chrome WebDriver: {e}")
            return False

    def _get_login_url(self) -> str:
        """Build the Breeze login URL with API key."""
        from urllib.parse import quote, unquote

        api_key = self.credentials.api_key
        logger.info(f"Raw API key from database: {api_key}")

        # Check if API key is already URL-encoded (contains %XX patterns)
        if '%' in api_key:
            # Already encoded, use as-is
            api_key_encoded = api_key
            logger.info("API key appears to be already URL-encoded")
        else:
            # Need to URL-encode (special chars like &, @, ^ need encoding)
            api_key_encoded = quote(api_key, safe='')
            logger.info(f"URL-encoded API key: {api_key_encoded}")

        url = self.LOGIN_URL_TEMPLATE.format(api_key=api_key_encoded)
        logger.info(f"Final login URL: {url}")
        return url

    def _fill_login_form(self) -> bool:
        """Fill mobile number, password and check T&C."""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            wait = WebDriverWait(self.driver, 20)

            # Wait for and fill User ID (mobile number)
            user_id_field = wait.until(
                EC.presence_of_element_located((By.ID, self.SELECTORS['user_id']))
            )
            user_id_field.clear()
            user_id_field.send_keys(self.credentials.username)
            logger.info(f"Filled Mobile Number: {self.credentials.username}")

            # Fill Password
            password_field = self.driver.find_element(By.ID, self.SELECTORS['password'])
            password_field.clear()
            password_field.send_keys(self.credentials.password)
            logger.info("Filled Password")

            # Check Terms & Conditions checkbox
            tnc_checkbox = self.driver.find_element(By.ID, self.SELECTORS['tnc_checkbox'])
            if not tnc_checkbox.is_selected():
                tnc_checkbox.click()
                logger.info("Checked T&C checkbox")

            return True

        except Exception as e:
            logger.error(f"Failed to fill login form: {e}")
            return False

    def _click_login(self) -> bool:
        """Click the login button."""
        try:
            from selenium.webdriver.common.by import By

            login_button = self.driver.find_element(By.ID, self.SELECTORS['login_button'])
            login_button.click()
            logger.info("Clicked Login button")

            # Wait a moment for OTP panel to appear or redirect
            time.sleep(2)
            return True

        except Exception as e:
            logger.error(f"Failed to click login button: {e}")
            return False

    # =========================================================================
    # OTP PANEL DETECTION & ENTRY
    # =========================================================================

    def _is_otp_panel_visible(self) -> bool:
        """Check if the OTP entry panel is visible on the page."""
        try:
            from selenium.webdriver.common.by import By

            panel = self.driver.find_element(By.ID, self.SELECTORS['otp_panel'])
            return panel.is_displayed()
        except Exception:
            return False

    def _detect_otp_input_field(self):
        """
        Find the OTP input field inside the dvgetotp panel.
        Searches for visible text/tel/number input elements.

        Returns:
            WebElement or None
        """
        try:
            from selenium.webdriver.common.by import By

            panel = self.driver.find_element(By.ID, self.SELECTORS['otp_panel'])

            # Try common input types used for OTP
            for input_type in ['text', 'tel', 'number', 'password']:
                inputs = panel.find_elements(By.CSS_SELECTOR, f'input[type="{input_type}"]')
                for inp in inputs:
                    if inp.is_displayed():
                        logger.info(f"Found OTP input field: type={input_type}, id={inp.get_attribute('id')}")
                        return inp

            # Fallback: any visible input in the panel
            all_inputs = panel.find_elements(By.TAG_NAME, 'input')
            for inp in all_inputs:
                if inp.is_displayed() and inp.get_attribute('type') not in ('hidden', 'checkbox', 'radio', 'submit', 'button'):
                    logger.info(f"Found OTP input field (fallback): type={inp.get_attribute('type')}, id={inp.get_attribute('id')}")
                    return inp

            logger.warning("No OTP input field found in OTP panel")
            return None

        except Exception as e:
            logger.warning(f"Error detecting OTP input field: {e}")
            return None

    def _enter_otp_and_submit(self, otp: str) -> bool:
        """
        Enter OTP into the detected field and submit.

        Args:
            otp: The OTP digits to enter

        Returns:
            True if OTP was entered successfully
        """
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys

            otp_field = self._detect_otp_input_field()
            if not otp_field:
                logger.error("Cannot enter OTP - input field not found")
                return False

            # Clear and enter OTP
            otp_field.clear()
            otp_field.send_keys(otp)
            logger.info(f"Entered OTP ({len(otp)} digits) into browser")

            # Try to find and click the submit/verify button
            panel = self.driver.find_element(By.ID, self.SELECTORS['otp_panel'])
            submitted = False

            # Look for submit-type buttons within the OTP panel
            for selector in [
                'input[type="submit"]',
                'input[type="button"]',
                'button[type="submit"]',
                'button',
                'a.btn',
            ]:
                buttons = panel.find_elements(By.CSS_SELECTOR, selector)
                for btn in buttons:
                    if btn.is_displayed():
                        btn_text = (btn.text or btn.get_attribute('value') or '').lower()
                        # Click buttons that look like submit/verify/continue
                        if any(kw in btn_text for kw in ['submit', 'verify', 'continue', 'confirm', 'proceed', 'get']):
                            btn.click()
                            submitted = True
                            logger.info(f"Clicked OTP submit button: '{btn_text}'")
                            break
                if submitted:
                    break

            # Fallback: press Enter if no button found
            if not submitted:
                otp_field.send_keys(Keys.RETURN)
                logger.info("Pressed Enter to submit OTP (no button found)")

            time.sleep(2)
            return True

        except Exception as e:
            logger.error(f"Error entering OTP: {e}")
            return False

    # =========================================================================
    # TELEGRAM OTP COMMUNICATION (via NseFlag)
    # =========================================================================

    def _cleanup_otp_flags(self):
        """Clear all OTP-related NseFlag keys."""
        try:
            from apps.core.models import NseFlag

            for flag_name in [OTP_FLAG_REQUEST, OTP_FLAG_VALUE, OTP_FLAG_TASK]:
                NseFlag.set(flag_name, "", "Cleared after OTP flow")
            logger.debug("OTP flags cleaned up")
        except Exception as e:
            logger.debug(f"Error cleaning up OTP flags: {e}")

    def _ensure_telegram_bot_running(self) -> bool:
        """
        Check if the Telegram bot is running. If not, start it as a background process.

        The bot must be polling to receive OTP replies from the user.
        The TelegramClient can send messages via HTTP API without the bot polling,
        but receiving replies requires the bot to be actively polling.

        Returns:
            True if bot is running (or was successfully started)
        """
        try:
            from apps.alerts.services.telegram_bot import is_bot_running

            if is_bot_running():
                logger.info("Telegram bot is already running")
                return True

            logger.warning("Telegram bot is NOT running - attempting to start it")
            return self._start_telegram_bot_subprocess()

        except Exception as e:
            logger.warning(f"Error checking/starting Telegram bot: {e}")
            return False

    def _start_telegram_bot_subprocess(self) -> bool:
        """
        Start the Telegram bot as a background subprocess.

        Uses the same pattern as Celery worker subprocess spawning in the codebase.

        Returns:
            True if bot was started successfully
        """
        import subprocess
        import sys
        import os

        try:
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            python_path = sys.executable
            log_dir = os.path.join(project_dir, 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'telegram_bot.log')

            with open(log_file, 'a') as log:
                from datetime import datetime
                log.write(f"\n{'='*60}\n")
                log.write(f"Telegram bot auto-started at {datetime.now().isoformat()}\n")
                log.write(f"Triggered by: {self.task_name}\n")
                log.write(f"{'='*60}\n")

                proc = subprocess.Popen(
                    [python_path, 'manage.py', 'run_telegram_bot', '--force'],
                    cwd=project_dir,
                    stdout=log,
                    stderr=log,
                    start_new_session=True
                )

            logger.info(f"Telegram bot subprocess started (PID: {proc.pid})")

            # Wait for bot to initialize before proceeding
            time.sleep(5)

            # Verify it started
            from apps.alerts.services.telegram_bot import is_bot_running
            if is_bot_running():
                logger.info("Telegram bot confirmed running after auto-start")
                return True
            else:
                logger.warning("Telegram bot process started but lock not acquired - may still be initializing")
                # Give it a bit more time
                time.sleep(3)
                return is_bot_running()

        except Exception as e:
            logger.error(f"Failed to start Telegram bot subprocess: {e}")
            return False

    def _request_otp_via_telegram(self) -> bool:
        """
        Send a Telegram message requesting the OTP and set NseFlag for cross-process comm.

        Ensures the Telegram bot is running first (starts it if needed),
        then sends the OTP request message.

        Returns:
            True if Telegram message was sent successfully
        """
        try:
            from apps.core.models import NseFlag
            from apps.alerts.services.telegram_client import get_telegram_client

            client = get_telegram_client()
            if not client.is_enabled():
                logger.info("Telegram not configured - OTP via browser only")
                return False

            # Ensure bot is running to receive OTP replies
            bot_running = self._ensure_telegram_bot_running()
            if not bot_running:
                logger.warning("Telegram bot not running and could not be started - OTP via browser only")
                return False

            # Set NseFlag to signal that we need an OTP
            NseFlag.set(OTP_FLAG_REQUEST, OTP_STATE_PENDING, "Breeze OTP request pending")
            NseFlag.set(OTP_FLAG_VALUE, "", "Awaiting OTP value")
            NseFlag.set(OTP_FLAG_TASK, self.task_name, "Task requesting OTP")

            # Send Telegram message
            message = (
                "<b>Breeze OTP Required</b>\n\n"
                f"mCube needs Breeze OTP for: <b>{self.task_name}</b>\n\n"
                "Reply with the OTP digits (4-6 digits).\n"
                "Or enter it directly in the browser window."
            )
            success, resp = client.send_message(message)

            if success:
                logger.info("Telegram OTP request sent successfully")
                self._telegram_otp_sent = True
                return True
            else:
                logger.warning(f"Failed to send Telegram OTP request: {resp}")
                # Clean up flags since Telegram failed
                self._cleanup_otp_flags()
                return False

        except Exception as e:
            logger.warning(f"Error requesting OTP via Telegram: {e}")
            self._cleanup_otp_flags()
            return False

    def _check_telegram_otp(self) -> Optional[str]:
        """
        Check if the Telegram bot has received and stored an OTP via NseFlag.

        Returns:
            The OTP string if available, None otherwise
        """
        try:
            from apps.core.models import NseFlag

            status = NseFlag.get(OTP_FLAG_REQUEST, "")
            if status == OTP_STATE_FULFILLED:
                otp = NseFlag.get(OTP_FLAG_VALUE, "")
                if otp and re.match(r'^\d{4,6}$', otp):
                    logger.info(f"Received OTP via Telegram: {'*' * len(otp)}")
                    return otp
                else:
                    logger.warning(f"OTP flag fulfilled but value invalid: '{otp}'")
            return None
        except Exception:
            return None

    def _send_telegram_timeout_message(self):
        """Notify the user on Telegram that OTP polling timed out."""
        try:
            from apps.alerts.services.telegram_client import get_telegram_client

            client = get_telegram_client()
            if client.is_enabled():
                client.send_message(
                    "Telegram OTP window expired. You can still enter the OTP in the browser.",
                    disable_notification=True
                )
        except Exception:
            pass

    def _send_telegram_success_message(self):
        """Notify the user on Telegram that OTP was received and entered."""
        try:
            from apps.alerts.services.telegram_client import get_telegram_client

            client = get_telegram_client()
            if client.is_enabled():
                client.send_message(
                    "OTP received and entered into Breeze login. Waiting for session...",
                    disable_notification=True
                )
        except Exception:
            pass

    # =========================================================================
    # REDIRECT DETECTION
    # =========================================================================

    def _check_redirect(self) -> Optional[str]:
        """
        Check if browser has been redirected to 127.0.0.1 with apisession.

        Returns:
            Session token string if redirect detected, None otherwise
        """
        try:
            current_url = self.driver.current_url
            parsed = urlparse(current_url)

            if parsed.hostname == self.REDIRECT_HOST or parsed.hostname == 'localhost':
                query_params = parse_qs(parsed.query)
                if 'apisession' in query_params:
                    session_token = query_params['apisession'][0]
                    logger.info(f"Captured session token: {session_token[:20]}...")
                    return session_token
            return None
        except Exception:
            return None

    # =========================================================================
    # MAIN WAIT LOGIC (DUAL-PATH)
    # =========================================================================

    def _wait_for_otp_and_redirect(self) -> Tuple[bool, str]:
        """
        Wait for OTP entry (via Telegram or browser) and redirect.

        Dual-path approach:
        1. If OTP panel is visible, request OTP via Telegram
        2. Poll for BOTH redirect (browser entry) and Telegram OTP simultaneously
        3. If Telegram OTP arrives first, enter it into browser, then wait for redirect
        4. If browser redirect happens first (manual entry), done
        5. Falls back gracefully if Telegram is unavailable

        Returns:
            Tuple of (success, session_token or error_message)
        """
        logger.info(f"Waiting for OTP and redirect (timeout: {self.timeout}s)...")
        logger.info("OTP can be entered via Telegram OR directly in the browser.")

        # Check if OTP panel is visible and request via Telegram
        telegram_active = False
        if self._is_otp_panel_visible():
            logger.info("OTP panel detected - requesting OTP via Telegram")
            telegram_active = self._request_otp_via_telegram()
            if not telegram_active:
                logger.info("Telegram unavailable - waiting for browser OTP entry only")
        else:
            logger.info("OTP panel not visible yet - will check during polling")

        start_time = time.time()
        telegram_otp_entered = False
        telegram_poll_expired = False

        while time.time() - start_time < self.timeout:
            elapsed = time.time() - start_time

            # === Path 1: Check for browser redirect (manual OTP or submitted Telegram OTP) ===
            session_token = self._check_redirect()
            if session_token:
                self._cleanup_otp_flags()
                return True, session_token

            # === Path 2: Check for Telegram OTP (only if active and not yet entered) ===
            if telegram_active and not telegram_otp_entered and not telegram_poll_expired:
                # Check if Telegram OTP polling window has expired
                if elapsed > TELEGRAM_OTP_TIMEOUT:
                    telegram_poll_expired = True
                    self._send_telegram_timeout_message()
                    self._cleanup_otp_flags()
                    logger.info(f"Telegram OTP window expired after {TELEGRAM_OTP_TIMEOUT}s - browser entry still open")
                else:
                    otp = self._check_telegram_otp()
                    if otp:
                        logger.info("Got OTP from Telegram - entering into browser")
                        if self._enter_otp_and_submit(otp):
                            telegram_otp_entered = True
                            self._send_telegram_success_message()
                            self._cleanup_otp_flags()
                            # Continue polling for redirect after OTP submission
                        else:
                            logger.warning("Failed to enter Telegram OTP into browser - browser entry still open")
                            self._cleanup_otp_flags()
                            telegram_active = False

            # === Late Telegram request: if OTP panel appeared after initial check ===
            if not telegram_active and not self._telegram_otp_sent and not telegram_otp_entered:
                if self._is_otp_panel_visible():
                    logger.info("OTP panel just appeared - requesting OTP via Telegram")
                    telegram_active = self._request_otp_via_telegram()

            time.sleep(TELEGRAM_OTP_POLL_INTERVAL)

        # Timeout
        self._cleanup_otp_flags()
        return False, f"Timeout waiting for redirect after {self.timeout} seconds"

    def _save_token(self, session_token: str) -> bool:
        """Save the session token to database."""
        try:
            success = save_session_token('breeze', session_token)
            if success:
                logger.info("Session token saved to database successfully")
            else:
                logger.error("Failed to save session token to database")
            return success
        except Exception as e:
            logger.error(f"Error saving session token: {e}")
            return False

    def _cleanup(self):
        """Close the browser and clean up OTP flags."""
        self._cleanup_otp_flags()
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Browser closed")
            except Exception as e:
                logger.debug(f"Error closing browser: {e}")

    def _run_browser_login(self) -> Tuple[bool, str]:
        """Execute the browser-based login flow."""
        try:
            # Check if auto-login credentials are available
            if not self._check_auto_login_credentials():
                return False, "Username/password not configured. Set them via: python manage.py setup_credentials --setup-breeze"

            # Setup browser
            if not self._setup_driver():
                return False, "Failed to initialize Chrome browser. Ensure Chrome is installed."

            # Navigate to login page
            login_url = self._get_login_url()
            logger.info(f"Navigating to Breeze login page: {login_url}")
            self.driver.get(login_url)

            # Wait for page to load and log current URL
            time.sleep(2)
            current_url = self.driver.current_url
            logger.info(f"Current URL after navigation: {current_url}")

            # Check if we were redirected to wrong page
            if 'tradelogin' in current_url:
                logger.warning(f"Redirected to tradelogin! Expected login page. Re-navigating...")
                # Try navigating again with the correct URL
                self.driver.get(login_url)
                time.sleep(2)
                logger.info(f"URL after re-navigation: {self.driver.current_url}")

            # Fill login form
            if not self._fill_login_form():
                return False, "Failed to fill login form"

            # Click login
            if not self._click_login():
                return False, "Failed to click login button"

            # Wait for OTP (Telegram + browser) and redirect
            success, result = self._wait_for_otp_and_redirect()

            if not success:
                return False, result

            # Save token
            session_token = result
            if not self._save_token(session_token):
                return False, "Captured token but failed to save to database"

            return True, "New session token obtained and saved"

        finally:
            self._cleanup()

    def run(self, caller_holds_lock: bool = False) -> Tuple[bool, str]:
        """
        Execute the auto-login process.

        First validates existing token. Only opens browser if token is invalid.
        Uses a lock to prevent concurrent login attempts across processes.

        Args:
            caller_holds_lock: If True, caller already holds the cross-process lock
                               (e.g., when called from BreezeSessionManager).
                               We skip lock acquisition to avoid deadlock.

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Step 1: Load credentials
        if not self._load_credentials():
            return False, "Failed to load Breeze credentials"

        # Step 2: Validate existing token (unless skip_validation is True)
        if not self.skip_validation:
            logger.info("Checking if existing session token is valid...")
            is_valid, validation_msg = validate_existing_token()

            if is_valid:
                logger.info("Existing token is valid - no browser login needed")
                return True, f"Existing token is valid. {validation_msg}"
            else:
                logger.info(f"Token validation failed: {validation_msg}")
                logger.info("Proceeding with browser-based login...")

        # Step 3: Handle locking (skip if caller already holds lock)
        lock_acquired_here = False

        if not caller_holds_lock:
            # Check if lock is held by another process
            if _is_login_locked():
                # Another login is in progress - wait for it to complete
                logger.info("Another login is in progress, waiting for it to complete...")
                success, message = _wait_for_login_completion()

                if success:
                    logger.info("Session refreshed by another process - no login needed")
                    return True, message
                else:
                    logger.warning(f"Other login failed: {message}, attempting our own...")

            # Try to acquire lock for our login
            if _acquire_login_lock():
                lock_acquired_here = True
                logger.info("Lock acquired for browser login")
            else:
                # Race condition - someone else just acquired it
                # Wait for them to complete
                success, message = _wait_for_login_completion()
                if success:
                    return True, message
                # If failed, check session one more time
                creds = get_credentials('breeze')
                if creds and is_session_valid_breeze(creds):
                    return True, "Session became valid during lock acquisition"
                return False, "Could not acquire login lock and session is still invalid"

            # One more check before opening browser
            creds = get_credentials('breeze')
            if creds and is_session_valid_breeze(creds):
                logger.info("Session became valid while waiting - no login needed")
                if lock_acquired_here:
                    _release_login_lock()
                return True, "Session was refreshed by another process"

        # Step 4: Run browser-based login
        try:
            return self._run_browser_login()
        finally:
            # Only release lock if we acquired it here
            if lock_acquired_here:
                _release_login_lock()


def auto_login_breeze(headless: bool = False, timeout: int = 300,
                      skip_validation: bool = False, task_name: str = "",
                      caller_holds_lock: bool = False) -> Tuple[bool, str]:
    """
    Convenience function to run Breeze auto-login.

    First validates existing token - only opens browser if needed.
    When OTP is required, requests it via Telegram AND keeps the browser
    open for manual entry - whichever delivers first wins.

    Args:
        headless: Run browser in headless mode (not recommended, OTP needs user input)
        timeout: Max seconds to wait for OTP entry (default: 5 minutes)
        skip_validation: Skip token validation and force browser login
        task_name: Description of what triggered this login (shown in Telegram)
        caller_holds_lock: If True, caller already holds the cross-process lock
                           (e.g., when called from BreezeSessionManager).
                           Prevents deadlock by skipping lock acquisition.

    Returns:
        Tuple of (success: bool, message: str)

    Example:
        >>> from apps.brokers.services.breeze_auto_login import auto_login_breeze
        >>> success, msg = auto_login_breeze(task_name="scheduled refresh")
        >>> print(msg)
        # If token valid: "Existing token is valid. Session token is valid"
        # If token expired: Opens browser, waits for OTP, then "New session token obtained and saved"
    """
    login = BreezeAutoLogin(
        headless=headless, timeout=timeout,
        skip_validation=skip_validation, task_name=task_name
    )
    return login.run(caller_holds_lock=caller_holds_lock)
