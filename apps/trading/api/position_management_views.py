"""
Position Management API Views

Endpoints for managing trading positions - viewing active positions,
getting position details, closing positions, and position averaging analysis.
"""

import logging
import json
import time
import re
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.core.cache import cache

from apps.brokers.integrations.breeze import get_breeze_client
from apps.positions.models import Position
from apps.brokers.models import Order
from apps.core.constants import POSITION_STATUS_ACTIVE
from apps.data.models import ContractData

logger = logging.getLogger(__name__)


@login_required
@require_GET
def get_active_positions(request):
    """
    Get LIVE active positions from broker API (Breeze or Neo)

    Fetches real-time open positions directly from the broker's API
    instead of reading from database. Shows only positions with non-zero quantity.

    GET params:
        - broker: 'breeze' or 'neo'

    Returns:
        JSON with live positions list including LTP and real-time P&L
    """
    try:
        broker = request.GET.get('broker', '').lower()

        if broker not in ['breeze', 'neo']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid broker. Must be "breeze" or "neo"'
            })

        result = None

        if broker == 'breeze':
            result = _fetch_breeze_positions()
            if 'error' in result:
                return JsonResponse({
                    'success': False,
                    'error': result['error']
                })

        elif broker == 'neo':
            result = _fetch_neo_positions()
            if 'error' in result:
                return JsonResponse({
                    'success': False,
                    'error': result['error']
                })

        positions_data = result.get('positions', [])
        broker_name = 'ICICI Breeze' if broker == 'breeze' else 'Kotak Neo'

        response = {
            'success': True,
            'broker': broker_name,
            'positions': positions_data,
            'count': len(positions_data),
        }

        # Include RMS-based Net P&L (from limits API) for Neo
        # This is the account-level P&L that matches NEO UI
        # Formula: Trader Net P&L = -(FoUnRlsMtomPrsnt + FoRlsMtomPrsnt)
        if result.get('rms_net_pnl') is not None:
            response['rms_net_pnl'] = result['rms_net_pnl']
            response['rms_unrealized_mtm'] = result.get('rms_unrealized_mtm')
            response['rms_realized_mtm'] = result.get('rms_realized_mtm')

        # Include raw API debug data for both brokers
        # Neo returns full response dicts (e.g. {'stat':'Ok','data':[...]})
        # Breeze returns plain lists
        try:
            raw_pos = result.get('raw_positions_api')
            raw_trades = result.get('raw_trade_report_api')
            raw_limits = result.get('raw_limits_api')
            # Round-trip through json to catch NaN/Infinity/non-standard types
            response['raw_positions_api'] = json.loads(json.dumps(raw_pos, default=str)) if raw_pos is not None else None
            response['raw_trade_report_api'] = json.loads(json.dumps(raw_trades, default=str)) if raw_trades is not None else None
            response['raw_limits_api'] = json.loads(json.dumps(raw_limits, default=str)) if raw_limits is not None else None
        except Exception as e:
            logger.warning(f"Could not serialize raw API data: {e}")
            response['raw_positions_api'] = None
            response['raw_trade_report_api'] = None
            response['raw_limits_api'] = None

        logger.info(f"[{broker}] Returning {len(positions_data)} positions, "
                     f"raw_positions type={type(result.get('raw_positions_api')).__name__}, "
                     f"raw_trades type={type(result.get('raw_trade_report_api')).__name__}")

        return JsonResponse(response)

    except Exception as e:
        logger.error(f"Error fetching active positions: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


def _fetch_breeze_positions():
    """Fetch live positions from Breeze API"""
    positions_data = []
    raw_positions = []
    breeze = get_breeze_client()
    pos_resp = breeze.get_portfolio_positions()

    if pos_resp and pos_resp.get('Status') == 200:
        raw_positions = pos_resp.get('Success', [])
        if not isinstance(raw_positions, list):
            raw_positions = []

        for p in raw_positions:
            quantity = int(p.get('quantity') or 0)

            # Skip positions with zero quantity (closed positions)
            if quantity == 0:
                continue

            avg_price = float(p.get('average_price') or 0)
            ltp = float(p.get('ltp') or p.get('price') or 0)

            # Calculate unrealized P&L
            if quantity > 0:  # LONG position
                unrealized_pnl = (ltp - avg_price) * quantity
                direction = 'LONG'
            else:  # SHORT position
                unrealized_pnl = (avg_price - ltp) * abs(quantity)
                direction = 'SHORT'

            # Realized P&L is typically 0 for carry-forward positions
            realized_pnl = 0.0

            symbol = p.get('stock_code', 'N/A')
            product = p.get('product_type', 'N/A')
            exchange = p.get('exchange_code', 'NFO')

            # Extract expiry date from Breeze response
            expiry_date = None
            expiry_dt_str = p.get('expiry_date', '')
            if expiry_dt_str:
                try:
                    for fmt in ['%d-%b-%Y', '%Y-%m-%d', '%d-%m-%Y']:
                        try:
                            expiry_dt = datetime.strptime(expiry_dt_str, fmt)
                            expiry_date = expiry_dt.strftime('%Y-%m-%d')
                            break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Could not parse Breeze expiry date '{expiry_dt_str}': {e}")

            positions_data.append({
                'symbol': symbol,
                'exchange': exchange,
                'product': product,
                'direction': direction,
                'quantity': abs(quantity),
                'net_quantity': quantity,
                'net_quantity_shares': quantity,
                'average_price': avg_price,
                'ltp': ltp,
                'unrealized_pnl': round(unrealized_pnl, 2),
                'realized_pnl': round(realized_pnl, 2),
                'total_pnl': round(unrealized_pnl + realized_pnl, 2),
                'pnl_percentage': round((unrealized_pnl / (avg_price * abs(quantity)) * 100), 2) if avg_price > 0 else 0,
                'expiry_date': expiry_date,
            })
    else:
        logger.warning(f"Breeze positions API returned non-200 status: {pos_resp}")

    return {
        'positions': positions_data,
        'raw_positions_api': raw_positions,
    }


def _fetch_neo_positions():
    """
    Fetch live positions from Neo API.

    Uses BOTH client.positions() AND client.trade_report() to build accurate position data.
    - positions() gives us current open positions and instrument info
    - trade_report() gives us actual executed trade prices for accurate avg price

    SDK response formats:
    - Success: {'stat': 'Ok', 'stCode': 200, 'data': [...]}
    - Error:   {'Error': exception_obj} or {'Error Message': '...'}
    - Network: None (PositionsAPI catches RequestException, prints, returns None)
    """
    from apps.brokers.integrations.kotak_neo import get_kotak_neo_client, get_ltp_from_neo

    positions_data = []

    def _safe_int(val, default=0):
        try:
            if val is None:
                return default
            return int(float(val)) if val != '' else default
        except (ValueError, TypeError):
            return default

    def _safe_float(val, default=0.0):
        try:
            if val is None:
                return default
            return float(val) if val != '' else default
        except (ValueError, TypeError):
            return default

    try:
        client = get_kotak_neo_client()
        logger.info("Neo client authenticated, calling positions API...")

        # ── 1. Call positions() API ──
        # Returns: {'stat':'Ok','data':[...]} | {'Error':e} | {'Error Message':'...'} | None
        positions_resp = client.positions()
        logger.info(f"Neo positions() response type={type(positions_resp).__name__}, "
                     f"keys={list(positions_resp.keys()) if isinstance(positions_resp, dict) else 'N/A'}")

        # Extract data array; store FULL response for debug
        raw_positions_full = positions_resp  # Full response for debug display
        raw_positions = []
        if isinstance(positions_resp, dict):
            if 'Error' in positions_resp or 'Error Message' in positions_resp:
                err = positions_resp.get('Error') or positions_resp.get('Error Message')
                logger.error(f"Neo positions() returned error: {err}")
            else:
                raw_positions = positions_resp.get('data', [])
                if not isinstance(raw_positions, list):
                    raw_positions = []
        elif positions_resp is None:
            logger.error("Neo positions() returned None (likely network error in SDK)")
            raw_positions_full = {'_error': 'positions() returned None - SDK network error'}
        else:
            logger.error(f"Neo positions() unexpected type: {type(positions_resp)}")
            raw_positions_full = {'_error': f'Unexpected response type: {type(positions_resp).__name__}'}

        logger.info(f"Neo positions(): {len(raw_positions)} position entries to process")

        # ── 2. Call trade_report() API ──
        # Returns: {'stat':'Ok','data':[...]} | {'Error':e} | {'Error Message':'...'} | None
        trade_resp_full = None
        raw_trades = []
        try:
            trade_resp = client.trade_report()
            trade_resp_full = trade_resp  # Full response for debug display
            logger.info(f"Neo trade_report() response type={type(trade_resp).__name__}, "
                         f"keys={list(trade_resp.keys()) if isinstance(trade_resp, dict) else 'N/A'}")

            if isinstance(trade_resp, dict):
                if 'Error' in trade_resp or 'Error Message' in trade_resp:
                    err = trade_resp.get('Error') or trade_resp.get('Error Message')
                    logger.warning(f"Neo trade_report() returned error: {err}")
                else:
                    raw_trades = trade_resp.get('data', [])
                    if not isinstance(raw_trades, list):
                        raw_trades = []
            elif trade_resp is None:
                logger.warning("Neo trade_report() returned None")
                trade_resp_full = {'_error': 'trade_report() returned None'}
        except Exception as e:
            logger.error(f"Error calling trade_report(): {e}", exc_info=True)
            trade_resp_full = {'_error': str(e)}

        logger.info(f"Neo trade_report(): {len(raw_trades)} trades to process")

        # ── 3. Aggregate trades by trading symbol ──
        trades_by_symbol = {}
        for t in raw_trades:
            tsym = t.get('trdSym', '')
            if not tsym:
                continue
            if tsym not in trades_by_symbol:
                trades_by_symbol[tsym] = {'buys': [], 'sells': []}

            filled_qty = _safe_int(t.get('fldQty', 0))
            avg_prc = _safe_float(t.get('avgPrc', 0))
            trans_type = t.get('trnsTp', '')

            if trans_type == 'B':
                trades_by_symbol[tsym]['buys'].append({
                    'qty': filled_qty, 'price': avg_prc, 'raw': t
                })
            elif trans_type == 'S':
                trades_by_symbol[tsym]['sells'].append({
                    'qty': filled_qty, 'price': avg_prc, 'raw': t
                })

        # ── 4. Process each position ──
        for idx, p in enumerate(raw_positions):
            symbol = p.get('trdSym', 'N/A')
            base_sym = p.get('sym', symbol)

            lot_sz = _safe_int(p.get('lotSz', 1)) or 1
            multiplier = _safe_int(p.get('multiplier', 1)) or 1
            gen_num = _safe_int(p.get('genNum', 1)) or 1
            gen_den = _safe_int(p.get('genDen', 1)) or 1
            prc_num = _safe_int(p.get('prcNum', 1)) or 1
            prc_den = _safe_int(p.get('prcDen', 1)) or 1
            precision = _safe_int(p.get('precision', 2)) or 2
            price_factor = multiplier * (gen_num / gen_den) * (prc_num / prc_den)

            # Quantities from positions API
            cf_buy_qty = _safe_int(p.get('cfBuyQty', 0))
            fl_buy_qty = _safe_int(p.get('flBuyQty', 0))
            cf_sell_qty = _safe_int(p.get('cfSellQty', 0))
            fl_sell_qty = _safe_int(p.get('flSellQty', 0))
            total_buy_qty = cf_buy_qty + fl_buy_qty
            total_sell_qty = cf_sell_qty + fl_sell_qty
            net_qty = total_buy_qty - total_sell_qty

            net_qty_lots = net_qty // lot_sz if lot_sz > 0 else net_qty

            if net_qty_lots == 0:
                continue

            # Amounts from positions API
            cf_buy_amt = _safe_float(p.get('cfBuyAmt', 0))
            buy_amt = _safe_float(p.get('buyAmt', 0))
            cf_sell_amt = _safe_float(p.get('cfSellAmt', 0))
            sell_amt = _safe_float(p.get('sellAmt', 0))
            total_buy_amt = cf_buy_amt + buy_amt
            total_sell_amt = cf_sell_amt + sell_amt

            # ── 5. Use trade_report for ACTUAL avg price ──
            trade_data = trades_by_symbol.get(symbol, {'buys': [], 'sells': []})

            trade_buy_qty = sum(t['qty'] for t in trade_data['buys'])
            trade_buy_value = sum(t['qty'] * t['price'] for t in trade_data['buys'])
            trade_sell_qty = sum(t['qty'] for t in trade_data['sells'])
            trade_sell_value = sum(t['qty'] * t['price'] for t in trade_data['sells'])
            trade_net_qty = trade_buy_qty - trade_sell_qty

            trade_avg_buy = trade_buy_value / trade_buy_qty if trade_buy_qty > 0 else 0
            trade_avg_sell = trade_sell_value / trade_sell_qty if trade_sell_qty > 0 else 0

            # Direction
            if net_qty > 0:
                direction = 'LONG'
            elif net_qty < 0:
                direction = 'SHORT'
            else:
                direction = 'LONG'

            # Avg price: prefer trade_report data, fallback to positions API
            if trade_buy_qty > 0 and direction == 'LONG':
                avg_price = round(trade_avg_buy, precision)
            elif trade_sell_qty > 0 and direction == 'SHORT':
                avg_price = round(trade_avg_sell, precision)
            else:
                # Fallback: positions API formula
                if direction == 'LONG':
                    avg_price = round(total_buy_amt / (total_buy_qty * price_factor), precision) if total_buy_qty > 0 else 0
                else:
                    avg_price = round(total_sell_amt / (total_sell_qty * price_factor), precision) if total_sell_qty > 0 else 0

            # Use trade_report net qty if available (more reliable for lot count)
            display_net_qty = trade_net_qty if trade_net_qty != 0 else net_qty
            display_lots = abs(display_net_qty) // lot_sz if lot_sz > 0 else abs(display_net_qty)

            # GET LTP (Neo stkPrc is usually 0, use Breeze API)
            ltp = None
            try:
                ltp = get_ltp_from_neo(
                    trading_symbol=symbol,
                    exchange_segment=p.get('exSeg', 'nse_fo'),
                    client=client
                )
            except Exception as e:
                logger.error(f"Error fetching LTP for {symbol}: {e}", exc_info=True)

            # ── 5b. P&L calculation (simple, correct) ──
            # Unrealized P&L = net_qty * (ltp - avg_price)
            # Works for both LONG (positive net_qty) and SHORT (negative net_qty)
            if ltp is not None and ltp > 0:
                unrealized_pnl = display_net_qty * (ltp - avg_price)
            else:
                unrealized_pnl = 0.0

            investment = avg_price * abs(display_net_qty)
            pnl_pct = (unrealized_pnl / investment * 100) if investment > 0 else 0

            logger.info(
                f"Position {symbol}: dir={direction} lots={display_lots} "
                f"avg={avg_price:.2f} ltp={ltp} unrealized={unrealized_pnl:,.2f} pnl%={pnl_pct:.2f}%"
            )

            # Expiry date
            expiry_date = None
            expiry_dt_str = p.get('expDt', '')
            if expiry_dt_str:
                try:
                    expiry_dt = datetime.strptime(expiry_dt_str, '%d %b, %Y')
                    expiry_date = expiry_dt.strftime('%Y-%m-%d')
                except Exception:
                    pass

            positions_data.append({
                'symbol': base_sym if base_sym and base_sym != 'N/A' else symbol,
                'trading_symbol': symbol,
                'exchange': p.get('exSeg', 'N/A'),
                'product': p.get('prod', 'N/A'),
                'direction': direction,
                'quantity': display_lots,
                'net_quantity': display_lots if direction == 'LONG' else -display_lots,
                'net_quantity_shares': display_net_qty,
                'lot_size': lot_sz,
                'average_price': round(avg_price, 2),
                'ltp': round(ltp, 2) if ltp is not None and ltp > 0 else None,
                'unrealized_pnl': round(unrealized_pnl, 2),
                'total_pnl': round(unrealized_pnl, 2),
                'pnl_percentage': round(pnl_pct, 2),
                'expiry_date': expiry_date,
            })

        logger.info(f"Neo: processed {len(positions_data)} active positions from {len(raw_positions)} entries")

        # ── 6. Fetch RMS MTM from limits API for account-level Net P&L ──
        # Broker RMS logic (matches NEO UI):
        #   RMS Net MTM = FoUnRlsMtomPrsnt + FoRlsMtomPrsnt
        #   Trader Net P&L = -(RMS Net MTM)
        rms_net_pnl = None
        rms_unrealized_mtm = None
        rms_realized_mtm = None
        raw_limits_full = None
        try:
            limits_resp = client.limits(segment="ALL", exchange="ALL", product="ALL")
            raw_limits_full = limits_resp
            logger.info(f"Neo limits() response type={type(limits_resp).__name__}, "
                         f"keys={list(limits_resp.keys()) if isinstance(limits_resp, dict) else 'N/A'}")

            if isinstance(limits_resp, dict) and 'Error' not in limits_resp and 'Error Message' not in limits_resp:
                fo_unrealized = _safe_float(limits_resp.get('FoUnRlsMtomPrsnt', 0))
                fo_realized = _safe_float(limits_resp.get('FoRlsMtomPrsnt', 0))
                rms_unrealized_mtm = fo_unrealized
                rms_realized_mtm = fo_realized

                # RMS Net MTM = unrealized + realized
                rms_net_mtm = fo_unrealized + fo_realized
                # Trader Net P&L = sign-reversed RMS MTM, rounded to nearest rupee
                rms_net_pnl = round(-rms_net_mtm)

                logger.info(
                    f"RMS P&L: FoUnRlsMtomPrsnt={fo_unrealized:,.2f}, "
                    f"FoRlsMtomPrsnt={fo_realized:,.2f}, "
                    f"RMS Net MTM={rms_net_mtm:,.2f}, "
                    f"Trader Net P&L={rms_net_pnl:,}"
                )
            else:
                err = limits_resp.get('Error') or limits_resp.get('Error Message') if isinstance(limits_resp, dict) else limits_resp
                logger.warning(f"Neo limits() returned error: {err}")
        except Exception as e:
            logger.error(f"Error fetching Neo limits for RMS P&L: {e}", exc_info=True)

        # Return positions + RMS P&L + FULL raw API responses for debugging
        return {
            'positions': positions_data,
            'rms_net_pnl': rms_net_pnl,
            'rms_unrealized_mtm': rms_unrealized_mtm,
            'rms_realized_mtm': rms_realized_mtm,
            'raw_positions_api': raw_positions_full,
            'raw_trade_report_api': trade_resp_full,
            'raw_limits_api': raw_limits_full,
        }

    except Exception as e:
        logger.error(f"Error fetching Neo positions: {e}", exc_info=True)
        return {'error': f'Failed to fetch Neo positions: {str(e)}'}


@login_required
@require_GET
def get_position_details(request):
    """
    Get detailed information for a specific position

    GET params:
        - broker: 'breeze' or 'neo'
        - position_id: Position ID

    Returns:
        JSON with position details
    """
    try:
        broker = request.GET.get('broker', '').lower()
        position_id = request.GET.get('position_id')

        if not position_id:
            return JsonResponse({
                'success': False,
                'error': 'position_id is required'
            })

        broker_name = 'ICICI' if broker == 'breeze' else 'KOTAK'

        position = Position.objects.filter(
            id=position_id,
            account__broker=broker_name,
            account__is_active=True
        ).select_related('account').first()

        if not position:
            return JsonResponse({
                'success': False,
                'error': 'Position not found'
            })

        position_data = {
            'id': position.id,
            'instrument': position.instrument,
            'direction': position.direction,
            'quantity': position.quantity,
            'lot_size': position.lot_size,
            'entry_price': float(position.entry_price),
            'current_price': float(position.current_price),
            'stop_loss': float(position.stop_loss) if position.stop_loss else None,
            'target': float(position.target) if position.target else None,
            'unrealized_pnl': float(position.unrealized_pnl),
            'realized_pnl': float(position.realized_pnl),
            'margin_used': float(position.margin_used),
            'entry_value': float(position.entry_value),
            'expiry_date': position.expiry_date.strftime('%Y-%m-%d'),
            'entry_time': position.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
            'exit_time': position.exit_time.strftime('%Y-%m-%d %H:%M:%S') if position.exit_time else None,
            'exit_price': float(position.exit_price) if position.exit_price else None,
            'exit_reason': position.exit_reason,
            'status': position.status,
            'strategy_type': position.strategy_type,
            'call_strike': float(position.call_strike) if position.call_strike else None,
            'put_strike': float(position.put_strike) if position.put_strike else None,
            'call_premium': float(position.call_premium) if position.call_premium else None,
            'put_premium': float(position.put_premium) if position.put_premium else None,
        }

        return JsonResponse({
            'success': True,
            'position': position_data
        })

    except Exception as e:
        logger.error(f"Error fetching position details: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def close_position(request):
    """
    Close a position by placing exit orders in batches

    POST params (JSON):
        - broker: 'breeze' or 'neo'
        - position_id: Position ID

    Returns:
        JSON with order execution results
    """
    try:
        from apps.brokers.utils.security_master import get_futures_instrument
        from apps.accounts.models import BrokerAccount

        # Parse JSON body
        data = json.loads(request.body)
        broker = data.get('broker', '').lower()
        position_id = data.get('position_id')

        if not position_id:
            return JsonResponse({
                'success': False,
                'error': 'position_id is required'
            })

        broker_name = 'ICICI' if broker == 'breeze' else 'KOTAK'

        # Get position
        position = Position.objects.filter(
            id=position_id,
            account__broker=broker_name,
            account__is_active=True,
            status=POSITION_STATUS_ACTIVE
        ).select_related('account').first()

        if not position:
            return JsonResponse({
                'success': False,
                'error': 'Position not found or already closed'
            })

        # Get contract details
        contract = ContractData.objects.filter(
            symbol=position.instrument,
            option_type='FUTURE',
            expiry=position.expiry_date
        ).first()

        if not contract:
            return JsonResponse({
                'success': False,
                'error': f'Contract not found for {position.instrument}'
            })

        # Format expiry for Breeze
        expiry_dt = position.expiry_date
        if isinstance(expiry_dt, str):
            expiry_dt = datetime.strptime(expiry_dt, '%Y-%m-%d').date()
        expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()

        # Get instrument details from SecurityMaster
        logger.info(f"Looking up {position.instrument} futures in SecurityMaster for expiry {expiry_breeze}")
        instrument = get_futures_instrument(position.instrument, expiry_breeze)

        # Always use contract.lot_size as the primary source
        lot_size = contract.lot_size

        if not instrument:
            logger.warning(f"Instrument not found in SecurityMaster, using contract data")
            stock_code = position.instrument
        else:
            stock_code = instrument['short_name']
            if instrument.get('lot_size', 0) > 0:
                lot_size = instrument['lot_size']
            logger.info(f"SecurityMaster lookup successful: stock_code={stock_code}, lot_size={lot_size}")

        # Initialize Breeze
        breeze = get_breeze_client()

        # Calculate batches (10 lots per order, 20 second delay)
        BATCH_SIZE = 10
        DELAY_SECONDS = 20

        total_lots = position.quantity
        batches = []
        remaining_lots = total_lots

        while remaining_lots > 0:
            batch_lots = min(BATCH_SIZE, remaining_lots)
            batches.append(batch_lots)
            remaining_lots -= batch_lots

        total_batches = len(batches)
        logger.info(f"Closing position: Splitting {total_lots} lots into {total_batches} batches: {batches}")

        # Track all orders
        successful_orders = []
        failed_orders = []

        # Place exit orders in batches (opposite direction)
        for batch_num, batch_lots in enumerate(batches, 1):
            batch_quantity = batch_lots * lot_size

            logger.info(f"Exit Batch {batch_num}/{total_batches}: Closing {batch_lots} lots ({batch_quantity} quantity)")

            if batch_quantity <= 0:
                error_msg = f"Invalid batch quantity: {batch_quantity}"
                logger.error(error_msg)
                failed_orders.append({
                    'batch': batch_num,
                    'lots': batch_lots,
                    'error': error_msg,
                    'response': None
                })
                continue

            try:
                # Determine action (opposite of position direction)
                action = 'sell' if position.direction == 'LONG' else 'buy'

                order_params = {
                    'stock_code': stock_code,
                    'exchange_code': 'NFO',
                    'product': 'futures',
                    'action': action,
                    'order_type': 'market',
                    'quantity': str(batch_quantity),
                    'price': '0',
                    'validity': 'day',
                    'stoploss': '0',
                    'disclosed_quantity': '0',
                    'expiry_date': expiry_breeze,
                    'right': 'others',
                    'strike_price': '0'
                }

                logger.info(f"Exit Batch {batch_num} order parameters: {order_params}")

                order_response = breeze.place_order(**order_params)
                logger.info(f"Exit Batch {batch_num} Breeze API Response: {order_response}")

                if order_response and order_response.get('Status') == 200:
                    order_data = order_response.get('Success', {})
                    order_id = order_data.get('order_id', 'UNKNOWN')

                    # Create Order record
                    order = Order.objects.create(
                        account=position.account,
                        position=position,
                        broker_order_id=order_id,
                        instrument=position.instrument,
                        order_type='MARKET',
                        direction='SELL' if position.direction == 'LONG' else 'BUY',
                        quantity=batch_quantity,
                        price=position.current_price,
                        exchange='NFO',
                        status='PENDING'
                    )

                    successful_orders.append({
                        'batch': batch_num,
                        'order_id': order_id,
                        'lots': batch_lots,
                        'quantity': batch_quantity,
                        'order_record_id': order.id
                    })

                    logger.info(f"Exit Batch {batch_num} SUCCESS: Order ID {order_id}")

                else:
                    error_msg = order_response.get('Error', 'Unknown error') if order_response else 'API call failed'
                    logger.error(f"Exit Batch {batch_num} FAILED: {error_msg}")

                    failed_orders.append({
                        'batch': batch_num,
                        'lots': batch_lots,
                        'error': error_msg,
                        'response': order_response
                    })

            except Exception as e:
                logger.error(f"Exit Batch {batch_num} EXCEPTION: {e}", exc_info=True)
                failed_orders.append({
                    'batch': batch_num,
                    'lots': batch_lots,
                    'error': str(e),
                    'response': None
                })

            # Wait before next batch (except for last batch)
            if batch_num < total_batches:
                logger.info(f"Waiting {DELAY_SECONDS} seconds before next batch...")
                time.sleep(DELAY_SECONDS)

        # Update position status if all orders succeeded
        if len(successful_orders) == total_batches:
            position.close_position(
                exit_price=position.current_price,
                exit_reason='MANUAL'
            )
            logger.info(f"Position {position.id} marked as CLOSED")

        if len(successful_orders) > 0:
            return JsonResponse({
                'success': True,
                'total_batches': total_batches,
                'successful_batches': len(successful_orders),
                'failed_batches': len(failed_orders),
                'position_id': position.id,
                'message': f'{len(successful_orders)}/{total_batches} exit batches placed successfully',
                'orders': successful_orders,
                'failed_orders': failed_orders if failed_orders else None,
                'position_closed': len(successful_orders) == total_batches
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'All {total_batches} exit batches failed',
                'failed_orders': failed_orders,
                'debug_info': {
                    'total_batches': total_batches,
                    'symbol': position.instrument,
                    'lots': total_lots
                }
            })

    except Exception as e:
        logger.error(f"Error closing position: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@csrf_exempt
def close_live_position(request):
    """
    Close a live position from broker API by placing exit orders in batches.

    This is different from close_position() which works with database Position objects.
    This function works with live positions fetched directly from broker APIs.

    POST params (JSON):
        - broker: 'breeze' or 'neo'
        - symbol: Trading symbol (e.g., 'JIOFIN25DECFUT', 'NIFTY25NOV24500CE')
        - quantity: Net quantity to close (positive for LONG, negative for SHORT)
        - exchange: Exchange code (e.g., 'NFO', 'nse_fo')
        - product: Product type (e.g., 'futures', 'NRML', 'MIS')
        - direction: Position direction ('LONG' or 'SHORT')

    Returns:
        JSON with order execution results
    """
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)

    # Check if POST method
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'POST method required'
        }, status=405)

    try:
        # Parse JSON body
        data = json.loads(request.body)
        broker = data.get('broker', '').lower()
        symbol = data.get('symbol')
        quantity = data.get('quantity')
        exchange = data.get('exchange', 'NFO')
        product = data.get('product', 'NRML')
        direction = data.get('direction', 'LONG').upper()

        logger.info(f"=" * 100)
        logger.info(f"CLOSING LIVE POSITION: {broker.upper()} - {symbol}")
        logger.info(f"Direction: {direction}, Quantity: {quantity}, Product: {product}")
        logger.info(f"=" * 100)

        if broker not in ['breeze', 'neo']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid broker. Must be "breeze" or "neo"'
            })

        if not symbol or quantity is None:
            return JsonResponse({
                'success': False,
                'error': 'symbol and quantity are required'
            })

        abs_quantity = abs(int(quantity))

        if abs_quantity == 0:
            return JsonResponse({
                'success': False,
                'error': 'Position has zero quantity'
            })

        # Generate cancellation key
        cancellation_key = f"cancel_order_{request.user.id}_{broker}_{symbol.replace('/', '_')}"
        cache.set(cancellation_key, False, 600)

        # Generate progress tracking key
        progress_key = f"close_progress_{request.user.id}_{broker}_{symbol.replace('/', '_')}"

        def update_progress(batches_completed, total_batches, current_batch=None, log_message=None, log_type='info', is_complete=False, is_success=False, is_cancelled=False):
            progress = {
                'batches_completed': batches_completed,
                'total_batches': total_batches,
                'current_batch': current_batch,
                'is_cancelled': is_cancelled,
                'is_complete': is_complete,
                'is_success': is_success,
                'last_log_message': log_message,
                'last_log_type': log_type
            }
            cache.set(progress_key, progress, 600)
            return progress

        if broker == 'neo':
            return _close_neo_position(symbol, abs_quantity, direction, product, cancellation_key, progress_key, update_progress)
        elif broker == 'breeze':
            return _close_breeze_position(request, symbol, abs_quantity, direction, product, cancellation_key, progress_key, update_progress)

        return JsonResponse({
            'success': False,
            'error': 'Unknown error - broker not supported or invalid parameters'
        })

    except Exception as e:
        logger.error(f"Error closing live position: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


def _close_neo_position(symbol, abs_quantity, direction, product, cancellation_key, progress_key, update_progress):
    """Close position on Neo broker"""
    from apps.brokers.integrations.kotak_neo import close_position_in_batches

    transaction_type = 'S' if direction == 'LONG' else 'B'
    logger.info(f"Closing Neo position: {symbol} with transaction type {transaction_type}")

    update_progress(0, 0, log_message='Starting position closure on Kotak Neo...', log_type='info')

    result = close_position_in_batches(
        trading_symbol=symbol,
        total_quantity=abs_quantity,
        transaction_type=transaction_type,
        product=product if product in ['NRML', 'MIS', 'CNC'] else 'NRML',
        batch_size=10,
        delay_seconds=10,
        position_type='OPTION',
        cancellation_key=cancellation_key,
        progress_key=progress_key
    )

    if result['success']:
        logger.info(f"Neo position closed successfully: {result['summary']}")
        return JsonResponse({
            'success': True,
            'cancelled': result.get('cancelled', False),
            'broker': 'neo',
            'symbol': symbol,
            'message': result.get('message', f"Position closed: {result['summary']['success_count']}/{result['total_batches']} batches succeeded"),
            'batches_completed': result['batches_completed'],
            'total_batches': result['total_batches'],
            'successful_batches': result['summary']['success_count'],
            'summary': result['summary']
        })
    else:
        logger.error(f"Neo position close failed: {result.get('error')}")
        return JsonResponse({
            'success': False,
            'error': result.get('error', 'Failed to close position'),
            'batches_completed': result.get('batches_completed', 0),
            'orders': result.get('orders', [])
        })


def _close_breeze_position(request, symbol, abs_quantity, direction, product, cancellation_key, progress_key, update_progress):
    """Close position on Breeze broker"""
    action = 'sell' if direction == 'LONG' else 'buy'
    logger.info(f"Closing Breeze position: {symbol} with action {action}")

    breeze = get_breeze_client()

    # Get the actual position from Breeze
    try:
        pos_resp = breeze.get_portfolio_positions()
        if not pos_resp or pos_resp.get('Status') != 200:
            return JsonResponse({
                'success': False,
                'error': f'Failed to fetch positions from Breeze: {pos_resp.get("Error", "Unknown error")}'
            })

        positions = pos_resp.get('Success', [])
        matching_pos = None

        for pos in positions:
            pos_qty = int(pos.get('quantity', 0))
            if abs(pos_qty) == abs_quantity:
                if product.lower() in pos.get('product_type', '').lower():
                    matching_pos = pos
                    break

        if not matching_pos:
            match = re.match(r'^([A-Z]+)', symbol.upper())
            base_symbol = match.group(1) if match else symbol

            for pos in positions:
                if pos.get('stock_code') == base_symbol:
                    matching_pos = pos
                    break

        if not matching_pos:
            return JsonResponse({
                'success': False,
                'error': f'Could not find position for {symbol} in Breeze positions'
            })

        stock_code = matching_pos.get('stock_code')
        exchange_code = matching_pos.get('exchange_code', 'NFO')
        product_type = matching_pos.get('product_type', 'Futures')
        expiry_date = matching_pos.get('expiry_date', '')
        right = matching_pos.get('right', 'others')
        strike_price = matching_pos.get('strike_price', '0')

    except Exception as e:
        logger.error(f"Error fetching Breeze positions: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Failed to get position details: {str(e)}'
        })

    # Calculate batches
    STANDARD_LOT_SIZES = {
        'NIFTY': 25,
        'BANKNIFTY': 15,
        'FINNIFTY': 25,
        'MIDCPNIFTY': 50,
        'JIOFIN': 2350,
        'RELIANCE': 250,
        'TCS': 150,
        'INFY': 300,
    }
    lot_size = STANDARD_LOT_SIZES.get(stock_code, 1)

    BATCH_SIZE_LOTS = 10
    DELAY_SECONDS = 40

    batch_size_shares = BATCH_SIZE_LOTS * lot_size
    total_lots = abs_quantity // lot_size if lot_size > 0 else 0

    if total_lots == 0:
        return JsonResponse({
            'success': False,
            'error': f'Quantity {abs_quantity} is less than one lot (lot size: {lot_size})'
        })

    batches = []
    remaining_shares = abs_quantity

    while remaining_shares > 0:
        batch_shares = min(batch_size_shares, remaining_shares)
        batches.append(batch_shares)
        remaining_shares -= batch_shares

    total_batches = len(batches)
    update_progress(0, total_batches, log_message=f'Starting position closure on ICICI Breeze: {total_batches} batches', log_type='info')

    successful_orders = []
    failed_orders = []

    for batch_num, batch_shares in enumerate(batches, 1):
        # Check for cancellation
        if cache.get(cancellation_key):
            update_progress(
                len(successful_orders), total_batches,
                is_complete=True, is_success=False, is_cancelled=True,
                log_message=f'Cancelled at batch {batch_num}/{total_batches}.',
                log_type='warning'
            )
            return JsonResponse({
                'success': True,
                'cancelled': True,
                'broker': 'breeze',
                'symbol': symbol,
                'message': f'Order placement stopped by user. Completed {len(successful_orders)}/{total_batches} batches.',
                'successful_batches': len(successful_orders),
                'failed_batches': len(failed_orders),
                'total_batches': total_batches,
                'orders': successful_orders,
                'failed_orders': failed_orders if failed_orders else None
            })

        batch_lots = batch_shares // lot_size

        update_progress(
            len(successful_orders), total_batches,
            current_batch={'batch_num': batch_num, 'lots': batch_lots, 'quantity': batch_shares},
            log_message=f'Processing batch {batch_num}/{total_batches}: {batch_lots} lots',
            log_type='info'
        )

        try:
            order_params = {
                'stock_code': stock_code,
                'exchange_code': exchange_code,
                'product': product_type.lower(),
                'action': action,
                'order_type': 'market',
                'quantity': str(batch_shares),
                'price': '0',
                'validity': 'day',
                'stoploss': '0',
                'disclosed_quantity': '0',
                'expiry_date': expiry_date,
                'right': right,
                'strike_price': str(strike_price)
            }

            order_response = breeze.place_order(**order_params)

            if order_response and order_response.get('Status') == 200:
                order_data = order_response.get('Success', {})
                order_id = order_data.get('order_id', 'UNKNOWN')

                successful_orders.append({
                    'batch': batch_num,
                    'order_id': order_id,
                    'lots': batch_lots,
                    'quantity': batch_shares
                })

                update_progress(
                    len(successful_orders), total_batches,
                    log_message=f'Batch {batch_num}/{total_batches} completed successfully',
                    log_type='success'
                )
            else:
                error_msg = order_response.get('Error', 'Unknown error') if order_response else 'API call failed'

                failed_orders.append({
                    'batch': batch_num,
                    'lots': batch_lots,
                    'error': error_msg
                })

                update_progress(
                    len(successful_orders), total_batches,
                    is_complete=True, is_success=False,
                    log_message=f'Batch {batch_num}/{total_batches} failed. Stopping execution.',
                    log_type='error'
                )

                return JsonResponse({
                    'success': False,
                    'broker': 'breeze',
                    'symbol': symbol,
                    'error': f'Batch {batch_num} failed: {error_msg}',
                    'successful_batches': len(successful_orders),
                    'failed_batches': len(failed_orders),
                    'total_batches': total_batches,
                    'orders': successful_orders,
                    'failed_orders': failed_orders
                })

        except Exception as e:
            failed_orders.append({
                'batch': batch_num,
                'lots': batch_lots,
                'error': str(e)
            })

            update_progress(
                len(successful_orders), total_batches,
                is_complete=True, is_success=False,
                log_message=f'Batch {batch_num}/{total_batches} error: {str(e)[:50]}. Stopping execution.',
                log_type='error'
            )

            return JsonResponse({
                'success': False,
                'broker': 'breeze',
                'symbol': symbol,
                'error': f'Batch {batch_num} exception: {str(e)}',
                'successful_batches': len(successful_orders),
                'failed_batches': len(failed_orders),
                'total_batches': total_batches,
                'orders': successful_orders,
                'failed_orders': failed_orders
            })

        # Wait before next batch
        if batch_num < total_batches:
            time.sleep(DELAY_SECONDS)

            if cache.get(cancellation_key):
                update_progress(
                    len(successful_orders), total_batches,
                    is_complete=True, is_success=False, is_cancelled=True,
                    log_message=f'Cancelled during wait after batch {batch_num}/{total_batches}.',
                    log_type='warning'
                )
                return JsonResponse({
                    'success': True,
                    'cancelled': True,
                    'broker': 'breeze',
                    'symbol': symbol,
                    'message': f'Order placement stopped by user. Completed {len(successful_orders)}/{total_batches} batches.',
                    'successful_batches': len(successful_orders),
                    'failed_batches': len(failed_orders),
                    'total_batches': total_batches,
                    'orders': successful_orders,
                    'failed_orders': failed_orders if failed_orders else None
                })

    # Final progress update
    if len(successful_orders) > 0:
        update_progress(
            len(successful_orders), total_batches,
            is_complete=True,
            is_success=len(failed_orders) == 0,
            log_message=f'Completed: {len(successful_orders)}/{total_batches} batches successful',
            log_type='success' if len(failed_orders) == 0 else 'warning'
        )

        return JsonResponse({
            'success': True,
            'broker': 'breeze',
            'symbol': symbol,
            'message': f'{len(successful_orders)}/{total_batches} exit batches placed successfully',
            'successful_batches': len(successful_orders),
            'failed_batches': len(failed_orders),
            'total_batches': total_batches,
            'orders': successful_orders,
            'failed_orders': failed_orders if failed_orders else None
        })
    else:
        update_progress(
            0, total_batches,
            is_complete=True, is_success=False,
            log_message=f'All {total_batches} batches failed',
            log_type='error'
        )
        return JsonResponse({
            'success': False,
            'error': f'All {total_batches} exit batches failed',
            'failed_orders': failed_orders
        })


