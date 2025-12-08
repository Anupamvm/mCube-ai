"""
Contract and Option Data API Views

Endpoints for fetching contract details, option premiums,
and lot size information.
"""

import logging
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.http import JsonResponse

logger = logging.getLogger(__name__)


@login_required
def get_option_premiums(request):
    """
    Get option premiums (LTP) for given strikes from OptionChain database

    GET params:
        - call_strike: Call strike price
        - put_strike: Put strike price
        - expiry: Expiry date (YYYY-MM-DD)

    Returns:
        JsonResponse with call_premium and put_premium from OptionChain (fetched via Breeze)
    """
    try:
        from apps.data.models import OptionChain

        call_strike = request.GET.get('call_strike')
        put_strike = request.GET.get('put_strike')
        expiry_str = request.GET.get('expiry')

        if not call_strike or not put_strike or not expiry_str:
            return JsonResponse({
                'success': False,
                'error': 'call_strike, put_strike, and expiry are required'
            })

        # Parse parameters
        call_strike_val = Decimal(call_strike)
        put_strike_val = Decimal(put_strike)
        expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()

        logger.info(f"[PREMIUM FETCH] Looking for: Call {call_strike_val} CE, Put {put_strike_val} PE, Expiry {expiry_date}")

        # Fetch call option data from OptionChain (populated via Breeze API)
        call_option = OptionChain.objects.filter(
            underlying='NIFTY',
            option_type='CE',
            strike=call_strike_val,
            expiry_date=expiry_date
        ).order_by('-snapshot_time').first()  # Get latest snapshot

        # Fetch put option data
        put_option = OptionChain.objects.filter(
            underlying='NIFTY',
            option_type='PE',
            strike=put_strike_val,
            expiry_date=expiry_date
        ).order_by('-snapshot_time').first()

        if not call_option or not put_option:
            logger.warning(f"[PREMIUM FETCH] Option data not found!")
            logger.warning(f"[PREMIUM FETCH] Call option found: {call_option is not None}")
            logger.warning(f"[PREMIUM FETCH] Put option found: {put_option is not None}")

            return JsonResponse({
                'success': False,
                'error': f'Option data not found in database for strikes {call_strike_val}/{put_strike_val} expiry {expiry_date}'
            })

        # Get LTP (Last Traded Price) from OptionChain
        call_premium = float(call_option.ltp) if call_option.ltp else 0.0
        put_premium = float(put_option.ltp) if put_option.ltp else 0.0

        logger.info(f"[PREMIUM FETCH] Call {call_strike_val} CE: {call_premium}, Put {put_strike_val} PE: {put_premium}")
        logger.info(f"[PREMIUM FETCH] Data from: {call_option.snapshot_time}")

        return JsonResponse({
            'success': True,
            'call_premium': call_premium,
            'put_premium': put_premium,
            'total_premium': call_premium + put_premium,
            'call_strike': float(call_strike_val),
            'put_strike': float(put_strike_val),
            'data_source': 'OptionChain (Breeze API)',
            'snapshot_time': call_option.snapshot_time.isoformat() if call_option.snapshot_time else None,
            'spot_price': float(call_option.spot_price) if call_option.spot_price else None
        })

    except Exception as e:
        logger.error(f"Error fetching option premiums: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_GET
def get_contract_details(request):
    """
    Get complete contract details including instrument token from SecurityMaster.

    GET params:
        - symbol: Stock symbol (e.g., 'TCS')
        - expiry: Expiry date in YYYY-MM-DD format (e.g., '2024-12-26')

    Returns:
        JSON with contract details and instrument token
    """
    try:
        symbol = request.GET.get('symbol', '').upper()
        expiry_str = request.GET.get('expiry', '')

        if not symbol or not expiry_str:
            return JsonResponse({
                'success': False,
                'error': 'Symbol and expiry are required'
            })

        # Get contract from database
        from apps.data.models import ContractData
        contract = ContractData.objects.filter(
            symbol=symbol,
            option_type='FUTURE',
            expiry=expiry_str
        ).first()

        if not contract:
            return JsonResponse({
                'success': False,
                'error': f'Contract not found for {symbol} with expiry {expiry_str}'
            })

        # Format expiry for SecurityMaster lookup
        expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d').date()
        expiry_breeze = expiry_dt.strftime('%d-%b-%Y').upper()

        # Get instrument details from SecurityMaster
        from apps.brokers.utils.security_master import get_futures_instrument
        instrument = get_futures_instrument(symbol, expiry_breeze)

        response_data = {
            'success': True,
            'symbol': symbol,
            'expiry': expiry_str,
            'expiry_formatted': expiry_breeze,
            'lot_size': contract.lot_size,
            'price': float(contract.price),
            'volume': contract.traded_contracts
        }

        if instrument:
            response_data['instrument'] = {
                'token': instrument.get('token', 'N/A'),
                'stock_code': instrument.get('short_name', symbol),
                'company_name': instrument.get('company_name', ''),
                'lot_size': instrument.get('lot_size', contract.lot_size),
                'source': 'SecurityMaster'
            }
        else:
            response_data['instrument'] = {
                'token': 'Not found in SecurityMaster',
                'stock_code': symbol,
                'company_name': '',
                'lot_size': contract.lot_size,
                'source': 'ContractData fallback'
            }

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error fetching contract details: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_GET
def get_lot_size(request):
    """
    Get lot size and instrument token for a trading symbol using Neo API.

    GET params:
        - trading_symbol: Trading symbol (e.g., 'NIFTY25NOV27050CE')

    Returns:
        JSON: {
            'success': True,
            'lot_size': 75,
            'symbol': 'NIFTY25NOV27050CE',
            'instrument_token': '12345',
            'expiry': '28-NOV-2024'
        }
    """
    try:
        trading_symbol = request.GET.get('trading_symbol', '')

        if not trading_symbol:
            return JsonResponse({
                'success': False,
                'error': 'Trading symbol is required'
            })

        from apps.brokers.integrations.kotak_neo import get_lot_size_from_neo_with_token

        # Get lot size and instrument details
        result = get_lot_size_from_neo_with_token(trading_symbol)

        return JsonResponse({
            'success': True,
            'lot_size': result.get('lot_size', 75),
            'symbol': trading_symbol,
            'instrument_token': result.get('token', 'N/A'),
            'expiry': result.get('expiry', 'N/A'),
            'source': 'Neo API'
        })

    except Exception as e:
        logger.error(f"Error fetching lot size: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
