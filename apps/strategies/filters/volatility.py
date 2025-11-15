"""
Market Regime Filter (Volatility & Technical Indicators)

Checks market regime before establishing market-neutral positions.

Filters:
1. India VIX threshold check (VIX > 20 = too volatile)
2. Bollinger Bands extreme check (price at BB extremes = avoid)

Rationale:
- High VIX = Higher volatility = Increased gamma risk for options
- Price at BB extremes = Likely directional move imminent = Bad for neutral strategies
"""

import logging
from decimal import Decimal
from typing import Dict, Tuple, List
from datetime import datetime, timedelta
import statistics

from django.utils import timezone

from apps.brokers.models import HistoricalPrice

logger = logging.getLogger(__name__)


def get_india_vix() -> Decimal:
    """
    Get current India VIX value

    India VIX is the volatility index for Nifty 50, similar to VIX in US markets.
    Higher VIX = Higher expected volatility

    Returns:
        Decimal: Current VIX value

    TODO: Integrate with broker API or NSE API to fetch real-time VIX
    """

    # Placeholder implementation
    # TODO: Replace with actual India VIX fetch from broker/NSE

    logger.debug("Fetching India VIX...")

    # Mock data for now
    vix = Decimal('14.5')  # Sample VIX value

    logger.debug(f"India VIX: {vix:.2f}")

    return vix


def get_nifty_spot() -> Decimal:
    """
    Get current Nifty 50 spot price

    Returns:
        Decimal: Current Nifty spot price

    TODO: Fetch from broker API or NSE
    """

    # Placeholder implementation
    # TODO: Replace with actual Nifty spot price fetch

    logger.debug("Fetching Nifty spot price...")

    # Mock data for now
    spot_price = Decimal('24000')  # Sample spot price

    logger.debug(f"Nifty Spot: ₹{spot_price:,.2f}")

    return spot_price


def get_historical_prices(symbol: str, days: int) -> List[Decimal]:
    """
    Get historical closing prices for a symbol

    Args:
        symbol: Symbol (e.g., 'NIFTY', 'BANKNIFTY')
        days: Number of days of historical data

    Returns:
        list: List of closing prices (most recent first)

    TODO: Query from HistoricalPrice model or broker API
    """

    logger.debug(f"Fetching {days} days of historical prices for {symbol}...")

    # Placeholder implementation
    # TODO: Replace with actual historical data query

    # Mock data - simulate prices around 24000 with some variance
    base_price = 24000
    prices = []

    for i in range(days):
        # Simulate small random movements
        variance = (-50 + (i * 5)) if i < 10 else (50 - (i * 5))
        price = Decimal(str(base_price + variance))
        prices.append(price)

    # Most recent first
    prices.reverse()

    logger.debug(f"Retrieved {len(prices)} historical prices")

    return prices


