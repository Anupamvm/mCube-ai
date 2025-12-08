"""
ICICI Breeze Expiry - Expiry Date Fetching

This module provides functions to fetch and calculate expiry dates.
"""

import logging
import requests
import json
import calendar
import time
from datetime import datetime, timedelta, date
from typing import List

logger = logging.getLogger(__name__)

NSE_BASE = "https://www.nseindia.com"
NSE_OC_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"


def get_all_nifty_expiry_dates(max_expiries: int = 10, timeout: int = 15) -> List[str]:
    """
    Fetch all available NIFTY options expiry dates from NSE.

    IMPORTANT: This function ONLY fetches the LIST OF EXPIRY DATES from NSE.
    The actual option chain data (LTP, OI, volume, etc.) is ALWAYS fetched from Breeze API.

    This fetches real contract expiry dates which properly handle holidays.
    NSE adjusts expiry dates when Thursday is a trading holiday.

    NOTE: NSE may block automated API access (403 errors). If this fails,
    the caller should fallback to generating Thursday dates.

    Args:
        max_expiries: Maximum number of expiries to return (default 10)
        timeout: Per-request timeout in seconds

    Returns:
        List[str]: List of expiry dates in 'DD-MMM-YYYY' format (e.g., ['21-NOV-2024', '28-NOV-2024', ...])

    Raises:
        RuntimeError: If data fetch/parsing fails or NSE blocks access
    """
    sess = requests.Session()

    # Enhanced headers to avoid 403 errors
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    })

    try:
        # First, visit NSE homepage to get cookies
        logger.info("Fetching NSE homepage to establish session...")
        resp_home = sess.get(NSE_BASE, timeout=timeout)
        if not resp_home.ok:
            logger.warning(f"NSE homepage returned {resp_home.status_code}, continuing anyway...")

        # Small delay to mimic human behavior
        time.sleep(1)

        # Update headers for API request
        sess.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com/option-chain",
        })

        # Fetch the option chain JSON
        logger.info("Fetching NIFTY option chain from NSE API...")
        resp = sess.get(NSE_OC_URL, timeout=timeout)

        if not resp.ok:
            logger.error(f"NSE API request failed with status {resp.status_code}")
            raise RuntimeError(f"NSE option chain request failed: {resp.status_code}")

        data = resp.json()
        expiry_list: List[str] = data["records"]["expiryDates"]

        if not expiry_list:
            raise RuntimeError("Expiry list is empty from NSE")

        # Parse, sort, and return dates in proper format
        def parse_dt(s: str) -> datetime:
            return datetime.strptime(s, "%d-%b-%Y")

        unique_dates = sorted({parse_dt(s) for s in expiry_list})

        # Format as 'DD-MMM-YYYY' with uppercase month and limit to max_expiries
        result = [dt.strftime("%d-%b-%Y").upper() for dt in unique_dates[:max_expiries]]

        logger.info(f"Successfully fetched {len(result)} NIFTY expiry dates from NSE: {result[:5]}...")
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching NSE data: {e}")
        raise RuntimeError(f"Failed to fetch NSE option chain data: {e}") from e
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse NSE response: {e}")
        raise RuntimeError(f"Failed to parse NSE response: {e}") from e


def get_next_nifty_expiry(next_expiry: bool = False, timeout: int = 10) -> str:
    """
    Fetch the nearest (or next) NIFTY options expiry date from NSE.

    Args:
        next_expiry: If True, returns the next expiry after the closest one
        timeout: Per-request timeout in seconds

    Returns:
        str: Expiry date in 'DD-MMM-YYYY' format (e.g., '02-SEP-2025')

    Raises:
        RuntimeError: If data fetch/parsing fails
    """
    try:
        expiries = get_all_nifty_expiry_dates(max_expiries=5, timeout=timeout)
        index = 1 if next_expiry else 0
        if index >= len(expiries):
            raise IndexError("Requested next expiry but only one expiry was found")
        return expiries[index]
    except Exception as e:
        raise RuntimeError(f"Failed to get NIFTY expiry: {e}") from e


def get_next_monthly_expiry():
    """
    Calculate next monthly expiry (last Thursday of month).

    Returns:
        str: Expiry date in 'DD-MMM-YYYY' format
    """
    today = date.today()
    month = today.month
    year = today.year
    last_day = calendar.monthrange(year, month)[1]
    last_date = date(year, month, last_day)
    last_thursday = last_date
    while last_thursday.weekday() != 3:
        last_thursday -= timedelta(days=1)
    if last_thursday <= today:
        month = (month % 12) + 1
        year = year + (1 if month == 1 else 0)
        last_day = calendar.monthrange(year, month)[1]
        last_date = date(year, month, last_day)
        last_thursday = last_date
        while last_thursday.weekday() != 3:
            last_thursday -= timedelta(days=1)
    return last_thursday.strftime('%d-%b-%Y').upper()
