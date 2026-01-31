"""
Shared market data fetching functions.

Used by all strategies to get current prices, VIX, premiums, etc.
These functions consolidate duplicated code from kotak_strangle.py
and kotak_broken_iron_condor.py.
"""

from decimal import Decimal
from datetime import datetime, timedelta
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


def get_nifty_price() -> Decimal:
    """
    Get current Nifty spot price.

    Fetches the latest Nifty 50 price from historical data.
    Falls back to a default value if data is unavailable.

    Returns:
        Decimal: Current Nifty price
    """
    try:
        from apps.brokers.models import HistoricalPrice

        # Try to get latest price from historical data
        latest_price = HistoricalPrice.objects.filter(
            symbol='NIFTY 50',
            timestamp__gte=datetime.now() - timedelta(days=1)
        ).order_by('-timestamp').first()

        if latest_price:
            return Decimal(str(latest_price.close))

        # Fallback to hardcoded value
        logger.warning("Using fallback Nifty price")
        return Decimal('24000.00')

    except Exception as e:
        logger.error(f"Error getting Nifty price: {e}")
        return Decimal('24000.00')


def get_vix() -> Decimal:
    """
    Get current India VIX value.

    Fetches the latest India VIX from historical data.
    Falls back to a default value if data is unavailable.

    Returns:
        Decimal: Current VIX value
    """
    try:
        from apps.brokers.models import HistoricalPrice

        latest_vix = HistoricalPrice.objects.filter(
            symbol='INDIA VIX',
            timestamp__gte=datetime.now() - timedelta(days=1)
        ).order_by('-timestamp').first()

        if latest_vix:
            return Decimal(str(latest_vix.close))

        logger.warning("Using fallback VIX value")
        return Decimal('14.50')

    except Exception as e:
        logger.error(f"Error getting VIX: {e}")
        return Decimal('14.50')


def get_option_premiums(call_strike: int, put_strike: int, expiry_date) -> Tuple[Decimal, Decimal]:
    """
    Get option premiums for given strikes.

    Fetches the latest LTP from option chain data for both
    call and put options at the specified strikes.

    Args:
        call_strike: Call option strike price
        put_strike: Put option strike price
        expiry_date: Expiry date for the options

    Returns:
        Tuple[Decimal, Decimal]: (call_premium, put_premium)
    """
    try:
        from apps.data.models import OptionChain

        # Get latest option chain data for call
        call_option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=call_strike,
            option_type='CE',
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        # Get latest option chain data for put
        put_option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=put_strike,
            option_type='PE',
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        call_premium = call_option.ltp if call_option else Decimal('100.0')
        put_premium = put_option.ltp if put_option else Decimal('100.0')

        logger.info(f"Premiums: {call_strike}CE = Rs.{call_premium}, {put_strike}PE = Rs.{put_premium}")

        return call_premium, put_premium

    except Exception as e:
        logger.error(f"Error getting option premiums: {e}")
        # Return fallback values
        return Decimal('100.0'), Decimal('100.0')


def get_put_premium(strike: int, expiry_date) -> Decimal:
    """
    Get put option premium for a single strike.

    Used for insurance put premium calculation in broken iron condor.

    Args:
        strike: Put option strike price
        expiry_date: Expiry date for the option

    Returns:
        Decimal: Put premium
    """
    try:
        from apps.data.models import OptionChain

        put_option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=strike,
            option_type='PE',
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        if put_option:
            return Decimal(str(put_option.ltp))

        # Estimate premium based on distance from ATM
        # Further OTM puts are cheaper
        logger.warning(f"Using estimated premium for {strike}PE")
        return Decimal('50.0')

    except Exception as e:
        logger.error(f"Error getting put premium: {e}")
        return Decimal('50.0')
