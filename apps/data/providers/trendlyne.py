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

    # ===== ANALYST REPORTS SCRAPING =====

    def _parse_price(self, price_str: str) -> Optional[float]:
        """
        Parse price string to float

        Args:
            price_str: Price string like "₹1,234.56" or "1234.56"

        Returns:
            float or None if parsing fails
        """
        if not price_str:
            return None
        try:
            # Remove currency symbol, commas, and whitespace
            clean = re.sub(r'[₹,\s]', '', str(price_str))
            return float(clean) if clean else None
        except (ValueError, TypeError):
            return None

    def _parse_recommendation(self, rec_str: str) -> str:
        """
        Parse recommendation string to standardized type

        Args:
            rec_str: Recommendation string like "Buy", "Strong Buy", "Sell"

        Returns:
            Standardized recommendation type
        """
        if not rec_str:
            return 'UNKNOWN'

        rec_lower = rec_str.lower().strip()

        if 'strong buy' in rec_lower or 'strongbuy' in rec_lower:
            return 'STRONG_BUY'
        elif 'strong sell' in rec_lower or 'strongsell' in rec_lower:
            return 'STRONG_SELL'
        elif 'buy' in rec_lower:
            return 'BUY'
        elif 'sell' in rec_lower:
            return 'SELL'
        elif 'hold' in rec_lower or 'neutral' in rec_lower:
            return 'HOLD'
        else:
            return 'UNKNOWN'

    def _download_pdf(self, pdf_url: str, symbol: str, report_date: str, author: str) -> Optional[str]:
        """
        Download PDF report to local storage using authenticated Selenium session.

        Trendlyne PDF URLs require authentication and redirect to S3 pre-signed URLs.
        We use the Selenium driver (already logged in) to follow the redirect,
        then download the actual PDF from the S3 URL.

        Args:
            pdf_url: URL to download PDF from (Trendlyne URL)
            symbol: Stock symbol
            report_date: Date of report (YYYY-MM-DD)
            author: Author/brokerage name

        Returns:
            Local file path if successful, None otherwise
        """
        if not pdf_url:
            return None

        try:
            import requests
            import time

            # Create directory for analyst reports
            reports_dir = os.path.join(self.download_dir, 'analyst_reports', symbol.upper())
            os.makedirs(reports_dir, exist_ok=True)

            # Sanitize filename
            safe_author = re.sub(r'[^\w\-]', '_', author)[:50]
            filename = f"{symbol}_{report_date}_{safe_author}.pdf"
            local_path = os.path.join(reports_dir, filename)

            # Skip if already downloaded and is a valid PDF
            if os.path.exists(local_path) and os.path.getsize(local_path) > 5000:
                with open(local_path, 'rb') as f:
                    if f.read(5) == b'%PDF-':
                        self.logger.info(f"Valid PDF already exists: {local_path}")
                        return local_path
                # Existing file is not a valid PDF (e.g. HTML login page), delete and re-download
                self.logger.warning(f"Existing file is not a valid PDF, re-downloading: {local_path}")
                os.remove(local_path)

            # Use authenticated Selenium session to get S3 redirect URL
            if hasattr(self, 'driver') and self.driver:
                self.logger.info(f"Downloading PDF via authenticated session: {pdf_url[:80]}...")
                self.driver.get(pdf_url)
                time.sleep(2)
                s3_url = self.driver.current_url

                # Download from S3 (pre-signed URL, no auth needed)
                response = requests.get(s3_url, timeout=30)
                if response.status_code == 200 and len(response.content) > 5000 and response.content[:5] == b'%PDF-':
                    with open(local_path, 'wb') as f:
                        f.write(response.content)
                    self.logger.info(f"PDF saved ({len(response.content)} bytes): {local_path}")
                    return local_path
                else:
                    self.logger.warning(
                        f"PDF download failed: status={response.status_code}, "
                        f"size={len(response.content)}, "
                        f"is_pdf={response.content[:5] == b'%PDF-' if response.content else False}"
                    )
                    return None
            else:
                # Fallback: direct download (may not work for authenticated URLs)
                self.logger.warning(f"No Selenium driver available, trying direct download: {pdf_url[:80]}...")
                response = requests.get(pdf_url, timeout=30, headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                })
                if response.status_code == 200 and len(response.content) > 5000 and response.content[:5] == b'%PDF-':
                    with open(local_path, 'wb') as f:
                        f.write(response.content)
                    self.logger.info(f"PDF saved via direct download ({len(response.content)} bytes): {local_path}")
                    return local_path
                else:
                    self.logger.warning(f"Direct PDF download failed or returned non-PDF content")
                    return None

        except Exception as e:
            self.logger.error(f"Error downloading PDF: {e}")
            return None

    def fetch_analyst_price_target(self, symbol: str, trendlyne_id: int = None) -> Dict:
        """
        Fetch analyst consensus price target data for a stock

        Args:
            symbol: Stock symbol (NSE code)
            trendlyne_id: Optional Trendlyne internal ID

        Returns:
            dict: Price target data with success status
        """
        try:
            if not self.driver:
                self.init_driver()

            # IMPORTANT: Trendlyne URLs require the trendlyne_id
            # URL patterns that work:
            # - /equity/{trendlyne_id}/{SYMBOL}/
            # - /research-reports/stock/{trendlyne_id}/{SYMBOL}/
            # URLs WITHOUT trendlyne_id return 404!

            # Strategy: If no trendlyne_id, first go to research-reports page
            # which accepts symbol-only URLs and redirects to proper URL with ID

            if not trendlyne_id:
                # First, try research-reports page to discover the trendlyne_id
                # This URL pattern redirects to the proper URL with ID
                discover_url = f"{self.BASE_URL}/research-reports/stock/{symbol.upper()}/"
                self.logger.info(f"Discovering trendlyne_id via: {discover_url}")
                self.driver.get(discover_url)
                time.sleep(4)

                current_url = self.driver.current_url
                self.logger.info(f"After redirect, current URL: {current_url}")

                # Extract trendlyne_id from redirected URL
                # Pattern: /research-reports/stock/{id}/{SYMBOL}/
                match = re.search(r'/research-reports/stock/(\d+)/', current_url)
                if match:
                    trendlyne_id = int(match.group(1))
                    self.logger.info(f"Extracted trendlyne_id from research-reports URL: {trendlyne_id}")

                if not trendlyne_id:
                    # Try searching in page source for equity links
                    page_source = self.driver.page_source
                    id_match = re.search(rf'/equity/(\d+)/{symbol.upper()}', page_source, re.I)
                    if id_match:
                        trendlyne_id = int(id_match.group(1))
                        self.logger.info(f"Extracted trendlyne_id from page source links: {trendlyne_id}")

                if not trendlyne_id:
                    # Try consensus-estimates link pattern
                    id_match = re.search(rf'/consensus-estimates/(\d+)/{symbol.upper()}', page_source, re.I)
                    if id_match:
                        trendlyne_id = int(id_match.group(1))
                        self.logger.info(f"Extracted trendlyne_id from consensus link: {trendlyne_id}")

            if not trendlyne_id:
                self.logger.error(f"Could not discover trendlyne_id for {symbol}")
                return {
                    'success': False,
                    'symbol': symbol,
                    'error': f"Could not find trendlyne_id for {symbol}. Stock may not exist on Trendlyne."
                }

            # ===== FIRST: Scrape equity page for target price and analyst count =====
            # The equity page has the forecaster section with target price data
            # URL must include trendlyne_id: /equity/{trendlyne_id}/{SYMBOL}/
            equity_url = f"{self.BASE_URL}/equity/{trendlyne_id}/{symbol.upper()}/"

            self.logger.info(f"Loading equity page for target data: {equity_url}")
            self.driver.get(equity_url)
            time.sleep(4)

            # Check if we hit a 404 page
            equity_current_url = self.driver.current_url
            self.logger.info(f"Equity page URL after load: {equity_current_url}")

            # Parse equity page for target price data
            equity_soup = BeautifulSoup(self.driver.page_source, 'html5lib')
            page_title = equity_soup.title.string if equity_soup.title else ''

            if 'not found' in page_title.lower() or 'dead end' in equity_soup.get_text().lower():
                self.logger.warning(f"Equity page returned 404. Trying consensus-estimates page...")
                # Try consensus-estimates page as fallback
                consensus_url = f"{self.BASE_URL}/equity/consensus-estimates/{trendlyne_id}/{symbol.upper()}/"
                self.logger.info(f"Trying consensus page: {consensus_url}")
                self.driver.get(consensus_url)
                time.sleep(4)
                equity_soup = BeautifulSoup(self.driver.page_source, 'html5lib')
                equity_current_url = self.driver.current_url

            # Initialize result with data from equity page
            equity_target_price = None
            equity_upside = None
            equity_analyst_count = None
            equity_current_price = None

            # === METHOD 1: Find the consensus-estimates link block ===
            # This block has: <span class="fs1p8rem real-score">1,157</span>
            # followed by forecaster-insights-container with upside and analyst count
            consensus_block = equity_soup.find('a', href=re.compile(r'consensus-estimates'))
            if consensus_block:
                self.logger.info("Found consensus-estimates block")

                # Target price is in <span class="real-score"> inside this block
                # The key is to find the span with BOTH 'fs1p8rem' AND 'real-score' classes
                target_spans = consensus_block.find_all('span', class_=True)
                for span in target_spans:
                    span_classes = span.get('class', [])
                    # Target price span has both fs1p8rem and real-score classes
                    if 'fs1p8rem' in span_classes and 'real-score' in span_classes:
                        target_text = span.get_text(strip=True)
                        parsed_price = self._parse_price(target_text)
                        # Validate: target price should be realistic (> 100 for most F&O stocks)
                        if parsed_price and parsed_price > 100:
                            equity_target_price = parsed_price
                            self.logger.info(f"Found target price from consensus block (fs1p8rem real-score): {equity_target_price}")
                            break
                        else:
                            self.logger.debug(f"Skipped price {parsed_price} from span (too low)")

                # Find forecaster-insights-container within this block
                forecaster_container = consensus_block.find('div', class_='forecaster-insights-container')
                if forecaster_container:
                    container_text = forecaster_container.get_text()
                    self.logger.info(f"Forecaster container text: {container_text}")

                    # Extract upside: "1Yr Price target upside is 24%"
                    upside_match = re.search(r'upside\s+is\s+([\d.]+)%', container_text, re.I)
                    if upside_match:
                        equity_upside = float(upside_match.group(1))
                        self.logger.info(f"Found upside from forecaster container: {equity_upside}%")

                    # Extract analyst count: "39 analysts"
                    analyst_match = re.search(r'(\d+)\s+analysts?', container_text, re.I)
                    if analyst_match:
                        equity_analyst_count = int(analyst_match.group(1))
                        self.logger.info(f"Found analyst count from forecaster container: {equity_analyst_count}")

            # === METHOD 2: Fallback - Find real-score with fs1p8rem class anywhere ===
            if not equity_target_price:
                # Look for spans with both 'fs1p8rem' and 'real-score' classes
                target_spans = equity_soup.find_all('span', class_=lambda c: c and 'fs1p8rem' in c and 'real-score' in c)
                for span in target_spans:
                    target_text = span.get_text(strip=True)
                    price = self._parse_price(target_text)
                    # Validate: target price should be > 50 for most stocks
                    if price and price > 50:
                        equity_target_price = price
                        self.logger.info(f"Found target price from fs1p8rem real-score span: {equity_target_price}")
                        break

            # === METHOD 3: Look for forecaster-insights-container anywhere ===
            if not equity_upside or not equity_analyst_count:
                forecaster_container = equity_soup.find('div', class_='forecaster-insights-container')
                if forecaster_container:
                    container_text = forecaster_container.get_text()
                    if not equity_upside:
                        upside_match = re.search(r'upside\s+is\s+([\d.]+)%', container_text, re.I)
                        if upside_match:
                            equity_upside = float(upside_match.group(1))
                            self.logger.info(f"Found upside from fallback container: {equity_upside}%")
                    if not equity_analyst_count:
                        analyst_match = re.search(r'(\d+)\s+analysts?', container_text, re.I)
                        if analyst_match:
                            equity_analyst_count = int(analyst_match.group(1))
                            self.logger.info(f"Found analyst count from fallback container: {equity_analyst_count}")

            # === METHOD 4: Find current price (LTP) ===
            # Look for price in various places
            ltp_patterns = [
                (r'₹\s*([\d,]+\.?\d*)', 'rupee symbol'),
                (r'CMP[:\s]*₹?\s*([\d,]+\.?\d*)', 'CMP label'),
                (r'LTP[:\s]*₹?\s*([\d,]+\.?\d*)', 'LTP label'),
            ]

            page_text = equity_soup.get_text()
            for pattern, desc in ltp_patterns:
                matches = re.findall(pattern, page_text)
                for match in matches:
                    price = self._parse_price(match)
                    # Current price should be reasonable (> 10 and < 100000)
                    if price and 10 < price < 100000:
                        # Skip if this looks like the target price we already found
                        if equity_target_price and abs(price - equity_target_price) < 1:
                            continue
                        equity_current_price = price
                        self.logger.info(f"Found current price via {desc}: {equity_current_price}")
                        break
                if equity_current_price:
                    break

            # === METHOD 5: Calculate target price from current price and upside ===
            # If we have upside and current price but no target, calculate it
            if not equity_target_price and equity_current_price and equity_upside:
                equity_target_price = round(equity_current_price * (1 + equity_upside / 100), 2)
                self.logger.info(f"Calculated target price from current price and upside: {equity_target_price}")

            # === Validate target price ===
            # If target price seems unrealistic, recalculate from current price + upside
            if equity_target_price and equity_current_price and equity_upside:
                expected_target = equity_current_price * (1 + equity_upside / 100)
                # If the scraped target differs by more than 20% from expected, use calculated value
                if abs(equity_target_price - expected_target) / expected_target > 0.20:
                    self.logger.warning(f"Scraped target price {equity_target_price} differs significantly from expected {expected_target:.2f}")
                    self.logger.info(f"Using calculated target price: {expected_target:.2f}")
                    equity_target_price = round(expected_target, 2)

            # ===== SECOND: Navigate to research reports page for reports table =====
            if trendlyne_id:
                reports_url = f"{self.BASE_URL}/research-reports/stock/{trendlyne_id}/{symbol.upper()}/"
            else:
                reports_url = f"{self.BASE_URL}/research-reports/stock/{symbol.upper()}/"

            self.logger.info(f"Navigating to reports page: {reports_url}")
            self.driver.get(reports_url)
            time.sleep(4)  # Allow page to fully load

            soup = BeautifulSoup(self.driver.page_source, 'html5lib')
            page_text = soup.get_text()
            final_url = self.driver.current_url

            # Try to extract trendlyne_id from final URL if still not found
            if not trendlyne_id:
                match = re.search(r'/(?:stock|equity)/(\d+)/', final_url)
                if match:
                    trendlyne_id = int(match.group(1))
                    self.logger.info(f"Extracted trendlyne_id from final URL: {trendlyne_id}")

            result = {
                'success': True,
                'symbol': symbol.upper(),
                'trendlyne_id': trendlyne_id,
                'source_url': final_url,
                'current_price': equity_current_price,  # From equity page
                'avg_target_price': equity_target_price,  # From equity page
                'upside_pct': equity_upside,  # From equity page
                'analyst_count': equity_analyst_count or 0,  # From equity page
                'strong_buy_count': 0,
                'buy_count': 0,
                'hold_count': 0,
                'sell_count': 0,
                'strong_sell_count': 0,
            }

            self.logger.info(f"Reports page loaded: {final_url}")
            self.logger.info(f"Page title: {soup.title.string if soup.title else 'N/A'}")
            self.logger.info(f"Pre-populated from equity page: Current={equity_current_price}, Target={equity_target_price}, Upside={equity_upside}%, Analysts={equity_analyst_count}")

            try:
                # Note: Target price, upside, and analyst count were already extracted from equity page above
                # The code below is for parsing additional data from the REPORTS page

                # === APPROACH 1: Try to find additional data from reports page if equity page missed anything ===
                if not result['avg_target_price']:
                    target_span = soup.find('span', class_='real-score')
                    if target_span:
                        target_text = target_span.get_text(strip=True)
                        target_price = self._parse_price(target_text)
                        if target_price and 10 < target_price < 100000:
                            result['avg_target_price'] = target_price
                            self.logger.info(f"Found target price from reports page real-score: {target_price}")

                # === APPROACH 2: Find forecaster-insights-container on reports page (backup) ===
                if not result['upside_pct'] or not result['analyst_count']:
                    forecaster_container = soup.find('div', class_='forecaster-insights-container')
                    if forecaster_container:
                        self.logger.info("Found forecaster-insights-container on reports page!")
                        container_text = forecaster_container.get_text()

                        if not result['upside_pct']:
                            upside_match = re.search(r'upside\s+is\s+([\d.]+)%', container_text, re.I)
                            if upside_match:
                                result['upside_pct'] = float(upside_match.group(1))
                                self.logger.info(f"Found upside from reports page container: {result['upside_pct']}%")

                        if not result['analyst_count']:
                            analyst_match = re.search(r'(\d+)\s+analysts?', container_text, re.I)
                            if analyst_match:
                                result['analyst_count'] = int(analyst_match.group(1))
                                self.logger.info(f"Found analyst count from reports page container: {result['analyst_count']}")

                # === APPROACH 2: Parse Consensus row from reports table ===
                # The first row in the reports table has consensus data:
                # Cell structure: hidden, Date, Stock, Author(Consensus Share Price Target), LTP, Target, Price at reco, Upside(%), Type
                # LTP: 938.05, Target: 1157.44, Upside: 23.39%, Type: buy
                consensus_row = soup.find('a', href=re.compile(r'consensus-estimates'))
                if consensus_row:
                    # Navigate up to find the table row
                    parent_row = consensus_row.find_parent('tr')
                    if parent_row:
                        cells = parent_row.find_all('td')
                        self.logger.info(f"Found consensus row with {len(cells)} cells")

                        # Based on Trendlyne HTML structure:
                        # Cell 0: hidden, Cell 1: Date, Cell 2: Stock, Cell 3: Author/Consensus link
                        # Cell 4: LTP, Cell 5: Target, Cell 6: Price at reco, Cell 7: Upside%, Cell 8: Type

                        # Get LTP (Cell 4)
                        if len(cells) > 4:
                            ltp_text = cells[4].get_text(strip=True)
                            ltp = self._parse_price(ltp_text)
                            if ltp and 10 < ltp < 100000:
                                result['current_price'] = ltp
                                self.logger.info(f"Found LTP from consensus row cell 4: {ltp}")

                        # Get Target (Cell 5)
                        if len(cells) > 5:
                            target_text = cells[5].get_text(strip=True)
                            target = self._parse_price(target_text)
                            if target and 10 < target < 100000:
                                result['avg_target_price'] = target
                                self.logger.info(f"Found target from consensus row cell 5: {target}")

                        # Get Upside (Cell 7)
                        if len(cells) > 7:
                            upside_text = cells[7].get_text(strip=True)
                            upside_match = re.search(r'([\d.]+)', upside_text)
                            if upside_match:
                                try:
                                    upside = float(upside_match.group(1))
                                    # Check for negative (has 'negative' class)
                                    if 'negative' in str(cells[7].get('class', [])):
                                        upside = -upside
                                    result['upside_pct'] = upside
                                    self.logger.info(f"Found upside from consensus row cell 7: {upside}%")
                                except ValueError:
                                    pass

                # === APPROACH 3: Look for JSON-LD schema data ===
                # Trendlyne embeds rating data in JSON-LD: "ratingCount": "26"
                for script in soup.find_all('script', type='application/ld+json'):
                    try:
                        import json
                        data = json.loads(script.string)
                        if data.get('@type') == 'AggregateRating':
                            rating_count = data.get('ratingCount')
                            if rating_count and not result['analyst_count']:
                                result['analyst_count'] = int(rating_count)
                                self.logger.info(f"Found analyst count from JSON-LD: {result['analyst_count']}")
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue

                # === APPROACH 4: Fallback regex patterns ===
                if not result['current_price']:
                    ltp_patterns = [
                        (r'LTP[:\s]*₹?\s*([\d,]+\.?\d*)', 'LTP pattern'),
                        (r'₹\s*([\d,]+\.?\d*)', 'Rupee symbol pattern'),
                    ]
                    for pattern, desc in ltp_patterns:
                        matches = re.findall(pattern, page_text, re.I)
                        for match in matches:
                            price = self._parse_price(match)
                            if price and 10 < price < 100000:
                                result['current_price'] = price
                                self.logger.info(f"Found current price via {desc}: {price}")
                                break
                        if result['current_price']:
                            break

                if not result['upside_pct']:
                    upside_patterns = [
                        (r'upside\s+(?:is\s+)?([\d.]+)\s*%', 'upside is X%'),
                        (r'([\d.]+)\s*%\s*upside', 'X% upside'),
                    ]
                    for pattern, desc in upside_patterns:
                        matches = re.findall(pattern, page_text, re.I)
                        for match in matches:
                            try:
                                upside = float(match)
                                if 0 < upside < 200:
                                    result['upside_pct'] = upside
                                    self.logger.info(f"Found upside via {desc}: {upside}%")
                                    break
                            except ValueError:
                                continue
                        if result['upside_pct']:
                            break

                # === APPROACH 5: Find analyst recommendation counts ===
                rec_patterns_with_count = [
                    (r'Strong\s*Buy[:\s]*\(?(\d+)\)?', 'strong_buy_count'),
                    (r'(?<!Strong\s)Buy[:\s]*\(?(\d+)\)?', 'buy_count'),
                    (r'Hold[:\s]*\(?(\d+)\)?', 'hold_count'),
                    (r'(?<!Strong\s)Sell[:\s]*\(?(\d+)\)?', 'sell_count'),
                    (r'Strong\s*Sell[:\s]*\(?(\d+)\)?', 'strong_sell_count'),
                ]

                for pattern, field in rec_patterns_with_count:
                    if result[field] == 0:
                        matches = re.findall(pattern, page_text, re.I)
                        for match in matches:
                            try:
                                count = int(match)
                                if 0 <= count < 100:
                                    result[field] = count
                                    self.logger.info(f"Found {field}: {count}")
                                    break
                            except ValueError:
                                continue

                # Method 2: Look for analyst ratings in a structured section
                analyst_sections = soup.find_all(['div', 'section'],
                    class_=lambda x: x and any(kw in str(x).lower() for kw in ['forecast', 'analyst', 'rating', 'consensus']))

                for section in analyst_sections:
                    section_text = section.get_text()
                    self.logger.debug(f"Checking analyst section: {section_text[:200]}")

                    # Look for rating distribution
                    for pattern, field in rec_patterns_with_count:
                        if result[field] == 0:  # Only if not already found
                            matches = re.findall(pattern, section_text, re.I)
                            if matches:
                                try:
                                    result[field] = int(matches[0])
                                except ValueError:
                                    pass

                # Method 3: Look for table rows with recommendation data
                # Trendlyne often displays data in tables
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        row_text = ' '.join(c.get_text(strip=True) for c in cells)

                        # Check for target price in table
                        if not result['avg_target_price']:
                            if any(kw in row_text.lower() for kw in ['target', 'consensus']):
                                prices = re.findall(r'₹?\s*([\d,]+\.?\d*)', row_text)
                                for p in prices:
                                    price = self._parse_price(p)
                                    if price and 10 < price < 1000000:
                                        result['avg_target_price'] = price
                                        self.logger.info(f"Found target price from table: {price}")
                                        break

                        # Check for recommendation counts in table
                        for rec_name, field in [('strong buy', 'strong_buy_count'), ('buy', 'buy_count'),
                                                ('hold', 'hold_count'), ('sell', 'sell_count'),
                                                ('strong sell', 'strong_sell_count')]:
                            if result[field] == 0 and rec_name in row_text.lower():
                                nums = re.findall(r'(\d+)', row_text)
                                for num in nums:
                                    try:
                                        count = int(num)
                                        if 0 <= count < 100:
                                            result[field] = count
                                            self.logger.info(f"Found {field} from table: {count}")
                                            break
                                    except ValueError:
                                        pass

                # Method 4: Look for data attributes or specific class names
                # Trendlyne may use data-* attributes
                for elem in soup.find_all(attrs={'data-target': True}):
                    try:
                        result['avg_target_price'] = float(elem['data-target'])
                        self.logger.info(f"Found target from data attribute: {result['avg_target_price']}")
                    except (ValueError, TypeError):
                        pass

                for elem in soup.find_all(attrs={'data-upside': True}):
                    try:
                        result['upside_pct'] = float(elem['data-upside'])
                        self.logger.info(f"Found upside from data attribute: {result['upside_pct']}")
                    except (ValueError, TypeError):
                        pass

                # === Calculate total analysts from recommendation counts (if found) ===
                rec_total = (
                    result['strong_buy_count'] + result['buy_count'] +
                    result['hold_count'] + result['sell_count'] + result['strong_sell_count']
                )
                # Only override analyst_count if we found recommendation breakdown
                if rec_total > 0:
                    result['analyst_count'] = rec_total
                # Otherwise keep the equity_analyst_count we found earlier

                # === Calculate upside if not found but have prices ===
                if result['upside_pct'] is None and result['avg_target_price'] and result['current_price']:
                    if result['current_price'] > 0:
                        result['upside_pct'] = round(
                            ((result['avg_target_price'] - result['current_price']) / result['current_price']) * 100, 2
                        )
                        self.logger.info(f"Calculated upside: {result['upside_pct']}%")

                # === Debug: Save HTML if no useful data found ===
                has_data = (result['avg_target_price'] is not None or
                           result['analyst_count'] > 0 or
                           result['upside_pct'] is not None)

                if not has_data:
                    self.logger.warning(f"No analyst data found for {symbol}, saving debug files")
                    self._save_debug_html(soup, f"analyst_debug_{symbol}")
                    self.save_debug_screenshot(f"analyst_debug_{symbol}")

                    # Log some page content for debugging
                    self.logger.info(f"Page title: {soup.title.string if soup.title else 'N/A'}")
                    self.logger.info(f"Current URL: {final_url}")

                    # Log first 2000 chars of visible text
                    visible_text = ' '.join(page_text.split())[:2000]
                    self.logger.info(f"Page text sample: {visible_text}")

            except Exception as e:
                self.logger.warning(f"Error parsing price target data: {e}", exc_info=True)

            self.logger.info(f"Price target for {symbol}: Current={result['current_price']}, "
                           f"Target={result['avg_target_price']}, Upside={result['upside_pct']}%, "
                           f"Analysts={result['analyst_count']} "
                           f"(SB:{result['strong_buy_count']}, B:{result['buy_count']}, "
                           f"H:{result['hold_count']}, S:{result['sell_count']}, SS:{result['strong_sell_count']})")

            return result

        except Exception as e:
            self.logger.error(f"Error fetching price target for {symbol}: {e}", exc_info=True)
            return {
                'success': False,
                'symbol': symbol,
                'error': str(e)
            }

    def _save_debug_html(self, soup, prefix: str):
        """Save debug HTML for troubleshooting scraping issues"""
        try:
            debug_dir = os.path.join(self.download_dir, 'debug_html')
            os.makedirs(debug_dir, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = os.path.join(debug_dir, f"{prefix}_{timestamp}.html")

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(str(soup))

            self.logger.info(f"Saved debug HTML to: {filepath}")
        except Exception as e:
            self.logger.warning(f"Could not save debug HTML: {e}")

    def fetch_analyst_reports(
        self,
        symbol: str,
        trendlyne_id: int = None,
        months_back: int = 3,
        download_pdfs: bool = True
    ) -> Dict:
        """
        Fetch analyst research reports for a stock

        Args:
            symbol: Stock symbol (NSE code)
            trendlyne_id: Optional Trendlyne internal ID
            months_back: Number of months to look back (default: 3)
            download_pdfs: Whether to download PDF reports

        Returns:
            dict: Reports data with success status
        """
        try:
            # Build URL
            if trendlyne_id:
                url = f"{self.BASE_URL}/research-reports/stock/{trendlyne_id}/{symbol.upper()}/"
            else:
                url = f"{self.BASE_URL}/research-reports/stock/{symbol.upper()}/"

            self.logger.info(f"Fetching analyst reports for {symbol} from {url}")

            if not self.driver:
                self.init_driver()

            self.driver.get(url)
            time.sleep(4)

            # Extract trendlyne_id from URL if not provided
            current_url = self.driver.current_url
            if not trendlyne_id:
                match = re.search(r'/stock/(\d+)/', current_url)
                if match:
                    trendlyne_id = int(match.group(1))

            soup = BeautifulSoup(self.driver.page_source, 'html5lib')

            # Calculate cutoff date
            cutoff_date = datetime.now() - timedelta(days=months_back * 30)

            reports = []

            # Find reports table - Trendlyne uses class "tl-dataTable"
            table = soup.find('table', class_='tl-dataTable')
            if not table:
                table = soup.find('table', id='brokerTable')
            if not table:
                # Fallback: Try finding any table on the page
                tables = soup.find_all('table')
                for t in tables:
                    if t.find(text=re.compile(r'report|date|author|brokerage', re.I)):
                        table = t
                        break

            if table:
                # Get rows from tbody (skip the consensus row if present)
                tbody = table.find('tbody')
                rows = tbody.find_all('tr') if tbody else table.find_all('tr')[1:]

                self.logger.info(f"Found {len(rows)} rows in reports table")

                for row in rows:
                    try:
                        # Skip consensus row (first row with "Consensus Share Price Target")
                        if 'consensus' in row.get_text().lower():
                            continue

                        cells = row.find_all(['td', 'th'])
                        if len(cells) < 5:
                            continue

                        report = {
                            'symbol': symbol.upper(),
                            'nse_code': symbol.upper(),
                            'trendlyne_id': trendlyne_id,
                            'report_date': None,
                            'author': '',
                            'report_title': '',
                            'ltp_at_report': None,
                            'target_price': None,
                            'upside_pct': None,
                            'recommendation_type': 'UNKNOWN',
                            'pdf_url': '',
                            'pdf_local_path': '',
                        }

                        # Trendlyne table structure (based on user-provided HTML):
                        # Cell 0: Hidden (Summary)
                        # Cell 1: Date (e.g., "20 Jan 2026")
                        # Cell 2: Stock name
                        # Cell 3: Author (broker name)
                        # Cell 4: LTP
                        # Cell 5: Target
                        # Cell 6: Price at reco
                        # Cell 7: Upside(%)
                        # Cell 8: Type (Buy/Hold/Sell)
                        # Cell 9: Report links

                        # Parse Date (Cell 1)
                        date_cell = cells[1] if len(cells) > 1 else None
                        if date_cell:
                            date_text = date_cell.get_text(strip=True)
                            # Try parsing dates like "20 Jan 2026"
                            for fmt in ['%d %b %Y', '%d-%b-%Y', '%d/%m/%Y', '%Y-%m-%d']:
                                try:
                                    report['report_date'] = datetime.strptime(date_text, fmt).date()
                                    break
                                except ValueError:
                                    continue

                        # Parse Author (Cell 3)
                        author_cell = cells[3] if len(cells) > 3 else None
                        if author_cell:
                            author_link = author_cell.find('a', class_='broker-link')
                            if author_link:
                                report['author'] = author_link.get_text(strip=True)[:200]
                            else:
                                report['author'] = author_cell.get_text(strip=True)[:200]

                        # Parse LTP (Cell 4)
                        ltp_cell = cells[4] if len(cells) > 4 else None
                        if ltp_cell:
                            report['ltp_at_report'] = self._parse_price(ltp_cell.get_text(strip=True))

                        # Parse Target (Cell 5)
                        target_cell = cells[5] if len(cells) > 5 else None
                        if target_cell:
                            report['target_price'] = self._parse_price(target_cell.get_text(strip=True))

                        # Parse Upside (Cell 7)
                        upside_cell = cells[7] if len(cells) > 7 else None
                        if upside_cell:
                            upside_text = upside_cell.get_text(strip=True)
                            upside_match = re.search(r'([\d.]+)', upside_text)
                            if upside_match:
                                try:
                                    report['upside_pct'] = float(upside_match.group(1))
                                    # Check if negative (look for 'negative' class)
                                    if 'negative' in str(upside_cell.get('class', [])):
                                        report['upside_pct'] = -report['upside_pct']
                                except ValueError:
                                    pass

                        # Parse Type (Cell 8)
                        type_cell = cells[8] if len(cells) > 8 else None
                        if type_cell:
                            type_text = type_cell.get_text(strip=True).lower()
                            report['recommendation_type'] = self._parse_recommendation(type_text)

                        # Parse PDF URL (Cell 9)
                        report_cell = cells[9] if len(cells) > 9 else None
                        if report_cell:
                            pdf_link = report_cell.find('a', href=re.compile(r'pdf|document'))
                            if pdf_link:
                                href = pdf_link.get('href', '')
                                if not href.startswith('http'):
                                    href = urljoin(self.BASE_URL, href)
                                report['pdf_url'] = href

                        # Parse cells - structure varies, try common patterns
                        for i, cell in enumerate(cells):
                            cell_text = cell.get_text(strip=True)

                            # Date detection
                            date_match = re.search(r'(\d{1,2}[-/]\w{3}[-/]\d{2,4}|\d{4}[-/]\d{2}[-/]\d{2})', cell_text)
                            if date_match and not report['report_date']:
                                try:
                                    date_str = date_match.group(1)
                                    for fmt in ['%d-%b-%Y', '%d/%b/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                                        try:
                                            report['report_date'] = datetime.strptime(date_str, fmt).date()
                                            break
                                        except ValueError:
                                            continue
                                except Exception:
                                    pass

                            # Author/brokerage (usually longer text)
                            if len(cell_text) > 5 and not cell_text.replace('.', '').replace(',', '').isdigit():
                                if not report['author']:
                                    report['author'] = cell_text[:200]

                            # Price detection
                            price = self._parse_price(cell_text)
                            if price:
                                if not report['ltp_at_report']:
                                    report['ltp_at_report'] = price
                                elif not report['target_price']:
                                    report['target_price'] = price

                            # Recommendation detection
                            rec = self._parse_recommendation(cell_text)
                            if rec != 'UNKNOWN':
                                report['recommendation_type'] = rec

                            # PDF link
                            link = cell.find('a', href=re.compile(r'\.pdf|download|report', re.I))
                            if link and link.get('href'):
                                href = link.get('href')
                                if not href.startswith('http'):
                                    href = urljoin(self.BASE_URL, href)
                                report['pdf_url'] = href

                        # Calculate upside if we have both prices
                        if report['ltp_at_report'] and report['target_price'] and report['ltp_at_report'] > 0:
                            report['upside_pct'] = round(
                                ((report['target_price'] - report['ltp_at_report']) / report['ltp_at_report']) * 100, 2
                            )

                        # Filter by date
                        if report['report_date']:
                            if isinstance(report['report_date'], str):
                                report_dt = datetime.strptime(report['report_date'], '%Y-%m-%d')
                            else:
                                report_dt = datetime.combine(report['report_date'], datetime.min.time())

                            if report_dt < cutoff_date:
                                continue

                            # Download PDF if requested
                            if download_pdfs and report['pdf_url']:
                                date_str = report['report_date'].strftime('%Y-%m-%d') if hasattr(report['report_date'], 'strftime') else str(report['report_date'])
                                local_path = self._download_pdf(
                                    report['pdf_url'],
                                    symbol,
                                    date_str,
                                    report['author']
                                )
                                if local_path:
                                    report['pdf_local_path'] = local_path

                            reports.append(report)

                    except Exception as e:
                        self.logger.warning(f"Error parsing report row: {e}")
                        continue

            self.logger.info(f"Found {len(reports)} analyst reports for {symbol} in last {months_back} months")

            return {
                'success': True,
                'symbol': symbol.upper(),
                'trendlyne_id': trendlyne_id,
                'reports': reports,
                'count': len(reports),
                'months_back': months_back,
                'source_url': current_url
            }

        except Exception as e:
            self.logger.error(f"Error fetching analyst reports for {symbol}: {e}")
            return {
                'success': False,
                'symbol': symbol,
                'error': str(e),
                'reports': []
            }

    def fetch_analyst_data(
        self,
        symbol: str,
        trendlyne_id: int = None,
        months_back: int = 3,
        download_pdfs: bool = True
    ) -> Dict:
        """
        Fetch both price targets and analyst reports for a stock

        Args:
            symbol: Stock symbol (NSE code)
            trendlyne_id: Optional Trendlyne internal ID
            months_back: Number of months to look back
            download_pdfs: Whether to download PDF reports

        Returns:
            dict: Combined price target and reports data
        """
        # Fetch price target first (also gets trendlyne_id)
        price_target = self.fetch_analyst_price_target(symbol, trendlyne_id)

        # Use extracted trendlyne_id for reports
        extracted_id = price_target.get('trendlyne_id') or trendlyne_id

        # Fetch reports
        reports = self.fetch_analyst_reports(
            symbol=symbol,
            trendlyne_id=extracted_id,
            months_back=months_back,
            download_pdfs=download_pdfs
        )

        return {
            'success': price_target.get('success', False) or reports.get('success', False),
            'symbol': symbol.upper(),
            'trendlyne_id': extracted_id,
            'price_target': price_target,
            'reports': reports
        }

    def fetch_data(self, data_type: str, **kwargs) -> Dict:
        """
        Fetch specific type of data

        Args:
            data_type: 'fno', 'market_snapshot', 'forecaster', 'analyst_reports'
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
        elif data_type == 'analyst_reports':
            return self.fetch_analyst_data(**kwargs)
        elif data_type == 'analyst_price_target':
            return self.fetch_analyst_price_target(**kwargs)
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
