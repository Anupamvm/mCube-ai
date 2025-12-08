"""
Kotak Neo Symbol Mapper - Symbol Conversion Between Brokers

This module provides functions to map symbols between Neo and Breeze formats.
"""

import logging
import re
import csv
import io
import time
import calendar
import requests
from datetime import datetime, date

from .client import _get_authenticated_client

logger = logging.getLogger(__name__)


# Cache for Neo scrip master (to avoid repeated downloads)
_neo_scrip_master_cache = {'data': None, 'timestamp': None}
_CACHE_DURATION_SECONDS = 3600  # 1 hour


def _get_neo_scrip_master(client) -> list:
    """
    Get Neo scrip master with caching.
    Returns list of all contracts from CSV.
    """
    global _neo_scrip_master_cache

    # Check cache
    current_time = time.time()
    if (_neo_scrip_master_cache['data'] is not None and
        _neo_scrip_master_cache['timestamp'] is not None and
        (current_time - _neo_scrip_master_cache['timestamp']) < _CACHE_DURATION_SECONDS):
        logger.info("[SCRIP MASTER] Using cached scrip master")
        return _neo_scrip_master_cache['data']

    logger.info("[SCRIP MASTER] Downloading Neo scrip master...")

    try:
        # Get scrip master URL from Neo API
        scrip_master_url = client.scrip_master(exchange_segment='nse_fo')

        if not scrip_master_url or not isinstance(scrip_master_url, str):
            logger.error("[SCRIP MASTER] Invalid scrip master response")
            return []

        # If it's a URL, download it
        if scrip_master_url.startswith('http'):
            response = requests.get(scrip_master_url, timeout=30)
            if response.status_code != 200:
                logger.error(f"[SCRIP MASTER] Failed to download CSV: {response.status_code}")
                return []
            scrip_master_csv = response.text
        else:
            scrip_master_csv = scrip_master_url

        # Parse CSV
        reader = csv.DictReader(io.StringIO(scrip_master_csv))
        contracts = list(reader)

        logger.info(f"[SCRIP MASTER] Downloaded {len(contracts)} contracts")

        # Cache the data
        _neo_scrip_master_cache['data'] = contracts
        _neo_scrip_master_cache['timestamp'] = current_time

        return contracts

    except Exception as e:
        logger.error(f"[SCRIP MASTER] Error downloading: {e}")
        return []


def map_neo_symbol_to_breeze(neo_symbol: str) -> dict:
    """
    Map Neo (Kotak) futures symbol to Breeze (ICICI) format for getting live quotes.

    Neo Format: NIFTY26JANFUT, BANKNIFTY25DECFUT
    Breeze Format: stock_code + expiry_date (separate parameters)

    Args:
        neo_symbol (str): Neo trading symbol (e.g., 'NIFTY26JANFUT', 'BANKNIFTY25DECFUT')

    Returns:
        dict: {
            'success': bool,
            'stock_code': str,  # e.g., 'NIFTY', 'BANKNIFTY'
            'expiry_date': str,  # e.g., '30-JAN-2026' (DD-MMM-YYYY format)
            'product_type': str,  # 'futures'
            'exchange_code': str,  # 'NFO'
            'error': str (if failed)
        }

    Example:
        >>> result = map_neo_symbol_to_breeze('NIFTY26JANFUT')
        >>> # Returns: {'success': True, 'stock_code': 'NIFTY', 'expiry_date': '30-JAN-2026', ...}
    """
    try:
        # Parse Neo futures symbol: NIFTY26JANFUT or BANKNIFTY25DECFUT
        # Pattern: (SYMBOL)(YY)(MMM)FUT
        pattern = r'^([A-Z]+)(\d{2})([A-Z]{3})FUT$'
        match = re.match(pattern, neo_symbol)

        if not match:
            return {
                'success': False,
                'error': f'Invalid Neo futures symbol format: {neo_symbol}',
                'stock_code': None,
                'expiry_date': None,
                'product_type': 'futures',
                'exchange_code': 'NFO'
            }

        stock_code = match.group(1)  # NIFTY or BANKNIFTY
        year_suffix = match.group(2)  # 26, 25
        month_name = match.group(3)  # JAN, DEC

        # Convert year suffix to full year (26 -> 2026, 25 -> 2025)
        year = 2000 + int(year_suffix)

        # Convert month name to month number
        month_map = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        month = month_map.get(month_name)

        if not month:
            return {
                'success': False,
                'error': f'Invalid month in symbol: {month_name}',
                'stock_code': None,
                'expiry_date': None,
                'product_type': 'futures',
                'exchange_code': 'NFO'
            }

        # Calculate last trading Thursday of the month (standard F&O expiry)
        last_day = calendar.monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        # Find last Thursday
        last_thursday = last_date
        while last_thursday.weekday() != 3:  # 3 = Thursday
            last_thursday = date(year, month, last_thursday.day - 1)

        # Format expiry date as DD-Mon-YYYY (Breeze format with title case month)
        expiry_date = last_thursday.strftime('%d-%b-%Y')

        logger.info(f"[NEO->BREEZE MAPPING] {neo_symbol} -> stock_code={stock_code}, expiry={expiry_date}")

        return {
            'success': True,
            'stock_code': stock_code,
            'expiry_date': expiry_date,
            'product_type': 'futures',
            'exchange_code': 'NFO',
            'error': None
        }

    except Exception as e:
        logger.error(f"Error mapping Neo symbol to Breeze: {e}")
        return {
            'success': False,
            'error': str(e),
            'stock_code': None,
            'expiry_date': None,
            'product_type': 'futures',
            'exchange_code': 'NFO'
        }


