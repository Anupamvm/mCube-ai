"""
Margin Service - Shared margin fetching logic for futures trading

This module centralizes margin-related operations used across:
- Futures Algorithm (algorithm_views.py)
- Trade Verification (verification_views.py)
- Position Sizing API (api_views.py)

Key functions:
- get_available_margin(): Fetches F&O available margin from Breeze account
- get_margin_per_lot(): Fetches margin required per lot for a specific contract
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, Union

logger = logging.getLogger(__name__)

# Default fallback values
DEFAULT_AVAILABLE_MARGIN = 5000000  # 50 lakh
DEFAULT_MARGIN_FALLBACK_PCT = 0.17  # 17% of contract value


def get_available_margin(breeze=None, exchange: str = "NFO", fallback: float = DEFAULT_AVAILABLE_MARGIN) -> float:
    """
    Get F&O available margin from Breeze account.

    Fetches account-level margin data and calculates available margin as:
    available_margin = cash_limit - block_by_trade

    Args:
        breeze: Breeze client instance. If None, returns fallback value.
        exchange: Exchange code (default "NFO" for F&O segment)
        fallback: Default margin if Breeze unavailable (default 50 lakh)

    Returns:
        float: Available margin in rupees

    Example:
        >>> breeze = get_breeze_client()
        >>> margin = get_available_margin(breeze)
        >>> print(f"Available margin: ₹{margin:,.0f}")
    """
    if not breeze:
        logger.warning(f"Breeze client not available, using default margin: ₹{fallback:,.0f}")
        return fallback

    try:
        margin_response = breeze.get_margin(exchange_code=exchange)

        if margin_response and margin_response.get('Status') == 200:
            margin_data = margin_response.get('Success', {})

            # Breeze F&O margin fields:
            # - cash_limit: Total margin limit
            # - amount_allocated: Currently allocated
            # - block_by_trade: Blocked by active trades
            cash_limit = float(margin_data.get('cash_limit', 0))
            block_by_trade = float(margin_data.get('block_by_trade', 0))

            # Available margin = cash_limit - block_by_trade
            available_margin = cash_limit - block_by_trade

            logger.info(f"Available F&O margin from Breeze: ₹{available_margin:,.0f} "
                       f"(cash_limit: ₹{cash_limit:,.0f}, blocked: ₹{block_by_trade:,.0f})")

            return available_margin
        else:
            logger.warning(f"Could not fetch F&O margin from Breeze (Status: {margin_response.get('Status') if margin_response else 'None'}), using default: ₹{fallback:,.0f}")
            return fallback

    except Exception as e:
        logger.warning(f"Error fetching F&O margin: {e}, using default: ₹{fallback:,.0f}")
        return fallback


def get_margin_per_lot(
    breeze,
    symbol: str,
    expiry: str,
    lot_size: int,
    direction: str = 'LONG',
    futures_price: Optional[Union[float, Decimal]] = None,
    fallback_pct: float = DEFAULT_MARGIN_FALLBACK_PCT
) -> Dict[str, Any]:
    """
    Get margin required per lot for a specific futures contract.

    Calls Breeze API to get actual margin requirement. Falls back to
    estimated margin (fallback_pct of contract value) if API fails.

    Args:
        breeze: Breeze client instance
        symbol: Stock symbol (e.g., 'RELIANCE')
        expiry: Expiry date in Breeze format (e.g., '27-FEB-2025')
        lot_size: Number of shares per lot
        direction: Trade direction ('LONG' or 'SHORT')
        futures_price: Current futures price (required for fallback calculation)
        fallback_pct: Percentage for margin estimation (default 17%)

    Returns:
        dict: {
            'success': bool,
            'margin_per_lot': float,
            'total_margin': float,  # For 1 lot
            'span_margin': float,
            'exposure_margin': float,
            'source': 'Breeze API' or 'Estimated'
        }

    Example:
        >>> result = get_margin_per_lot(breeze, 'RELIANCE', '27-FEB-2025', 250, 'LONG', 2800.0)
        >>> print(f"Margin per lot: ₹{result['margin_per_lot']:,.0f}")
    """
    result = {
        'success': False,
        'margin_per_lot': 0,
        'total_margin': 0,
        'span_margin': 0,
        'exposure_margin': 0,
        'source': 'Unknown'
    }

    if not breeze:
        # Fallback to estimation
        if futures_price:
            estimated_margin = float(futures_price) * lot_size * fallback_pct
            result.update({
                'success': True,
                'margin_per_lot': estimated_margin,
                'total_margin': estimated_margin,
                'source': 'Estimated'
            })
            logger.warning(f"Breeze not available for {symbol}, estimated margin: ₹{estimated_margin:,.0f}")
        return result

    try:
        # Map direction to Breeze action
        action = 'buy' if direction.upper() == 'LONG' else 'sell'

        margin_response = breeze.get_margin(
            exchange_code='NFO',
            product_type='futures',
            stock_code=symbol,
            quantity=str(lot_size),  # 1 lot
            price='0',  # Market price
            action=action,
            expiry_date=expiry,
            right='others',
            strike_price='0'
        )

        if margin_response and margin_response.get('Status') == 200:
            margin_data = margin_response.get('Success', {})

            total_margin = float(margin_data.get('total', 0))
            span_margin = float(margin_data.get('span', 0))
            exposure_margin = float(margin_data.get('exposure', 0))

            if total_margin > 0:
                result.update({
                    'success': True,
                    'margin_per_lot': total_margin,
                    'total_margin': total_margin,
                    'span_margin': span_margin,
                    'exposure_margin': exposure_margin,
                    'source': 'Breeze API'
                })
                logger.info(f"Breeze margin for {symbol}: ₹{total_margin:,.0f} per lot "
                           f"(SPAN: ₹{span_margin:,.0f}, Exposure: ₹{exposure_margin:,.0f})")
                return result

        # Fallback if API returned no data
        logger.warning(f"Margin API returned no data for {symbol}, using estimation")

    except Exception as e:
        logger.warning(f"Error fetching margin for {symbol}: {e}")

    # Fallback to estimation
    if futures_price:
        estimated_margin = float(futures_price) * lot_size * fallback_pct
        result.update({
            'success': True,
            'margin_per_lot': estimated_margin,
            'total_margin': estimated_margin,
            'source': 'Estimated'
        })
        logger.warning(f"Using estimated margin for {symbol}: ₹{estimated_margin:,.0f} ({fallback_pct*100:.0f}% of contract value)")

    return result


def get_margin_summary(
    breeze,
    symbol: str,
    expiry: str,
    lot_size: int,
    direction: str = 'LONG',
    futures_price: Optional[Union[float, Decimal]] = None,
    available_margin: Optional[float] = None
) -> Dict[str, Any]:
    """
    Get comprehensive margin summary for position sizing.

    Combines available margin and per-lot margin to provide complete
    margin context for position sizing decisions.

    Args:
        breeze: Breeze client instance
        symbol: Stock symbol
        expiry: Expiry date in Breeze format
        lot_size: Number of shares per lot
        direction: Trade direction
        futures_price: Current futures price
        available_margin: Pre-fetched available margin (optional)

    Returns:
        dict: {
            'available_margin': float,
            'margin_per_lot': float,
            'max_lots_possible': int,
            'futures_price': float,
            'source': str
        }
    """
    # Fetch available margin if not provided
    if available_margin is None:
        available_margin = get_available_margin(breeze)

    # Fetch margin per lot
    margin_result = get_margin_per_lot(
        breeze=breeze,
        symbol=symbol,
        expiry=expiry,
        lot_size=lot_size,
        direction=direction,
        futures_price=futures_price
    )

    margin_per_lot = margin_result.get('margin_per_lot', 0)

    # Calculate max lots possible
    max_lots = int(available_margin / margin_per_lot) if margin_per_lot > 0 else 0

    return {
        'available_margin': available_margin,
        'margin_per_lot': margin_per_lot,
        'max_lots_possible': max_lots,
        'futures_price': float(futures_price) if futures_price else 0,
        'source': margin_result.get('source', 'Unknown'),
        'span_margin': margin_result.get('span_margin', 0),
        'exposure_margin': margin_result.get('exposure_margin', 0)
    }
