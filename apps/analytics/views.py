"""
Analytics and Learning System Views for mCube Trading System

Includes:
- Learning control views
- Pattern & suggestion views
- API endpoints for P&L and positions
- Dashboard API endpoints for visualization
- ML insights API endpoints
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal
from datetime import datetime

from apps.analytics.models import (
    LearningSession,
    LearningPattern,
    ParameterAdjustment,
    TradePerformance,
    PerformanceMetric,
)
from apps.analytics.services.learning_engine import LearningEngine
from apps.analytics.services.dashboard_service import get_dashboard_service
from apps.positions.models import Position
from apps.accounts.models import BrokerAccount

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
@require_http_methods(["GET"])
def api_positions_data(request):
    """
    API endpoint to get current positions data organized by status.
    Returns: open positions and suggestions.
    Trade history is now sourced from CSV imports (BrokerContractPnL).
    """
    try:
        from apps.positions.services.position_sync import get_position_summary
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

        return JsonResponse({
            'success': True,
            'open_positions': open_positions,
            'suggestions': suggestions,
            'counts': {
                'open': summary['counts']['open'],
                'suggested': summary['counts']['suggested'],
            },
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_positions_data: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# DASHBOARD API ENDPOINTS
# =============================================================================

@login_required
@require_http_methods(["GET"])
def api_dashboard_summary(request):
    """
    API endpoint to get dashboard summary metrics.

    Query params:
    - account_id: Optional specific account ID
    - period: Time period (1D, 1W, 1M, 3M, 6M, 1Y, FY, YTD, ALL)
    """
    try:
        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        period = request.GET.get('period', 'FY')

        service = get_dashboard_service()
        summary = service.get_summary_metrics(request.user, account, period)

        return JsonResponse({
            'success': True,
            'data': summary,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_dashboard_summary: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_pnl_chart_data(request):
    """
    API endpoint to get P&L chart data.

    Query params:
    - account_id: Optional specific account ID
    - period: Time period (1D, 1W, 1M, 3M, 6M, 1Y, FY)
    - granularity: Data granularity (daily, weekly, monthly)
    """
    try:
        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        period = request.GET.get('period', '1M')
        granularity = request.GET.get('granularity', 'daily')

        service = get_dashboard_service()
        chart_data = service.get_pnl_chart_data(request.user, account, period, granularity)

        return JsonResponse({
            'success': True,
            'data': chart_data,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_pnl_chart_data: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_cumulative_returns(request):
    """
    API endpoint to get cumulative returns / equity curve data.

    Query params:
    - account_id: Optional specific account ID
    - period: Time period
    """
    try:
        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        period = request.GET.get('period', 'FY')

        service = get_dashboard_service()
        returns_data = service.get_cumulative_returns(request.user, account, period)

        return JsonResponse({
            'success': True,
            'data': returns_data,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_cumulative_returns: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_win_loss_distribution(request):
    """
    API endpoint to get win/loss distribution data.

    Query params:
    - account_id: Optional specific account ID
    - period: Time period
    """
    try:
        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        period = request.GET.get('period', 'FY')

        service = get_dashboard_service()
        distribution = service.get_win_loss_distribution(request.user, account, period)

        return JsonResponse({
            'success': True,
            'data': distribution,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_win_loss_distribution: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_strategy_performance(request):
    """
    API endpoint to get performance by strategy.

    Query params:
    - account_id: Optional specific account ID
    - period: Time period
    """
    try:
        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        period = request.GET.get('period', 'FY')

        service = get_dashboard_service()
        strategy_data = service.get_strategy_performance(request.user, account, period)

        return JsonResponse({
            'success': True,
            'data': strategy_data,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_strategy_performance: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_drawdown_chart(request):
    """
    API endpoint to get drawdown chart data.

    Query params:
    - account_id: Optional specific account ID
    - period: Time period
    """
    try:
        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        period = request.GET.get('period', 'FY')

        service = get_dashboard_service()
        returns_data = service.get_cumulative_returns(request.user, account, period)

        # Extract drawdown data
        drawdown_data = {
            'labels': returns_data.get('labels', []),
            'drawdown_pct': returns_data.get('drawdown_pct', []),
        }

        return JsonResponse({
            'success': True,
            'data': drawdown_data,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_drawdown_chart: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_performance_heatmap(request):
    """
    API endpoint to get performance heatmap data (by day/hour).

    Query params:
    - account_id: Optional specific account ID
    - period: Time period
    """
    try:
        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        period = request.GET.get('period', 'FY')

        service = get_dashboard_service()
        heatmap_data = service.get_performance_heatmap(request.user, account, period)

        return JsonResponse({
            'success': True,
            'data': heatmap_data,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_performance_heatmap: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_best_worst_trades(request):
    """
    API endpoint to get best and worst trades.

    Query params:
    - account_id: Optional specific account ID
    - limit: Number of trades to return (default 10)
    """
    try:
        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        limit = int(request.GET.get('limit', 10))

        service = get_dashboard_service()
        trades_data = service.get_best_worst_trades(request.user, account, limit)

        return JsonResponse({
            'success': True,
            'data': trades_data,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_best_worst_trades: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_benchmark_comparison(request):
    """
    API endpoint to get benchmark comparison data.

    Query params:
    - account_id: Optional specific account ID
    - benchmark: Benchmark to compare (NIFTY50, BANKNIFTY)
    - period: Time period
    """
    try:
        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        benchmark = request.GET.get('benchmark', 'NIFTY50')
        period = request.GET.get('period', 'FY')

        service = get_dashboard_service()
        comparison_data = service.get_benchmark_comparison(request.user, account, benchmark, period)

        return JsonResponse({
            'success': True,
            'data': comparison_data,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_benchmark_comparison: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# ML INSIGHTS API ENDPOINTS
# =============================================================================

@login_required
@require_http_methods(["GET"])
def api_decision_patterns(request):
    """
    API endpoint to get user decision pattern analysis.

    Query params:
    - period: Time period
    """
    try:
        period = request.GET.get('period', 'FY')

        service = get_dashboard_service()
        patterns_data = service.get_decision_patterns(request.user, period)

        return JsonResponse({
            'success': True,
            'data': patterns_data,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_decision_patterns: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_recommendation_accuracy(request):
    """
    API endpoint to get recommendation accuracy analysis.

    Query params:
    - period: Time period
    """
    try:
        period = request.GET.get('period', 'FY')

        service = get_dashboard_service()
        accuracy_data = service.get_recommendation_accuracy(request.user, period)

        return JsonResponse({
            'success': True,
            'data': accuracy_data,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_recommendation_accuracy: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# EXPORT API ENDPOINTS
# =============================================================================

@login_required
@require_http_methods(["GET"])
def api_export_trades(request):
    """
    API endpoint to export trades data.

    Query params:
    - from_date: Start date (YYYY-MM-DD)
    - to_date: End date (YYYY-MM-DD)
    - format: Export format (json, csv)
    """
    try:
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        export_format = request.GET.get('format', 'json')

        if not from_date or not to_date:
            return JsonResponse({
                'success': False,
                'error': 'from_date and to_date are required'
            }, status=400)

        from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date = datetime.strptime(to_date, '%Y-%m-%d').date()

        from apps.trading.models import TakenTrade

        trades = TakenTrade.objects.filter(
            user=request.user,
            status='CLOSED',
            closed_at__date__gte=from_date,
            closed_at__date__lte=to_date,
        ).values(
            'id', 'instrument', 'strategy', 'direction', 'trade_type',
            'entry_price', 'exit_price', 'quantity', 'net_pnl', 'outcome',
            'taken_at', 'closed_at'
        )

        trades_list = list(trades)

        # Convert Decimal and datetime for JSON
        for trade in trades_list:
            for key, value in trade.items():
                if isinstance(value, Decimal):
                    trade[key] = float(value)
                elif isinstance(value, datetime):
                    trade[key] = value.isoformat()

        if export_format == 'csv':
            import csv
            from django.http import HttpResponse

            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="trades_{from_date}_{to_date}.csv"'

            if trades_list:
                writer = csv.DictWriter(response, fieldnames=trades_list[0].keys())
                writer.writeheader()
                writer.writerows(trades_list)

            return response

        return JsonResponse({
            'success': True,
            'data': trades_list,
            'count': len(trades_list),
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_export_trades: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["GET"])
def api_export_ml_data(request):
    """
    API endpoint to export ML training data.

    Query params:
    - from_date: Start date (YYYY-MM-DD)
    - to_date: End date (YYYY-MM-DD)
    - format: Export format (json, parquet)
    """
    try:
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        export_format = request.GET.get('format', 'json')

        if not from_date or not to_date:
            return JsonResponse({
                'success': False,
                'error': 'from_date and to_date are required'
            }, status=400)

        from_date = datetime.strptime(from_date, '%Y-%m-%d')
        to_date = datetime.strptime(to_date, '%Y-%m-%d')

        from apps.analytics.services.ml_data_collector import export_training_data

        if export_format == 'parquet':
            filepath = export_training_data(from_date, to_date, output_format='parquet')
            return JsonResponse({
                'success': True,
                'filepath': filepath,
                'message': f'ML data exported to {filepath}',
                'timestamp': timezone.now().isoformat()
            })
        else:
            data = export_training_data(from_date, to_date, output_format='dict')
            return JsonResponse({
                'success': True,
                'data': data,
                'count': len(data),
                'timestamp': timezone.now().isoformat()
            })

    except Exception as e:
        logger.error(f"Error in api_export_ml_data: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# DASHBOARD VIEW
# =============================================================================

@login_required
# =============================================================================
# FY TRADE ANALYTICS API ENDPOINTS
# =============================================================================

@login_required
@require_http_methods(["GET"])
def api_fy_monthly_performance(request):
    """
    API endpoint to get FY monthly performance breakdown.
    Separates Futures and Options P&L.

    Query params:
    - account_id: Optional specific account ID
    """
    try:
        from apps.analytics.services.fy_trade_analytics import get_fy_analytics

        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        analytics = get_fy_analytics()
        performance = analytics.get_monthly_performance(account)

        return JsonResponse({
            'success': True,
            'data': performance,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_fy_monthly_performance: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_fy_broker_breakdown(request):
    """
    API endpoint to get FY performance by broker.
    """
    try:
        from apps.analytics.services.fy_trade_analytics import get_fy_analytics

        analytics = get_fy_analytics()
        breakdown = analytics.get_broker_breakdown()

        return JsonResponse({
            'success': True,
            'data': breakdown,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_fy_broker_breakdown: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# BROKER TRADE ANALYTICS API ENDPOINTS
# =============================================================================

@login_required
@require_http_methods(["GET"])
def api_broker_trade_summary(request):
    """
    API endpoint to get trade summary from actual broker trade history.

    Query params:
    - account_id: Optional specific account ID
    - from_date: Start date (YYYY-MM-DD)
    - to_date: End date (YYYY-MM-DD)
    """
    try:
        from apps.analytics.services.broker_trade_analytics import get_broker_analytics
        from datetime import datetime

        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        from_date = None
        to_date = None
        if request.GET.get('from_date'):
            from_date = datetime.strptime(request.GET['from_date'], '%Y-%m-%d').date()
        if request.GET.get('to_date'):
            to_date = datetime.strptime(request.GET['to_date'], '%Y-%m-%d').date()

        analytics = get_broker_analytics()
        summary = analytics.get_trade_summary(account, from_date, to_date)

        return JsonResponse({
            'success': True,
            'data': summary,
            'source': 'broker_api',
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_broker_trade_summary: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_broker_daily_pnl(request):
    """
    API endpoint to get daily P&L from broker trade history.

    Query params:
    - account_id: Optional specific account ID
    - from_date: Start date (YYYY-MM-DD)
    - to_date: End date (YYYY-MM-DD)
    """
    try:
        from apps.analytics.services.broker_trade_analytics import get_broker_analytics
        from datetime import datetime

        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        from_date = None
        to_date = None
        if request.GET.get('from_date'):
            from_date = datetime.strptime(request.GET['from_date'], '%Y-%m-%d').date()
        if request.GET.get('to_date'):
            to_date = datetime.strptime(request.GET['to_date'], '%Y-%m-%d').date()

        analytics = get_broker_analytics()
        daily_data = analytics.get_daily_pnl(account, from_date, to_date)

        # Format for chart
        labels = [d['date'].strftime('%Y-%m-%d') if d['date'] else '' for d in daily_data]
        pnl_values = [d['pnl'] for d in daily_data]

        return JsonResponse({
            'success': True,
            'data': {
                'labels': labels,
                'pnl': pnl_values,
                'daily_data': daily_data,
            },
            'source': 'broker_api',
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_broker_daily_pnl: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_broker_symbol_performance(request):
    """
    API endpoint to get performance by symbol from broker trade history.

    Query params:
    - account_id: Optional specific account ID
    - from_date: Start date (YYYY-MM-DD)
    - to_date: End date (YYYY-MM-DD)
    - limit: Number of symbols to return (default 20)
    """
    try:
        from apps.analytics.services.broker_trade_analytics import get_broker_analytics
        from datetime import datetime

        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        from_date = None
        to_date = None
        if request.GET.get('from_date'):
            from_date = datetime.strptime(request.GET['from_date'], '%Y-%m-%d').date()
        if request.GET.get('to_date'):
            to_date = datetime.strptime(request.GET['to_date'], '%Y-%m-%d').date()

        limit = int(request.GET.get('limit', 20))

        analytics = get_broker_analytics()
        symbol_data = analytics.get_symbol_performance(account, from_date, to_date, limit)

        return JsonResponse({
            'success': True,
            'data': symbol_data,
            'source': 'broker_api',
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_broker_symbol_performance: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_broker_fy_summary(request):
    """
    API endpoint to get financial year summary from broker trade history.

    Query params:
    - account_id: Optional specific account ID
    - fy_year: Financial year start (e.g., 2024 for FY 2024-25)
    """
    try:
        from apps.analytics.services.broker_trade_analytics import get_broker_analytics

        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        fy_year = None
        if request.GET.get('fy_year'):
            fy_year = int(request.GET['fy_year'])

        analytics = get_broker_analytics()
        fy_data = analytics.get_fy_summary(account, fy_year)

        return JsonResponse({
            'success': True,
            'data': fy_data,
            'source': 'broker_api',
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_broker_fy_summary: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_broker_monthly_summary(request):
    """
    API endpoint to get monthly summary from broker trade history.

    Query params:
    - account_id: Optional specific account ID
    - from_date: Start date (YYYY-MM-DD)
    - to_date: End date (YYYY-MM-DD)
    """
    try:
        from apps.analytics.services.broker_trade_analytics import get_broker_analytics
        from datetime import datetime

        account = None
        account_id = request.GET.get('account_id')
        if account_id:
            account = get_object_or_404(BrokerAccount, id=account_id)

        from_date = None
        to_date = None
        if request.GET.get('from_date'):
            from_date = datetime.strptime(request.GET['from_date'], '%Y-%m-%d').date()
        if request.GET.get('to_date'):
            to_date = datetime.strptime(request.GET['to_date'], '%Y-%m-%d').date()

        analytics = get_broker_analytics()
        monthly_data = analytics.get_monthly_summary(account, from_date, to_date)

        return JsonResponse({
            'success': True,
            'data': monthly_data,
            'source': 'broker_api',
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in api_broker_monthly_summary: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# DASHBOARD VIEW
# =============================================================================

@login_required
def dashboard(request):
    """
    Main analytics dashboard view.
    """
    # Get accounts for dropdown
    accounts = BrokerAccount.objects.filter(is_active=True)

    # Get broker trade sync status
    from apps.brokers.models import BrokerTradeHistory
    trade_count = BrokerTradeHistory.objects.count()
    last_trade = BrokerTradeHistory.objects.order_by('-trade_date').first()

    context = {
        'accounts': accounts,
        'default_period': 'FY',
        'broker_trade_count': trade_count,
        'last_broker_trade_date': last_trade.trade_date if last_trade else None,
    }

    return render(request, 'analytics/dashboard.html', context)

