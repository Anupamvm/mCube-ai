"""
Option chain + Greeks + symbol-resolution for the Cover Position feature.

Always sources chain/quote data from ICICI Breeze, regardless of which
broker holds the underlying futures position — Kotak Neo has no
full-chain-fetch API, only single-symbol LTP and order placement.
`resolve_execution_symbol()` is the single choke point for translating a
Breeze-priced strike into the broker that will actually execute the order;
no other hedging module should call the Neo/Breeze symbol resolvers
directly.
"""
import logging
from datetime import date
from decimal import Decimal
from typing import List, Optional

logger = logging.getLogger(__name__)


def format_breeze_expiry(expiry_date: date) -> str:
    return expiry_date.strftime('%d-%b-%Y')


def resolve_breeze_stock_code(underlying_symbol: str, expiry_date: date) -> str:
    """
    Translate the plain NSE symbol (e.g. 'VBL') carried by Kotak Neo
    positions into Breeze's own stock_code convention (e.g. 'VARBEV')
    required for chain/quote calls — Breeze positions already report
    their native code, so this is a no-op (identity fallback below) for
    those, but Neo positions are not.

    Two-step resolution, same pattern as futures_analyzer.py's
    discover_instruments_for_symbol (used by Future Trade / Nifty
    Strangle):
    1. apps.brokers.utils.security_master.get_futures_instrument — fast,
       no network call, but only matches when SecurityMaster's CSV has a
       FUTSTK row for this exact expiry_date (it doesn't carry every
       future-dated monthly contract, e.g. an expiry 2+ months out).
    2. Breeze's own get_names(exchange_code='NSE') lookup — one network
       call, but expiry-independent and authoritative (same mechanism as
       apps.trading.services.chart_data_service.resolve_breeze_stock_code).
    """
    from django.core.cache import cache

    from apps.brokers.utils.security_master import get_futures_instrument

    instrument = get_futures_instrument(underlying_symbol, format_breeze_expiry(expiry_date))
    if instrument and instrument.get('source') == 'security_master' and instrument.get('short_name'):
        return instrument['short_name']

    cache_key = f'hedging:breeze_stock_code:{underlying_symbol}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        from apps.brokers.integrations.breeze import get_breeze_client

        breeze = get_breeze_client()
        result = breeze.get_names(exchange_code='NSE', stock_code=underlying_symbol)
        if result and result.get('isec_stock_code'):
            breeze_code = result['isec_stock_code']
            cache.set(cache_key, breeze_code, 6 * 60 * 60)
            return breeze_code
    except Exception as exc:
        logger.warning(f"Breeze get_names lookup failed for {underlying_symbol!r}: {exc}")

    logger.warning(
        f"Could not resolve a Breeze stock code for {underlying_symbol!r} "
        f"(expiry {expiry_date}) — falling back to the symbol as-is."
    )
    return underlying_symbol


