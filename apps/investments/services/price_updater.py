from __future__ import annotations
import logging
from datetime import date
from decimal import Decimal
import yfinance as yf
from django.db.models import Q
from apps.investments.models import InvestmentProduct, EquityPrice, MutualFundScheme
from apps.investments.services.mfapi_client import MFAPIClient

logger = logging.getLogger('apps.investments')


def update_mf_navs(member_ids: list | None = None):
    """Fetch latest NAV from MFAPI for all held MF products and update current_value."""
    qs = InvestmentProduct.objects.filter(product_type='MUTUAL_FUND', is_active=True)
    if member_ids:
        qs = qs.filter(investment_account__family_member_id__in=member_ids)

    # MF Central holdings arrive with no ISIN at all — resolve by name before
    # attempting any NAV lookup, otherwise every such holding is silently
    # skipped below with no NAV, no price update, ever.
    from apps.investments.services.mf_scheme_matcher import backfill_isins
    backfill_isins(qs)

    client = MFAPIClient()
    isin_map = client.get_isin_map()
    updated = 0

    for product in qs:
        isin = product.isin
        if not isin:
            logger.warning('No ISIN for "%s" (id=%d) — name match against MFAPI failed, skipping', product.name[:60], product.id)
            continue
        scheme_code = isin_map.get(isin)
        if not scheme_code:
            logger.warning('No MFAPI scheme code for ISIN %s', isin)
            continue

        nav_entry = client.get_latest_nav(scheme_code)
        if not nav_entry:
            continue

        try:
            nav = Decimal(str(nav_entry.get('nav', 0)))
            nav_date_str = nav_entry.get('date', '')

            from datetime import datetime
            try:
                nav_date = datetime.strptime(nav_date_str, '%d-%m-%Y').date()
            except ValueError:
                nav_date = date.today()

            units = Decimal(str(product.extra_data.get('units', 0)))
            product.current_value = units * nav
            product.as_of_date = nav_date
            ed = dict(product.extra_data)
            ed['nav'] = float(nav)
            product.extra_data = ed
            product.save(update_fields=['current_value', 'as_of_date', 'gain_loss', 'extra_data', 'updated_at'])

            # Keep MutualFundScheme in sync
            MutualFundScheme.objects.filter(isin=isin).update(latest_nav=nav, nav_date=nav_date)
            updated += 1
        except Exception as e:
            logger.error('NAV update error for product %d isin=%s: %s', product.id, isin, e)

    logger.info('Updated NAVs for %d MF products', updated)
    return updated


def _build_nse_isin_map() -> dict:
    """
    Download NSE equity list CSV and return {isin: nse_symbol} mapping.
    Cached in Django's cache for 24 hours.
    """
    from django.core.cache import cache
    cached = cache.get('inv:nse_isin_map')
    if cached:
        return cached

    import requests
    try:
        resp = requests.get(
            'https://archives.nseindia.com/content/equities/EQUITY_L.csv',
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=20,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning('Could not download NSE equity list: %s', e)
        return {}

    import csv, io
    isin_map = {}
    reader = csv.reader(io.StringIO(resp.text))
    next(reader, None)  # skip header
    for row in reader:
        if len(row) < 7:
            continue
        symbol = row[0].strip()
        isin = row[6].strip()
        if symbol and isin:
            isin_map[isin] = symbol

    cache.set('inv:nse_isin_map', isin_map, timeout=86400)
    logger.info('Built NSE ISIN→symbol map: %d entries', len(isin_map))
    return isin_map


def _get_equity_ltp_breeze(nse_symbol: str) -> float | None:
    """
    Fetch LTP for an NSE equity symbol via Breeze get_quotes.
    Returns the LTP as float, or None if unavailable.
    """
    try:
        from apps.brokers.services.breeze_session import get_authenticated_breeze_client
        from apps.brokers.exceptions import BreezeAuthenticationError
        client = get_authenticated_breeze_client(auto_refresh=False)
        resp = client.get_quotes(
            stock_code=nse_symbol,
            exchange_code='NSE',
            product_type='cash',
            expiry_date='',
            right='',
            strike_price='',
        )
        if not resp or resp.get('Status') != 200:
            return None
        rows = resp.get('Success') or []
        if not rows:
            return None
        row = next((r for r in rows if r and r.get('exchange_code') == 'NSE'), rows[0])
        ltp = row.get('ltp') or row.get('last_traded_price')
        return float(ltp) if ltp else None
    except Exception as e:
        logger.debug('Breeze LTP failed for %s: %s', nse_symbol, e)
        return None


def _get_equity_ltp_yfinance(nse_symbol: str) -> float | None:
    """Fallback: fetch LTP via yfinance using NSE ticker format."""
    try:
        # yfinance encodes '&' as '%26' in NSE symbols (e.g. M&M → M%26M)
        yf_symbol = nse_symbol.replace('&', '%26') + '.NS'
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period='2d')
        if hist.empty:
            return None
        return float(round(hist['Close'].iloc[-1], 4))
    except Exception as e:
        logger.debug('yfinance LTP failed for %s: %s', nse_symbol, e)
        return None


