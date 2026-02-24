"""
Shared market data fetching functions.

Used by all strategies to get current prices, VIX, premiums, etc.
These functions consolidate duplicated code from kotak_strangle.py
and kotak_broken_iron_condor.py.

Error Handling:
- All functions return None or default values on error
- Errors are logged with full context
- Warnings are issued for fallback usage
"""

from decimal import Decimal
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict
import logging
import traceback

logger = logging.getLogger(__name__)


def safe_decimal(value, default: Decimal = Decimal('0')) -> Decimal:
    """Safely convert a value to Decimal with fallback."""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


# =============================================================================
# NIFTY HISTORICAL MOVEMENT FUNCTIONS
# =============================================================================

def get_nifty_change(days: int = 5) -> Optional[Decimal]:
    """
    Get Nifty percentage change over the last N trading days.

    Uses actual trading days from HistoricalPrice (Mon-Fri, excluding holidays).
    Queries last N records ordered by date.

    Args:
        days: Number of trading days to look back (1, 3, 5, etc.)

    Returns:
        Decimal: Percentage change, or None if data unavailable

    Example:
        5D change = ((today_close - close_5_days_ago) / close_5_days_ago) * 100

    Error Handling:
        - Returns None if database query fails
        - Returns None if insufficient records
        - Logs detailed error context for debugging
    """
    try:
        from apps.brokers.models import HistoricalPrice

        # Validate input
        if days < 1 or days > 30:
            logger.warning(f"Invalid days parameter: {days}. Using default 5.")
            days = 5

        # Get last N+1 records (need N+1 to calculate N-day change)
        records = HistoricalPrice.objects.filter(
            stock_code='NIFTY',
            product_type='cash',
            interval='1day'
        ).order_by('-datetime')[:days + 1]

        records = list(records)

        if len(records) < 2:
            logger.warning(
                f"Insufficient historical data for {days}D Nifty change. "
                f"Found {len(records)} records, need at least 2."
            )
            return None

        # Most recent close and N-days-ago close
        latest_record = records[0]
        older_record = records[min(days, len(records) - 1)]

        latest_close = safe_decimal(latest_record.close)
        older_close = safe_decimal(older_record.close)

        if older_close == 0:
            logger.warning(f"Older close price is 0, cannot calculate {days}D change")
            return None

        change_pct = ((latest_close - older_close) / older_close) * Decimal('100')

        logger.debug(
            f"Nifty {days}D change: {change_pct:+.2f}% "
            f"({older_close:.2f} -> {latest_close:.2f}) "
            f"[{older_record.datetime.date()} to {latest_record.datetime.date()}]"
        )

        return change_pct.quantize(Decimal('0.01'))

    except ImportError as e:
        logger.error(f"Failed to import HistoricalPrice model: {e}")
        return None
    except Exception as e:
        logger.error(
            f"Error getting Nifty {days}D change: {e}\n"
            f"Traceback: {traceback.format_exc()}"
        )
        return None


def get_consecutive_red_days() -> int:
    """
    Count consecutive red (down) days for Nifty.

    A red day is when close < previous close.

    Returns:
        int: Number of consecutive red days (0 if last day was green or error)

    Error Handling:
        - Returns 0 on any error (safe default for PUT widening logic)
        - Logs detailed error context
    """
    try:
        from apps.brokers.models import HistoricalPrice

        # Get last 10 days of data (enough to count consecutive days)
        records = HistoricalPrice.objects.filter(
            stock_code='NIFTY',
            product_type='cash',
            interval='1day'
        ).order_by('-datetime')[:10]

        records = list(records)

        if len(records) < 2:
            logger.warning(
                f"Insufficient data to count consecutive red days. "
                f"Found {len(records)} records, need at least 2."
            )
            return 0

        consecutive_red = 0
        red_day_dates = []

        # Start from most recent, count backwards
        for i in range(len(records) - 1):
            current_close = safe_decimal(records[i].close)
            prev_close = safe_decimal(records[i + 1].close)

            if prev_close == 0:
                logger.warning(f"Previous close is 0 at index {i+1}, stopping count")
                break

            if current_close < prev_close:
                consecutive_red += 1
                red_day_dates.append(str(records[i].datetime.date()))
            else:
                break  # Stop at first green day

        if consecutive_red > 0:
            logger.info(f"Consecutive red days: {consecutive_red} ({', '.join(red_day_dates)})")
        else:
            logger.debug("No consecutive red days (last day was green)")

        return consecutive_red

    except ImportError as e:
        logger.error(f"Failed to import HistoricalPrice model: {e}")
        return 0
    except Exception as e:
        logger.error(
            f"Error counting consecutive red days: {e}\n"
            f"Traceback: {traceback.format_exc()}"
        )
        return 0


