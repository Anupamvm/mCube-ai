"""
Analytics and Learning System Views for mCube Trading System
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal

from apps.analytics.models import (
    LearningSession,
    LearningPattern,
    ParameterAdjustment,
    TradePerformance,
    PerformanceMetric,
)
from apps.analytics.services.learning_engine import LearningEngine
from apps.positions.models import Position

import logging

logger = logging.getLogger(__name__)


def is_admin_user(user):
    """Check if user has admin privileges"""
    return user.is_superuser or user.groups.filter(name='Admin').exists()


# =============================================================================
# LEARNING CONTROL VIEWS
# =============================================================================

@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
def learning_dashboard(request):
    """
    Main learning system dashboard.
    Shows active session, patterns, suggestions, and controls.
    """
    # Get active or most recent session
    active_session = LearningSession.objects.filter(status='RUNNING').first()
    recent_session = active_session or LearningSession.objects.order_by('-created_at').first()

    # Get patterns and suggestions
    patterns = LearningPattern.objects.filter(session=recent_session).order_by('-confidence_score')[:10] if recent_session else []
    suggestions = ParameterAdjustment.objects.filter(session=recent_session, status='SUGGESTED').order_by('-confidence')[:5] if recent_session else []

    # Get recent metrics
    recent_metrics = PerformanceMetric.objects.filter(session=recent_session).order_by('-calculation_date')[:5] if recent_session else []

    # Get trade statistics
    total_trades = Position.objects.filter(status='CLOSED').count()
    analyzed_trades = TradePerformance.objects.count()

    context = {
        'active_session': active_session,
        'recent_session': recent_session,
        'patterns': patterns,
        'suggestions': suggestions,
        'recent_metrics': recent_metrics,
        'total_trades': total_trades,
        'analyzed_trades': analyzed_trades,
        'can_start_learning': total_trades >= 10 and not active_session,
    }

    return render(request, 'analytics/learning_dashboard.html', context)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
def start_learning(request):
    """Start a new learning session."""
    name = request.POST.get('name', f'Learning Session {LearningSession.objects.count() + 1}')

    try:
        engine = LearningEngine()
        session = engine.start_learning(name)

        # Start continuous learning in background
        from apps.analytics.tasks import start_continuous_learning
        start_continuous_learning(session.id)

        messages.success(request, f" Learning session '{session.name}' started!")
        logger.info(f"User {request.user.username} started learning session: {session.name}")

    except Exception as e:
        logger.error(f"Error starting learning session: {e}")
        messages.error(request, f"Error starting learning: {str(e)}")

    return redirect('analytics:learning_dashboard')


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
def stop_learning(request, session_id):
    """Stop a learning session."""
    session = get_object_or_404(LearningSession, id=session_id)

    try:
        engine = LearningEngine()
        engine.stop_learning(session)

        messages.success(request, f"�  Learning session '{session.name}' stopped")
        logger.info(f"User {request.user.username} stopped learning session: {session.name}")

    except Exception as e:
        logger.error(f"Error stopping learning session: {e}")
        messages.error(request, f"Error: {str(e)}")

    return redirect('analytics:learning_dashboard')


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
def pause_learning(request, session_id):
    """Pause a learning session."""
    session = get_object_or_404(LearningSession, id=session_id)

    try:
        engine = LearningEngine()
        engine.pause_learning(session)

        messages.success(request, f"�  Learning session paused")
        logger.info(f"User {request.user.username} paused learning session: {session.name}")

    except Exception as e:
        logger.error(f"Error pausing learning session: {e}")
        messages.error(request, f"Error: {str(e)}")

    return redirect('analytics:learning_dashboard')


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
def resume_learning(request, session_id):
    """Resume a paused learning session."""
    session = get_object_or_404(LearningSession, id=session_id)

    try:
        engine = LearningEngine()
        engine.resume_learning(session)

        messages.success(request, f"�  Learning session resumed")
        logger.info(f"User {request.user.username} resumed learning session: {session.name}")

    except Exception as e:
        logger.error(f"Error resuming learning session: {e}")
        messages.error(request, f"Error: {str(e)}")

    return redirect('analytics:learning_dashboard')


# =============================================================================
# PATTERN & SUGGESTION VIEWS
# =============================================================================

@login_required
def view_patterns(request):
    """View all discovered patterns."""
    patterns = LearningPattern.objects.all().order_by('-confidence_score', '-success_rate')

    # Filter by type if specified
    pattern_type = request.GET.get('type')
    if pattern_type:
        patterns = patterns.filter(pattern_type=pattern_type)

    # Filter by actionable status
    actionable_only = request.GET.get('actionable')
    if actionable_only:
        patterns = patterns.filter(is_actionable=True)

    context = {
        'patterns': patterns,
        'pattern_type': pattern_type,
        'actionable_only': actionable_only,
    }

    return render(request, 'analytics/patterns_list.html', context)


@login_required
def view_pattern_detail(request, pattern_id):
    """View detailed information about a specific pattern."""
    pattern = get_object_or_404(LearningPattern, id=pattern_id)

    context = {
        'pattern': pattern,
    }

    return render(request, 'analytics/pattern_detail.html', context)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
def view_suggestions(request):
    """View all parameter suggestions."""
    suggestions = ParameterAdjustment.objects.all().order_by('-confidence', '-expected_improvement_pct')

    # Filter by status
    status = request.GET.get('status')
    if status:
        suggestions = suggestions.filter(status=status)

    context = {
        'suggestions': suggestions,
        'status': status,
    }

    return render(request, 'analytics/suggestions_list.html', context)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
def approve_suggestion(request, suggestion_id):
    """Approve a parameter suggestion."""
    suggestion = get_object_or_404(ParameterAdjustment, id=suggestion_id)

    try:
        from apps.analytics.services.parameter_optimizer import ParameterOptimizer
        optimizer = ParameterOptimizer(suggestion.session)
        optimizer.apply_suggestion(suggestion, request.user)

        messages.success(request, f" Suggestion approved: {suggestion.parameter_name}")
        logger.info(f"User {request.user.username} approved suggestion: {suggestion.parameter_name}")

    except Exception as e:
        logger.error(f"Error approving suggestion: {e}")
        messages.error(request, f"Error: {str(e)}")

    return redirect('analytics:view_suggestions')


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
def reject_suggestion(request, suggestion_id):
    """Reject a parameter suggestion."""
    suggestion = get_object_or_404(ParameterAdjustment, id=suggestion_id)
    reason = request.POST.get('reason', '')

    try:
        from apps.analytics.services.parameter_optimizer import ParameterOptimizer
        optimizer = ParameterOptimizer(suggestion.session)
        optimizer.reject_suggestion(suggestion, request.user, reason)

        messages.success(request, f"L Suggestion rejected: {suggestion.parameter_name}")
        logger.info(f"User {request.user.username} rejected suggestion: {suggestion.parameter_name}")

    except Exception as e:
        logger.error(f"Error rejecting suggestion: {e}")
        messages.error(request, f"Error: {str(e)}")

    return redirect('analytics:view_suggestions')


# =============================================================================
# API ENDPOINTS
# =============================================================================

@login_required
@require_http_methods(["GET"])
def api_learning_status(request):
    """API endpoint to get current learning status."""
    active_session = LearningSession.objects.filter(status='RUNNING').first()

    if not active_session:
        return JsonResponse({'status': 'stopped', 'session': None})

    engine = LearningEngine()
    summary = engine.get_session_summary(active_session)

    return JsonResponse({
        'status': 'running',
        'session': summary
    })


@login_required
@require_http_methods(["GET"])
def api_performance_metrics(request):
    """API endpoint to get performance metrics."""
    session_id = request.GET.get('session_id')

    if session_id:
        session = get_object_or_404(LearningSession, id=session_id)
    else:
        session = LearningSession.objects.filter(status='RUNNING').first()

    if not session:
        return JsonResponse({'error': 'No active session'}, status=404)

    engine = LearningEngine()
    metrics = engine.calculate_metrics(session, time_period='last_30_days')

    return JsonResponse({'metrics': metrics})


def _safe_float(value, default=0.0):
    """Safely convert a value to float, returning default if None or invalid."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@login_required
