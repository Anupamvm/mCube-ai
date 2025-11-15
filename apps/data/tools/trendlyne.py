"""
Trendlyne Data Scraping Tool

This module provides functions to scrape various data from Trendlyne.com:
- F&O Contracts data
- Market Snapshot data
- Forecaster data (21 different screeners)
- Analyst summaries
- Broker reports

Usage:
    from apps.data.tools.trendlyne import get_all_trendlyne_data
    success = get_all_trendlyne_data()
"""

import os
import time
import csv
import re
import pandas as pd
from datetime import datetime, timedelta
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from django.conf import settings
import logging

from apps.core.models import CredentialStore
import chromedriver_autoinstaller

# Auto-install ChromeDriver
chromedriver_autoinstaller.install()

logger = logging.getLogger(__name__)

# Trendlyne Configuration
TRENDLYNE_URL = "https://trendlyne.com/features/"


# ===================================================================
# CREDENTIAL ACCESS
# ===================================================================
def get_trendlyne_credentials():
    """
    Retrieve Trendlyne credentials from database

    Returns:
        tuple: (username, password)

    Raises:
        Exception: If no credentials found
    """
    creds = CredentialStore.objects.filter(service='trendlyne').first()
    if not creds:
        raise Exception("No Trendlyne credentials found in CredentialStore")
    return creds.username, creds.password


# ===================================================================
# CHROME DRIVER INITIALIZATION
# ===================================================================
def init_driver_with_download(download_dir_path):
    """
    Initialize Chrome WebDriver with download preferences

    Args:
        download_dir_path (str): Absolute path for downloads

    Returns:
        webdriver.Chrome: Configured Chrome driver instance
    """
    abs_download_path = os.path.abspath(download_dir_path)
    os.makedirs(abs_download_path, exist_ok=True)

    chrome_options = Options()
    prefs = {
        "download.default_directory": abs_download_path,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
        "safebrowsing.enabled": True,
        "download.directory_upgrade": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument("--start-maximized")

    # Headless mode for production
    if getattr(settings, 'TRENDLYNE_HEADLESS', False):
        chrome_options.add_argument("--headless")

    driver = webdriver.Chrome(options=chrome_options)
    logger.info(f"Chrome driver initialized with download path: {abs_download_path}")
    return driver


# ===================================================================
# LOGIN
# ===================================================================
def login_to_trendlyne(driver):
    """
    Login to Trendlyne website

    Args:
        driver: Selenium WebDriver instance

    Returns:
        bool: True if login successful, False otherwise
    """
    try:
        username, password = get_trendlyne_credentials()

        driver.get(TRENDLYNE_URL)
        time.sleep(2)

        login_button = driver.find_element(By.ID, "login-signup-btn")
        login_button.click()
        time.sleep(2)

        email_field = driver.find_element(By.ID, "id_login")
        password_field = driver.find_element(By.ID, "id_password")

        email_field.send_keys(username)
        password_field.send_keys(password)
        password_field.send_keys(Keys.RETURN)
        time.sleep(5)

        if "logout" in driver.page_source.lower():
            logger.info("✅ Trendlyne login successful")
            return True
        else:
            logger.error("❌ Trendlyne login may have failed")
            return False
    except Exception as e:
        logger.error(f"Error during Trendlyne login: {e}")
        return False


# ===================================================================
# F&O DATA DOWNLOAD
# ===================================================================
def getFnOData(driver, download_dir="tldata"):
    """
    Download F&O Contracts data from Trendlyne

    Args:
        driver: Selenium WebDriver instance
        download_dir (str): Directory to save downloaded file

    Returns:
        str: Path to downloaded file, None if failed
    """
    try:
        driver.get("https://trendlyne.com/futures-options/contracts-excel-download/")
        logger.info("🔄 Navigated to FnO data downloader...")
        time.sleep(3)

        download_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Download')]"))
        )
        download_button.click()
        logger.info("📥 FnO download initiated...")
        time.sleep(10)

        # Find the latest downloaded CSV file
        files = [f for f in os.listdir(download_dir) if f.endswith(".csv")]
        if not files:
            logger.error("❌ No CSV found in download directory")
            return None

        files.sort(key=lambda x: os.path.getctime(os.path.join(download_dir, x)), reverse=True)
        latest_file = files[0]

        new_filename = f"fno_data_{datetime.now().strftime('%Y-%m-%d')}.csv"
        old_path = os.path.join(download_dir, latest_file)
        new_path = os.path.join(download_dir, new_filename)
        os.rename(old_path, new_path)

        logger.info(f"✅ F&O data saved: {new_filename}")
        return new_path
    except Exception as e:
        logger.error(f"⚠️ Error during FnO download: {e}")
        return None