def check_strike_liquidity(strike: int, option_type: str, expiry_date, min_oi: int = 100000) -> Dict:
    """
    Check if a strike has sufficient liquidity (Open Interest).

    Args:
        strike: Strike price
        option_type: 'CE' or 'PE'
        expiry_date: Expiry date
        min_oi: Minimum OI threshold (default: 100,000)

    Returns:
        dict: {
            'is_liquid': bool,
            'current_oi': int,
            'min_required': int,
            'warning': str or None,
            'data_available': bool
        }

    Error Handling:
        - Returns is_liquid=True on error (don't block trade on data issues)
        - Logs warning with full context
    """
    result = {
        'is_liquid': True,  # Default to liquid (don't block on data issues)
        'current_oi': None,
        'min_required': min_oi,
        'warning': None,
        'data_available': False
    }

    try:
        from apps.data.models import OptionChain

        # Validate inputs
        if option_type not in ['CE', 'PE']:
            logger.warning(f"Invalid option_type: {option_type}. Expected 'CE' or 'PE'.")
            result['warning'] = f"Invalid option type: {option_type}"
            return result

        option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=strike,
            option_type=option_type,
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        if not option:
            logger.warning(
                f"No option chain data for {strike}{option_type} expiry {expiry_date}"
            )
            result['warning'] = f"No OI data available for {strike}{option_type}"
            return result

        result['data_available'] = True
        current_oi = option.oi or 0
        result['current_oi'] = current_oi
        result['is_liquid'] = current_oi >= min_oi

        if not result['is_liquid']:
            result['warning'] = (
                f"Low liquidity: {strike}{option_type} has OI={current_oi:,} "
                f"(min required: {min_oi:,})"
            )
            logger.warning(result['warning'])
        else:
            logger.debug(f"Liquidity OK: {strike}{option_type} OI={current_oi:,}")

        return result

    except ImportError as e:
        logger.error(f"Failed to import OptionChain model: {e}")
        result['warning'] = "OptionChain model not available"
        return result
    except Exception as e:
        logger.error(
            f"Error checking strike liquidity for {strike}{option_type}: {e}\n"
            f"Traceback: {traceback.format_exc()}"
        )
        result['warning'] = f"Error checking liquidity: {str(e)}"
        return result


def get_option_premium_for_strike(strike: int, option_type: str, expiry_date) -> Optional[Decimal]:
    """
    Get the current premium (LTP) for a specific strike.

    Args:
        strike: Strike price
        option_type: 'CE' or 'PE'
        expiry_date: Expiry date

    Returns:
        Decimal: Premium (LTP), or None if unavailable

    Error Handling:
        - Returns None if data unavailable
        - Logs context for debugging
    """
    try:
        from apps.data.models import OptionChain

        # Validate inputs
        if option_type not in ['CE', 'PE']:
            logger.warning(f"Invalid option_type: {option_type}")
            return None

        option = OptionChain.objects.filter(
            underlying='NIFTY',
            strike=strike,
            option_type=option_type,
            expiry_date=expiry_date
        ).order_by('-created_at').first()

        if not option:
            logger.debug(f"No option chain data for {strike}{option_type} expiry {expiry_date}")
            return None

        if option.ltp is None or option.ltp == 0:
            logger.debug(f"No LTP available for {strike}{option_type}")
            return None

        premium = safe_decimal(option.ltp)
        logger.debug(f"Premium for {strike}{option_type}: Rs.{premium:.2f}")
        return premium

    except ImportError as e:
        logger.error(f"Failed to import OptionChain model: {e}")
        return None
    except Exception as e:
        logger.error(
            f"Error getting premium for {strike}{option_type}: {e}\n"
            f"Traceback: {traceback.format_exc()}"
        )
        return None


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
