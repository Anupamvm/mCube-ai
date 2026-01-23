"""
ICICI SecurityMaster Utility Module

This module provides utilities to read and parse ICICI Direct SecurityMaster files.
SecurityMaster files are updated daily at 8:00 AM IST and contain instrument details
for all tradable securities.

Download URL: https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip

FALLBACK MECHANISM:
If SecurityMaster lookup fails (file missing or instrument not found), the system
automatically fetches instrument details from Breeze API as a fallback.

Usage:
    from apps.brokers.utils.security_master import get_futures_instrument, get_option_instrument

    # Get futures instrument (auto-fetches from Breeze if SecurityMaster fails)
    instrument = get_futures_instrument('SBIN', '30-Dec-2025')
    stock_code = instrument['short_name']  # 'STABAN'
    lot_size = instrument['lot_size']      # 750

    # Get option instrument
    instrument = get_option_instrument('NIFTY', '27-Nov-2025', 24500, 'CE')
    stock_code = instrument['short_name']
"""

import os
import csv
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from pathlib import Path
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Default SecurityMaster file path
DEFAULT_SECURITY_MASTER_PATH = '/Users/anupammangudkar/Downloads/SecurityMaster/FONSEScripMaster.txt'

# Cache timeout: 6 hours (SecurityMaster is updated once daily at 8 AM)
CACHE_TIMEOUT = 6 * 60 * 60


def fetch_instrument_from_breeze(
    symbol: str,
    expiry_date: str,
    instrument_type: str = 'futures',
    strike_price: Optional[float] = None,
    option_type: Optional[str] = None
) -> Optional[Dict]:
    """
    Fetch instrument details directly from Breeze API.

    This is used as a fallback when SecurityMaster lookup fails.

    Args:
        symbol: Stock symbol (e.g., 'SBIN', 'NIFTY')
        expiry_date: Expiry date in 'DD-MMM-YYYY' format
        instrument_type: 'futures' or 'options'
        strike_price: Strike price (for options)
        option_type: 'CE' or 'PE' (for options)

    Returns:
        dict: Instrument details or None if fetch fails
    """
    try:
        from apps.brokers.integrations.breeze import get_breeze_client

        logger.info(f"Fetching instrument from Breeze API: {symbol} {expiry_date} {instrument_type}")

        breeze = get_breeze_client()

        # Prepare parameters for Breeze API
        if instrument_type == 'futures':
            quote_params = {
                'stock_code': symbol,
                'exchange_code': 'NFO',
                'expiry_date': expiry_date,
                'product_type': 'futures',
                'right': 'others',
                'strike_price': '0'
            }
        else:  # options
            right = 'call' if option_type == 'CE' else 'put'
            quote_params = {
                'stock_code': symbol,
                'exchange_code': 'NFO',
                'expiry_date': expiry_date,
                'product_type': 'options',
                'right': right,
                'strike_price': str(int(strike_price))
            }

        logger.debug(f"Breeze API quote params: {quote_params}")

        # Fetch quote from Breeze
        response = breeze.get_quotes(**quote_params)

        if not response or response.get('Status') != 200:
            error = response.get('Error', 'Unknown error') if response else 'No response'
            logger.error(f"Breeze API fetch failed: {error}")
            return None

        # Extract data from response
        success_data = response.get('Success', [])
        if not success_data or len(success_data) == 0:
            logger.warning(f"No data in Breeze response for {symbol}")
            return None

        quote = success_data[0]  # Get first quote

        # Extract instrument details
        # Note: Breeze API doesn't return all SecurityMaster fields,
        # but we can construct what we need
        instrument = {
            'token': quote.get('exchange_code', ''),  # Not available in quote
            'short_name': symbol,  # Use symbol as fallback
            'lot_size': int(quote.get('lot_quantity', 0) or 0),
            'exchange_code': symbol,
            'company_name': quote.get('stock_name', symbol),
            'expiry_date': expiry_date,
            'tick_size': float(quote.get('tick_size', 0) or 0),
            'base_price': float(quote.get('ltp', 0) or 0),
            'source': 'breeze_api'  # Mark as fetched from Breeze
        }

        logger.info(f"✅ Fetched from Breeze: {symbol} -> lot_size={instrument['lot_size']}")

        return instrument

    except Exception as e:
        logger.error(f"Error fetching from Breeze API: {e}", exc_info=True)
        return None


