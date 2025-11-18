"""
Date and time utility functions for mCube Trading System

This module provides functions for:
- Expiry date calculations (weekly/monthly)
- Trading day validation
- Market hours checking
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

import pytz

from apps.core.constants import (
    MARKET_OPEN_TIME,
    MARKET_CLOSE_TIME,
    TRADING_DAYS,
    WEEKDAY_TUESDAY,
    WEEKDAY_WEDNESDAY,
    WEEKDAY_THURSDAY,
    WEEKDAY_FRIDAY,
)

logger = logging.getLogger(__name__)

# Indian timezone
IST = pytz.timezone('Asia/Kolkata')


def get_current_weekly_expiry(instrument: str = 'NIFTY') -> date:
    """
    Get the current weekly expiry date for the given instrument

    IMPORTANT: As of 2025, NIFTY weekly expiry changed from Thursday to Tuesday
    - NIFTY: Tuesday (since 2025)
    - BANKNIFTY: Wednesday
    - FINNIFTY: Tuesday

    Args:
        instrument: The instrument name (NIFTY, BANKNIFTY, FINNIFTY)

    Returns:
        date: The current weekly expiry date

    Example:
        >>> get_current_weekly_expiry('NIFTY')
        datetime.date(2025, 11, 18)  # Next Tuesday
    """
    today = date.today()

    # Determine expiry weekday based on instrument
    # NIFTY changed from Thursday to Tuesday in 2025
    if instrument.upper() == 'NIFTY':
        expiry_weekday = WEEKDAY_TUESDAY  # Tuesday = 1
    elif instrument.upper() == 'BANKNIFTY':
        expiry_weekday = WEEKDAY_WEDNESDAY  # Wednesday = 2 (changed from Thursday)
    elif instrument.upper() == 'FINNIFTY':
        expiry_weekday = WEEKDAY_TUESDAY  # Tuesday = 1
    else:
        # Default to Thursday for unknown instruments (legacy behavior)
        expiry_weekday = WEEKDAY_THURSDAY  # Thursday = 3
        logger.warning(f"Unknown instrument {instrument}, defaulting to Thursday expiry")

    days_ahead = expiry_weekday - today.weekday()

    if days_ahead < 0:  # Expiry day already passed this week
        days_ahead += 7

    expiry = today + timedelta(days=days_ahead)
    logger.debug(f"Current weekly expiry for {instrument}: {expiry}")

    return expiry


def get_next_weekly_expiry(instrument: str = 'NIFTY') -> date:
    """
    Get the next weekly expiry date (skip current week if already expired)

    Args:
        instrument: The instrument name (NIFTY, BANKNIFTY, FINNIFTY)

    Returns:
        date: The next weekly expiry date

    Example:
        >>> get_next_weekly_expiry('NIFTY')
        datetime.date(2025, 11, 25)  # Next week's Tuesday
    """
    current_expiry = get_current_weekly_expiry(instrument)
    today = date.today()

    # Determine expiry weekday based on instrument (must match get_current_weekly_expiry)
    if instrument.upper() == 'NIFTY':
        expiry_weekday = WEEKDAY_TUESDAY
    elif instrument.upper() == 'BANKNIFTY':
        expiry_weekday = WEEKDAY_WEDNESDAY
    elif instrument.upper() == 'FINNIFTY':
        expiry_weekday = WEEKDAY_TUESDAY
    else:
        expiry_weekday = WEEKDAY_THURSDAY

    # If current expiry is today or has passed, get next week
    if current_expiry <= today:
        next_expiry = current_expiry + timedelta(days=7)
    else:
        # If we're past expiry day 3:30 PM, skip to next week
        now = datetime.now(IST)
        if today.weekday() == expiry_weekday and now.time() > time(15, 30):
            next_expiry = current_expiry + timedelta(days=7)
        else:
            next_expiry = current_expiry + timedelta(days=7)

    logger.debug(f"Next weekly expiry for {instrument}: {next_expiry}")
    return next_expiry


def get_current_month_expiry(symbol: str) -> date:
    """
    Get the current monthly expiry date for futures

    Monthly expiry is on the last Thursday of the month

    Args:
        symbol: The stock/index symbol

    Returns:
        date: The current monthly expiry date

    Example:
        >>> get_current_month_expiry('RELIANCE')
        datetime.date(2024, 11, 28)  # Last Thursday of November
    """
    today = date.today()

    # Get the last day of current month
    if today.month == 12:
        next_month = date(today.year + 1, 1, 1)
    else:
        next_month = date(today.year, today.month + 1, 1)

    last_day = next_month - timedelta(days=1)

    # Find the last Thursday
    days_back = (last_day.weekday() - WEEKDAY_THURSDAY) % 7
    expiry = last_day - timedelta(days=days_back)

    logger.debug(f"Current monthly expiry for {symbol}: {expiry}")
    return expiry


def get_next_month_expiry(symbol: str) -> date:
    """
    Get the next monthly expiry date (next month's last Thursday)

    Args:
        symbol: The stock/index symbol

    Returns:
        date: The next monthly expiry date

    Example:
        >>> get_next_month_expiry('RELIANCE')
        datetime.date(2024, 12, 26)  # Last Thursday of December
    """
    today = date.today()

    # Get next month
    if today.month == 12:
        next_month_start = date(today.year + 1, 1, 1)
    else:
        next_month_start = date(today.year, today.month + 1, 1)

    # Get the last day of next month
    if next_month_start.month == 12:
        month_after = date(next_month_start.year + 1, 1, 1)
    else:
        month_after = date(next_month_start.year, next_month_start.month + 1, 1)

    last_day = month_after - timedelta(days=1)

    # Find the last Thursday
    days_back = (last_day.weekday() - WEEKDAY_THURSDAY) % 7
    expiry = last_day - timedelta(days=days_back)

    logger.debug(f"Next monthly expiry for {symbol}: {expiry}")
    return expiry


def get_days_to_expiry(expiry_date: date) -> int:
    """
    Calculate days remaining until expiry

    Args:
        expiry_date: The expiry date

    Returns:
        int: Number of days to expiry

    Example:
        >>> get_days_to_expiry(date(2024, 11, 28))
        7
    """
    today = date.today()
    days = (expiry_date - today).days
    return days


def is_trading_day(check_date: Optional[date] = None) -> bool:
    """
    Check if a given date is a trading day (Monday-Friday, excluding holidays)

    Note: This only checks for weekdays. Market holidays need to be checked separately.

    Args:
        check_date: Date to check (defaults to today)

    Returns:
        bool: True if it's a trading day

    Example:
        >>> is_trading_day(date(2024, 11, 16))  # Saturday
        False
        >>> is_trading_day(date(2024, 11, 18))  # Monday
        True
    """
    if check_date is None:
        check_date = date.today()

    is_weekday = check_date.weekday() in TRADING_DAYS

    # TODO: Add holiday calendar check
    # is_holiday = check_date in MARKET_HOLIDAYS

    return is_weekday


def is_market_hours(check_time: Optional[datetime] = None) -> bool:
    """
    Check if current time is within market hours (9:15 AM - 3:30 PM IST)

    Args:
        check_time: Time to check (defaults to now in IST)

    Returns:
        bool: True if within market hours

    Example:
        >>> is_market_hours()  # Called at 10:00 AM
        True
        >>> is_market_hours()  # Called at 4:00 PM
        False
    """
    if check_time is None:
        check_time = datetime.now(IST)
    elif check_time.tzinfo is None:
        # Localize to IST if timezone-naive
        check_time = IST.localize(check_time)

    # Check if it's a trading day
    if not is_trading_day(check_time.date()):
        return False

    # Parse market hours
    market_open = time(9, 15)
    market_close = time(15, 30)

    current_time = check_time.time()

    return market_open <= current_time <= market_close


def is_within_entry_window(check_time: Optional[datetime] = None) -> bool:
    """
    Check if current time is within the entry window (9:00 AM - 11:30 AM IST)

    Args:
        check_time: Time to check (defaults to now in IST)

    Returns:
        bool: True if within entry window

    Example:
        >>> is_within_entry_window()  # Called at 10:00 AM
        True
        >>> is_within_entry_window()  # Called at 12:00 PM
        False
    """
    if check_time is None:
        check_time = datetime.now(IST)
    elif check_time.tzinfo is None:
        check_time = IST.localize(check_time)

    # Check if it's a trading day
    if not is_trading_day(check_time.date()):
        return False

    entry_start = time(9, 0)
    entry_end = time(11, 30)

    current_time = check_time.time()

    return entry_start <= current_time <= entry_end


def get_current_ist_time() -> datetime:
    """
    Get current time in IST timezone

    Returns:
        datetime: Current datetime in IST

    Example:
        >>> get_current_ist_time()
        datetime.datetime(2024, 11, 15, 10, 30, 0, tzinfo=<DstTzInfo 'Asia/Kolkata' IST+5:30:00 STD>)
    """
    return datetime.now(IST)


def format_time_ist(dt: datetime) -> str:
    """
    Format datetime to IST string

    Args:
        dt: Datetime to format

    Returns:
        str: Formatted time string

    Example:
        >>> format_time_ist(datetime.now())
        '15-Nov-2024 10:30:45 IST'
    """
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    else:
        dt = dt.astimezone(IST)

    return dt.strftime('%d-%b-%Y %H:%M:%S %Z')
