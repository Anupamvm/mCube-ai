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
   d. Wait for user to enter OTP manually
   e. Capture redirect URL with apisession parameter
   f. Save session token to database

Requirements:
- selenium>=4.15.2
- Chrome browser installed
- ChromeDriver (auto-managed by selenium-manager)
"""

import logging
import time
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple

from apps.brokers.utils.auth_manager import get_credentials, save_session_token, is_session_valid_breeze

logger = logging.getLogger(__name__)


def validate_existing_token() -> Tuple[bool, str]:
    """
    Validate the existing Breeze session token by making an API call.

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

        from apps.brokers.integrations.breeze_module.client import get_breeze_client
        breeze = get_breeze_client()

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

    Usage:
        login = BreezeAutoLogin()
        success, message = login.run()
        if success:
            print(f"Login successful! {message}")
        else:
            print(f"Login failed: {message}")
    """

    LOGIN_URL_TEMPLATE = "https://api.icicidirect.com/apiuser/login?api_key={api_key}"
    REDIRECT_HOST = "127.0.0.1"

    # Element selectors based on the ICICI login form
    SELECTORS = {
        'user_id': 'txtuid',
        'password': 'txtPass',
        'tnc_checkbox': 'chkssTnc',
        'login_button': 'btnSubmit',
        'otp_panel': 'dvgetotp',
    }

    def __init__(self, headless: bool = False, timeout: int = 300, skip_validation: bool = False):
        """
        Initialize the auto-login service.

        Args:
            headless: Run browser in headless mode (not recommended for OTP entry)
            timeout: Max seconds to wait for OTP entry and redirect (default: 5 minutes)
            skip_validation: Skip token validation and force browser login
        """
        self.headless = headless
        self.timeout = timeout
        self.skip_validation = skip_validation
        self.driver = None
        self.credentials = None

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
        from urllib.parse import quote
        api_key = quote(self.credentials.api_key, safe='')
        return self.LOGIN_URL_TEMPLATE.format(api_key=api_key)

    def _fill_login_form(self) -> bool:
        """Fill username, password and check T&C."""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            wait = WebDriverWait(self.driver, 20)

            # Wait for and fill User ID
            user_id_field = wait.until(
                EC.presence_of_element_located((By.ID, self.SELECTORS['user_id']))
            )
            user_id_field.clear()
            user_id_field.send_keys(self.credentials.username)
            logger.info("Filled User ID")

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

    def _wait_for_redirect(self) -> Tuple[bool, str]:
        """
        Wait for the redirect to 127.0.0.1 with apisession parameter.

        Returns:
            Tuple of (success, session_token or error_message)
        """
        logger.info(f"Waiting for OTP entry and redirect (timeout: {self.timeout}s)...")
        logger.info("Please enter the OTP in the browser window.")

        start_time = time.time()

        while time.time() - start_time < self.timeout:
            try:
                current_url = self.driver.current_url
                parsed = urlparse(current_url)

                # Check if we've been redirected to 127.0.0.1
                if parsed.hostname == self.REDIRECT_HOST or parsed.hostname == 'localhost':
                    query_params = parse_qs(parsed.query)

                    if 'apisession' in query_params:
                        session_token = query_params['apisession'][0]
                        logger.info(f"Captured session token: {session_token[:20]}...")
                        return True, session_token
                    else:
                        logger.warning(f"Redirected to {self.REDIRECT_HOST} but no apisession found")
                        # Still might be processing, continue waiting

                time.sleep(1)

            except Exception as e:
                logger.debug(f"Error checking URL: {e}")
                time.sleep(1)

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
        """Close the browser."""
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
            logger.info(f"Navigating to Breeze login page...")
            self.driver.get(login_url)

            # Fill login form
            if not self._fill_login_form():
                return False, "Failed to fill login form"

            # Click login
            if not self._click_login():
                return False, "Failed to click login button"

            # Wait for OTP and redirect
            success, result = self._wait_for_redirect()

            if not success:
                return False, result

            # Save token
            session_token = result
            if not self._save_token(session_token):
                return False, "Captured token but failed to save to database"

            return True, "New session token obtained and saved"

        finally:
            self._cleanup()

    def run(self) -> Tuple[bool, str]:
        """
        Execute the auto-login process.

        First validates existing token. Only opens browser if token is invalid.

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

        # Step 3: Run browser-based login
        return self._run_browser_login()


def auto_login_breeze(headless: bool = False, timeout: int = 300, skip_validation: bool = False) -> Tuple[bool, str]:
    """
    Convenience function to run Breeze auto-login.

    First validates existing token - only opens browser if needed.

    Args:
        headless: Run browser in headless mode (not recommended, OTP needs user input)
        timeout: Max seconds to wait for OTP entry (default: 5 minutes)
        skip_validation: Skip token validation and force browser login

    Returns:
        Tuple of (success: bool, message: str)

    Example:
        >>> from apps.brokers.services.breeze_auto_login import auto_login_breeze
        >>> success, msg = auto_login_breeze()
        >>> print(msg)
        # If token valid: "Existing token is valid. Session token is valid"
        # If token expired: Opens browser, waits for OTP, then "New session token obtained and saved"
    """
    login = BreezeAutoLogin(headless=headless, timeout=timeout, skip_validation=skip_validation)
    return login.run()
