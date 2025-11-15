"""
Trendlyne data scraping module for mCube Trading System

This module handles automated web scraping of stock data from Trendlyne.com
including analyst consensus, F&O data, and market snapshots.
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

from apps.core.models import CredentialStore
import chromedriver_autoinstaller

# Auto-install chromedriver
chromedriver_autoinstaller.install()

# Trendlyne Configuration
TRENDLYNE_URL = "https://trendlyne.com/features/"


def get_trendlyne_credentials():
    """Retrieve Trendlyne credentials from database"""
    creds = CredentialStore.objects.filter(service='trendlyne').first()
    if not creds:
        raise Exception("No Trendlyne credentials found in DB. Please add credentials via Django admin.")
    return creds.username, creds.password


def init_driver_with_download(download_dir_path):
    """
    Initialize Chrome WebDriver with download configuration

    Args:
        download_dir_path: Directory path for automatic downloads

    Returns:
        Configured Chrome WebDriver instance
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

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def login_to_trendlyne(driver):
    """
    Login to Trendlyne using stored credentials

    Args:
        driver: Selenium WebDriver instance

    Returns:
        bool: True if login successful, False otherwise
    """
    username, password = get_trendlyne_credentials()

    driver.get(TRENDLYNE_URL)
    time.sleep(2)

    try:
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
            print("✅ Trendlyne login successful!")
            return True
        else:
            print("❌ Trendlyne login may have failed.")
            return False
    except Exception as e:
        print(f"❌ Error during login: {e}")
        return False


def getFnOData(driver, download_dir="trendlynedata"):
    """
    Download Futures & Options data from Trendlyne

    Args:
        driver: Selenium WebDriver instance
        download_dir: Directory to save downloaded files
    """
    driver.get("https://trendlyne.com/futures-options/contracts-excel-download/")
    print("🔄 Navigated to FnO data downloader...")
    time.sleep(3)

    try:
        download_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Download')]"))
        )
        download_button.click()
        print("📥 FnO download initiated...")
        time.sleep(10)

        files = [f for f in os.listdir(download_dir) if f.endswith(".csv")]
        if not files:
            print("❌ No CSV found.")
            return

        files.sort(key=lambda x: os.path.getctime(os.path.join(download_dir, x)), reverse=True)
        latest_file = files[0]

        new_filename = f"fno_data_{datetime.now().strftime('%Y-%m-%d')}.csv"
        os.rename(os.path.join(download_dir, latest_file), os.path.join(download_dir, new_filename))
        print(f"✅ Saved: {new_filename}")
    except Exception as e:
        print(f"⚠️ Error during FnO download: {e}")


def getMarketSnapshotData(driver, download_dir="trendlynedata"):
    """
    Download market snapshot data from Trendlyne

    Args:
        driver: Selenium WebDriver instance
        download_dir: Directory to save downloaded files
    """
    driver.get("https://trendlyne.com/tools/data-downloader/market-snapshot-excel/")
    print("🔄 Navigated to Market Snapshot Downloader...")
    time.sleep(5)

    try:
        download_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'DOWNLOAD')]"))
        )
        download_button.click()
        print("📥 Market Snapshot download initiated...")
        time.sleep(10)

        files = [f for f in os.listdir(download_dir) if f.endswith(".csv")]
        if not files:
            print("❌ No CSV found.")
            return

        files.sort(key=lambda x: os.path.getctime(os.path.join(download_dir, x)), reverse=True)
        latest_file = files[0]

        new_filename = f"market_snapshot_{datetime.now().strftime('%Y-%m-%d')}.csv"
        os.rename(os.path.join(download_dir, latest_file), os.path.join(download_dir, new_filename))
        print(f"✅ Saved: {new_filename}")
    except Exception as e:
        print(f"⚠️ Error during Market Snapshot download: {e}")


