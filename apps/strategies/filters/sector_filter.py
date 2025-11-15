"""
Sector Analysis Filter

Analyzes sector strength across multiple timeframes before establishing futures positions.

CRITICAL RULE (from design doc):
- For LONG: ALL timeframes (3D, 7D, 21D) must be POSITIVE
- For SHORT: ALL timeframes (3D, 7D, 21D) must be NEGATIVE
- Mixed signals → DON'T TRADE (wait for clarity)

This is a NON-NEGOTIABLE filter for ICICI Futures Strategy.

Rationale:
Sector tailwinds/headwinds significantly impact individual stock performance.
Trading against the sector is fighting the tide. We only trade when the sector
provides a clear, sustained directional bias.
"""

import logging
from decimal import Decimal
from typing import Dict, List
from datetime import datetime, timedelta

from django.utils import timezone

from apps.data.models import TLStockData
from apps.brokers.models import HistoricalPrice

logger = logging.getLogger(__name__)


# Sector to Index mapping
SECTOR_INDEX_MAP = {
    'BANKING': 'BANKNIFTY',
    'IT': 'CNXIT',
    'AUTO': 'CNXAUTO',
    'PHARMA': 'CNXPHARMA',
    'FMCG': 'CNXFMCG',
    'METAL': 'CNXMETAL',
    'REALTY': 'CNXREALTY',
    'ENERGY': 'CNXENERGY',
    'INFRASTRUCTURE': 'CNXINFRA',
    'FINANCE': 'NIFTYFIN',
}


def get_stock_sector(symbol: str) -> str:
    """
    Get sector for a stock symbol

    Args:
        symbol: Stock symbol (e.g., 'RELIANCE', 'TCS')

    Returns:
        str: Sector name (e.g., 'ENERGY', 'IT')

    TODO: Query from TLStockData model or maintain separate sector mapping
    """

    # Placeholder implementation
    # TODO: Query from TLStockData model

    logger.debug(f"Fetching sector for {symbol}...")

    # Sample sector mapping
    sector_map = {
        'RELIANCE': 'ENERGY',
        'TCS': 'IT',
        'INFY': 'IT',
        'HDFCBANK': 'BANKING',
        'ICICIBANK': 'BANKING',
        'BHARTIARTL': 'TELECOM',
        'ITC': 'FMCG',
        'HINDUNILVR': 'FMCG',
        'MARUTI': 'AUTO',
        'TATAMOTORS': 'AUTO',
        'SUNPHARMA': 'PHARMA',
        'DRREDDY': 'PHARMA',
    }

    sector = sector_map.get(symbol, 'UNKNOWN')

    logger.debug(f"{symbol} → {sector}")

    return sector


def get_sector_index(sector: str) -> str:
    """
    Get sector index symbol for a sector

    Args:
        sector: Sector name (e.g., 'IT', 'BANKING')

    Returns:
        str: Sector index symbol (e.g., 'CNXIT', 'BANKNIFTY')
    """

    sector_index = SECTOR_INDEX_MAP.get(sector, 'NIFTY')

    logger.debug(f"Sector {sector} → Index {sector_index}")

    return sector_index


def get_performance(index_symbol: str, days: int) -> Decimal:
    """
    Get performance (% change) of an index over N days

    Args:
        index_symbol: Index symbol (e.g., 'CNXIT', 'BANKNIFTY')
        days: Number of days to look back

    Returns:
        Decimal: Percentage change (e.g., 2.5 for +2.5%, -1.8 for -1.8%)

    TODO: Query from HistoricalPrice model or broker API
    """

    logger.debug(f"Calculating {days}D performance for {index_symbol}...")

    # Placeholder implementation
    # TODO: Query actual historical data

    # Mock data - simulate different scenarios
    if days == 3:
        # 3-day performance
        performance = Decimal('1.2')
    elif days == 7:
        # 7-day performance
        performance = Decimal('2.5')
    elif days == 21:
        # 21-day performance
        performance = Decimal('4.8')
    else:
        performance = Decimal('0.0')

    logger.debug(f"{index_symbol} {days}D performance: {performance:+.2f}%")

    return performance


