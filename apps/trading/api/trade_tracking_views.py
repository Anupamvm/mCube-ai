"""
Trade Tracking API Views

Provides REST API endpoints for:
- Accept/reject trade suggestions
- List taken trades with filters
- FY performance reports
- Trigger broker trade sync
"""

import logging
from datetime import date
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from apps.trading.models import TradeSuggestion, TakenTrade
from apps.trading.services.trade_action_service import TradeActionService
from apps.brokers.services.trade_sync import TradeSyncService
from apps.analytics.services.fy_analytics import FYAnalyticsService
from apps.accounts.models import BrokerAccount

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def accept_suggestion(request, suggestion_id):
    """
    Accept a trade suggestion and create a TakenTrade record.

    POST /api/suggestions/<id>/accept/

    Request body (JSON):
        - account_id: int (required) - BrokerAccount ID to use
        - notes: str (optional) - User notes

    Response:
        - success: bool
        - taken_trade_id: int (if successful)
        - message: str
        - error: str (if failed)
    """
    import json

    try:
        data = json.loads(request.body)
        account_id = data.get('account_id')
        notes = data.get('notes', '')

        if not account_id:
            return JsonResponse({
                'success': False,
                'error': 'account_id is required'
            }, status=400)

        suggestion = get_object_or_404(TradeSuggestion, id=suggestion_id)
        account = get_object_or_404(BrokerAccount, id=account_id)

        # Note: BrokerAccount is shared across users (no user field)

        result = TradeActionService.accept_suggestion(
            suggestion=suggestion,
            user=request.user,
            account=account,
            notes=notes
        )

        if result.get('success'):
            taken_trade = result['taken_trade']
            return JsonResponse({
                'success': True,
                'taken_trade_id': taken_trade.id,
                'message': f'Trade accepted successfully. TakenTrade #{taken_trade.id} created.'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Unknown error')
            }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.exception(f"Error accepting suggestion: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def reject_suggestion(request, suggestion_id):
    """
    Reject a trade suggestion.

    POST /api/suggestions/<id>/reject/

    Request body (JSON):
        - reason: str (optional) - Reason for rejection

    Response:
        - success: bool
        - message: str
        - error: str (if failed)
    """
    import json

    try:
        data = json.loads(request.body) if request.body else {}
        reason = data.get('reason', '')

        suggestion = get_object_or_404(TradeSuggestion, id=suggestion_id)

        result = TradeActionService.reject_suggestion(
            suggestion=suggestion,
            user=request.user,
            reason=reason
        )

        if result.get('success'):
            return JsonResponse({
                'success': True,
                'message': 'Trade suggestion rejected successfully.'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Unknown error')
            }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.exception(f"Error rejecting suggestion: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def list_taken_trades(request):
    """
    List taken trades with filters.

    GET /api/taken-trades/

    Query parameters:
        - status: str (optional) - Filter by status (ACTIVE, CLOSED, etc.)
        - account_id: int (optional) - Filter by account
        - strategy: str (optional) - Filter by strategy
        - outcome: str (optional) - Filter by outcome (PROFIT, LOSS, BREAKEVEN)
        - from_date: str (optional) - YYYY-MM-DD
        - to_date: str (optional) - YYYY-MM-DD
        - limit: int (optional) - Number of records (default: 50)
        - offset: int (optional) - Offset for pagination

    Response:
        - success: bool
        - trades: list of trade dicts
        - total_count: int
        - summary: dict with aggregate stats
    """
    try:
        # Get query parameters
        status = request.GET.get('status')
        account_id = request.GET.get('account_id')
        strategy = request.GET.get('strategy')
        outcome = request.GET.get('outcome')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))

        # Build queryset
        queryset = TakenTrade.objects.filter(user=request.user)

        if status:
            if status.upper() == 'ACTIVE':
                queryset = queryset.filter(status__in=['PENDING_EXECUTION', 'EXECUTED', 'ACTIVE'])
            else:
                queryset = queryset.filter(status=status.upper())

        if account_id:
            queryset = queryset.filter(account_id=account_id)

        if strategy:
            queryset = queryset.filter(strategy=strategy)

        if outcome:
            queryset = queryset.filter(outcome=outcome.upper())

        if from_date:
            queryset = queryset.filter(taken_at__date__gte=from_date)

        if to_date:
            queryset = queryset.filter(taken_at__date__lte=to_date)

        # Get total count before pagination
        total_count = queryset.count()

        # Apply pagination and fetch
        trades = queryset.select_related(
            'account', 'suggestion', 'position'
        ).order_by('-taken_at')[offset:offset + limit]

        # Serialize trades
        trade_list = []
        for trade in trades:
            trade_list.append({
                'id': trade.id,
                'instrument': trade.instrument,
                'strategy': trade.strategy,
                'trade_type': trade.trade_type,
                'direction': trade.direction,
                'entry_price': float(trade.entry_price) if trade.entry_price else None,
                'exit_price': float(trade.exit_price) if trade.exit_price else None,
                'quantity': trade.quantity,
                'lot_size': trade.lot_size,
                'status': trade.status,
                'status_display': trade.get_status_display(),
                'status_color': trade.get_status_color(),
                'outcome': trade.outcome,
                'outcome_display': trade.get_outcome_display(),
                'outcome_color': trade.get_outcome_color(),
                'realized_pnl': float(trade.realized_pnl) if trade.realized_pnl else None,
                'net_pnl': float(trade.net_pnl) if trade.net_pnl else None,
                'charges': float(trade.charges) if trade.charges else 0,
                'return_on_margin': float(trade.return_on_margin) if trade.return_on_margin else None,
                'margin_used': float(trade.margin_used) if trade.margin_used else None,
                'taken_at': trade.taken_at.isoformat() if trade.taken_at else None,
                'executed_at': trade.executed_at.isoformat() if trade.executed_at else None,
                'closed_at': trade.closed_at.isoformat() if trade.closed_at else None,
                'account_name': trade.account.account_name if trade.account else None,
                'notes': trade.notes,
            })

        # Get summary stats
        summary = TradeActionService.get_trade_summary(request.user)

        return JsonResponse({
            'success': True,
            'trades': trade_list,
            'total_count': total_count,
            'summary': summary
        })

    except Exception as e:
        logger.exception(f"Error listing taken trades: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_fy_report(request):
    """
    Get FY performance report.

    GET /api/reports/fy/

    Query parameters:
        - fy_year: int (optional) - FY start year (default: current FY)
        - account_id: int (optional) - Filter by account

    Response:
        - success: bool
        - report: dict with FY metrics, charts, strategy breakdown
        - available_years: list of FY years with data
    """
    try:
        fy_year = request.GET.get('fy_year')
        account_id = request.GET.get('account_id')

        if fy_year:
            fy_year = int(fy_year)
        else:
            fy_year = FYAnalyticsService.get_current_fy_year()

        account = None
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        report = FYAnalyticsService.get_fy_report(
            user=request.user,
            fy_year=fy_year,
            account=account
        )

        available_years = FYAnalyticsService.get_available_fy_years(request.user)

        return JsonResponse({
            'success': True,
            'report': report,
            'available_years': available_years,
            'current_fy_year': fy_year
        })

    except Exception as e:
        logger.exception(f"Error getting FY report: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def sync_trades(request):
    """
    Trigger trade sync from broker.

    POST /api/sync/trades/

    Request body (JSON):
        - account_id: int (required) - BrokerAccount ID
        - from_date: str (optional) - YYYY-MM-DD (default: today)
        - to_date: str (optional) - YYYY-MM-DD (default: today)

    Response:
        - success: bool
        - new_count: int
        - updated_count: int
        - total_fetched: int
        - errors: list of error messages
    """
    import json
    from datetime import datetime

    try:
        data = json.loads(request.body)
        account_id = data.get('account_id')
        from_date = data.get('from_date')
        to_date = data.get('to_date')

        if not account_id:
            return JsonResponse({
                'success': False,
                'error': 'account_id is required'
            }, status=400)

        account = get_object_or_404(BrokerAccount, id=account_id)

        # Note: BrokerAccount is shared across users (no user field)

        # Parse dates or use today
        if from_date:
            from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
        else:
            from_date = date.today()

        if to_date:
            to_date = datetime.strptime(to_date, '%Y-%m-%d').date()
        else:
            to_date = date.today()

        result = TradeSyncService.sync_trades_for_date_range(
            account=account,
            from_date=from_date,
            to_date=to_date
        )

        return JsonResponse({
            'success': result.get('success', False),
            'new_count': result.get('new_count', 0),
            'updated_count': result.get('updated_count', 0),
            'total_fetched': result.get('total_fetched', 0),
            'errors': result.get('errors', []),
            'message': f"Synced {result.get('new_count', 0)} new trades, {result.get('updated_count', 0)} existing"
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.exception(f"Error syncing trades: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_sync_status(request, account_id):
    """
    Get trade sync status for an account.

    GET /api/sync/status/<account_id>/

    Response:
        - success: bool
        - last_sync: datetime ISO string
        - total_records: int
        - unreconciled_count: int
        - is_syncing: bool
    """
    try:
        account = get_object_or_404(BrokerAccount, id=account_id)

        # Note: BrokerAccount is shared across users (no user field)

        status = TradeSyncService.get_sync_status(account)

        return JsonResponse({
            'success': True,
            'last_sync': status['last_sync'].isoformat() if status['last_sync'] else None,
            'total_records': status['total_records'],
            'unreconciled_count': status['unreconciled_count'],
            'is_syncing': status['is_syncing']
        })

    except Exception as e:
        logger.exception(f"Error getting sync status: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_trade_detail(request, trade_id):
    """
    Get detailed information about a taken trade.

    GET /api/taken-trades/<id>/

    Response:
        - success: bool
        - trade: dict with full trade details
    """
    try:
        trade = get_object_or_404(
            TakenTrade.objects.select_related('suggestion', 'position', 'account'),
            id=trade_id,
            user=request.user
        )

        trade_data = {
            'id': trade.id,
            'instrument': trade.instrument,
            'strategy': trade.strategy,
            'strategy_display': trade.get_strategy_display(),
            'trade_type': trade.trade_type,
            'direction': trade.direction,
            'entry_price': float(trade.entry_price) if trade.entry_price else None,
            'exit_price': float(trade.exit_price) if trade.exit_price else None,
            'quantity': trade.quantity,
            'lot_size': trade.lot_size,
            'total_quantity': trade.total_quantity,
            'call_strike': float(trade.call_strike) if trade.call_strike else None,
            'put_strike': float(trade.put_strike) if trade.put_strike else None,
            'expiry_date': trade.expiry_date.isoformat() if trade.expiry_date else None,
            'status': trade.status,
            'status_display': trade.get_status_display(),
            'status_color': trade.get_status_color(),
            'outcome': trade.outcome,
            'outcome_display': trade.get_outcome_display(),
            'outcome_color': trade.get_outcome_color(),
            'realized_pnl': float(trade.realized_pnl) if trade.realized_pnl else None,
            'charges': float(trade.charges) if trade.charges else 0,
            'net_pnl': float(trade.net_pnl) if trade.net_pnl else None,
            'return_on_margin': float(trade.return_on_margin) if trade.return_on_margin else None,
            'margin_used': float(trade.margin_used) if trade.margin_used else None,
            'taken_at': trade.taken_at.isoformat() if trade.taken_at else None,
            'executed_at': trade.executed_at.isoformat() if trade.executed_at else None,
            'closed_at': trade.closed_at.isoformat() if trade.closed_at else None,
            'notes': trade.notes,
            'account': {
                'id': trade.account.id,
                'name': trade.account.account_name,
                'broker': trade.account.broker,
            } if trade.account else None,
            'suggestion': {
                'id': trade.suggestion.id,
                'status': trade.suggestion.status,
                'algorithm_reasoning': trade.suggestion.algorithm_reasoning,
            } if trade.suggestion else None,
            'position': {
                'id': trade.position.id,
                'status': trade.position.status,
                'unrealized_pnl': float(trade.position.unrealized_pnl) if trade.position.unrealized_pnl else None,
            } if trade.position else None,
        }

        return JsonResponse({
            'success': True,
            'trade': trade_data
        })

    except Exception as e:
        logger.exception(f"Error getting trade detail: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def create_trades_from_broker(request):
    """
    Create TakenTrade records from synced broker trade history.

    POST /api/trades/create-from-broker/

    Request body (JSON):
        - account_id: int (required) - BrokerAccount ID
        - from_date: str (optional) - YYYY-MM-DD
        - to_date: str (optional) - YYYY-MM-DD

    Response:
        - success: bool
        - created_count: int
        - skipped_count: int
        - errors: list of error messages
        - message: str
    """
    import json
    from datetime import datetime

    try:
        data = json.loads(request.body)
        account_id = data.get('account_id')
        from_date = data.get('from_date')
        to_date = data.get('to_date')

        if not account_id:
            return JsonResponse({
                'success': False,
                'error': 'account_id is required'
            }, status=400)

        account = get_object_or_404(BrokerAccount, id=account_id)

        # Parse dates if provided
        if from_date:
            from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
        if to_date:
            to_date = datetime.strptime(to_date, '%Y-%m-%d').date()

        result = TradeActionService.create_trades_from_broker_history(
            user=request.user,
            account=account,
            from_date=from_date,
            to_date=to_date
        )

        return JsonResponse({
            'success': result['success'],
            'created_count': result['created_count'],
            'skipped_count': result['skipped_count'],
            'errors': result['errors'],
            'message': f"Created {result['created_count']} trades, skipped {result['skipped_count']} (open positions)"
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.exception(f"Error creating trades from broker: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
