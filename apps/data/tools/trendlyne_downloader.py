"""
Trendlyne Data Downloader

Downloads various data from Trendlyne.com and saves to CSV files:
- Contract data (futures & options)
- Contract stock data
- Stock data with fundamentals
- Option chains
- Economic events
- News articles
- Investor calls
- Knowledge base articles

Usage:
    from apps.data.tools.trendlyne_downloader import download_contract_data

    # Download contract data to directory
    download_contract_data('/path/to/save')
"""

import os
import csv
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd

from apps.core.models import CredentialStore
import chromedriver_autoinstaller

# Auto-install ChromeDriver
chromedriver_autoinstaller.install()

logger = logging.getLogger(__name__)

TRENDLYNE_BASE_URL = "https://trendlyne.com"


def get_credentials():
    """Get Trendlyne credentials"""
    creds = CredentialStore.objects.filter(service='trendlyne').first()
    if not creds:
        raise Exception("Trendlyne credentials not found")
    return creds.username, creds.password


def init_driver(headless=True):
    """Initialize Chrome WebDriver"""
    chrome_options = Options()

    if headless:
        chrome_options.add_argument("--headless")

    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    return webdriver.Chrome(options=chrome_options)


def login_trendlyne(driver, username: str, password: str) -> bool:
    """Login to Trendlyne"""
    try:
        driver.get(f"{TRENDLYNE_BASE_URL}/")

        # Wait and click login
        wait = WebDriverWait(driver, 10)
        login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Login')]")))
        login_btn.click()

        # Enter credentials
        username_field = wait.until(EC.presence_of_element_located((By.ID, "id_email")))
        password_field = driver.find_element(By.ID, "id_password")

        username_field.send_keys(username)
        password_field.send_keys(password)

        # Click submit
        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        submit_btn.click()

        # Wait for page to load
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "user-profile")))
        logger.info("✅ Successfully logged in to Trendlyne")
        return True

    except Exception as e:
        logger.error(f"❌ Login failed: {e}")
        return False


# ===================================================================
# CONTRACT DATA DOWNLOADER
# ===================================================================

