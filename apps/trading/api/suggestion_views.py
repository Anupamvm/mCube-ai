"""
Trade Suggestion API Views

Endpoints for managing trade suggestions - viewing details,
listing suggestions, updating status and parameters.
"""

import logging
from decimal import Decimal
from datetime import datetime, date

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse

logger = logging.getLogger(__name__)


@login_required
@require_GET
def get_suggestion_details(request, suggestion_id):
    """
    Get detailed data for a specific trade suggestion

    URL params:
        - suggestion_id: ID of the suggestion
    """
    try:
        from apps.trading.models import TradeSuggestion

        # Get suggestion
        suggestion = TradeSuggestion.objects.filter(
            id=suggestion_id,
            user=request.user
        ).first()

        if not suggestion:
            return JsonResponse({
                'success': False,
                'error': 'Suggestion not found'
            })

        # Get position details from JSON field
        position_details = suggestion.position_details or {}

        # Return all data needed for trade execution
        return JsonResponse({
            'success': True,
            'suggestion': {
                'id': suggestion.id,
                'stock_symbol': suggestion.instrument,
                'instrument': suggestion.instrument,
                'suggestion_type': suggestion.suggestion_type,
                'strategy': suggestion.strategy,
                'direction': suggestion.direction,
                'spot_price': float(suggestion.spot_price) if suggestion.spot_price else 0,
                'expiry_date': suggestion.expiry_date.strftime('%Y-%m-%d') if suggestion.expiry_date else None,
                'days_to_expiry': suggestion.days_to_expiry if suggestion.days_to_expiry else 0,
                'recommended_lots': suggestion.recommended_lots,
                'margin_required': float(suggestion.margin_required) if suggestion.margin_required else 0,
                'margin_available': float(suggestion.margin_available) if suggestion.margin_available else 0,
                'margin_per_lot': float(suggestion.margin_per_lot) if suggestion.margin_per_lot else 0,
                'margin_utilization': float(suggestion.margin_utilization) if suggestion.margin_utilization else 0,
                'max_profit': float(suggestion.max_profit) if suggestion.max_profit else 0,
                'max_loss': float(suggestion.max_loss) if suggestion.max_loss else 0,
                # Strangle-specific fields
                'call_strike': float(suggestion.call_strike) if suggestion.call_strike else None,
                'put_strike': float(suggestion.put_strike) if suggestion.put_strike else None,
                'call_premium': float(suggestion.call_premium) if suggestion.call_premium else None,
                'put_premium': float(suggestion.put_premium) if suggestion.put_premium else None,
                'total_premium': float(suggestion.total_premium) if suggestion.total_premium else None,
                'vix': float(suggestion.vix) if suggestion.vix else None,
                # Position details from JSON
                'stop_loss': position_details.get('stop_loss', 0),
                'target': position_details.get('target', 0),
                'lot_size': position_details.get('lot_size', 0),
                'entry_value': position_details.get('entry_value', 0),
                'futures_price': position_details.get('margin_data', {}).get('futures_price', suggestion.spot_price),
                # Full position details for reference
                'position_details': position_details
            }
        })

    except Exception as e:
        logger.error(f"Error fetching suggestion details: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_GET
def get_trade_suggestions(request):
    """
    Get trade suggestions history for the logged-in user

    Query params:
        - status: Filter by status (SUGGESTED, TAKEN, ACTIVE, CLOSED, etc.)
        - suggestion_type: Filter by type (OPTIONS, FUTURES)
        - limit: Number of records (default: 20)
    """
    try:
        from apps.trading.models import TradeSuggestion

        # Get query parameters
        status = request.GET.get('status', None)
        suggestion_type = request.GET.get('suggestion_type', None)
        limit = int(request.GET.get('limit', 20))

        # Build query
        queryset = TradeSuggestion.objects.filter(user=request.user)

        if status:
            queryset = queryset.filter(status=status)

        if suggestion_type:
            queryset = queryset.filter(suggestion_type=suggestion_type)

        # Get suggestions ordered by created_at desc
        suggestions = queryset[:limit]

        # Serialize to JSON
        suggestions_data = []
        for suggestion in suggestions:
            suggestions_data.append({
                'id': suggestion.id,
                'strategy': suggestion.get_strategy_display(),
                'suggestion_type': suggestion.suggestion_type,
                'instrument': suggestion.instrument,
                'direction': suggestion.direction,
                'status': suggestion.status,
                'status_color': suggestion.get_status_color(),
                # Market Data
                'spot_price': float(suggestion.spot_price) if suggestion.spot_price else None,
                'vix': float(suggestion.vix) if suggestion.vix else None,
                'expiry_date': suggestion.expiry_date.strftime('%Y-%m-%d') if suggestion.expiry_date else None,
                'days_to_expiry': suggestion.days_to_expiry,
                # Strike Details (for Options)
                'call_strike': float(suggestion.call_strike) if suggestion.call_strike else None,
                'put_strike': float(suggestion.put_strike) if suggestion.put_strike else None,
                'call_premium': float(suggestion.call_premium) if suggestion.call_premium else None,
                'put_premium': float(suggestion.put_premium) if suggestion.put_premium else None,
                'total_premium': float(suggestion.total_premium) if suggestion.total_premium else None,
                # Position Sizing
                'recommended_lots': suggestion.recommended_lots,
                'margin_required': float(suggestion.margin_required) if suggestion.margin_required else None,
                'margin_available': float(suggestion.margin_available) if suggestion.margin_available else None,
                'margin_per_lot': float(suggestion.margin_per_lot) if suggestion.margin_per_lot else None,
                'margin_utilization': float(suggestion.margin_utilization) if suggestion.margin_utilization else None,
                # Risk Metrics
                'max_profit': float(suggestion.max_profit) if suggestion.max_profit else None,
                'max_loss': float(suggestion.max_loss) if suggestion.max_loss else None,
                'breakeven_upper': float(suggestion.breakeven_upper) if suggestion.breakeven_upper else None,
                'breakeven_lower': float(suggestion.breakeven_lower) if suggestion.breakeven_lower else None,
                # P&L (for closed trades)
                'realized_pnl': float(suggestion.realized_pnl) if suggestion.realized_pnl else None,
                'return_on_margin': float(suggestion.return_on_margin) if suggestion.return_on_margin else None,
                # Timestamps
                'created_at': suggestion.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'taken_timestamp': suggestion.taken_timestamp.strftime('%Y-%m-%d %H:%M:%S') if suggestion.taken_timestamp else None,
                'closed_timestamp': suggestion.closed_timestamp.strftime('%Y-%m-%d %H:%M:%S') if suggestion.closed_timestamp else None,
                # Complete Data
                'algorithm_reasoning': suggestion.algorithm_reasoning,
                'position_details': suggestion.position_details,
                'user_notes': suggestion.user_notes,
                # State
                'is_actionable': suggestion.is_actionable,
                'is_active': suggestion.is_active,
                'is_closed': suggestion.is_closed,
            })

        return JsonResponse({
            'success': True,
            'count': len(suggestions_data),
            'suggestions': suggestions_data
        })

    except Exception as e:
        logger.error(f"Error fetching trade suggestions: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def update_suggestion_status(request):
    """
    Update trade suggestion status

    POST params:
        - suggestion_id: ID of the suggestion
        - action: Action to perform (TAKE, REJECT, MARK_ACTIVE, CLOSE)
        - pnl: Realized P&L (for CLOSE action)
        - exit_value: Exit value (for CLOSE action)
        - outcome: Outcome (SUCCESSFUL, LOSS, BREAKEVEN) for CLOSE action
        - user_notes: User notes
    """
    try:
        from apps.trading.models import TradeSuggestion

        suggestion_id = request.POST.get('suggestion_id')
        action = request.POST.get('action', '').upper()
        user_notes = request.POST.get('user_notes', '')

        if not suggestion_id:
            return JsonResponse({
                'success': False,
                'error': 'suggestion_id is required'
            })

        # Get suggestion
        suggestion = TradeSuggestion.objects.filter(
            id=suggestion_id,
            user=request.user
        ).first()

        if not suggestion:
            return JsonResponse({
                'success': False,
                'error': 'Suggestion not found'
            })

        # Perform action
        if action == 'TAKE':
            suggestion.mark_taken(user_notes=user_notes)
            message = 'Suggestion marked as TAKEN'

        elif action == 'REJECT':
            suggestion.mark_rejected(user_notes=user_notes)
            message = 'Suggestion marked as REJECTED'

        elif action == 'MARK_ACTIVE':
            suggestion.mark_active()
            message = 'Trade marked as ACTIVE'

        elif action == 'CLOSE':
            pnl = request.POST.get('pnl')
            exit_value = request.POST.get('exit_value')
            outcome = request.POST.get('outcome', 'CLOSED').upper()

            if pnl:
                pnl = Decimal(pnl)
            if exit_value:
                exit_value = Decimal(exit_value)

            suggestion.mark_closed(
                pnl=pnl,
                exit_value=exit_value,
                outcome=outcome,
                user_notes=user_notes
            )
            message = f'Trade closed with outcome: {outcome}'

        else:
            return JsonResponse({
                'success': False,
                'error': f'Invalid action: {action}'
            })

        return JsonResponse({
            'success': True,
            'message': message,
            'suggestion': {
                'id': suggestion.id,
                'status': suggestion.status,
                'status_color': suggestion.get_status_color(),
            }
        })

    except Exception as e:
        logger.error(f"Error updating suggestion status: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def update_suggestion_parameters(request):
    """
    Update trade suggestion parameters (lots, strikes, expiry, etc.) from UI edits

    POST params (JSON):
        - suggestion_id: ID of the suggestion to update
        - recommended_lots: Updated number of lots
        - call_strike: Updated call strike (for strangles)
        - put_strike: Updated put strike (for strangles)
        - call_premium: Updated call premium (for strangles)
        - put_premium: Updated put premium (for strangles)
        - expiry_date: Updated expiry date (YYYY-MM-DD format)
        - entry_price: Updated entry price (for futures)
        - stop_loss: Updated stop loss
        - target: Updated target

    Returns:
        JsonResponse with success status and updated values
    """
    try:
        import json
        from apps.trading.models import TradeSuggestion

        # Parse JSON body
        data = json.loads(request.body)
        suggestion_id = data.get('suggestion_id')

        if not suggestion_id:
            return JsonResponse({
                'success': False,
                'error': 'suggestion_id is required'
            })

        # Get suggestion
        suggestion = TradeSuggestion.objects.filter(
            id=suggestion_id,
            user=request.user
        ).first()

        if not suggestion:
            return JsonResponse({
                'success': False,
                'error': 'Suggestion not found'
            })

        # Track what was updated
        updated_fields = []

        # Update lots
        if 'recommended_lots' in data:
            new_lots = int(data['recommended_lots'])
            if new_lots != suggestion.recommended_lots:
                suggestion.recommended_lots = new_lots
                updated_fields.append(f'lots: {new_lots}')

                # Recalculate margin_required based on new lots
                if suggestion.margin_per_lot:
                    suggestion.margin_required = suggestion.margin_per_lot * new_lots
                    updated_fields.append(f'margin_required: {suggestion.margin_required}')

        # Update strangle strikes and premiums
        if 'call_strike' in data:
            new_call_strike = Decimal(str(data['call_strike']))
            if new_call_strike != suggestion.call_strike:
                suggestion.call_strike = new_call_strike
                updated_fields.append(f'call_strike: {new_call_strike}')

        if 'put_strike' in data:
            new_put_strike = Decimal(str(data['put_strike']))
            if new_put_strike != suggestion.put_strike:
                suggestion.put_strike = new_put_strike
                updated_fields.append(f'put_strike: {new_put_strike}')

        if 'call_premium' in data:
            new_call_premium = Decimal(str(data['call_premium']))
            if new_call_premium != suggestion.call_premium:
                suggestion.call_premium = new_call_premium
                updated_fields.append(f'call_premium: {new_call_premium}')

        if 'put_premium' in data:
            new_put_premium = Decimal(str(data['put_premium']))
            if new_put_premium != suggestion.put_premium:
                suggestion.put_premium = new_put_premium
                updated_fields.append(f'put_premium: {new_put_premium}')

        # Recalculate total premium if call or put premium changed
        if suggestion.call_premium and suggestion.put_premium:
            new_total = suggestion.call_premium + suggestion.put_premium
            if new_total != suggestion.total_premium:
                suggestion.total_premium = new_total
                updated_fields.append(f'total_premium: {new_total}')

        # Update expiry date
        if 'expiry_date' in data:
            new_expiry = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
            if new_expiry != suggestion.expiry_date:
                suggestion.expiry_date = new_expiry
                updated_fields.append(f'expiry_date: {new_expiry}')

                # Recalculate days_to_expiry
                days_diff = (new_expiry - date.today()).days
                suggestion.days_to_expiry = days_diff
                updated_fields.append(f'days_to_expiry: {days_diff}')

        # Update futures-specific fields
        if 'entry_price' in data:
            new_entry = Decimal(str(data['entry_price']))
            # Store in position_details JSON field
            position_details = suggestion.position_details or {}
            if position_details.get('margin_data', {}).get('futures_price') != float(new_entry):
                if 'margin_data' not in position_details:
                    position_details['margin_data'] = {}
                position_details['margin_data']['futures_price'] = float(new_entry)
                suggestion.position_details = position_details
                updated_fields.append(f'entry_price: {new_entry}')

        if 'stop_loss' in data:
            new_sl = Decimal(str(data['stop_loss']))
            position_details = suggestion.position_details or {}
            if position_details.get('stop_loss') != float(new_sl):
                position_details['stop_loss'] = float(new_sl)
                suggestion.position_details = position_details
                updated_fields.append(f'stop_loss: {new_sl}')

        if 'target' in data:
            new_target = Decimal(str(data['target']))
            position_details = suggestion.position_details or {}
            if position_details.get('target') != float(new_target):
                position_details['target'] = float(new_target)
                suggestion.position_details = position_details
                updated_fields.append(f'target: {new_target}')

        # Save if anything changed
        if updated_fields:
            suggestion.save()
            logger.info(f"Updated TradeSuggestion #{suggestion_id} - {', '.join(updated_fields)}")

            return JsonResponse({
                'success': True,
                'message': f'Updated: {", ".join(updated_fields)}',
                'updated_fields': updated_fields,
                'suggestion': {
                    'id': suggestion.id,
                    'recommended_lots': suggestion.recommended_lots,
                    'call_strike': float(suggestion.call_strike) if suggestion.call_strike else None,
                    'put_strike': float(suggestion.put_strike) if suggestion.put_strike else None,
                    'call_premium': float(suggestion.call_premium) if suggestion.call_premium else None,
                    'put_premium': float(suggestion.put_premium) if suggestion.put_premium else None,
                    'total_premium': float(suggestion.total_premium) if suggestion.total_premium else None,
                    'expiry_date': suggestion.expiry_date.strftime('%Y-%m-%d') if suggestion.expiry_date else None,
                    'margin_required': float(suggestion.margin_required) if suggestion.margin_required else None,
                }
            })
        else:
            return JsonResponse({
                'success': True,
                'message': 'No changes detected',
                'updated_fields': []
            })

    except Exception as e:
        logger.error(f"Error updating suggestion parameters: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
