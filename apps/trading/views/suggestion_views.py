"""
Suggestion Views - Trade Suggestion Management

Handles the complete lifecycle of trade suggestions:
- List pending suggestions
- View detailed suggestion with reasoning
- Approve/reject suggestions
- Execute approved suggestions
- View suggestion history
- Export suggestions to CSV
- Configure auto-trade settings

Extracted from apps/trading/views.py as part of refactoring.
Business logic will be moved to service layer in Phase 2.2.
"""

import csv
import logging
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from apps.trading.models import TradeSuggestion, AutoTradeConfig, TradeSuggestionLog
from apps.positions.models import Position
from apps.accounts.models import BrokerAccount
from apps.strategies.models import StrategyConfig

logger = logging.getLogger(__name__)


@login_required
def pending_suggestions(request):
    """
    List all pending trade suggestions for current user.

    Displays suggestions that need user decision (PENDING) or have been
    approved but not yet executed (APPROVED, AUTO_APPROVED).

    Template: trading/suggestions_list.html

    Context:
        suggestions: QuerySet of TradeSuggestion objects
        total_pending: Count of PENDING suggestions
        total_approved: Count of APPROVED + AUTO_APPROVED suggestions

    Returns:
        HttpResponse: Rendered template with suggestion list
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
    Detailed view of a single trade suggestion.

    Shows complete analysis, reasoning, position details, and action buttons
    for approval/rejection.

    Template: trading/suggestion_detail.html

    Args:
        suggestion_id: ID of the TradeSuggestion

    Context:
        suggestion: TradeSuggestion object
        reasoning: Algorithm reasoning/analysis
        position_details: Position sizing and risk details
        is_pending: Boolean - can be approved/rejected
        is_approved: Boolean - ready for execution

    Returns:
        HttpResponse: Rendered suggestion detail page

    Raises:
        Http404: If suggestion doesn't exist or doesn't belong to user
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
    Approve a trade suggestion and proceed to execution confirmation.

    Updates suggestion status to APPROVED and logs the approval action.
    Redirects to execution confirmation page.

    Args:
        suggestion_id: ID of the TradeSuggestion to approve

    Returns:
        HttpResponseRedirect: To execution page if successful, detail page on error

    Side Effects:
        - Updates TradeSuggestion.status to 'APPROVED'
        - Sets approval_timestamp
        - Creates TradeSuggestionLog entry

    Note:
        Only PENDING suggestions can be approved. Already processed
        suggestions will show a warning and redirect.
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

        messages.success(
            request,
            f"Trade suggestion approved! Ready to execute {suggestion.instrument} {suggestion.direction}"
        )

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
    Reject a trade suggestion with optional reason.

    Updates suggestion status to REJECTED and logs the rejection.

    Args:
        suggestion_id: ID of the TradeSuggestion to reject

    POST Parameters:
        reason: Optional rejection reason (default: "No reason provided")

    Returns:
        HttpResponseRedirect: To pending list if successful, detail page on error

    Side Effects:
        - Updates TradeSuggestion.status to 'REJECTED'
        - Sets approval_notes with rejection reason
        - Creates TradeSuggestionLog entry

    Note:
        Only PENDING suggestions can be rejected.
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
    Confirmation page before executing an approved suggestion.

    Shows final trading details including entry price, stop loss, target,
    margin requirements, and lot size. User must click final confirmation
    to actually execute the trade.

    Template: trading/execute_confirmation.html

    Args:
        suggestion_id: ID of the approved TradeSuggestion

    Context:
        suggestion: TradeSuggestion object
        position_details: Dict with execution details

    Returns:
        HttpResponse: Execution confirmation page

    Note:
        Only APPROVED suggestions can be executed. Redirects to detail
        page if suggestion is not approved.
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
    Final confirmation to execute the trade.

    Creates a Position record and updates suggestion status to EXECUTED.
    This is the actual trade execution step.

    Args:
        suggestion_id: ID of the approved TradeSuggestion to execute

    Returns:
        HttpResponseRedirect: To new position detail page if successful

    Side Effects:
        - Creates new Position object
        - Updates TradeSuggestion.status to 'EXECUTED'
        - Links position to suggestion
        - Creates TradeSuggestionLog entry

    Raises:
        Error messages if:
        - Suggestion not approved
        - No active broker account found
        - Position creation fails

    Note:
        In Phase 2.2, actual broker order placement will be added via
        OrderManager service.
    """
    suggestion = get_object_or_404(TradeSuggestion, id=suggestion_id, user=request.user)

    if not suggestion.is_approved:
        messages.warning(request, "Suggestion is not approved")
        return redirect('trading:suggestion_detail', suggestion_id=suggestion.id)

    try:
        # Get user's active broker account
        account = BrokerAccount.objects.filter(user=request.user, is_active=True).first()
        if not account:
            messages.error(request, "No active broker account found")
            return redirect('trading:suggestion_detail', suggestion_id=suggestion.id)

        position_details = suggestion.position_details

        # Create Position (actual broker order placement will be in Phase 2.2)
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
    View and manage auto-trade configuration.

    Allows users to enable/disable auto-trading per strategy and set
    auto-approval thresholds.

    Template: trading/auto_trade_config.html

    Context:
        configs: Dict of {strategy_name: AutoTradeConfig} mappings

    POST Parameters:
        strategy: Strategy code
        is_enabled: Boolean (checkbox 'on' = True)
        auto_approve_threshold: Integer (0-100)

    Returns:
        HttpResponse: Configuration page
        HttpResponseRedirect: After POST to same page

    Note:
        Creates AutoTradeConfig records if they don't exist for each strategy.
    """
    strategies = StrategyConfig.objects.all()
    configs = {}

    # Get or create config for each strategy
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

            messages.success(request, "Auto-trade configuration updated")
            return redirect('trading:auto_trade_config')

        except Exception as e:
            logger.error(f"Error updating auto-trade config: {e}", exc_info=True)
            messages.error(request, f"Error updating configuration: {str(e)}")

    context = {
        'configs': configs,
    }

    return render(request, 'trading/auto_trade_config.html', context)


@login_required
def suggestion_history(request):
    """
    View history of all trade suggestions with pagination and filters.

    Displays complete history of suggestions with filtering by:
    - Status (PENDING, APPROVED, REJECTED, EXECUTED, etc.)
    - Strategy (which algorithm generated the suggestion)
    - Date range (from/to dates)

    Template: trading/suggestion_history.html

    GET Parameters:
        status: Filter by status
        strategy: Filter by strategy
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        page: Page number for pagination

    Context:
        suggestions: Paginated suggestions (50 per page)
        status_choices: Available status filters
        strategy_choices: Available strategy filters
        total_count: Total matching suggestions
        status_filter: Current status filter
        strategy_filter: Current strategy filter
        date_from: Current from date filter
        date_to: Current to date filter

    Returns:
        HttpResponse: Suggestion history page with filters
    """
    suggestions = TradeSuggestion.objects.filter(user=request.user).order_by('-created_at')

    # Apply filters
    status_filter = request.GET.get('status')
    if status_filter:
        suggestions = suggestions.filter(status=status_filter)

    strategy_filter = request.GET.get('strategy')
    if strategy_filter:
        suggestions = suggestions.filter(strategy=strategy_filter)

    # Date range filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            suggestions = suggestions.filter(created_at__date__gte=date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            suggestions = suggestions.filter(created_at__date__lte=date_to_obj)
        except ValueError:
            pass

    # Pagination (50 per page)
    paginator = Paginator(suggestions, 50)
    page = request.GET.get('page')

    try:
        suggestions_page = paginator.page(page)
    except PageNotAnInteger:
        # First page if page is not an integer
        suggestions_page = paginator.page(1)
    except EmptyPage:
        # Last page if page is out of range
        suggestions_page = paginator.page(paginator.num_pages)

    context = {
        'suggestions': suggestions_page,
        'status_choices': TradeSuggestion.STATUS_CHOICES,
        'strategy_choices': TradeSuggestion.STRATEGY_CHOICES,
        'total_count': suggestions.count(),
        'status_filter': status_filter,
        'strategy_filter': strategy_filter,
        'date_from': date_from,
        'date_to': date_to,
    }

    return render(request, 'trading/suggestion_history.html', context)


@login_required
def export_suggestions_csv(request):
    """
    Export trade suggestions history to CSV file.

    Applies same filters as suggestion_history view and exports
    matching suggestions to downloadable CSV file.

    GET Parameters:
        status: Filter by status
        strategy: Filter by strategy
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)

    CSV Columns:
        ID, Created At, Strategy, Instrument, Direction, Type, Status,
        Approved By, Approval Timestamp, Executed At, Auto Trade,
        Entry Price, Stop Loss, Target, Margin Required

    Returns:
        HttpResponse: CSV file download with appropriate headers

    File Naming:
        trade_suggestions_YYYYMMDD_HHMMSS.csv
    """
    # Create HttpResponse with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="trade_suggestions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    )

    writer = csv.writer(response)

    # Write header row
    writer.writerow([
        'ID', 'Created At', 'Strategy', 'Instrument', 'Direction', 'Type',
        'Status', 'Approved By', 'Approval Timestamp', 'Executed At',
        'Auto Trade', 'Entry Price', 'Stop Loss', 'Target', 'Margin Required'
    ])

    # Get filtered suggestions (same logic as history view)
    suggestions = TradeSuggestion.objects.filter(user=request.user).order_by('-created_at')

    # Apply filters
    status_filter = request.GET.get('status')
    if status_filter:
        suggestions = suggestions.filter(status=status_filter)

    strategy_filter = request.GET.get('strategy')
    if strategy_filter:
        suggestions = suggestions.filter(strategy=strategy_filter)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            suggestions = suggestions.filter(created_at__date__gte=date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            suggestions = suggestions.filter(created_at__date__lte=date_to_obj)
        except ValueError:
            pass

    # Write data rows
    for suggestion in suggestions:
        position_details = suggestion.position_details or {}

        writer.writerow([
            suggestion.id,
            suggestion.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            suggestion.get_strategy_display(),
            suggestion.instrument,
            suggestion.direction,
            suggestion.suggestion_type,
            suggestion.get_status_display(),
            suggestion.approved_by.get_full_name() if suggestion.approved_by else '',
            suggestion.approval_timestamp.strftime('%Y-%m-%d %H:%M:%S') if suggestion.approval_timestamp else '',
            suggestion.executed_at.strftime('%Y-%m-%d %H:%M:%S') if suggestion.executed_at else '',
            'Yes' if suggestion.is_auto_trade else 'No',
            position_details.get('entry_price', ''),
            position_details.get('stop_loss', ''),
            position_details.get('target', ''),
            position_details.get('margin_required', '')
        ])

    logger.info(
        f"Exported {suggestions.count()} trade suggestions to CSV for user {request.user.username}"
    )

    return response
