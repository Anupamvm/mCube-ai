"""
Views for the llmskill "Verify Trade" / "Get Data" flow.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.positions.models import Position
from apps.positions.views import _underlying

logger = logging.getLogger(__name__)


@login_required
def verify_trade_page(request, position_id):
    """Render the trade verification page for an open position.

    Data itself is fetched client-side via the "Get Data" button, not on
    page load, so opening this page never triggers a live analysis run.
    """
    position = get_object_or_404(Position, id=position_id)
    # label falls back to instrument when display_name is blank (e.g. broker-synced
    # positions without a formatted display name); _underlying() is a no-op on plain
    # symbols like "VBL" that don't carry an expiry/FUT suffix.
    symbol = _underlying(position.label)
    expiry_date = position.expiry_date.isoformat() if position.expiry_date else ''

    return render(request, 'llmskill/verify_trade.html', {
        'position': position,
        'symbol': symbol,
        'expiry_date': expiry_date,
    })


@login_required
@require_POST
def get_data_api(request):
    """Aggregate and return all stored/computed verification data for a symbol+expiry.

    Request body (POST form data):
        symbol: Underlying symbol, e.g. 'HDFCBANK'
        expiry_date: 'YYYY-MM-DD'
        position_id: Optional Position id, recorded on the saved snapshot
    """
    from apps.trading.services.analysis_service import clean_dict_for_json

    from .models import TradeVerificationSnapshot
    from .services.data_aggregator import get_verification_data

    symbol = request.POST.get('symbol', '').strip().upper()
    expiry_date = request.POST.get('expiry_date', '').strip()
    position_id = request.POST.get('position_id') or None

    if not symbol or not expiry_date:
        return JsonResponse({'success': False, 'error': 'symbol and expiry_date are required'}, status=400)

    try:
        data = get_verification_data(symbol, expiry_date)
        data = clean_dict_for_json(data)

        TradeVerificationSnapshot.objects.create(
            position_id=position_id,
            symbol=symbol,
            expiry_date=expiry_date,
            requested_by=request.user,
            data_snapshot=data,
        )

        return JsonResponse({'success': True, 'data': data})
    except Exception as e:
        logger.error(f"get_data_api failed for {symbol}/{expiry_date}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