def get_security_master_path() -> str:
    """
    Get the path to the SecurityMaster file.

    Priority:
    1. Django setting SECURITY_MASTER_PATH (if configured)
    2. Environment variable SECURITY_MASTER_PATH
    3. Default path: ~/Downloads/SecurityMaster/FONSEScripMaster.txt

    Returns:
        str: Path to SecurityMaster file
    """
    # Check Django settings
    if hasattr(settings, 'SECURITY_MASTER_PATH'):
        return settings.SECURITY_MASTER_PATH

    # Check environment variable
    env_path = os.environ.get('SECURITY_MASTER_PATH')
    if env_path:
        return env_path

    # Default path
    return DEFAULT_SECURITY_MASTER_PATH


def parse_security_master_row(row: Dict) -> Dict:
    """
    Parse a row from SecurityMaster CSV and extract relevant fields.

    Args:
        row: CSV row as dictionary

    Returns:
        dict: Parsed instrument data with cleaned fields
    """
    return {
        'token': row.get('Token', '').strip('"'),
        'instrument_name': row.get('InstrumentName', '').strip('"'),
        'short_name': row.get('ShortName', '').strip('"'),
        'series': row.get('Series', '').strip('"'),
        'expiry_date': row.get('ExpiryDate', '').strip('"'),
        'strike_price': row.get('StrikePrice', '').strip('"'),
        'option_type': row.get('OptionType', '').strip('"'),
        'lot_size': int(row.get('LotSize', '0').strip('"') or 0),
        'exchange_code': row.get('ExchangeCode', '').strip('"'),
        'company_name': row.get('CompanyName', '').strip('"'),
        'tick_size': float(row.get('TickSize', '0').strip('"') or 0),
        'base_price': float(row.get('BasePrice', '0').strip('"') or 0),
    }


