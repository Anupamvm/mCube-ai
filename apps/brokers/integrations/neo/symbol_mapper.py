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

    # Validate client
    if client is None:
        logger.error("[SCRIP MASTER] Client is None - cannot download scrip master")
        return []

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
        scrip_master_result = client.scrip_master(exchange_segment='nse_fo')
        logger.info(f"[SCRIP MASTER] scrip_master() returned type: {type(scrip_master_result)}")

        # Handle dict response (may contain URL in a field)
        if isinstance(scrip_master_result, dict):
            # Check if it's an error response
            if 'error' in scrip_master_result or scrip_master_result.get('stat') == 'Not_Ok':
                logger.error(f"[SCRIP MASTER] API error response: {scrip_master_result}")
                return []
            # Try to extract URL from dict
            scrip_master_url = scrip_master_result.get('url') or scrip_master_result.get('data')
            logger.info(f"[SCRIP MASTER] Extracted from dict: {type(scrip_master_url)}")
        else:
            scrip_master_url = scrip_master_result

        if not scrip_master_url or not isinstance(scrip_master_url, str):
            logger.error(f"[SCRIP MASTER] Invalid scrip master response: {type(scrip_master_url)}, value: {str(scrip_master_url)[:200]}")
            return []

        # If it's a URL, download it with retry logic
        if scrip_master_url.startswith('http'):
            logger.info(f"[SCRIP MASTER] Downloading from URL: {scrip_master_url[:100]}...")

            max_retries = 3
            scrip_master_csv = None

            for attempt in range(1, max_retries + 1):
                try:
                    # Use longer timeout (120s) and separate connect/read timeouts
                    response = requests.get(scrip_master_url, timeout=(30, 120))
                    if response.status_code != 200:
                        logger.error(f"[SCRIP MASTER] Failed to download CSV: {response.status_code}")
                        return []
                    scrip_master_csv = response.text
                    break  # Success, exit retry loop
                except requests.exceptions.Timeout as e:
                    logger.warning(f"[SCRIP MASTER] Timeout on attempt {attempt}/{max_retries}: {e}")
                    if attempt == max_retries:
                        raise
                    time.sleep(2)  # Wait before retry
                except requests.exceptions.ConnectionError as e:
                    logger.warning(f"[SCRIP MASTER] Connection error on attempt {attempt}/{max_retries}: {e}")
                    if attempt == max_retries:
                        raise
                    time.sleep(2)  # Wait before retry

            if scrip_master_csv is None:
                logger.error("[SCRIP MASTER] Failed to download after all retries")
                return []
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
        logger.error(f"[SCRIP MASTER] Error downloading: {e}", exc_info=True)
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

    Uses Neo's pScripRefKey for exact matching (most reliable method).
    - Breeze format: NIFTY09JAN24400CE
    - Neo pScripRefKey: NIFTY09JAN2624400.00CE

    Args:
        breeze_symbol (str): Breeze format symbol (e.g., 'NIFTY09JAN24400CE')
        expiry_date (date): Required - expiry date for year determination
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
            logger.info("[SYMBOL MAPPING] No client provided, getting authenticated client...")
            try:
                client = _get_authenticated_client()
                logger.info(f"[SYMBOL MAPPING] Got authenticated client: {client}")
            except Exception as auth_error:
                logger.error(f"[SYMBOL MAPPING] Failed to authenticate: {auth_error}")
                return {
                    'success': False,
                    'error': f'Neo authentication failed: {str(auth_error)}',
                    'neo_symbol': None,
                    'lot_size': 75,
                    'token': None
                }

        # Parse Breeze symbol: NIFTY09JAN24400CE
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
        expiry_ddmmm = match.group(2)  # 09JAN
        strike_price = match.group(3)  # 24400
        option_type = match.group(4)  # CE or PE

        logger.info(f"[SYMBOL MAPPING] Breeze: {breeze_symbol} -> Parsed: symbol={symbol_name}, expiry={expiry_ddmmm}, strike={strike_price}, type={option_type}")

        if not expiry_date:
            logger.error("[SYMBOL MAPPING] expiry_date is required for Neo symbol mapping")
            return {
                'success': False,
                'error': 'expiry_date is required for Neo symbol mapping',
                'neo_symbol': None,
                'lot_size': 75,
                'token': None
            }

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

        # Build the expected pScripRefKey pattern for exact matching
        # Format: SYMBOL + DDMMM + YY + STRIKE.00 + TYPE
        # Example: NIFTY09JAN2624400.00CE
        year_short = expiry_date.strftime('%y')  # '26' for 2026
        expected_scrip_ref = f"{symbol_name}{expiry_ddmmm}{year_short}{strike_price}.00{option_type}"

        logger.info(f"[SYMBOL MAPPING] Looking for pScripRefKey: {expected_scrip_ref}")

        # Search for exact match in scrip master
        matching_contract = None
        for contract in scrip_master:
            scrip_ref = contract.get('pScripRefKey', '')
            if scrip_ref == expected_scrip_ref:
                matching_contract = contract
                break

        if matching_contract:
            neo_symbol = matching_contract.get('pTrdSymbol', '')
            lot_size = int(matching_contract.get('lLotSize', 75))

            logger.info(f"[SYMBOL MAPPING] Found Neo symbol: {neo_symbol}, lot_size={lot_size}")

            return {
                'success': True,
                'neo_symbol': str(neo_symbol),
                'lot_size': lot_size,
                'token': str(neo_symbol),
                'expiry': expiry_date.strftime('%d%b%Y').upper(),
                'error': None
            }
        else:
            # Log available contracts for debugging
            available = [c.get('pScripRefKey', '') for c in scrip_master
                        if c.get('pSymbolName') == symbol_name
                        and c.get('pOptionType') == option_type][:10]
            logger.error(f"[SYMBOL MAPPING] No match for {expected_scrip_ref}. Available samples: {available}")

            return {
                'success': False,
                'error': f'No matching Neo contract found for {breeze_symbol} (expected pScripRefKey: {expected_scrip_ref})',
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
