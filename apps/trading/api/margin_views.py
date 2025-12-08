"""
Margin Data API Views

Endpoints for fetching real-time margin information from broker APIs.
"""

import logging
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.http import JsonResponse

logger = logging.getLogger(__name__)


@login_required
@require_GET
def get_margin_data(request):
    """
    Get real-time margin data from Neo API

    Returns:
        JSON with margin information:
        - available_margin: Available margin/collateral
        - used_margin: Currently used margin
        - total_margin: Total margin (Net)
        - collateral: Collateral value
        - margin_utilization_pct: Percentage of margin used
        - last_updated: Timestamp
    """
    try:
        from tools.neo import NeoAPI

        # Initialize Neo API
        neo = NeoAPI()

        # Login if not already logged in
        if not neo.session_active:
            neo.login()

        # Fetch margin data
        margin_data = neo.get_margin()

        if not margin_data:
            return JsonResponse({
                'success': False,
                'error': 'Could not fetch margin data from Neo API'
            })

        # Calculate margin utilization percentage
        available = margin_data.get('available_margin', 0)
        used = margin_data.get('used_margin', 0)
        total = margin_data.get('total_margin', 0)

        margin_utilization_pct = 0
        if total > 0:
            margin_utilization_pct = (used / total) * 100

        return JsonResponse({
            'success': True,
            'data': {
                'available_margin': float(available),
                'used_margin': float(used),
                'total_margin': float(total),
                'collateral': float(margin_data.get('collateral', 0)),
                'margin_utilization_pct': round(margin_utilization_pct, 2),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'Neo API',
                'raw': margin_data.get('raw', {})
            }
        })

    except Exception as e:
        logger.error(f"Error fetching margin data: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Error fetching margin data: {str(e)}'
        })