def analyze_sector(symbol: str) -> Dict:
    """
    Analyze sector strength across multiple timeframes

    CRITICAL RULE:
    - For LONG: ALL timeframes (3D, 7D, 21D) must be POSITIVE
    - For SHORT: ALL timeframes (3D, 7D, 21D) must be NEGATIVE
    - Mixed signals → DON'T TRADE (wait for clarity)

    This is a NON-NEGOTIABLE filter.

    Args:
        symbol: Stock symbol to analyze

    Returns:
        dict: {
            'verdict': str,  # 'STRONG_BULLISH', 'STRONG_BEARISH', 'MIXED'
            'allow_long': bool,
            'allow_short': bool,
            'reason': str,
            'performance': {
                '3d': Decimal,
                '7d': Decimal,
                '21d': Decimal
            },
            'sector': str,
            'sector_index': str
        }
    """

    logger.info(f"=" * 80)
    logger.info(f"SECTOR ANALYSIS: {symbol}")
    logger.info(f"=" * 80)

    try:
        # Get stock sector
        sector = get_stock_sector(symbol)
        sector_index = get_sector_index(sector)

        logger.info(f"Symbol: {symbol}")
        logger.info(f"Sector: {sector}")
        logger.info(f"Sector Index: {sector_index}")
        logger.info("")

        # Multi-timeframe performance
        logger.info("Multi-Timeframe Performance:")
        logger.info("-" * 80)

        perf_3d = get_performance(sector_index, days=3)
        perf_7d = get_performance(sector_index, days=7)
        perf_21d = get_performance(sector_index, days=21)

        logger.info(f"  3-Day:  {perf_3d:+.2f}%")
        logger.info(f"  7-Day:  {perf_7d:+.2f}%")
        logger.info(f"  21-Day: {perf_21d:+.2f}%")
        logger.info("")

        # Determine verdict based on CRITICAL RULE
        logger.info("Sector Verdict:")
        logger.info("-" * 80)

        # For LONG: ALL must be positive
        if perf_3d > 0 and perf_7d > 0 and perf_21d > 0:
            verdict = 'STRONG_BULLISH'
            allow_long = True
            allow_short = False
            reason = (
                f'All timeframes positive - strong sector tailwind '
                f'(3D: +{perf_3d:.1f}%, 7D: +{perf_7d:.1f}%, 21D: +{perf_21d:.1f}%)'
            )
            logger.info(f"✅ {verdict}")
            logger.info(f"   → LONG positions allowed")
            logger.info(f"   → SHORT positions blocked")
            logger.info(f"   Reason: {reason}")

        # For SHORT: ALL must be negative
        elif perf_3d < 0 and perf_7d < 0 and perf_21d < 0:
            verdict = 'STRONG_BEARISH'
            allow_long = False
            allow_short = True
            reason = (
                f'All timeframes negative - strong sector headwind '
                f'(3D: {perf_3d:.1f}%, 7D: {perf_7d:.1f}%, 21D: {perf_21d:.1f}%)'
            )
            logger.info(f"✅ {verdict}")
            logger.info(f"   → SHORT positions allowed")
            logger.info(f"   → LONG positions blocked")
            logger.info(f"   Reason: {reason}")

        # Mixed signals → DON'T TRADE
        else:
            verdict = 'MIXED'
            allow_long = False
            allow_short = False

            # Identify which timeframes are mixed
            mixed_details = []
            if perf_3d > 0:
                mixed_details.append("3D: bullish")
            else:
                mixed_details.append("3D: bearish")

            if perf_7d > 0:
                mixed_details.append("7D: bullish")
            else:
                mixed_details.append("7D: bearish")

            if perf_21d > 0:
                mixed_details.append("21D: bullish")
            else:
                mixed_details.append("21D: bearish")

            reason = f'Mixed sector signals - no clear trend ({", ".join(mixed_details)})'

            logger.warning(f"❌ {verdict}")
            logger.warning(f"   → BOTH LONG and SHORT positions blocked")
            logger.warning(f"   Reason: {reason}")

        logger.info("")
        logger.info(f"=" * 80)

        return {
            'verdict': verdict,
            'allow_long': allow_long,
            'allow_short': allow_short,
            'reason': reason,
            'performance': {
                '3d': perf_3d,
                '7d': perf_7d,
                '21d': perf_21d
            },
            'sector': sector,
            'sector_index': sector_index
        }

    except Exception as e:
        logger.error(f"Sector analysis failed for {symbol}: {e}", exc_info=True)

        # On error, fail safely (block trade)
        return {
            'verdict': 'ERROR',
            'allow_long': False,
            'allow_short': False,
            'reason': f'Sector analysis failed: {str(e)}',
            'performance': {
                '3d': Decimal('0'),
                '7d': Decimal('0'),
                '21d': Decimal('0')
            },
            'sector': 'UNKNOWN',
            'sector_index': 'UNKNOWN'
        }


