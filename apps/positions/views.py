"""
Views for System Positions management page.
"""

import json
from decimal import Decimal, InvalidOperation
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from apps.positions.models import Position
from apps.core.constants import (
    POSITION_STATUS_OPEN,
    POSITION_STATUS_CLOSED,
    POSITION_STATUS_SUGGESTED,
)

BROKER_DISPLAY = {'KOTAK': 'Kotak Neo', 'ICICI': 'ICICI Breeze'}


@login_required
def system_positions(request):
    """System Positions page - view and manage all positions tracked by mCube."""
    status_filter = request.GET.get('status', 'OPEN')

    if status_filter == 'ALL':
        positions = Position.objects.select_related('account').all()
    else:
        positions = Position.objects.select_related('account').filter(status=status_filter)

    # Compute P&L % for each position
    position_data = []
    total_unrealized = Decimal('0')
    total_realized = Decimal('0')

    for pos in positions:
        pnl_pct = None
        if pos.entry_price and pos.entry_price != 0 and pos.quantity:
            # quantity stores total shares (not lots), so no lot_size multiplication
            entry_value = pos.entry_price * pos.quantity
            if entry_value != 0:
                pnl_pct = (pos.unrealized_pnl / entry_value * 100) if pos.status == POSITION_STATUS_OPEN else (
                    pos.realized_pnl / entry_value * 100 if pos.realized_pnl else Decimal('0')
                )

        sl_distance = None
        target_distance = None
        if pos.stop_loss and pos.current_price and pos.current_price != 0:
            if pos.direction == 'LONG':
                sl_distance = ((pos.current_price - pos.stop_loss) / pos.current_price * 100)
            elif pos.direction == 'SHORT':
                sl_distance = ((pos.stop_loss - pos.current_price) / pos.current_price * 100)

        if pos.target and pos.current_price and pos.current_price != 0:
            if pos.direction == 'LONG':
                target_distance = ((pos.target - pos.current_price) / pos.current_price * 100)
            elif pos.direction == 'SHORT':
                target_distance = ((pos.current_price - pos.target) / pos.current_price * 100)

        if pos.status == POSITION_STATUS_OPEN:
            total_unrealized += pos.unrealized_pnl or Decimal('0')
        total_realized += pos.realized_pnl or Decimal('0')

        broker_code = pos.account.broker if pos.account else ''
        broker_display = BROKER_DISPLAY.get(broker_code, broker_code)

        position_data.append({
            'position': pos,
            'pnl_pct': round(pnl_pct, 2) if pnl_pct is not None else None,
            'sl_distance': round(sl_distance, 2) if sl_distance is not None else None,
            'target_distance': round(target_distance, 2) if target_distance is not None else None,
            'broker_display': broker_display,
        })

    context = {
        'position_data': position_data,
        'status_filter': status_filter,
        'total_unrealized': total_unrealized,
        'total_realized': total_realized,
        'total_count': len(position_data),
        'open_count': Position.objects.filter(status=POSITION_STATUS_OPEN).count(),
        'closed_count': Position.objects.filter(status=POSITION_STATUS_CLOSED).count(),
        'suggested_count': Position.objects.filter(status=POSITION_STATUS_SUGGESTED).count(),
    }

    return render(request, 'positions/system_positions.html', context)


@require_POST
@login_required
def update_position_field(request):
    """API endpoint to update a single field on a position."""
    try:
        data = json.loads(request.body)
        position_id = data.get('position_id')
        field = data.get('field')
        value = data.get('value')

        EDITABLE_FIELDS = {
            'stop_loss', 'target', 'notes', 'quantity',
            'entry_price', 'exit_reason', 'strategy_type',
        }

        if field not in EDITABLE_FIELDS:
            return JsonResponse({'success': False, 'error': f'Field "{field}" is not editable'})

        position = Position.objects.get(id=position_id)

        # Handle decimal fields
        decimal_fields = {'stop_loss', 'target', 'entry_price'}
        if field in decimal_fields:
            if value == '' or value is None:
                value = None
            else:
                try:
                    value = Decimal(str(value))
                except (InvalidOperation, ValueError):
                    return JsonResponse({'success': False, 'error': f'Invalid number for {field}'})

        # Handle integer fields
        if field == 'quantity':
            try:
                value = int(value)
                if value < 1:
                    return JsonResponse({'success': False, 'error': 'Quantity must be at least 1'})
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': 'Invalid quantity'})

        setattr(position, field, value)
        position.save(update_fields=[field, 'updated_at'])

        # Return computed values that may have changed
        response = {'success': True, 'field': field, 'value': str(value) if value is not None else ''}

        # If stop_loss or target changed, recalculate distances
        if field in ('stop_loss', 'target') and position.current_price and position.current_price != 0:
            if field == 'stop_loss' and value is not None:
                if position.direction == 'LONG':
                    response['sl_distance'] = str(round((position.current_price - value) / position.current_price * 100, 2))
                elif position.direction == 'SHORT':
                    response['sl_distance'] = str(round((value - position.current_price) / position.current_price * 100, 2))
            if field == 'target' and value is not None:
                if position.direction == 'LONG':
                    response['target_distance'] = str(round((value - position.current_price) / position.current_price * 100, 2))
                elif position.direction == 'SHORT':
                    response['target_distance'] = str(round((position.current_price - value) / position.current_price * 100, 2))

        return JsonResponse(response)

    except Position.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Position not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
