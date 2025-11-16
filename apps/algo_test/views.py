"""
Algorithm Testing Views

Views for algorithm testing and analysis
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from decimal import Decimal
from datetime import datetime
import json
import logging

from apps.algo_test.services import OptionsAlgorithmCalculator, FuturesAlgorithmCalculator
from apps.algo_test.models import OptionsTestLog, FuturesTestLog

logger = logging.getLogger(__name__)


@login_required
def options_test_page(request):
    """
    Options Algorithm Testing Page
    Tests Kotak Strangle strategy entry logic
    """
    context = {
        'page_title': 'Options Algorithm Tester',
        'strategy': 'Kotak Strangle',
        'page_description': 'Trace how the options algorithm selects strike prices and evaluates entry filters'
    }

    # Get live data or use defaults
    try:
        from apps.brokers.services.data_fetcher import DataFetcher
        fetcher = DataFetcher()

        nifty_spot = Decimal(str(fetcher.get_spot_price('NIFTY')))
        india_vix = Decimal(str(fetcher.get_vix()))
    except:
        # Fallback defaults
        nifty_spot = Decimal('24000')
        india_vix = Decimal('14.5')

    context['default_values'] = {
        'nifty_spot': float(nifty_spot),
        'india_vix': float(india_vix),
        'days_to_expiry': 4,
        'available_margin': 200000,
        'active_positions': 0,
    }

    return render(request, 'algo_test/options.html', context)


@login_required
def options_test_analyze(request):
    """
    AJAX endpoint for options algorithm analysis
    Accepts input parameters and returns detailed analysis
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    try:
        data = json.loads(request.body)

        # Parse inputs
        nifty_spot = Decimal(str(data.get('nifty_spot', 24000)))
        vix = Decimal(str(data.get('india_vix', 14.5)))
        days_to_expiry = int(data.get('days_to_expiry', 4))
        available_margin = Decimal(str(data.get('available_margin', 200000)))
        active_positions = int(data.get('active_positions', 0))

        # Market data
        sgx_nifty_change = Decimal(str(data.get('sgx_nifty_change', -0.3)))
        nasdaq_change = Decimal(str(data.get('nasdaq_change', 0.8)))
        dow_change = Decimal(str(data.get('dow_change', -0.6)))
        nifty_1d_change = Decimal(str(data.get('nifty_1d_change', 0.4)))
        nifty_3d_change = Decimal(str(data.get('nifty_3d_change', 1.5)))

        # Optional: Call and put premiums (calculated if not provided)
        call_premium = data.get('call_premium')
        put_premium = data.get('put_premium')

        if call_premium:
            call_premium = Decimal(str(call_premium))
        if put_premium:
            put_premium = Decimal(str(put_premium))

        # Run analysis
        analysis_result = OptionsAlgorithmCalculator.run_full_analysis(
            nifty_spot=nifty_spot,
            vix=vix,
            days_to_expiry=days_to_expiry,
            available_margin=available_margin,
            active_positions=active_positions,
            current_time=datetime.now(),
            sgx_nifty_change=sgx_nifty_change,
            nasdaq_change=nasdaq_change,
            dow_change=dow_change,
            nifty_1d_change=nifty_1d_change,
            nifty_3d_change=nifty_3d_change,
            call_premium=call_premium,
            put_premium=put_premium,
            price_vs_bb=data.get('price_vs_bb', 'middle')
        )

        # Save test log
        if analysis_result['final_decision']['status'] != 'ERROR':
            OptionsTestLog.objects.create(
                user=request.user,
                nifty_spot=nifty_spot,
                india_vix=vix,
                days_to_expiry=days_to_expiry,
                available_margin=available_margin,
                active_positions=active_positions,
                adjusted_delta=Decimal(str(analysis_result['calculations'].get('vix_adjusted_delta', 0.5))),
                call_strike=analysis_result['calculations'].get('call_strike', 0),
                put_strike=analysis_result['calculations'].get('put_strike', 0),
                premium_collected=Decimal(str(analysis_result['calculations'].get('premium_collected', 0))),
                filter_results=analysis_result['filters'],
                status='pass' if analysis_result['final_decision']['status'] == 'ENTRY_APPROVED' else 'fail',
                decision=analysis_result['final_decision']['decision'],
            )

        return JsonResponse(analysis_result)

    except Exception as e:
        logger.error(f"Error in options analysis: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def futures_test_page(request):
    """
    Futures Algorithm Testing Page
    Tests ICICI Futures screening and scoring
    """
    context = {
        'page_title': 'Futures Algorithm Tester',
        'strategy': 'ICICI Futures',
        'page_description': 'Trace multi-factor scoring for futures position selection',
        'default_direction': 'LONG'
    }

    context['default_values'] = {
        'symbol': 'RELIANCE',
        'current_price': 2450,
        'previous_price': 2420,
        'current_oi': 1250000,
        'previous_oi': 1180000,
        'pcr_ratio': 1.31,
        'sector_3d_change': 2.1,
        'sector_7d_change': 4.8,
        'sector_21d_change': 8.3,
        'trendlyne_score': 12,
        'dma_score': 7,
        'volume_score': 9,
        'available_margin': 500000,
    }

    return render(request, 'algo_test/futures.html', context)


@login_required
def futures_test_analyze(request):
    """
    AJAX endpoint for futures algorithm analysis
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    try:
        data = json.loads(request.body)

        # Parse inputs
        symbol = data.get('symbol', 'RELIANCE')
        direction = data.get('direction', 'LONG')
        current_price = Decimal(str(data.get('current_price', 2450)))
        previous_price = Decimal(str(data.get('previous_price', 2420)))
        current_oi = int(data.get('current_oi', 1250000))
        previous_oi = int(data.get('previous_oi', 1180000))
        pcr_ratio = Decimal(str(data.get('pcr_ratio', 1.31)))

        sector_3d = Decimal(str(data.get('sector_3d_change', 2.1)))
        sector_7d = Decimal(str(data.get('sector_7d_change', 4.8)))
        sector_21d = Decimal(str(data.get('sector_21d_change', 8.3)))

        trendlyne = Decimal(str(data.get('trendlyne_score', 12)))
        dma = Decimal(str(data.get('dma_score', 7)))
        volume = Decimal(str(data.get('volume_score', 9)))

        llm_confidence = data.get('llm_confidence')
        if llm_confidence:
            llm_confidence = Decimal(str(llm_confidence))

        available_margin = data.get('available_margin')
        if available_margin:
            available_margin = Decimal(str(available_margin))

        # Run analysis
        analysis_result = FuturesAlgorithmCalculator.run_full_analysis(
            symbol=symbol,
            direction=direction,
            current_price=current_price,
            previous_price=previous_price,
            current_oi=current_oi,
            previous_oi=previous_oi,
            pcr_ratio=pcr_ratio,
            sector_3d_change=sector_3d,
            sector_7d_change=sector_7d,
            sector_21d_change=sector_21d,
            trendlyne_score=trendlyne,
            dma_score=dma,
            volume_score=volume,
            llm_confidence=llm_confidence or Decimal('85'),
            available_margin=available_margin
        )

        # Save test log
        FuturesTestLog.objects.create(
            user=request.user,
            symbol=symbol,
            current_price=current_price,
            oi_score=Decimal(str(analysis_result['scoring']['oi_analysis'].get('score', 0))),
            sector_score=Decimal(str(analysis_result['scoring']['sector_analysis'].get('score', 0))),
            technical_score=Decimal(str(analysis_result['scoring']['technical_analysis'].get('score', 0))),
            composite_score=Decimal(str(analysis_result['scoring']['composite'].get('total', 0))),
            factor_details=analysis_result['scoring'],
            llm_confidence=llm_confidence or Decimal('0'),
            llm_recommendation=analysis_result['llm_validation'].get('approved', False) and 'APPROVED' or 'REJECTED',
            status=analysis_result['final_decision']['status'].lower().replace('_', ''),
            decision=analysis_result['final_decision']['decision'],
            margin_required=Decimal(str(analysis_result['final_decision'].get('position_details', {}).get('margin_available', 0)))
        )

        return JsonResponse(analysis_result)

    except Exception as e:
        logger.error(f"Error in futures analysis: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def position_monitor_page(request):
    """
    Position Monitoring Dashboard
    Real-time P&L and exit decision tracking
    """
    from apps.positions.models import Position

    # Get active positions
    active_positions = Position.objects.filter(
        user=request.user,
        status='ACTIVE'
    ).select_related('account')

    context = {
        'page_title': 'Position Monitor',
        'active_positions': active_positions,
    }

    return render(request, 'algo_test/monitor.html', context)


@login_required
def risk_dashboard_page(request):
    """
    Risk Management Dashboard
    Daily/weekly limits, circuit breaker status
    """
    from apps.risk.models import RiskLimit, CircuitBreaker
    from apps.accounts.models import BrokerAccount

    # Get user's accounts
    accounts = BrokerAccount.objects.filter(user=request.user, is_active=True)

    # Get risk limits for each account
    risk_data = []
    for account in accounts:
        limits = RiskLimit.objects.filter(account=account)
        circuit = CircuitBreaker.objects.filter(account=account).first()

        risk_data.append({
            'account': account,
            'limits': limits,
            'circuit_breaker': circuit,
        })

    context = {
        'page_title': 'Risk Dashboard',
        'risk_data': risk_data,
    }

    return render(request, 'algo_test/risk.html', context)
