"""
ICICI Breeze Historical - Historical Price Data Fetching

This module provides functions to fetch and save historical price data.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.utils import timezone as dj_timezone

from apps.brokers.models import HistoricalPrice

from .client import get_breeze_client

logger = logging.getLogger(__name__)


def save_historical_price_record(stock_code, exchange_code, product_type, candle_data,
                                expiry_date=None, right='', strike_price=None):
    """
    Save a single historical price record to database.

    Args:
        stock_code: Stock/index code
        exchange_code: Exchange code (NSE, NFO, etc.)
        product_type: 'cash', 'futures', or 'options'
        candle_data: Dict with OHLCV data
        expiry_date: Optional expiry date for derivatives
        right: Optional 'call'/'put' for options
        strike_price: Optional strike price for options

    Returns:
        HistoricalPrice: Created object or None if already exists
    """
    try:
        # Parse datetime and make it timezone-aware
        dt_str = candle_data['datetime'].replace('Z', '+00:00')
        dt = datetime.fromisoformat(dt_str)

        # Ensure datetime is timezone-aware for Django
        if dt.tzinfo is None:
            dt = dj_timezone.make_aware(dt)

        # Check if record already exists
        existing = HistoricalPrice.objects.filter(
            datetime=dt,
            stock_code=stock_code,
            exchange_code=exchange_code,
            product_type=product_type,
            expiry_date=expiry_date,
            right=right,
            strike_price=strike_price
        ).first()

        if existing:
            return None

        # Safely handle None values for volume and open_interest
        volume = candle_data.get('volume')
        open_interest = candle_data.get('open_interest')

        obj = HistoricalPrice.objects.create(
            datetime=dt,
            stock_code=stock_code,
            exchange_code=exchange_code,
            product_type=product_type,
            expiry_date=expiry_date,
            right=right,
            strike_price=Decimal(str(strike_price)) if strike_price else None,
            open=Decimal(str(candle_data.get('open', 0))),
            high=Decimal(str(candle_data.get('high', 0))),
            low=Decimal(str(candle_data.get('low', 0))),
            close=Decimal(str(candle_data.get('close', 0))),
            volume=int(volume) if volume is not None else 0,
            open_interest=int(open_interest) if open_interest is not None else 0,
        )
        return obj
    except Exception as e:
        logger.error(f"Error saving historical price: {e}")
        return None


def get_nifty50_historical_days(days=3000, interval="1day"):
    """
    Fetch historical NIFTY50 cash data and save to database.

    Args:
        days: Number of days of historical data to fetch
        interval: Data interval ('1minute', '5minute', '30minute', '1day')

    Returns:
        int: Number of records saved
    """
    breeze = get_breeze_client()
    today = date.today()
    batch_size = 1000
    saved_count = 0

    for batch_start in range(0, days, batch_size):
        batch_days = min(batch_size, days - batch_start)
        from_date = (today - timedelta(days=batch_start + batch_days)).strftime('%Y-%m-%dT09:15:00.000Z')
        to_date = (today - timedelta(days=batch_start)).strftime('%Y-%m-%dT15:30:00.000Z')

        try:
            resp = breeze.get_historical_data(
                interval=interval,
                from_date=from_date,
                to_date=to_date,
                stock_code="NIFTY",
                exchange_code="NSE",
                product_type="cash"
            )
            candles = resp.get('Success', [])
            for candle in candles:
                if save_historical_price_record("NIFTY", "NSE", "cash", candle):
                    saved_count += 1
        except Exception as e:
            logger.error(f"Error fetching historical data batch: {e}")

    logger.info(f"Saved {saved_count} NIFTY historical records")
    return saved_count
