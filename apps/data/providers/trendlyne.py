"""
Trendlyne Data Provider

Consolidated and refactored Trendlyne data fetching module.

Features:
- F&O Contracts data
- Market Snapshot data
- Forecaster data (21 screeners)
- Analyst summaries
- Broker reports

Usage:
    from apps.data.providers.trendlyne import TrendlyneProvider

    with TrendlyneProvider() as provider:
        provider.fetch_all_data()
"""

import os
import time
import csv
import re
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from django.conf import settings

from apps.core.models import CredentialStore
from .base import BaseWebScraper, DataProviderException


class TrendlyneProvider(BaseWebScraper):
    """
    Trendlyne data provider

    Handles all Trendlyne data fetching with enhanced reliability
    """

    BASE_URL = "https://trendlyne.com"
    FEATURES_URL = f"{BASE_URL}/features/"

    # Forecaster screener URLs
    FORECASTER_URLS = {
        "High Bullishness": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/consensus_highest_bullish-above-0/",
        "High Bearishness": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/consensus_highest_bearish-above-0/",
        "Highest Forward 12Mth Upside %": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/consensus_highest_upside-above-0/",
        "Highest Forward Annual EPS Growth": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/eps_annual_growth-above-0/",
        "Lowest Forward Annual EPS Growth": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/eps_annual_growth-below-0/",
        "Highest Forward Annual Revenue Growth": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/revenue_annual_growth-above-0/",
        "Highest 3Mth Analyst Upgrades": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/consensus_analyst_upgrade-above-0/",
        "Highest Forward Annual Capex Growth": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/consensus_highest_capex-above-0/",
        "Highest Dividend Yield": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/consensus_highest_dps-above-0/",
        "Beat Annual Revenue Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/revenue-annual-surprise-above-0/",
        "Missed Annual Revenue Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/revenue-annual-surprise-below-0/",
        "Beat Quarter Revenue Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/revenue-quarter-surprise-above-0/",
        "Missed Quarter Revenue Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/revenue-quarter-surprise-below-0/",
        "Beat Annual Net Income Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/net-income-annual-surprise-above-0/",
        "Missed Annual Net Income Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/net-income-annual-surprise-below-0/",
        "Beat Quarter Net Income Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/net-income-quarter-surprise-above-0/",
        "Missed Quarter Net Income Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/net-income-quarter-surprise-below-0/",
        "Beat Annual EPS Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/eps-annual-surprise-above-0/",
        "Missed Annual EPS Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/eps-annual-surprise-below-0/",
        "Beat Quarter EPS Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/eps-quarter-surprise-above-0/",
        "Missed Quarter EPS Estimates": f"{BASE_URL}/equity/consensus-estimates/dashboard/forecaster/eps-quarter-surprise-below-0/"
    }

    def __init__(self, headless: bool = True, download_dir: str = None):
        """
        Initialize Trendlyne provider

        Args:
            headless: Run browser in headless mode
            download_dir: Directory for downloads (default: apps/data/tldata)
        """
        super().__init__(headless=headless)

        if download_dir is None:
            self.download_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata')
        else:
            self.download_dir = download_dir

        os.makedirs(self.download_dir, exist_ok=True)

    def get_credentials(self) -> tuple:
        """
        Retrieve Trendlyne credentials from database

        Returns:
            tuple: (username, password)

        Raises:
            DataProviderException: If credentials not found
        """
        try:
            creds = CredentialStore.objects.filter(service='trendlyne').first()
            if not creds:
                raise DataProviderException(
                    "No Trendlyne credentials found in database. "
                    "Please add credentials via Django admin."
                )
            return creds.username, creds.password
        except Exception as e:
            raise DataProviderException(f"Error retrieving credentials: {e}")

    def login(self) -> bool:
        """
        Login to Trendlyne with enhanced reliability

        Returns:
            bool: True if login successful

        Raises:
            DataProviderException: If login fails after all attempts
        """
        username, password = self.get_credentials()

        if not self.driver:
            self.init_driver()

        try:
            self.logger.info("Navigating to Trendlyne homepage...")
            self.driver.get(self.FEATURES_URL)
            time.sleep(3)

            # Try multiple selectors for login button
            login_selectors = [
                (By.ID, "login-signup-btn"),
                (By.XPATH, "//a[contains(text(), 'Login')]"),
                (By.XPATH, "//a[contains(@href, 'login')]"),
                (By.CSS_SELECTOR, "a[href*='login']"),
            ]

            self.try_multiple_selectors(login_selectors, action="click")
            time.sleep(2)

            # Try multiple selectors for username field
            username_selectors = [
                (By.ID, "id_login"),
                (By.ID, "id_email"),
                (By.NAME, "login"),
                (By.NAME, "email"),
                (By.XPATH, "//input[@type='email']"),
                (By.XPATH, "//input[@type='text'][@name='login']"),
            ]

            username_field = self.try_multiple_selectors(username_selectors, action="find")
            username_field.clear()
            username_field.send_keys(username)
            self.logger.info("Username entered successfully")

            # Try multiple selectors for password field
            password_selectors = [
                (By.ID, "id_password"),
                (By.NAME, "password"),
                (By.XPATH, "//input[@type='password']"),
            ]

            password_field = self.try_multiple_selectors(password_selectors, action="find")
            password_field.clear()
            password_field.send_keys(password)
            self.logger.info("Password entered successfully")

            # Try clicking submit button or pressing Enter
            submit_selectors = [
                (By.XPATH, "//button[@type='submit']"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//input[@type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Login')]"),
            ]

            try:
                self.try_multiple_selectors(submit_selectors, action="click")
            except DataProviderException:
                # Fallback: Press Enter on password field
                self.logger.info("Submit button not found, trying Enter key...")
                password_field.send_keys(Keys.RETURN)

            time.sleep(3)

            # Verify login success
            page_source_lower = self.driver.page_source.lower()
            success_indicators = [
                "logout" in page_source_lower,
                "user-profile" in page_source_lower,
                "dashboard" in page_source_lower,
                "my account" in page_source_lower,
            ]

            if any(success_indicators):
                self.logger.info("✅ Successfully logged in to Trendlyne")
                return True
            else:
                self.save_debug_screenshot("login_failed")
                raise DataProviderException("Login verification failed - success indicators not found")

        except DataProviderException:
            raise
        except Exception as e:
            self.save_debug_screenshot("login_error")
            raise DataProviderException(f"Login failed: {e}")

    def fetch_fno_data(self, download_dir: str = None) -> Dict:
        """
        Download F&O contracts data from Trendlyne

        Args:
            download_dir: Override default download directory

        Returns:
            dict: Download status and file info
        """
        if download_dir is None:
            download_dir = self.download_dir

        try:
            self.driver.get(f"{self.BASE_URL}/futures-options/contracts-excel-download/")
            self.logger.info("Navigated to F&O data downloader...")
            time.sleep(3)

            # Wait for download button and click
            download_button = self.wait_for_element(
                By.XPATH,
                "//a[contains(text(), 'Download')]",
                timeout=15,
                condition=EC.element_to_be_clickable
            )
            download_button.click()
            self.logger.info("F&O download initiated...")
            time.sleep(10)

            # Find downloaded file (could be .xlsx or .csv)
            files = [f for f in os.listdir(download_dir) if f.endswith(".xlsx") or f.endswith(".csv")]
            if not files:
                raise DataProviderException("No Excel/CSV file found after download")

            files.sort(key=lambda x: os.path.getctime(os.path.join(download_dir, x)), reverse=True)
            latest_file = files[0]

            # Determine file extension
            file_ext = ".xlsx" if latest_file.endswith(".xlsx") else ".csv"

            # Rename to standard format
            new_filename = f"fno_data_{datetime.now().strftime('%Y-%m-%d')}{file_ext}"
            os.rename(
                os.path.join(download_dir, latest_file),
                os.path.join(download_dir, new_filename)
            )

            self.logger.info(f"✅ F&O data saved: {new_filename}")

            return {
                'success': True,
                'filename': new_filename,
                'path': os.path.join(download_dir, new_filename)
            }

        except Exception as e:
            self.logger.error(f"F&O download failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def fetch_market_snapshot(self, download_dir: str = None) -> Dict:
        """
        Download market snapshot (stock) data from Trendlyne Market Snapshot Downloader

        Args:
            download_dir: Override default download directory

        Returns:
            dict: Download status and file info
        """
        if download_dir is None:
            download_dir = self.download_dir

        try:
            # Record files before download to detect new files
            files_before = set(os.listdir(download_dir))

            download_success = False

            # PRIMARY APPROACH: Navigate to Data Downloader page and click "Market Snapshot Downloader"
            # The sidebar has: Stock Data Downloader, F&O Data Downloader, Portfolio Downloader, Market Snapshot Downloader
            data_downloader_url = f"{self.BASE_URL}/tools/data-downloader/trendlyne-excel-connect/"
            self.logger.info(f"Navigating to Data Downloader page: {data_downloader_url}")
            self.driver.get(data_downloader_url)
            time.sleep(4)

            # Check if we're logged in (not redirected to login)
            if "login" in self.driver.current_url.lower():
                self.logger.warning("Redirected to login - session may have expired")
                return {'success': False, 'error': 'Login required - session expired'}

            # Log page info for debugging
            self.logger.info(f"Page title: {self.driver.title}")
            self.logger.info(f"Current URL: {self.driver.current_url}")

            # Step 1: Click on "Market Snapshot Downloader" in the left sidebar
            self.logger.info("Looking for 'Market Snapshot Downloader' in sidebar...")
            sidebar_selectors = [
                (By.XPATH, "//a[contains(text(), 'Market Snapshot Downloader')]"),
                (By.XPATH, "//span[contains(text(), 'Market Snapshot Downloader')]/parent::a"),
                (By.XPATH, "//*[contains(text(), 'Market Snapshot')]"),
                (By.CSS_SELECTOR, "a[href*='market-snapshot']"),
            ]

            clicked_sidebar = False
            for selector_type, selector in sidebar_selectors:
                try:
                    element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((selector_type, selector))
                    )
                    self.logger.info(f"Found sidebar item: {element.text}")
                    element.click()
                    time.sleep(3)
                    clicked_sidebar = True
                    self.logger.info("Clicked on Market Snapshot Downloader")
                    break
                except Exception as e:
                    self.logger.debug(f"Sidebar selector {selector} failed: {e}")
                    continue

            if not clicked_sidebar:
                # Try direct URL to Market Snapshot Downloader
                self.logger.info("Sidebar click failed, trying direct URL...")
                snapshot_urls = [
                    f"{self.BASE_URL}/tools/data-downloader/market-snapshot-downloader/",
                    f"{self.BASE_URL}/research/data-downloader/market-snapshot-downloader/",
                    f"{self.BASE_URL}/equity/market-snapshot-downloader/",
                ]
                for url in snapshot_urls:
                    try:
                        self.driver.get(url)
                        time.sleep(3)
                        if "market-snapshot" in self.driver.current_url.lower():
                            clicked_sidebar = True
                            self.logger.info(f"Navigated to: {self.driver.current_url}")
                            break
                    except:
                        continue

            # Save screenshot of the Market Snapshot page
            self.save_debug_screenshot("market_snapshot_page")
            self.logger.info(f"Current URL after navigation: {self.driver.current_url}")

            # Step 2: On the Market Snapshot page, look for download button/link
            # The page shows: MarketSnapshot-Data.xls with a blue "DOWNLOAD" button
            self.logger.info("Looking for download button on Market Snapshot page...")

            # First, let's find all clickable elements and log them for debugging
            try:
                all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                all_links = self.driver.find_elements(By.TAG_NAME, "a")
                self.logger.info(f"Found {len(all_buttons)} buttons and {len(all_links)} links on page")

                # Look for any element with DOWNLOAD text
                for btn in all_buttons:
                    try:
                        if 'download' in btn.text.lower():
                            self.logger.info(f"Found button with text: '{btn.text}'")
                    except:
                        pass
                for link in all_links:
                    try:
                        if 'download' in link.text.lower():
                            self.logger.info(f"Found link with text: '{link.text}', href: {link.get_attribute('href')[:60] if link.get_attribute('href') else 'N/A'}")
                    except:
                        pass
            except Exception as e:
                self.logger.warning(f"Error scanning page elements: {e}")

            download_selectors = [
                # The blue DOWNLOAD button (exact match)
                (By.XPATH, "//a[text()='DOWNLOAD']"),
                (By.XPATH, "//button[text()='DOWNLOAD']"),
                (By.XPATH, "//a[contains(text(), 'DOWNLOAD')]"),
                (By.XPATH, "//button[contains(text(), 'DOWNLOAD')]"),
                # Look for buttons near MarketSnapshot-Data text
                (By.XPATH, "//*[contains(text(), 'MarketSnapshot')]/following::a[1]"),
                (By.XPATH, "//*[contains(text(), 'MarketSnapshot')]/following::button[1]"),
                # CSS selectors for primary buttons
                (By.CSS_SELECTOR, "a.btn-primary"),
                (By.CSS_SELECTOR, "button.btn-primary"),
                # Href-based selectors
                (By.XPATH, "//a[contains(@href, 'download-stocks-data')]"),
                (By.XPATH, "//a[contains(@href, 'Stocks-data')]"),
                (By.CSS_SELECTOR, "a[href*='download']"),
            ]

            for selector_type, selector in download_selectors:
                try:
                    self.logger.info(f"Trying selector: {selector}")
                    element = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((selector_type, selector))
                    )
                    href = element.get_attribute('href') or 'N/A'
                    text = element.text or 'N/A'
                    self.logger.info(f"Found download element!")
                    self.logger.info(f"  Text: '{text}', Href: {href[:80] if href != 'N/A' else 'N/A'}...")

                    # Scroll element into view
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(1)

                    # Try JavaScript click if regular click fails
                    try:
                        element.click()
                    except Exception:
                        self.logger.info("Regular click failed, trying JavaScript click...")
                        self.driver.execute_script("arguments[0].click();", element)

                    self.logger.info("Click executed, waiting for download...")
                    time.sleep(12)  # Wait for download

                    # Check if a new file was downloaded
                    files_after = set(os.listdir(download_dir))
                    new_files = files_after - files_before

                    if new_files:
                        self.logger.info(f"New files downloaded: {new_files}")
                        # Check if any new file looks like stock data
                        for f in new_files:
                            if f.startswith("Stocks-data"):
                                self.logger.info(f"Downloaded stock data file: {f}")
                                download_success = True
                                break

                    if download_success:
                        break
                except Exception as e:
                    self.logger.debug(f"Selector {selector} failed: {e}")
                    continue

            # SECONDARY APPROACH: Try direct download URL
            if not download_success:
                self.logger.info("Button click failed, trying direct download URLs...")

                # Try various direct download URL patterns
                direct_urls = [
                    f"{self.BASE_URL}/research/data-downloader/download-stocks-data/?type=IND",
                    f"{self.BASE_URL}/research/data-downloader/download-stocks-data/",
                    f"{self.BASE_URL}/tools/data-downloader/download-stocks-data/?type=IND",
                    f"{self.BASE_URL}/tools/data-downloader/download-stocks-data/",
                ]

                for url in direct_urls:
                    try:
                        self.logger.info(f"Trying direct URL: {url}")
                        self.driver.get(url)
                        time.sleep(10)

                        files_after = set(os.listdir(download_dir))
                        new_files = files_after - files_before
                        if new_files:
                            for f in new_files:
                                if f.startswith("Stocks-data") or f.endswith('.xlsx'):
                                    self.logger.info(f"Downloaded via direct URL: {f}")
                                    download_success = True
                                    break
                        if download_success:
                            break
                    except Exception as e:
                        self.logger.debug(f"Direct URL {url} failed: {e}")
                        continue

            # TERTIARY APPROACH: Look for any download links on the page
            if not download_success:
                self.logger.info("Searching page for any download links...")
                try:
                    # Find all anchor tags
                    links = self.driver.find_elements(By.TAG_NAME, "a")
                    potential_links = []

                    for link in links:
                        try:
                            href = link.get_attribute('href') or ''
                            text = link.text.lower()
                            # Look for download-related links
                            if any(keyword in href.lower() for keyword in ['download', 'xlsx', 'stock']):
                                potential_links.append({'href': href, 'text': link.text, 'element': link})
                            elif any(keyword in text for keyword in ['download', 'stock', 'snapshot']):
                                potential_links.append({'href': href, 'text': link.text, 'element': link})
                        except:
                            continue

                    if potential_links:
                        self.logger.info(f"Found {len(potential_links)} potential download links:")
                        for i, pl in enumerate(potential_links[:5]):
                            self.logger.info(f"  {i+1}. '{pl['text'][:30]}' -> {pl['href'][:60]}")

                        # Try clicking each link
                        for pl in potential_links:
                            try:
                                if pl['href']:
                                    self.driver.get(pl['href'])
                                    time.sleep(10)
                                    files_after = set(os.listdir(download_dir))
                                    new_files = files_after - files_before
                                    if new_files:
                                        self.logger.info(f"Downloaded via link: {new_files}")
                                        download_success = True
                                        break
                            except:
                                continue
                except Exception as e:
                    self.logger.warning(f"Error searching for links: {e}")

            # Check for newly downloaded files
            files_after = set(os.listdir(download_dir))
            new_files = files_after - files_before

            # Filter for stock data files - ONLY look for Stocks-data pattern (original Trendlyne naming)
            stock_files = [f for f in new_files if f.startswith("Stocks-data") and (f.endswith(".xlsx") or f.endswith(".csv"))]

            if not stock_files:
                # Check all existing files for Stocks-data pattern
                all_files = os.listdir(download_dir)
                stock_files = [f for f in all_files if f.startswith("Stocks-data") and (f.endswith(".xlsx") or f.endswith(".csv"))]

            if not stock_files:
                self.logger.error("No Stock data file found. This feature may require a premium Trendlyne subscription.")
                raise DataProviderException("No Stock data file found after download attempt. The Excel Connect feature may require premium subscription.")

            # Use the most recent stock file
            stock_files.sort(key=lambda x: os.path.getctime(os.path.join(download_dir, x)), reverse=True)
            latest_file = stock_files[0]
            file_path = os.path.join(download_dir, latest_file)

            # Validate the file has stock data columns (not F&O data)
            import pandas as pd
            try:
                df_check = pd.read_excel(file_path, nrows=5)
                if 'SYMBOL' in df_check.columns and 'OPTION TYPE' in df_check.columns:
                    self.logger.error(f"File {latest_file} appears to be F&O data, not stock data")
                    raise DataProviderException("Downloaded file is F&O data, not stock data")
                if 'Stock Name' not in df_check.columns and 'NSEcode' not in df_check.columns:
                    self.logger.warning(f"File {latest_file} may not be valid stock data - missing expected columns")
            except DataProviderException:
                raise
            except Exception as e:
                self.logger.warning(f"Could not validate file: {e}")

            self.logger.info(f"✅ Stock Data saved: {latest_file}")

            return {
                'success': True,
                'filename': latest_file,
                'path': file_path
            }

        except Exception as e:
            self.logger.error(f"Market Snapshot download failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def fetch_forecaster_data(self, output_dir: str = None) -> Dict:
        """
        Scrape analyst forecaster data from 21 different Trendlyne screeners

        Args:
            output_dir: Override default output directory

        Returns:
            dict: Scraping results for all screeners
        """
        if output_dir is None:
            output_dir = os.path.join(self.download_dir, 'forecaster')

        os.makedirs(output_dir, exist_ok=True)

        results = {}

        for label, url in self.FORECASTER_URLS.items():
            try:
                self.logger.info(f"📊 Fetching: {label}")
                self.driver.get(url)
                time.sleep(2)

                soup = BeautifulSoup(self.driver.page_source, 'html5lib')
                table = soup.find("table", class_="trendlyne-screener-table")

                if not table:
                    self.logger.warning(f"Table not found on {label}")
                    results[label] = {'success': False, 'error': 'Table not found'}
                    continue

                headers = [th.text.strip() for th in table.find("thead").find_all("th")]
                rows = []
                for tr in table.find("tbody").find_all("tr"):
                    row = [td.get_text(strip=True) for td in tr.find_all("td")]
                    rows.append(row)

                df = pd.DataFrame(rows, columns=headers)
                safe_label = label.replace(" ", "_").replace("%", "pct").replace("/", "_")
                file_path = os.path.join(output_dir, f"trendlyne_{safe_label}.csv")
                df.to_csv(file_path, index=False)

                self.logger.info(f"✅ Saved {file_path}")
                results[label] = {
                    'success': True,
                    'filename': f"trendlyne_{safe_label}.csv",
                    'rows': len(rows)
                }

            except Exception as e:
                self.logger.error(f"Error fetching {label}: {e}")
                results[label] = {'success': False, 'error': str(e)}

        return results

    def fetch_data(self, data_type: str, **kwargs) -> Dict:
        """
        Fetch specific type of data

        Args:
            data_type: 'fno', 'market_snapshot', 'forecaster'
            **kwargs: Additional parameters

        Returns:
            dict: Fetch results
        """
        if data_type == 'fno':
            return self.fetch_fno_data(**kwargs)
        elif data_type == 'market_snapshot':
            return self.fetch_market_snapshot(**kwargs)
        elif data_type == 'forecaster':
            return self.fetch_forecaster_data(**kwargs)
        else:
            raise DataProviderException(f"Unknown data type: {data_type}")

    def fetch_all_data(self, download_dir: str = None) -> Dict:
        """
        Fetch all available Trendlyne data

        Args:
            download_dir: Override default download directory

        Returns:
            dict: Combined results for all data types
        """
        if download_dir:
            self.download_dir = download_dir

        try:
            # Initialize driver and login
            self.init_driver(download_dir=self.download_dir)

            if not self.login():
                return {
                    'success': False,
                    'error': 'Login failed'
                }

            results = {
                'fno': self.fetch_fno_data(),
                'market_snapshot': self.fetch_market_snapshot(),
                'forecaster': self.fetch_forecaster_data(),
            }

            self.logger.info("✅ All Trendlyne data fetched successfully")

            return {
                'success': True,
                'results': results,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Error in fetch_all_data: {e}")
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            self.cleanup()


# Convenience function for backwards compatibility
def get_all_trendlyne_data(download_dir: str = None) -> bool:
    """
    Fetch all Trendlyne data (backwards compatible function)

    Args:
        download_dir: Directory for downloads

    Returns:
        bool: True if successful
    """
    with TrendlyneProvider() as provider:
        result = provider.fetch_all_data(download_dir=download_dir)
        return result.get('success', False)