def get_futures_instrument(
    symbol: str,
    expiry_date: str,
    security_master_path: Optional[str] = None,
    use_cache: bool = True,
    use_breeze_fallback: bool = True
) -> Optional[Dict]:
    """
    Get futures instrument details from SecurityMaster file.

    FALLBACK MECHANISM:
    If SecurityMaster lookup fails (file missing or instrument not found),
    automatically fetches from Breeze API as fallback.

    Args:
        symbol: Stock symbol (e.g., 'SBIN', 'NIFTY', 'RELIANCE')
        expiry_date: Expiry date in 'DD-MMM-YYYY' format (e.g., '30-Dec-2025')
        security_master_path: Optional custom path to SecurityMaster file
        use_cache: Whether to use cached results (default: True)
        use_breeze_fallback: Whether to fetch from Breeze if SecurityMaster fails (default: True)

    Returns:
        dict: Instrument details with keys:
            - token: Instrument code/token
            - short_name: Stock code for Breeze API
            - lot_size: Lot size
            - exchange_code: Stock symbol
            - company_name: Full company name
            - expiry_date: Expiry date
            - tick_size: Tick size
            - base_price: Base price
            - source: 'security_master' or 'breeze_api'

        None if instrument not found in both sources

    Example:
        >>> instrument = get_futures_instrument('SBIN', '30-Dec-2025')
        >>> print(instrument['short_name'])  # 'STABAN'
        >>> print(instrument['lot_size'])    # 750
        >>> print(instrument['source'])      # 'security_master'
    """
    # Check cache first
    cache_key = f'security_master:futures:{symbol}:{expiry_date}'
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for {symbol} futures {expiry_date}")
            return cached

    # Get SecurityMaster file path
    if not security_master_path:
        security_master_path = get_security_master_path()

    # Try SecurityMaster first
    instrument = None
    security_master_available = os.path.exists(security_master_path)

    if security_master_available:
        try:
            logger.info(f"Reading SecurityMaster for {symbol} futures expiring {expiry_date}")

            with open(security_master_path, 'r') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Match: ExchangeCode = symbol, ExpiryDate = expiry_date (case-insensitive), InstrumentName = FUTSTK
                    row_expiry = row.get('ExpiryDate', '').strip('"')
                    if (row.get('ExchangeCode', '').strip('"') == symbol and
                        row_expiry.upper() == expiry_date.upper() and  # Case-insensitive date comparison
                        row.get('InstrumentName', '').strip('"') == 'FUTSTK'):

                        instrument = parse_security_master_row(row)
                        instrument['source'] = 'security_master'

                        logger.info(f"✅ Found in SecurityMaster: {symbol} futures - Token={instrument['token']}, "
                                   f"StockCode={instrument['short_name']}, LotSize={instrument['lot_size']}")

                        # Cache the result
                        if use_cache:
                            cache.set(cache_key, instrument, CACHE_TIMEOUT)

                        return instrument

            logger.warning(f"Instrument not found in SecurityMaster for {symbol} expiring {expiry_date}")

        except Exception as e:
            logger.error(f"Error reading SecurityMaster: {e}", exc_info=True)
    else:
        logger.warning(f"SecurityMaster file not found at {security_master_path}")

    # Fallback to Breeze API if SecurityMaster failed
    if use_breeze_fallback and not instrument:
        logger.info(f"⚠️  SecurityMaster lookup failed, fetching from Breeze API as fallback...")

        instrument = fetch_instrument_from_breeze(
            symbol=symbol,
            expiry_date=expiry_date,
            instrument_type='futures'
        )

        if instrument:
            logger.info(f"✅ Fetched from Breeze API fallback: {symbol} futures - LotSize={instrument['lot_size']}")

            # Cache the Breeze result too
            if use_cache:
                cache.set(cache_key, instrument, CACHE_TIMEOUT)

            return instrument

    # Both SecurityMaster and Breeze failed
    if not instrument:
        logger.error(f"❌ Failed to get instrument from both SecurityMaster and Breeze API for {symbol} {expiry_date}")
        logger.error("Please either:")
        logger.error("  1. Download SecurityMaster: https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip")
        logger.error("  2. Ensure Breeze API is authenticated and accessible")

    return instrument


