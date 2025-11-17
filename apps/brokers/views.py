"""
Broker views for mCube Trading System

This module contains views for broker authentication, data fetching, and display.
"""

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator

from apps.core.models import CredentialStore
from apps.brokers.models import BrokerLimit, BrokerPosition, OptionChainQuote, HistoricalPrice, NiftyOptionChain
from apps.brokers.integrations.kotak_neo import (
    fetch_and_save_kotakneo_data,
    is_open_position
)
from apps.brokers.integrations.breeze import (
    get_or_prompt_breeze_token,
    save_breeze_token,
    fetch_and_save_breeze_data,
    get_nifty_quote,
    get_and_save_option_chain_quotes,
    get_nifty50_historical_days,
    get_next_nifty_expiry,
    fetch_and_save_nifty_option_chain_all_expiries
)

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# AUTHENTICATION VIEWS
# =============================================================================

def login_view(request):
    """
    Handle user login.
    """
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")

            # Redirect to next or home page
            next_url = request.GET.get('next', 'home')
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'brokers/login.html')


@login_required
def logout_view(request):
    """
    Handle user logout.
    """
    auth_logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('home')


# =============================================================================
# HELPER FUNCTIONS FOR PERMISSIONS
# =============================================================================

def is_admin_user(user):
    """Check if user is admin (superuser or in Admin group)"""
    return user.is_superuser or user.groups.filter(name='Admin').exists()


def is_trader_user(user):
    """Check if user is trader (in User group or Admin group)"""
    return user.groups.filter(name__in=['Admin', 'User']).exists() or user.is_superuser


# =============================================================================
# KOTAK NEO VIEWS
# =============================================================================

@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
def kotakneo_login(request):
    """
    Handle Kotak Neo OTP login (Admin only).
    """
    if request.method == 'POST':
        otp = request.POST.get('otp')
        if otp:
            try:
                # Save OTP to credentials
                creds = CredentialStore.objects.filter(service='kotakneo').first()
                if not creds:
                    messages.error(request, "No Kotak Neo credentials found. Please add credentials first.")
                    return render(request, 'brokers/kotakneo_login.html')

                creds.session_token = otp
                creds.save()

                messages.success(request, "OTP saved successfully!")
                return redirect('brokers:kotakneo_data')

            except Exception as e:
                logger.exception(f"Error saving Kotak Neo OTP: {e}")
                messages.error(request, f"Error: {str(e)}")

    return render(request, 'brokers/kotakneo_login.html')


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
def kotakneo_data(request):
    """
    Fetch and display Kotak Neo limits and positions (Traders can view).
    """
    try:
        limit_rec, pos_list = fetch_and_save_kotakneo_data()
        has_positions = is_open_position()

        context = {
            'limit': limit_rec,
            'positions': pos_list,
            'has_open_positions': has_positions,
            'broker': 'Kotak Neo',
        }
        messages.success(request, f"Fetched {len(pos_list)} positions from Kotak Neo")
        return render(request, 'brokers/broker_data.html', context)

    except Exception as e:
        logger.exception(f"Error fetching Kotak Neo data: {e}")
        messages.error(request, f"Error: {str(e)}")
        return redirect('brokers:kotakneo_login')


# =============================================================================
# BREEZE VIEWS
# =============================================================================