@require_http_methods(["GET"])
def api_pnl_data(request):
    """
    API endpoint to get comprehensive P&L data for all accounts.

    Returns real-time P&L data at multiple levels:
    - Account-level summary
    - Position-level details
    - Strategy-level aggregation
    - Daily/Weekly/Monthly trends
    """
    from apps.accounts.models import BrokerAccount
    from apps.core.utils.pnl_aggregator import get_comprehensive_pnl_data
    from apps.core.utils.formatting import format_indian_currency, format_percentage

    # Get all active accounts
    accounts = BrokerAccount.objects.filter(is_active=True)

    # Optionally filter by specific account
    account_id = request.GET.get('account_id')
    if account_id:
        accounts = accounts.filter(id=account_id)

    all_accounts_data = []

    for account in accounts:
        try:
            # Get comprehensive P&L data
            pnl_data = get_comprehensive_pnl_data(account)

            # Format currency values for display
            account_summary = pnl_data['account_summary']
            account_summary['total_pnl_formatted'] = format_indian_currency(account_summary.get('total_pnl'))
            account_summary['realized_pnl_formatted'] = format_indian_currency(account_summary.get('realized_pnl'))
            account_summary['unrealized_pnl_formatted'] = format_indian_currency(account_summary.get('unrealized_pnl'))
            account_summary['todays_pnl_formatted'] = format_indian_currency(account_summary.get('todays_pnl'))
            account_summary['win_rate_formatted'] = format_percentage(_safe_float(account_summary.get('win_rate'), 0) / 100)

            # Format position data
            for pos in pnl_data['active_positions']:
                pos['pnl_formatted'] = format_indian_currency(pos.get('pnl'))
                pos['pnl_pct_formatted'] = format_percentage(_safe_float(pos.get('pnl_pct'), 0) / 100)
                pos['entry_price'] = _safe_float(pos.get('entry_price'))
                pos['current_price'] = _safe_float(pos.get('current_price'))
                pos['stop_loss'] = _safe_float(pos.get('stop_loss'))
                pos['target'] = _safe_float(pos.get('target'))
                pos['pnl'] = _safe_float(pos.get('pnl'))
                pos['margin_used'] = _safe_float(pos.get('margin_used'))

            for pos in pnl_data['recent_closed_positions']:
                pos['pnl_formatted'] = format_indian_currency(pos.get('pnl'))
                pos['pnl_pct_formatted'] = format_percentage(_safe_float(pos.get('pnl_pct'), 0) / 100)
                pos['entry_price'] = _safe_float(pos.get('entry_price'))
                pos['current_price'] = _safe_float(pos.get('current_price')) or None
                pos['stop_loss'] = _safe_float(pos.get('stop_loss'))
                pos['target'] = _safe_float(pos.get('target'))
                pos['pnl'] = _safe_float(pos.get('pnl'))
                pos['margin_used'] = _safe_float(pos.get('margin_used'))

            # Format strategy data
            for strategy in pnl_data['strategy_summary']:
                strategy['total_pnl_formatted'] = format_indian_currency(strategy.get('total_pnl'))
                strategy['realized_pnl_formatted'] = format_indian_currency(strategy.get('realized_pnl'))
                strategy['unrealized_pnl_formatted'] = format_indian_currency(strategy.get('unrealized_pnl'))
                strategy['win_rate_formatted'] = format_percentage(_safe_float(strategy.get('win_rate'), 0) / 100)
                strategy['total_pnl'] = _safe_float(strategy.get('total_pnl'))
                strategy['realized_pnl'] = _safe_float(strategy.get('realized_pnl'))
                strategy['unrealized_pnl'] = _safe_float(strategy.get('unrealized_pnl'))
                strategy['win_rate'] = _safe_float(strategy.get('win_rate'))

            # Convert Decimal to float for JSON serialization
            for dpnl in pnl_data['daily_pnl']:
                dpnl['realized_pnl'] = _safe_float(dpnl.get('realized_pnl'))
                dpnl['unrealized_pnl'] = _safe_float(dpnl.get('unrealized_pnl'))
                dpnl['total_pnl'] = _safe_float(dpnl.get('total_pnl'))
                dpnl['win_rate'] = _safe_float(dpnl.get('win_rate'))

            for wpnl in pnl_data['weekly_pnl']:
                wpnl['total_pnl'] = _safe_float(wpnl.get('total_pnl'))
                wpnl['win_rate'] = _safe_float(wpnl.get('win_rate'))
                wpnl['profit_factor'] = _safe_float(wpnl.get('profit_factor'))
                wpnl['sharpe_ratio'] = _safe_float(wpnl.get('sharpe_ratio')) or None

            for mpnl in pnl_data['monthly_pnl']:
                mpnl['total_pnl'] = _safe_float(mpnl.get('total_pnl'))
                mpnl['win_rate'] = _safe_float(mpnl.get('win_rate'))
                mpnl['profit_factor'] = _safe_float(mpnl.get('profit_factor'))
                mpnl['sharpe_ratio'] = _safe_float(mpnl.get('sharpe_ratio')) or None

            # Convert numeric account summary values to float
            for key in ['total_pnl', 'realized_pnl', 'unrealized_pnl', 'todays_pnl', 'todays_realized', 'win_rate', 'allocated_capital', 'available_capital']:
                if key in account_summary:
                    account_summary[key] = _safe_float(account_summary.get(key))

            all_accounts_data.append(pnl_data)

        except Exception as e:
            logger.error(f"Error fetching P&L data for account {account.account_name}: {e}")
            continue

    return JsonResponse({
        'success': True,
        'accounts': all_accounts_data,
        'timestamp': timezone.now().isoformat()
    }, safe=False)


