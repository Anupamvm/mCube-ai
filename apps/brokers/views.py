"""
Broker views for mCube Trading System

This module contains views for broker authentication, data fetching, and display.
"""

from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db import models

from apps.core.models import CredentialStore
from apps.brokers.models import BrokerLimit, BrokerPosition, OptionChainQuote, HistoricalPrice, NiftyOptionChain
from apps.brokers.exceptions import BreezeAuthenticationError
from apps.data.models import OptionChain
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
# BREEZE AUTO-LOGIN DECORATOR
# =============================================================================

def breeze_auth_required(view_func):
    """
    Decorator that catches Breeze authentication errors and redirects to login page.

    When a BreezeAuthenticationError is raised (or any error containing 'session'
    or 'expired' keywords), this decorator:
    1. Logs the error
    2. Shows a user-friendly message
    3. Redirects to the Breeze login page with the current URL as 'next' parameter

    This enables automatic re-authentication flow across all Breeze-dependent views.

    Usage:
        @login_required
        @breeze_auth_required
        def my_view(request):
            # Uses Breeze API
            pass
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except BreezeAuthenticationError as e:
            logger.warning(f"Breeze auth error in {view_func.__name__}: {e}")
            return _handle_breeze_auth_error(request, str(e))
        except Exception as e:
            error_str = str(e).lower()
            # Check if this is a session/auth related error
            if any(keyword in error_str for keyword in ['session', 'expired', 'authentication', 'unauthorized', 'login']):
                logger.warning(f"Possible Breeze auth error in {view_func.__name__}: {e}")
                return _handle_breeze_auth_error(request, str(e))
            # Re-raise non-auth errors
            raise
    return wrapper


def _handle_breeze_auth_error(request, error_message):
    """
    Handle Breeze authentication error by redirecting to login page.

    For AJAX requests: Returns JSON with auth_required flag
    For regular requests: Redirects to Breeze login page with next URL
    """
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
       request.content_type == 'application/json' or \
       request.headers.get('Accept', '').startswith('application/json'):
        return JsonResponse({
            'success': False,
            'auth_required': True,
            'error': error_message,
            'message': 'Breeze session expired. Please re-authenticate.',
            'login_url': '/brokers/breeze/login/'
        }, status=401)

    # For regular page requests, redirect to login with next parameter
    messages.warning(
        request,
        f"Breeze session expired. Please complete auto-login to continue. ({error_message})"
    )

    # Build the login URL with next parameter
    current_url = request.get_full_path()
    login_url = f"/brokers/breeze/login/?{urlencode({'next': current_url})}"

    return redirect(login_url)


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
        limit_rec, pos_list, _ = fetch_and_save_kotakneo_data()
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

    Supports 'next' parameter for redirect after successful login/token entry.
    This enables automatic re-authentication flow when session expires.
    """
    # Get the return URL (where to redirect after successful login)
    next_url = request.POST.get('next') or request.GET.get('next')

    if request.method == 'POST':
        session_token = request.POST.get('session_token')
        if session_token:
            try:
                save_breeze_token(session_token)
                messages.success(request, "Session token saved successfully!")
                # Redirect to the original page if next_url is provided
                if next_url:
                    return redirect(next_url)
                return redirect('brokers:breeze_data')

            except Exception as e:
                logger.exception(f"Error saving Breeze token: {e}")
                messages.error(request, f"Error: {str(e)}")

    # Check if token is already valid
    token_valid = False
    session_expired = False
    try:
        status = get_or_prompt_breeze_token()
        if status == 'ready':
            token_valid = True
            # Only show message if not redirected from another page
            if not next_url:
                messages.info(request, "Session token is already valid for today.")
        else:
            # Session expired - user needs to re-authenticate
            session_expired = True
    except:
        session_expired = True

    # Check if auto-login credentials are configured
    creds = CredentialStore.objects.filter(service='breeze').first()
    auto_login_available = creds and creds.username and creds.password and creds.api_key

    return render(request, 'brokers/breeze_login.html', {
        'token_valid': token_valid,
        'auto_login_available': auto_login_available,
        'session_expired': session_expired,
        'next_url': next_url,
        'stored_username': creds.username if creds else '',
        'api_key': creds.api_key if creds else '',
    })


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
def breeze_update_credentials(request):
    """
    Update Breeze auto-login credentials (username/password) from the web UI
    and immediately trigger auto-login.

    This allows users to set up and login in one seamless step.
    """
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()
    next_url = request.POST.get('next', '')
    auto_login = request.POST.get('auto_login', 'true') == 'true'

    if not username or not password:
        messages.error(request, "Both username and password are required.")
        return redirect('brokers:breeze_login')

    try:
        # Get or create the breeze credentials
        creds = CredentialStore.objects.filter(service='breeze').first()

        if not creds:
            messages.error(request, "Breeze API credentials not found. Please set up API key first.")
            return redirect('brokers:breeze_login')

        # Update the username and password
        creds.username = username
        creds.password = password
        creds.save()

        messages.success(request, "Credentials saved successfully!")
        logger.info(f"Breeze auto-login credentials updated for user: {request.user}")

        # If auto_login is requested, trigger it immediately
        if auto_login:
            try:
                from apps.brokers.services.breeze_auto_login import auto_login_breeze

                # Run the auto-login process (skip validation since we know token is expired)
                success, message = auto_login_breeze(
                    headless=False, timeout=300, skip_validation=True,
                    task_name="credential update login"
                )

                if success:
                    messages.success(request, f"Auto-login successful! {message}")
                    # Redirect to the original page
                    if next_url:
                        return redirect(next_url)
                    return redirect('brokers:breeze_data')
                else:
                    messages.error(request, f"Auto-login failed: {message}")

            except ImportError as e:
                logger.exception(f"Selenium not installed: {e}")
                messages.error(request, "Auto-login requires Selenium. Install with: pip install selenium")

            except Exception as e:
                logger.exception(f"Error in auto-login: {e}")
                messages.error(request, f"Auto-login error: {str(e)}")

    except Exception as e:
        logger.exception(f"Error updating Breeze credentials: {e}")
        messages.error(request, f"Error saving credentials: {str(e)}")

    # Redirect back to login page (with next parameter if provided)
    if next_url:
        return redirect(f"/brokers/breeze/login/?next={next_url}")
    return redirect('brokers:breeze_login')


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
def breeze_auto_login(request):
    """
    Automated Breeze login using Selenium (Admin only).

    Opens browser, fills credentials, waits for OTP, captures session token.

    Supports 'next' parameter for redirect after successful login.
    This enables automatic re-authentication flow when session expires.
    """
    if request.method != 'POST':
        return redirect('brokers:breeze_login')

    # Get the return URL (where to redirect after successful login)
    next_url = request.POST.get('next') or request.GET.get('next') or 'brokers:breeze_data'

    try:
        from apps.brokers.services.breeze_auto_login import auto_login_breeze

        # Run the auto-login process
        success, message = auto_login_breeze(
            headless=False, timeout=300,
            task_name="web UI login"
        )

        if success:
            messages.success(request, message)
            # Redirect to the original page user was trying to access
            if next_url.startswith('/'):
                return redirect(next_url)
            return redirect(next_url)
        else:
            messages.error(request, f"Auto-login failed: {message}")

    except ImportError as e:
        logger.exception(f"Selenium not installed: {e}")
        messages.error(request, "Auto-login requires Selenium. Install with: pip install selenium")

    except Exception as e:
        logger.exception(f"Error in Breeze auto-login: {e}")
        messages.error(request, f"Auto-login error: {str(e)}")

    return redirect('brokers:breeze_login')