@csrf_exempt
def get_close_position_progress(request, broker, symbol):
    """
    Get progress of an ongoing close position operation.

    URL params:
        - broker: 'breeze' or 'neo'
        - symbol: Trading symbol

    Returns:
        JSON with progress information
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)

    try:
        progress_key = f"close_progress_{request.user.id}_{broker}_{symbol.replace('/', '_')}"

        progress = cache.get(progress_key, {
            'batches_completed': 0,
            'total_batches': 0,
            'current_batch': None,
            'is_cancelled': False,
            'is_complete': False,
            'is_success': False,
            'last_log_message': None,
            'last_log_type': None
        })

        return JsonResponse({
            'success': True,
            'progress': progress
        })

    except Exception as e:
        logger.error(f"Error getting close position progress: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@csrf_exempt
def cancel_order_placement(request):
    """
    Cancel an ongoing batch order placement.

    POST params (JSON):
        - broker: 'breeze' or 'neo'
        - symbol: Trading symbol

    Returns:
        JSON with cancellation status
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'POST method required'
        }, status=405)

    try:
        data = json.loads(request.body)
        broker = data.get('broker', '').lower()
        symbol = data.get('symbol')

        if not broker or not symbol:
            return JsonResponse({
                'success': False,
                'error': 'broker and symbol are required'
            })

        cancellation_key = f"cancel_order_{request.user.id}_{broker}_{symbol.replace('/', '_')}"
        cache.set(cancellation_key, True, 600)
        logger.info(f"Cancellation requested for key: {cancellation_key}")

        return JsonResponse({
            'success': True,
            'message': 'Cancellation requested. Remaining batches will be skipped.'
        })

    except Exception as e:
        logger.error(f"Error cancelling order placement: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@require_http_methods(["POST"])
def analyze_position_averaging(request):
    """
    Analyze an existing futures position for averaging opportunities.

    CRITICAL CONDITIONS (must pass):
    1. Price movement: Down 1.5%+ from entry (LONG) or Up 1.5%+ (SHORT)
    2. Support/Resistance: Near support (LONG) or resistance (SHORT)

    ADDITIONAL CHECKS:
    3. Trend analysis (not in strong opposite trend)
    4. Volume & liquidity
    5. Sector health
    6. Volatility assessment

    POST params (JSON):
        - broker: 'breeze' or 'neo'
        - symbol: Trading symbol (e.g., 'RELIANCE-I')
        - direction: Position direction ('LONG' or 'SHORT')
        - entry_price: Original entry price
        - quantity: Current position quantity
        - expiry_date: Futures expiry (YYYY-MM-DD format)

    Returns:
        JSON with averaging recommendation and analysis
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)

    try:
        from apps.trading.averaging_analyzer import AveragingAnalyzer
        from apps.brokers.integrations.kotak_neo import get_kotak_neo_client

        data = json.loads(request.body)
        broker = data.get('broker', '').lower()
        symbol = data.get('symbol', '')
        direction = data.get('direction', 'LONG').upper()
        entry_price = float(data.get('entry_price', 0))
        quantity = int(data.get('quantity', 0))
        expiry_date = data.get('expiry_date', '')

        if not all([broker, symbol, entry_price, quantity]):
            return JsonResponse({
                'success': False,
                'error': 'broker, symbol, entry_price, and quantity are required'
            })

        logger.info(f"Analyzing averaging for {symbol} {direction} @ {entry_price} ({quantity} qty)")

        # Extract base symbol
        if '-' in symbol:
            base_symbol = symbol.split('-')[0]
        else:
            match = re.match(r'^([A-Z]+)', symbol.upper())
            base_symbol = match.group(1) if match else symbol

        logger.info(f"Extracted base symbol: '{base_symbol}' from '{symbol}'")

        # Get lot size from ContractData
        lot_size = 0
        if expiry_date:
            contract = ContractData.objects.filter(
                symbol=base_symbol,
                option_type='FUTURE',
                expiry=expiry_date
            ).first()

            if contract:
                lot_size = contract.lot_size

        # Fallback lot sizes
        if not lot_size:
            fallback_lot_sizes = {
                'RELIANCE': 250, 'TCS': 150, 'INFY': 300, 'HDFCBANK': 550,
                'ICICIBANK': 1375, 'SBIN': 1500, 'NIFTY': 50, 'BANKNIFTY': 15,
            }
            lot_size = fallback_lot_sizes.get(base_symbol, 500)

        # Initialize analyzer with Breeze client
        breeze = get_breeze_client()
        analyzer = AveragingAnalyzer(breeze_client=breeze)

        # Run averaging analysis
        analysis_result = analyzer.analyze_position_for_averaging(
            symbol=base_symbol,
            direction=direction,
            entry_price=entry_price,
            current_quantity=quantity,
            lot_size=lot_size,
            expiry_date=expiry_date,
            exchange='NFO'
        )

        if not analysis_result.get('success'):
            return JsonResponse({
                'success': False,
                'error': analysis_result.get('error', 'Analysis failed'),
                'execution_log': analysis_result.get('execution_log', [])
            })

        # Add margin information
        position_sizing = analysis_result.get('position_sizing', {})
        recommended_lots = position_sizing.get('recommended_lots', 0)

        if recommended_lots > 0 and broker == 'breeze':
            from apps.trading.position_sizer import PositionSizer

            sizer = PositionSizer(breeze_client=breeze)

            if expiry_date:
                expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
                expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()
            else:
                expiry_breeze = None

            margin_response = sizer.fetch_margin_requirement(
                stock_code=base_symbol,
                expiry=expiry_breeze,
                quantity=lot_size * recommended_lots,
                direction=direction,
                futures_price=analysis_result.get('current_price', 0)
            )

            if margin_response.get('success'):
                try:
                    margin_data = breeze.get_margin(exchange_code="NFO")
                    if margin_data and margin_data.get('Status') == 200:
                        margin_info = margin_data.get('Success', {})
                        available_margin = float(margin_info.get('cash_limit', 0)) - float(margin_info.get('block_by_trade', 0))
                    else:
                        available_margin = 5000000
                except:
                    available_margin = 5000000

                position_sizing['margin_per_lot'] = margin_response.get('margin_per_lot', 0)
                position_sizing['total_margin_required'] = margin_response.get('total_margin', 0)
                position_sizing['available_margin'] = available_margin
                position_sizing['margin_utilization_pct'] = (
                    margin_response.get('total_margin', 0) / available_margin * 100
                ) if available_margin > 0 else 0

        response_data = {
            'success': True,
            'symbol': base_symbol,
            'direction': direction,
            'entry_price': entry_price,
            'current_price': analysis_result.get('current_price', 0),
            'price_change_pct': analysis_result.get('price_change_pct', 0),
            'recommendation': analysis_result.get('recommendation', 'NO_AVERAGE'),
            'confidence': analysis_result.get('confidence', 0),
            'reason': analysis_result.get('reason', ''),
            'critical_checks': analysis_result.get('critical_checks', {}),
            'additional_checks': analysis_result.get('additional_checks', {}),
            'risk_assessment': analysis_result.get('risk_assessment', {}),
            'position_sizing': position_sizing,
            'execution_log': analysis_result.get('execution_log', []),
            'lot_size': lot_size,
            'expiry_date': expiry_date
        }

        logger.info(f"Averaging analysis complete: {response_data['recommendation']} (Confidence: {response_data['confidence']}%)")

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in averaging analysis: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