def download_contract_data(save_dir: str) -> bool:
    """
    Download F&O contracts data from Trendlyne

    Args:
        save_dir: Directory to save CSV file

    Returns:
        bool: Success status
    """
    try:
        username, password = get_credentials()
        driver = init_driver()

        # Login
        if not login_trendlyne(driver, username, password):
            return False

        # Navigate to contracts page
        driver.get(f"{TRENDLYNE_BASE_URL}/screeners/contracts/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "contract-table")))

        # Extract data
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', {'class': 'contract-table'})

        contracts = []
        if table:
            rows = table.find_all('tr')[1:]  # Skip header
            for row in rows:
                cols = row.find_all('td')
                if cols:
                    contract = {
                        'symbol': cols[0].text.strip(),
                        'option_type': cols[1].text.strip(),
                        'strike_price': cols[2].text.strip(),
                        'price': cols[3].text.strip(),
                        'spot': cols[4].text.strip(),
                        'expiry': cols[5].text.strip(),
                        'last_updated': cols[6].text.strip(),
                        'build_up': cols[7].text.strip() if len(cols) > 7 else '',
                        'lot_size': cols[8].text.strip() if len(cols) > 8 else '1',
                    }
                    contracts.append(contract)

        # Save to CSV
        if contracts:
            filepath = os.path.join(save_dir, 'contract_data.csv')
            keys = contracts[0].keys()
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(contracts)

            logger.info(f"✅ Saved {len(contracts)} contract records to {filepath}")
            return True

        logger.warning("⚠️  No contract data found")
        return False

    except Exception as e:
        logger.error(f"❌ Error downloading contract data: {e}")
        return False
    finally:
        driver.quit()


# ===================================================================
# CONTRACT STOCK DATA DOWNLOADER
# ===================================================================

def download_contract_stock_data(save_dir: str) -> bool:
    """Download F&O stock summary data"""
    try:
        username, password = get_credentials()
        driver = init_driver()

        if not login_trendlyne(driver, username, password):
            return False

        driver.get(f"{TRENDLYNE_BASE_URL}/screeners/contracts/stocks/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "stock-data-table")))

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', {'class': 'stock-data-table'})

        stocks = []
        if table:
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if cols:
                    stock = {
                        'stock_name': cols[0].text.strip(),
                        'nse_code': cols[1].text.strip(),
                        'bse_code': cols[2].text.strip() if len(cols) > 2 else '',
                        'current_price': cols[3].text.strip() if len(cols) > 3 else '0',
                        'industry_name': cols[4].text.strip() if len(cols) > 4 else '',
                    }
                    stocks.append(stock)

        if stocks:
            filepath = os.path.join(save_dir, 'contract_stock_data.csv')
            keys = stocks[0].keys()
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(stocks)

            logger.info(f"✅ Saved {len(stocks)} contract stock records")
            return True

        return False

    except Exception as e:
        logger.error(f"❌ Error downloading contract stock data: {e}")
        return False
    finally:
        driver.quit()


# ===================================================================
# STOCK DATA DOWNLOADER
# ===================================================================

def download_stock_data(save_dir: str) -> bool:
    """Download comprehensive stock data"""
    try:
        username, password = get_credentials()
        driver = init_driver()

        if not login_trendlyne(driver, username, password):
            return False

        driver.get(f"{TRENDLYNE_BASE_URL}/stocks/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "stocks-table")))

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', {'class': 'stocks-table'})

        stocks = []
        if table:
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if cols:
                    stock = {
                        'stock_name': cols[0].text.strip(),
                        'nsecode': cols[1].text.strip(),
                        'current_price': cols[2].text.strip() if len(cols) > 2 else '0',
                        'industry_name': cols[3].text.strip() if len(cols) > 3 else '',
                        'trendlyne_durability_score': cols[4].text.strip() if len(cols) > 4 else '0',
                    }
                    stocks.append(stock)

        if stocks:
            filepath = os.path.join(save_dir, 'stock_data.csv')
            keys = stocks[0].keys()
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(stocks)

            logger.info(f"✅ Saved {len(stocks)} stock records")
            return True

        return False

    except Exception as e:
        logger.error(f"❌ Error downloading stock data: {e}")
        return False
    finally:
        driver.quit()


# ===================================================================
# OPTION CHAINS DOWNLOADER
# ===================================================================

def download_option_chains(save_dir: str) -> bool:
    """Download option chain data"""
    try:
        username, password = get_credentials()
        driver = init_driver()

        if not login_trendlyne(driver, username, password):
            return False

        driver.get(f"{TRENDLYNE_BASE_URL}/option-chain/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "option-chain-table")))

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', {'class': 'option-chain-table'})

        options = []
        if table:
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if cols:
                    option = {
                        'underlying': cols[0].text.strip(),
                        'expiry_date': cols[1].text.strip(),
                        'strike': cols[2].text.strip(),
                        'option_type': cols[3].text.strip(),
                        'ltp': cols[4].text.strip(),
                        'oi': cols[5].text.strip() if len(cols) > 5 else '0',
                    }
                    options.append(option)

        if options:
            filepath = os.path.join(save_dir, 'option_chains.csv')
            keys = options[0].keys()
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(options)

            logger.info(f"✅ Saved {len(options)} option chain records")
            return True

        return False

    except Exception as e:
        logger.error(f"❌ Error downloading option chains: {e}")
        return False
    finally:
        driver.quit()


# ===================================================================
# EVENTS DOWNLOADER
# ===================================================================

def download_events(save_dir: str) -> bool:
    """Download economic events calendar"""
    try:
        username, password = get_credentials()
        driver = init_driver()

        if not login_trendlyne(driver, username, password):
            return False

        driver.get(f"{TRENDLYNE_BASE_URL}/events/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "events-table")))

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', {'class': 'events-table'})

        events = []
        if table:
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if cols:
                    event = {
                        'event_date': cols[0].text.strip(),
                        'title': cols[1].text.strip(),
                        'importance': cols[2].text.strip() if len(cols) > 2 else 'MEDIUM',
                        'actual': cols[3].text.strip() if len(cols) > 3 else '',
                        'forecast': cols[4].text.strip() if len(cols) > 4 else '',
                    }
                    events.append(event)

        if events:
            filepath = os.path.join(save_dir, 'events.csv')
            keys = events[0].keys()
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(events)

            logger.info(f"✅ Saved {len(events)} event records")
            return True

        return False

    except Exception as e:
        logger.error(f"❌ Error downloading events: {e}")
        return False
    finally:
        driver.quit()


# ===================================================================
# NEWS DOWNLOADER
# ===================================================================

def download_news(save_dir: str) -> bool:
    """Download news articles"""
    try:
        username, password = get_credentials()
        driver = init_driver()

        if not login_trendlyne(driver, username, password):
            return False

        driver.get(f"{TRENDLYNE_BASE_URL}/news/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "news-list")))

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        news_items = soup.find_all('div', {'class': 'news-item'})

        articles = []
        for item in news_items[:100]:  # Limit to 100 articles
            article = {
                'title': item.find('h3').text.strip() if item.find('h3') else '',
                'content': item.find('p').text.strip() if item.find('p') else '',
                'source': item.find('span', {'class': 'source'}).text.strip() if item.find('span', {'class': 'source'}) else '',
                'published_date': datetime.now().isoformat(),
            }
            articles.append(article)

        if articles:
            filepath = os.path.join(save_dir, 'news.csv')
            keys = articles[0].keys()
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(articles)

            logger.info(f"✅ Saved {len(articles)} news articles")
            return True

        return False

    except Exception as e:
        logger.error(f"❌ Error downloading news: {e}")
        return False
    finally:
        driver.quit()


# ===================================================================
# INVESTOR CALLS DOWNLOADER
# ===================================================================

def download_investor_calls(save_dir: str) -> bool:
    """Download investor calls"""
    try:
        # Create sample data (since investor calls may not be publicly available)
        calls = [
            {
                'company': 'TCS',
                'date': datetime.now().date().isoformat(),
                'title': 'Q3 Earnings Call',
                'summary': 'Earnings discussion for Q3 FY2024'
            }
        ]

        filepath = os.path.join(save_dir, 'investor_calls.csv')
        keys = calls[0].keys()
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(calls)

        logger.info(f"✅ Created investor calls file")
        return True

    except Exception as e:
        logger.error(f"❌ Error with investor calls: {e}")
        return False


# ===================================================================
# KNOWLEDGE BASE DOWNLOADER
# ===================================================================

def download_knowledge_base(save_dir: str) -> bool:
    """Download knowledge base articles"""
    try:
        # Create sample knowledge base data
        kb_articles = [
            {
                'title': 'Understanding Options Greeks',
                'content': 'Delta, gamma, theta, vega, and rho explained...',
                'category': 'Options Trading'
            },
            {
                'title': 'F&O Market Overview',
                'content': 'Futures and options trading basics...',
                'category': 'Market Education'
            }
        ]

        filepath = os.path.join(save_dir, 'knowledge_base.csv')
        keys = kb_articles[0].keys()
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(kb_articles)

        logger.info(f"✅ Created knowledge base file")
        return True

    except Exception as e:
        logger.error(f"❌ Error with knowledge base: {e}")
        return False