@login_required
@require_http_methods(["GET"])
def breeze_session_status(request):
    """
    API endpoint to check Breeze session status.

    Uses centralized BreezeSessionManager for consistent status checks.

    Returns:
        JsonResponse: {
            'valid': bool,
            'auto_login_available': bool,
            'login_url': str,
            'message': str,
            'last_update': datetime or null
        }
    """
    from apps.brokers.services.breeze_session import check_breeze_session

    try:
        status = check_breeze_session()
        return JsonResponse(status)

    except Exception as e:
        logger.exception(f"Error checking Breeze session status: {e}")
        return JsonResponse({
            'valid': False,
            'auto_login_available': False,
            'message': str(e),
            'login_url': '/brokers/breeze/login/'
        })


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
@breeze_auth_required
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

    except BreezeAuthenticationError:
        # Re-raise auth errors so the decorator can handle them
        raise
    except Exception as e:
        # Check if this is a session/auth error and re-raise it
        error_str = str(e).lower()
        if any(keyword in error_str for keyword in ['session', 'expired', 'authentication', 'unauthorized']):
            raise BreezeAuthenticationError(str(e), original_error=e)
        logger.exception(f"Error fetching Breeze data: {e}")
        messages.error(request, f"Error: {str(e)}")
        return redirect('brokers:breeze_login')


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
@breeze_auth_required
def nifty_quote(request):
    """
    Get current NIFTY spot price (Traders can access).
    """
    try:
        quote = get_nifty_quote()
        return JsonResponse(quote if quote else {'error': 'Failed to fetch quote'})
    except BreezeAuthenticationError:
        # Re-raise auth errors so the decorator can handle them
        raise
    except Exception as e:
        # Check if this is a session/auth error and re-raise it
        error_str = str(e).lower()
        if any(keyword in error_str for keyword in ['session', 'expired', 'authentication', 'unauthorized']):
            raise BreezeAuthenticationError(str(e), original_error=e)
        logger.exception(f"Error fetching NIFTY quote: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
@breeze_auth_required
def breeze_option_chain(request):
    """
    Fetch and display NIFTY option chain data for all expiries (Traders can access).
    """
    try:
        if request.method == 'POST':
            # Fetch and save NIFTY option chain for all expiries
            total_saved = fetch_and_save_nifty_option_chain_all_expiries()
            messages.success(request, f"Fetched and saved {total_saved} NIFTY option chain records across all expiries")

        # Get all unique expiry dates for NIFTY
        expiry_dates = OptionChain.objects.filter(
            underlying='NIFTY'
        ).values_list('expiry_date', flat=True).distinct().order_by('expiry_date')

        # Get selected expiry or use first one
        selected_expiry = request.GET.get('expiry')
        if selected_expiry:
            from datetime import datetime
            # Handle both '%Y-%m-%d' format (from form) and date object (from template)
            if isinstance(selected_expiry, str):
                try:
                    # Try parsing as date string
                    selected_expiry = datetime.strptime(selected_expiry, '%Y-%m-%d').date()
                except ValueError:
                    # If that fails, it might already be a date object passed as string
                    logger.warning(f"Could not parse expiry date '{selected_expiry}', using first available expiry")
                    selected_expiry = expiry_dates[0] if expiry_dates else None
        elif expiry_dates:
            selected_expiry = expiry_dates[0]
        else:
            selected_expiry = None

        # Fetch option chain data for selected expiry
        option_chain = []
        spot_price = None
        if selected_expiry:
            # Get all option chain records for this expiry (CE and PE separately)
            all_ce_options = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=selected_expiry,
                option_type='CE'
            ).order_by('strike')

            all_pe_options = OptionChain.objects.filter(
                underlying='NIFTY',
                expiry_date=selected_expiry,
                option_type='PE'
            ).order_by('strike')

            if all_ce_options or all_pe_options:
                # Get spot price from first record (could be CE or PE)
                spot_price = (all_ce_options[0].spot_price if all_ce_options else
                             all_pe_options[0].spot_price if all_pe_options else None)

                # Get all unique strikes
                ce_strikes = {opt.strike for opt in all_ce_options}
                pe_strikes = {opt.strike for opt in all_pe_options}
                all_strikes = sorted(ce_strikes | pe_strikes)

                if spot_price and all_strikes:
                    # Find the strike closest to spot price
                    from decimal import Decimal
                    min_diff = None
                    closest_index = 0

                    for idx, strike in enumerate(all_strikes):
                        diff = abs(strike - spot_price)
                        if min_diff is None or diff < min_diff:
                            min_diff = diff
                            closest_index = idx

                    # Get 50 strikes above and 50 below the closest strike
                    start_index = max(0, closest_index - 50)
                    end_index = min(len(all_strikes), closest_index + 51)  # +51 to include 50 above

                    selected_strikes = all_strikes[start_index:end_index]

                    # Create option chain data organized by strike with both CE and PE
                    ce_dict = {opt.strike: opt for opt in all_ce_options if opt.strike in selected_strikes}
                    pe_dict = {opt.strike: opt for opt in all_pe_options if opt.strike in selected_strikes}

                    # Build combined records
                    for strike in selected_strikes:
                        ce_opt = ce_dict.get(strike)
                        pe_opt = pe_dict.get(strike)

                        # Create a combined object for template
                        combined = type('obj', (object,), {
                            'strike_price': strike,
                            'spot_price': spot_price,
                            # Call data
                            'call_ltp': ce_opt.ltp if ce_opt else Decimal('0.00'),
                            'call_bid': ce_opt.bid if ce_opt else Decimal('0.00'),
                            'call_ask': ce_opt.ask if ce_opt else Decimal('0.00'),
                            'call_oi': ce_opt.oi if ce_opt else 0,
                            'call_volume': ce_opt.volume if ce_opt else 0,
                            # Put data
                            'put_ltp': pe_opt.ltp if pe_opt else Decimal('0.00'),
                            'put_bid': pe_opt.bid if pe_opt else Decimal('0.00'),
                            'put_ask': pe_opt.ask if pe_opt else Decimal('0.00'),
                            'put_oi': pe_opt.oi if pe_opt else 0,
                            'put_volume': pe_opt.volume if pe_opt else 0,
                        })()
                        option_chain.append(combined)

        context = {
            'option_chain': option_chain,
            'expiry_dates': expiry_dates,
            'selected_expiry': selected_expiry,
            'spot_price': spot_price,
            'total_records': OptionChain.objects.filter(underlying='NIFTY').count(),
        }
        return render(request, 'brokers/option_chain.html', context)

    except BreezeAuthenticationError:
        # Re-raise auth errors so the decorator can handle them
        raise
    except Exception as e:
        # Check if this is a session/auth error and re-raise it
        error_str = str(e).lower()
        if any(keyword in error_str for keyword in ['session', 'expired', 'authentication', 'unauthorized']):
            raise BreezeAuthenticationError(str(e), original_error=e)
        logger.exception(f"Error with NIFTY option chain: {e}")
        messages.error(request, f"Error: {str(e)}")
        return render(request, 'brokers/option_chain.html', {'error': str(e)})


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
@breeze_auth_required
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
        except BreezeAuthenticationError:
            # Re-raise auth errors so the decorator can handle them
            raise
        except Exception as e:
            # Check if this is a session/auth error and re-raise it
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ['session', 'expired', 'authentication', 'unauthorized']):
                raise BreezeAuthenticationError(str(e), original_error=e)
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
    API endpoint to get positions from BrokerPosition model (Traders can access).
    Note: For live positions with accurate P&L, use /trading/api/get-positions/ instead.
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

