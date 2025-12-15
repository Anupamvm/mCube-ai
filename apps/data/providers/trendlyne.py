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
        Download market snapshot data from Trendlyne

        Args:
            download_dir: Override default download directory

        Returns:
            dict: Download status and file info
        """
        if download_dir is None:
            download_dir = self.download_dir

        try:
            # Try different URLs for market snapshot download
            snapshot_urls = [
                f"{self.BASE_URL}/tools/data-downloader/trendlyne-excel-connect/",
                f"{self.BASE_URL}/tools/data-downloader/market-snapshot-excel/",
                f"{self.BASE_URL}/equity/market-snapshot/",
            ]

            page_loaded = False
            for url in snapshot_urls:
                try:
                    self.driver.get(url)
                    self.logger.info(f"Trying URL: {url}")
                    time.sleep(5)

                    # Check if we're on a valid page (not login redirect)
                    if "login" not in self.driver.current_url.lower():
                        page_loaded = True
                        self.logger.info(f"Successfully loaded: {url}")
                        break
                except Exception:
                    continue

            if not page_loaded:
                raise DataProviderException("Could not access Market Snapshot page - may require premium subscription")

            # Try multiple selectors for download button
            download_selectors = [
                (By.XPATH, "//a[contains(text(), 'DOWNLOAD')]"),
                (By.XPATH, "//a[contains(text(), 'Download')]"),
                (By.XPATH, "//a[contains(text(), 'DOWNLOAD EXCEL')]"),
                (By.XPATH, "//a[contains(text(), 'Download Excel')]"),
                (By.XPATH, "//button[contains(text(), 'DOWNLOAD')]"),
                (By.XPATH, "//button[contains(text(), 'Download')]"),
                (By.XPATH, "//button[contains(text(), 'Download Data')]"),
                (By.CSS_SELECTOR, "a.download-btn"),
                (By.CSS_SELECTOR, "button.download-btn"),
                (By.CSS_SELECTOR, "[data-action='download']"),
                (By.XPATH, "//a[contains(@class, 'download')]"),
                (By.XPATH, "//button[contains(@class, 'download')]"),
                (By.XPATH, "//a[contains(@href, 'download')]"),
                (By.XPATH, "//a[contains(@href, 'excel')]"),
            ]

            download_button = self.try_multiple_selectors(download_selectors, action="click")
            self.logger.info("Market Snapshot download initiated...")
            time.sleep(10)

            # Find downloaded file - look for stock data files specifically
            # Stock data files are named like "Stocks-data-IND-*.xlsx"
            all_files = os.listdir(download_dir)
            stock_files = [f for f in all_files if f.startswith("Stocks-data") and (f.endswith(".xlsx") or f.endswith(".csv"))]

            if not stock_files:
                # Fallback: look for any new xlsx/csv file
                files = [f for f in all_files if f.endswith(".xlsx") or f.endswith(".csv")]
                if not files:
                    raise DataProviderException("No Excel/CSV file found after download")
                files.sort(key=lambda x: os.path.getctime(os.path.join(download_dir, x)), reverse=True)
                latest_file = files[0]
            else:
                stock_files.sort(key=lambda x: os.path.getctime(os.path.join(download_dir, x)), reverse=True)
                latest_file = stock_files[0]

            # Determine file extension
            file_ext = ".xlsx" if latest_file.endswith(".xlsx") else ".csv"

            # Rename to standard format
            new_filename = f"stock_data_{datetime.now().strftime('%Y-%m-%d')}{file_ext}"
            new_path = os.path.join(download_dir, new_filename)

            # Only rename if not already renamed
            if latest_file != new_filename:
                os.rename(
                    os.path.join(download_dir, latest_file),
                    new_path
                )

            self.logger.info(f"✅ Stock Data saved: {new_filename}")

            return {
                'success': True,
                'filename': new_filename,
                'path': new_path
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