# ===================================================================
# MARKET SNAPSHOT DOWNLOAD
# ===================================================================
def getMarketSnapshotData(driver, download_dir="tldata"):
    """
    Download Market Snapshot data from Trendlyne

    Args:
        driver: Selenium WebDriver instance
        download_dir (str): Directory to save downloaded file

    Returns:
        str: Path to downloaded file, None if failed
    """
    try:
        driver.get("https://trendlyne.com/tools/data-downloader/market-snapshot-excel/")
        logger.info("🔄 Navigated to Market Snapshot Downloader...")
        time.sleep(5)

        download_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'DOWNLOAD')]"))
        )
        download_button.click()
        logger.info("📥 Market Snapshot download initiated...")
        time.sleep(10)

        files = [f for f in os.listdir(download_dir) if f.endswith(".csv")]
        if not files:
            logger.error("❌ No CSV found in download directory")
            return None

        files.sort(key=lambda x: os.path.getctime(os.path.join(download_dir, x)), reverse=True)
        latest_file = files[0]

        new_filename = f"market_snapshot_{datetime.now().strftime('%Y-%m-%d')}.csv"
        old_path = os.path.join(download_dir, latest_file)
        new_path = os.path.join(download_dir, new_filename)
        os.rename(old_path, new_path)

        logger.info(f"✅ Market Snapshot data saved: {new_filename}")
        return new_path
    except Exception as e:
        logger.error(f"⚠️ Error during Market Snapshot download: {e}")
        return None


# ===================================================================
# FORECASTER DATA SCRAPING
# ===================================================================
def getTrendlyneForecasterData(driver, output_dir="tldata/forecaster"):
    """
    Scrape Forecaster data from 21 different Trendlyne screeners

    Args:
        driver: Selenium WebDriver instance
        output_dir (str): Directory to save scraped data

    Returns:
        int: Number of successfully scraped pages
    """
    urls = {
        "High Bullishness": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/consensus_highest_bullish-above-0/",
        "High Bearishness": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/consensus_highest_bearish-above-0/",
        "Highest Forward 12Mth Upside %": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/consensus_highest_upside-above-0/",
        "Highest Forward Annual EPS Growth": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/eps_annual_growth-above-0/",
        "Lowest Forward Annual EPS Growth": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/eps_annual_growth-below-0/",
        "Highest Forward Annual Revenue Growth": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/revenue_annual_growth-above-0/",
        "Highest 3Mth Analyst Upgrades": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/consensus_analyst_upgrade-above-0/",
        "Highest Forward Annual Capex Growth": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/consensus_highest_capex-above-0/",
        "Highest Dividend Yield": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/consensus_highest_dps-above-0/",
        "Beat Annual Revenue Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/revenue-annual-surprise-above-0/",
        "Missed Annual Revenue Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/revenue-annual-surprise-below-0/",
        "Beat Quarter Revenue Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/revenue-quarter-surprise-above-0/",
        "Missed Quarter Revenue Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/revenue-quarter-surprise-below-0/",
        "Beat Annual Net Income Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/net-income-annual-surprise-above-0/",
        "Missed Annual Net Income Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/net-income-annual-surprise-below-0/",
        "Beat Quarter Net Income Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/net-income-quarter-surprise-above-0/",
        "Missed Quarter Net Income Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/net-income-quarter-surprise-below-0/",
        "Beat Annual EPS Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/eps-annual-surprise-above-0/",
        "Missed Annual EPS Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/eps-annual-surprise-below-0/",
        "Beat Quarter EPS Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/eps-quarter-surprise-above-0/",
        "Missed Quarter EPS Estimates": "https://trendlyne.com/equity/consensus-estimates/dashboard/forecaster/eps-quarter-surprise-below-0/"
    }

    os.makedirs(output_dir, exist_ok=True)
    success_count = 0

    for label, url in urls.items():
        try:
            logger.info(f"Fetching Forecaster: {label}")
            driver.get(url)
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            table = soup.find("table", class_="trendlyne-screener-table")
            if not table:
                logger.warning(f"❌ Table not found on {label}")
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
            logger.info(f"✅ Saved {file_path}")
            success_count += 1
        except Exception as e:
            logger.error(f"Error scraping {label}: {e}")

    logger.info(f"Forecaster data: {success_count}/{len(urls)} pages scraped successfully")
    return success_count