# =============================================================================
# HISTORICAL TRADE SYNC VIEWS
# =============================================================================

@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
def trade_sync_dashboard(request):
    """
    Dashboard for syncing historical trades from broker APIs.
    Shows sync status and provides action buttons for manual sync.
    """
    from apps.brokers.models import BrokerTradeHistory
    from apps.accounts.models import BrokerAccount
    from apps.brokers.services.trade_sync import TradeSyncService
    from datetime import date, timedelta

    # Get all active accounts
    accounts = BrokerAccount.objects.filter(is_active=True)

    # Get sync status for each account
    sync_status = []
    for account in accounts:
        status = TradeSyncService.get_sync_status(account)
        trade_count = BrokerTradeHistory.objects.filter(account=account).count()

        # Get date range of synced trades
        first_trade = BrokerTradeHistory.objects.filter(account=account).order_by('trade_date').first()
        last_trade = BrokerTradeHistory.objects.filter(account=account).order_by('-trade_date').first()

        sync_status.append({
            'account': account,
            'total_trades': trade_count,
            'last_sync': status['last_sync'],
            'unreconciled': status['unreconciled_count'],
            'is_syncing': status['is_syncing'],
            'first_trade_date': first_trade.trade_date if first_trade else None,
            'last_trade_date': last_trade.trade_date if last_trade else None,
        })

    # Default date range (last 1 year)
    default_from = date.today() - timedelta(days=365)
    default_to = date.today()

    context = {
        'sync_status': sync_status,
        'accounts': accounts,
        'default_from': default_from.strftime('%Y-%m-%d'),
        'default_to': default_to.strftime('%Y-%m-%d'),
    }

    return render(request, 'brokers/trade_sync_dashboard.html', context)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