def getTrendlyneForecasterData(driver):
    """
    Scrape analyst consensus and forecaster data from 21 different Trendlyne pages

    This function scrapes:
    - Analyst bullishness/bearishness
    - Earnings surprises (beat/missed estimates)
    - Forward growth projections
    - Analyst upgrades
    - Other consensus metrics

    Args:
        driver: Selenium WebDriver instance
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

    # Create output directory in the app's data directory
    from django.conf import settings
    output_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'trendlynedata')
    os.makedirs(output_dir, exist_ok=True)

    for label, url in urls.items():
        print(f"📊 Fetching: {label}")
        driver.get(url)
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, 'html5lib')
        table = soup.find("table", class_="trendlyne-screener-table")
        if not table:
            print(f"❌ Table not found on {label}")
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
        print(f"✅ Saved {file_path}")


def getTrendlyneAnalystSummary(driver, url="https://trendlyne.com/equity/consensus-estimates/533/HDFCBANK/hdfc-bank-ltd/"):
    """
    Scrape analyst summary for a specific stock

    Args:
        driver: Selenium WebDriver instance
        url: URL of the stock's consensus page on Trendlyne
    """
    from django.conf import settings

    driver.get(url)
    time.sleep(5)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    stockname = url.rstrip("/").split("/")[-1].replace("-", "_")
    base_folder = os.path.join(settings.BASE_DIR, 'apps', 'data', 'trendlynedata', stockname)
    os.makedirs(base_folder, exist_ok=True)
    filepath = os.path.join(base_folder, f"{stockname}_analysts_summary.csv")

    data = {"Stock": stockname}

    try:
        share_card = soup.find("h3", string=re.compile("Share price target", re.I)).find_parent("div", class_="consensus-card")
        data["Current Price"] = share_card.find("div", class_="marker-1").find("div", class_="fw500 price").text.strip()
        data["Avg Estimate"] = share_card.find("div", class_="marker-color-2").find("div", class_="fw500 price").text.strip()
        data["Low Estimate"] = share_card.find("div", class_="low-estimate").find("div", class_="fw500 price").text.strip()
        data["High Estimate"] = share_card.find("div", class_="high-estimate").find("div", class_="fw500 rightAlgn price").text.strip()
        data["Upside %"] = re.search(r"upside of (.*?)\%?", share_card.text).group(1).strip() + "%"
    except Exception as e:
        print("❌ Share price forecast extraction error:", e)

    try:
        eps_card = soup.find("h3", string=re.compile("EPS forecast", re.I)).find_parent("div", class_="consensus-card")
        data["EPS Insight"] = eps_card.find("h4", class_="consensus-heading").text.strip()
    except Exception as e:
        print("❌ EPS insight extraction error:", e)

    try:
        rec_card = soup.find("h3", string=re.compile("Consensus Recommendation", re.I)).find_parent("div", class_="consensus-card")
        analyst_text = rec_card.find("div", class_="subtitle").text.strip()
        rec_text = rec_card.find("div", class_="insight-title").text.strip()
        data["Analyst Count"] = re.search(r"\d+", analyst_text).group()
        data["Recommendation"] = rec_text
    except Exception as e:
        print("❌ Recommendation extraction error:", e)

    df = pd.DataFrame([{"Variable": k, "Value": v} for k, v in data.items()])
    df.to_csv(filepath, index=False)
    print(f"✅ Saved analyst summary to: {filepath}")


def getReportsFrom(driver, url, download_dir="trendlynedata/tmp_downloads"):
    """
    Download broker research reports for a specific stock

    Args:
        driver: Selenium WebDriver instance
        url: URL of the stock's research reports page
        download_dir: Directory for temporary downloads
    """
    from django.conf import settings

    os.makedirs(download_dir, exist_ok=True)
    print(f"✅ Chrome download path set to: {download_dir}")

    driver.get(url)
    time.sleep(3)

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    table = soup.find("table", {"id": "brokerTable"})
    if not table:
        print("❌ Broker reports table not found.")
        return

    stock_slug = url.rstrip("/").split("/")[-1]
    stock_folder = stock_slug.replace("-", "_").lower()
    base_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'trendlynedata', stock_folder, 'reports')
    os.makedirs(base_dir, exist_ok=True)
    summary_csv_path = os.path.join(settings.BASE_DIR, 'apps', 'data', 'trendlynedata', stock_folder, 'reportssummary.csv')

    headers = [
        "Date", "Stock", "Author", "LTP", "Target",
        "Price at Reco (Change)", "Upside (%)", "Type", "PDF Link", "Post Link"
    ]
    rows_data = []

    tbody = table.find("tbody", {"id": "allreportsbody"})
    rows = tbody.find_all("tr", {"role": "row"})

    cutoff_date = datetime.now() - timedelta(days=183)

    for row in rows:
        cols = row.find_all("td")
        if not cols or len(cols) < 10:
            continue

        date_str = cols[1].text.strip()
        try:
            report_date = datetime.strptime(date_str, "%d %b %Y")
        except ValueError:
            continue

        if report_date < cutoff_date:
            continue

        stock = cols[2].text.strip()
        author = cols[3].text.strip()
        ltp = cols[4].text.strip()
        target = cols[5].text.strip()
        reco_price = cols[6].text.strip().replace("\n", " ")
        upside = cols[7].text.strip()
        rating = cols[8].text.strip()

        report_links = cols[9].find_all("a")
        pdf_link = ""
        post_link = ""
        for link in report_links:
            label = link.text.strip().lower()
            href = link.get("href", "")
            if "pdf" in label and "loginmodal" not in href:
                pdf_link = urljoin("https://trendlyne.com", href)
            elif "post" in label:
                post_link = urljoin("https://trendlyne.com", href)

        rows_data.append([
            date_str, stock, author, ltp, target, reco_price, upside, rating, pdf_link, post_link
        ])

    with open(summary_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows_data)

    print(f"✅ Downloaded {len(rows_data)} reports for {stock_folder}")


def get_all_trendlyne_data():
    """
    Main orchestration function to fetch all Trendlyne data

    This function:
    1. Creates download directory
    2. Initializes Chrome driver
    3. Logs in to Trendlyne
    4. Downloads F&O data
    5. Downloads market snapshot
    6. Scrapes forecaster data (21 pages)

    Returns:
        bool: True if successful, False otherwise
    """
    from django.conf import settings

    base_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata')
    os.makedirs(base_dir, exist_ok=True)

    driver = init_driver_with_download(base_dir)

    try:
        if not login_to_trendlyne(driver):
            print("❌ Login failed, skipping data fetch.")
            return False

        getFnOData(driver, download_dir=base_dir)
        getMarketSnapshotData(driver, download_dir=base_dir)
        getTrendlyneForecasterData(driver)

        print("✅ All Trendlyne data fetched and saved.")
        return True

    except Exception as e:
        print(f"❌ Error during data fetch: {e}")
        return False
    finally:
        driver.quit()
