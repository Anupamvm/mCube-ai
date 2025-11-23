"""
Base Data Provider Classes

Provides abstract base classes for all data providers to ensure
consistent interface and extensibility.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import chromedriver_autoinstaller

# Auto-install ChromeDriver
chromedriver_autoinstaller.install()

logger = logging.getLogger(__name__)


class DataProviderException(Exception):
    """Base exception for data provider errors"""
    pass


class BaseDataProvider(ABC):
    """
    Abstract base class for all data providers

    Provides common functionality:
    - WebDriver management
    - Credential handling
    - Logging
    - Error handling

    Subclasses must implement:
    - get_credentials()
    - login()
    - fetch_data()
    """

    def __init__(self, headless: bool = True):
        """
        Initialize data provider

        Args:
            headless: Run browser in headless mode
        """
        self.headless = headless
        self.driver = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def init_driver(self, download_dir: Optional[str] = None) -> webdriver.Chrome:
        """
        Initialize Chrome WebDriver with enhanced stability

        Args:
            download_dir: Optional directory for file downloads

        Returns:
            Configured Chrome WebDriver instance
        """
        chrome_options = Options()

        # Download configuration
        if download_dir:
            import os
            abs_download_path = os.path.abspath(download_dir)
            os.makedirs(abs_download_path, exist_ok=True)

            prefs = {
                "download.default_directory": abs_download_path,
                "download.prompt_for_download": False,
                "plugins.always_open_pdf_externally": True,
                "safebrowsing.enabled": True,
                "download.directory_upgrade": True
            }
            chrome_options.add_experimental_option("prefs", prefs)

        # Headless mode
        if self.headless:
            chrome_options.add_argument("--headless=new")

        # Stability and compatibility options
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--window-size=1920,1080")

        # Anti-detection
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # User agent
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.implicitly_wait(10)
            self.driver = driver
            self.logger.info("WebDriver initialized successfully")
            return driver
        except Exception as e:
            self.logger.error(f"Failed to initialize Chrome driver: {e}")
            raise DataProviderException(f"WebDriver initialization failed: {e}")

    @abstractmethod
    def get_credentials(self) -> tuple:
        """
        Retrieve credentials from database or config

        Returns:
            tuple: (username, password)

        Raises:
            DataProviderException: If credentials not found
        """
        pass

    @abstractmethod
    def login(self) -> bool:
        """
        Login to the data provider

        Returns:
            bool: True if login successful

        Raises:
            DataProviderException: If login fails
        """
        pass

    @abstractmethod
    def fetch_data(self, data_type: str, **kwargs) -> Dict:
        """
        Fetch specific type of data

        Args:
            data_type: Type of data to fetch (e.g., 'contracts', 'market_snapshot')
            **kwargs: Additional parameters

        Returns:
            dict: Fetched data and metadata

        Raises:
            DataProviderException: If fetch fails
        """
        pass

    def cleanup(self):
        """Cleanup resources (close driver, etc.)"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("WebDriver closed successfully")
            except Exception as e:
                self.logger.warning(f"Error closing WebDriver: {e}")
            finally:
                self.driver = None

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.cleanup()

    def save_debug_screenshot(self, filename_prefix: str = "error"):
        """
        Save screenshot for debugging

        Args:
            filename_prefix: Prefix for screenshot filename
        """
        if not self.driver:
            return

        try:
            import os
            import time
            from django.conf import settings

            screenshot_dir = os.path.join(
                settings.BASE_DIR, 'apps', 'data', 'debug_screenshots'
            )
            os.makedirs(screenshot_dir, exist_ok=True)

            screenshot_path = os.path.join(
                screenshot_dir,
                f"{filename_prefix}_{int(time.time())}.png"
            )
            self.driver.save_screenshot(screenshot_path)
            self.logger.info(f"Screenshot saved to: {screenshot_path}")
            return screenshot_path
        except Exception as e:
            self.logger.debug(f"Could not save screenshot: {e}")
            return None


class BaseWebScraper(BaseDataProvider):
    """
    Base class for web scraping providers

    Extends BaseDataProvider with common web scraping utilities
    """

    def wait_for_element(
        self,
        by: By,
        value: str,
        timeout: int = 15,
        condition=EC.presence_of_element_located
    ):
        """
        Wait for element to be present/clickable

        Args:
            by: Selenium By locator type
            value: Locator value
            timeout: Maximum wait time in seconds
            condition: Expected condition

        Returns:
            WebElement if found

        Raises:
            DataProviderException: If element not found
        """
        try:
            wait = WebDriverWait(self.driver, timeout)
            element = wait.until(condition((by, value)))
            return element
        except Exception as e:
            self.logger.error(f"Element not found: {by}={value}")
            self.save_debug_screenshot(f"element_not_found_{by}_{value[:20]}")
            raise DataProviderException(f"Element not found: {by}={value}: {e}")

    def try_multiple_selectors(
        self,
        selectors: List[tuple],
        action: str = "find",
        timeout: int = 15
    ):
        """
        Try multiple selectors until one succeeds

        Args:
            selectors: List of (By, value) tuples
            action: 'find', 'click', or 'send_keys'
            timeout: Timeout for each attempt

        Returns:
            WebElement or None

        Raises:
            DataProviderException: If all selectors fail
        """
        for by, value in selectors:
            try:
                self.logger.debug(f"Trying selector: {by}={value}")

                if action == "find":
                    element = self.wait_for_element(by, value, timeout)
                    self.logger.info(f"Found element with: {by}={value}")
                    return element

                elif action == "click":
                    element = self.wait_for_element(
                        by, value, timeout,
                        EC.element_to_be_clickable
                    )
                    element.click()
                    self.logger.info(f"Clicked element with: {by}={value}")
                    return element

            except DataProviderException:
                self.logger.debug(f"Selector failed: {by}={value}")
                continue

        raise DataProviderException(
            f"All selectors failed for action: {action}. "
            f"Tried {len(selectors)} selectors."
        )