def calculate_bollinger_bands(
    prices: List[Decimal],
    period: int = 20,
    std_dev: int = 2
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Calculate Bollinger Bands

    Bollinger Bands consist of:
    - Middle Band: Simple Moving Average (SMA)
    - Upper Band: SMA + (Standard Deviation × multiplier)
    - Lower Band: SMA - (Standard Deviation × multiplier)

    Args:
        prices: List of closing prices (most recent first)
        period: Lookback period for SMA (default: 20)
        std_dev: Standard deviation multiplier (default: 2)

    Returns:
        tuple: (upper_band, middle_band, lower_band)
    """

    if len(prices) < period:
        raise ValueError(f"Insufficient price data (need {period}, got {len(prices)})")

    # Get last 'period' prices (most recent data)
    recent_prices = prices[:period]

    # Convert to float for statistics module
    prices_float = [float(p) for p in recent_prices]

    # Calculate SMA (Middle Band)
    middle_band = Decimal(str(statistics.mean(prices_float)))

    # Calculate Standard Deviation
    std = Decimal(str(statistics.stdev(prices_float)))

    # Calculate Upper and Lower Bands
    upper_band = middle_band + (std * Decimal(str(std_dev)))
    lower_band = middle_band - (std * Decimal(str(std_dev)))

    logger.debug(f"Bollinger Bands ({period}-period, {std_dev}-SD):")
    logger.debug(f"  Upper Band: ₹{upper_band:,.2f}")
    logger.debug(f"  Middle Band (SMA): ₹{middle_band:,.2f}")
    logger.debug(f"  Lower Band: ₹{lower_band:,.2f}")

    return upper_band, middle_band, lower_band


def check_vix_threshold(max_vix: Decimal = Decimal('20')) -> Dict:
    """
    Check if India VIX is below threshold

    Args:
        max_vix: Maximum acceptable VIX value (default: 20)

    Returns:
        dict: {
            'passed': bool,
            'vix': Decimal,
            'threshold': Decimal,
            'message': str
        }
    """

    logger.info(f"Checking VIX threshold (max: {max_vix})...")

    try:
        vix = get_india_vix()

        passed = vix <= max_vix

        if passed:
            message = f"VIX {vix:.2f} below threshold ({max_vix})"
            logger.info(f"✅ {message}")
        else:
            message = f"VIX {vix:.2f} exceeds threshold ({max_vix})"
            logger.warning(f"❌ {message}")

        return {
            'passed': passed,
            'vix': vix,
            'threshold': max_vix,
            'message': message
        }

    except Exception as e:
        logger.error(f"VIX check failed: {e}", exc_info=True)
        return {
            'passed': False,
            'vix': Decimal('0'),
            'threshold': max_vix,
            'message': f"VIX check failed: {str(e)}"
        }


def check_bollinger_bands(
    symbol: str = 'NIFTY',
    period: int = 20,
    std_dev: int = 2
) -> Dict:
    """
    Check if price is at Bollinger Band extremes

    When price is at upper or lower BB extreme, a reversal or continuation
    move is likely, making it risky to establish market-neutral positions.

    Args:
        symbol: Symbol to check (default: 'NIFTY')
        period: BB period (default: 20)
        std_dev: BB standard deviation (default: 2)

    Returns:
        dict: {
            'passed': bool,
            'current_price': Decimal,
            'upper_band': Decimal,
            'middle_band': Decimal,
            'lower_band': Decimal,
            'position': str,  # 'NEUTRAL', 'AT_UPPER', 'AT_LOWER'
            'message': str
        }
    """

    logger.info(f"Checking Bollinger Bands for {symbol}...")

    try:
        # Get current price
        current_price = get_nifty_spot()

        # Get historical prices
        prices = get_historical_prices(symbol, days=period + 5)

        # Calculate Bollinger Bands
        upper_band, middle_band, lower_band = calculate_bollinger_bands(
            prices, period=period, std_dev=std_dev
        )

        # Check position relative to bands
        # Allow 0.5% buffer from extreme bands
        upper_threshold = upper_band * Decimal('0.995')  # 0.5% below upper band
        lower_threshold = lower_band * Decimal('1.005')  # 0.5% above lower band

        if current_price >= upper_threshold:
            position = 'AT_UPPER'
            passed = False
            message = (
                f"Price at upper BB extreme "
                f"(₹{current_price:,.0f} near ₹{upper_band:,.0f})"
            )
            logger.warning(f"❌ {message}")

        elif current_price <= lower_threshold:
            position = 'AT_LOWER'
            passed = False
            message = (
                f"Price at lower BB extreme "
                f"(₹{current_price:,.0f} near ₹{lower_band:,.0f})"
            )
            logger.warning(f"❌ {message}")

        else:
            position = 'NEUTRAL'
            passed = True
            message = (
                f"Price in neutral zone "
                f"(₹{current_price:,.0f} between ₹{lower_band:,.0f} - ₹{upper_band:,.0f})"
            )
            logger.info(f"✅ {message}")

        return {
            'passed': passed,
            'current_price': current_price,
            'upper_band': upper_band,
            'middle_band': middle_band,
            'lower_band': lower_band,
            'position': position,
            'message': message
        }

    except Exception as e:
        logger.error(f"Bollinger Bands check failed: {e}", exc_info=True)
        return {
            'passed': False,
            'current_price': Decimal('0'),
            'upper_band': Decimal('0'),
            'middle_band': Decimal('0'),
            'lower_band': Decimal('0'),
            'position': 'UNKNOWN',
            'message': f"Bollinger Bands check failed: {str(e)}"
        }


def check_market_regime() -> Dict:
    """
    Comprehensive market regime check

    Combines VIX and Bollinger Bands checks to determine if market regime
    is favorable for establishing market-neutral short strangle positions.

    Returns:
        dict: {
            'passed': bool,
            'message': str,
            'details': {
                'vix_check': dict,
                'bb_check': dict
            }
        }
    """

    logger.info("Checking market regime (VIX + Bollinger Bands)...")

    issues = []
    details = {}

    # Check 1: VIX Threshold
    vix_check = check_vix_threshold(max_vix=Decimal('20'))
    details['vix_check'] = {
        'passed': vix_check['passed'],
        'vix': float(vix_check['vix']),
        'threshold': float(vix_check['threshold'])
    }

    if not vix_check['passed']:
        issues.append(vix_check['message'])

    # Check 2: Bollinger Bands
    bb_check = check_bollinger_bands(symbol='NIFTY', period=20, std_dev=2)
    details['bb_check'] = {
        'passed': bb_check['passed'],
        'current_price': float(bb_check['current_price']),
        'upper_band': float(bb_check['upper_band']),
        'middle_band': float(bb_check['middle_band']),
        'lower_band': float(bb_check['lower_band']),
        'position': bb_check['position']
    }

    if not bb_check['passed']:
        issues.append(bb_check['message'])

    # Final verdict
    passed = len(issues) == 0

    if passed:
        message = "Market regime favorable (VIX acceptable, price not at BB extremes)"
    else:
        message = "; ".join(issues)

    logger.info(f"Market regime check: {'PASSED' if passed else 'FAILED'}")
    if not passed:
        for issue in issues:
            logger.warning(f"  - {issue}")

    return {
        'passed': passed,
        'message': message,
        'details': details
    }