def map_breeze_symbol_to_neo(breeze_symbol: str, expiry_date=None, client=None) -> dict:
    """
    Map Breeze (ICICI) symbol format to Kotak Neo trading symbol.

    CRITICAL: Breeze and Neo use different symbol formats!
    - Breeze: NIFTY02DEC27050CE (day-based format)
    - Neo: Must be fetched via search_scrip API

    Args:
        breeze_symbol (str): Breeze format symbol (e.g., 'NIFTY02DEC27050CE')
        expiry_date (date): Optional expiry date object for precise matching
        client: Optional authenticated Neo client to reuse

    Returns:
        dict: {
            'success': bool,
            'neo_symbol': str,  # Actual Neo trading symbol from pTrdSymbol
            'lot_size': int,
            'token': str,
            'expiry': str,
            'error': str (if failed)
        }
    """
    try:
        # Use provided client or get new one
        if client is None:
            client = _get_authenticated_client()

        # Parse Breeze symbol: NIFTY02DEC27050CE
        # Pattern: (SYMBOL)(DDMMM)(STRIKE)(CE|PE)
        pattern = r'^([A-Z]+)(\d{2}[A-Z]{3})(\d+)(CE|PE)$'
        match = re.match(pattern, breeze_symbol)

        if not match:
            logger.error(f"Invalid Breeze symbol format: {breeze_symbol}")
            return {
                'success': False,
                'error': f'Invalid symbol format: {breeze_symbol}',
                'neo_symbol': None,
                'lot_size': 75,
                'token': None
            }

        symbol_name = match.group(1)  # NIFTY
        expiry_ddmmm = match.group(2)  # 02DEC
        strike_price = match.group(3)  # 27050
        option_type = match.group(4)  # CE or PE

        logger.info(f"[SYMBOL MAPPING] Breeze: {breeze_symbol} -> Parsed: symbol={symbol_name}, expiry={expiry_ddmmm}, strike={strike_price}, type={option_type}")

        # Get scrip master from Neo
        scrip_master = _get_neo_scrip_master(client)

        if not scrip_master:
            logger.error("[SYMBOL MAPPING] Failed to get scrip master")
            return {
                'success': False,
                'error': 'Failed to download Neo scrip master',
                'neo_symbol': None,
                'lot_size': 75,
                'token': None
            }

        # Filter for matching contracts
        matching_contracts = []

        for contract in scrip_master:
            # Check if it's a NIFTY option
            if contract.get('pSymbolName') != symbol_name:
                continue

            # Check option type
            if contract.get('pOptionType') != option_type:
                continue

            # Check strike price (handle scientific notation)
            contract_strike_raw = str(contract.get('dStrikePrice;', ''))
            try:
                contract_strike_float = float(contract_strike_raw.replace(',', ''))
                contract_strike = contract_strike_float / 100
                target_strike = float(strike_price)

                if abs(contract_strike - target_strike) > 0.1:
                    continue
            except (ValueError, AttributeError):
                if str(strike_price) not in contract_strike_raw:
                    continue

            # Check if expiry matches
            neo_symbol = contract.get('pTrdSymbol', '')
            expiry_day = expiry_ddmmm[:2]

            if expiry_date:
                year_short = expiry_date.strftime('%y')
                month_code = expiry_date.strftime('%b')[0].upper()
                date_pattern = f"{year_short}{month_code}{expiry_day}"

                if date_pattern in neo_symbol:
                    matching_contracts.append(contract)

        if matching_contracts:
            contract = matching_contracts[0]
            neo_symbol = contract.get('pTrdSymbol', '')
            lot_size = int(contract.get('lLotSize', 75))

            logger.info(f"[SYMBOL MAPPING] Found Neo symbol: {neo_symbol}, lot_size={lot_size}")

            return {
                'success': True,
                'neo_symbol': str(neo_symbol),
                'lot_size': lot_size,
                'token': str(neo_symbol),
                'expiry': expiry_date.strftime('%d%b%Y').upper() if expiry_date else '',
                'error': None
            }
        else:
            logger.error(f"[SYMBOL MAPPING] No matching contract found for {breeze_symbol}")
            return {
                'success': False,
                'error': f'No matching Neo contract found for {breeze_symbol}',
                'neo_symbol': None,
                'lot_size': 75,
                'token': None
            }

    except Exception as e:
        logger.error(f"[SYMBOL MAPPING] Error mapping {breeze_symbol}: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'neo_symbol': None,
            'lot_size': 75,
            'token': None
        }
