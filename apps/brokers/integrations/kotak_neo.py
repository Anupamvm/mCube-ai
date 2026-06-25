"""
Kotak Neo API Integration

This module provides integration with Kotak Neo broker API for:
- Authentication and session management
- Fetching positions and limits
- Checking open positions
"""

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
try:
    pass
except ImportError:
    # Use local wrapper if neo_api_client not installed
    pass
from django.utils import timezone
from django.core.cache import cache
from apps.core.constants import BROKER_KOTAK
from apps.brokers.models import BrokerLimit, BrokerPosition, PositionAvgOverride
from apps.brokers.utils.common import parse_float as _parse_float

logger = logging.getLogger(__name__)


def _parse_expiry_date(expiry_str):
    """Parse expiry date string from Kotak Neo API (e.g., '30 Jan, 2025') to a date object."""
    if not expiry_str:
        return None
    try:
        return datetime.strptime(expiry_str, '%d %b, %Y').date()
    except (ValueError, TypeError):
        return None



class NeoAuthenticationError(Exception):
    """Custom exception for Neo authentication failures with detailed error info."""

    def __init__(self, message: str, error_type: str = 'unknown', is_retryable: bool = False):
        self.message = message
        self.error_type = error_type
        self.is_retryable = is_retryable
        super().__init__(message)


def _get_authenticated_client():
    """
    Get authenticated Kotak Neo API client using the process-level cached wrapper.

    Uses tools.neo.get_neo_api() which caches the NeoAPI instance per-process.
    First call creates the client and logs in (session restore or full login).
    Subsequent calls return the same cached client — no repeated API calls.

    Returns:
        neo_api_client.NeoAPI: Authenticated client instance

    Raises:
        NeoAuthenticationError: If authentication fails
    """
    try:
        from tools.neo import get_neo_api

        neo_wrapper = get_neo_api()
        if neo_wrapper.session_active:
            return neo_wrapper.neo

        # Login failed — categorize the error for UI messaging
        last_error = neo_wrapper.get_last_error() or "Unknown authentication error"
        logger.error(f"Neo API login failed: {last_error}")

        error_lower = last_error.lower()
        if any(kw in error_lower for kw in ['timeout', 'connection', 'network', 'unreachable']):
            raise NeoAuthenticationError(
                f"Kotak Neo server unreachable: {last_error}",
                error_type='connection',
                is_retryable=True
            )
        elif any(kw in error_lower for kw in ['invalid', 'credential', 'password', 'pan', 'mpin']):
            raise NeoAuthenticationError(
                f"Invalid credentials: {last_error}",
                error_type='credentials',
                is_retryable=False
            )
        elif any(kw in error_lower for kw in ['2fa', 'otp', 'session']):
            raise NeoAuthenticationError(
                f"2FA/Session error: {last_error}",
                error_type='2fa',
                is_retryable=False
            )
        else:
            raise NeoAuthenticationError(
                f"Authentication failed: {last_error}",
                error_type='unknown',
                is_retryable=False
            )

    except NeoAuthenticationError:
        raise
    except Exception as e:
        error_msg = str(e) if str(e) else repr(e)
        logger.error(f"Failed to get authenticated Neo client: {error_msg}")

        error_lower = error_msg.lower()
        if any(kw in error_lower for kw in ['timeout', 'connection', 'network']):
            raise NeoAuthenticationError(
                f"Connection error: {error_msg}",
                error_type='connection',
                is_retryable=True
            )
        raise NeoAuthenticationError(
            f"Unexpected error: {error_msg}",
            error_type='unknown',
            is_retryable=False
        )