def update_equity_prices(member_ids: list | None = None):
    """
    Fetch latest equity LTPs via Breeze (primary) or yfinance (fallback).
    ISIN → NSE symbol mapping is sourced from NSE's public equity list CSV.
    """
    qs = InvestmentProduct.objects.filter(product_type='EQUITY', is_active=True)
    if member_ids:
        qs = qs.filter(investment_account__family_member_id__in=member_ids)

    products = list(qs)
    if not products:
        return 0

    # Build ISIN → NSE symbol map
    nse_isin_map = _build_nse_isin_map()

    today = date.today()
    updated = 0

    for product in products:
        isin = product.isin
        shares = Decimal(str(product.extra_data.get('shares', 0) or product.extra_data.get('quantity', 0)))
        if not shares:
            continue

        # Resolve NSE symbol: prefer stored extra_data.symbol, then ISIN lookup
        nse_symbol = product.extra_data.get('symbol') or nse_isin_map.get(isin)
        if not nse_symbol:
            logger.warning('No NSE symbol for ISIN %s (%s), skipping', isin, product.name)
            continue

        # Try Breeze first, fall back to yfinance
        ltp = _get_equity_ltp_breeze(nse_symbol) or _get_equity_ltp_yfinance(nse_symbol)
        if ltp is None:
            logger.warning('Could not fetch price for %s (ISIN=%s)', nse_symbol, isin)
            continue

        price = Decimal(str(round(ltp, 4)))

        EquityPrice.objects.update_or_create(
            isin=isin or nse_symbol,
            date=today,
            defaults={'price': price, 'symbol': nse_symbol, 'source': 'BREEZE'},
        )

        product.current_value = shares * price
        product.as_of_date = today
        ed = dict(product.extra_data)
        ed['symbol'] = nse_symbol   # persist resolved symbol for future calls
        ed['last_price'] = ltp
        product.extra_data = ed
        product.save(update_fields=['current_value', 'as_of_date', 'gain_loss', 'extra_data', 'updated_at'])
        updated += 1
        logger.info('Equity %s (%s): LTP=%.2f, value=%.2f', nse_symbol, isin, ltp, float(product.current_value))

    logger.info('Updated prices for %d / %d equity products', updated, len(products))
    return updated


def update_gold_prices():
    """Fetch gold price and update SGB and physical gold products."""
    try:
        # Try futures ticker first, fall back to ETF proxy
        for gold_sym in ('GC=F', 'GLD', 'IAU'):
            ticker = yf.Ticker(gold_sym)
            hist = ticker.history(period='5d')
            if not hist.empty:
                break
        if hist.empty:
            logger.warning('Could not fetch gold price from yfinance')
            return 0
        gold_usd = hist['Close'].iloc[-1]
        # GLD/IAU track ~1/10 oz and ~1/100 oz respectively — convert to per troy oz
        if gold_sym == 'GLD':
            gold_usd = gold_usd * 10
        elif gold_sym == 'IAU':
            gold_usd = gold_usd * 100

        # Approximate INR from USD (use a rough rate; ideally fetch from RBI)
        usd_inr_ticker = yf.Ticker('INR=X')
        fx_hist = usd_inr_ticker.history(period='1d')
        usd_inr = float(fx_hist['Close'].iloc[-1]) if not fx_hist.empty else 84.0
        gold_inr_per_gram = float(gold_usd) * usd_inr / 31.1035  # Troy oz to grams

        updated = 0
        for product in InvestmentProduct.objects.filter(
            product_type__in=['SGB', 'PHYSICAL_GOLD'], is_active=True
        ):
            from apps.investments.services.valuation_engine import compute_product_value
            ed = dict(product.extra_data)
            if product.product_type == 'SGB':
                ed['gold_price'] = round(gold_inr_per_gram, 2)
            else:
                ed['gold_price_per_gram'] = round(gold_inr_per_gram, 2)
            product.extra_data = ed
            product.save(update_fields=['extra_data'])
            compute_product_value(product)
            updated += 1

        logger.info('Updated gold price to ₹%.2f/g, refreshed %d products', gold_inr_per_gram, updated)
        return updated
    except Exception as e:
        logger.error('Gold price update failed: %s', e)
        return 0
