"""
Kotak Neo Quotes - LTP and Price Fetching

This module provides functions to fetch real-time quotes and LTP from Kotak Neo API.
"""

import logging
import re
from datetime import datetime

from .client import _get_authenticated_client
from .symbol_mapper import map_neo_symbol_to_breeze

logger = logging.getLogger(__name__)


def get_ltp_from_neo(trading_symbol: str, exchange_segment: str = 'nse_fo', client=None) -> float:
    """
    Get Last Traded Price (LTP) for a Neo trading symbol using Breeze API.

    This function maps Neo symbols to Breeze format and fetches real-time LTP
    from Breeze API for the actual traded instrument (futures contract).

    Args:
        trading_symbol (str): Neo trading symbol (e.g., 'NIFTY26JANFUT', 'BANKNIFTY25DECFUT')
        exchange_segment (str): Exchange segment (default: 'nse_fo')
        client: Optional authenticated Neo client (not used, kept for compatibility)

    Returns:
        float: Real-time LTP for the futures contract, or None if not found

    Example:
        >>> ltp = get_ltp_from_neo('NIFTY26JANFUT')
        >>> print(ltp)  # 26499.30 (real-time futures price from Breeze)
    """
    try:
        from apps.brokers.integrations.breeze import get_breeze_client

        # Map Neo symbol to Breeze format
        mapping = map_neo_symbol_to_breeze(trading_symbol)

        if not mapping['success']:
            logger.error(f"Failed to map Neo symbol to Breeze: {mapping['error']}")
            return None

        logger.info(f"Fetching real-time LTP for {trading_symbol} futures contract via Breeze")

        # Get Breeze client
        breeze = get_breeze_client()

        # Strategy 1: Get all futures contracts for this stock and match by month/year
        try:
            resp = breeze.get_option_chain_quotes(
                stock_code=mapping['stock_code'],
                exchange_code=mapping['exchange_code'],
                product_type=mapping['product_type'],
                expiry_date=""  # Empty string returns all available expiries
            )

            if resp and resp.get('Status') == 200:
                contracts = resp.get('Success', [])
                if contracts:
                    # Match contract by month and year (handles holiday adjustments)
                    calc_expiry = mapping['expiry_date']
                    calc_month_year = calc_expiry.split('-')[1:3]  # ['Jan', '2026']

                    for contract in contracts:
                        contract_expiry = contract.get('expiry_date', '')
                        if contract_expiry:
                            contract_month_year = contract_expiry.split('-')[1:3]

                            if contract_month_year == calc_month_year:
                                ltp = float(contract.get('ltp', 0))
                                if ltp > 0:
                                    logger.info(f"Real-time futures LTP for {trading_symbol}: {ltp:.2f}")
                                    logger.info(f"   Breeze expiry: {contract_expiry} (Neo mapped to {calc_expiry})")
                                    return ltp

        except Exception as e:
            logger.error(f"Error calling Breeze get_option_chain_quotes: {e}")

        # Final fallback to Neo search_scrip when Breeze also fails
        logger.info(f"Falling back to Neo search_scrip for {trading_symbol}")

        # Use provided client or get new one
        if client is None:
            client = _get_authenticated_client()

        # Extract base symbol from trading symbol
        match = re.match(r'^([A-Z]+)', trading_symbol)
        base_symbol = match.group(1) if match else trading_symbol

        logger.info(f"Fetching LTP from Neo search_scrip for {trading_symbol}")

        # Search using Neo API
        result = client.search_scrip(
            exchange_segment=exchange_segment,
            symbol=base_symbol
        )

        if result and isinstance(result, list):
            # Find exact match for trading symbol
            for scrip in result:
                if scrip.get('pTrdSymbol') == trading_symbol:
                    # Extract price from scrip data
                    base_price = float(scrip.get('pScripBasePrice', 0))

                    if base_price > 0:
                        # Divide by 100 to get actual price
                        ltp = base_price / 100
                        logger.info(f"LTP for {trading_symbol} from Neo (may be delayed): {ltp:.2f}")
                        return ltp

            logger.warning(f"No exact match found for {trading_symbol} in Neo search results")
            return None
        else:
            logger.warning(f"No scrip found for {trading_symbol} in Neo")
            return None

    except Exception as e:
        logger.error(f"Error fetching LTP for {trading_symbol}: {e}")
        return None