def fetch_and_save_kotakneo_data():
    """
    Fetch limits and positions from Kotak Neo API and save to database.

    Uses trade_report() for actual execution prices and maintains a blended
    weighted-average cost across days (for position averaging).

    Returns:
        tuple: (limit_record, pos_objs, raw_limits, raw_positions, raw_trades)
            - limit_record: BrokerLimit instance
            - pos_objs: list of BrokerPosition instances
            - raw_limits: raw limits API response dict
            - raw_positions: raw positions API response dict
            - raw_trades: raw trade_report API response dict (or None)

    Raises:
        NeoAuthenticationError: If authentication fails
        Exception: If API call or database save fails
    """
    client = _get_authenticated_client()

    # Fetch & save limits
    lim = client.limits(segment="ALL", exchange="ALL", product="ALL")
    logger.info(f"Kotak Neo limits response: {lim}")

    # Create limit record with guaranteed fields
    limit_record = BrokerLimit.objects.create(
        broker=BROKER_KOTAK,
        fetched_at=timezone.now(),
    )

    # Mapping from API keys to model fields (convert all floats to Decimal with proper rounding)
    try:
        # Helper to create properly quantized Decimal with 2 decimal places
        def to_decimal_2dp(value):
            """Convert value to Decimal with exactly 2 decimal places"""
            return Decimal(str(_parse_float(value))).quantize(Decimal('0.01'))

        kotak_fields = {
            'category': lim.get('Category', ''),
            # Monetary fields (absolute values)
            'net_balance': to_decimal_2dp(lim.get('Net')),
            'collateral_value': to_decimal_2dp(lim.get('CollateralValue')),
            'margin_available': to_decimal_2dp(lim.get('Collateral')),
            'margin_used': to_decimal_2dp(lim.get('MarginUsed')),
            # IMPORTANT: Kotak API naming is confusing!
            # Fields ending in "Prsnt" are ABSOLUTE values, not percentages
            # Fields ending in "PrcntPrsnt" are actual percentages
            # Only mapping the one true percentage field available:
            'margin_warning_pct': to_decimal_2dp(lim.get('MarginWarningPrcntPrsnt')),
            # Skip margin_used_percent, exposure_margin_pct, span_margin_pct
            # as API doesn't provide these as percentages (they're absolute values)
            'board_lot_limit': int(lim.get('BoardLotLimit', 0)),
        }

        # Assign only existing attributes
        for attr, val in kotak_fields.items():
            try:
                if hasattr(limit_record, attr):
                    setattr(limit_record, attr, val)
            except Exception as field_error:
                logger.error(f"Error setting {attr}={val}: {field_error}")
                raise

        limit_record.save()
        logger.info("Kotak Neo limits saved successfully")
    except (ValueError, InvalidOperation) as e:
        import traceback
        logger.error(f"Error saving Kotak Neo limits: {type(e).__name__}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Continue with positions even if limits fail

    # Fetch & save positions
    resp = client.positions()

    # Validate response — Neo API returns error dicts on session expiry
    if not resp or not isinstance(resp, dict):
        raise Exception(f"Neo positions() returned invalid response: {type(resp)}")

    # Check for success: only 'ok' stat means valid data.
    # Known error patterns:
    #   stat='Not_Ok', stCode=5203 → no open positions (not an error)
    #   stat='error in neo-login-check-api', stCode=100022 → invalid/expired session
    #   key 'Error' or 'error' (ApiException wrapper) → connection error
    stat = resp.get('stat', '')
    if stat == 'ok':
        raw_positions = resp.get('data', [])
    else:
        # Extract error message robustly (handles ApiException with broken __str__)
        err_msg = resp.get('errMsg', '')
        if not err_msg:
            raw_err = resp.get('Error Message') or resp.get('Error') or resp.get('error') or resp.get('message')
            if raw_err is None:
                err_msg = f"stat={stat!r}, stCode={resp.get('stCode')}"
            elif isinstance(raw_err, str):
                err_msg = raw_err
            else:
                # Could be an ApiException whose __str__ returns None — use repr or type name
                try:
                    err_msg = repr(raw_err)
                except Exception:
                    err_msg = type(raw_err).__name__

        # stCode 5203 = "No Data" — no open positions today, not an auth error
        if 'no data' in str(err_msg).lower() or resp.get('stCode') == 5203:
            logger.info("Neo positions() returned no data (no open positions)")
            raw_positions = []
        else:
            logger.error(f"Neo positions() API error: {err_msg}")
            raise NeoAuthenticationError(
                f"Neo API error: {err_msg}",
                error_type='session',
                is_retryable=True
            )

    # ── Fetch trade_report() for ACTUAL trade execution prices ──
    # positions() cfBuyAmt/cfBuyQty gives MTM settlement price (resets daily),
    # NOT the original entry price. trade_report() has real execution prices.
    trades_by_symbol = {}
    trade_resp = None
    try:
        trade_resp = client.trade_report()
        raw_trades = []
        if isinstance(trade_resp, dict) and 'Error' not in trade_resp and 'Error Message' not in trade_resp:
            raw_trades = trade_resp.get('data', [])
            if not isinstance(raw_trades, list):
                raw_trades = []

        for t in raw_trades:
            tsym = t.get('trdSym', '')
            if not tsym:
                continue
            if tsym not in trades_by_symbol:
                trades_by_symbol[tsym] = {'buys': [], 'sells': []}

            filled_qty = int(float(t.get('fldQty', 0) or 0))
            avg_prc = _parse_float(t.get('avgPrc', 0))
            trans_type = t.get('trnsTp', '')

            if trans_type == 'B':
                trades_by_symbol[tsym]['buys'].append({'qty': filled_qty, 'price': avg_prc})
            elif trans_type == 'S':
                trades_by_symbol[tsym]['sells'].append({'qty': filled_qty, 'price': avg_prc})

        logger.info(f"Loaded trade_report: {len(raw_trades)} trades across {len(trades_by_symbol)} symbols")
    except Exception as e:
        logger.warning(f"Could not fetch trade_report for avg prices: {e}")

    # Process each position
    pos_objs = []
    for p in raw_positions:
        try:
            buy_qty = int(p.get('cfBuyQty', 0)) + int(p.get('flBuyQty', 0))
            sell_qty = int(p.get('cfSellQty', 0)) + int(p.get('flSellQty', 0))
            net_q = buy_qty - sell_qty

            # Debug log ALL raw API values for position
            api_lot_size = p.get('lotSz', 'N/A')
            logger.info(
                f"[RAW API] {p.get('trdSym')}: cfBuyQty={p.get('cfBuyQty')}, flBuyQty={p.get('flBuyQty')}, "
                f"cfSellQty={p.get('cfSellQty')}, flSellQty={p.get('flSellQty')}, "
                f"net_qty={net_q}, lotSz={api_lot_size}, stkPrc={p.get('stkPrc')}, "
                f"cfBuyAmt={p.get('cfBuyAmt')}, buyAmt={p.get('buyAmt')}, "
                f"cfSellAmt={p.get('cfSellAmt')}, sellAmt={p.get('sellAmt')}, "
                f"optTp={p.get('optTp')}, expDt={p.get('expDt')}"
            )

            buy_amt = _parse_float(p.get('cfBuyAmt', 0)) + _parse_float(p.get('buyAmt', 0))
            sell_amt = _parse_float(p.get('cfSellAmt', 0)) + _parse_float(p.get('sellAmt', 0))

            # MTM cost basis (fallback only — resets daily, NOT original entry price)
            mtm_cost = (buy_amt / buy_qty) if buy_qty > 0 else (
                (sell_amt / sell_qty) if sell_qty > 0 else 0.0)

            # Fetch LTP
            # IMPORTANT: stkPrc is the STRIKE PRICE for options (e.g., 26350 for NIFTY 26350 CE),
            # NOT the Last Traded Price! Only use stkPrc for non-option instruments.
            trading_symbol = p.get('trdSym') or ''
            is_option = bool(re.search(r'(CE|PE)$', trading_symbol))

            ltp = 0.0
            if trading_symbol:
                try:
                    if is_option:
                        ltp = _fetch_option_ltp_from_breeze(
                            trading_symbol,
                            expiry_date_str=p.get('expDt', ''),
                            strike_price=p.get('stkPrc', ''),
                            option_type=p.get('optTp', ''),
                            symbol=p.get('sym', ''))
                    else:
                        fetched_ltp = get_ltp_from_neo(trading_symbol, client=client)
                        if fetched_ltp and fetched_ltp > 0:
                            ltp = fetched_ltp
                except Exception as ltp_error:
                    logger.warning(f"Could not fetch LTP for {p.get('sym')}: {ltp_error}")

            # Fallback chain: stkPrc (non-options only) → MTM cost
            if ltp == 0.0 and not is_option:
                stk_prc = _parse_float(p.get('stkPrc', 0))
                if stk_prc > 0:
                    ltp = stk_prc
                    logger.info(f"Using stkPrc as LTP fallback for {p.get('sym')}: {ltp:,.2f}")

            if ltp == 0.0:
                ltp = mtm_cost
                logger.info(f"Using MTM cost as LTP fallback for {p.get('sym')}: {ltp:,.2f}")

            # ── Average price: blended weighted average across days ──
            #
            # Maintains a true weighted-average cost from original entry, through
            # any averaging (adding lots on subsequent days), until full square-off.
            #
            # Neo positions API fields:
            #   cfBuyQty / cfSellQty  = carry-forward qty from previous days
            #   flBuyQty / flSellQty  = fresh fills today
            #   cfBuyAmt / cfSellAmt  = MTM settlement amounts (resets daily, NOT original cost)
            #
            # Data sources:
            #   trade_report()  = today's actual execution prices (accurate, but only today)
            #   DB avg_price    = blended weighted avg saved from previous fetches
            #
            # Blending logic:
            #   LONG:  avg = (cf_buy_qty × db_avg + today_buy_value) / (cf_buy_qty + today_buy_qty)
            #          Only buys affect avg; sells are exits that don't change cost basis.
            #   SHORT: avg = (cf_sell_qty × db_avg + today_sell_value) / (cf_sell_qty + today_sell_qty)
            #          Only sells affect avg; buys are exits that don't change cost basis.
            trd_sym = p.get('trdSym') or ''
            direction = 'LONG' if net_q > 0 else 'SHORT'
            trade_data = trades_by_symbol.get(trd_sym, {'buys': [], 'sells': []})

            trade_buy_qty = sum(t['qty'] for t in trade_data['buys'])
            trade_buy_value = sum(t['qty'] * t['price'] for t in trade_data['buys'])
            trade_sell_qty = sum(t['qty'] for t in trade_data['sells'])
            trade_sell_value = sum(t['qty'] * t['price'] for t in trade_data['sells'])

            cf_buy_qty = int(p.get('cfBuyQty', 0))
            cf_sell_qty = int(p.get('cfSellQty', 0))

            # ── Look up carry-forward avg price for blending ──
            #
            # Key principles:
            #   1. The carry-forward avg (cf_avg) must come from a PRE-TODAY record
            #      to avoid double-counting when trade_report returns all of today's
            #      trades on every fetch (including earlier batches already blended).
            #   2. Today's sells reduce the effective carry-forward quantity for LONG
            #      (and today's buys reduce it for SHORT) — partial/full exits.
            #   3. If today's record exists with same net_qty, reuse it (drift guard).
            #   4. Lifecycle filter: only look at records after the last full close.
            today = timezone.now().date()
            override = PositionAvgOverride.objects.filter(trading_symbol=trd_sym).first()
            if override:
                cf_avg = float(override.manual_avg_price)
                logger.info(f"[AVG OVERRIDE] {p.get('sym')}: Using manual override avg={cf_avg:.2f}")
                already_blended_today = False
            else:
                # Find the last time this symbol was fully closed
                last_close = BrokerPosition.objects.filter(
                    broker=BROKER_KOTAK, trading_symbol=trd_sym, net_quantity=0,
                ).order_by('-fetched_at').values_list('fetched_at', flat=True).first()

                qs = BrokerPosition.objects.filter(
                    broker=BROKER_KOTAK, trading_symbol=trd_sym,
                )
                if last_close:
                    qs = qs.filter(fetched_at__gt=last_close)

                # Drift guard: if today's record exists with same qty, reuse it
                prev_today = qs.filter(
                    fetched_at__date=today, net_quantity=net_q,
                ).order_by('-fetched_at').first()
                already_blended_today = prev_today is not None

                # Carry-forward avg: always from PRE-TODAY record to avoid
                # double-counting today's trades in blending formula
                if direction == 'LONG':
                    prev_pre_today = qs.filter(
                        net_quantity__gt=0, fetched_at__date__lt=today,
                    ).order_by('-fetched_at').first()
                else:
                    prev_pre_today = qs.filter(
                        net_quantity__lt=0, fetched_at__date__lt=today,
                    ).order_by('-fetched_at').first()

                cf_avg = float(prev_pre_today.average_price) if (
                    prev_pre_today and float(prev_pre_today.average_price) > 0
                ) else 0.0

            # Effective carry-forward qty after today's exits:
            #   LONG: sells reduce the carry-forward buy qty
            #   SHORT: buys reduce the carry-forward sell qty
            if direction == 'LONG':
                effective_cf = max(cf_buy_qty - trade_sell_qty, 0)
            else:
                effective_cf = max(cf_sell_qty - trade_buy_qty, 0)

            logger.info(
                f"[DB LOOKUP] {p.get('sym')}: trd_sym={trd_sym}, "
                f"override={'YES' if override else 'NO'}, cf_avg={cf_avg:.2f}, "
                f"effective_cf={effective_cf} (cf_buy={cf_buy_qty}, cf_sell={cf_sell_qty}, "
                f"trade_buy={trade_buy_qty}, trade_sell={trade_sell_qty}), "
                f"mtm_cost={mtm_cost:.2f}, already_blended={already_blended_today}"
            )

            if already_blended_today:
                # Same qty as a previous fetch today — reuse saved value
                avg_price = float(prev_today.average_price)
                logger.info(f"{p.get('sym')}: Reusing today's blended avg {avg_price:.2f} (no qty change)")
            elif direction == 'LONG':
                if effective_cf > 0 and trade_buy_qty > 0 and cf_avg > 0:
                    # Blend remaining carry-forward cost with today's new buys
                    avg_price = (effective_cf * cf_avg + trade_buy_value) / (effective_cf + trade_buy_qty)
                    logger.info(
                        f"{p.get('sym')}: Blended LONG avg: "
                        f"({effective_cf} × {cf_avg:.2f} + {trade_buy_value:.2f}) "
                        f"/ {effective_cf + trade_buy_qty} = {avg_price:.2f}"
                    )
                elif trade_buy_qty > 0:
                    # All carry-forward sold (full close+reopen) or new position today
                    avg_price = trade_buy_value / trade_buy_qty
                    logger.info(f"{p.get('sym')}: LONG from trade_report VWAP {avg_price:.2f}")
                elif cf_avg > 0:
                    # Pure carry-forward, no trades today
                    avg_price = cf_avg
                    logger.info(f"{p.get('sym')}: Carry-forward LONG avg from DB {avg_price:.2f}")
                else:
                    avg_price = mtm_cost
                    logger.warning(f"{p.get('sym')}: No trade data or DB record for LONG, using MTM cost {avg_price:.2f}")
            else:  # SHORT
                if effective_cf > 0 and trade_sell_qty > 0 and cf_avg > 0:
                    avg_price = (effective_cf * cf_avg + trade_sell_value) / (effective_cf + trade_sell_qty)
                    logger.info(
                        f"{p.get('sym')}: Blended SHORT avg: "
                        f"({effective_cf} × {cf_avg:.2f} + {trade_sell_value:.2f}) "
                        f"/ {effective_cf + trade_sell_qty} = {avg_price:.2f}"
                    )
                elif trade_sell_qty > 0:
                    avg_price = trade_sell_value / trade_sell_qty
                    logger.info(f"{p.get('sym')}: SHORT from trade_report VWAP {avg_price:.2f}")
                elif cf_avg > 0:
                    avg_price = cf_avg
                    logger.info(f"{p.get('sym')}: Carry-forward SHORT avg from DB {avg_price:.2f}")
                else:
                    avg_price = mtm_cost
                    logger.warning(f"{p.get('sym')}: No trade data or DB record for SHORT, using MTM cost {avg_price:.2f}")

            # P&L calculation
            unrealized_pnl = net_q * (ltp - avg_price) if ltp > 0 else 0.0
            realized_pnl = sell_amt - buy_amt

            db_pos = BrokerPosition.objects.create(
                broker=BROKER_KOTAK,
                fetched_at=timezone.now(),
                symbol=p.get('sym') or p.get('trdSym') or '',
                trading_symbol=p.get('trdSym') or '',
                expiry_date=_parse_expiry_date(p.get('expDt') or ''),
                lot_size=int(p.get('lotSz') or 1),
                exchange_segment=p.get('exSeg') or '',
                product=p.get('prod') or '',
                buy_qty=buy_qty,
                sell_qty=sell_qty,
                net_quantity=net_q,
                buy_amount=Decimal(str(buy_amt)),
                sell_amount=Decimal(str(sell_amt)),
                ltp=Decimal(str(ltp)),
                average_price=Decimal(str(avg_price)),
                realized_pnl=Decimal(str(realized_pnl)),
                unrealized_pnl=Decimal(str(unrealized_pnl)),
            )
            pos_objs.append(db_pos)
        except (ValueError, InvalidOperation, ZeroDivisionError) as e:
            logger.error(f"Error saving Kotak position {p.get('sym', 'UNKNOWN')}: {e}")
            continue

    logger.info(f"Saved {len(pos_objs)} Kotak Neo positions")
    return limit_record, pos_objs, lim, resp, trade_resp


def get_order_book() -> dict:
    """
    Fetch today's orders from Kotak Neo API.

    Returns:
        dict: {
            'success': bool,
            'orders': list of order dicts,
            'error': str (if failed)
        }

    Each order dict contains:
        - order_id: Neo order ID
        - trading_symbol: Symbol traded
        - transaction_type: BUY or SELL
        - quantity: Order quantity
        - price: Order price
        - status: Order status (EXECUTED, PENDING, CANCELLED, REJECTED)
        - order_time: Time of order
        - filled_quantity: Quantity filled
        - average_price: Average execution price
    """
    try:
        client = _get_authenticated_client()
        response = client.order_report()

        logger.info(f"Kotak Neo order book response: {response}")

        if not response:
            return {'success': True, 'orders': [], 'message': 'No orders found'}

        # Handle different response formats
        if isinstance(response, dict):
            if response.get('stat') == 'Not_Ok':
                error_msg = response.get('errMsg', response.get('message', 'Unknown error'))
                # "No Data" is not an error, just empty orders
                if 'no data' in error_msg.lower():
                    return {'success': True, 'orders': [], 'message': 'No orders for today'}
                return {'success': False, 'error': error_msg, 'orders': []}

            orders_data = response.get('data', [])
        elif isinstance(response, list):
            orders_data = response
        else:
            return {'success': False, 'error': f'Unexpected response type: {type(response)}', 'orders': []}

        # Parse orders
        orders = []
        for order in orders_data:
            parsed_order = {
                'order_id': order.get('nOrdNo', ''),
                'trading_symbol': order.get('trdSym', order.get('sym', '')),
                'exchange': order.get('exSeg', 'NFO'),
                'transaction_type': 'BUY' if order.get('trnsTp') == 'B' else 'SELL',
                'quantity': int(order.get('qty', 0)),
                'price': float(order.get('prc', 0)),
                'status': order.get('ordSt', ''),
                'order_time': order.get('ordEntTm', ''),
                'filled_quantity': int(order.get('fldQty', 0)),
                'average_price': float(order.get('avgPrc', 0)),
                'product': order.get('prod', ''),
                'order_type': order.get('prcTp', ''),
                'validity': order.get('vldt', ''),
                'disclosed_quantity': int(order.get('dscQty', 0)),
                'trigger_price': float(order.get('trgPrc', 0)),
                'rejection_reason': order.get('rejRsn', ''),
                'raw_data': order
            }
            orders.append(parsed_order)

        logger.info(f"Fetched {len(orders)} orders from Kotak Neo")
        return {'success': True, 'orders': orders}

    except NeoAuthenticationError as e:
        logger.error(f"Authentication error fetching order book: {e}")
        return {'success': False, 'error': str(e), 'orders': []}
    except Exception as e:
        logger.exception(f"Error fetching Kotak Neo order book: {e}")
        return {'success': False, 'error': str(e), 'orders': []}


def get_trade_book() -> dict:
    """
    Fetch executed trades from Kotak Neo API.

    The API returns all available trades with their fill dates (flDt field).
    Unlike previously documented, this API returns historical trades, not just today's.

    Returns:
        dict: {
            'success': bool,
            'trades': list of trade dicts,
            'error': str (if failed)
        }

    Each trade dict contains:
        - trade_id: Neo trade ID (flId)
        - order_id: Associated order ID (nOrdNo)
        - trading_symbol: Symbol traded (trdSym)
        - transaction_type: BUY or SELL (from trnsTp: B/S)
        - quantity: Trade quantity (fldQty)
        - price: Trade price (flPrc or avgPrc)
        - trade_time: Time of trade (from exTm)
        - trade_date: Date of trade (from flDt, format: DD-Mon-YYYY)
        - exchange: Exchange (NFO, NSE, etc.)
    """
    try:
        client = _get_authenticated_client()
        response = client.trade_report()

        logger.info(f"Kotak Neo trade book response: {response}")

        if not response:
            return {'success': True, 'trades': [], 'message': 'No trades found'}

        # Handle different response formats
        if isinstance(response, dict):
            if response.get('stat') == 'Not_Ok':
                error_msg = response.get('errMsg', response.get('message', 'Unknown error'))
                # "No Data" is not an error, just empty trades
                if 'no data' in error_msg.lower():
                    return {'success': True, 'trades': [], 'message': 'No trades for today'}
                return {'success': False, 'error': error_msg, 'trades': []}

            trades_data = response.get('data', [])
        elif isinstance(response, list):
            trades_data = response
        else:
            return {'success': False, 'error': f'Unexpected response type: {type(response)}', 'trades': []}

        # Parse trades
        trades = []
        for trade in trades_data:
            from datetime import datetime, date

            # Parse trade date from flDt (format: "DD-Mon-YYYY" e.g., "07-Oct-2022")
            trade_date_str = trade.get('flDt', '')
            trade_date = None
            if trade_date_str:
                try:
                    trade_date = datetime.strptime(trade_date_str, '%d-%b-%Y').date()
                except ValueError:
                    try:
                        # Try alternative format
                        trade_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        trade_date = date.today()
            else:
                trade_date = date.today()

            # Parse trade time from exTm (format: "DD-Mon-YYYY HH:MM:SS")
            trade_time = None
            ex_tm = trade.get('exTm', '')
            if ex_tm:
                try:
                    # Parse full datetime and extract time
                    dt = datetime.strptime(ex_tm, '%d-%b-%Y %H:%M:%S')
                    trade_time = dt.time()
                    # Also use date from exTm if flDt wasn't available
                    if not trade_date_str:
                        trade_date = dt.date()
                except ValueError:
                    # Try just time format
                    trade_time_str = trade.get('flTm', '')
                    if trade_time_str:
                        try:
                            trade_time = datetime.strptime(trade_time_str, '%H:%M:%S').time()
                        except ValueError:
                            pass

            parsed_trade = {
                'trade_id': trade.get('flId', ''),
                'order_id': trade.get('nOrdNo', ''),
                'trading_symbol': trade.get('trdSym', trade.get('sym', '')),
                'exchange': trade.get('exSeg', 'NFO'),
                'transaction_type': 'BUY' if trade.get('trnsTp') == 'B' else 'SELL',
                'quantity': int(trade.get('fldQty', trade.get('qty', 0))),
                'price': float(trade.get('flPrc', trade.get('avgPrc', 0))),
                'trade_time': trade_time,
                'trade_date': trade_date,
                'product': trade.get('prod', ''),
                'symbol': trade.get('sym', ''),
                'raw_data': trade
            }
            trades.append(parsed_trade)

        logger.info(f"Fetched {len(trades)} trades from Kotak Neo")
        return {'success': True, 'trades': trades}

    except NeoAuthenticationError as e:
        logger.error(f"Authentication error fetching trade book: {e}")
        return {'success': False, 'error': str(e), 'trades': []}
    except Exception as e:
        logger.exception(f"Error fetching Kotak Neo trade book: {e}")
        return {'success': False, 'error': str(e), 'trades': []}


def is_open_position() -> bool:
    """
    Returns True if any net position is open, else False.
    A position is 'open' when (cfBuyQty + flBuyQty) - (cfSellQty + flSellQty) != 0.

    Returns:
        bool: True if any position is open, False otherwise
    """
    try:
        client = _get_authenticated_client()
        resp = client.positions()

        # Expecting dict; safely get the list
        raw_positions = resp.get('data', []) if isinstance(resp, dict) else []
        if not isinstance(raw_positions, list):
            raw_positions = []

        for p in raw_positions:
            # Aggregate quantities (defaults 0 if key missing)
            buy_qty = int(p.get('cfBuyQty', 0)) + int(p.get('flBuyQty', 0))
            sell_qty = int(p.get('cfSellQty', 0)) + int(p.get('flSellQty', 0))
            net_q = buy_qty - sell_qty

            # Fallback: if API gives a direct net qty field (rare)
            if net_q == 0 and 'netQty' in p:
                try:
                    net_q = int(p.get('netQty') or 0)
                except Exception:
                    net_q = 0

            if net_q != 0:
                return True

        return False

    except Exception as e:
        logger.exception(f"[is_open_position] Failed to fetch/parse positions: {e}")
        return False


def place_option_order(
    trading_symbol: str,
    transaction_type: str,  # 'B' (BUY) or 'S' (SELL)
    quantity: int,
    product: str = 'NRML',  # 'NRML', 'MIS', 'CNC'
    order_type: str = 'MKT',  # 'MKT' (Market) or 'L' (Limit)
    price: float = 0.0,
    trigger_price: float = 0.0,
    disclosed_quantity: int = 0,
    client=None  # Optional: reuse existing client
):
    """
    Place an options order via Kotak Neo API.

    Args:
        trading_symbol (str): Trading symbol (e.g., 'NIFTY25NOV24500CE')
        transaction_type (str): 'B' for BUY, 'S' for SELL
        quantity (int): Quantity to trade (must be in multiples of lot size)
        product (str): Product type - 'NRML', 'MIS', 'CNC'
        order_type (str): 'MKT' for Market, 'L' for Limit
        price (float): Price for limit orders (0 for market orders)
        trigger_price (float): Trigger price for SL orders
        disclosed_quantity (int): Disclosed quantity (0 for no disclosure)
        client: Optional authenticated client to reuse (avoids multiple logins)

    Returns:
        dict: Order response with order_id if successful, error details if failed
            Success: {'success': True, 'order_id': 'NEO123456', 'message': '...'}
            Failure: {'success': False, 'error': '...'}

    Example:
        >>> result = place_option_order(
        ...     trading_symbol='NIFTY25NOV24500CE',
        ...     transaction_type='B',
        ...     quantity=50,  # 1 lot for NIFTY
        ...     product='NRML',
        ...     order_type='MKT'
        ... )
        >>> print(result)
        {'success': True, 'order_id': 'NEO123456', 'message': 'Order placed successfully'}
    """
    try:
        # Use provided client or get new one
        if client is None:
            client = _get_authenticated_client()

        # Log order details before placing
        logger.info(f"Placing Neo order: symbol={trading_symbol}, type={transaction_type}, qty={quantity}, product={product}, order_type={order_type}")

        # Place order using Neo API
        response = client.place_order(
            exchange_segment='nse_fo',  # NSE F&O for options
            product=product,
            price=str(price) if price > 0 else '0',
            order_type=order_type,
            quantity=str(quantity),
            validity='DAY',
            trading_symbol=trading_symbol,
            transaction_type=transaction_type,
            amo='NO',  # After Market Order - NO for regular orders
            disclosed_quantity=str(disclosed_quantity),
            market_protection='0',
            pf='N',  # PF (Price Factor) - N for normal
            trigger_price=str(trigger_price) if trigger_price > 0 else '0',
            tag=None  # Optional tag for tracking
        )

        logger.info(f"Kotak Neo order response: {response}")

        # Check response status
        if response and response.get('stat') == 'Ok':
            order_id = response.get('nOrdNo', 'UNKNOWN')
            logger.info(f"✅ Order placed successfully: {order_id} for {trading_symbol}")

            return {
                'success': True,
                'order_id': order_id,
                'message': f'Order placed successfully. Order ID: {order_id}',
                'response': response
            }
        else:
            # Handle different error response formats
            if response:
                error_msg = response.get('errMsg') or response.get('message') or response.get('description', 'Unknown error')
                error_code = response.get('stCode') or response.get('code', '')
                full_error = f"[{error_code}] {error_msg}" if error_code else error_msg
            else:
                full_error = 'No response from API'

            logger.error(f"❌ Order placement failed: {full_error}")

            return {
                'success': False,
                'error': full_error,
                'response': response
            }

    except Exception as e:
        logger.exception(f"Exception in place_option_order: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def get_kotak_neo_client():
    """
    Get authenticated Kotak Neo client for placing orders.

    Returns:
        NeoAPI: Authenticated client instance

    Raises:
        NeoAuthenticationError: If authentication fails with detailed error info
    """
    try:
        return _get_authenticated_client()
    except NeoAuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Failed to get Kotak Neo client: {e}")
        raise NeoAuthenticationError(
            f"Unexpected error getting Neo client: {e}",
            error_type='unknown',
            is_retryable=False
        )


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

        import re
        from datetime import datetime

        # Check if it's a FUTURES symbol: SYMBOL + YYMMMFUT
        # Pattern: (SYMBOL)(YY)(MMM)FUT
        futures_pattern = r'^([A-Z]+)(\d{2})([A-Z]{3})FUT$'
        futures_match = re.match(futures_pattern, trading_symbol)

        if futures_match:
            # It's a futures contract
            symbol_name = futures_match.group(1)  # JIOFIN, NIFTY, BANKNIFTY
            year_suffix = futures_match.group(2)  # 25, 26
            month_name = futures_match.group(3)  # DEC, JAN

            logger.info(f"Detected FUTURES symbol: {trading_symbol}")

            # Search using Neo API (for futures, no strike or option_type needed)
            result = client.search_scrip(
                exchange_segment='nse_fo',
                symbol=symbol_name
            )

            if result and isinstance(result, list):
                # Find the matching futures contract
                # Match by trading symbol directly
                for scrip in result:
                    if scrip.get('pTrdSymbol') == trading_symbol:
                        lot_size = scrip.get('lLotSize', scrip.get('iLotSize', 50))
                        logger.info(f"✅ Found lot size for {trading_symbol}: {lot_size}")
                        return int(lot_size)

                logger.warning(f"No exact match found for {trading_symbol}, using first {symbol_name} contract")
                # Fallback: use first contract's lot size (usually same for all expiries)
                if len(result) > 0:
                    lot_size = result[0].get('lLotSize', result[0].get('iLotSize', 50))
                    logger.info(f"✅ Found lot size for {symbol_name} futures: {lot_size}")
                    return int(lot_size)

            logger.warning(f"No scrip found for {trading_symbol}, using default lot size 50")
            return 50  # Default for futures

        # Check if it's an OPTIONS symbol: SYMBOL + DDMMM + STRIKE + CE/PE
        # Pattern: (SYMBOL)(DDMMM)(STRIKE)(CE|PE)
        options_pattern = r'^([A-Z]+)(\d{2}[A-Z]{3})(\d+)(CE|PE)$'
        options_match = re.match(options_pattern, trading_symbol)

        if options_match:
            # It's an options contract
            symbol_name = options_match.group(1)  # NIFTY
            expiry_date = options_match.group(2)  # 25NOV
            strike_price = options_match.group(3)  # 27050
            option_type = options_match.group(4)  # CE or PE

            # Convert expiry to Neo format: 25NOV → 25NOV2025
            current_year = datetime.now().year
            expiry_full = f"{expiry_date}{current_year}"  # 25NOV2025

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
                logger.info(f"✅ Found lot size for {trading_symbol}: {lot_size}")
                return int(lot_size)
            else:
                logger.warning(f"No scrip found for {trading_symbol}, using default lot size 25")
                return 25  # Default for NIFTY options

        # Weekly compact format: {SYMBOL}{YY}{M}{DD}{STRIKE}{CE/PE}
        # Month codes: 1-9 = Jan-Sep, O = Oct, N = Nov, D = Dec
        # Examples: NIFTY2670224500CE (Jul 02), NIFTY26N0224500CE (Nov 02)
        weekly_options_pattern = r'^([A-Z]+)(\d{2})([1-9OND])(\d{2})(\d+)(CE|PE)$'
        weekly_match = re.match(weekly_options_pattern, trading_symbol)

        if weekly_match:
            base_symbol = weekly_match.group(1)  # NIFTY

            logger.info(f"Detected WEEKLY OPTIONS symbol: {trading_symbol}")

            # Search by base symbol and match pTrdSymbol exactly
            result = client.search_scrip(
                exchange_segment='nse_fo',
                symbol=base_symbol
            )

            if result and isinstance(result, list):
                for scrip in result:
                    if scrip.get('pTrdSymbol') == trading_symbol:
                        lot_size = scrip.get('lLotSize', scrip.get('iLotSize', 25))
                        logger.info(f"✅ Found lot size for weekly {trading_symbol}: {lot_size}")
                        return int(lot_size)

            logger.warning(f"No scrip found for weekly {trading_symbol}, using default lot size 25")
            return 25

        # Unknown format
        logger.warning(f"Unable to parse trading symbol: {trading_symbol}, using default lot size 50")
        return 50  # Default fallback

    except Exception as e:
        logger.error(f"Error fetching lot size for {trading_symbol}: {e}")
        logger.warning(f"Using default lot size 50")
        return 50  # Default fallback


def lookup_neo_option_symbol(
    symbol_name: str,
    expiry_date,
    strike: int,
    option_type: str,
    client=None
) -> dict:
    """
    Resolve the exact Kotak Neo trading symbol for an options contract.

    The constructed format (NIFTY26JULSTRIKE CE) only works for monthly expiries.
    For weekly expiries Kotak Neo uses a compact date format (NIFTY267224500CE).
    This function uses search_scrip to get the correct pTrdSymbol regardless of
    whether the expiry is weekly or monthly.

    Args:
        symbol_name: Base symbol (e.g. 'NIFTY')
        expiry_date: Exact expiry date as a date object (e.g. date(2026, 7, 2))
        strike: Strike price as int (e.g. 24500)
        option_type: 'CE' or 'PE'
        client: Optional authenticated Neo client to reuse

    Returns:
        dict with 'trading_symbol', 'lot_size', 'p_symbol' keys, or None if not found
    """
    try:
        import re
        from datetime import date as _date

        if client is None:
            client = _get_authenticated_client()

        if isinstance(expiry_date, _date):
            expiry_full = expiry_date.strftime('%d%b%Y').upper()  # e.g., 02JUL2026
        else:
            expiry_full = str(expiry_date)

        logger.info(
            f"Searching Neo scrip: {symbol_name} expiry={expiry_full} "
            f"strike={strike} type={option_type}"
        )

        result = client.search_scrip(
            exchange_segment='nse_fo',
            symbol=symbol_name,
            expiry=expiry_full,
            option_type=option_type,
            strike_price=str(strike)
        )

        if result and isinstance(result, list) and len(result) > 0:
            scrip = result[0]
            trading_symbol = scrip.get('pTrdSymbol')
            lot_size = int(scrip.get('lLotSize') or scrip.get('iLotSize') or 25)
            p_symbol = scrip.get('pSymbol')
            logger.info(
                f"✅ Resolved Neo option: {trading_symbol} "
                f"(lot_size={lot_size}, pSymbol={p_symbol})"
            )
            return {
                'trading_symbol': trading_symbol,
                'lot_size': lot_size,
                'p_symbol': p_symbol,
            }

        logger.warning(
            f"No scrip found for {symbol_name} {expiry_full} {strike} {option_type}"
        )
        return None

    except Exception as e:
        logger.error(f"Error looking up Neo option symbol: {e}")
        return None


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
    import re
    from datetime import date
    import calendar

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

        # Map Neo stock codes to Breeze stock codes (they differ for some stocks)
        # Breeze uses truncated/different codes for F&O (max 7 chars typically)
        neo_to_breeze_mapping = {
            'HDFCBANK': 'HDFCBAN',  # HDFC Bank (Breeze: HDFCBAN for options, HDFBAN for futures)
            'ICICIBANK': 'ICICIBNK',  # ICICI Bank
            'KOTAKBANK': 'KOTAKBNK',  # Kotak Bank
            'AXISBANK': 'AXISBNK',  # Axis Bank
            'INDUSINDBK': 'INDUSIND',  # IndusInd Bank
            'BANDHANBNK': 'BANDHAN',  # Bandhan Bank
            'FEDERALBNK': 'FEDBANK',  # Federal Bank
            'IDFCFIRSTB': 'IDFCBANK',  # IDFC First Bank
            'BANKBARODA': 'BANKBARO',  # Bank of Baroda
            'CANBK': 'CANBANK',  # Canara Bank
            'SBIN': 'SBIN',  # SBI (same)
            'NIFTY': 'NIFTY',  # NIFTY (same)
            'BANKNIFTY': 'CNXBAN',  # Bank NIFTY
        }
        stock_code = neo_to_breeze_mapping.get(stock_code, stock_code)

        # For stock futures, Breeze sometimes uses shorter codes
        # e.g., HDFCBANK -> HDFBAN (without the C)
        stock_futures_mapping = {
            'HDFCBAN': 'HDFBAN',  # HDFC Bank futures specifically
        }
        stock_code = stock_futures_mapping.get(stock_code, stock_code)

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
        # Note: F&O contracts expire on the last Thursday, but if that Thursday
        # is a holiday, the expiry moves to the previous trading day
        last_day = calendar.monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        # Find last Thursday
        last_thursday = last_date
        while last_thursday.weekday() != 3:  # 3 = Thursday
            last_thursday = date(year, month, last_thursday.day - 1)

        # Format expiry date as DD-Mon-YYYY (Breeze format with title case month)
        # Example: 27-Jan-2026, NOT 27-JAN-2026
        expiry_date = last_thursday.strftime('%d-%b-%Y')

        logger.info(f"[NEO→BREEZE MAPPING] {neo_symbol} → stock_code={stock_code}, expiry={expiry_date}")

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


def _fetch_option_ltp_from_breeze(trading_symbol: str, expiry_date_str: str = '',
                                  strike_price: str = '', option_type: str = '',
                                  symbol: str = '') -> float:
    """
    Fetch real-time LTP for an option contract via Breeze API.

    Uses raw Neo API fields directly (strike_price, option_type, symbol) instead
    of parsing the complex Neo trading symbol format.

    Args:
        trading_symbol: Neo trading symbol (for logging only)
        expiry_date_str: Expiry date from Neo API expDt field (e.g., '10 Feb, 2026')
        strike_price: Strike price from Neo API stkPrc field (e.g., '26350.00')
        option_type: Option type from Neo API optTp field ('CE' or 'PE')
        symbol: Base symbol from Neo API sym field (e.g., 'NIFTY')

    Returns:
        float: LTP of the option, or 0.0 if not found
    """
    try:
        from apps.brokers.integrations.breeze import get_breeze_client

        if not symbol or not option_type or not strike_price:
            logger.warning(f"[OPTION LTP] Missing params for {trading_symbol}: "
                           f"symbol={symbol}, optType={option_type}, strike={strike_price}")
            return 0.0

        right = 'call' if option_type.upper() == 'CE' else 'put'

        # Clean strike price - remove decimals if present (e.g., '26350.00' -> '26350')
        strike = str(strike_price).split('.')[0] if strike_price else ''

        # Format expiry for Breeze API (DD-MMM-YYYY)
        expiry_breeze = None
        if expiry_date_str:
            # Neo expDt format is typically '10 Feb, 2026' or other variants
            for fmt in ('%d %b, %Y', '%d-%b-%Y', '%d%b%Y', '%d-%B-%Y', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(expiry_date_str.strip(), fmt)
                    expiry_breeze = dt.strftime('%d-%b-%Y')
                    break
                except ValueError:
                    continue
            if not expiry_breeze:
                expiry_breeze = expiry_date_str

        if not expiry_breeze:
            logger.warning(f"[OPTION LTP] No expiry date for: {trading_symbol}")
            return 0.0

        breeze = get_breeze_client()
        logger.info(f"[OPTION LTP] Fetching {trading_symbol}: stock={symbol}, "
                     f"strike={strike}, right={right}, expiry={expiry_breeze}")

        resp = breeze.get_quotes(
            stock_code=symbol,
            exchange_code="NFO",
            product_type="options",
            expiry_date=expiry_breeze,
            right=right,
            strike_price=strike
        )

        if resp and resp.get('Status') == 200:
            data = resp.get('Success', [])
            if data and len(data) > 0:
                ltp = float(data[0].get('ltp', 0))
                if ltp > 0:
                    logger.info(f"[OPTION LTP] {trading_symbol}: ₹{ltp:.2f}")
                    return ltp

        logger.warning(f"[OPTION LTP] No LTP from Breeze for {trading_symbol}: {resp}")
        return 0.0

    except Exception as e:
        logger.error(f"[OPTION LTP] Error fetching LTP for {trading_symbol}: {e}")
        return 0.0


def get_ltp_from_neo(trading_symbol: str, exchange_segment: str = 'nse_fo', client=None) -> float:
    """
    Get real-time Last Traded Price (LTP) for a Neo trading symbol.

    Strategy order:
      1. Neo quotes() API — real-time, works for ALL instruments by trading symbol
      2. Breeze option_chain_quotes — real-time, requires symbol mapping
      3. Breeze portfolio positions — works if position held on Breeze side

    Args:
        trading_symbol (str): Neo trading symbol (e.g., 'NIFTY26FEBFUT', 'BHARTIARTL26FEBFUT')
        exchange_segment (str): Exchange segment (default: 'nse_fo')
        client: Optional authenticated Neo client to reuse

    Returns:
        float: Real-time LTP, or None if all strategies fail
    """
    # ── Strategy 1: Neo quotes() API — real-time, universal ──
    # The quotes API needs pSymbol (internal token), NOT the trading symbol.
    # Use search_scrip to find pSymbol first, then pass it to quotes().
    try:
        neo_client = client or _get_authenticated_client()

        # Extract base symbol for search_scrip (e.g., BHARTIARTL from BHARTIARTL26MARFUT)
        base_match = re.match(r'^([A-Z]+)', trading_symbol)
        base_symbol = base_match.group(1) if base_match else trading_symbol

        scrip_results = neo_client.search_scrip(
            exchange_segment=exchange_segment,
            symbol=base_symbol,
        )
        if scrip_results and isinstance(scrip_results, list):
            for scrip in scrip_results:
                if scrip.get('pTrdSymbol') == trading_symbol:
                    p_symbol = scrip.get('pSymbol')
                    if p_symbol:
                        response = neo_client.quotes(
                            instrument_tokens=[{
                                "exchange_segment": exchange_segment,
                                "instrument_token": p_symbol,
                            }],
                            quote_type="ltp",
                        )
                        if isinstance(response, list) and response:
                            ltp = float(response[0].get('ltp', 0))
                            if ltp > 0:
                                logger.info(f"[LTP] {trading_symbol}: ₹{ltp:.2f} (Neo quotes via pSymbol={p_symbol})")
                                return ltp
                        elif isinstance(response, dict) and not response.get('error') and not response.get('fault'):
                            data = response.get('data', response)
                            if isinstance(data, list) and data:
                                ltp = float(data[0].get('ltp', 0))
                                if ltp > 0:
                                    logger.info(f"[LTP] {trading_symbol}: ₹{ltp:.2f} (Neo quotes via pSymbol={p_symbol})")
                                    return ltp
                        logger.warning(f"[LTP] Neo quotes no LTP for {trading_symbol} (pSymbol={p_symbol}): {response}")
                    break

        logger.info(f"[LTP] Neo quotes: no pSymbol found for {trading_symbol}")
    except Exception as e:
        logger.warning(f"[LTP] Neo quotes API failed for {trading_symbol}: {e}")

    # ── Strategy 2: Breeze option_chain_quotes — real-time, needs mapping ──
    try:
        from apps.brokers.integrations.breeze import get_breeze_client

        mapping = map_neo_symbol_to_breeze(trading_symbol)
        if mapping['success']:
            breeze = get_breeze_client()
            resp = breeze.get_option_chain_quotes(
                stock_code=mapping['stock_code'],
                exchange_code=mapping['exchange_code'],
                product_type=mapping['product_type'],
                expiry_date="",
            )
            if resp and resp.get('Status') == 200:
                contracts = resp.get('Success', [])
                calc_month_year = mapping['expiry_date'].split('-')[1:3]
                for contract in contracts:
                    contract_expiry = contract.get('expiry_date', '')
                    if contract_expiry and contract_expiry.split('-')[1:3] == calc_month_year:
                        ltp = float(contract.get('ltp', 0))
                        if ltp > 0:
                            logger.info(f"[LTP] {trading_symbol}: ₹{ltp:.2f} (Breeze option_chain)")
                            return ltp
    except Exception as e:
        logger.warning(f"[LTP] Breeze option_chain_quotes failed for {trading_symbol}: {e}")

    # ── Strategy 3: Breeze portfolio positions ──
    try:
        from apps.brokers.integrations.breeze import get_breeze_client
        mapping = map_neo_symbol_to_breeze(trading_symbol)
        if mapping['success']:
            breeze = get_breeze_client()
            pos_resp = breeze.get_portfolio_positions()
            if pos_resp and pos_resp.get('Status') == 200:
                for pos in (pos_resp.get('Success') or []):
                    if pos.get('stock_code', '') == mapping['stock_code']:
                        ltp = float(pos.get('ltp', 0))
                        if ltp > 0:
                            logger.info(f"[LTP] {trading_symbol}: ₹{ltp:.2f} (Breeze position)")
                            return ltp
    except Exception as e:
        logger.warning(f"[LTP] Breeze positions failed for {trading_symbol}: {e}")

    logger.error(f"[LTP] All strategies failed for {trading_symbol}")
    return None


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

    Example:
        >>> result = get_lot_size_from_neo_with_token('NIFTY25NOV27050CE')
        >>> print(result)
        {'lot_size': 75, 'token': '12345', 'expiry': '28-NOV-2024', ...}
    """
    try:
        # Use provided client or get new one
        if client is None:
            client = _get_authenticated_client()

        # Parse symbol to extract components
        import re
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

        symbol_name = match.group(1)  # NIFTY
        expiry_date = match.group(2)  # 25NOV
        strike_price = match.group(3)  # 27050
        option_type = match.group(4)  # CE or PE

        # Convert expiry to Neo format
        from datetime import datetime
        current_year = datetime.now().year
        expiry_full = f"{expiry_date}{current_year}"  # 25NOV2025

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

            logger.info(f"✅ Found scrip details for {trading_symbol}: lot_size={lot_size}, token={token}")

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


# Cache for Neo scrip master (to avoid repeated downloads)
_neo_scrip_master_cache = {'data': None, 'timestamp': None}
_CACHE_DURATION_SECONDS = 3600  # 1 hour

def _is_neo_error_response(result: dict) -> str:
    """
    Check if a Neo API response dict is an error. Returns error message or empty string.

    Neo API returns errors with different key patterns:
    - {"Error Message": "Complete the 2fa process..."}  (auth/session issue)
    - {"Error": "Exchange Segment is not available"}    (API error)
    - {"error": <exception>}                            (ApiException)
    - {"stat": "Not_Ok", ...}                           (general failure)
    """
    for key in ('Error Message', 'Error', 'error'):
        if key in result:
            return str(result[key])
    if result.get('stat') == 'Not_Ok':
        return result.get('message', 'API returned Not_Ok')
    return ''


def _retry_with_fresh_auth_kotak():
    """
    Clear cached Neo session and get a fresh authenticated client.
    Returns the fresh client or None if auth fails.
    """
    try:
        from tools.neo import get_neo_api, _cache_lock
        import tools.neo as neo_module

        with _cache_lock:
            if neo_module._cached_instance:
                neo_module._cached_instance.session_active = False
                neo_module._cached_instance = None

        try:
            from apps.brokers.utils.auth_manager import clear_neo_session
            clear_neo_session()
        except Exception:
            pass

        neo_wrapper = get_neo_api()
        if neo_wrapper.session_active:
            logger.info("[SCRIP MASTER] Fresh authentication successful")
            return neo_wrapper.neo
        else:
            logger.error(f"[SCRIP MASTER] Fresh authentication failed: {neo_wrapper.get_last_error()}")
            return None
    except Exception as e:
        logger.error(f"[SCRIP MASTER] Error during fresh auth: {e}")
        return None


def _get_neo_scrip_master(client, _retried=False) -> list:
    """
    Get Neo scrip master with caching.
    Returns list of all contracts from CSV.
    Retries once with fresh authentication on auth-related failures.
    """
    import csv
    import io
    import requests
    import time

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

        # Handle dict response (may contain error or URL)
        if isinstance(scrip_master_result, dict):
            error_msg = _is_neo_error_response(scrip_master_result)
            if error_msg:
                logger.error(f"[SCRIP MASTER] API error: {error_msg}")

                # Retry once with fresh auth if this looks like a session/auth issue
                auth_keywords = ['2fa', 'session', 'token', 'auth', 'login', 'unauthorized']
                if not _retried and any(kw in error_msg.lower() for kw in auth_keywords):
                    logger.info("[SCRIP MASTER] Auth-related error, retrying with fresh session...")
                    fresh_client = _retry_with_fresh_auth_kotak()
                    if fresh_client:
                        return _get_neo_scrip_master(fresh_client, _retried=True)

                return []

            scrip_master_url = scrip_master_result.get('url') or scrip_master_result.get('data')
        else:
            scrip_master_url = scrip_master_result

        if not scrip_master_url or not isinstance(scrip_master_url, str):
            logger.error(f"[SCRIP MASTER] Invalid scrip master response: {type(scrip_master_result)}, value: {str(scrip_master_result)[:200]}")

            if not _retried:
                logger.info("[SCRIP MASTER] Unexpected response, retrying with fresh session...")
                fresh_client = _retry_with_fresh_auth_kotak()
                if fresh_client:
                    return _get_neo_scrip_master(fresh_client, _retried=True)

            return []

        # If it's a URL, download it with retry logic
        if scrip_master_url.startswith('http'):
            logger.info(f"[SCRIP MASTER] Downloading from URL: {scrip_master_url[:100]}...")

            max_retries = 3
            scrip_master_csv = None

            for attempt in range(1, max_retries + 1):
                try:
                    response = requests.get(scrip_master_url, timeout=(30, 120))
                    if response.status_code != 200:
                        logger.error(f"[SCRIP MASTER] Failed to download CSV: {response.status_code}")
                        return []
                    scrip_master_csv = response.text
                    break
                except requests.exceptions.Timeout as e:
                    logger.warning(f"[SCRIP MASTER] Timeout on attempt {attempt}/{max_retries}: {e}")
                    if attempt == max_retries:
                        raise
                    time.sleep(2)
                except requests.exceptions.ConnectionError as e:
                    logger.warning(f"[SCRIP MASTER] Connection error on attempt {attempt}/{max_retries}: {e}")
                    if attempt == max_retries:
                        raise
                    time.sleep(2)

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


def map_breeze_symbol_to_neo(breeze_symbol: str, expiry_date=None, client=None) -> dict:
    """
    Map Breeze (ICICI) symbol format to Kotak Neo trading symbol.

    CRITICAL: Breeze and Neo use different symbol formats!
    - Breeze: NIFTY02DEC27050CE (day-based format)
    - Neo: Must be fetched via search_scrip API

    This function:
    1. Parses the Breeze-style symbol
    2. Calls Neo's search_scrip to find the actual Neo trading symbol
    3. Returns Neo symbol with lot size and token

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

    Example:
        >>> result = map_breeze_symbol_to_neo('NIFTY02DEC27050CE')
        >>> if result['success']:
        ...     print(f"Neo symbol: {result['neo_symbol']}")
        Neo symbol: NIFTY 02 DEC 2025 27050 CE
    """
    import re

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

        logger.info(f"[SYMBOL MAPPING] Breeze: {breeze_symbol} → Parsed: symbol={symbol_name}, expiry={expiry_ddmmm}, strike={strike_price}, type={option_type}")

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
        # Neo format: NIFTY25D0226800CE (NIFTY + YY + D + DD + STRIKE + CE/PE)
        # Where: YY=year, D=month code, DD=day
        matching_contracts = []

        for contract in scrip_master:
            # Check if it's a NIFTY option
            if contract.get('pSymbolName') != symbol_name:
                continue

            # Check option type
            if contract.get('pOptionType') != option_type:
                continue

            # Check strike price (handle scientific notation)
            # NOTE: Strike prices in CSV are stored as actual_strike * 100
            # e.g., 27000 strike is stored as 2700000 or 2.7e+06
            contract_strike_raw = str(contract.get('dStrikePrice;', ''))
            try:
                contract_strike_float = float(contract_strike_raw.replace(',', ''))
                # Divide by 100 to get actual strike
                contract_strike = contract_strike_float / 100
                target_strike = float(strike_price)

                # Compare with small tolerance for floating point
                if abs(contract_strike - target_strike) > 0.1:
                    continue
            except (ValueError, AttributeError):
                # Fallback to string comparison if float conversion fails
                if str(strike_price) not in contract_strike_raw:
                    continue

            # Check if expiry matches (look for the date pattern in symbol)
            neo_symbol = contract.get('pTrdSymbol', '')

            # Neo format includes date in symbol: NIFTY25D0226800CE
            # Extract day from Breeze format: 02DEC → day=02
            expiry_day = expiry_ddmmm[:2]  # "02"

            # Check if this contract matches our expiry date
            # Look for patterns like "25D02" (year=25, month code D, day=02)
            if expiry_date:
                year_short = expiry_date.strftime('%y')  # "25"
                month_code = expiry_date.strftime('%b')[0].upper()  # "D" for Dec
                date_pattern = f"{year_short}{month_code}{expiry_day}"  # "25D02"

                if date_pattern in neo_symbol:
                    matching_contracts.append(contract)

        if matching_contracts:
            # Use the first match
            contract = matching_contracts[0]
            neo_symbol = contract.get('pTrdSymbol', '')
            lot_size = int(contract.get('lLotSize', 75))

            logger.info(f"[SYMBOL MAPPING] ✅ Found Neo symbol: {neo_symbol}, lot_size={lot_size}")

            return {
                'success': True,
                'neo_symbol': str(neo_symbol),
                'lot_size': lot_size,
                'token': str(neo_symbol),
                'expiry': expiry_date.strftime('%d%b%Y').upper() if expiry_date else '',
                'error': None
            }
        else:
            logger.error(f"[SYMBOL MAPPING] ❌ No matching contract found for {breeze_symbol}")
            logger.info(f"[SYMBOL MAPPING] Searched for: symbol={symbol_name}, strike={strike_price}, type={option_type}, expiry_day={expiry_ddmmm[:2]}")

            # Show nearby/similar contracts to help debugging
            logger.info(f"[SYMBOL MAPPING] Searching for similar contracts...")

            # Find contracts with same symbol and option type
            similar_contracts = []
            target_strike = float(strike_price)

            for contract in scrip_master:
                if contract.get('pSymbolName') != symbol_name:
                    continue
                if contract.get('pOptionType') != option_type:
                    continue

                # Get strike (divide by 100 as strikes are stored * 100)
                try:
                    contract_strike_raw = str(contract.get('dStrikePrice;', ''))
                    contract_strike_float = float(contract_strike_raw.replace(',', ''))
                    contract_strike = contract_strike_float / 100  # Divide by 100

                    # Find strikes within ±200 points
                    if abs(contract_strike - target_strike) <= 200:
                        similar_contracts.append({
                            'symbol': contract.get('pTrdSymbol', ''),
                            'strike': int(contract_strike),
                            'lot_size': contract.get('lLotSize', 'N/A')
                        })
                except:
                    continue

            if similar_contracts:
                # Sort by strike
                similar_contracts.sort(key=lambda x: x['strike'])

                logger.info(f"[SYMBOL MAPPING] Found {len(similar_contracts)} similar contracts:")
                for i, c in enumerate(similar_contracts[:10]):  # Show first 10
                    logger.info(f"[SYMBOL MAPPING]   [{i+1}] {c['symbol']} - Strike: {c['strike']}, Lot: {c['lot_size']}")

                if len(similar_contracts) > 10:
                    logger.info(f"[SYMBOL MAPPING]   ... and {len(similar_contracts) - 10} more")
            else:
                logger.warning(f"[SYMBOL MAPPING] No similar contracts found nearby")

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


def place_strangle_orders_in_batches(
    call_symbol: str,
    put_symbol: str,
    total_lots: int,
    batch_size: int = 20,
    delay_seconds: int = 20,
    product: str = 'NRML',
    lot_size: int = None  # Optional: if provided, use this instead of fetching
):
    """
    Place strangle orders (Call SELL + Put SELL) in batches with delays.

    This function places orders in batches to avoid overwhelming the broker API
    and to provide better execution monitoring.

    Args:
        call_symbol (str): Call option trading symbol (e.g., 'NIFTY25NOV24500CE')
        put_symbol (str): Put option trading symbol (e.g., 'NIFTY25NOV24000PE')
        total_lots (int): Total number of lots to trade
        batch_size (int): Maximum lots per order (default: 20, Neo API limit)
        delay_seconds (int): Delay between orders in seconds (default: 20)
        product (str): Product type - 'NRML', 'MIS' (default: 'NRML')

    Returns:
        dict: Batch execution results
            {
                'success': True/False,
                'total_lots': int,
                'batches_completed': int,
                'call_orders': [list of order results],
                'put_orders': [list of order results],
                'summary': {
                    'call_success_count': int,
                    'put_success_count': int,
                    'call_failed_count': int,
                    'put_failed_count': int
                },
                'error': str (if failed)
            }

    Example:
        >>> # For 167 lots: Places 9 orders (8×20 lots + 1×7 lots) with 20s delays
        >>> result = place_strangle_orders_in_batches(
        ...     call_symbol='NIFTY25NOV24500CE',
        ...     put_symbol='NIFTY25NOV24000PE',
        ...     total_lots=167,
        ...     batch_size=20,
        ...     delay_seconds=20
        ... )
        >>> print(result['summary'])
        >>> # Result: 9 call orders + 9 put orders = 18 total orders
        {'call_success_count': 9, 'put_success_count': 9, 'total_orders_placed': 18}
    """
    import time
    import threading

    logger.info(f"Starting batch order placement: {total_lots} lots in batches of {batch_size}")

    # Get single authenticated session for all orders (optimization)
    try:
        client = _get_authenticated_client()
        logger.info("✅ Single Neo API session established for all orders")
    except Exception as e:
        logger.error(f"Failed to establish Neo session: {e}")
        return {
            'success': False,
            'error': f'Authentication failed: {str(e)}',
            'call_orders': [],
            'put_orders': []
        }

    # Use provided lot size or fetch dynamically from Neo API
    if lot_size is None:
        lot_size = get_lot_size_from_neo(call_symbol, client=client)
        logger.info(f"Fetched lot size: {lot_size} for {call_symbol}")
    else:
        logger.info(f"Using provided lot size: {lot_size} for {call_symbol}")

    call_orders = []
    put_orders = []
    batches_completed = 0

    # Calculate number of batches
    num_batches = (total_lots + batch_size - 1) // batch_size  # Ceiling division

    try:
        for batch_num in range(1, num_batches + 1):
            # Calculate lots for this batch
            remaining_lots = total_lots - (batch_num - 1) * batch_size
            current_batch_lots = min(batch_size, remaining_lots)
            current_batch_quantity = current_batch_lots * lot_size

            logger.info(f"Batch {batch_num}/{num_batches}: Placing {current_batch_lots} lots ({current_batch_quantity} qty)")

            # Optimization: Place CALL and PUT orders in parallel using threads
            call_result = {}
            put_result = {}

            def place_call_order():
                nonlocal call_result
                call_result = place_option_order(
                    trading_symbol=call_symbol,
                    transaction_type='S',  # SELL
                    quantity=current_batch_quantity,
                    product=product,
                    order_type='MKT',
                    client=client  # Reuse session
                )

            def place_put_order():
                nonlocal put_result
                put_result = place_option_order(
                    trading_symbol=put_symbol,
                    transaction_type='S',  # SELL
                    quantity=current_batch_quantity,
                    product=product,
                    order_type='MKT',
                    client=client  # Reuse session
                )

            # Start both orders in parallel
            call_thread = threading.Thread(target=place_call_order)
            put_thread = threading.Thread(target=place_put_order)

            logger.info(f"⚡ Placing CALL and PUT orders in parallel...")
            call_thread.start()
            put_thread.start()

            # Wait for both to complete
            call_thread.join()
            put_thread.join()

            # Record results
            call_orders.append({
                'batch': batch_num,
                'lots': current_batch_lots,
                'quantity': current_batch_quantity,
                'result': call_result
            })

            put_orders.append({
                'batch': batch_num,
                'lots': current_batch_lots,
                'quantity': current_batch_quantity,
                'result': put_result
            })

            if call_result.get('success'):
                logger.info(f"✅ CALL SELL batch {batch_num}: Order ID {call_result['order_id']}")
            else:
                logger.error(f"❌ CALL SELL batch {batch_num} failed: {call_result.get('error', 'Unknown error')}")

            if put_result.get('success'):
                logger.info(f"✅ PUT SELL batch {batch_num}: Order ID {put_result['order_id']}")
            else:
                logger.error(f"❌ PUT SELL batch {batch_num} failed: {put_result.get('error', 'Unknown error')}")

            batches_completed += 1

            # Delay before next batch (except for last batch)
            # We only wait between batches, not between CALL and PUT
            if batch_num < num_batches:
                logger.info(f"⏱️  Waiting {delay_seconds} seconds before next batch...")
                time.sleep(delay_seconds)

        # Calculate summary
        call_success_count = sum(1 for order in call_orders if order['result']['success'])
        put_success_count = sum(1 for order in put_orders if order['result']['success'])
        call_failed_count = len(call_orders) - call_success_count
        put_failed_count = len(put_orders) - put_success_count

        success = (call_failed_count == 0 and put_failed_count == 0)

        logger.info(f"Batch execution complete: {batches_completed}/{num_batches} batches processed")
        logger.info(f"Summary: Call {call_success_count}/{len(call_orders)} success, Put {put_success_count}/{len(put_orders)} success")

        return {
            'success': success,
            'total_lots': total_lots,
            'batches_completed': batches_completed,
            'total_batches': num_batches,
            'call_orders': call_orders,
            'put_orders': put_orders,
            'summary': {
                'call_success_count': call_success_count,
                'put_success_count': put_success_count,
                'call_failed_count': call_failed_count,
                'put_failed_count': put_failed_count,
                'total_orders_placed': len(call_orders) + len(put_orders)
            }
        }

    except Exception as e:
        logger.exception(f"Error in batch order placement: {e}")
        return {
            'success': False,
            'error': str(e),
            'total_lots': total_lots,
            'batches_completed': batches_completed,
            'call_orders': call_orders,
            'put_orders': put_orders
        }


def close_position_in_batches(
    trading_symbol: str,
    total_quantity: int,
    transaction_type: str,  # 'B' (BUY to close SHORT) or 'S' (SELL to close LONG)
    product: str = 'NRML',
    batch_size: int = 20,
    delay_seconds: int = 20,
    position_type: str = 'OPTION',  # 'OPTION' or 'FUTURE'
    cancellation_key: str = None,  # Cache key to check for cancellation between batches
    progress_key: str = None  # Cache key for progress tracking
):
    """
    Close a position (futures or options) in batches with delays.

    This function places exit orders in batches to avoid overwhelming the broker API
    and to provide better execution monitoring.

    Args:
        trading_symbol (str): Trading symbol (e.g., 'NIFTY25DECFUT', 'NIFTY25NOV24500CE')
        total_quantity (int): Total quantity to close (in shares/contracts)
        transaction_type (str): 'B' to close SHORT position, 'S' to close LONG position
        product (str): Product type - 'NRML', 'MIS' (default: 'NRML')
        batch_size (int): Maximum lots per order (default: 20, Neo API limit)
        delay_seconds (int): Delay between orders in seconds (default: 20)
        position_type (str): 'OPTION' or 'FUTURE' (default: 'OPTION')

    Returns:
        dict: Batch execution results
            {
                'success': True/False,
                'total_quantity': int,
                'batches_completed': int,
                'orders': [list of order results],
                'summary': {
                    'success_count': int,
                    'failed_count': int,
                    'total_orders_placed': int
                },
                'error': str (if failed)
            }

    Example:
        >>> # Close 3350 shares (167 lots) LONG position
        >>> result = close_position_in_batches(
        ...     trading_symbol='NIFTY25DECFUT',
        ...     total_quantity=3350,
        ...     transaction_type='S',  # SELL to close LONG
        ...     batch_size=20,
        ...     delay_seconds=20,
        ...     position_type='FUTURE'
        ... )
    """
    import time

    logger.info(f"Starting batch position closing: {total_quantity} qty in batches")

    # Get single authenticated session for all orders
    try:
        client = _get_authenticated_client()
        logger.info("✅ Single Neo API session established for closing position")
    except Exception as e:
        logger.error(f"Failed to establish Neo session: {e}")
        return {
            'success': False,
            'error': f'Authentication failed: {str(e)}',
            'orders': []
        }

    # Get lot size dynamically from Neo API
    lot_size = get_lot_size_from_neo(trading_symbol, client=client)
    logger.info(f"Using lot size: {lot_size} for {trading_symbol}")

    # Calculate total lots
    total_lots = total_quantity // lot_size if lot_size > 0 else 0
    logger.info(f"Total quantity: {total_quantity} shares = {total_lots} lots")

    orders = []
    batches_completed = 0

    # Calculate number of batches
    num_batches = (total_lots + batch_size - 1) // batch_size  # Ceiling division

    # Initialize progress
    if progress_key:
        cache.set(progress_key, {
            'batches_completed': 0,
            'total_batches': num_batches,
            'current_batch': None,
            'is_cancelled': False,
            'is_complete': False,
            'is_success': False,
            'last_log_message': f'Calculated {num_batches} batches for {total_lots} lots',
            'last_log_type': 'info'
        }, 600)

    try:
        for batch_num in range(1, num_batches + 1):
            # Check for cancellation before processing batch
            if cancellation_key and cache.get(cancellation_key):
                logger.warning(f"⚠️ Order placement cancelled by user at batch {batch_num}/{num_batches}")

                # Update progress
                if progress_key:
                    cache.set(progress_key, {
                        'batches_completed': batches_completed,
                        'total_batches': num_batches,
                        'current_batch': None,
                        'is_cancelled': True,
                        'is_complete': True,
                        'is_success': False,
                        'last_log_message': f'Cancelled at batch {batch_num}/{num_batches}',
                        'last_log_type': 'warning'
                    }, 600)

                success_count = sum(1 for o in orders if o['result'].get('success'))
                failed_count = len(orders) - success_count
                return {
                    'success': True,
                    'cancelled': True,
                    'total_quantity': total_quantity,
                    'batches_completed': batches_completed,
                    'total_batches': num_batches,
                    'orders': orders,
                    'summary': {
                        'success_count': success_count,
                        'failed_count': failed_count,
                        'total_orders_placed': len(orders)
                    },
                    'message': f'Order placement stopped by user. Completed {batches_completed}/{num_batches} batches.'
                }

            # Calculate lots for this batch
            remaining_lots = total_lots - (batch_num - 1) * batch_size
            current_batch_lots = min(batch_size, remaining_lots)
            current_batch_quantity = current_batch_lots * lot_size

            logger.info(f"Batch {batch_num}/{num_batches}: Closing {current_batch_lots} lots ({current_batch_quantity} qty)")

            # Update progress - starting batch
            if progress_key:
                cache.set(progress_key, {
                    'batches_completed': batches_completed,
                    'total_batches': num_batches,
                    'current_batch': {
                        'batch_num': batch_num,
                        'lots': current_batch_lots,
                        'quantity': current_batch_quantity
                    },
                    'is_cancelled': False,
                    'is_complete': False,
                    'is_success': False,
                    'last_log_message': f'Processing batch {batch_num}/{num_batches}: {current_batch_lots} lots',
                    'last_log_type': 'info'
                }, 600)

            # Place exit order
            order_result = place_option_order(
                trading_symbol=trading_symbol,
                transaction_type=transaction_type,
                quantity=current_batch_quantity,
                product=product,
                order_type='MKT',
                client=client  # Reuse session
            )

            # Record result
            orders.append({
                'batch': batch_num,
                'lots': current_batch_lots,
                'quantity': current_batch_quantity,
                'result': order_result
            })

            batches_completed += 1

            if order_result.get('success'):
                logger.info(f"✅ Exit batch {batch_num}: Order ID {order_result['order_id']}")
                # Update progress - batch succeeded
                if progress_key:
                    cache.set(progress_key, {
                        'batches_completed': batches_completed,
                        'total_batches': num_batches,
                        'current_batch': None,
                        'is_cancelled': False,
                        'is_complete': False,
                        'is_success': False,
                        'last_log_message': f'✅ Batch {batch_num}/{num_batches} completed successfully',
                        'last_log_type': 'success'
                    }, 600)
            else:
                # Batch failed - STOP immediately
                error_msg = order_result.get('error', 'Unknown error')
                logger.error(f"❌ Exit batch {batch_num} failed: {error_msg}")

                # Update progress - batch failed and STOP
                if progress_key:
                    cache.set(progress_key, {
                        'batches_completed': batches_completed,
                        'total_batches': num_batches,
                        'current_batch': None,
                        'is_cancelled': False,
                        'is_complete': True,
                        'is_success': False,
                        'last_log_message': f'❌ Batch {batch_num}/{num_batches} failed. Stopping execution.',
                        'last_log_type': 'error'
                    }, 600)

                # Return immediately with failure
                success_count = sum(1 for o in orders if o['result'].get('success'))
                failed_count = len(orders) - success_count
                return {
                    'success': False,
                    'error': f'Batch {batch_num} failed: {error_msg}',
                    'total_quantity': total_quantity,
                    'total_lots': total_lots,
                    'batches_completed': batches_completed,
                    'total_batches': num_batches,
                    'orders': orders,
                    'summary': {
                        'success_count': success_count,
                        'failed_count': failed_count,
                        'total_orders_placed': len(orders)
                    },
                    'message': f'Stopped at batch {batch_num}/{num_batches} due to failure.'
                }

            # Check for cancellation after batch completes (success or failure)
            if cancellation_key and cache.get(cancellation_key):
                logger.warning(f"⚠️ Order placement cancelled by user after batch {batch_num}/{num_batches}")

                # Update progress
                if progress_key:
                    cache.set(progress_key, {
                        'batches_completed': batches_completed,
                        'total_batches': num_batches,
                        'current_batch': None,
                        'is_cancelled': True,
                        'is_complete': True,
                        'is_success': False,
                        'last_log_message': f'🛑 Cancelled after batch {batch_num}/{num_batches}. Completed {batches_completed} batches.',
                        'last_log_type': 'warning'
                    }, 600)

                success_count = sum(1 for o in orders if o['result'].get('success'))
                failed_count = len(orders) - success_count
                return {
                    'success': True,
                    'cancelled': True,
                    'total_quantity': total_quantity,
                    'batches_completed': batches_completed,
                    'total_batches': num_batches,
                    'orders': orders,
                    'summary': {
                        'success_count': success_count,
                        'failed_count': failed_count,
                        'total_orders_placed': len(orders)
                    },
                    'message': f'Order placement stopped by user. Completed {batches_completed}/{num_batches} batches.'
                }

            # Delay before next batch (except for last batch)
            if batch_num < num_batches:
                logger.info(f"⏱️  Waiting {delay_seconds} seconds before next batch...")
                time.sleep(delay_seconds)

                # Check for cancellation after sleep
                if cancellation_key and cache.get(cancellation_key):
                    logger.warning(f"⚠️ Order placement cancelled by user during wait after batch {batch_num}/{num_batches}")

                    # Update progress
                    if progress_key:
                        cache.set(progress_key, {
                            'batches_completed': batches_completed,
                            'total_batches': num_batches,
                            'current_batch': None,
                            'is_cancelled': True,
                            'is_complete': True,
                            'is_success': False,
                            'last_log_message': f'🛑 Cancelled during wait after batch {batch_num}/{num_batches}. Completed {batches_completed} batches.',
                            'last_log_type': 'warning'
                        }, 600)

                    success_count = sum(1 for o in orders if o['result'].get('success'))
                    failed_count = len(orders) - success_count
                    return {
                        'success': True,
                        'cancelled': True,
                        'total_quantity': total_quantity,
                        'batches_completed': batches_completed,
                        'total_batches': num_batches,
                        'orders': orders,
                        'summary': {
                            'success_count': success_count,
                            'failed_count': failed_count,
                            'total_orders_placed': len(orders)
                        },
                        'message': f'Order placement stopped by user. Completed {batches_completed}/{num_batches} batches.'
                    }

        # Calculate summary
        success_count = sum(1 for order in orders if order['result']['success'])
        failed_count = len(orders) - success_count

        success = (failed_count == 0)

        logger.info(f"Batch execution complete: {batches_completed}/{num_batches} batches processed")
        logger.info(f"Summary: {success_count}/{len(orders)} success")

        # Final progress update
        if progress_key:
            cache.set(progress_key, {
                'batches_completed': batches_completed,
                'total_batches': num_batches,
                'current_batch': None,
                'is_cancelled': False,
                'is_complete': True,
                'is_success': success,
                'last_log_message': f'✅ Completed: {success_count}/{len(orders)} orders successful' if success else f'⚠️ Completed with {failed_count} failures',
                'last_log_type': 'success' if success else 'warning'
            }, 600)

        return {
            'success': success,
            'total_quantity': total_quantity,
            'total_lots': total_lots,
            'batches_completed': batches_completed,
            'total_batches': num_batches,
            'orders': orders,
            'summary': {
                'success_count': success_count,
                'failed_count': failed_count,
                'total_orders_placed': len(orders)
            }
        }

    except Exception as e:
        logger.exception(f"Error in batch position closing: {e}")
        return {
            'success': False,
            'error': str(e),
            'total_quantity': total_quantity,
            'batches_completed': batches_completed,
            'orders': orders
        }


def close_strangle_positions_in_batches(
    call_symbol: str,
    put_symbol: str,
    total_lots: int,
    batch_size: int = 20,
    delay_seconds: int = 20,
    product: str = 'NRML',
    lot_size: int = None,  # Pass to skip API lookup (required for weekly compact symbols)
):
    """
    Close strangle positions (Call BUY + Put BUY) in batches with delays.

    This function closes strangle positions in batches to avoid overwhelming the broker API.
    Since strangles are typically sold, closing them requires buying back both legs.

    Args:
        call_symbol (str): Call option Neo trading symbol
        put_symbol (str): Put option Neo trading symbol
        total_lots (int): Total number of lots to close
        batch_size (int): Maximum lots per order (default: 20, Neo API limit)
        delay_seconds (int): Delay between orders in seconds (default: 20)
        product (str): Product type - 'NRML', 'MIS' (default: 'NRML')
        lot_size (int): Lot size if already known; fetched from Neo API if None

    Returns:
        dict: Batch execution results
            {
                'success': True/False,
                'total_lots': int,
                'batches_completed': int,
                'call_orders': [list of order results],
                'put_orders': [list of order results],
                'summary': {
                    'call_success_count': int,
                    'put_success_count': int,
                    'call_failed_count': int,
                    'put_failed_count': int
                },
                'error': str (if failed)
            }
    """
    import time
    import threading

    logger.info(f"Starting batch strangle closing: {total_lots} lots in batches of {batch_size}")

    # Get single authenticated session for all orders
    try:
        client = _get_authenticated_client()
        logger.info("✅ Single Neo API session established for all orders")
    except Exception as e:
        logger.error(f"Failed to establish Neo session: {e}")
        return {
            'success': False,
            'error': f'Authentication failed: {str(e)}',
            'call_orders': [],
            'put_orders': []
        }

    # Use provided lot size or fetch from Neo API (handles both monthly and weekly formats)
    if lot_size is None:
        lot_size = get_lot_size_from_neo(call_symbol, client=client)
    logger.info(f"Using lot size: {lot_size} for {call_symbol}")

    call_orders = []
    put_orders = []
    batches_completed = 0

    # Calculate number of batches
    num_batches = (total_lots + batch_size - 1) // batch_size  # Ceiling division

    try:
        for batch_num in range(1, num_batches + 1):
            # Calculate lots for this batch
            remaining_lots = total_lots - (batch_num - 1) * batch_size
            current_batch_lots = min(batch_size, remaining_lots)
            current_batch_quantity = current_batch_lots * lot_size

            logger.info(f"Batch {batch_num}/{num_batches}: Closing {current_batch_lots} lots ({current_batch_quantity} qty)")

            # Optimization: Place CALL and PUT exit orders in parallel using threads
            call_result = {}
            put_result = {}

            def place_call_exit_order():
                nonlocal call_result
                call_result = place_option_order(
                    trading_symbol=call_symbol,
                    transaction_type='B',  # BUY to close SELL
                    quantity=current_batch_quantity,
                    product=product,
                    order_type='MKT',
                    client=client  # Reuse session
                )

            def place_put_exit_order():
                nonlocal put_result
                put_result = place_option_order(
                    trading_symbol=put_symbol,
                    transaction_type='B',  # BUY to close SELL
                    quantity=current_batch_quantity,
                    product=product,
                    order_type='MKT',
                    client=client  # Reuse session
                )

            # Start both orders in parallel
            call_thread = threading.Thread(target=place_call_exit_order)
            put_thread = threading.Thread(target=place_put_exit_order)

            logger.info(f"⚡ Placing CALL and PUT exit orders in parallel...")
            call_thread.start()
            put_thread.start()

            # Wait for both to complete
            call_thread.join()
            put_thread.join()

            # Record results
            call_orders.append({
                'batch': batch_num,
                'lots': current_batch_lots,
                'quantity': current_batch_quantity,
                'result': call_result
            })

            put_orders.append({
                'batch': batch_num,
                'lots': current_batch_lots,
                'quantity': current_batch_quantity,
                'result': put_result
            })

            if call_result.get('success'):
                logger.info(f"✅ CALL EXIT batch {batch_num}: Order ID {call_result['order_id']}")
            else:
                logger.error(f"❌ CALL EXIT batch {batch_num} failed: {call_result.get('error', 'Unknown error')}")

            if put_result.get('success'):
                logger.info(f"✅ PUT EXIT batch {batch_num}: Order ID {put_result['order_id']}")
            else:
                logger.error(f"❌ PUT EXIT batch {batch_num} failed: {put_result.get('error', 'Unknown error')}")

            batches_completed += 1

            # Delay before next batch (except for last batch)
            if batch_num < num_batches:
                logger.info(f"⏱️  Waiting {delay_seconds} seconds before next batch...")
                time.sleep(delay_seconds)

        # Calculate summary
        call_success_count = sum(1 for order in call_orders if order['result']['success'])
        put_success_count = sum(1 for order in put_orders if order['result']['success'])
        call_failed_count = len(call_orders) - call_success_count
        put_failed_count = len(put_orders) - put_success_count

        success = (call_failed_count == 0 and put_failed_count == 0)

        logger.info(f"Batch strangle closing complete: {batches_completed}/{num_batches} batches processed")
        logger.info(f"Summary: Call {call_success_count}/{len(call_orders)} success, Put {put_success_count}/{len(put_orders)} success")

        return {
            'success': success,
            'total_lots': total_lots,
            'batches_completed': batches_completed,
            'total_batches': num_batches,
            'call_orders': call_orders,
            'put_orders': put_orders,
            'summary': {
                'call_success_count': call_success_count,
                'put_success_count': put_success_count,
                'call_failed_count': call_failed_count,
                'put_failed_count': put_failed_count,
                'total_orders_placed': len(call_orders) + len(put_orders)
            }
        }

    except Exception as e:
        logger.exception(f"Error in batch strangle closing: {e}")
        return {
            'success': False,
            'error': str(e),
            'total_lots': total_lots,
            'batches_completed': batches_completed,
            'call_orders': call_orders,
            'put_orders': put_orders
        }


def get_neo_open_positions(include_raw=False) -> dict:
    """
    Single source of truth for Neo open positions.
    Called by both web API and Telegram bot.

    Args:
        include_raw: If True, includes raw API responses for debug display.

    Returns:
        {
            'positions': [
                {
                    'symbol', 'trading_symbol', 'exchange', 'product', 'direction',
                    'quantity' (lots), 'net_quantity' (lots), 'net_quantity_shares',
                    'lot_size', 'average_price', 'ltp',
                    'unrealized_pnl', 'total_pnl', 'pnl_percentage',
                    'expiry_date',
                }, ...
            ],
            # Only when include_raw=True:
            'raw_positions_api': <raw positions response>,
            'raw_trade_report_api': <raw trade_report response>,
        }
    or {'error': str} on failure.
    """
    try:
        try:
            _, positions, _, raw_positions_resp, raw_trade_resp = fetch_and_save_kotakneo_data()
        except NeoAuthenticationError:
            # Session might be stale — invalidate cached instance and retry once
            logger.warning("Neo session error on positions fetch — invalidating cache and retrying")
            from tools.neo import _cache_lock
            import tools.neo as neo_module
            with _cache_lock:
                neo_module._cached_instance = None
            _, positions, _, raw_positions_resp, raw_trade_resp = fetch_and_save_kotakneo_data()

        # ── Fetch Holdings API for TRUE average prices (carry-forward positions) ──
        # The positions() API returns MTM-settled prices that reset daily.
        # The holdings() API returns the actual average purchase price.
        client = _get_authenticated_client()
        holdings_avg_map = {}
        raw_holdings_resp = None

        try:
            raw_holdings_resp = client.holdings()
            if isinstance(raw_holdings_resp, dict) and 'data' in raw_holdings_resp:
                holdings_data = raw_holdings_resp.get('data', [])
                if isinstance(holdings_data, list):
                    for h in holdings_data:
                        symbol = h.get('symbol', '').upper()
                        avg_price = _parse_float(h.get('averagePrice', 0))
                        exchange_seg = h.get('exchangeSegment', '')

                        if avg_price > 0:
                            entry = {
                                'avg_price': avg_price,
                                'quantity': int(h.get('quantity', 0)),
                                'holding_cost': _parse_float(h.get('holdingCost', 0)),
                                'exchange_segment': exchange_seg,
                                'instrument_type': h.get('instrumentType', ''),
                                'expiry_date': h.get('expiryDate', ''),
                            }
                            # Store as list: same symbol can have futures + options entries
                            if symbol not in holdings_avg_map:
                                holdings_avg_map[symbol] = []
                            holdings_avg_map[symbol].append(entry)
                            logger.info(f"[HOLDINGS] {symbol}: avg_price={avg_price:.2f}, "
                                       f"qty={h.get('quantity')}, segment={exchange_seg}")
        except Exception as holdings_err:
            logger.warning(f"Could not fetch holdings for avg prices: {holdings_err}")

        # ── Parse Trade Report for today's trades (same-day accuracy) ──
        # Trade report has actual execution prices for trades made TODAY
        today_trades_map = {}  # trdSym -> {buy_qty, buy_value, sell_qty, sell_value}
        if raw_trade_resp and isinstance(raw_trade_resp, dict) and 'data' in raw_trade_resp:
            trades_data = raw_trade_resp.get('data', [])
            if isinstance(trades_data, list):
                for t in trades_data:
                    symbol = (t.get('sym') or '').upper()
                    trd_sym = (t.get('trdSym') or '').upper()
                    # Key by trdSym (specific, e.g. NIFTY2621026350CE) not sym (base NIFTY)
                    # to avoid merging futures + options trades together
                    key = trd_sym or symbol
                    if not key:
                        continue

                    if key not in today_trades_map:
                        today_trades_map[key] = {
                            'buy_qty': 0, 'buy_value': 0,
                            'sell_qty': 0, 'sell_value': 0,
                            'trading_symbol': trd_sym,
                        }

                    filled_qty = int(float(t.get('fldQty', 0) or 0))
                    avg_prc = _parse_float(t.get('avgPrc', 0))
                    trans_type = t.get('trnsTp', '')

                    if trans_type == 'B':
                        today_trades_map[key]['buy_qty'] += filled_qty
                        today_trades_map[key]['buy_value'] += filled_qty * avg_prc
                    elif trans_type == 'S':
                        today_trades_map[key]['sell_qty'] += filled_qty
                        today_trades_map[key]['sell_value'] += filled_qty * avg_prc

                for sym, data in today_trades_map.items():
                    if data['buy_qty'] > 0:
                        data['buy_avg'] = data['buy_value'] / data['buy_qty']
                        logger.info(f"[TODAY TRADES] {sym}: BUY {data['buy_qty']} @ avg {data['buy_avg']:.2f}")
                    if data['sell_qty'] > 0:
                        data['sell_avg'] = data['sell_value'] / data['sell_qty']
                        logger.info(f"[TODAY TRADES] {sym}: SELL {data['sell_qty']} @ avg {data['sell_avg']:.2f}")

        # ── Build position dicts ──
        positions_data = []
        for pos in positions:
            broker_avg_price = float(pos.average_price or 0)
            ltp = float(pos.ltp or 0)
            net_qty = pos.net_quantity  # in shares

            if net_qty == 0:
                continue

            # Use lot size from broker API (stored in DB), not hardcoded
            lot_size = pos.lot_size or 1

            # ── Calculate TRUE average price combining Holdings + Today's Trades ──
            # Priority:
            # 1. If both carry-forward (holdings) and today's trades -> weighted blend
            # 2. If only carry-forward (no trades today) -> use holdings avg
            # 3. If only today's trades (new position) -> use trade_report avg
            # 4. Fallback -> use positions API (MTM, least accurate)
            symbol_upper = (pos.symbol or '').upper()
            trading_symbol_upper = (pos.trading_symbol or '').upper()

            # Match by trading_symbol first (specific, e.g., NIFTY26FEB26350CE),
            # then fall back to base symbol (e.g., NIFTY)
            # Holdings map is a list per symbol (same symbol can have futures + options).
            # Pick the entry matching position direction (LONG→qty>0, SHORT→qty<0).
            #
            # A symbol like HDFCBANK can appear in holdings TWICE: once as an equity
            # demat holding (nse_cm, e.g. 6000 shares @ ₹701) and once as a futures
            # carry-forward (nse_fo, e.g. 96250 shares @ ₹913).  Without segment
            # filtering, `next(e for e in entries if e['quantity'] > 0)` picks the
            # first entry — often the cheaper equity holding — and blends it with
            # today's F&O trades, producing a completely wrong average.
            # Fix: keep only holdings entries whose exchange segment matches the
            # position's own segment so each entry is compared apples-to-apples.
            holdings_entries = (holdings_avg_map.get(trading_symbol_upper)
                                or holdings_avg_map.get(symbol_upper)
                                or [])
            pos_seg = (pos.exchange_segment or '').lower()
            if holdings_entries and pos_seg:
                seg_filtered = [e for e in holdings_entries
                                if (e.get('exchange_segment') or '').lower() == pos_seg]
                if seg_filtered:
                    holdings_entries = seg_filtered
                # else: no segment match — keep all as fallback (unknown segment)

            # If multiple entries still remain after segment filtering (e.g. same symbol has
            # both Mar and Apr futures in nse_fo), narrow further by expiry date.
            # Without this, the code picks the first entry — often the wrong contract month.
            if len(holdings_entries) > 1 and pos.expiry_date:
                expiry_str = pos.expiry_date.strftime('%d-%b-%Y').upper()  # e.g. '30-MAR-2026'
                expiry_filtered = [e for e in holdings_entries
                                   if (e.get('expiry_date') or '').upper() == expiry_str]
                if expiry_filtered:
                    holdings_entries = expiry_filtered
                    logger.info(f"[HOLDINGS MATCH] {pos.symbol}: Narrowed to expiry {expiry_str} "
                                f"-> avg={expiry_filtered[0]['avg_price']:.2f}")

            today_data = (today_trades_map.get(trading_symbol_upper)
                          or today_trades_map.get(symbol_upper))

            # Determine direction for correct avg calculation
            direction = 'LONG' if net_qty > 0 else 'SHORT'

            # Pick holdings entry matching position direction
            if direction == 'LONG':
                holdings_data = next((e for e in holdings_entries if e['quantity'] > 0), None)
            else:
                holdings_data = next((e for e in holdings_entries if e['quantity'] < 0), None)
            avg_price = None
            avg_price_source = 'unknown'

            # Check for manual avg_price override (fixes DB chain corruption)
            override = PositionAvgOverride.objects.filter(
                trading_symbol=pos.trading_symbol
            ).first()
            if override:
                avg_price = float(override.manual_avg_price)
                avg_price_source = 'manual override'
                logger.info(f"[AVG OVERRIDE] {pos.symbol}: Using manual override avg={avg_price:.2f}")

            # Get carry-forward quantities from raw positions data
            # Match by trdSym (specific) first, fall back to sym (base)
            raw_pos = None
            if raw_positions_resp:
                raw_pos = next((p for p in raw_positions_resp.get('data', [])
                               if (p.get('trdSym') or '').upper() == trading_symbol_upper), None)
                if not raw_pos:
                    raw_pos = next((p for p in raw_positions_resp.get('data', [])
                                   if (p.get('sym') or '').upper() == symbol_upper), None)
            cf_buy_qty = int(raw_pos.get('cfBuyQty', 0)) if raw_pos else 0
            cf_sell_qty = int(raw_pos.get('cfSellQty', 0)) if raw_pos else 0

            if avg_price is not None:
                # Override was applied — skip the normal avg_price computation
                pass
            elif direction == 'LONG':
                # For LONG: avg is weighted avg of buys
                holdings_qty = holdings_data['quantity'] if holdings_data else 0
                holdings_avg = holdings_data['avg_price'] if holdings_data else 0
                today_buy_qty = today_data['buy_qty'] if today_data else 0
                today_buy_avg = today_data.get('buy_avg', 0) if today_data else 0
                today_sell_qty = today_data['sell_qty'] if today_data else 0

                # Effective carry-forward after today's exits (sells reduce LONG cf)
                effective_holdings = max(holdings_qty - today_sell_qty, 0) if today_sell_qty > 0 else holdings_qty

                if effective_holdings > 0 and today_buy_qty > 0 and holdings_avg > 0:
                    # Blend remaining carry-forward with today's new buys
                    total_qty = effective_holdings + today_buy_qty
                    avg_price = (effective_holdings * holdings_avg + today_buy_qty * today_buy_avg) / total_qty
                    avg_price_source = 'blended (holdings + today)'
                    logger.info(f"[AVG PRICE] {pos.symbol}: {avg_price_source} = {avg_price:.2f} "
                               f"(eff_holdings: {effective_holdings}@{holdings_avg:.2f}, today_buy: {today_buy_qty}@{today_buy_avg:.2f})")
                elif today_buy_qty > 0 and effective_holdings == 0:
                    # All carry-forward sold (full close+reopen) or new position today
                    avg_price = today_buy_avg
                    avg_price_source = 'trade_report'
                    logger.info(f"[AVG PRICE] {pos.symbol}: Using Trade Report avg {avg_price:.2f} (cf fully exited or new)")
                elif holdings_qty > 0 and holdings_avg > 0:
                    # Pure carry-forward, no new buys today (sells don't change avg)
                    avg_price = holdings_avg
                    avg_price_source = 'holdings'
                    logger.info(f"[AVG PRICE] {pos.symbol}: Using Holdings avg {avg_price:.2f} (carry-forward only)")
                elif broker_avg_price > 0:
                    # No holdings data — use broker_avg_price from fetch_and_save (just computed)
                    avg_price = broker_avg_price
                    avg_price_source = 'positions (blended from DB)'
                    logger.info(f"[AVG PRICE] {pos.symbol}: Using DB-blended avg {avg_price:.2f} "
                               f"(cf_buy_qty={cf_buy_qty}, no holdings data)")
                else:
                    # Fallback to positions API
                    avg_price = broker_avg_price
                    avg_price_source = 'positions (MTM)'
                    logger.info(f"[AVG PRICE] {pos.symbol}: Fallback to positions MTM avg {avg_price:.2f}")

            else:  # SHORT
                # For SHORT: avg is weighted avg of sells
                holdings_qty = abs(holdings_data['quantity']) if holdings_data else 0
                holdings_avg = holdings_data['avg_price'] if holdings_data else 0
                today_sell_qty = today_data['sell_qty'] if today_data else 0
                today_sell_avg = today_data.get('sell_avg', 0) if today_data else 0
                today_buy_qty_short = today_data['buy_qty'] if today_data else 0

                # Effective carry-forward after today's exits (buys reduce SHORT cf)
                effective_holdings = max(holdings_qty - today_buy_qty_short, 0) if today_buy_qty_short > 0 else holdings_qty

                if effective_holdings > 0 and today_sell_qty > 0 and holdings_avg > 0:
                    total_qty = effective_holdings + today_sell_qty
                    avg_price = (effective_holdings * holdings_avg + today_sell_qty * today_sell_avg) / total_qty
                    avg_price_source = 'blended (holdings + today)'
                    logger.info(f"[AVG PRICE] {pos.symbol}: {avg_price_source} = {avg_price:.2f}")
                elif today_sell_qty > 0 and effective_holdings == 0:
                    avg_price = today_sell_avg
                    avg_price_source = 'trade_report'
                    logger.info(f"[AVG PRICE] {pos.symbol}: Using Trade Report avg {avg_price:.2f} (cf fully exited or new)")
                elif holdings_qty > 0 and holdings_avg > 0:
                    # Pure carry-forward, no new sells today
                    avg_price = holdings_avg
                    avg_price_source = 'holdings'
                    logger.info(f"[AVG PRICE] {pos.symbol}: Using Holdings avg {avg_price:.2f} (carry-forward only)")
                elif broker_avg_price > 0:
                    avg_price = broker_avg_price
                    avg_price_source = 'positions (blended from DB)'
                    logger.info(f"[AVG PRICE] {pos.symbol}: Using DB-blended avg {avg_price:.2f} "
                               f"(cf_sell_qty={cf_sell_qty}, no holdings data)")
                else:
                    avg_price = broker_avg_price
                    avg_price_source = 'positions (MTM)'
                    logger.info(f"[AVG PRICE] {pos.symbol}: Fallback to positions MTM avg {avg_price:.2f}")

            # Update BrokerPosition with correct avg so DB chain stays clean
            if avg_price and avg_price > 0 and avg_price_source != 'positions (MTM)':
                if abs(float(pos.average_price) - avg_price) > 0.01:
                    pos.average_price = Decimal(str(round(avg_price, 2)))
                    pos.save(update_fields=['average_price'])
                    logger.info(f"[DB FIX] {pos.symbol}: Updated BrokerPosition avg to {avg_price:.2f} (source={avg_price_source})")

            net_qty_lots = net_qty // lot_size if lot_size > 0 else net_qty
            unrealized_pnl = net_qty * (ltp - avg_price) if ltp > 0 else 0.0
            direction = 'LONG' if net_qty > 0 else 'SHORT'
            investment = avg_price * abs(net_qty)
            pnl_pct = (unrealized_pnl / investment * 100) if investment > 0 else 0

            # Get today's trade info for response
            today_buy_qty = today_data['buy_qty'] if today_data else 0
            today_buy_avg = today_data.get('buy_avg', 0) if today_data else 0
            today_sell_qty = today_data['sell_qty'] if today_data else 0
            today_sell_avg = today_data.get('sell_avg', 0) if today_data else 0

            # Debug: log computation details for options
            is_option_pos = bool(re.search(r'(CE|PE)$', pos.trading_symbol or ''))
            if is_option_pos:
                logger.info(
                    f"[POS DEBUG] {pos.trading_symbol}: net_qty={net_qty}, lot_size={lot_size}, "
                    f"net_qty_lots={net_qty_lots}, ltp={ltp:.2f}, avg_price={avg_price:.2f}, "
                    f"avg_source={avg_price_source}, broker_avg={broker_avg_price:.2f}, "
                    f"holdings_match={'YES' if holdings_data else 'NO'}, "
                    f"buy_qty={pos.buy_qty}, sell_qty={pos.sell_qty}, "
                    f"buy_amt={float(pos.buy_amount or 0):.2f}, sell_amt={float(pos.sell_amount or 0):.2f}"
                )

            # Include raw position fields for debugging
            raw_fields = None
            if raw_pos:
                raw_fields = {
                    'cfBuyQty': raw_pos.get('cfBuyQty'),
                    'cfSellQty': raw_pos.get('cfSellQty'),
                    'flBuyQty': raw_pos.get('flBuyQty'),
                    'flSellQty': raw_pos.get('flSellQty'),
                    'cfBuyAmt': raw_pos.get('cfBuyAmt'),
                    'cfSellAmt': raw_pos.get('cfSellAmt'),
                    'buyAmt': raw_pos.get('buyAmt'),
                    'sellAmt': raw_pos.get('sellAmt'),
                    'lotSz': raw_pos.get('lotSz'),
                    'stkPrc': raw_pos.get('stkPrc'),
                    'optTp': raw_pos.get('optTp'),
                    'trdSym': raw_pos.get('trdSym'),
                }

            positions_data.append({
                'symbol': pos.symbol,
                'trading_symbol': pos.trading_symbol or pos.symbol,
                'exchange': pos.exchange_segment or 'nse_fo',
                'product': pos.product or 'NRML',
                'direction': direction,
                'quantity': abs(net_qty_lots),
                'net_quantity': net_qty_lots,
                'net_quantity_shares': net_qty,
                'lot_size': lot_size,
                'average_price': avg_price,
                'holdings_avg_price': holdings_data['avg_price'] if holdings_data else None,
                'positions_avg_price': broker_avg_price,  # MTM avg (resets daily)
                'today_buy_qty': today_buy_qty,
                'today_buy_avg': round(today_buy_avg, 2) if today_buy_avg else None,
                'today_sell_qty': today_sell_qty,
                'today_sell_avg': round(today_sell_avg, 2) if today_sell_avg else None,
                'avg_price_source': avg_price_source,
                'ltp': ltp,
                'unrealized_pnl': round(unrealized_pnl, 2),
                'total_pnl': round(unrealized_pnl, 2),
                'pnl_percentage': round(pnl_pct, 2),
                'expiry_date': pos.expiry_date.strftime('%Y-%m-%d') if pos.expiry_date else None,
                '_raw_fields': raw_fields,
            })

        result = {
            'positions': positions_data,
        }

        if include_raw:
            result['raw_positions_api'] = raw_positions_resp
            result['raw_trade_report_api'] = raw_trade_resp
            result['raw_holdings_api'] = raw_holdings_resp

        return result

    except NeoAuthenticationError:
        raise  # Let callers handle auth errors specifically
    except Exception as e:
        logger.error(f"Error in get_neo_open_positions: {e}", exc_info=True)
        return {'error': str(e)}