# =============================================================================
# POSITION SYNC & DATA ENDPOINTS
# =============================================================================

@login_required
@require_http_methods(["POST"])
def api_sync_positions(request):
    """
    API endpoint to sync positions from brokers.
    Fetches fresh data from Kotak Neo and ICICI Breeze.
    """
    try:
        from apps.positions.services.position_sync import sync_positions_from_brokers

        clear_existing = request.POST.get('clear', 'false').lower() == 'true'
        results = sync_positions_from_brokers(clear_existing=clear_existing)

        return JsonResponse({
            'success': results['success'],
            'accounts_synced': results['accounts_synced'],
            'positions_created': results['positions_created'],
            'positions_updated': results['positions_updated'],
            'positions_closed': results['positions_closed'],
            'history_synced': results.get('history_synced', 0),
            'errors': results['errors'],
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_sync_positions: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_positions_data(request):
    """
    API endpoint to get all positions data organized by status.
    Returns: open positions, suggestions, trade history
    """
    try:
        from apps.positions.services.position_sync import get_position_summary
        from apps.core.constants import POSITION_SOURCE_SYSTEM
        from apps.core.utils.formatting import format_indian_currency

        summary = get_position_summary()

        # Format open positions
        open_positions = []
        for pos in summary['open_positions']:
            open_positions.append({
                'id': pos.id,
                'instrument': pos.instrument,
                'direction': pos.direction,
                'quantity': pos.quantity,
                'entry_price': float(pos.entry_price),
                'current_price': float(pos.current_price),
                'unrealized_pnl': float(pos.unrealized_pnl),
                'pnl_formatted': format_indian_currency(pos.unrealized_pnl),
                'entry_time': pos.entry_time.isoformat() if pos.entry_time else None,
                'account': pos.account.account_name if pos.account else None,
                'broker': pos.account.broker if pos.account else None,
                'source': pos.source,
                'last_synced': pos.last_synced_at.isoformat() if pos.last_synced_at else None,
            })

        # Format suggestions
        suggestions = []
        for pos in summary['suggestions']:
            suggestions.append({
                'id': pos.id,
                'instrument': pos.instrument,
                'direction': pos.direction,
                'quantity': pos.quantity,
                'entry_price': float(pos.entry_price),
                'stop_loss': float(pos.stop_loss) if pos.stop_loss else None,
                'target': float(pos.target) if pos.target else None,
                'confidence': float(pos.confidence) if pos.confidence else None,
                'reason': pos.suggestion_reason,
                'created_at': pos.created_at.isoformat(),
            })

        # Format trade history
        trade_history = []
        for pos in summary['trade_history']:
            trade_history.append({
                'id': pos.id,
                'instrument': pos.instrument,
                'direction': pos.direction,
                'quantity': pos.quantity,
                'entry_price': float(pos.entry_price),
                'exit_price': float(pos.exit_price) if pos.exit_price else None,
                'realized_pnl': float(pos.realized_pnl),
                'pnl_formatted': format_indian_currency(pos.realized_pnl),
                'entry_time': pos.entry_time.isoformat() if pos.entry_time else None,
                'exit_time': pos.exit_time.isoformat() if pos.exit_time else None,
                'exit_reason': pos.exit_reason,
                'account': pos.account.account_name if pos.account else None,
            })

        return JsonResponse({
            'success': True,
            'open_positions': open_positions,
            'suggestions': suggestions,
            'trade_history': trade_history,
            'counts': summary['counts'],
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_positions_data: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