def get_lot_size_from_neo(trading_symbol: str, client=None) -> int:
    """
    Get lot size for a trading symbol using Neo API search_scrip.

    Handles both OPTIONS and FUTURES symbols.

    Args:
        trading_symbol (str): Trading symbol
            - Options: 'NIFTY25NOV27050CE', 'BANKNIFTY25DEC48000PE'
            - Futures: 'NIFTY26JANFUT', 'JIOFIN25DECFUT'
        client: Optional authenticated client to reuse

    Returns:
        int: Lot size for the symbol

    Example:
        >>> lot_size = get_lot_size_from_neo('NIFTY25NOV27050CE')  # 25 (options)
        >>> lot_size = get_lot_size_from_neo('JIOFIN25DECFUT')  # 2350 (futures)
    """
    try:
        # Use provided client or get new one
        if client is None:
            client = _get_authenticated_client()

        # Check if it's a FUTURES symbol: SYMBOL + YYMMMFUT
        futures_pattern = r'^([A-Z]+)(\d{2})([A-Z]{3})FUT$'
        futures_match = re.match(futures_pattern, trading_symbol)

        if futures_match:
            # It's a futures contract
            symbol_name = futures_match.group(1)

            logger.info(f"Detected FUTURES symbol: {trading_symbol}")

            # Search using Neo API (for futures, no strike or option_type needed)
            result = client.search_scrip(
                exchange_segment='nse_fo',
                symbol=symbol_name
            )

            if result and isinstance(result, list):
                # Find the matching futures contract
                for scrip in result:
                    if scrip.get('pTrdSymbol') == trading_symbol:
                        lot_size = scrip.get('lLotSize', scrip.get('iLotSize', 50))
                        logger.info(f"Found lot size for {trading_symbol}: {lot_size}")
                        return int(lot_size)

                logger.warning(f"No exact match found for {trading_symbol}, using first {symbol_name} contract")
                if len(result) > 0:
                    lot_size = result[0].get('lLotSize', result[0].get('iLotSize', 50))
                    logger.info(f"Found lot size for {symbol_name} futures: {lot_size}")
                    return int(lot_size)

            logger.warning(f"No scrip found for {trading_symbol}, using default lot size 50")
            return 50  # Default for futures

        # Check if it's an OPTIONS symbol
        options_pattern = r'^([A-Z]+)(\d{2}[A-Z]{3})(\d+)(CE|PE)$'
        options_match = re.match(options_pattern, trading_symbol)

        if options_match:
            # It's an options contract
            symbol_name = options_match.group(1)
            expiry_date = options_match.group(2)
            strike_price = options_match.group(3)
            option_type = options_match.group(4)

            # Convert expiry to Neo format
            current_year = datetime.now().year
            expiry_full = f"{expiry_date}{current_year}"

            logger.info(f"Detected OPTIONS symbol: {trading_symbol}")
            logger.info(f"Searching scrip: symbol={symbol_name}, expiry={expiry_full}, strike={strike_price}, type={option_type}")

            # Search using Neo API
            result = client.search_scrip(
                exchange_segment='nse_fo',
                symbol=symbol_name,
                expiry=expiry_full,
                option_type=option_type,
                strike_price=strike_price
            )

            if result and isinstance(result, list) and len(result) > 0:
                scrip = result[0]
                lot_size = scrip.get('lLotSize', scrip.get('iLotSize', 25))
                logger.info(f"Found lot size for {trading_symbol}: {lot_size}")
                return int(lot_size)
            else:
                logger.warning(f"No scrip found for {trading_symbol}, using default lot size 25")
                return 25  # Default for NIFTY options

        # Unknown format
        logger.warning(f"Unable to parse trading symbol: {trading_symbol}, using default lot size 50")
        return 50  # Default fallback

    except Exception as e:
        logger.error(f"Error fetching lot size for {trading_symbol}: {e}")
        logger.warning(f"Using default lot size 50")
        return 50  # Default fallback


def get_lot_size_from_neo_with_token(trading_symbol: str, client=None) -> dict:
    """
    Get lot size AND instrument token for a trading symbol using Neo API search_scrip.

    Args:
        trading_symbol (str): Trading symbol (e.g., 'NIFTY25NOV27050CE')
        client: Optional authenticated client to reuse

    Returns:
        dict: {
            'lot_size': int,
            'token': str,
            'expiry': str,
            'exchange_segment': str,
            'symbol': str
        }
    """
    try:
        # Use provided client or get new one
        if client is None:
            client = _get_authenticated_client()

        # Parse symbol to extract components
        pattern = r'^([A-Z]+)(\d{2}[A-Z]{3})(\d+)(CE|PE)$'
        match = re.match(pattern, trading_symbol)

        if not match:
            logger.warning(f"Unable to parse trading symbol: {trading_symbol}, using defaults")
            return {
                'lot_size': 75,
                'token': 'N/A',
                'expiry': 'N/A',
                'exchange_segment': 'nse_fo',
                'symbol': trading_symbol
            }

        symbol_name = match.group(1)
        expiry_date = match.group(2)
        strike_price = match.group(3)
        option_type = match.group(4)

        # Convert expiry to Neo format
        current_year = datetime.now().year
        expiry_full = f"{expiry_date}{current_year}"

        logger.info(f"Searching scrip with token: symbol={symbol_name}, expiry={expiry_full}, strike={strike_price}, type={option_type}")

        # Search using Neo API
        result = client.search_scrip(
            exchange_segment='nse_fo',
            symbol=symbol_name,
            expiry=expiry_full,
            option_type=option_type,
            strike_price=strike_price
        )

        if result and isinstance(result, list) and len(result) > 0:
            scrip = result[0]
            lot_size = scrip.get('lLotSize', scrip.get('iLotSize', 75))
            token = scrip.get('pTrdSymbol', scrip.get('pSymbol', 'N/A'))
            expiry_display = scrip.get('pExchSeg', expiry_full)

            logger.info(f"Found scrip details for {trading_symbol}: lot_size={lot_size}, token={token}")

            return {
                'lot_size': int(lot_size),
                'token': str(token),
                'expiry': expiry_display,
                'exchange_segment': 'nse_fo',
                'symbol': trading_symbol
            }
        else:
            logger.warning(f"No scrip found for {trading_symbol}, using defaults")
            return {
                'lot_size': 75,
                'token': 'N/A',
                'expiry': expiry_full,
                'exchange_segment': 'nse_fo',
                'symbol': trading_symbol
            }

    except Exception as e:
        logger.error(f"Error fetching scrip details for {trading_symbol}: {e}")
        return {
            'lot_size': 75,
            'token': 'N/A',
            'expiry': 'N/A',
            'exchange_segment': 'nse_fo',
            'symbol': trading_symbol
        }
