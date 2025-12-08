"""
Execution Control API Views

Endpoints for managing order execution - creating controls,
tracking progress, and cancelling executions.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse

logger = logging.getLogger(__name__)


@login_required
@require_POST
def create_execution_control(request):
    """Create execution control record for order tracking and cancellation"""
    try:
        import json
        from apps.trading.models import OrderExecutionControl

        data = json.loads(request.body)
        suggestion_id = data.get('suggestion_id')
        total_batches = data.get('total_batches', 0)

        if not suggestion_id:
            return JsonResponse({
                'success': False,
                'error': 'suggestion_id is required'
            })

        # Create or update execution control
        control, created = OrderExecutionControl.objects.get_or_create(
            suggestion_id=suggestion_id,
            defaults={'total_batches': total_batches}
        )

        if not created:
            # Reset if reusing
            control.is_cancelled = False
            control.cancel_reason = ''
            control.batches_completed = 0
            control.total_batches = total_batches
            control.save()

        return JsonResponse({
            'success': True,
            'message': 'Execution control created',
            'control_id': control.id
        })

    except Exception as e:
        logger.error(f"Error creating execution control: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def cancel_execution(request):
    """Cancel ongoing order execution"""
    try:
        import json
        from apps.trading.models import OrderExecutionControl

        data = json.loads(request.body)
        suggestion_id = data.get('suggestion_id')

        if not suggestion_id:
            return JsonResponse({
                'success': False,
                'error': 'suggestion_id is required'
            })

        control = OrderExecutionControl.objects.filter(
            suggestion_id=suggestion_id
        ).first()

        if not control:
            return JsonResponse({
                'success': False,
                'error': 'No ongoing execution found'
            })

        control.cancel(reason='User requested cancellation')

        return JsonResponse({
            'success': True,
            'message': 'Order execution cancelled'
        })

    except Exception as e:
        logger.error(f"Error cancelling execution: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def get_execution_progress(request, suggestion_id):
    """Get real-time progress of order execution"""
    try:
        from apps.trading.models import OrderExecutionControl

        control = OrderExecutionControl.objects.filter(
            suggestion_id=suggestion_id
        ).first()

        if not control:
            return JsonResponse({
                'success': False,
                'error': 'No execution found'
            })

        # For now, return basic progress
        # In future, this can be enhanced with detailed batch info
        return JsonResponse({
            'success': True,
            'progress': {
                'batches_completed': control.batches_completed,
                'total_batches': control.total_batches,
                'call_orders': control.batches_completed,  # Simplified for now
                'put_orders': control.batches_completed,   # Simplified for now
                'current_batch': {
                    'batch_num': control.batches_completed + 1,
                    'lots': None,
                    'quantity': None
                },
                'is_cancelled': control.is_cancelled
            }
        })

    except Exception as e:
        logger.error(f"Error getting execution progress: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
