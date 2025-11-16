"""
Trading Views - Trade Suggestion Approval and Management
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
import logging

from apps.trading.models import TradeSuggestion, AutoTradeConfig, TradeSuggestionLog
from apps.positions.models import Position

logger = logging.getLogger(__name__)


@login_required
def pending_suggestions(request):
    """
    List all pending trade suggestions for current user
    """
    suggestions = TradeSuggestion.objects.filter(
        user=request.user,
        status__in=['PENDING', 'APPROVED', 'AUTO_APPROVED']
    ).order_by('-created_at')

    context = {
        'suggestions': suggestions,
        'total_pending': suggestions.filter(status='PENDING').count(),
        'total_approved': suggestions.filter(status__in=['APPROVED', 'AUTO_APPROVED']).count(),
    }

    return render(request, 'trading/suggestions_list.html', context)


@login_required
def suggestion_detail(request, suggestion_id):
    """
    Detailed view of a single trade suggestion with full reasoning
    Allows approval/rejection decision
    """
    suggestion = get_object_or_404(TradeSuggestion, id=suggestion_id, user=request.user)

    context = {
        'suggestion': suggestion,
        'reasoning': suggestion.algorithm_reasoning,
        'position_details': suggestion.position_details,
        'is_pending': suggestion.is_pending,
        'is_approved': suggestion.is_approved,
    }

    return render(request, 'trading/suggestion_detail.html', context)


@login_required
@require_POST
def approve_suggestion(request, suggestion_id):
    """
    Approve a trade suggestion and proceed to execution
    """
    suggestion = get_object_or_404(TradeSuggestion, id=suggestion_id, user=request.user)

    if not suggestion.is_pending:
        messages.warning(request, "This suggestion has already been processed")
        return redirect('trading:pending_suggestions')

    try:
        # Update suggestion status
        suggestion.status = 'APPROVED'
        suggestion.approved_by = request.user
        suggestion.approval_timestamp = timezone.now()
        suggestion.save()

        # Log the approval
        TradeSuggestionLog.objects.create(
            suggestion=suggestion,
            action='APPROVED',
            user=request.user,
            notes="Manually approved by user"
        )

        messages.success(request, f"Trade suggestion approved! Ready to execute {suggestion.instrument} {suggestion.direction}")

        # Redirect to execution confirmation
        return redirect('trading:execute_suggestion', suggestion_id=suggestion.id)

    except Exception as e:
        logger.error(f"Error approving suggestion {suggestion_id}: {e}", exc_info=True)
        messages.error(request, "Error approving suggestion. Please try again.")
        return redirect('trading:suggestion_detail', suggestion_id=suggestion.id)


@login_required
@require_POST
def reject_suggestion(request, suggestion_id):
    """
    Reject a trade suggestion
    """
    suggestion = get_object_or_404(TradeSuggestion, id=suggestion_id, user=request.user)

    if not suggestion.is_pending:
        messages.warning(request, "This suggestion has already been processed")
        return redirect('trading:pending_suggestions')

    try:
        rejection_reason = request.POST.get('reason', 'No reason provided')

        # Update suggestion status
        suggestion.status = 'REJECTED'
        suggestion.approval_notes = rejection_reason
        suggestion.save()

        # Log the rejection
        TradeSuggestionLog.objects.create(
            suggestion=suggestion,
            action='REJECTED',
            user=request.user,
            notes=rejection_reason
        )

        messages.info(request, "Trade suggestion rejected")

        return redirect('trading:pending_suggestions')

    except Exception as e:
        logger.error(f"Error rejecting suggestion {suggestion_id}: {e}", exc_info=True)
        messages.error(request, "Error rejecting suggestion. Please try again.")
        return redirect('trading:suggestion_detail', suggestion_id=suggestion.id)


@login_required
def execute_suggestion(request, suggestion_id):
    """
    Confirmation page before executing an approved suggestion
    Shows final trading details
    """
    suggestion = get_object_or_404(TradeSuggestion, id=suggestion_id, user=request.user)

    if not suggestion.is_approved:
        messages.warning(request, "Suggestion must be approved before execution")
        return redirect('trading:suggestion_detail', suggestion_id=suggestion.id)

    context = {
        'suggestion': suggestion,
        'position_details': suggestion.position_details,
    }

    return render(request, 'trading/execute_confirmation.html', context)


@login_required
@require_POST
def confirm_execution(request, suggestion_id):
    """
    Final confirmation to execute the trade
    Creates Position and updates suggestion status
    """
    suggestion = get_object_or_404(TradeSuggestion, id=suggestion_id, user=request.user)

    if not suggestion.is_approved:
        messages.warning(request, "Suggestion is not approved")
        return redirect('trading:suggestion_detail', suggestion_id=suggestion.id)

    try:
        from apps.accounts.models import BrokerAccount
        from apps.orders.services.order_manager import OrderManager

        # Get user's active broker account
        account = BrokerAccount.objects.filter(user=request.user, is_active=True).first()
        if not account:
            messages.error(request, "No active broker account found")
            return redirect('trading:suggestion_detail', suggestion_id=suggestion.id)

        position_details = suggestion.position_details

        # Create Position
        position = Position.objects.create(
            user=request.user,
            account=account,
            instrument=suggestion.instrument,
            direction=suggestion.direction,
            entry_price=position_details.get('entry_price'),
            current_price=position_details.get('entry_price'),
            quantity=position_details.get('quantity', 1),
            lot_size=position_details.get('lot_size', 1),
            stop_loss=position_details.get('stop_loss'),
            target=position_details.get('target'),
            margin_used=position_details.get('margin_required', 0),
            status='ACTIVE',
        )

        # Update suggestion
        suggestion.status = 'EXECUTED'
        suggestion.executed_position = position
        suggestion.save()

        # Log execution
        TradeSuggestionLog.objects.create(
            suggestion=suggestion,
            action='EXECUTED',
            user=request.user,
            notes=f"Position created: {position.id}"
        )

        messages.success(request, f"Trade executed successfully! Position {position.id} created")

        # Redirect to new position
        return redirect('positions:detail', position_id=position.id)

    except Exception as e:
        logger.error(f"Error executing suggestion {suggestion_id}: {e}", exc_info=True)
        messages.error(request, f"Error executing trade: {str(e)}")
        return redirect('trading:execute_suggestion', suggestion_id=suggestion.id)


@login_required
def auto_trade_config(request):
    """
    View and manage auto-trade configuration
    """
    from apps.strategies.models import StrategyConfig

    strategies = StrategyConfig.objects.all()
    configs = {}

    for strategy_obj in strategies:
        config, created = AutoTradeConfig.objects.get_or_create(
            user=request.user,
            strategy=strategy_obj.strategy_code if hasattr(strategy_obj, 'strategy_code') else ''
        )
        configs[strategy_obj.name] = config

    if request.method == 'POST':
        strategy_code = request.POST.get('strategy')
        is_enabled = request.POST.get('is_enabled') == 'on'
        threshold = request.POST.get('auto_approve_threshold', 95)

        try:
            config, _ = AutoTradeConfig.objects.get_or_create(
                user=request.user,
                strategy=strategy_code
            )
            config.is_enabled = is_enabled
            config.auto_approve_threshold = threshold
            config.save()

            messages.success(request, f"Auto-trade configuration updated")
            return redirect('trading:auto_trade_config')
        except Exception as e:
            messages.error(request, f"Error updating configuration: {str(e)}")

    context = {
        'configs': configs,
    }

    return render(request, 'trading/auto_trade_config.html', context)


@login_required
def suggestion_history(request):
    """
    View history of all trade suggestions and decisions
    """
    suggestions = TradeSuggestion.objects.filter(user=request.user).order_by('-created_at')

    # Filter by status if requested
    status_filter = request.GET.get('status')
    if status_filter:
        suggestions = suggestions.filter(status=status_filter)

    context = {
        'suggestions': suggestions,
        'status_choices': TradeSuggestion.STATUS_CHOICES,
    }

    return render(request, 'trading/suggestion_history.html', context)