def fetch_covered_call_chain(
    underlying_symbol: str,
    option_expiry_date: date,
    spot_price: Decimal,
    india_vix: Optional[Decimal] = None,
) -> List[dict]:
    """
    Fetch CE+PE quotes for `underlying_symbol`/`option_expiry_date` from
    Breeze and enrich with Greeks. Only CALL strikes at or above spot are
    returned to the caller — put_ltp is used internally by
    greeks_calculator's IV averaging but is never shipped out; a covered
    call only ever needs the call side of the chain.

    `underlying_symbol` is the same plain NSE symbol (e.g. 'NIFTY',
    'RELIANCE') used elsewhere in this codebase for security-master
    lookups — it is first translated to Breeze's own stock_code via
    resolve_breeze_stock_code() since Breeze's `stock_code` param IS a
    separate code space for many stocks (e.g. NSE 'VBL' -> Breeze
    'VARBEV').
    """
    from apps.brokers.integrations.breeze_module.option_chain import get_and_save_option_chain_quotes
    from apps.brokers.models import OptionChainQuote
    from apps.strategies.services.greeks_calculator import calculate_all_greeks

    breeze_stock_code = resolve_breeze_stock_code(underlying_symbol, option_expiry_date)
    breeze_expiry = format_breeze_expiry(option_expiry_date)
    get_and_save_option_chain_quotes(breeze_stock_code, expiry_date=breeze_expiry, product_type="options")

    quotes = OptionChainQuote.objects.filter(
        stock_code=breeze_stock_code, expiry_date=option_expiry_date,
    )
    calls_by_strike = {q.strike_price: q for q in quotes if q.right.lower() == 'call'}
    puts_by_strike = {q.strike_price: q for q in quotes if q.right.lower() == 'put'}

    chain_rows: List[dict] = []
    for strike, call_quote in sorted(calls_by_strike.items()):
        if strike < spot_price:
            continue  # a covered call is only ever sold at or above spot
        put_quote = puts_by_strike.get(strike)
        # Greeks calc needs a put_ltp for its IV-averaging methodology even
        # though we only surface call-side numbers — fall back to the call
        # quote itself if the put leg is missing (rare, e.g. thin strikes).
        put_ltp = put_quote.ltp if put_quote else call_quote.ltp

        greeks = calculate_all_greeks(
            spot_price=spot_price,
            strike_price=strike,
            expiry_date=option_expiry_date,
            call_ltp=call_quote.ltp,
            put_ltp=put_ltp,
            india_vix=india_vix,
        )
        chain_rows.append({
            'strike': strike,
            'ltp': call_quote.ltp,
            'bid': call_quote.best_bid_price,
            'ask': call_quote.best_offer_price,
            'open_interest': call_quote.open_interest,
            # Put OI at the same strike is not shown to the client, but is
            # needed by recommendation_engine.calculate_max_pain (standard
            # max-pain formula needs both sides of the chain).
            'put_open_interest': put_quote.open_interest if put_quote else 0,
            'volume': call_quote.total_quantity_traded,
            'delta': greeks['call_delta'],
            'gamma': greeks['call_gamma'],
            'theta': greeks['call_theta'],
            'vega': greeks['call_vega'],
            'iv': greeks['call_iv'],
        })
    return chain_rows


def resolve_execution_symbol(
    broker: str,
    underlying_symbol: str,
    option_expiry_date: date,
    strike,
    option_type: str = 'CE',
    neo_client=None,
) -> dict:
    """
    Translate a Breeze-priced strike into whatever the executing broker
    needs. Returns {'trading_symbol': str|None, 'lot_size': int, 'source': str}.

    For Neo, `trading_symbol` is the resolved pTrdSymbol required by
    place_option_order(). For Breeze, `trading_symbol` is None because
    place_option_order_with_security_master() resolves the instrument
    internally from (symbol, expiry, strike, option_type) — this call is
    still useful there as a pre-flight lot-size / existence check.
    """
    if broker == 'neo':
        from apps.brokers.integrations.kotak_neo import lookup_neo_option_symbol
        result = lookup_neo_option_symbol(
            underlying_symbol, option_expiry_date, int(strike), option_type, client=neo_client,
        )
        if not result:
            raise ValueError(
                f"Could not resolve a Kotak Neo trading symbol for "
                f"{underlying_symbol} {strike}{option_type} expiring {option_expiry_date}"
            )
        return {
            'trading_symbol': result['trading_symbol'],
            'lot_size': result['lot_size'],
            'source': 'neo_search_scrip',
        }

    if broker == 'breeze':
        from apps.brokers.utils.security_master import get_option_instrument
        breeze_expiry = format_breeze_expiry(option_expiry_date)
        instrument = get_option_instrument(underlying_symbol, breeze_expiry, float(strike), option_type)
        if not instrument:
            raise ValueError(
                f"Could not resolve a Breeze instrument for "
                f"{underlying_symbol} {strike}{option_type} expiring {option_expiry_date}"
            )
        return {
            'trading_symbol': None,
            'lot_size': instrument['lot_size'],
            'source': instrument.get('source', 'security_master'),
        }

    raise ValueError(f"Unknown broker: {broker!r}")