def get_strong_sectors(min_performance: Decimal = Decimal('2.0')) -> List[Dict]:
    """
    Get list of sectors with strong bullish performance across all timeframes

    Args:
        min_performance: Minimum % performance on 21D timeframe

    Returns:
        list: List of sector analysis dictionaries for strong sectors
    """

    logger.info(f"Scanning for strong sectors (min 21D performance: {min_performance}%)...")

    strong_sectors = []

    # Scan all sector indices
    for sector, sector_index in SECTOR_INDEX_MAP.items():
        perf_3d = get_performance(sector_index, days=3)
        perf_7d = get_performance(sector_index, days=7)
        perf_21d = get_performance(sector_index, days=21)

        # Check if all timeframes positive and meet minimum threshold
        if perf_3d > 0 and perf_7d > 0 and perf_21d >= min_performance:
            strong_sectors.append({
                'sector': sector,
                'sector_index': sector_index,
                'performance': {
                    '3d': perf_3d,
                    '7d': perf_7d,
                    '21d': perf_21d
                }
            })

            logger.info(
                f"  ✅ {sector} ({sector_index}): "
                f"3D: +{perf_3d:.1f}%, 7D: +{perf_7d:.1f}%, 21D: +{perf_21d:.1f}%"
            )

    logger.info(f"Found {len(strong_sectors)} strong sectors")

    return strong_sectors


def get_weak_sectors(max_performance: Decimal = Decimal('-2.0')) -> List[Dict]:
    """
    Get list of sectors with strong bearish performance across all timeframes

    Args:
        max_performance: Maximum % performance on 21D timeframe (negative)

    Returns:
        list: List of sector analysis dictionaries for weak sectors
    """

    logger.info(f"Scanning for weak sectors (max 21D performance: {max_performance}%)...")

    weak_sectors = []

    # Scan all sector indices
    for sector, sector_index in SECTOR_INDEX_MAP.items():
        perf_3d = get_performance(sector_index, days=3)
        perf_7d = get_performance(sector_index, days=7)
        perf_21d = get_performance(sector_index, days=21)

        # Check if all timeframes negative and meet minimum threshold
        if perf_3d < 0 and perf_7d < 0 and perf_21d <= max_performance:
            weak_sectors.append({
                'sector': sector,
                'sector_index': sector_index,
                'performance': {
                    '3d': perf_3d,
                    '7d': perf_7d,
                    '21d': perf_21d
                }
            })

            logger.info(
                f"  ✅ {sector} ({sector_index}): "
                f"3D: {perf_3d:.1f}%, 7D: {perf_7d:.1f}%, 21D: {perf_21d:.1f}%"
            )

    logger.info(f"Found {len(weak_sectors)} weak sectors")

    return weak_sectors