# ===================================================================
# ANALYST SUMMARY SCRAPING
# ===================================================================
def getTrendlyneAnalystSummary(driver, url, output_dir="tldata/analysts"):
    """
    Scrape analyst summary for a specific stock

    Args:
        driver: Selenium WebDriver instance
        url (str): Trendlyne stock consensus URL
        output_dir (str): Directory to save data

    Returns:
        str: Path to saved file, None if failed
    """
    try:
        driver.get(url)
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        stockname = url.rstrip("/").split("/")[-1].replace("-", "_")
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f"{stockname}_analysts_summary.csv")

        data = {"Stock": stockname}

        # Share price target
        try:
            share_card = soup.find("h3", string=re.compile("Share price target", re.I)).find_parent("div", class_="consensus-card")
            data["Current Price"] = share_card.find("div", class_="marker-1").find("div", class_="fw500 price").text.strip()
            data["Avg Estimate"] = share_card.find("div", class_="marker-color-2").find("div", class_="fw500 price").text.strip()
            data["Low Estimate"] = share_card.find("div", class_="low-estimate").find("div", class_="fw500 price").text.strip()
            data["High Estimate"] = share_card.find("div", class_="high-estimate").find("div", class_="fw500 rightAlgn price").text.strip()
            data["Upside %"] = re.search(r"upside of (.*?)\%?", share_card.text).group(1).strip() + "%"
        except Exception as e:
            logger.warning(f"Share price forecast extraction error: {e}")

        # EPS forecast
        try:
            eps_card = soup.find("h3", string=re.compile("EPS forecast", re.I)).find_parent("div", class_="consensus-card")
            data["EPS Insight"] = eps_card.find("h4", class_="consensus-heading").text.strip()
        except Exception as e:
            logger.warning(f"EPS insight extraction error: {e}")

        # Consensus recommendation
        try:
            rec_card = soup.find("h3", string=re.compile("Consensus Recommendation", re.I)).find_parent("div", class_="consensus-card")
            analyst_text = rec_card.find("div", class_="subtitle").text.strip()
            rec_text = rec_card.find("div", class_="insight-title").text.strip()
            data["Analyst Count"] = re.search(r"\d+", analyst_text).group()
            data["Recommendation"] = rec_text
        except Exception as e:
            logger.warning(f"Recommendation extraction error: {e}")

        df = pd.DataFrame([{"Variable": k, "Value": v} for k, v in data.items()])
        df.to_csv(filepath, index=False)
        logger.info(f"✅ Saved analyst summary to: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Error scraping analyst summary: {e}")
        return None


# ===================================================================
# MAIN FUNCTION
# ===================================================================
def get_all_trendlyne_data(download_dir=None):
    """
    Main function to fetch all Trendlyne data

    Args:
        download_dir (str, optional): Base directory for downloads
                                     Defaults to apps/data/tldata/

    Returns:
        dict: Summary of downloaded data with success/failure status
    """
    if download_dir is None:
        download_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata')

    os.makedirs(download_dir, exist_ok=True)

    driver = init_driver_with_download(download_dir)
    results = {
        'login': False,
        'fno_data': None,
        'market_snapshot': None,
        'forecaster_pages': 0,
        'errors': []
    }

    try:
        # Login
        if not login_to_trendlyne(driver):
            results['errors'].append("Login failed")
            logger.error("❌ Login failed, skipping data fetch.")
            return results
        results['login'] = True

        # Download F&O Data
        fno_path = getFnOData(driver, download_dir=download_dir)
        results['fno_data'] = fno_path

        # Download Market Snapshot
        snapshot_path = getMarketSnapshotData(driver, download_dir=download_dir)
        results['market_snapshot'] = snapshot_path

        # Scrape Forecaster Data
        forecaster_dir = os.path.join(download_dir, 'forecaster')
        forecaster_count = getTrendlyneForecasterData(driver, output_dir=forecaster_dir)
        results['forecaster_pages'] = forecaster_count

        logger.info("✅ All Trendlyne data fetched and saved.")
        return results

    except Exception as e:
        logger.error(f"Error in get_all_trendlyne_data: {e}")
        results['errors'].append(str(e))
        return results
    finally:
        driver.quit()
        logger.info("Chrome driver closed.")