@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
def breeze_login(request):
    """
    Handle Breeze session token entry (Admin only).
    """
    if request.method == 'POST':
        session_token = request.POST.get('session_token')
        if session_token:
            try:
                save_breeze_token(session_token)
                messages.success(request, "Session token saved successfully!")
                return redirect('brokers:breeze_data')

            except Exception as e:
                logger.exception(f"Error saving Breeze token: {e}")
                messages.error(request, f"Error: {str(e)}")

    # Check if token is already valid
    try:
        status = get_or_prompt_breeze_token()
        if status == 'ready':
            messages.info(request, "Session token is already valid for today.")
    except:
        pass

    return render(request, 'brokers/breeze_login.html')


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
def breeze_data(request):
    """
    Fetch and display Breeze funds and positions (Traders can view).
    """
    try:
        limit_rec, pos_list = fetch_and_save_breeze_data()

        context = {
            'limit': limit_rec,
            'positions': pos_list,
            'broker': 'ICICI Breeze',
        }
        messages.success(request, f"Fetched {len(pos_list)} positions from Breeze")
        return render(request, 'brokers/broker_data.html', context)

    except Exception as e:
        logger.exception(f"Error fetching Breeze data: {e}")
        messages.error(request, f"Error: {str(e)}")
        return redirect('brokers:breeze_login')


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
def nifty_quote(request):
    """
    Get current NIFTY spot price (Traders can access).
    """
    try:
        quote = get_nifty_quote()
        return JsonResponse(quote if quote else {'error': 'Failed to fetch quote'})
    except Exception as e:
        logger.exception(f"Error fetching NIFTY quote: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
def breeze_option_chain(request):
    """
    Fetch and display NIFTY option chain data for all expiries (Traders can access).
    """
    try:
        if request.method == 'POST':
            # Fetch and save NIFTY option chain for all expiries
            total_saved = fetch_and_save_nifty_option_chain_all_expiries()
            messages.success(request, f"Fetched and saved {total_saved} NIFTY option chain records across all expiries")

        # Get all unique expiry dates
        expiry_dates = NiftyOptionChain.objects.values_list('expiry_date', flat=True).distinct().order_by('expiry_date')

        # Get selected expiry or use first one
        selected_expiry = request.GET.get('expiry')
        if selected_expiry:
            from datetime import datetime
            selected_expiry = datetime.strptime(selected_expiry, '%Y-%m-%d').date()
        elif expiry_dates:
            selected_expiry = expiry_dates[0]
        else:
            selected_expiry = None

        # Fetch option chain data for selected expiry
        option_chain = []
        spot_price = None
        if selected_expiry:
            option_chain = NiftyOptionChain.objects.filter(
                expiry_date=selected_expiry
            ).order_by('strike_price')[:100]

            if option_chain:
                spot_price = option_chain[0].spot_price

        context = {
            'option_chain': option_chain,
            'expiry_dates': expiry_dates,
            'selected_expiry': selected_expiry,
            'spot_price': spot_price,
            'total_records': NiftyOptionChain.objects.count(),
        }
        return render(request, 'brokers/option_chain.html', context)

    except Exception as e:
        logger.exception(f"Error with NIFTY option chain: {e}")
        messages.error(request, f"Error: {str(e)}")
        return render(request, 'brokers/option_chain.html', {'error': str(e)})


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
def breeze_historical(request):
    """
    Fetch and display historical data (Traders can access).
    """
    if request.method == 'POST':
        days = int(request.POST.get('days', 1000))
        interval = request.POST.get('interval', '1day')

        try:
            saved_count = get_nifty50_historical_days(days=days, interval=interval)
            messages.success(request, f"Saved {saved_count} historical records")
        except Exception as e:
            logger.exception(f"Error fetching historical data: {e}")
            messages.error(request, f"Error: {str(e)}")

    # Display latest historical data
    historical_data = HistoricalPrice.objects.filter(
        stock_code='NIFTY',
        product_type='cash'
    ).order_by('-datetime')[:100]

    paginator = Paginator(historical_data, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'total_records': HistoricalPrice.objects.filter(
            stock_code='NIFTY',
            product_type='cash'
        ).count(),
    }
    return render(request, 'brokers/historical_data.html', context)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
@require_http_methods(["GET"])
def api_positions(request):
    """
    API endpoint to get all positions (Traders can access).
    """
    broker = request.GET.get('broker')
    query = BrokerPosition.objects.all()

    if broker:
        query = query.filter(broker=broker)

    positions = query.order_by('-fetched_at')[:100]

    data = [{
        'broker': p.get_broker_display(),
        'symbol': p.symbol,
        'net_quantity': p.net_quantity,
        'ltp': float(p.ltp),
        'average_price': float(p.average_price),
        'unrealized_pnl': float(p.unrealized_pnl),
        'realized_pnl': float(p.realized_pnl),
    } for p in positions]

    return JsonResponse({'positions': data})


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
@require_http_methods(["GET"])
def api_limits(request):
    """
    API endpoint to get latest limits for all brokers (Traders can access).
    """
    limits = {}

    for broker_code, broker_name in [('KOTAK', 'Kotak Neo'), ('ICICI', 'ICICI Breeze')]:
        latest = BrokerLimit.objects.filter(broker=broker_code).order_by('-fetched_at').first()
        if latest:
            limits[broker_code] = {
                'broker': broker_name,
                'margin_available': float(latest.margin_available),
                'margin_used': float(latest.margin_used),
                'fetched_at': latest.fetched_at.isoformat(),
            }

    return JsonResponse({'limits': limits})


# =============================================================================
# DASHBOARD VIEW
# =============================================================================

@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
def broker_dashboard(request):
    """
    Main dashboard showing overview of all brokers (Traders can access).
    """
    # Get latest limits for each broker
    kotak_limit = BrokerLimit.objects.filter(broker='KOTAK').order_by('-fetched_at').first()
    breeze_limit = BrokerLimit.objects.filter(broker='ICICI').order_by('-fetched_at').first()

    # Get recent positions
    kotak_positions = BrokerPosition.objects.filter(broker='KOTAK').order_by('-fetched_at')[:10]
    breeze_positions = BrokerPosition.objects.filter(broker='ICICI').order_by('-fetched_at')[:10]

    context = {
        'kotak_limit': kotak_limit,
        'breeze_limit': breeze_limit,
        'kotak_positions': kotak_positions,
        'breeze_positions': breeze_positions,
    }

    return render(request, 'brokers/dashboard.html', context)


# =============================================================================
# FUTURE TRADE VALIDATION VIEW
# =============================================================================

@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
def validate_future_trade(request):
    """
    Validate future trade logic by:
    1. Refreshing Trendlyne data
    2. Getting live ICICI data
    3. Running futures screening logic
    4. Showing step-by-step decisions
    5. Generating sample Telegram notification
    """
    from apps.strategies.strategies.icici_futures import (
        screen_futures_opportunities,
        execute_icici_futures_entry
    )
    from apps.data.models import TrendlyneData
    from apps.core.models import BrokerAccount
    from decimal import Decimal
    import json
    from datetime import datetime

    validation_steps = []
    telegram_message = ""
    trade_suggestion = None
    error = None

    try:
        # Step 1: Refresh Trendlyne Data
        validation_steps.append({
            'step': 1,
            'title': 'Refresh Trendlyne Data',
            'status': 'in_progress',
            'details': 'Checking Trendlyne database...'
        })

        trendlyne_count = TrendlyneData.objects.count()
        latest_trendlyne = TrendlyneData.objects.order_by('-updated_at').first()

        if latest_trendlyne:
            validation_steps[-1].update({
                'status': 'success',
                'details': f'Found {trendlyne_count} Trendlyne records. Latest update: {latest_trendlyne.updated_at.strftime("%Y-%m-%d %H:%M:%S")}'
            })
        else:
            validation_steps[-1].update({
                'status': 'warning',
                'details': 'No Trendlyne data found. Please run: python manage.py populate_trendlyne'
            })

        # Step 2: Get ICICI Account and Live Data
        validation_steps.append({
            'step': 2,
            'title': 'Connect to ICICI Breeze',
            'status': 'in_progress',
            'details': 'Fetching ICICI account and live market data...'
        })

        try:
            icici_account = BrokerAccount.objects.get(broker='ICICI', is_active=True)

            # Fetch latest limit data
            limit_rec, pos_list = fetch_and_save_breeze_data()

            validation_steps[-1].update({
                'status': 'success',
                'details': f'Connected to ICICI Breeze. Margin Available: ₹{limit_rec.margin_available:,.2f}, Active Positions: {len(pos_list)}'
            })
        except BrokerAccount.DoesNotExist:
            validation_steps[-1].update({
                'status': 'error',
                'details': 'No active ICICI account found. Please configure ICICI account in Django admin.'
            })
            raise Exception("ICICI account not configured")
        except Exception as e:
            validation_steps[-1].update({
                'status': 'error',
                'details': f'Failed to connect to ICICI: {str(e)}'
            })
            raise

        # Step 3: Screen Futures Opportunities
        validation_steps.append({
            'step': 3,
            'title': 'Screen Futures Opportunities (Multi-Factor Analysis)',
            'status': 'in_progress',
            'details': 'Running comprehensive screening: OI Analysis, Sector Alignment, Technical Indicators...'
        })

        screening_result = screen_futures_opportunities(icici_account)

        if screening_result['success'] and screening_result.get('opportunities'):
            opportunities = screening_result['opportunities']
            validation_steps[-1].update({
                'status': 'success',
                'details': f'Found {len(opportunities)} opportunities after multi-factor screening',
                'opportunities': opportunities[:5]  # Top 5 for display
            })

            # Step 4: Detailed Analysis of Top Candidate
            top_opportunity = opportunities[0]
            validation_steps.append({
                'step': 4,
                'title': 'Top Candidate Analysis',
                'status': 'in_progress',
                'details': f'Analyzing {top_opportunity["symbol"]} ({top_opportunity["direction"]})',
                'breakdown': {
                    'Symbol': top_opportunity['symbol'],
                    'Direction': top_opportunity['direction'],
                    'Composite Score': f"{top_opportunity['composite_score']:.1f}/100",
                    'OI Score': f"{top_opportunity.get('oi_score', 0):.1f}/40",
                    'Sector Score': f"{top_opportunity.get('sector_score', 0):.1f}/25",
                    'Technical Score': f"{top_opportunity.get('technical_score', 0):.1f}/35",
                    'OI Buildup': top_opportunity.get('oi_buildup_type', 'N/A'),
                    'PCR Ratio': f"{top_opportunity.get('pcr_ratio', 0):.2f}",
                    'Sector Alignment': top_opportunity.get('sector_alignment', 'N/A'),
                }
            })

            validation_steps[-1].update({'status': 'success'})

            # Step 5: Trade Recommendation Analysis
            validation_steps.append({
                'step': 5,
                'title': 'Trade Recommendation Summary',
                'status': 'success',
                'details': 'Based on multi-factor analysis, here is the recommendation:',
                'workflow': [
                    '✅ Morning Position Check: Would verify ONE POSITION RULE',
                    '✅ Entry Timing: Would validate 09:15-15:00 window',
                    '✅ Expiry Selection: Would select contract with 15+ days to expiry',
                    '⚠️ LLM Validation: Would require 70% confidence minimum',
                    '✅ Position Sizing: Would calculate based on 50% margin usage',
                    '✅ Risk Checks: Would verify daily/weekly limits',
                    '⚠️ Order Placement: SKIPPED (Validation mode - no actual order)'
                ],
                'trade_details': {
                    'Symbol': top_opportunity['symbol'],
                    'Direction': top_opportunity['direction'],
                    'Composite Score': f"{top_opportunity['composite_score']:.1f}/100",
                    'OI Buildup': top_opportunity.get('oi_buildup_type', 'N/A'),
                    'PCR Ratio': f"{top_opportunity.get('pcr_ratio', 0):.2f}",
                    'Sector Performance 3D': f"{top_opportunity.get('sector_3d', 0):.2f}%",
                    'Sector Performance 7D': f"{top_opportunity.get('sector_7d', 0):.2f}%",
                    'Sector Performance 21D': f"{top_opportunity.get('sector_21d', 0):.2f}%",
                    'RSI': f"{top_opportunity.get('rsi', 0):.1f}",
                    'LTP vs 200 DMA': f"{top_opportunity.get('ltp_vs_200dma', 0):.2f}%",
                    'Volume Score': f"{top_opportunity.get('volume_score', 0):.1f}",
                }
            })

            trade_suggestion = top_opportunity

            # Step 6: Generate Telegram Message
            validation_steps.append({
                'step': 6,
                'title': 'Generate Telegram Notification',
                'status': 'success',
                'details': 'Sample notification message generated'
            })

            telegram_message = f"""
🎯 **ICICI FUTURES TRADE VALIDATION**

📊 **Trade Details:**
Symbol: {top_opportunity['symbol']}
Direction: {top_opportunity['direction']}
Composite Score: {top_opportunity['composite_score']:.1f}/100

📈 **Multi-Factor Analysis:**
• OI Score: {top_opportunity.get('oi_score', 0):.1f}/40
  - Buildup Type: {top_opportunity.get('oi_buildup_type', 'N/A')}
  - PCR Ratio: {top_opportunity.get('pcr_ratio', 0):.2f}

• Sector Score: {top_opportunity.get('sector_score', 0):.1f}/25
  - 3D Performance: {top_opportunity.get('sector_3d', 0):.2f}%
  - 7D Performance: {top_opportunity.get('sector_7d', 0):.2f}%
  - 21D Performance: {top_opportunity.get('sector_21d', 0):.2f}%
  - Alignment: {top_opportunity.get('sector_alignment', 'N/A')}

• Technical Score: {top_opportunity.get('technical_score', 0):.1f}/35
  - RSI: {top_opportunity.get('rsi', 0):.1f}
  - LTP vs 200 DMA: {top_opportunity.get('ltp_vs_200dma', 0):.2f}%
  - Volume Score: {top_opportunity.get('volume_score', 0):.1f}

📋 **Entry Workflow (7 Steps):**
1. ✅ Morning Check: Verify ONE POSITION RULE
2. ✅ Entry Timing: Validate 09:15-15:00 window
3. ✅ Expiry Selection: Select 15+ days contract
4. ⚠️ LLM Validation: Requires 70% confidence
5. ✅ Position Sizing: Calculate based on 50% margin
6. ✅ Risk Checks: Verify daily/weekly limits
7. ⚠️ Order: VALIDATION MODE (no actual order)

💰 **Expected Trade Parameters:**
Entry Price: Market price at execution time
Quantity: Based on 50% margin usage
Stop Loss: 1.5% from entry (futures strategy default)
Target: 3:1 Risk:Reward ratio
Position Size: ~50% of available margin

⚠️ **IMPORTANT:**
This is a VALIDATION TEST only. No actual order has been placed.
In live trading, this opportunity would go through:
• Complete LLM validation (70% confidence required)
• Real-time price checks
• Actual position sizing calculations
• Risk limit verification
• Live order placement via broker API

Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        else:
            validation_steps[-1].update({
                'status': 'warning',
                'details': screening_result.get('message', 'No opportunities found after screening')
            })

            telegram_message = f"""
ℹ️ **ICICI FUTURES TRADE VALIDATION - NO OPPORTUNITIES**

Screening completed but no opportunities found.

Reason: {screening_result.get('message', 'No stocks passed the screening criteria')}

Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        messages.success(request, "Future trade validation completed successfully")

    except Exception as e:
        logger.exception(f"Error validating future trade: {e}")
        error = str(e)
        messages.error(request, f"Validation error: {error}")

        # Mark current step as failed
        if validation_steps and validation_steps[-1]['status'] == 'in_progress':
            validation_steps[-1]['status'] = 'error'

    context = {
        'validation_steps': validation_steps,
        'telegram_message': telegram_message,
        'trade_suggestion': trade_suggestion,
        'error': error,
        'timestamp': datetime.now(),
    }

    return render(request, 'brokers/validate_future_trade.html', context)