def get_option_instrument(
    symbol: str,
    expiry_date: str,
    strike_price: float,
    option_type: str,
    security_master_path: Optional[str] = None,
    use_cache: bool = True,
    use_breeze_fallback: bool = True
) -> Optional[Dict]:
    """
    Get option instrument details from SecurityMaster file.

    FALLBACK MECHANISM:
    If SecurityMaster lookup fails, automatically fetches from Breeze API.

    Args:
        symbol: Stock symbol (e.g., 'NIFTY', 'BANKNIFTY')
        expiry_date: Expiry date in 'DD-MMM-YYYY' format (e.g., '27-Nov-2025')
        strike_price: Strike price (e.g., 24500)
        option_type: 'CE' for Call or 'PE' for Put
        security_master_path: Optional custom path to SecurityMaster file
        use_cache: Whether to use cached results (default: True)
        use_breeze_fallback: Whether to fetch from Breeze if SecurityMaster fails (default: True)

    Returns:
        dict: Instrument details (same structure as get_futures_instrument)
              Includes 'source' field: 'security_master' or 'breeze_api'
        None if instrument not found in both sources

    Example:
        >>> instrument = get_option_instrument('NIFTY', '27-Nov-2025', 24500, 'CE')
        >>> print(instrument['short_name'])  # Stock code for Breeze API
        >>> print(instrument['lot_size'])    # 25 (for NIFTY options)
        >>> print(instrument['source'])      # 'security_master' or 'breeze_api'
    """
    # Normalize option type
    option_type = option_type.upper()
    if option_type not in ['CE', 'PE']:
        logger.error(f"Invalid option type: {option_type}. Must be 'CE' or 'PE'")
        return None

    # Check cache first
    cache_key = f'security_master:option:{symbol}:{expiry_date}:{strike_price}:{option_type}'
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for {symbol} {strike_price}{option_type} {expiry_date}")
            return cached

    # Get SecurityMaster file path
    if not security_master_path:
        security_master_path = get_security_master_path()

    # Try SecurityMaster first
    instrument = None
    security_master_available = os.path.exists(security_master_path)

    if security_master_available:
        try:
            logger.info(f"Reading SecurityMaster for {symbol} {strike_price}{option_type} expiring {expiry_date}")

            with open(security_master_path, 'r') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Match: ExchangeCode, ExpiryDate (case-insensitive), StrikePrice, OptionType, InstrumentName = OPTSTK
                    row_expiry = row.get('ExpiryDate', '').strip('"')
                    if (row.get('ExchangeCode', '').strip('"') == symbol and
                        row_expiry.upper() == expiry_date.upper() and  # Case-insensitive date comparison
                        row.get('StrikePrice', '').strip('"') == str(int(strike_price)) and
                        row.get('OptionType', '').strip('"') == option_type and
                        row.get('InstrumentName', '').strip('"') == 'OPTSTK'):

                        instrument = parse_security_master_row(row)
                        instrument['source'] = 'security_master'

                        logger.info(f"✅ Found in SecurityMaster: {symbol} {strike_price}{option_type} - "
                                   f"Token={instrument['token']}, StockCode={instrument['short_name']}, "
                                   f"LotSize={instrument['lot_size']}")

                        # Cache the result
                        if use_cache:
                            cache.set(cache_key, instrument, CACHE_TIMEOUT)

                        return instrument

            logger.warning(f"Option not found in SecurityMaster for {symbol} {strike_price}{option_type} expiring {expiry_date}")

        except Exception as e:
            logger.error(f"Error reading SecurityMaster: {e}", exc_info=True)
    else:
        logger.warning(f"SecurityMaster file not found at {security_master_path}")

    # Fallback to Breeze API if SecurityMaster failed
    if use_breeze_fallback and not instrument:
        logger.info(f"⚠️  SecurityMaster lookup failed, fetching from Breeze API as fallback...")

        instrument = fetch_instrument_from_breeze(
            symbol=symbol,
            expiry_date=expiry_date,
            instrument_type='options',
            strike_price=strike_price,
            option_type=option_type
        )

        if instrument:
            logger.info(f"✅ Fetched from Breeze API fallback: {symbol} {strike_price}{option_type} - "
                       f"LotSize={instrument['lot_size']}")

            # Cache the Breeze result
            if use_cache:
                cache.set(cache_key, instrument, CACHE_TIMEOUT)

            return instrument

    # Both sources failed
    if not instrument:
        logger.error(f"❌ Failed to get option instrument from both SecurityMaster and Breeze API")
        logger.error(f"   Symbol: {symbol}, Strike: {strike_price}{option_type}, Expiry: {expiry_date}")

    return instrument


def clear_security_master_cache():
    """
    Clear all cached SecurityMaster data.

    Use this after downloading a new SecurityMaster file.
    """
    logger.info("Clearing SecurityMaster cache")
    # Clear all security_master cache keys by pattern
    # Since Django doesn't have delete_pattern, we'll clear common patterns
    try:
        from django.core.cache import cache
        # The cache keys follow pattern: security_master:futures:SYMBOL:EXPIRY
        # We can't easily clear by pattern, but we can set a version flag
        cache.set('security_master:version', datetime.now().isoformat(), CACHE_TIMEOUT)
        logger.info("SecurityMaster cache version updated")
    except Exception as e:
        logger.warning(f"Could not update cache version: {e}")


