"""
ICICI Breeze Option Chain - Option Chain Data Fetching

This module provides functions to fetch and save option chain data.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from apps.brokers.models import OptionChainQuote
from apps.data.models import OptionChain

from .client import get_breeze_client
from .quotes import get_nifty_quote
from .expiry import get_next_nifty_expiry, get_all_nifty_expiry_dates

logger = logging.getLogger(__name__)


def get_and_save_option_chain_quotes(stock_code, expiry_date=None, product_type="futures"):
    """
    Fetch option chain quotes from Breeze API and save to database.

    Args:
        stock_code: Stock/index code (e.g., 'NIFTY')
        expiry_date: Expiry date in 'DD-MMM-YYYY' format (if None, fetches from NSE)
        product_type: 'futures' or 'options'

    Returns:
        list: List of OptionChainQuote objects created

    Raises:
        Exception: If API call fails
    """
    breeze = get_breeze_client()

    if not expiry_date:
        expiry_date = get_next_nifty_expiry()

    logger.info(f"Fetching option chain for {stock_code}, expiry: {expiry_date}")

    # Convert to date object for storage
    expiry_date_obj = datetime.strptime(expiry_date, "%d-%b-%Y").date()

    # Delete old quotes for this stock and product type
    OptionChainQuote.objects.filter(
        stock_code=stock_code,
        product_type__iexact=product_type
    ).delete()

    quotes = []
    if product_type == "options":
        for right in ["call", "put"]:
            resp = breeze.get_option_chain_quotes(
                stock_code=stock_code,
                exchange_code="NFO",
                product_type=product_type,
                expiry_date=expiry_date,
                right=right,
            )
            quotes.extend(resp.get("Success", []))
    else:
        resp = breeze.get_option_chain_quotes(
            stock_code=stock_code,
            exchange_code="NFO",
            product_type=product_type,
            expiry_date=expiry_date
        )
        quotes.extend(resp.get("Success", []))

    objs = []
    for q in quotes:
        obj = OptionChainQuote.objects.create(
            exchange_code=q.get('exchange_code', ''),
            product_type=q.get('product_type', ''),
            stock_code=q.get('stock_code', ''),
            expiry_date=expiry_date_obj,
            right=q.get('right', ''),
            strike_price=Decimal(str(q.get('strike_price', 0.0) or 0.0)),
            ltp=Decimal(str(q.get('ltp', 0.0) or 0.0)),
            best_bid_price=Decimal(str(q.get('best_bid_price', 0.0) or 0.0)),
            best_offer_price=Decimal(str(q.get('best_offer_price', 0.0) or 0.0)),
            open=Decimal(str(q.get('open', 0.0) or 0.0)),
            high=Decimal(str(q.get('high', 0.0) or 0.0)),
            low=Decimal(str(q.get('low', 0.0) or 0.0)),
            previous_close=Decimal(str(q.get('previous_close', 0.0) or 0.0)),
            open_interest=int(q.get('open_interest', 0) or 0),
            total_quantity_traded=int(q.get('total_quantity_traded', 0) or 0),
            spot_price=Decimal('0.00'),  # Set separately if needed
        )
        objs.append(obj)

    logger.info(f"Saved {len(objs)} option chain quotes")
    return objs


def fetch_and_save_nifty_option_chain_all_expiries():
    """
    Fetch NIFTY option chain for all available expiries and save to OptionChain model.

    DATA SOURCES:
    - Expiry dates list: NSE (with fallback to generated Thursdays)
    - ALL live option chain data (LTP, OI, volume, bid, ask, etc.): ICICI Breeze API ONLY

    Returns:
        int: Total number of option chain records saved

    Raises:
        RuntimeError: If no data could be fetched or API calls fail
    """
    logger.info("Fetching NIFTY option chain for all expiries")

    # Get Breeze client (will use existing valid session)
    breeze = get_breeze_client()

    # Quick session validation
    try:
        funds = breeze.get_funds()
        if not funds or funds.get('Status') != 200:
            raise RuntimeError("Breeze session appears to be invalid. Please refresh your session at /brokers/breeze/login/")
        logger.info("Breeze session validated successfully")
    except Exception as e:
        logger.error(f"Breeze session validation failed: {e}")
        raise RuntimeError(
            "Could not validate Breeze session. Please ensure you are logged in at /brokers/breeze/login/. "
            f"Error: {str(e)}"
        )

    # Get NIFTY spot price from Breeze
    try:
        quote = get_nifty_quote()
        spot_price = Decimal(str(quote.get('ltp', 0))) if quote else Decimal('0.00')
        logger.info(f"NIFTY spot price: {spot_price:,.2f}")
    except Exception as e:
        logger.warning(f"Could not fetch NIFTY spot price: {e}")
        spot_price = Decimal('0.00')

    # STEP 1: Get list of expiry dates
    logger.info("Fetching NIFTY expiry dates...")

    expiry_list = []

    # Try to get real expiry dates from NSE first
    try:
        expiry_list = get_all_nifty_expiry_dates(max_expiries=10, timeout=15)
        logger.info(f"Got {len(expiry_list)} real expiry dates from NSE: {expiry_list[:3]}...")
    except Exception as nse_error:
        logger.warning(f"NSE expiry fetch failed: {nse_error}")
        logger.info("Falling back to generating Tuesday expiry dates...")

        # Fallback: Generate NIFTY expiry dates (weekly expiries - Tuesdays as of 2025)
        today = datetime.now().date()
        current_date = today

        # Find next 4 Tuesdays
        for _ in range(30):
            if current_date.weekday() == 1:  # Tuesday = 1
                if current_date >= today:
                    expiry_str = current_date.strftime("%d-%b-%Y")
                    expiry_list.append(expiry_str)
                    if len(expiry_list) >= 4:
                        break
            current_date += timedelta(days=1)

        if expiry_list:
            logger.info(f"Generated {len(expiry_list)} fallback expiries: {expiry_list}")
        else:
            raise RuntimeError("Could not fetch or generate expiry dates")

    logger.info(f"Using {len(expiry_list)} expiry dates for NIFTY option chain fetch (spot: {spot_price})")

    # Store new data temporarily before clearing old data
    new_records = []
    total_saved = 0

    # STEP 2: Fetch LIVE option chain data from ICICI Breeze API
    for expiry_str in expiry_list:
        try:
            logger.info(f"Fetching live option chain from Breeze for expiry: {expiry_str}")

            expiry_date_obj = datetime.strptime(expiry_str, "%d-%b-%Y").date()

            calls_data = []
            puts_data = []

            try:
                calls_resp = breeze.get_option_chain_quotes(
                    stock_code="NIFTY",
                    exchange_code="NFO",
                    product_type="options",
                    expiry_date=expiry_str,
                    right="call",
                )
                if calls_resp and calls_resp.get("Success"):
                    calls_data = calls_resp["Success"]
                else:
                    logger.warning(f"No calls data for {expiry_str}: {calls_resp.get('Error', 'Unknown error')}")
            except Exception as e:
                logger.warning(f"Failed to fetch calls for {expiry_str}: {e}")

            try:
                puts_resp = breeze.get_option_chain_quotes(
                    stock_code="NIFTY",
                    exchange_code="NFO",
                    product_type="options",
                    expiry_date=expiry_str,
                    right="put",
                )
                if puts_resp and puts_resp.get("Success"):
                    puts_data = puts_resp["Success"]
                else:
                    logger.warning(f"No puts data for {expiry_str}: {puts_resp.get('Error', 'Unknown error')}")
            except Exception as e:
                logger.warning(f"Failed to fetch puts for {expiry_str}: {e}")

            # Process call options
            for call in calls_data:
                strike = Decimal(str(call.get('strike_price', 0.0) or 0.0))

                record = OptionChain(
                    underlying='NIFTY',
                    expiry_date=expiry_date_obj,
                    strike=strike,
                    option_type='CE',
                    ltp=Decimal(str(call.get('ltp', 0.0) or 0.0)),
                    bid=Decimal(str(call.get('best_bid_price', 0.0) or 0.0)),
                    ask=Decimal(str(call.get('best_offer_price', 0.0) or 0.0)),
                    volume=int(call.get('total_quantity_traded', 0) or 0),
                    oi=int(call.get('open_interest', 0) or 0),
                    oi_change=0,
                    spot_price=spot_price,
                )
                new_records.append(record)
                total_saved += 1

            # Process put options
            for put in puts_data:
                strike = Decimal(str(put.get('strike_price', 0.0) or 0.0))

                record = OptionChain(
                    underlying='NIFTY',
                    expiry_date=expiry_date_obj,
                    strike=strike,
                    option_type='PE',
                    ltp=Decimal(str(put.get('ltp', 0.0) or 0.0)),
                    bid=Decimal(str(put.get('best_bid_price', 0.0) or 0.0)),
                    ask=Decimal(str(put.get('best_offer_price', 0.0) or 0.0)),
                    volume=int(put.get('total_quantity_traded', 0) or 0),
                    oi=int(put.get('open_interest', 0) or 0),
                    oi_change=0,
                    spot_price=spot_price,
                )
                new_records.append(record)
                total_saved += 1

            if calls_data or puts_data:
                logger.info(f"Collected {len(calls_data)} CE and {len(puts_data)} PE options for expiry {expiry_str}")
            else:
                logger.warning(f"No option chain data available for expiry {expiry_str}")

        except Exception as e:
            logger.error(f"Error processing expiry {expiry_str}: {e}")
            continue

    # Save new records
    if new_records:
        logger.info(f"Successfully fetched {total_saved} records. Clearing old data and saving new records...")

        deleted_count = OptionChain.objects.filter(underlying='NIFTY').delete()[0]
        logger.info(f"Deleted {deleted_count} old OptionChain records for NIFTY")

        OptionChain.objects.bulk_create(new_records, batch_size=500)
        logger.info(f"Bulk created {total_saved} new NIFTY option chain records across {len(expiry_list)} expiries")
    else:
        logger.warning("No new records to save, keeping existing data intact")

    if total_saved == 0:
        raise RuntimeError(
            f"No option chain data could be fetched for any of the {len(expiry_list)} expiry dates.\n\n"
            "Possible reasons:\n"
            "1. Market is closed - Option chain data is only available during trading hours (9:15 AM - 3:30 PM IST)\n"
            "2. The expiry dates don't have active contracts yet\n"
            "3. Breeze API session needs refresh\n\n"
            f"Expiry dates tried: {', '.join(expiry_list[:3])}{'...' if len(expiry_list) > 3 else ''}\n\n"
            "Solution: Please try again during market hours (Mon-Fri 9:15 AM - 3:30 PM IST) or refresh Breeze session at /brokers/breeze/login/"
        )

    return total_saved
