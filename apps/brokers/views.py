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
from apps.brokers.models import BrokerLimit, BrokerPosition, OptionChainQuote, HistoricalPrice
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
    get_next_nifty_expiry
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
        return redirect('brokers:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")

            # Redirect to next or dashboard
            next_url = request.GET.get('next', 'brokers:dashboard')
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
    return redirect('brokers:login')


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
    Fetch and display option chain data (Traders can access).
    """
    stock_code = request.GET.get('stock_code', 'NIFTY')
    product_type = request.GET.get('product_type', 'options')

    try:
        expiry_date = get_next_nifty_expiry()

        if request.method == 'POST':
            # Fetch and save option chain
            quotes = get_and_save_option_chain_quotes(
                stock_code=stock_code,
                product_type=product_type
            )
            messages.success(request, f"Fetched {len(quotes)} option chain quotes")

        # Display latest option chain quotes
        quotes = OptionChainQuote.objects.filter(
            stock_code=stock_code,
            product_type=product_type
        ).order_by('-created_at', 'strike_price')[:500]

        context = {
            'quotes': quotes,
            'stock_code': stock_code,
            'product_type': product_type,
            'expiry_date': expiry_date,
        }
        return render(request, 'brokers/option_chain.html', context)

    except Exception as e:
        logger.exception(f"Error with option chain: {e}")
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