def api_sync_trades(request):
    """
    API endpoint to sync trades from broker APIs.

    POST params:
        - broker: 'BREEZE', 'NEO', or 'BOTH'
        - from_date: Start date (YYYY-MM-DD)
        - to_date: End date (YYYY-MM-DD)
        - account_id: Optional specific account ID
    """
    import json
    from apps.brokers.services.trade_sync import TradeSyncService
    from apps.accounts.models import BrokerAccount
    from apps.core.constants import BROKER_KOTAK, BROKER_ICICI
    from datetime import datetime

    try:
        # Parse request data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        broker = data.get('broker', 'BOTH').upper()
        from_date_str = data.get('from_date')
        to_date_str = data.get('to_date')
        account_id = data.get('account_id')

        # Validate dates
        if not from_date_str or not to_date_str:
            return JsonResponse({
                'success': False,
                'error': 'from_date and to_date are required'
            }, status=400)

        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()

        if from_date > to_date:
            return JsonResponse({
                'success': False,
                'error': 'from_date cannot be after to_date'
            }, status=400)

        results = []

        # Determine which accounts to sync
        if account_id:
            accounts = BrokerAccount.objects.filter(id=account_id, is_active=True)
        else:
            if broker == 'BREEZE':
                accounts = BrokerAccount.objects.filter(broker=BROKER_ICICI, is_active=True)
            elif broker == 'NEO':
                accounts = BrokerAccount.objects.filter(broker=BROKER_KOTAK, is_active=True)
            else:  # BOTH
                accounts = BrokerAccount.objects.filter(is_active=True)

        # Sync each account
        for account in accounts:
            logger.info(f"Syncing trades for {account.account_name} from {from_date} to {to_date}")

            result = TradeSyncService.sync_trades_for_date_range(
                account=account,
                from_date=from_date,
                to_date=to_date
            )

            results.append({
                'account_id': account.id,
                'account_name': account.account_name,
                'broker': account.get_broker_display(),
                'success': result['success'],
                'new_count': result['new_count'],
                'updated_count': result['updated_count'],
                'total_fetched': result['total_fetched'],
                'errors': result['errors']
            })

        # Calculate totals
        total_new = sum(r['new_count'] for r in results)
        total_updated = sum(r['updated_count'] for r in results)
        total_fetched = sum(r['total_fetched'] for r in results)
        all_success = all(r['success'] for r in results)

        return JsonResponse({
            'success': all_success,
            'message': f"Synced {total_new} new trades, {total_updated} updated from {total_fetched} total",
            'results': results,
            'totals': {
                'new': total_new,
                'updated': total_updated,
                'fetched': total_fetched
            }
        })

    except Exception as e:
        logger.exception(f"Error syncing trades: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
@breeze_auth_required
def api_sync_breeze_trades(request):
    """
    Sync trades specifically from ICICI Breeze.
    Supports date range for historical sync.
    """
    import json
    from apps.brokers.services.trade_sync import TradeSyncService
    from apps.accounts.models import BrokerAccount
    from apps.core.constants import BROKER_ICICI
    from datetime import datetime, date, timedelta

    try:
        # Parse request data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        from_date_str = data.get('from_date')
        to_date_str = data.get('to_date')

        # Default to last 365 days if not provided
        if from_date_str:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        else:
            from_date = date.today() - timedelta(days=365)

        if to_date_str:
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        else:
            to_date = date.today()

        # Get ICICI account
        account = BrokerAccount.objects.filter(broker=BROKER_ICICI, is_active=True).first()
        if not account:
            return JsonResponse({
                'success': False,
                'error': 'No active ICICI Breeze account found'
            }, status=404)

        # Sync trades
        result = TradeSyncService.sync_trades_for_date_range(
            account=account,
            from_date=from_date,
            to_date=to_date
        )

        return JsonResponse({
            'success': result['success'],
            'message': f"Synced {result['new_count']} new, {result['updated_count']} updated from Breeze",
            'new_count': result['new_count'],
            'updated_count': result['updated_count'],
            'total_fetched': result['total_fetched'],
            'errors': result['errors'],
            'date_range': {
                'from': from_date.strftime('%Y-%m-%d'),
                'to': to_date.strftime('%Y-%m-%d')
            }
        })

    except Exception as e:
        logger.exception(f"Error syncing Breeze trades: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
def api_sync_neo_trades(request):
    """
    Sync trades from Kotak Neo.
    The Neo trade_report() API returns all available trades with fill dates.
    """
    from apps.brokers.services.trade_sync import TradeSyncService
    from apps.accounts.models import BrokerAccount
    from apps.core.constants import BROKER_KOTAK
    from datetime import date

    try:
        # Get Kotak Neo account
        account = BrokerAccount.objects.filter(broker=BROKER_KOTAK, is_active=True).first()
        if not account:
            return JsonResponse({
                'success': False,
                'error': 'No active Kotak Neo account found'
            }, status=404)

        # Sync trades from Neo
        result = TradeSyncService.sync_today_trades(account)

        return JsonResponse({
            'success': result['success'],
            'message': f"Synced {result['new_count']} new, {result['updated_count']} updated from Neo",
            'new_count': result['new_count'],
            'updated_count': result['updated_count'],
            'total_fetched': result['total_fetched'],
            'errors': result['errors'],
            'date': date.today().strftime('%Y-%m-%d')
        })

    except Exception as e:
        logger.exception(f"Error syncing Neo trades: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["GET"])
def api_trade_sync_status(request):
    """
    Get sync status for all accounts.
    """
    from apps.brokers.models import BrokerTradeHistory
    from apps.accounts.models import BrokerAccount
    from apps.brokers.services.trade_sync import TradeSyncService

    try:
        accounts = BrokerAccount.objects.filter(is_active=True)
        status_list = []

        for account in accounts:
            status = TradeSyncService.get_sync_status(account)

            # Get date range
            first_trade = BrokerTradeHistory.objects.filter(account=account).order_by('trade_date').first()
            last_trade = BrokerTradeHistory.objects.filter(account=account).order_by('-trade_date').first()

            status_list.append({
                'account_id': account.id,
                'account_name': account.account_name,
                'broker': account.get_broker_display(),
                'total_trades': status['total_records'],
                'last_sync': status['last_sync'].isoformat() if status['last_sync'] else None,
                'unreconciled': status['unreconciled_count'],
                'is_syncing': status['is_syncing'],
                'first_trade_date': first_trade.trade_date.strftime('%Y-%m-%d') if first_trade and first_trade.trade_date else None,
                'last_trade_date': last_trade.trade_date.strftime('%Y-%m-%d') if last_trade and last_trade.trade_date else None,
            })

        return JsonResponse({
            'success': True,
            'accounts': status_list
        })

    except Exception as e:
        logger.exception(f"Error getting sync status: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
@breeze_auth_required
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
    from apps.data.models import ContractData, TLStockData
    from apps.accounts.models import BrokerAccount
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

        # Check both Contract and Stock data
        contract_count = ContractData.objects.count()
        stock_count = TLStockData.objects.count()
        trendlyne_count = contract_count + stock_count

        latest_contract = ContractData.objects.order_by('-updated_at').first()
        latest_stock = TLStockData.objects.order_by('-updated_at').first()
        latest_trendlyne = latest_contract if latest_contract else latest_stock

        if latest_trendlyne:
            validation_steps[-1].update({
                'status': 'success',
                'details': f'Found {trendlyne_count} Trendlyne records ({contract_count} contracts, {stock_count} stocks). Latest update: {latest_trendlyne.updated_at.strftime("%Y-%m-%d %H:%M:%S")}'
            })
        else:
            validation_steps[-1].update({
                'status': 'warning',
                'details': 'No Trendlyne data found. Please populate Trendlyne data first.'
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

    except BreezeAuthenticationError:
        # Re-raise auth errors so the decorator can handle them
        raise
    except Exception as e:
        # Check if this is a session/auth error and re-raise it
        error_str = str(e).lower()
        if any(keyword in error_str for keyword in ['session', 'expired', 'authentication', 'unauthorized']):
            raise BreezeAuthenticationError(str(e), original_error=e)
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


# =============================================================================
# CSV UPLOAD VIEWS
# =============================================================================

@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
def csv_upload_dashboard(request):
    """
    Dashboard for uploading CSV trade history files.
    Shows upload form, recent imports, and summary stats.
    """
    from apps.brokers.models import BrokerContractPnL, CSVImportLog
    from apps.brokers.forms import CSVUploadForm
    from django.db.models import Sum, Count

    # Get recent imports
    recent_imports = CSVImportLog.objects.all()[:10]

    # Get summary stats
    total_imports = CSVImportLog.objects.filter(status='SUCCESS').count()

    kotak_summary = BrokerContractPnL.objects.filter(broker='KOTAK').aggregate(
        total_records=Count('id'),
        futures_pnl=Sum('net_pnl', filter=models.Q(segment='FUTURES')),
        options_pnl=Sum('net_pnl', filter=models.Q(segment='OPTIONS')),
        total_pnl=Sum('net_pnl'),
    )

    breeze_summary = BrokerContractPnL.objects.filter(broker='ICICI').aggregate(
        total_records=Count('id'),
        futures_pnl=Sum('net_pnl', filter=models.Q(segment='FUTURES')),
        options_pnl=Sum('net_pnl', filter=models.Q(segment='OPTIONS')),
        total_pnl=Sum('net_pnl'),
    )

    context = {
        'form': CSVUploadForm(),
        'recent_imports': recent_imports,
        'total_imports': total_imports,
        'kotak_summary': kotak_summary,
        'breeze_summary': breeze_summary,
    }

    return render(request, 'brokers/csv_upload_dashboard.html', context)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST"])
def api_upload_csv(request):
    """
    API endpoint to upload and process multiple CSV files.
    Duplicate detection happens at the data level - same contracts are updated, not duplicated.
    Users can freely re-upload any files.
    """
    import json
    from apps.brokers.forms import CSVUploadForm
    from apps.brokers.services.csv_importers import KotakFNOImporter, BreezeFNOImporter

    try:
        form = CSVUploadForm(request.POST, request.FILES)

        if not form.is_valid():
            return JsonResponse({
                'success': False,
                'error': 'Invalid form data',
                'errors': form.errors,
            }, status=400)

        file_type = form.cleaned_data['file_type']
        csv_files = form.cleaned_data['csv_files']

        # Select importer based on file type
        if file_type == 'kotak_fno':
            importer_class = KotakFNOImporter
        elif file_type == 'breeze_fno':
            importer_class = BreezeFNOImporter
        else:
            return JsonResponse({
                'success': False,
                'error': f'Unknown file type: {file_type}',
            }, status=400)

        # Process each file - no filename restrictions, duplicates handled at data level
        # Incremental upload: only new records are created, only changed records are updated
        results = []
        total_created = 0
        total_updated = 0
        total_skipped = 0
        total_unchanged = 0
        all_errors = []

        for csv_file in csv_files:
            logger.info(f"Processing {file_type} CSV upload: {csv_file.name}")

            # Create a new importer instance for each file
            importer = importer_class()
            result = importer.import_file(csv_file, user=request.user)

            results.append({
                'filename': csv_file.name,
                'success': result['success'],
                'batch_id': result.get('batch_id'),
                'records_created': result.get('records_created', 0),
                'records_updated': result.get('records_updated', 0),
                'records_skipped': result.get('records_skipped', 0),
                'records_unchanged': result.get('records_unchanged', 0),
                'errors': result.get('errors', []),
            })

            if result['success']:
                total_created += result.get('records_created', 0)
                total_updated += result.get('records_updated', 0)
                total_skipped += result.get('records_skipped', 0)
                total_unchanged += result.get('records_unchanged', 0)

            if result.get('errors'):
                all_errors.extend([f"{csv_file.name}: {err}" for err in result['errors'][:5]])

        # Build response message
        files_processed = len(results)
        files_successful = sum(1 for r in results if r['success'])

        return JsonResponse({
            'success': files_successful > 0,
            'message': f"Processed {files_processed} file(s): {files_successful} successful, {files_processed - files_successful} failed",
            'files_processed': files_processed,
            'files_successful': files_successful,
            'records_created': total_created,
            'records_updated': total_updated,
            'records_skipped': total_skipped,
            'records_unchanged': total_unchanged,
            'errors': all_errors,
            'results': results,
        })

    except Exception as e:
        logger.exception(f"Error processing CSV upload: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["POST", "DELETE"])
def api_delete_import_batch(request, batch_id):
    """
    API endpoint to delete an import batch and all its records.
    """
    from apps.brokers.services.csv_importers import delete_import_batch

    try:
        result = delete_import_batch(batch_id)

        if result['success']:
            return JsonResponse({
                'success': True,
                'message': f"Deleted {result['records_deleted']} records from batch {batch_id}",
                'records_deleted': result['records_deleted'],
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Delete failed'),
            }, status=400)

    except Exception as e:
        logger.exception(f"Error deleting batch {batch_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
@require_http_methods(["GET"])
def api_import_logs(request):
    """
    API endpoint to get recent import logs.
    """
    from apps.brokers.models import CSVImportLog

    try:
        limit = int(request.GET.get('limit', 20))
        logs = CSVImportLog.objects.all()[:limit]

        data = [{
            'batch_id': log.import_batch_id,
            'file_type': log.file_type,
            'file_type_display': log.get_file_type_display(),
            'original_filename': log.original_filename,
            'status': log.status,
            'status_display': log.get_status_display(),
            'records_created': log.records_created,
            'records_updated': log.records_updated,
            'records_skipped': log.records_skipped,
            'errors': log.errors,
            'imported_by': log.imported_by.username if log.imported_by else None,
            'created_at': log.created_at.isoformat(),
        } for log in logs]

        return JsonResponse({
            'success': True,
            'logs': data,
        })

    except Exception as e:
        logger.exception(f"Error fetching import logs: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
@require_http_methods(["GET"])
def api_imported_pnl_summary(request):
    """
    API endpoint to get summary of imported contract P&L.
    Also returns list of contracts for display in dashboard.

    Query params:
    - broker: Filter by broker (KOTAK, ICICI)
    - segment: Filter by segment (FUTURES, OPTIONS)
    - symbol: Filter by symbol
    - pnl: Filter by P&L (winners, losers)
    - month: Filter by expiry month (YYYY-MM format)
    - limit: Max contracts to return (default: 500)
    """
    from apps.brokers.models import BrokerContractPnL
    from django.db.models import Sum, Count

    try:
        # Get filter parameters
        broker = request.GET.get('broker')
        segment = request.GET.get('segment')
        symbol = request.GET.get('symbol')
        pnl_filter = request.GET.get('pnl')
        month = request.GET.get('month')
        limit = int(request.GET.get('limit', 500))

        queryset = BrokerContractPnL.objects.all()

        # Apply filters
        if broker and broker not in ('all', 'ALL'):
            queryset = queryset.filter(broker=broker)

        if segment and segment not in ('all', 'ALL'):
            queryset = queryset.filter(segment=segment)

        if symbol and symbol not in ('all', 'ALL'):
            queryset = queryset.filter(symbol=symbol)

        if pnl_filter == 'winners':
            queryset = queryset.filter(net_pnl__gt=0)
        elif pnl_filter == 'losers':
            queryset = queryset.filter(net_pnl__lt=0)

        if month and month not in ('all', 'ALL'):
            # month format: YYYY-MM
            try:
                year, month_num = month.split('-')
                queryset = queryset.filter(
                    expiry_date__year=int(year),
                    expiry_date__month=int(month_num)
                )
            except (ValueError, AttributeError):
                pass

        # Aggregate by broker and segment
        summary = queryset.values('broker', 'segment').annotate(
            total_records=Count('id'),
            total_pnl=Sum('net_pnl'),
            total_charges=Sum('total_charges'),
            total_buy=Sum('buy_amount'),
            total_sell=Sum('sell_amount'),
        ).order_by('broker', 'segment')

        # Overall totals (after filters applied)
        overall = queryset.aggregate(
            total_records=Count('id'),
            total_pnl=Sum('net_pnl'),
            total_charges=Sum('total_charges'),
        )

        # Get list of contracts for display (ordered by net_pnl desc)
        contracts = list(queryset.order_by('-net_pnl').values(
            'symbol', 'trading_symbol', 'segment', 'broker',
            'expiry_date', 'net_pnl', 'gross_pnl', 'total_charges',
            'option_type', 'strike_price'
        )[:limit])

        # Convert dates and decimals for JSON
        for c in contracts:
            c['net_pnl'] = float(c['net_pnl'] or 0)
            c['gross_pnl'] = float(c['gross_pnl'] or 0)
            c['total_charges'] = float(c['total_charges'] or 0)
            c['strike_price'] = float(c['strike_price']) if c['strike_price'] else None
            c['expiry_date'] = c['expiry_date'].strftime('%Y-%m-%d') if c['expiry_date'] else None

        # Get all unique symbols and months for filter dropdowns (from ALL contracts, not filtered)
        all_contracts = BrokerContractPnL.objects.all()
        all_symbols = sorted(list(all_contracts.values_list('symbol', flat=True).distinct()))
        all_months = sorted(list(all_contracts.exclude(expiry_date__isnull=True)
                                 .values_list('expiry_date', flat=True)
                                 .distinct()), reverse=True)
        # Convert months to YYYY-MM format
        unique_months = sorted(list(set(
            d.strftime('%Y-%m') for d in all_months if d
        )), reverse=True)

        # Count winners/losers in filtered results
        winners_count = queryset.filter(net_pnl__gt=0).count()
        losers_count = queryset.filter(net_pnl__lt=0).count()

        return JsonResponse({
            'success': True,
            'summary': list(summary),
            'overall': {
                **overall,
                'winners_count': winners_count,
                'losers_count': losers_count,
            },
            'contracts': contracts,
            'filter_options': {
                'symbols': all_symbols,
                'months': unique_months,
            }
        })

    except Exception as e:
        logger.exception(f"Error fetching imported P&L summary: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)