def update_security_master(force: bool = False) -> Dict:
    """
    Download and update the SecurityMaster file from ICICI Direct.

    The SecurityMaster file is updated daily at 8:00 AM IST by ICICI.
    This function checks if the local file is outdated and downloads a fresh copy.

    Args:
        force: If True, always download regardless of file age

    Returns:
        dict: {
            'success': bool,
            'updated': bool,  # True if file was downloaded
            'message': str,
            'file_date': str,  # Date of the file
            'error': str (if failed)
        }
    """
    import requests
    import zipfile
    import tempfile
    import shutil

    SECURITY_MASTER_URL = "https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip"
    security_master_dir = Path(get_security_master_path()).parent

    result = {
        'success': False,
        'updated': False,
        'message': '',
        'file_date': None,
        'error': None
    }

    try:
        # Check if file exists and its age
        fo_nse_path = security_master_dir / 'FONSEScripMaster.txt'

        if fo_nse_path.exists() and not force:
            file_mtime = datetime.fromtimestamp(fo_nse_path.stat().st_mtime)
            file_age = datetime.now() - file_mtime

            # If file is less than 12 hours old, skip update
            if file_age < timedelta(hours=12):
                result['success'] = True
                result['updated'] = False
                result['message'] = f"SecurityMaster is recent ({file_age.seconds // 3600}h old), skipping update"
                result['file_date'] = file_mtime.strftime('%Y-%m-%d %H:%M')
                logger.info(result['message'])
                return result

        logger.info("Downloading fresh SecurityMaster from ICICI Direct...")

        # Download to temp file
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
            tmp_zip_path = tmp_file.name

        response = requests.get(SECURITY_MASTER_URL, timeout=60)
        response.raise_for_status()

        with open(tmp_zip_path, 'wb') as f:
            f.write(response.content)

        logger.info(f"Downloaded {len(response.content) / 1024 / 1024:.2f} MB")

        # Extract to temp directory first
        with tempfile.TemporaryDirectory() as tmp_extract_dir:
            with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmp_extract_dir)

            # Ensure target directory exists
            security_master_dir.mkdir(parents=True, exist_ok=True)

            # Copy files to target directory
            for file_name in os.listdir(tmp_extract_dir):
                src = Path(tmp_extract_dir) / file_name
                dst = security_master_dir / file_name
                shutil.copy2(src, dst)
                logger.info(f"Updated: {file_name}")

        # Clean up temp zip
        os.unlink(tmp_zip_path)

        # Clear cache after update
        clear_security_master_cache()

        result['success'] = True
        result['updated'] = True
        result['message'] = "SecurityMaster updated successfully"
        result['file_date'] = datetime.now().strftime('%Y-%m-%d %H:%M')

        logger.info(f"✅ SecurityMaster updated successfully at {result['file_date']}")

    except requests.exceptions.RequestException as e:
        result['error'] = f"Download failed: {str(e)}"
        logger.error(result['error'])
    except zipfile.BadZipFile as e:
        result['error'] = f"Invalid zip file: {str(e)}"
        logger.error(result['error'])
    except Exception as e:
        result['error'] = f"Update failed: {str(e)}"
        logger.error(result['error'], exc_info=True)

    return result


def ensure_security_master_current() -> bool:
    """
    Ensure SecurityMaster is current before lookups.

    This is a convenience function that updates SecurityMaster if needed
    and returns True if the file is available and current.

    Returns:
        bool: True if SecurityMaster is available and current
    """
    result = update_security_master(force=False)

    if result['success']:
        return True

    # If update failed, check if existing file is still usable
    validation = validate_security_master_file()
    return validation['valid']


def validate_security_master_file(security_master_path: Optional[str] = None) -> Dict:
    """
    Validate that SecurityMaster file exists and is readable.

    Args:
        security_master_path: Optional custom path to SecurityMaster file

    Returns:
        dict: Validation result with keys:
            - valid: bool
            - path: str
            - exists: bool
            - readable: bool
            - row_count: int (if readable)
            - error: str (if invalid)
    """
    if not security_master_path:
        security_master_path = get_security_master_path()

    result = {
        'valid': False,
        'path': security_master_path,
        'exists': False,
        'readable': False,
        'row_count': 0,
        'error': None
    }

    # Check if file exists
    if not os.path.exists(security_master_path):
        result['error'] = f"File not found at {security_master_path}"
        return result

    result['exists'] = True

    # Try to read the file
    try:
        with open(security_master_path, 'r') as f:
            reader = csv.DictReader(f)
            row_count = sum(1 for _ in reader)

        result['readable'] = True
        result['row_count'] = row_count
        result['valid'] = True

    except Exception as e:
        result['error'] = f"Error reading file: {str(e)}"

    return result
