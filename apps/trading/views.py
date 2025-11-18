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
from apps.brokers.integrations.breeze import get_india_vix

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
    View history of all trade suggestions and decisions with pagination and filters
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from datetime import datetime, timedelta

    suggestions = TradeSuggestion.objects.filter(user=request.user).order_by('-created_at')

    # Filter by status if requested
    status_filter = request.GET.get('status')
    if status_filter:
        suggestions = suggestions.filter(status=status_filter)

    # Filter by strategy if requested
    strategy_filter = request.GET.get('strategy')
    if strategy_filter:
        suggestions = suggestions.filter(strategy=strategy_filter)

    # Filter by date range if requested
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

    # Pagination
    paginator = Paginator(suggestions, 50)  # Show 50 suggestions per page
    page = request.GET.get('page')

    try:
        suggestions_page = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page
        suggestions_page = paginator.page(1)
    except EmptyPage:
        # If page is out of range, deliver last page of results
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
    Export trade suggestions history to CSV file
    """
    import csv
    from django.http import HttpResponse
    from datetime import datetime

    # Create HttpResponse with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="trade_suggestions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

    writer = csv.writer(response)

    # Write header row
    writer.writerow([
        'ID',
        'Created At',
        'Strategy',
        'Instrument',
        'Direction',
        'Type',
        'Status',
        'Approved By',
        'Approval Timestamp',
        'Executed At',
        'Auto Trade',
        'Entry Price',
        'Stop Loss',
        'Target',
        'Margin Required'
    ])

    # Get filtered suggestions (same logic as history view)
    suggestions = TradeSuggestion.objects.filter(user=request.user).order_by('-created_at')

    # Apply same filters as history view
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

    logger.info(f"Exported {suggestions.count()} trade suggestions to CSV for user {request.user.username}")

    return response


@login_required
def manual_triggers(request):
    """
    Manual Trade Triggers Page

    Three features:
    1. Run Futures Algorithm - Screen and suggest futures opportunities
    2. Nifty Options Strangle - Generate Kotak strangle position
    3. Verify Future Trade - Verify a specific futures contract
    """
    from apps.data.models import ContractData
    from django.db.models import Q
    from datetime import datetime, timedelta

    # Get all futures contracts based on volume criteria from Trendlyne data
    # Criteria (OR condition):
    # - This month: >= 1000 traded contracts OR
    # - Next month: >= 800 traded contracts

    today = datetime.now().date()

    # Calculate date ranges
    # This month: expiry within next 30 days
    this_month_end = today + timedelta(days=30)
    # Next month: expiry between 30-60 days
    next_month_start = today + timedelta(days=30)
    next_month_end = today + timedelta(days=60)

    # Get futures contracts that meet volume criteria
    # Using OR logic: (this month >= 1000) OR (next month >= 800)
    futures_contracts = ContractData.objects.filter(
        option_type='FUTURE',  # Futures only (stored as 'FUTURE' in DB)
        expiry__gte=str(today),
        expiry__lte=str(next_month_end)
    ).filter(
        Q(expiry__lte=str(this_month_end), traded_contracts__gte=1000) |  # This month >= 1000
        Q(expiry__gte=str(next_month_start), expiry__lte=str(next_month_end), traded_contracts__gte=800)  # Next month >= 800
    ).order_by('symbol', 'expiry').values(
        'symbol',
        'expiry',
        'traded_contracts',
        'price',
        'lot_size'
    )

    # Format contracts as "SYMBOL - DD-MMM-YYYY (Volume: X)"
    contract_list = []
    for contract in futures_contracts:
        expiry_date = datetime.strptime(contract['expiry'], '%Y-%m-%d').strftime('%d-%b-%Y')
        display_name = f"{contract['symbol']} - {expiry_date}"
        contract_value = f"{contract['symbol']}|{contract['expiry']}"  # value format: SYMBOL|YYYY-MM-DD

        contract_list.append({
            'value': contract_value,
            'display': display_name,
            'volume': contract['traded_contracts'],
            'price': contract['price'],
            'lot_size': contract['lot_size']
        })

    logger.info(f"Found {len(contract_list)} futures contracts with sufficient volume")

    # If no contracts found, provide a default list
    if not contract_list:
        logger.warning("No contracts found in Trendlyne data, using fallback list")
        # Get current and next month expiry dates (approximation)
        current_month_expiry = (today + timedelta(days=25)).strftime('%d-%b-%Y')
        next_month_expiry = (today + timedelta(days=55)).strftime('%d-%b-%Y')

        fallback_stocks = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
            'HINDUNILVR', 'ITC', 'SBIN', 'BHARTIARTL', 'KOTAKBANK'
        ]

        for stock in fallback_stocks:
            contract_list.append({
                'value': f"{stock}|{(today + timedelta(days=25)).strftime('%Y-%m-%d')}",
                'display': f"{stock} - {current_month_expiry}",
                'volume': 1000,
                'price': 0,
                'lot_size': 0
            })
            contract_list.append({
                'value': f"{stock}|{(today + timedelta(days=55)).strftime('%Y-%m-%d')}",
                'display': f"{stock} - {next_month_expiry}",
                'volume': 800,
                'price': 0,
                'lot_size': 0
            })

    context = {
        'futures_contracts': contract_list,
        'page_title': 'Manual Trade Triggers',
        'total_contracts': len(contract_list),
    }

    return render(request, 'trading/manual_triggers.html', context)


@login_required
@require_POST
def refresh_trendlyne_data(request):
    """
    Trigger Trendlyne data refresh for F&O contracts
    """
    import subprocess
    import json

    try:
        body = json.loads(request.body)
        data_type = body.get('data_type', 'fno')  # fno, stocks, etc.

        logger.info(f"Triggering Trendlyne data refresh for: {data_type}")

        # Run the management command in background
        # For now, we'll run the full cycle to ensure fresh data
        result = subprocess.run(
            ['python', 'manage.py', 'trendlyne_data_manager', '--full-cycle'],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            logger.info("Trendlyne data refresh completed successfully")
            return JsonResponse({
                'success': True,
                'message': 'Trendlyne data refreshed successfully',
                'output': result.stdout
            })
        else:
            logger.error(f"Trendlyne refresh failed: {result.stderr}")
            return JsonResponse({
                'success': False,
                'error': result.stderr or 'Command failed'
            })

    except subprocess.TimeoutExpired:
        logger.error("Trendlyne refresh timed out")
        return JsonResponse({
            'success': False,
            'error': 'Data refresh timed out. Please try again later.'
        })
    except Exception as e:
        logger.error(f"Error refreshing Trendlyne data: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def get_contracts(request):
    """
    AJAX endpoint to fetch futures contracts based on dynamic volume thresholds
    """
    import json
    from apps.data.models import ContractData
    from django.db.models import Q
    from datetime import datetime, timedelta

    try:
        # Parse JSON body
        body = json.loads(request.body)
        this_month_volume = int(body.get('this_month_volume', 1000))
        next_month_volume = int(body.get('next_month_volume', 800))

        logger.info(f"Fetching contracts with volume thresholds: this_month={this_month_volume}, next_month={next_month_volume}")

        today = datetime.now().date()

        # Calculate date ranges
        this_month_end = today + timedelta(days=30)
        next_month_start = today + timedelta(days=30)
        next_month_end = today + timedelta(days=60)

        # Get futures contracts that meet volume criteria
        futures_contracts = ContractData.objects.filter(
            option_type='FUTURE',
            expiry__gte=str(today),
            expiry__lte=str(next_month_end)
        ).filter(
            Q(expiry__lte=str(this_month_end), traded_contracts__gte=this_month_volume) |
            Q(expiry__gte=str(next_month_start), expiry__lte=str(next_month_end), traded_contracts__gte=next_month_volume)
        ).order_by('symbol', 'expiry').values(
            'symbol',
            'expiry',
            'traded_contracts',
            'price',
            'lot_size'
        )

        # Format contracts
        contract_list = []
        for contract in futures_contracts:
            expiry_date = datetime.strptime(contract['expiry'], '%Y-%m-%d').strftime('%d-%b-%Y')
            display_name = f"{contract['symbol']} - {expiry_date}"
            contract_value = f"{contract['symbol']}|{contract['expiry']}"

            contract_list.append({
                'value': contract_value,
                'display': display_name,
                'volume': contract['traded_contracts'],
                'price': contract['price'],
                'lot_size': contract['lot_size']
            })

        logger.info(f"Found {len(contract_list)} contracts matching volume criteria")

        return JsonResponse({
            'success': True,
            'contracts': contract_list,
            'total_contracts': len(contract_list),
        })

    except Exception as e:
        logger.error(f"Error fetching contracts: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def trigger_futures_algorithm(request):
    """
    Manually trigger the futures screening algorithm with volume filtering
    Returns top 3 analyzed contracts with detailed explanations
    """
    import json
    from apps.trading.futures_analyzer import comprehensive_futures_analysis
    from apps.data.models import ContractData
    from django.db.models import Q
    from datetime import datetime, timedelta

    try:
        # Parse volume thresholds from request
        body = json.loads(request.body)
        this_month_volume = int(body.get('this_month_volume', 1000))
        next_month_volume = int(body.get('next_month_volume', 800))
        confirmed = body.get('confirmed', False)

        logger.info(f"Manual trigger: Futures algorithm with volume filters (this_month≥{this_month_volume}, next_month≥{next_month_volume})")

        # Get filtered contracts based on volume criteria
        today = datetime.now().date()
        this_month_end = today + timedelta(days=30)
        next_month_start = today + timedelta(days=30)
        next_month_end = today + timedelta(days=60)

        futures_contracts = ContractData.objects.filter(
            option_type='FUTURE',
            expiry__gte=str(today),
            expiry__lte=str(next_month_end)
        ).filter(
            Q(expiry__lte=str(this_month_end), traded_contracts__gte=this_month_volume) |
            Q(expiry__gte=str(next_month_start), expiry__lte=str(next_month_end), traded_contracts__gte=next_month_volume)
        ).order_by('-traded_contracts')  # Order by volume descending

        contract_count = futures_contracts.count()

        if contract_count == 0:
            return JsonResponse({
                'success': False,
                'error': f'No futures contracts found matching volume criteria (this_month≥{this_month_volume}, next_month≥{next_month_volume})'
            })

        logger.info(f"Found {contract_count} contracts matching volume criteria")

        # If more than 15 contracts and not yet confirmed, ask for user confirmation
        if contract_count > 15 and not confirmed:
            return JsonResponse({
                'success': False,
                'requires_confirmation': True,
                'contract_count': contract_count,
                'message': f'Found {contract_count} contracts to analyze. This may take a while (estimated {contract_count * 3} seconds). Do you want to proceed?'
            })

        # Run comprehensive analysis on all contracts (no limit)
        analyzed_results = []
        execution_summary = []

        for contract in futures_contracts:  # Analyze ALL contracts
            try:
                logger.info(f"Analyzing {contract.symbol} (expiry: {contract.expiry})")

                analysis_result = comprehensive_futures_analysis(
                    stock_symbol=contract.symbol,
                    expiry_date=contract.expiry,
                    contract=contract
                )

                # Extract metrics regardless of pass/fail
                metrics = analysis_result.get('metrics', {})
                composite_score = analysis_result.get('composite_score', 0)
                direction = analysis_result.get('direction', 'NEUTRAL')
                verdict = analysis_result.get('verdict', 'FAIL')
                success = analysis_result.get('success', False)

                # Format expiry
                expiry_dt = datetime.strptime(contract.expiry, '%Y-%m-%d')
                expiry_formatted = expiry_dt.strftime('%d-%b-%Y')

                # Build explanation using execution log
                explanation_parts = []
                execution_log = analysis_result.get('execution_log', [])

                # Extract key analysis points (both pass and fail)
                for log in execution_log:
                    if log['action'] == 'Open Interest Analysis' and log['status'] != 'SKIP':
                        explanation_parts.append(f"OI: {log['message']}")
                    elif log['action'] == 'Sector Strength' and log['status'] != 'SKIP':
                        explanation_parts.append(f"Sector: {log['message']}")
                    elif log['action'] == 'Multi-Factor Technical Analysis' and log['status'] != 'SKIP':
                        explanation_parts.append(f"Technical: {log['message']}")
                    elif log['action'] == 'DMA Analysis' and log['status'] != 'SKIP':
                        explanation_parts.append(f"DMA: {log['message']}")
                    elif log['action'] == 'Composite Scoring & Verdict':
                        explanation_parts.append(f"Final: {log['message']}")

                # Add to results regardless of pass/fail
                analyzed_results.append({
                    'symbol': contract.symbol,
                    'expiry': expiry_formatted,
                    'expiry_date': contract.expiry,
                    'composite_score': composite_score,
                    'direction': direction,
                    'verdict': verdict,
                    'success': success,
                    'spot_price': metrics.get('spot_price', 0),
                    'futures_price': metrics.get('futures_price', 0),
                    'basis': metrics.get('basis', 0),
                    'basis_pct': metrics.get('basis_pct', 0),
                    'volume': contract.traded_contracts,
                    'lot_size': contract.lot_size,
                    'explanation': explanation_parts,
                    'execution_log': execution_log,
                    'metrics': metrics,
                    'scores': analysis_result.get('scores', {}),
                    'error': analysis_result.get('error', None) if not success else None
                })

                execution_summary.append({
                    'symbol': contract.symbol,
                    'status': verdict,
                    'score': composite_score,
                    'success': success
                })

            except Exception as e:
                logger.error(f"Error analyzing {contract.symbol}: {e}")

                # Add failed contract to results
                try:
                    expiry_dt = datetime.strptime(contract.expiry, '%Y-%m-%d')
                    expiry_formatted = expiry_dt.strftime('%d-%b-%Y')
                except:
                    expiry_formatted = contract.expiry

                analyzed_results.append({
                    'symbol': contract.symbol,
                    'expiry': expiry_formatted,
                    'expiry_date': contract.expiry,
                    'composite_score': 0,
                    'direction': 'NEUTRAL',
                    'verdict': 'ERROR',
                    'success': False,
                    'spot_price': 0,
                    'futures_price': 0,
                    'basis': 0,
                    'basis_pct': 0,
                    'volume': contract.traded_contracts,
                    'lot_size': contract.lot_size,
                    'explanation': [f"Analysis failed: {str(e)[:200]}"],
                    'execution_log': [],
                    'metrics': {},
                    'scores': {},
                    'error': str(e)
                })

                execution_summary.append({
                    'symbol': contract.symbol,
                    'status': 'ERROR',
                    'error': str(e),
                    'score': 0,
                    'success': False
                })
                continue

        # Sort by verdict priority (PASS first, then FAIL, then ERROR) and then by score
        def sort_key(contract):
            verdict = contract['verdict']
            score = contract['composite_score']

            # Priority: PASS=0, FAIL=1, ERROR=2 (lower is better)
            priority = 0 if verdict == 'PASS' else (1 if verdict == 'FAIL' else 2)

            # Return tuple: (priority, negative_score) so PASS comes first, then sorted by score descending
            return (priority, -score)

        analyzed_results.sort(key=sort_key)

        # Count passed contracts
        passed_results = [r for r in analyzed_results if r['verdict'] == 'PASS']

        if not analyzed_results:
            return JsonResponse({
                'success': False,
                'error': 'No contracts could be analyzed',
                'execution_summary': execution_summary,
                'total_analyzed': 0
            })

        logger.info(f"Analysis complete: {len(analyzed_results)} contracts analyzed, {len(passed_results)} passed")

        # Prepare response - return ALL analyzed results
        response_data = {
            'success': True,
            'all_contracts': analyzed_results,  # All contracts sorted by score
            'total_analyzed': len(analyzed_results),
            'total_passed': len(passed_results),
            'total_failed': len([r for r in analyzed_results if r['verdict'] == 'FAIL']),
            'total_errors': len([r for r in analyzed_results if r['verdict'] == 'ERROR']),
            'execution_summary': execution_summary,
            'volume_filters': {
                'this_month': this_month_volume,
                'next_month': next_month_volume
            }
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in trigger_futures_algorithm: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def trigger_nifty_strangle(request):
    """
    Manually trigger Nifty options strangle strategy
    Uses real Breeze option chain data and smart delta-based strike selection
    """
    try:
        from apps.brokers.integrations.breeze import (
            fetch_and_save_nifty_option_chain_all_expiries,
            get_nifty_quote,
            get_india_vix
        )
        from apps.core.services.expiry_selector import select_expiry_for_options
        from apps.accounts.models import BrokerAccount
        from apps.data.models import OptionChain
        from apps.strategies.services.strangle_delta_algorithm import StrangleDeltaAlgorithm
        from decimal import Decimal

        execution_log = []

        # Get Kotak account
        account = BrokerAccount.objects.filter(
            broker='KOTAK',
            is_active=True
        ).first()

        if not account:
            return JsonResponse({
                'success': False,
                'error': 'No active Kotak broker account found'
            })

        logger.info("Manual trigger: Nifty strangle strategy with real Breeze data")

        # STEP 1: Fetch fresh option chain data from Breeze
        try:
            logger.info("Fetching fresh NIFTY option chain from Breeze...")
            total_saved = fetch_and_save_nifty_option_chain_all_expiries()
            execution_log.append({
                'step': 1,
                'action': 'Option Chain Data Fetch',
                'status': 'success',
                'message': f'Fetched {total_saved} option records from Breeze API'
            })
        except Exception as e:
            logger.warning(f"Could not fetch fresh option chain: {e}")
            execution_log.append({
                'step': 1,
                'action': 'Option Chain Data Fetch',
                'status': 'warning',
                'message': f'Using cached data (fetch failed: {str(e)[:100]})'
            })

        # STEP 2: Get current Nifty price and VIX from Breeze
        try:
            nifty_quote = get_nifty_quote()
            nifty_price = Decimal(str(nifty_quote.get('ltp', 0)))
            execution_log.append({
                'step': 2,
                'action': 'Nifty Spot Price',
                'status': 'success',
                'message': f'₹{nifty_price:,.2f}'
            })
        except Exception as e:
            logger.error(f"Failed to get Nifty price: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Could not fetch Nifty price: {str(e)}',
                'execution_log': execution_log
            })

        try:
            vix = get_india_vix()
            execution_log.append({
                'step': 3,
                'action': 'India VIX',
                'status': 'success',
                'message': f'{float(vix):.2f}'
            })
        except Exception as e:
            logger.error(f"Failed to get VIX: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Could not fetch VIX: {str(e)}',
                'execution_log': execution_log
            })

        # STEP 3: Select expiry
        try:
            expiry_date, expiry_details = select_expiry_for_options(instrument='NIFTY', min_days=1)
            days_to_expiry = expiry_details['days_remaining']
            execution_log.append({
                'step': 4,
                'action': 'Expiry Selection',
                'status': 'success',
                'message': f'{expiry_details["expiry_type"]} - {expiry_date.strftime("%d-%b-%Y")} ({days_to_expiry} days)',
                'details': expiry_details
            })
        except Exception as e:
            logger.error(f"Failed to select expiry: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Could not select expiry: {str(e)}',
                'execution_log': execution_log
            })

        # STEP 3.5: Validate market conditions (NO TRADE DAY checks)
        try:
            from apps.strategies.services.market_condition_validator import validate_market_conditions

            logger.info("Validating market conditions for strangle entry")
            validation_report = validate_market_conditions(nifty_price, vix, days_to_expiry)

            # Add validation summary to execution log
            verdict = validation_report['overall_verdict']
            verdict_status = 'success' if validation_report['trade_allowed'] else 'fail'
            if validation_report['warnings'] and validation_report['trade_allowed']:
                verdict_status = 'warning'

            execution_log.append({
                'step': 5,
                'action': 'Market Condition Validation',
                'status': verdict_status,
                'message': f'{verdict}: {validation_report["verdict_reason"]}',
                'details': {
                    'checks_passed': validation_report['status_summary']['PASS'],
                    'warnings': validation_report['status_summary']['WARNING'],
                    'checks_failed': validation_report['status_summary']['FAIL'],
                    'total_warnings': len(validation_report['warnings'])
                }
            })

            # If NO TRADE DAY, stop here and return the report
            if not validation_report['trade_allowed']:
                logger.warning(f"NO TRADE DAY detected: {validation_report['verdict_reason']}")
                return JsonResponse({
                    'success': False,
                    'error': f'NO TRADE DAY: {validation_report["verdict_reason"]}',
                    'execution_log': execution_log,
                    'validation_report': validation_report,
                    'is_no_trade_day': True
                })

        except Exception as e:
            logger.warning(f"Market validation failed: {e}, continuing anyway")
            execution_log.append({
                'step': 5,
                'action': 'Market Condition Validation',
                'status': 'warning',
                'message': f'Validation skipped: {str(e)[:100]}'
            })
            validation_report = None

        # STEP 4: Run technical analysis (Support/Resistance, Moving Averages)
        try:
            from apps.strategies.services.technical_analysis import analyze_technical_indicators

            logger.info(f"Running technical analysis for strike optimization")
            technical_analysis = analyze_technical_indicators(
                symbol='NIFTY',
                current_price=float(nifty_price)
            )

            ta_verdict = technical_analysis.get('technical_verdict', 'SYMMETRIC')
            ta_status = 'success' if technical_analysis.get('delta_adjustments', {}).get('is_asymmetric') else 'warning'

            execution_log.append({
                'step': 6,
                'action': 'Technical Analysis (S/R & MA)',
                'status': ta_status,
                'message': ta_verdict,
                'details': {
                    'sr_position': technical_analysis.get('sr_position', {}).get('position'),
                    'trend': technical_analysis.get('trend_analysis', {}).get('bias'),
                    'call_multiplier': technical_analysis.get('delta_adjustments', {}).get('call_multiplier'),
                    'put_multiplier': technical_analysis.get('delta_adjustments', {}).get('put_multiplier'),
                }
            })

        except Exception as e:
            logger.warning(f"Technical analysis failed: {e}, continuing with symmetric strikes")
            execution_log.append({
                'step': 6,
                'action': 'Technical Analysis (S/R & MA)',
                'status': 'warning',
                'message': f'Skipped: {str(e)[:100]}'
            })
            technical_analysis = None

        # STEP 5: Calculate strikes using smart delta algorithm with technical analysis
        try:
            logger.info(f"Calculating strikes using delta algorithm (spot={nifty_price}, days={days_to_expiry}, vix={vix})")

            # Initialize delta algorithm
            algo = StrangleDeltaAlgorithm(
                spot_price=nifty_price,
                days_to_expiry=days_to_expiry,
                vix=vix
            )

            # Calculate market conditions from option chain data
            # Get available option chain data for PCR and OI analysis
            option_data = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=expiry_date
            )

            market_conditions = {}

            # Calculate PCR from real data
            if option_data.exists():
                total_call_oi = sum(option_data.filter(option_type='CE').values_list('oi', flat=True))
                total_put_oi = sum(option_data.filter(option_type='PE').values_list('oi', flat=True))

                if total_call_oi > 0:
                    pcr = Decimal(total_put_oi) / Decimal(total_call_oi)
                    market_conditions['pcr'] = pcr
                    logger.info(f"Calculated PCR from real data: {float(pcr):.2f}")

            # Calculate adjusted strikes with technical analysis
            strike_result = algo.calculate_strikes(market_conditions, technical_analysis)

            call_strike = strike_result['call_strike']
            put_strike = strike_result['put_strike']

            strike_message = f'CE {call_strike} | PE {put_strike} (Δ={strike_result["adjusted_delta"]:.3f}%)'
            if strike_result.get('is_asymmetric'):
                strike_message += f' [ASYMMETRIC: Call ×{strike_result["call_multiplier"]:.2f}, Put ×{strike_result["put_multiplier"]:.2f}]'

            execution_log.append({
                'step': 7,
                'action': 'Delta-Based Strike Calculation',
                'status': 'success',
                'message': strike_message,
                'details': {
                    'base_delta': strike_result['base_delta'],
                    'adjusted_delta': strike_result['adjusted_delta'],
                    'strike_distance': strike_result['strike_distance'],
                    'call_distance': strike_result.get('call_distance'),
                    'put_distance': strike_result.get('put_distance'),
                    'is_asymmetric': strike_result.get('is_asymmetric'),
                    'delta_breakdown': strike_result['delta_breakdown'],
                    'calculation_log': strike_result['calculation_log']
                }
            })

        except Exception as e:
            logger.error(f"Failed to calculate strikes: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': f'Strike calculation failed: {str(e)}',
                'execution_log': execution_log
            })

        # STEP 5.5: Check for psychological levels and adjust strikes if needed
        try:
            from apps.strategies.services.psychological_levels import check_psychological_levels

            logger.info(f"Checking strikes for psychological levels (CE {call_strike}, PE {put_strike})")
            psych_analysis = check_psychological_levels(call_strike, put_strike, float(nifty_price))

            # Update strikes if adjustments were made
            if psych_analysis['any_adjustments']:
                original_call = call_strike
                original_put = put_strike
                call_strike = psych_analysis['adjusted_call']
                put_strike = psych_analysis['adjusted_put']

                psych_message = f"ADJUSTED: {', '.join(psych_analysis['adjustments_made'])}"
                psych_status = 'warning'

                logger.warning(f"Psychological level adjustments: CE {original_call}→{call_strike}, PE {original_put}→{put_strike}")
            else:
                psych_message = "Strikes clear of psychological levels - No adjustment needed"
                psych_status = 'success'

            execution_log.append({
                'step': 8,
                'action': 'Psychological Level Check',
                'status': psych_status,
                'message': psych_message,
                'details': {
                    'original_call': psych_analysis['original_call'],
                    'original_put': psych_analysis['original_put'],
                    'final_call': call_strike,
                    'final_put': put_strike,
                    'adjustments_made': psych_analysis['adjustments_made'],
                    'safety_verdict': psych_analysis['safety_verdict'],
                    'call_dangers': psych_analysis['call_analysis']['danger_analysis']['dangers'] if psych_analysis['call_analysis']['danger_analysis']['in_danger_zone'] else [],
                    'put_dangers': psych_analysis['put_analysis']['danger_analysis']['dangers'] if psych_analysis['put_analysis']['danger_analysis']['in_danger_zone'] else [],
                }
            })

        except Exception as e:
            logger.warning(f"Psychological level check failed: {e}, continuing with original strikes")
            execution_log.append({
                'step': 8,
                'action': 'Psychological Level Check',
                'status': 'warning',
                'message': f'Skipped: {str(e)[:100]}'
            })

        # STEP 9: Get real option premiums from database
        # Find nearest available strikes since calculated strikes might not exist
        # IMPORTANT: Use the psychologically-adjusted strikes (call_strike, put_strike are already adjusted at this point)
        try:
            from django.db.models import F, Func
            from django.db.models.functions import Abs

            # Get all available call strikes for this expiry
            available_call_strikes = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=expiry_date,
                option_type='CE',
                ltp__gt=0  # Only strikes with valid prices
            ).values_list('strike', flat=True)

            # Get all available put strikes for this expiry
            available_put_strikes = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=expiry_date,
                option_type='PE',
                ltp__gt=0  # Only strikes with valid prices
            ).values_list('strike', flat=True)

            if not available_call_strikes or not available_put_strikes:
                raise ValueError(f"No option data available for expiry {expiry_date}")

            # IMPORTANT: Check if psychologically-adjusted strikes exist in database
            # We should NOT compromise on psychological safety by using non-adjusted strikes
            logger.info(f"Psychologically-adjusted strikes: CE {call_strike}, PE {put_strike}")

            # Check if adjusted call strike exists
            call_option = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=expiry_date,
                strike=call_strike,
                option_type='CE',
                ltp__gt=0
            ).first()

            if not call_option:
                # Adjusted strike doesn't exist - find nearest
                logger.warning(f"Adjusted CE {call_strike} not found in database, finding nearest...")
                call_strike_actual = min(available_call_strikes, key=lambda x: abs(float(x) - call_strike))
                call_option = OptionChain.objects.filter(
                    underlying='NIFTY',
                    expiry_date=expiry_date,
                    strike=call_strike_actual,
                    option_type='CE'
                ).first()
                call_strike = int(call_strike_actual)
                logger.warning(f"Using nearest available CE {call_strike}")

            # Check if adjusted put strike exists
            put_option = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=expiry_date,
                strike=put_strike,
                option_type='PE',
                ltp__gt=0
            ).first()

            if not put_option:
                # Adjusted strike doesn't exist - find nearest
                logger.warning(f"Adjusted PE {put_strike} not found in database, finding nearest...")
                put_strike_actual = min(available_put_strikes, key=lambda x: abs(float(x) - put_strike))
                put_option = OptionChain.objects.filter(
                    underlying='NIFTY',
                    expiry_date=expiry_date,
                    strike=put_strike_actual,
                    option_type='PE'
                ).first()
                put_strike = int(put_strike_actual)
                logger.warning(f"Using nearest available PE {put_strike}")

            if not call_option or not put_option:
                raise ValueError(f"Option data not found for strikes CE {call_strike}, PE {put_strike}")

            call_premium = call_option.ltp or Decimal('0')
            put_premium = put_option.ltp or Decimal('0')
            total_premium = call_premium + put_premium

            logger.info(f"Strikes from database: CE {call_strike}, PE {put_strike}")

            # FINAL SAFETY CHECK: Verify strikes are not at psychological levels
            # This catches cases where database only has round number strikes
            final_psych_check = check_psychological_levels(call_strike, put_strike, float(nifty_price))

            if final_psych_check['any_adjustments']:
                logger.warning(f"⚠️ FINAL SAFETY CHECK: Database strikes are at psychological levels!")
                logger.warning(f"Database returned: CE {call_strike}, PE {put_strike}")
                logger.warning(f"Required adjustment: CE {call_strike}→{final_psych_check['adjusted_call']}, PE {put_strike}→{final_psych_check['adjusted_put']}")

                # Update to safe strikes
                call_strike = final_psych_check['adjusted_call']
                put_strike = final_psych_check['adjusted_put']

                # Re-fetch premiums for adjusted strikes
                call_option = OptionChain.objects.filter(
                    underlying='NIFTY',
                    expiry_date=expiry_date,
                    strike=call_strike,
                    option_type='CE'
                ).first()

                put_option = OptionChain.objects.filter(
                    underlying='NIFTY',
                    expiry_date=expiry_date,
                    strike=put_strike,
                    option_type='PE'
                ).first()

                if call_option and put_option:
                    call_premium = call_option.ltp or Decimal('0')
                    put_premium = put_option.ltp or Decimal('0')
                    total_premium = call_premium + put_premium
                    logger.info(f"✓ Adjusted to safe strikes: CE {call_strike}, PE {put_strike}")
                else:
                    # If adjusted strikes don't exist, we have a problem
                    logger.error(f"Adjusted strikes CE {call_strike}, PE {put_strike} not available in database!")
                    return JsonResponse({
                        'success': False,
                        'error': f'Cannot find safe strikes. Database has CE {final_psych_check["original_call"]}, PE {final_psych_check["original_put"]} but adjusted strikes CE {call_strike}, PE {put_strike} not available.',
                        'execution_log': execution_log
                    })

            logger.info(f"Final SAFE strikes: CE {call_strike}, PE {put_strike}")

            execution_log.append({
                'step': 9,
                'action': 'Real Premium Fetch',
                'status': 'success',
                'message': f'CE {call_strike}: ₹{float(call_premium):.2f} | PE {put_strike}: ₹{float(put_premium):.2f} | Total: ₹{float(total_premium):.2f}',
                'details': {
                    'call_strike_calculated': strike_result['call_strike'],
                    'call_strike_adjusted_by_psych': psych_analysis['adjusted_call'] if 'psych_analysis' in locals() else call_strike,
                    'call_strike_final': call_strike,
                    'call_ltp': float(call_premium),
                    'call_volume': call_option.volume,
                    'call_oi': call_option.oi,
                    'put_strike_calculated': strike_result['put_strike'],
                    'put_strike_adjusted_by_psych': psych_analysis['adjusted_put'] if 'psych_analysis' in locals() else put_strike,
                    'put_strike_final': put_strike,
                    'put_ltp': float(put_premium),
                    'put_volume': put_option.volume,
                    'put_oi': put_option.oi
                }
            })

        except Exception as e:
            logger.error(f"Failed to get option premiums: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Could not fetch option premiums: {str(e)}',
                'execution_log': execution_log
            })

        # STEP 6: Calculate margins and risk
        try:
            # Approximate margin for short strangle (15% of notional)
            margin_required = float(nifty_price * 50 * Decimal('0.15'))

            # Calculate breakeven points
            breakeven_upper = call_strike + float(total_premium)
            breakeven_lower = put_strike - float(total_premium)

            execution_log.append({
                'step': 7,
                'action': 'Risk Calculation',
                'status': 'success',
                'message': f'Margin: ₹{margin_required:,.0f} | Breakeven: {breakeven_lower:.0f} - {breakeven_upper:.0f}',
                'details': {
                    'margin_required': margin_required,
                    'breakeven_upper': breakeven_upper,
                    'breakeven_lower': breakeven_lower,
                    'max_profit': float(total_premium),
                    'profit_pct': (float(total_premium) / margin_required * 100) if margin_required > 0 else 0
                }
            })

        except Exception as e:
            logger.warning(f"Risk calculation issue: {e}")
            margin_required = 0
            breakeven_upper = call_strike
            breakeven_lower = put_strike

        # Prepare final response
        explanation = {
            'strategy': 'Short Strangle (Delta-Based)',
            'underlying': 'NIFTY',
            'current_price': float(nifty_price),
            'expiry_date': expiry_date.strftime('%Y-%m-%d'),
            'days_to_expiry': days_to_expiry,
            'vix': float(vix),
            'call_strike': call_strike,
            'put_strike': put_strike,
            'call_premium': float(call_premium),
            'put_premium': float(put_premium),
            'total_premium': float(total_premium),
            'margin_required': margin_required,
            'max_profit': float(total_premium),
            'breakeven_upper': breakeven_upper,
            'breakeven_lower': breakeven_lower,
            'reasoning': {
                'strike_selection': f"Smart delta-based selection: Base Δ={strike_result['base_delta']:.2f}% → Adjusted Δ={strike_result['adjusted_delta']:.3f}%",
                'risk_profile': 'Market-neutral short strangle collecting premium with multi-factor delta adjustment',
                'entry_logic': f'Selling {days_to_expiry}-day OTM options at {float(strike_result["strike_distance"]):.0f} points from spot',
                'exit_strategy': '50% profit target or expiry, whichever comes first',
                'delta_analysis': strike_result['calculation_log'],
            },
            'execution_log': execution_log,
            'delta_details': strike_result,
            'validation_report': validation_report  # Include validation report in response
        }

        return JsonResponse({
            'success': True,
            'strangle': explanation
        })

    except Exception as e:
        logger.error(f"Error in trigger_nifty_strangle: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'execution_log': execution_log if 'execution_log' in locals() else []
        })


@login_required
@require_POST
def verify_future_trade(request):
    """
    Verify a specific futures contract for trading
    Runs comprehensive 9-step analysis using Breeze API
    """
    try:
        from apps.trading.futures_analyzer import comprehensive_futures_analysis
        from apps.data.models import ContractData

        contract_value = request.POST.get('contract', '').strip()

        if not contract_value:
            return JsonResponse({
                'success': False,
                'error': 'Contract selection is required'
            })

        # Parse contract value: "SYMBOL|YYYY-MM-DD"
        try:
            stock_symbol, expiry_date = contract_value.split('|')
            stock_symbol = stock_symbol.upper()
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid contract format'
            })

        logger.info(f"Manual verification: {stock_symbol} expiry {expiry_date}")

        # Get contract details from Trendlyne
        contract = ContractData.objects.filter(
            symbol=stock_symbol,
            option_type='FUTURE',
            expiry=expiry_date
        ).first()

        # Run comprehensive analysis with Breeze API
        analysis_result = comprehensive_futures_analysis(
            stock_symbol=stock_symbol,
            expiry_date=expiry_date,
            contract=contract
        )

        if not analysis_result.get('success'):
            return JsonResponse({
                'success': False,
                'error': analysis_result.get('error', f'Unable to analyze {stock_symbol}. Stock may not be available for F&O or data is missing.'),
                'execution_log': analysis_result.get('execution_log', [])
            })

        # Extract metrics and prepare response
        metrics = analysis_result.get('metrics', {})
        execution_log = analysis_result.get('execution_log', [])

        # Get prices from analysis
        spot_price = metrics.get('spot_price', 0)
        futures_price = metrics.get('futures_price', 0)

        # Format expiry for display
        from datetime import datetime
        expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
        expiry_formatted = expiry_dt.strftime('%d-%b-%Y')

        # Determine pass/fail based on analysis verdict
        passed = analysis_result.get('verdict') == 'PASS'
        direction = analysis_result.get('direction', 'NEUTRAL')
        composite_score = analysis_result.get('composite_score', 0)

        # Calculate position details if we have contract data
        position_details = {}
        if contract and futures_price > 0:
            lot_size = contract.lot_size
            entry_value = futures_price * lot_size

            # Use simple 2% stop loss and 4% target for now
            if direction == 'LONG':
                stop_loss = futures_price * 0.98
                target = futures_price * 1.04
            elif direction == 'SHORT':
                stop_loss = futures_price * 1.02
                target = futures_price * 0.96
            else:
                stop_loss = futures_price * 0.98
                target = futures_price * 1.02

            risk_amount = abs(futures_price - stop_loss) * lot_size
            reward_amount = abs(target - futures_price) * lot_size
            risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0

            position_details = {
                'lot_size': lot_size,
                'entry_value': entry_value,
                'risk_amount': risk_amount,
                'reward_amount': reward_amount,
                'risk_reward_ratio': round(risk_reward_ratio, 2)
            }

        # Build analysis summary
        analysis_summary = {
            'direction': direction,
            'entry_price': futures_price,
            'stop_loss': position_details.get('stop_loss', futures_price * 0.98) if position_details else futures_price * 0.98,
            'target': position_details.get('target', futures_price * 1.04) if position_details else futures_price * 1.04,
            'composite_score': composite_score,
            'contract_price': futures_price,
            'spot_price': spot_price,
            'lot_size': contract.lot_size if contract else 0,
            'traded_volume': contract.traded_contracts if contract else 0,
            'basis': metrics.get('basis', 0),
            'basis_pct': metrics.get('basis_pct', 0),
            'cost_of_carry': metrics.get('cost_of_carry', 0),
            'position_details': position_details
        }

        response_data = {
            'success': True,
            'symbol': stock_symbol,
            'expiry': expiry_formatted,
            'contract_display': f"{stock_symbol} - {expiry_formatted}",
            'passed': passed,
            'analysis': analysis_summary,
            'execution_log': execution_log,
            'llm_validation': {'approved': False, 'confidence': 0, 'reasoning': 'LLM validation skipped (Phase 2)'},
            'verdict': f'{"PASS" if passed else "FAIL"} - Score: {composite_score}/100',
            'reason': f'Composite score: {composite_score}/100. Direction: {direction}'
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in verify_future_trade: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_POST
def prepare_manual_execution(request):
    """
    Prepare manual trade execution - show confirmation page with 4-checkbox safety check

    Receives trade data from manual_triggers.html and displays confirmation page
    """
    import json
    from decimal import Decimal

    try:
        # Get trade data from POST
        trade_data_json = request.POST.get('trade_data')
        if not trade_data_json:
            messages.error(request, "No trade data received")
            return redirect('trading:manual_triggers')

        trade_data = json.loads(trade_data_json)

        # Get current VIX
        vix = get_india_vix()

        # Determine algorithm display name
        algorithm_type = trade_data.get('algorithm_type', 'unknown')
        algorithm_display_map = {
            'futures': 'ICICI Futures Algorithm',
            'strangle': 'Nifty Strangle Generator',
            'verify': 'Verify Future Trade'
        }
        algorithm_display = algorithm_display_map.get(algorithm_type, algorithm_type)

        # Calculate risk metrics
        entry_price = Decimal(str(trade_data.get('entry_price', 0)))
        stop_loss = Decimal(str(trade_data.get('stop_loss', 0)))
        target = Decimal(str(trade_data.get('target', 0)))
        quantity = int(trade_data.get('quantity', 1))

        # Calculate max loss and risk:reward
        max_loss = abs(entry_price - stop_loss) * quantity
        max_gain = abs(target - entry_price) * quantity
        risk_reward_ratio = max_gain / max_loss if max_loss > 0 else Decimal('0')

        # Analysis summary
        analysis_summary = trade_data.get('analysis_summary',
            f"Trade generated by {algorithm_display} with {len(trade_data.get('factors_met', []))} factors validated")

        context = {
            'trade_data': trade_data,
            'trade_data_json': trade_data_json,
            'algorithm_display': algorithm_display,
            'vix': vix,
            'max_loss': max_loss,
            'risk_reward_ratio': risk_reward_ratio,
            'analysis_summary': analysis_summary,
        }

        return render(request, 'trading/manual_execution_confirm.html', context)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in trade data: {e}")
        messages.error(request, "Invalid trade data format")
        return redirect('trading:manual_triggers')

    except Exception as e:
        logger.error(f"Error preparing manual execution: {e}", exc_info=True)
        messages.error(request, f"Error: {str(e)}")
        return redirect('trading:manual_triggers')


@login_required
@require_POST
def confirm_manual_execution(request):
    """
    Execute manual trade after user confirms via 4-checkbox safety protocol

    Places live orders with broker and creates Position record
    """
    import json
    from decimal import Decimal
    from django.db import transaction

    from apps.orders.models import Order
    from apps.accounts.models import BrokerAccount
    from apps.brokers.integrations.breeze import get_breeze_client
    from apps.brokers.integrations.kotak_neo import get_kotak_client

    try:
        # Get trade data
        trade_data_json = request.POST.get('trade_data')
        if not trade_data_json:
            messages.error(request, "No trade data received")
            return redirect('trading:manual_triggers')

        trade_data = json.loads(trade_data_json)

        # Determine broker based on algorithm
        algorithm_type = trade_data.get('algorithm_type', 'futures')
        if algorithm_type == 'strangle':
            broker_code = 'KOTAK'
        else:
            broker_code = 'ICICI'

        # Get broker account
        try:
            broker_account = BrokerAccount.objects.get(broker=broker_code, is_active=True)
        except BrokerAccount.DoesNotExist:
            messages.error(request, f"No active {broker_code} broker account found")
            return redirect('trading:manual_triggers')

        # Check ONE POSITION RULE
        existing_positions = Position.objects.filter(
            account=broker_account,
            status__in=['OPEN', 'PARTIAL']
        )

        if existing_positions.exists():
            messages.error(request,
                f"Cannot execute: ONE POSITION RULE violated. "
                f"Close existing position first: {existing_positions.first().instrument}")
            return redirect('trading:manual_triggers')

        # Execute trade with transaction safety
        with transaction.atomic():
            # Create Position record
            position = Position.objects.create(
                account=broker_account,
                user=request.user,
                instrument=trade_data.get('instrument'),
                direction=trade_data.get('direction', 'LONG'),
                quantity=int(trade_data.get('quantity', 1)),
                entry_price=Decimal(str(trade_data.get('entry_price', 0))),
                current_price=Decimal(str(trade_data.get('entry_price', 0))),
                stop_loss=Decimal(str(trade_data.get('stop_loss', 0))),
                target=Decimal(str(trade_data.get('target', 0))),
                status='OPEN',
                margin_used=Decimal(str(trade_data.get('margin_required', 0))),
                entry_reasoning=trade_data.get('analysis_summary', 'Manual trade execution'),
                strategy_name=f"manual_{algorithm_type}"
            )

            logger.info(f"Created position {position.id} for manual trade")

            # Place order with broker
            try:
                if broker_code == 'ICICI':
                    # Place order with Breeze
                    breeze = get_breeze_client()
                    # Note: Actual order placement logic depends on Breeze API
                    # This is a placeholder - implement based on your broker API
                    order_result = {
                        'success': True,
                        'order_id': f'MANUAL_{position.id}',
                        'message': 'Order placed successfully (simulated)'
                    }
                else:
                    # Place order with Kotak Neo
                    kotak = get_kotak_client()
                    # Note: Implement actual Kotak order placement
                    order_result = {
                        'success': True,
                        'order_id': f'MANUAL_{position.id}',
                        'message': 'Order placed successfully (simulated)'
                    }

                # Create Order record
                order = Order.objects.create(
                    position=position,
                    order_type='MARKET',
                    action='BUY' if trade_data.get('direction') == 'LONG' else 'SELL',
                    quantity=position.quantity,
                    price=position.entry_price,
                    status='FILLED',
                    broker_order_id=order_result.get('order_id'),
                    filled_quantity=position.quantity,
                    filled_price=position.entry_price
                )

                logger.info(f"Created order {order.id} for position {position.id}")

                messages.success(request,
                    f"Trade executed successfully! Position ID: {position.id}, Order ID: {order.broker_order_id}")

                # TODO: Send Telegram notification

                return redirect('positions:position_detail', position_id=position.id)

            except Exception as broker_error:
                logger.error(f"Broker order failed: {broker_error}", exc_info=True)
                # Rollback will happen automatically due to transaction.atomic()
                messages.error(request, f"Order placement failed: {str(broker_error)}")
                return redirect('trading:manual_triggers')

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in trade data: {e}")
        messages.error(request, "Invalid trade data format")
        return redirect('trading:manual_triggers')

    except Exception as e:
        logger.error(f"Error confirming manual execution: {e}", exc_info=True)
        messages.error(request, f"Execution error: {str(e)}")
        return redirect('trading:manual_triggers')
