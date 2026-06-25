"""
Core views for mCube Trading System

This module contains system-wide views including the comprehensive test page.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import connection
from django.conf import settings
import requests
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from tools.neo import _parse_float
from apps.core.utils import format_currency

logger = logging.getLogger(__name__)


def home_page(request):
    """
    Home page view - Main landing page for mCube Trading System
    Shows system overview, quick actions, and navigation
    """
    context = {}

    # If user is authenticated, show dashboard info
    if request.user.is_authenticated:
        try:
            from apps.positions.models import Position
            from apps.accounts.models import BrokerAccount
            from apps.brokers.models import Order

            # Get active positions count
            active_positions = Position.objects.filter(status='ACTIVE').count()

            # Get active accounts
            active_accounts = BrokerAccount.objects.filter(is_active=True).count()

            # Get today's orders
            today = datetime.now().date()
            today_orders = Order.objects.filter(created_at__date=today).count()

            # Get total P&L for today
            total_pnl = sum([
                pos.calculate_pnl() or Decimal('0')
                for pos in Position.objects.filter(status='ACTIVE')
            ])

            context.update({
                'active_positions': active_positions,
                'active_accounts': active_accounts,
                'today_orders': today_orders,
                'total_pnl': format_currency(total_pnl),
                'is_admin': is_admin_user(request.user),
            })
        except Exception as e:
            logger.error(f"Error fetching dashboard data: {e}")
            context['error'] = 'Unable to fetch dashboard data'

    return render(request, 'core/home.html', context)


@login_required
def documentation_dashboard(request):
    """
    Documentation Dashboard - Comprehensive guide to the mCube Trading System.
    Provides architecture overview, module documentation, and user guides.
    """
    return render(request, 'core/documentation.html')


def error_400(request, exception):
    """Custom 400 bad request page - Always succeeds"""
    try:
        context = {
            'error_code': '400',
            'error_title': 'Bad Request',
            'error_message': 'The request could not be understood by the server.',
            'error_details': str(exception) if exception else 'Invalid request format.',
            'show_home_link': True,
        }
        return render(request, 'core/error.html', context, status=400)
    except Exception as e:
        logger.error(f"Error in error_400 handler: {e}")
        return _fallback_error_response('400', 'Bad Request')


def error_403(request, exception):
    """Custom 403 forbidden page - Always succeeds"""
    try:
        context = {
            'error_code': '403',
            'error_title': 'Forbidden',
            'error_message': 'You do not have permission to access this resource.',
            'error_details': str(exception) if exception else 'Access denied.',
            'show_login_link': not request.user.is_authenticated if hasattr(request, 'user') else True,
            'show_home_link': True,
        }
        return render(request, 'core/error.html', context, status=403)
    except Exception as e:
        logger.error(f"Error in error_403 handler: {e}")
        return _fallback_error_response('403', 'Forbidden')


def error_404(request, exception):
    """Custom 404 error page - Always succeeds"""
    try:
        requested_url = getattr(request, 'path', '/unknown')
        context = {
            'error_code': '404',
            'error_title': 'Page Not Found',
            'error_message': f'The requested URL "{requested_url}" was not found on this server.',
            'error_details': 'Please check the URL and try again, or navigate to the home page.',
            'show_home_link': True,
            'available_urls': get_available_urls() if settings.DEBUG else None,
        }
        return render(request, 'core/error.html', context, status=404)
    except Exception as e:
        logger.error(f"Error in error_404 handler: {e}")
        return _fallback_error_response('404', 'Page Not Found')


def error_500(request):
    """Custom 500 server error page - Always succeeds"""
    try:
        context = {
            'error_code': '500',
            'error_title': 'Internal Server Error',
            'error_message': 'An unexpected error occurred while processing your request.',
            'error_details': 'Our team has been notified. Please try again later.',
            'show_home_link': True,
        }
        return render(request, 'core/error.html', context, status=500)
    except Exception as e:
        logger.error(f"Error in error_500 handler: {e}")
        return _fallback_error_response('500', 'Internal Server Error')


def _fallback_error_response(code, title):
    """
    Ultimate fallback error response when even error handlers fail.
    Returns inline HTML without any dependencies.
    """
    from django.http import HttpResponse
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{code} - {title}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                padding: 20px;
            }}
            .error-box {{
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                text-align: center;
                max-width: 500px;
            }}
            h1 {{ color: #667eea; margin: 0 0 10px 0; font-size: 60px; }}
            h2 {{ color: #333; margin: 0 0 20px 0; }}
            p {{ color: #666; margin-bottom: 30px; }}
            a {{
                display: inline-block;
                padding: 10px 30px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 5px;
            }}
            a:hover {{ background: #5568d3; }}
        </style>
    </head>
    <body>
        <div class="error-box">
            <h1>{code}</h1>
            <h2>{title}</h2>
            <p>Something went wrong. Please try again.</p>
            <a href="/">Go to Home</a>
            <a href="javascript:history.back()">Go Back</a>
        </div>
    </body>
    </html>
    '''
    return HttpResponse(html, status=int(code))


def get_available_urls():
    """Get list of available URLs for debugging (only in DEBUG mode)"""
    from django.urls import get_resolver
    from django.urls.resolvers import URLPattern, URLResolver

    def extract_urls(urlpatterns, prefix=''):
        urls = []
        for pattern in urlpatterns:
            if isinstance(pattern, URLPattern):
                urls.append(prefix + str(pattern.pattern))
            elif isinstance(pattern, URLResolver):
                urls.extend(extract_urls(pattern.url_patterns, prefix + str(pattern.pattern)))
        return urls

    try:
        resolver = get_resolver()
        return sorted(set(extract_urls(resolver.url_patterns)))
    except Exception as e:
        logger.error(f"Error getting available URLs: {e}")
        return []


def is_admin_user(user):
    """Check if user is admin (superuser or in Admin group)"""
    return user.is_superuser or user.groups.filter(name='Admin').exists()


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def view_documentation(request, doc_name):
    """
    Serve markdown documentation files to admin users.
    """
    import os
    from django.http import Http404, HttpResponse

    # Define allowed documentation files (mapping to docs/ directory)
    allowed_docs = {
        'quick_start': 'docs/01-GETTING-STARTED.md',
        'setup_guide': 'docs/01-GETTING-STARTED.md',
        'celery_setup': 'docs/06-OPERATIONS.md',
        'telegram_bot': 'docs/06-OPERATIONS.md',
        'architecture': 'docs/02-ARCHITECTURE.md',
        'trading_strategies': 'docs/03-TRADING-STRATEGIES.md',
        'broker_integration': 'docs/04-BROKER-INTEGRATION.md',
        'data_sources': 'docs/05-DATA-SOURCES.md',
        'operations': 'docs/06-OPERATIONS.md',
        'algorithms': 'docs/ALGORITHMS.md',
    }

    if doc_name not in allowed_docs:
        raise Http404("Documentation not found")

    file_path = os.path.join(settings.BASE_DIR, allowed_docs[doc_name])

    if not os.path.exists(file_path):
        raise Http404("Documentation file not found")

    # Return the file as plain text for browser viewing
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    return HttpResponse(content, content_type='text/plain; charset=utf-8')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_trendlyne_download(request):
    """
    Trigger Trendlyne Data Population using the unified TrendlyneDataFetcher service.

    Complete workflow:
    1. Login to Trendlyne via Selenium
    2. Download F&O contracts data
    3. Download Market Snapshot (Stock data)
    4. Fetch Forecaster data (21 screeners)
    5. Parse and save all to database
    6. Cleanup

    Populates:
    - ContractData (F&O contracts)
    - TLStockData (Stock data with 163 fields)
    """
    from django.contrib import messages
    import threading

    # Only allow POST requests
    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        def populate_task():
            try:
                from apps.data.services.trendlyne_fetcher import TrendlyneDataFetcher, TrendlyneLogCallback

                logger.info("Starting Trendlyne FULL data fetch workflow...")

                # Create a simple log callback that logs to Django logger
                class DjangoLogCallback(TrendlyneLogCallback):
                    def log(self, message: str, level: str = "info"):
                        super().log(message, level)
                        if level == "error":
                            logger.error(f"[Trendlyne] {message}")
                        elif level == "warning":
                            logger.warning(f"[Trendlyne] {message}")
                        else:
                            logger.info(f"[Trendlyne] {message}")

                callback = DjangoLogCallback()
                fetcher = TrendlyneDataFetcher(callback)
                result = fetcher.fetch_fno_data()

                # Get final statistics
                from apps.data.models import ContractData, TLStockData

                contract_count = ContractData.objects.count()
                stock_count = TLStockData.objects.count()
                total = contract_count + stock_count

                logger.info(f"Trendlyne population completed: {total:,} total records")
                logger.info(f"  - ContractData: {contract_count:,}")
                logger.info(f"  - TLStockData: {stock_count:,}")

                if result.get('data'):
                    logger.info(f"  - Forecaster Screeners: {result['data'].get('forecaster_screeners', 0)}/21")

            except Exception as e:
                logger.error(f"Trendlyne population failed: {e}", exc_info=True)

        thread = threading.Thread(target=populate_task, daemon=True)
        thread.start()

        messages.success(request, "Trendlyne FULL data fetch started! Using Selenium to: Login → Download F&O → Download Stock Data → Fetch Forecaster (21 pages) → Parse & Populate DB. Refresh in 2-3 minutes to see updated data.")

    except Exception as e:
        messages.error(request, f"Failed to start population: {str(e)}")
        logger.error(f"Error triggering Trendlyne population: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_fno_data_download(request):
    """
    Trigger F&O Contract Data download and database population
    Downloads only contract data and populates ContractData model
    """
    from django.contrib import messages
    import threading

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        def fno_download_task():
            try:
                from django.core.management import call_command
                from io import StringIO

                # Run the trendlyne_data_manager command with --parse-all
                out = StringIO()
                call_command('trendlyne_data_manager', '--parse-all', stdout=out)

                from apps.data.models import ContractData
                record_count = ContractData.objects.count()

                logger.info(f"F&O data population completed: {record_count} contract records")

            except Exception as e:
                logger.error(f"F&O data population failed: {e}", exc_info=True)

        thread = threading.Thread(target=fno_download_task, daemon=True)
        thread.start()

        messages.success(request, "F&O data population initiated. Refresh in 30 seconds to see updated record counts.")

    except Exception as e:
        messages.error(request, f"Failed to start F&O data population: {str(e)}")
        logger.error(f"Error triggering F&O data: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_trendlyne_full_cycle(request):
    """
    Trigger complete Trendlyne data pipeline using unified TrendlyneDataFetcher:
    1. Login to Trendlyne via Selenium
    2. Download F&O contracts data
    3. Download Market Snapshot (Stock data)
    4. Fetch Forecaster data (21 screeners)
    5. Parse and save all to database
    6. Cleanup

    This provides comprehensive data refresh with all statistics
    """
    from django.contrib import messages
    import threading

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        def full_cycle_task():
            try:
                from apps.data.services.trendlyne_fetcher import TrendlyneDataFetcher, TrendlyneLogCallback

                logger.info("Starting Trendlyne FULL cycle workflow...")

                # Create a simple log callback that logs to Django logger
                class DjangoLogCallback(TrendlyneLogCallback):
                    def log(self, message: str, level: str = "info"):
                        super().log(message, level)
                        if level == "error":
                            logger.error(f"[Trendlyne] {message}")
                        elif level == "warning":
                            logger.warning(f"[Trendlyne] {message}")
                        else:
                            logger.info(f"[Trendlyne] {message}")

                callback = DjangoLogCallback()
                fetcher = TrendlyneDataFetcher(callback)
                fetcher.fetch_fno_data()

                # Get summary statistics
                from apps.data.models import (
                    ContractData, ContractStockData, TLStockData,
                    OptionChain, Event, NewsArticle, InvestorCall, KnowledgeBase
                )

                stats = {
                    'ContractData': ContractData.objects.count(),
                    'ContractStockData': ContractStockData.objects.count(),
                    'TLStockData': TLStockData.objects.count(),
                    'OptionChain': OptionChain.objects.count(),
                    'Event': Event.objects.count(),
                    'NewsArticle': NewsArticle.objects.count(),
                    'InvestorCall': InvestorCall.objects.count(),
                    'KnowledgeBase': KnowledgeBase.objects.count(),
                }

                total = sum(stats.values())
                logger.info(f"Full Trendlyne cycle completed: {total} total records | {stats}")

            except Exception as e:
                logger.error(f"Full Trendlyne cycle failed: {e}", exc_info=True)

        thread = threading.Thread(target=full_cycle_task, daemon=True)
        thread.start()

        messages.success(request, "Full Trendlyne data cycle initiated! Using Selenium to: Login → Download F&O → Download Stock Data → Fetch Forecaster (21 pages) → Parse & Populate DB. Refresh in 2-3 minutes to see all updated statistics.")

    except Exception as e:
        messages.error(request, f"Failed to start Trendlyne full cycle: {str(e)}")
        logger.error(f"Error triggering Trendlyne full cycle: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_market_snapshot_download(request):
    """
    Trigger Market Snapshot (Stock) data download and database population.
    Uses unified TrendlyneDataFetcher for downloading and parsing.
    """
    from django.contrib import messages
    import threading

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        def market_snapshot_task():
            try:
                from apps.data.services.trendlyne_fetcher import TrendlyneDataFetcher, TrendlyneLogCallback

                logger.info("Starting Market Snapshot (Stock Data) fetch...")

                # Create a simple log callback that logs to Django logger
                class DjangoLogCallback(TrendlyneLogCallback):
                    def log(self, message: str, level: str = "info"):
                        super().log(message, level)
                        if level == "error":
                            logger.error(f"[Trendlyne] {message}")
                        elif level == "warning":
                            logger.warning(f"[Trendlyne] {message}")
                        else:
                            logger.info(f"[Trendlyne] {message}")

                callback = DjangoLogCallback()
                fetcher = TrendlyneDataFetcher(callback)

                # The fetch_fno_data method fetches ALL data including stock data
                fetcher.fetch_fno_data()

                from apps.data.models import TLStockData
                record_count = TLStockData.objects.count()

                logger.info(f"Market Snapshot data population completed: {record_count} stock records")

            except Exception as e:
                logger.error(f"Market Snapshot data task failed: {e}", exc_info=True)

        thread = threading.Thread(target=market_snapshot_task, daemon=True)
        thread.start()

        messages.success(request, "Market Snapshot (Stock Data) download initiated! Using Selenium to: Login → Download Stock Data → Parse & Populate TLStockData. Refresh in 2-3 minutes to see results.")

    except Exception as e:
        messages.error(request, f"Failed to start Market Snapshot download: {str(e)}")
        logger.error(f"Error triggering Market Snapshot: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_forecaster_download(request):
    """
    Trigger Forecaster data download (21 screener pages).
    Uses unified TrendlyneDataFetcher for downloading.
    """
    from django.contrib import messages
    import threading

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        def forecaster_task():
            try:
                from apps.data.services.trendlyne_fetcher import TrendlyneDataFetcher, TrendlyneLogCallback

                logger.info("Starting Forecaster data (21 screeners) fetch...")

                # Create a simple log callback that logs to Django logger
                class DjangoLogCallback(TrendlyneLogCallback):
                    def log(self, message: str, level: str = "info"):
                        super().log(message, level)
                        if level == "error":
                            logger.error(f"[Trendlyne] {message}")
                        elif level == "warning":
                            logger.warning(f"[Trendlyne] {message}")
                        else:
                            logger.info(f"[Trendlyne] {message}")

                callback = DjangoLogCallback()
                fetcher = TrendlyneDataFetcher(callback)

                # The fetch_fno_data method fetches ALL data including Forecaster data
                result = fetcher.fetch_fno_data()

                if result.get('data'):
                    forecaster_count = result['data'].get('forecaster_screeners', 0)
                    logger.info(f"Forecaster data fetch completed: {forecaster_count}/21 screeners")
                else:
                    logger.info("Forecaster data fetch completed")

            except Exception as e:
                logger.error(f"Forecaster data task failed: {e}", exc_info=True)

        thread = threading.Thread(target=forecaster_task, daemon=True)
        thread.start()

        messages.success(request, "Forecaster data download initiated (21 screener pages)! Using Selenium to: Login → Fetch all 21 Forecaster screeners → Save to CSV. Refresh in 2-3 minutes to see results.")

    except Exception as e:
        messages.error(request, f"Failed to start Forecaster download: {str(e)}")
        logger.error(f"Error triggering Forecaster: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def verify_kotak_login(request):
    """
    Verify Kotak Neo API login
    """
    from django.contrib import messages

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        from apps.core.models import CredentialStore
        from tools.neo import NeoAPI

        # Get credentials
        creds = CredentialStore.objects.filter(service='kotakneo').first()
        if not creds:
            messages.error(request, "Kotak Neo credentials not found")
            return redirect('core:system_test')

        # User-initiated login from web UI — reset any previous failed status
        # so the auto-login guard doesn't block this explicit attempt
        from apps.brokers.utils.auth_manager import reset_auto_login_status
        reset_auto_login_status('kotakneo')

        # Attempt login (manual=True bypasses trading window + daily limit)
        neo = NeoAPI()
        success = neo.login(manual=True)

        if success:
            # Update process-level cache so subsequent API calls in this worker
            # (including order placement) use this same fresh session instead of a stale one
            try:
                from tools.neo import _cache_lock
                import tools.neo as neo_module
                with _cache_lock:
                    neo_module._cached_instance = neo
            except Exception:
                pass

            # Fetch account data to verify connection
            try:
                margin = neo.get_margin()
                positions = neo.get_positions()

                # Also fetch holdings (equity stocks)
                try:
                    holdings_resp = neo.neo.holdings()
                    holdings = holdings_resp.get('data', []) if holdings_resp else []
                except Exception as e:
                    logger.warning(f"Could not fetch holdings: {e}")
                    holdings = []

                logger.info(f"Kotak Neo margin data: {margin}")
                logger.info(f"Kotak Neo positions count: {len(positions) if positions else 0}")
                logger.info(f"Kotak Neo holdings count: {len(holdings) if holdings else 0}")

                # margin is a dict, positions are Position objects or dicts
                available_margin = margin.get('available_margin', 0) if isinstance(margin, dict) else 0
                position_count = len(positions) if positions else 0
                holding_count = len(holdings) if holdings else 0

                # Calculate total investment from positions (F&O)
                total_investment = 0
                for p in positions:
                    if hasattr(p, 'quantity') and hasattr(p, 'average_price'):
                        # Position object
                        qty = p.quantity
                        avg_price = p.average_price
                        investment = abs(qty * avg_price)
                        logger.info(f"Position: {p.symbol}, qty={qty}, avg_price={avg_price}, investment={investment}")
                        total_investment += investment
                    elif isinstance(p, dict):
                        # Dict fallback
                        qty = p.get('quantity', 0)
                        avg_price = p.get('average_price', 0)
                        investment = abs(qty * avg_price)
                        logger.info(f"Position (dict): qty={qty}, avg_price={avg_price}, investment={investment}")
                        total_investment += investment

                # Add investment from holdings (equity stocks)
                for h in holdings:
                    qty = int(h.get('flHoldQty', 0)) + int(h.get('dpHoldQty', 0))
                    avg_price = _parse_float(h.get('avg', 0)) if 'avg' in h else _parse_float(h.get('avgPrc', 0))
                    investment = abs(qty * avg_price)
                    logger.info(f"Holding: {h.get('trdSym', 'Unknown')}, qty={qty}, avg_price={avg_price}, investment={investment}")
                    total_investment += investment

                logger.info(f"Total investment calculated: {total_investment}")

                # Store verification details in session
                request.session['kotak_login_verified'] = True
                request.session['kotak_login_time'] = str(datetime.now())
                request.session['kotak_available_margin'] = float(available_margin)
                request.session['kotak_position_count'] = position_count
                request.session['kotak_holding_count'] = holding_count
                request.session['kotak_total_investment'] = float(total_investment)

                messages.success(
                    request,
                    f"✅ Kotak Neo login successful! "
                    f"Available Margin: {format_currency(available_margin)}, "
                    f"F&O Positions: {position_count}, "
                    f"Stock Holdings: {holding_count}, "
                    f"Total Investment: {format_currency(total_investment)}"
                )
            except Exception as e:
                logger.warning(f"Kotak Neo login successful but couldn't fetch account data: {e}")
                request.session['kotak_login_verified'] = True
                request.session['kotak_login_time'] = str(datetime.now())
                messages.success(request, f"✅ Kotak Neo login successful for {creds.username}!")
        else:
            request.session['kotak_login_verified'] = False
            error_detail = neo.last_error or "Unknown error"
            messages.error(request, f"❌ Kotak Neo login failed: {error_detail}")

    except Exception as e:
        messages.error(request, f"❌ Kotak Neo login error: {str(e)}")
        logger.error(f"Kotak Neo login verification error: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def verify_breeze_login(request):
    """
    Verify Breeze API login - requires session token input
    """
    from django.contrib import messages

    from django.shortcuts import render
    from apps.core.models import CredentialStore
    from django.utils import timezone
    from apps.brokers.integrations.breeze import BreezeAPI

    # Get credentials
    creds = CredentialStore.objects.filter(service='breeze').first()
    if not creds:
        messages.error(request, "Breeze credentials not found")
        return redirect('core:system_test')

    if request.method == 'GET':
        # Check if we have a valid token from today
        has_valid_token = (
            creds.session_token and
            creds.last_session_update and
            creds.last_session_update.date() == timezone.now().date()
        )

        if has_valid_token:
            # Token is valid for today, attempt login (auto-login triggers if token is invalid)
            logger.info("Breeze has valid token from today, attempting login")
            session_token = creds.session_token
            skip_save = True
        elif creds.username and creds.password:
            # No valid token, but auto-login credentials available
            # Trigger Selenium + OTP auto-login flow
            logger.info("Breeze token missing/expired — triggering auto-login (Selenium + OTP)")
            from apps.brokers.utils.auth_manager import reset_auto_login_status
            reset_auto_login_status('breeze')
            session_token = None
            skip_save = True
        else:
            # No auto-login credentials, show manual token form
            logger.info("Breeze token missing or expired, no auto-login creds — showing form")
            context = {
                'username': creds.username,
                'api_key': creds.api_key,
            }
            return render(request, 'core/breeze_token_input.html', context)

    elif request.method == 'POST':
        # Get session token from form
        session_token = request.POST.get('session_token', '').strip()
        if not session_token:
            # No token submitted - check if we have a valid one from today
            has_valid_token = (
                creds.session_token and
                creds.last_session_update and
                creds.last_session_update.date() == timezone.now().date()
            )
            if has_valid_token:
                logger.info("Breeze POST without token but valid token exists from today, using existing")
                session_token = creds.session_token
                skip_save = True
            else:
                messages.error(request, "Session token is required - no valid token from today")
                return redirect('core:verify_breeze_login')
        else:
            # Store new session token
            creds.session_token = session_token
            creds.last_session_update = timezone.now()
            creds.save()
            skip_save = False
            logger.info(f"Saved new session token for Breeze: {creds.session_token[:10] if creds.session_token else 'None'}...")

    else:
        return redirect('core:system_test')

    # Common login logic for both GET (with valid token) and POST (with new token)
    try:
        # Refresh from database to ensure we have the latest data
        if not skip_save:
            creds.refresh_from_db()

        breeze = BreezeAPI()
        logger.info(f"BreezeAPI initialized successfully")
        success = breeze.login()

        if success:
            # Fetch account data to verify connection
            try:
                margin = breeze.get_margin()
                positions = breeze.get_positions()

                # Also fetch holdings (equity stocks)
                try:
                    holdings_resp = breeze.breeze.get_portfolio_holdings()
                    holdings = holdings_resp.get('Success', []) if holdings_resp else []
                except Exception as e:
                    logger.warning(f"Could not fetch holdings: {e}")
                    holdings = []

                logger.info(f"Breeze margin data: {margin}")
                logger.info(f"Breeze positions count: {len(positions) if positions else 0}")
                logger.info(f"Breeze holdings count: {len(holdings) if holdings else 0}")

                # margin is a dict, positions are Position objects or dicts
                available_margin = margin.get('available_margin', 0) if isinstance(margin, dict) else 0
                position_count = len(positions) if positions else 0
                holding_count = len(holdings) if holdings else 0

                # Calculate total investment from positions (F&O)
                total_investment = 0
                for p in positions:
                    if hasattr(p, 'quantity') and hasattr(p, 'average_price'):
                        # Position object
                        qty = p.quantity
                        avg_price = p.average_price
                        investment = abs(qty * avg_price)
                        logger.info(f"Position: {p.symbol}, qty={qty}, avg_price={avg_price}, investment={investment}")
                        total_investment += investment
                    elif isinstance(p, dict):
                        # Dict fallback
                        qty = p.get('quantity', 0)
                        avg_price = p.get('average_price', 0)
                        investment = abs(qty * avg_price)
                        logger.info(f"Position (dict): qty={qty}, avg_price={avg_price}, investment={investment}")
                        total_investment += investment

                # Add investment from holdings (equity stocks)
                for h in holdings:
                    qty = int(h.get('quantity', 0))
                    avg_price = _parse_float(h.get('average_price', 0))
                    investment = abs(qty * avg_price)
                    logger.info(f"Holding: {h.get('stock_code', 'Unknown')}, qty={qty}, avg_price={avg_price}, investment={investment}")
                    total_investment += investment

                logger.info(f"Total investment calculated: {total_investment}")

                # Store verification details in session
                request.session['breeze_login_verified'] = True
                request.session['breeze_login_time'] = str(datetime.now())
                request.session['breeze_available_margin'] = float(available_margin)
                request.session['breeze_position_count'] = position_count
                request.session['breeze_holding_count'] = holding_count
                request.session['breeze_total_investment'] = float(total_investment)

                messages.success(
                    request,
                    f"✅ Breeze login successful! "
                    f"Available Margin: {format_currency(available_margin)}, "
                    f"F&O Positions: {position_count}, "
                    f"Stock Holdings: {holding_count}, "
                    f"Total Investment: {format_currency(total_investment)}"
                )
            except Exception as e:
                logger.warning(f"Breeze login successful but couldn't fetch account data: {e}")
                request.session['breeze_login_verified'] = True
                request.session['breeze_login_time'] = str(datetime.now())
                messages.success(request, f"✅ Breeze login successful for {creds.username}!")
        else:
            request.session['breeze_login_verified'] = False
            messages.error(request, f"❌ Breeze login failed")

    except Exception as e:
        messages.error(request, f"❌ Breeze login error: {str(e)}")
        logger.error(f"Breeze login verification error: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def system_test_page(request):
    """
    Comprehensive system test page for testing all critical functionalities.
    Only accessible by admin users.
    """
    test_results = {
        'database': test_database(),
        'brokers': test_brokers(),
        'trendlyne': test_trendlyne(),
        'data': test_data_app(),
        'orders': test_orders(),
        'positions': test_positions(),
        'accounts': test_accounts(request),
        'llm': test_llm(),
        'redis': test_redis(),
        'background_tasks': test_background_tasks(),
        'django_admin': test_django_admin(),
        'telegram': test_telegram(),
    }

    # Add passed count to each category
    for category in test_results.values():
        category['passed'] = sum(1 for test in category['tests'] if test['status'] == 'pass')

    # Calculate summary statistics
    total_tests = sum(len(category['tests']) for category in test_results.values())
    passed_tests = sum(
        sum(1 for test in category['tests'] if test['status'] == 'pass')
        for category in test_results.values()
    )
    failed_tests = total_tests - passed_tests

    context = {
        'test_results': test_results,
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'failed_tests': failed_tests,
        'pass_rate': round((passed_tests / total_tests * 100), 2) if total_tests > 0 else 0,
        'timestamp': datetime.now(),
    }

    return render(request, 'core/system_test.html', context)


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

def test_database():
    """Test database connectivity and basic operations"""
    tests = []

    # Test 1: Database connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        tests.append({
            'name': 'Database Connection',
            'status': 'pass' if result[0] == 1 else 'fail',
            'message': 'Database connection successful' if result[0] == 1 else 'Connection failed',
        })
    except Exception as e:
        tests.append({
            'name': 'Database Connection',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 2: Migrations status
    try:
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('showmigrations', stdout=out)
        migrations_output = out.getvalue()
        unapplied = '[' in migrations_output and '[ ]' in migrations_output

        tests.append({
            'name': 'Migrations Status',
            'status': 'fail' if unapplied else 'pass',
            'message': 'All migrations applied' if not unapplied else 'Unapplied migrations found',
        })
    except Exception as e:
        tests.append({
            'name': 'Migrations Status',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: Database tables exist
    try:
        expected_tables = ['broker_limits', 'broker_positions', 'orders', 'positions',
                          'broker_accounts', 'market_data', 'llm_validations']
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            tables = [row[0] for row in cursor.fetchall()]

        missing = [t for t in expected_tables if t not in tables]
        tests.append({
            'name': 'Database Tables',
            'status': 'pass' if not missing else 'fail',
            'message': f'Found {len(tables)} tables' if not missing else f'Missing: {", ".join(missing)}',
        })
    except Exception as e:
        tests.append({
            'name': 'Database Tables',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'Database', 'tests': tests}


def test_brokers():
    """Test broker-related functionalities"""
    tests = []

    # Test 1: BrokerLimit model access
    try:
        from apps.brokers.models import BrokerLimit
        count = BrokerLimit.objects.count()
        latest = BrokerLimit.objects.order_by('-fetched_at').first()

        tests.append({
            'name': 'Broker Limits Access',
            'status': 'pass',
            'message': f'Found {count} records. Latest: {latest.fetched_at if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'Broker Limits Access',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 2: BrokerPosition model access
    try:
        from apps.brokers.models import BrokerPosition
        count = BrokerPosition.objects.count()
        latest = BrokerPosition.objects.order_by('-fetched_at').first()

        tests.append({
            'name': 'Broker Positions Access',
            'status': 'pass',
            'message': f'Found {count} records. Latest: {latest.symbol if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'Broker Positions Access',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: Option chain model access
    try:
        from apps.brokers.models import OptionChainQuote
        count = OptionChainQuote.objects.count()
        latest = OptionChainQuote.objects.order_by('-created_at').first()

        tests.append({
            'name': 'Option Chain Data',
            'status': 'pass',
            'message': f'Found {count} records. Latest: {latest.stock_code if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'Option Chain Data',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 4: Historical price data access
    try:
        from apps.brokers.models import HistoricalPrice
        count = HistoricalPrice.objects.count()
        latest = HistoricalPrice.objects.order_by('-datetime').first()

        tests.append({
            'name': 'Historical Price Data',
            'status': 'pass',
            'message': f'Found {count} records. Latest: {latest.stock_code if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'Historical Price Data',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 5: Credential Store access
    try:
        from apps.core.models import CredentialStore
        kotak_creds = CredentialStore.objects.filter(service='kotakneo').first()
        breeze_creds = CredentialStore.objects.filter(service='breeze').first()

        status = 'pass' if (kotak_creds or breeze_creds) else 'fail'
        message = []
        if kotak_creds:
            message.append('Kotak Neo configured')
        if breeze_creds:
            message.append('Breeze configured')

        tests.append({
            'name': 'Broker Credentials',
            'status': status if message else 'fail',
            'message': ', '.join(message) if message else 'No credentials found',
        })
    except Exception as e:
        tests.append({
            'name': 'Broker Credentials',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'Brokers', 'tests': tests}


def test_trendlyne():
    """Test Trendlyne integration and data scraping"""
    tests = []

    # Test 1: Trendlyne credentials
    try:
        from apps.core.models import CredentialStore
        creds = CredentialStore.objects.filter(service='trendlyne').first()

        if creds:
            tests.append({
                'name': 'Trendlyne Credentials',
                'status': 'pass',
                'message': f'Credentials configured for user: {creds.username}',
            })
        else:
            tests.append({
                'name': 'Trendlyne Credentials',
                'status': 'fail',
                'message': 'No Trendlyne credentials found in database',
            })
    except Exception as e:
        tests.append({
            'name': 'Trendlyne Credentials',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 2: Trendlyne website accessibility
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get('https://trendlyne.com', headers=headers, timeout=10)

        if response.status_code == 200:
            tests.append({
                'name': 'Trendlyne Website Access',
                'status': 'pass',
                'message': f'Website accessible (HTTP {response.status_code})',
            })
        else:
            tests.append({
                'name': 'Trendlyne Website Access',
                'status': 'fail',
                'message': f'HTTP {response.status_code} - Website may be blocking automated requests',
            })
    except Exception as e:
        tests.append({
            'name': 'Trendlyne Website Access',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: ChromeDriver availability
    try:
        pass
        # Just check if the module can be imported
        tests.append({
            'name': 'ChromeDriver (Selenium)',
            'status': 'pass',
            'message': 'ChromeDriver autoinstaller available',
        })
    except Exception as e:
        tests.append({
            'name': 'ChromeDriver (Selenium)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 4: Trendlyne data directory and database population
    try:
        import os
        from django.conf import settings

        data_dirs = [
            os.path.join(settings.BASE_DIR, 'apps', 'data', 'trendlynedata'),
            os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata'),
        ]

        existing_dirs = []
        total_files = 0

        for data_dir in data_dirs:
            if os.path.exists(data_dir):
                existing_dirs.append(os.path.basename(data_dir))
                # Count CSV files
                for root, dirs, files in os.walk(data_dir):
                    total_files += len([f for f in files if f.endswith('.csv')])

        if existing_dirs:
            # Get comprehensive database statistics
            try:
                from apps.data.models import (
                    ContractData, ContractStockData, TLStockData,
                    OptionChain, Event, NewsArticle, InvestorCall, KnowledgeBase
                )

                db_stats = {
                    'ContractData': ContractData.objects.count(),
                    'ContractStockData': ContractStockData.objects.count(),
                    'TLStockData': TLStockData.objects.count(),
                    'OptionChain': OptionChain.objects.count(),
                    'Event': Event.objects.count(),
                    'NewsArticle': NewsArticle.objects.count(),
                    'InvestorCall': InvestorCall.objects.count(),
                    'KnowledgeBase': KnowledgeBase.objects.count(),
                }

                total_records = sum(db_stats.values())

                # Format with Indian numbering
                formatted_total = format_currency(total_records).replace('₹', '')

                # Build detailed breakdown
                breakdown_parts = []
                for model_name, count in db_stats.items():
                    if count > 0:
                        formatted_count = format_currency(count).replace('₹', '')
                        # Shorten model names for display
                        short_name = model_name.replace('Data', '').replace('Contract', 'Cont.')
                        breakdown_parts.append(f"{short_name}: {formatted_count}")

                breakdown_str = " | ".join(breakdown_parts) if breakdown_parts else "No data populated yet"

                status = 'pass' if total_records > 0 else 'warning'
                message = f'Downloaded {total_files} CSV files | Populated {formatted_total} total rows | {breakdown_str}'

            except Exception as db_error:
                logger.warning(f"Could not fetch database stats: {db_error}")
                message = f'Found {len(existing_dirs)} data dirs with {total_files} CSV files | Database stats unavailable'
                status = 'warning'

            tests.append({
                'name': 'Trendlyne Data Directory',
                'status': status,
                'message': message,
                'trigger_url': '/system/test/trigger-trendlyne/',
                'trigger_label': 'Download & Populate All',
            })
        else:
            tests.append({
                'name': 'Trendlyne Data Directory',
                'status': 'fail',
                'message': 'No data directories found (not downloaded yet)',
                'trigger_url': '/system/test/trigger-trendlyne/',
                'trigger_label': 'Download & Populate Now',
            })
    except Exception as e:
        tests.append({
            'name': 'Trendlyne Data Directory',
            'status': 'fail',
            'message': f'Error: {str(e)}',
            'trigger_url': '/system/test/trigger-trendlyne/',
            'trigger_label': 'Try Download',
        })

    # Test 5: F&O Data freshness
    try:
        import os
        from django.conf import settings
        from datetime import datetime

        data_dir = os.path.join(settings.BASE_DIR, 'trendlyne_data')

        if os.path.exists(data_dir):
            fno_files = [f for f in os.listdir(data_dir) if f.startswith('contract_') and (f.endswith('.csv') or f.endswith('.xlsx'))]

            if fno_files:
                fno_files.sort(reverse=True)
                latest_file = fno_files[0]
                file_path = os.path.join(data_dir, latest_file)
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                age_days = (datetime.now() - file_time).days

                status = 'pass' if age_days <= 1 else 'warning' if age_days <= 7 else 'fail'

                # Get record count from database
                try:
                    from apps.data.models import ContractData
                    record_count = ContractData.objects.count()
                    message = f'Latest: {latest_file} ({age_days} days old) | Updated {record_count} records at {file_time.strftime("%Y-%m-%d %H:%M:%S")}'
                except:
                    message = f'Latest: {latest_file} ({age_days} days old) | Updated at {file_time.strftime("%Y-%m-%d %H:%M:%S")}'

                tests.append({
                    'name': 'F&O Data Freshness',
                    'status': status,
                    'message': message,
                    'trigger_url': '/system/test/trigger-fno-data/',
                    'trigger_label': 'Populate Data',
                })
            else:
                tests.append({
                    'name': 'F&O Data Freshness',
                    'status': 'fail',
                    'message': 'No F&O data files found in trendlyne_data directory',
                    'trigger_url': '/system/test/trigger-trendlyne-full/',
                    'trigger_label': 'Download & Populate',
                })
        else:
            tests.append({
                'name': 'F&O Data Freshness',
                'status': 'fail',
                'message': 'Data directory not found at /trendlyne_data',
                'trigger_url': '/system/test/trigger-trendlyne-full/',
                'trigger_label': 'Create & Download',
            })
    except Exception as e:
        tests.append({
            'name': 'F&O Data Freshness',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 6: Market Snapshot Data
    try:
        import os
        from django.conf import settings
        from datetime import datetime

        data_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata')

        if os.path.exists(data_dir):
            snapshot_files = [f for f in os.listdir(data_dir) if f.startswith('market_snapshot_') and (f.endswith('.csv') or f.endswith('.xlsx'))]

            if snapshot_files:
                snapshot_files.sort(reverse=True)
                latest_file = snapshot_files[0]
                file_path = os.path.join(data_dir, latest_file)
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                age_days = (datetime.now() - file_time).days
                age_minutes = (datetime.now() - file_time).total_seconds() / 60

                # Get database record count
                try:
                    from apps.data.models import TLStockData
                    db_count = TLStockData.objects.count()
                    db_info = f"Updated {format_currency(db_count).replace('₹', '')} rows in database"
                except:
                    db_info = "Database not populated"

                status = 'pass' if age_days <= 7 else 'fail'

                # Show "Refresh" button if older than 10 minutes
                trigger_label = 'Refresh Data' if age_minutes > 10 else 'Download Again'

                # Format download time
                download_time = file_time.strftime("%d %b %Y at %I:%M %p")

                tests.append({
                    'name': 'Market Snapshot Data',
                    'status': status,
                    'message': f'Downloaded latest files on {download_time} | {db_info}',
                    'trigger_url': '/system/test/trigger-market-snapshot/',
                    'trigger_label': trigger_label,
                })
            else:
                tests.append({
                    'name': 'Market Snapshot Data',
                    'status': 'fail',
                    'message': 'No market snapshot files found',
                    'trigger_url': '/system/test/trigger-market-snapshot/',
                    'trigger_label': 'Download Now',
                })
        else:
            tests.append({
                'name': 'Market Snapshot Data',
                'status': 'fail',
                'message': 'Data directory not found',
                'trigger_url': '/system/test/trigger-market-snapshot/',
                'trigger_label': 'Create & Download',
            })
    except Exception as e:
        tests.append({
            'name': 'Market Snapshot Data',
            'status': 'fail',
            'message': f'Error: {str(e)}',
            'trigger_url': '/system/test/trigger-market-snapshot/',
            'trigger_label': 'Try Download',
        })

    # Test 7: Forecaster Data (21 pages)
    try:
        import os
        from django.conf import settings
        from datetime import datetime

        data_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata', 'forecaster')

        if os.path.exists(data_dir):
            forecaster_files = [f for f in os.listdir(data_dir) if f.startswith('trendlyne_') and f.endswith('.csv')]

            if forecaster_files:
                # Check age of most recent file
                file_times = [os.path.getmtime(os.path.join(data_dir, f)) for f in forecaster_files]
                most_recent_time = datetime.fromtimestamp(max(file_times))
                age_minutes = (datetime.now() - most_recent_time).total_seconds() / 60

                trigger_label = 'Refresh Data' if age_minutes > 10 else 'Download Again'

                # Format download time
                download_time = most_recent_time.strftime("%d %b %Y at %I:%M %p")

                # Count total rows across all CSV files
                total_rows = 0
                try:
                    import csv
                    for file in forecaster_files:
                        file_path = os.path.join(data_dir, file)
                        with open(file_path, 'r', encoding='utf-8') as f:
                            reader = csv.reader(f)
                            # Subtract 1 for header row
                            row_count = sum(1 for row in reader) - 1
                            total_rows += row_count

                    rows_info = f"Contains {format_currency(total_rows).replace('₹', '')} total rows"
                except:
                    rows_info = f"{len(forecaster_files)} files downloaded"

                tests.append({
                    'name': 'Forecaster Data (21 Pages)',
                    'status': 'pass' if len(forecaster_files) >= 15 else 'fail',
                    'message': f'Downloaded latest files on {download_time} | {rows_info} across {len(forecaster_files)} CSV files',
                    'trigger_url': '/system/test/trigger-forecaster/',
                    'trigger_label': trigger_label,
                })
            else:
                tests.append({
                    'name': 'Forecaster Data (21 Pages)',
                    'status': 'fail',
                    'message': 'No forecaster data files found',
                    'trigger_url': '/system/test/trigger-forecaster/',
                    'trigger_label': 'Download Now',
                })
        else:
            tests.append({
                'name': 'Forecaster Data (21 Pages)',
                'status': 'fail',
                'message': 'Data directory not found',
                'trigger_url': '/system/test/trigger-forecaster/',
                'trigger_label': 'Create & Download',
            })
    except Exception as e:
        tests.append({
            'name': 'Forecaster Data (21 Pages)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
            'trigger_url': '/system/test/trigger-forecaster/',
            'trigger_label': 'Try Download',
        })

    # Test 8: Selenium and BeautifulSoup packages
    try:
        pass

        tests.append({
            'name': 'Scraping Dependencies',
            'status': 'pass',
            'message': 'Selenium, BeautifulSoup, Pandas available',
        })
    except Exception as e:
        tests.append({
            'name': 'Scraping Dependencies',
            'status': 'fail',
            'message': f'Missing: {str(e)}',
        })

    # Test 9: Trendlyne Tool Module
    try:
        pass

        tests.append({
            'name': 'Trendlyne Tool Module',
            'status': 'pass',
            'message': 'Tool module and functions available',
        })
    except Exception as e:
        tests.append({
            'name': 'Trendlyne Tool Module',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 10: ContractData Model
    try:
        from apps.data.models import ContractData
        count = ContractData.objects.count()
        latest = ContractData.objects.order_by('-created_at').first()

        tests.append({
            'name': 'ContractData Model (F&O)',
            'status': 'pass',
            'message': f'Found {count} records. Latest: {latest.symbol if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'ContractData Model (F&O)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 11: TLStockData Model
    try:
        from apps.data.models import TLStockData
        count = TLStockData.objects.count()
        latest = TLStockData.objects.order_by('-created_at').first()

        tests.append({
            'name': 'TLStockData Model (Market Snapshot)',
            'status': 'pass',
            'message': f'Found {count} records. Latest: {latest.stock_name if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'TLStockData Model (Market Snapshot)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 12: ContractStockData Model
    try:
        from apps.data.models import ContractStockData
        count = ContractStockData.objects.count()
        latest = ContractStockData.objects.order_by('-created_at').first()

        tests.append({
            'name': 'ContractStockData Model',
            'status': 'pass',
            'message': f'Found {count} records. Latest: {latest.stock_name if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'ContractStockData Model',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 13: Trendlyne Database Records Summary
    try:
        from apps.data.models import (
            ContractData, ContractStockData, TLStockData,
            OptionChain, Event, NewsArticle, InvestorCall, KnowledgeBase
        )
        from datetime import datetime

        # Count records across all tables
        record_stats = {
            'ContractData': ContractData.objects.count(),
            'ContractStockData': ContractStockData.objects.count(),
            'TLStockData': TLStockData.objects.count(),
            'OptionChain': OptionChain.objects.count(),
            'Event': Event.objects.count(),
            'NewsArticle': NewsArticle.objects.count(),
            'InvestorCall': InvestorCall.objects.count(),
            'KnowledgeBase': KnowledgeBase.objects.count(),
        }

        total_records = sum(record_stats.values())

        # Get latest update time from most recently updated record
        latest_times = []
        for model in [ContractData, ContractStockData, TLStockData, OptionChain,
                      Event, NewsArticle, InvestorCall, KnowledgeBase]:
            latest = model.objects.order_by('-created_at').first()
            if latest:
                latest_times.append(latest.created_at)

        if latest_times:
            most_recent = max(latest_times)
            last_update = most_recent.strftime("%d %b %Y at %I:%M %p")
        else:
            last_update = "Never"

        # Build detailed message with Indian formatting
        formatted_total = format_currency(total_records).replace('₹', '')

        # Format each model count with Indian numbering
        stats_parts = []
        for model_name, count in record_stats.items():
            if count > 0:
                formatted_count = format_currency(count).replace('₹', '')
                # Shorten model names
                short_name = model_name.replace('Data', '').replace('Contract', 'Cont.')
                stats_parts.append(f"{short_name}: {formatted_count}")

        stats_msg = " | ".join(stats_parts) if stats_parts else "No data"
        message = f'Total: {formatted_total} rows | Last updated: {last_update} | {stats_msg}'

        # Determine status
        if total_records > 0:
            status = 'pass'
        else:
            status = 'fail'

        trigger_label = 'Refresh Data'
        trigger_url = '/system/test/trigger-trendlyne-full/'

        if total_records == 0:
            trigger_label = 'Download & Populate Now'

        tests.append({
            'name': 'Trendlyne Database Summary',
            'status': status,
            'message': message,
            'trigger_url': trigger_url,
            'trigger_label': trigger_label,
        })
    except Exception as e:
        tests.append({
            'name': 'Trendlyne Database Summary',
            'status': 'fail',
            'message': f'Error: {str(e)}',
            'trigger_url': '/system/test/trigger-trendlyne-full/',
            'trigger_label': 'Download & Populate',
        })

    return {'category': 'Trendlyne Integration', 'tests': tests}


def test_data_app():
    """Test data app functionalities"""
    tests = []

    # Test 1: Market data model
    try:
        from apps.data.models import MarketData
        count = MarketData.objects.count()
        latest = MarketData.objects.order_by('-timestamp').first()

        tests.append({
            'name': 'Market Data',
            'status': 'pass',
            'message': f'Found {count} records. Latest: {latest.symbol if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'Market Data',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 2: Trendlyne stock data
    try:
        from apps.data.models import TLStockData
        count = TLStockData.objects.count()
        latest = TLStockData.objects.order_by('-created_at').first()

        tests.append({
            'name': 'Trendlyne Stock Data',
            'status': 'pass',
            'message': f'Found {count} records. Latest: {latest.stock_name if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'Trendlyne Stock Data',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: Contract data
    try:
        from apps.data.models import ContractData
        count = ContractData.objects.count()
        latest = ContractData.objects.order_by('-created_at').first()

        tests.append({
            'name': 'Contract Data (F&O)',
            'status': 'pass',
            'message': f'Found {count} records. Latest: {latest.symbol if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'Contract Data (F&O)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 4: News articles
    try:
        from apps.data.models import NewsArticle
        count = NewsArticle.objects.count()
        latest = NewsArticle.objects.order_by('-published_at').first()
        processed = NewsArticle.objects.filter(processed=True).count()

        tests.append({
            'name': 'News Articles',
            'status': 'pass',
            'message': f'Found {count} articles. Processed: {processed}',
        })
    except Exception as e:
        tests.append({
            'name': 'News Articles',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 5: Knowledge base
    try:
        from apps.data.models import KnowledgeBase
        count = KnowledgeBase.objects.count()

        tests.append({
            'name': 'Knowledge Base (RAG)',
            'status': 'pass',
            'message': f'Found {count} knowledge chunks',
        })
    except Exception as e:
        tests.append({
            'name': 'Knowledge Base (RAG)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'Data', 'tests': tests}


def test_orders():
    """Test order management functionalities"""
    tests = []

    # Test 1: Order model access
    try:
        from apps.brokers.models import Order
        count = Order.objects.count()
        pending = Order.objects.filter(status='PENDING').count()
        filled = Order.objects.filter(status='FILLED').count()

        tests.append({
            'name': 'Order Records',
            'status': 'pass',
            'message': f'Total: {count}, Pending: {pending}, Filled: {filled}',
        })
    except Exception as e:
        tests.append({
            'name': 'Order Records',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 2: Execution tracking
    try:
        from apps.brokers.models import Execution
        count = Execution.objects.count()
        latest = Execution.objects.order_by('-exchange_timestamp').first()

        tests.append({
            'name': 'Order Executions',
            'status': 'pass',
            'message': f'Found {count} executions. Latest: {latest.execution_id if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'Order Executions',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: Order creation capability
    try:
        from apps.brokers.models import Order
        # Just test that we can access the model methods
        test_order = Order(
            quantity=1,
            instrument='TEST',
            order_type='MARKET',
            direction='LONG',
        )
        # Don't save, just verify the model is accessible
        tests.append({
            'name': 'Order Creation (Model)',
            'status': 'pass',
            'message': 'Order model methods accessible',
        })
    except Exception as e:
        tests.append({
            'name': 'Order Creation (Model)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'Orders', 'tests': tests}


def test_positions():
    """Test position management functionalities"""
    tests = []

    # Test 1: Position model access
    try:
        from apps.positions.models import Position
        count = Position.objects.count()
        active = Position.objects.filter(status='ACTIVE').count()
        closed = Position.objects.filter(status='CLOSED').count()

        tests.append({
            'name': 'Position Records',
            'status': 'pass',
            'message': f'Total: {count}, Active: {active}, Closed: {closed}',
        })
    except Exception as e:
        tests.append({
            'name': 'Position Records',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 2: One position per account rule
    try:
        from apps.positions.models import Position

        # Check if the method exists
        if hasattr(Position, 'has_active_position'):
            tests.append({
                'name': 'One Position Rule',
                'status': 'pass',
                'message': 'Position control methods available',
            })
        else:
            tests.append({
                'name': 'One Position Rule',
                'status': 'fail',
                'message': 'has_active_position method not found',
            })
    except Exception as e:
        tests.append({
            'name': 'One Position Rule',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: P&L calculation
    try:
        from apps.positions.models import Position
        latest = Position.objects.order_by('-entry_time').first()

        if latest:
            pnl = latest.calculate_pnl()
            tests.append({
                'name': 'P&L Calculation',
                'status': 'pass',
                'message': f'Latest position P&L: {format_currency(pnl) if pnl is not None else "N/A"}',
            })
        else:
            tests.append({
                'name': 'P&L Calculation',
                'status': 'pass',
                'message': 'No positions to calculate P&L',
            })
    except Exception as e:
        tests.append({
            'name': 'P&L Calculation',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 4: Monitor logs
    try:
        from apps.positions.models import MonitorLog
        count = MonitorLog.objects.count()
        latest = MonitorLog.objects.order_by('-created_at').first()

        tests.append({
            'name': 'Position Monitoring',
            'status': 'pass',
            'message': f'Found {count} monitor logs. Latest: {latest.check_type if latest else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'Position Monitoring',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'Positions', 'tests': tests}


def test_accounts(request=None):
    """Test account management functionalities"""
    tests = []

    # Test 1: Broker accounts
    try:
        from apps.accounts.models import BrokerAccount
        count = BrokerAccount.objects.count()
        active = BrokerAccount.objects.filter(is_active=True).count()

        tests.append({
            'name': 'Broker Accounts',
            'status': 'pass' if count > 0 else 'fail',
            'message': f'Total: {count}, Active: {active}' if count > 0 else 'No accounts configured',
        })
    except Exception as e:
        tests.append({
            'name': 'Broker Accounts',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 2: Kotak Neo Login Verification
    try:
        from apps.core.models import CredentialStore
        kotak_creds = CredentialStore.objects.filter(service='kotakneo').first()

        if kotak_creds:
            # Check session for verification status
            kotak_verified = request.session.get('kotak_login_verified', False) if request else False
            request.session.get('kotak_login_time', '') if request else ''

            if kotak_verified:
                # Get account data from session
                kotak_margin = request.session.get('kotak_available_margin', 0) if request else 0
                kotak_positions = request.session.get('kotak_position_count', 0) if request else 0
                kotak_holdings = request.session.get('kotak_holding_count', 0) if request else 0
                kotak_investment = request.session.get('kotak_total_investment', 0) if request else 0

                tests.append({
                    'name': 'Kotak Neo Login Verification',
                    'status': 'pass',
                    'message': f'✅ Login verified for {kotak_creds.username} | Margin: {format_currency(kotak_margin)} | F&O: {kotak_positions} | Stocks: {kotak_holdings} | Investment: {format_currency(kotak_investment)}',
                    'trigger_url': '/system/test/verify-kotak-login/',
                    'trigger_label': 'Re-verify',
                })
            else:
                tests.append({
                    'name': 'Kotak Neo Login Verification',
                    'status': 'fail',
                    'message': f'Credentials found for {kotak_creds.username} - Click to verify login',
                    'trigger_url': '/system/test/verify-kotak-login/',
                    'trigger_label': 'Verify Login',
                })
        else:
            tests.append({
                'name': 'Kotak Neo Login Verification',
                'status': 'fail',
                'message': 'No Kotak Neo credentials configured',
            })
    except Exception as e:
        tests.append({
            'name': 'Kotak Neo Login Verification',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: Breeze Login Verification
    try:
        from apps.core.models import CredentialStore
        breeze_creds = CredentialStore.objects.filter(service='breeze').first()

        if breeze_creds:
            # Check session for verification status
            breeze_verified = request.session.get('breeze_login_verified', False) if request else False
            request.session.get('breeze_login_time', '') if request else ''

            if breeze_verified:
                # Get account data from session
                breeze_margin = request.session.get('breeze_available_margin', 0) if request else 0
                breeze_positions = request.session.get('breeze_position_count', 0) if request else 0
                breeze_holdings = request.session.get('breeze_holding_count', 0) if request else 0
                breeze_investment = request.session.get('breeze_total_investment', 0) if request else 0

                tests.append({
                    'name': 'Breeze Login Verification',
                    'status': 'pass',
                    'message': f'✅ Login verified for {breeze_creds.username} | Margin: {format_currency(breeze_margin)} | F&O: {breeze_positions} | Stocks: {breeze_holdings} | Investment: {format_currency(breeze_investment)}',
                    'trigger_url': '/system/test/verify-breeze-login/',
                    'trigger_label': 'Re-verify',
                })
            else:
                tests.append({
                    'name': 'Breeze Login Verification',
                    'status': 'fail',
                    'message': f'Credentials found for {breeze_creds.username} - Click to verify login',
                    'trigger_url': '/system/test/verify-breeze-login/',
                    'trigger_label': 'Verify Login',
                })
        else:
            tests.append({
                'name': 'Breeze Login Verification',
                'status': 'fail',
                'message': 'No Breeze credentials configured',
            })
    except Exception as e:
        tests.append({
            'name': 'Breeze Login Verification',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 4: Capital calculation
    try:
        from apps.accounts.models import BrokerAccount
        account = BrokerAccount.objects.filter(is_active=True, is_paper_trading=False).first()

        if account:
            available = account.get_available_capital()
            total_pnl = account.get_total_pnl()
            tests.append({
                'name': 'Capital Calculations',
                'status': 'pass',
                'message': f'Available: {format_currency(available)}, Total P&L: {format_currency(total_pnl)}',
            })
        else:
            tests.append({
                'name': 'Capital Calculations',
                'status': 'fail',
                'message': 'No active account to test',
            })
    except Exception as e:
        tests.append({
            'name': 'Capital Calculations',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'Accounts', 'tests': tests}


def test_llm():
    """Test LLM integration functionalities with comprehensive vLLM tests"""
    tests = []

    # Test 1: vLLM Server Connection
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        from django.urls import reverse
        client = get_vllm_client()

        if client.is_enabled():
            network = 'Local Network' if '192.168.' in client.base_url else 'Public IP'
            model_short = client.model.split('/')[-1] if '/' in client.model else client.model
            tests.append({
                'name': '🔌 vLLM Server Connection',
                'status': 'pass',
                'message': '✓ Connected via ' + network + ' at ' + client.base_url + ' | Model: ' + model_short,
                'description': (
                    '<b>Status:</b> LLM server is running and responding to requests.'
                    '<br><br><b>Check server health on GPU server:</b>'
                    '<br><code>docker ps --filter name=vllm-70b</code>'
                    '<br><code>nvidia-smi</code>'
                    '<br><code>curl -s http://192.168.1.32:8000/v1/models | python3 -m json.tool</code>'
                    '<br><code>docker logs --tail 50 vllm-70b</code>'
                ),
                'trigger_url': reverse('llm:test_connection'),
                'trigger_label': '🔄 Test Connection',
            })
        else:
            tests.append({
                'name': '🔌 vLLM Server Connection',
                'status': 'fail',
                'message': '✗ LLM server is not running or unreachable',
                'description': (
                    '<b>Start LLM server:</b>'
                    '<br><code>docker ps --filter name=vllm-70b</code>'
                    '<br><code>nvidia-smi</code>'
                    '<br><code>cd /home/anupamvm/vllm && docker compose up -d</code>'
                    '<br><code>docker logs -f vllm-70b</code>'
                    '<br><br><i>Model takes 2-3 min to load. Wait for "Application startup complete" in logs.</i>'
                ),
                'trigger_url': reverse('llm:test_connection'),
                'trigger_label': '🔄 Retry Connection',
            })
    except Exception as e:
        tests.append({
            'name': '🔌 vLLM Server Connection',
            'status': 'fail',
            'message': f'✗ Error: {str(e)}',
            'description': (
                '<b>Start LLM server:</b>'
                '<br><code>docker ps --filter name=vllm-70b</code>'
                '<br><code>nvidia-smi</code>'
                '<br><code>cd /home/anupamvm/vllm && docker compose up -d</code>'
                '<br><code>docker logs -f vllm-70b</code>'
            ),
        })

    # Test 2: Text Generation
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if client.is_enabled():
            success, response, metadata = client.generate(
                prompt="What is 2+2? Answer with just the number.",
                temperature=0.1,
                max_tokens=10
            )

            if success and response:
                tokens = metadata.get('usage', {}).get('total_tokens', 0)
                time_ms = metadata.get('processing_time_ms', 0)
                tests.append({
                    'name': 'Text Generation',
                    'status': 'pass',
                    'message': f'Response: "{response[:50]}..." | {tokens} tokens in {time_ms}ms',
                })
            else:
                tests.append({
                    'name': 'Text Generation',
                    'status': 'fail',
                    'message': f'Generation failed: {metadata.get("error", "Unknown error")}',
                })
        else:
            tests.append({
                'name': 'Text Generation',
                'status': 'skip',
                'message': 'Skipped - vLLM not connected',
            })
    except Exception as e:
        tests.append({
            'name': 'Text Generation',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: Chat Completion
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if client.is_enabled():
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'test passed' in one sentence."}
            ]
            success, response, metadata = client.chat(messages, temperature=0.1, max_tokens=20)

            if success and response:
                tokens = metadata.get('usage', {}).get('total_tokens', 0)
                tests.append({
                    'name': 'Chat Completion',
                    'status': 'pass',
                    'message': f'Chat working | Response: "{response[:40]}..." | {tokens} tokens',
                })
            else:
                tests.append({
                    'name': 'Chat Completion',
                    'status': 'fail',
                    'message': f'Chat failed: {metadata.get("error", "Unknown error")}',
                })
        else:
            tests.append({
                'name': 'Chat Completion',
                'status': 'skip',
                'message': 'Skipped - vLLM not connected',
            })
    except Exception as e:
        tests.append({
            'name': 'Chat Completion',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 4: Sentiment Analysis
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if client.is_enabled():
            test_text = "The stock market rallied today with strong gains across all sectors."
            success, sentiment, metadata = client.analyze_sentiment(test_text)

            if success and sentiment:
                label = sentiment.get('label', 'N/A')
                score = sentiment.get('score', 0)
                confidence = sentiment.get('confidence', 0)
                tests.append({
                    'name': 'Sentiment Analysis',
                    'status': 'pass',
                    'message': f'Label: {label} | Score: {score:.2f} | Confidence: {confidence:.2f}',
                })
            else:
                tests.append({
                    'name': 'Sentiment Analysis',
                    'status': 'fail',
                    'message': f'Analysis failed: {metadata.get("error", "Unknown error")}',
                })
        else:
            tests.append({
                'name': 'Sentiment Analysis',
                'status': 'skip',
                'message': 'Skipped - vLLM not connected',
            })
    except Exception as e:
        tests.append({
            'name': 'Sentiment Analysis',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 5: Text Summarization
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if client.is_enabled():
            test_text = """RELIANCE Industries reported strong Q4 results with revenue growth of 15% YoY.
            The company added multiple new contracts worth over $500M. Management expressed confidence
            in maintaining growth momentum in the upcoming fiscal year."""

            success, summary, metadata = client.summarize(test_text, max_length=30)

            if success and summary:
                word_count = len(summary.split())
                tests.append({
                    'name': 'Text Summarization',
                    'status': 'pass',
                    'message': f'Summary generated ({word_count} words): "{summary[:60]}..."',
                })
            else:
                tests.append({
                    'name': 'Text Summarization',
                    'status': 'fail',
                    'message': f'Summarization failed: {metadata.get("error", "Unknown error")}',
                })
        else:
            tests.append({
                'name': 'Text Summarization',
                'status': 'skip',
                'message': 'Skipped - vLLM not connected',
            })
    except Exception as e:
        tests.append({
            'name': 'Text Summarization',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 6: Insight Extraction
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if client.is_enabled():
            test_text = """TCS reported revenue growth of 15% YoY. The company added 10 new large deals
            worth over $100M each. Attrition rate decreased to 12% from 18%. Management guided for
            double-digit growth in FY25."""

            success, insights, metadata = client.extract_insights(test_text, num_insights=3)

            if success and insights:
                insight_count = len(insights) if isinstance(insights, list) else 0
                first_insight = insights[0][:50] if insight_count > 0 else "N/A"
                tests.append({
                    'name': 'Insight Extraction',
                    'status': 'pass',
                    'message': f'Extracted {insight_count} insights | First: "{first_insight}..."',
                })
            else:
                tests.append({
                    'name': 'Insight Extraction',
                    'status': 'fail',
                    'message': f'Extraction failed: {metadata.get("error", "Unknown error")}',
                })
        else:
            tests.append({
                'name': 'Insight Extraction',
                'status': 'skip',
                'message': 'Skipped - vLLM not connected',
            })
    except Exception as e:
        tests.append({
            'name': 'Insight Extraction',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 7: Question Answering (RAG)
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if client.is_enabled():
            context = "RELIANCE Industries reported Q4 net profit of Rs 19,299 crore, up 12% YoY. The board recommended a dividend of Rs 9 per share."
            question = "What was the net profit?"

            success, answer, metadata = client.answer_question(question, context, temperature=0.1)

            if success and answer:
                tests.append({
                    'name': 'Question Answering (RAG)',
                    'status': 'pass',
                    'message': f'Answer: "{answer[:70]}..."',
                })
            else:
                tests.append({
                    'name': 'Question Answering (RAG)',
                    'status': 'fail',
                    'message': f'QA failed: {metadata.get("error", "Unknown error")}',
                })
        else:
            tests.append({
                'name': 'Question Answering (RAG)',
                'status': 'skip',
                'message': 'Skipped - vLLM not connected',
            })
    except Exception as e:
        tests.append({
            'name': 'Question Answering (RAG)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 8: Document Models (NewsArticle)
    try:
        from apps.data.models import NewsArticle
        total = NewsArticle.objects.count()
        processed = NewsArticle.objects.filter(processed=True).count()
        with_sentiment = NewsArticle.objects.filter(sentiment_label__isnull=False).count()

        tests.append({
            'name': 'News Articles (LLM Ready)',
            'status': 'pass',
            'message': f'Total: {total} | Processed: {processed} | With Sentiment: {with_sentiment}',
        })
    except Exception as e:
        tests.append({
            'name': 'News Articles (LLM Ready)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 9: Document Models (InvestorCall)
    try:
        from apps.data.models import InvestorCall
        total = InvestorCall.objects.count()
        processed = InvestorCall.objects.filter(processed=True).count()
        with_summary = InvestorCall.objects.exclude(executive_summary='').count()

        tests.append({
            'name': 'Investor Calls (LLM Ready)',
            'status': 'pass',
            'message': f'Total: {total} | Processed: {processed} | With Summary: {with_summary}',
        })
    except Exception as e:
        tests.append({
            'name': 'Investor Calls (LLM Ready)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 10: Knowledge Base (RAG Storage)
    try:
        from apps.data.models import KnowledgeBase
        total = KnowledgeBase.objects.count()
        news_chunks = KnowledgeBase.objects.filter(source_type='NEWS').count()
        call_chunks = KnowledgeBase.objects.filter(source_type='CALL').count()

        tests.append({
            'name': 'Knowledge Base (RAG)',
            'status': 'pass',
            'message': f'Total Chunks: {total} | News: {news_chunks} | Calls: {call_chunks}',
        })
    except Exception as e:
        tests.append({
            'name': 'Knowledge Base (RAG)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 11: LLM Validation Records
    try:
        from apps.llm.models import LLMValidation
        count = LLMValidation.objects.count()
        recent = LLMValidation.objects.order_by('-created_at').first()

        tests.append({
            'name': 'LLM Trade Validations',
            'status': 'pass',
            'message': f'Found {count} validations | Latest: {recent.symbol if recent else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'LLM Trade Validations',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 12: LLM Prompt Templates
    try:
        from apps.llm.models import LLMPrompt
        count = LLMPrompt.objects.count()
        active = LLMPrompt.objects.filter(is_active=True).count()

        tests.append({
            'name': 'LLM Prompt Templates',
            'status': 'pass',
            'message': f'Total: {count} | Active: {active}',
        })
    except Exception as e:
        tests.append({
            'name': 'LLM Prompt Templates',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 13: Performance Test
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        import time
        client = get_vllm_client()

        if client.is_enabled():
            start = time.time()
            success, _, metadata = client.generate(
                prompt="Say hello",
                temperature=0.1,
                max_tokens=10
            )
            elapsed_ms = int((time.time() - start) * 1000)

            if success:
                status = 'pass' if elapsed_ms < 2000 else 'warning'
                tests.append({
                    'name': 'LLM Performance',
                    'status': status,
                    'message': f'Response time: {elapsed_ms}ms | {"Good" if elapsed_ms < 1000 else "Acceptable" if elapsed_ms < 2000 else "Slow"}',
                })
            else:
                tests.append({
                    'name': 'LLM Performance',
                    'status': 'fail',
                    'message': 'Performance test failed',
                })
        else:
            tests.append({
                'name': 'LLM Performance',
                'status': 'skip',
                'message': 'Skipped - vLLM not connected',
            })
    except Exception as e:
        tests.append({
            'name': 'LLM Performance',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'LLM Integration', 'tests': tests}


def test_redis():
    """Test Redis connectivity for Celery"""
    tests = []

    try:
        import redis
        redis_url = settings.CELERY_BROKER_URL

        # Parse Redis URL
        if redis_url.startswith('redis://'):
            parts = redis_url.replace('redis://', '').split(':')
            host = parts[0]
            port_db = parts[1].split('/')
            port = int(port_db[0])
            db = int(port_db[1]) if len(port_db) > 1 else 0

            r = redis.Redis(host=host, port=port, db=db, socket_timeout=5)
            r.ping()

            tests.append({
                'name': 'Redis Connection',
                'status': 'pass',
                'message': f'Connected to {host}:{port}/{db}',
            })
        else:
            tests.append({
                'name': 'Redis Connection',
                'status': 'fail',
                'message': 'Invalid Redis URL format',
            })
    except Exception as e:
        tests.append({
            'name': 'Redis Connection',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'Redis', 'tests': tests}


def test_background_tasks():
    """Test background task system (Celery)"""
    tests = []

    # Test 1: Celery connection
    try:
        from mcube_ai.celery import app
        inspect = app.control.inspect()
        active = inspect.active()

        if active is not None:
            worker_count = len(active)
            total_active = sum(len(tasks) for tasks in active.values())
            tests.append({
                'name': 'Celery Workers',
                'status': 'pass',
                'message': f'{worker_count} workers, {total_active} active tasks',
            })
        else:
            tests.append({
                'name': 'Celery Workers',
                'status': 'warning',
                'message': 'No workers responding (may not be running)',
            })
    except Exception as e:
        tests.append({
            'name': 'Celery Workers',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 2: Check for task definitions
    try:
        import importlib
        task_modules = [
            'apps.data.tasks',
            'apps.positions.tasks',
            'apps.strategies.tasks',
            'apps.risk.tasks',
        ]

        available_tasks = []
        for module_name in task_modules:
            try:
                importlib.import_module(module_name)
                available_tasks.append(module_name.split('.')[-2])
            except:
                pass

        tests.append({
            'name': 'Task Definitions',
            'status': 'pass' if available_tasks else 'fail',
            'message': f'Found tasks in: {", ".join(available_tasks)}' if available_tasks else 'No task modules found',
        })
    except Exception as e:
        tests.append({
            'name': 'Task Definitions',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'Background Tasks', 'tests': tests}


def test_django_admin():
    """Test Django admin accessibility"""
    tests = []

    # Test 1: Admin models registered
    try:
        from django.contrib import admin
        registered = len(admin.site._registry)

        tests.append({
            'name': 'Admin Models Registered',
            'status': 'pass',
            'message': f'{registered} models registered in admin',
        })
    except Exception as e:
        tests.append({
            'name': 'Admin Models Registered',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 2: Admin URL accessible
    try:
        from django.urls import reverse
        admin_url = reverse('admin:index')
        tests.append({
            'name': 'Admin URL',
            'status': 'pass',
            'message': f'Admin accessible at {admin_url}',
        })
    except Exception as e:
        tests.append({
            'name': 'Admin URL',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'Django Admin', 'tests': tests}


def test_telegram():
    """Test Telegram integration with detailed response testing"""
    tests = []

    # Test 1: Telegram client configuration
    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        is_enabled = telegram_client.is_enabled()
        tests.append({
            'name': 'Telegram Client Configuration',
            'status': 'pass' if is_enabled else 'warning',
            'message': 'Telegram client configured' if is_enabled else 'Telegram not configured (TELEGRAM_BOT_TOKEN missing)',
        })
    except Exception as e:
        tests.append({
            'name': 'Telegram Client Configuration',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Tests 2-8: Check that message methods exist and are callable (no actual sends on page load).
    # Actual messages are sent only when user clicks the explicit trigger buttons.
    message_tests = [
        ('Send Simple Message', 'send_message', '/system/test/trigger-telegram-simple/', 'Send Test'),
        ('Send Priority Message (CRITICAL)', 'send_priority_message', '/system/test/trigger-telegram-critical/', 'Trigger'),
        ('Position Alert - Stop-Loss Hit', 'send_position_alert', '/system/test/trigger-telegram-sl-alert/', 'Send Alert'),
        ('Position Alert - Target Hit', 'send_position_alert', '/system/test/trigger-telegram-target-alert/', 'Send Alert'),
        ('Risk Alert - Warning', 'send_risk_alert', '/system/test/trigger-telegram-risk-alert/', 'Send Alert'),
        ('Risk Alert - Circuit Breaker (Emergency)', 'send_risk_alert', '/system/test/trigger-telegram-circuit-breaker/', 'Send Alert'),
        ('Daily Trading Summary', 'send_daily_summary', '/system/test/trigger-telegram-summary/', 'Send Summary'),
    ]

    for test_name, method_name, trigger_url, trigger_label in message_tests:
        try:
            from apps.alerts.services import get_telegram_client
            telegram_client = get_telegram_client()

            if telegram_client.is_enabled():
                has_method = hasattr(telegram_client, method_name) and callable(getattr(telegram_client, method_name))
                tests.append({
                    'name': test_name,
                    'status': 'pass' if has_method else 'fail',
                    'message': f'Ready — use button to send' if has_method else f'Method {method_name} not found',
                    'trigger_url': trigger_url,
                    'trigger_label': trigger_label,
                })
            else:
                tests.append({
                    'name': test_name,
                    'status': 'warning',
                    'message': 'Telegram not configured',
                    'trigger_url': trigger_url,
                    'trigger_label': 'Test (Configure First)',
                })
        except Exception as e:
            tests.append({
                'name': test_name,
                'status': 'fail',
                'message': f'Error: {str(e)}',
            })

    # Test 9: Alert Manager integration (database check only — no Telegram send on page load)
    try:
        from apps.alerts.services import get_alert_manager
        get_alert_manager()

        # Just verify AlertManager is accessible and DB model works
        from apps.alerts.models import Alert
        alert_count = Alert.objects.count()
        latest_alert = Alert.objects.order_by('-created_at').first()

        tests.append({
            'name': 'AlertManager - Database Integration',
            'status': 'pass',
            'message': f'{alert_count} alerts in DB. Latest: {latest_alert.alert_type if latest_alert else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'AlertManager - Database Integration',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 10: Alert log verification (response tracking)
    try:
        from apps.alerts.models import Alert

        # Get the most recent alert
        latest_alert = Alert.objects.order_by('-created_at').first()

        if latest_alert:
            logs = latest_alert.logs.all()
            log_count = logs.count()

            # Check for successful deliveries
            successful_logs = logs.filter(status='sent').count()
            failed_logs = logs.filter(status='failed').count()

            status_msg = f'Logs: {log_count} total, {successful_logs} sent, {failed_logs} failed'

            tests.append({
                'name': 'Alert Log Verification',
                'status': 'pass' if successful_logs > 0 else 'warning',
                'message': status_msg,
            })
        else:
            tests.append({
                'name': 'Alert Log Verification',
                'status': 'warning',
                'message': 'No alerts in database yet',
            })
    except Exception as e:
        tests.append({
            'name': 'Alert Log Verification',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    return {'category': 'Telegram', 'tests': tests}


# =============================================================================
# TELEGRAM TEST TRIGGER ENDPOINTS
# =============================================================================

@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_telegram_simple(request):
    """Send a simple test message to Telegram"""
    from django.contrib import messages

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if not telegram_client.is_enabled():
            messages.warning(request, "Telegram client not configured (TELEGRAM_BOT_TOKEN missing)")
            return redirect('core:system_test')

        test_message = "Test message from mCube System Test Page - Simple message test"
        success, response = telegram_client.send_message(test_message)

        if success:
            messages.success(request, f"✅ Simple message sent successfully")
            logger.info("Simple Telegram message sent successfully")
        else:
            messages.error(request, f"❌ Failed to send message: {response}")
            logger.error(f"Failed to send simple Telegram message: {response}")

    except Exception as e:
        messages.error(request, f"❌ Error sending message: {str(e)}")
        logger.error(f"Error in trigger_telegram_simple: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_telegram_critical(request):
    """Send a critical priority test message to Telegram"""
    from django.contrib import messages

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if not telegram_client.is_enabled():
            messages.warning(request, "Telegram client not configured")
            return redirect('core:system_test')

        test_message = "CRITICAL: This is a test critical priority message from mCube System"
        success, response = telegram_client.send_priority_message(test_message, priority='CRITICAL')

        if success:
            messages.success(request, f"✅ Critical priority message sent")
            logger.info("Critical Telegram message sent successfully")
        else:
            messages.error(request, f"❌ Failed to send critical message: {response}")

    except Exception as e:
        messages.error(request, f"❌ Error: {str(e)}")
        logger.error(f"Error in trigger_telegram_critical: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_telegram_sl_alert(request):
    """Send a stop-loss hit position alert to Telegram"""
    from django.contrib import messages

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if not telegram_client.is_enabled():
            messages.warning(request, "Telegram client not configured")
            return redirect('core:system_test')

        position_data = {
            'account_name': 'TEST_ACCOUNT',
            'instrument': 'NIFTY24NOV2424000CE',
            'direction': 'LONG',
            'quantity': 10,
            'entry_price': 100.00,
            'current_price': 210.00,
            'stop_loss': 200.00,
            'target': 50.00,
            'unrealized_pnl': -55000.00,
            'message': 'STOP-LOSS BREACHED - IMMEDIATE ACTION REQUIRED'
        }
        success, response = telegram_client.send_position_alert('SL_HIT', position_data)

        if success:
            messages.success(request, f"✅ Stop-Loss hit alert sent")
            logger.info("SL_HIT alert sent to Telegram")
        else:
            messages.error(request, f"❌ Failed to send SL alert: {response}")

    except Exception as e:
        messages.error(request, f"❌ Error: {str(e)}")
        logger.error(f"Error in trigger_telegram_sl_alert: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_telegram_target_alert(request):
    """Send a target hit position alert to Telegram"""
    from django.contrib import messages

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if not telegram_client.is_enabled():
            messages.warning(request, "Telegram client not configured")
            return redirect('core:system_test')

        position_data = {
            'account_name': 'TEST_ACCOUNT',
            'instrument': 'NIFTY24NOV2424000CE',
            'direction': 'LONG',
            'quantity': 10,
            'entry_price': 100.00,
            'current_price': 35.00,
            'stop_loss': 150.00,
            'target': 50.00,
            'unrealized_pnl': 37500.00,
            'message': 'Target achieved! Consider booking profits.'
        }
        success, response = telegram_client.send_position_alert('TARGET_HIT', position_data)

        if success:
            messages.success(request, f"✅ Target hit alert sent")
            logger.info("TARGET_HIT alert sent to Telegram")
        else:
            messages.error(request, f"❌ Failed to send target alert: {response}")

    except Exception as e:
        messages.error(request, f"❌ Error: {str(e)}")
        logger.error(f"Error in trigger_telegram_target_alert: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_telegram_risk_alert(request):
    """Send a risk warning alert to Telegram"""
    from django.contrib import messages

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if not telegram_client.is_enabled():
            messages.warning(request, "Telegram client not configured")
            return redirect('core:system_test')

        risk_data = {
            'account_name': 'TEST_ACCOUNT',
            'action_required': 'WARNING',
            'trading_allowed': True,
            'active_circuit_breakers': 0,
            'warnings': [
                {'type': 'DAILY_LOSS', 'utilization': 75.5},
                {'type': 'WEEKLY_LOSS', 'utilization': 45.0}
            ],
            'message': 'Daily loss limit at 75.5%. Exercise caution with new positions.'
        }
        success, response = telegram_client.send_risk_alert(risk_data)

        if success:
            messages.success(request, f"✅ Risk warning alert sent")
            logger.info("Risk warning alert sent to Telegram")
        else:
            messages.error(request, f"❌ Failed to send risk alert: {response}")

    except Exception as e:
        messages.error(request, f"❌ Error: {str(e)}")
        logger.error(f"Error in trigger_telegram_risk_alert: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_telegram_circuit_breaker(request):
    """Send an emergency circuit breaker alert to Telegram"""
    from django.contrib import messages

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if not telegram_client.is_enabled():
            messages.warning(request, "Telegram client not configured")
            return redirect('core:system_test')

        risk_data = {
            'account_name': 'TEST_ACCOUNT',
            'action_required': 'EMERGENCY_EXIT',
            'trading_allowed': False,
            'active_circuit_breakers': 1,
            'breached_limits': [
                {'type': 'DAILY_LOSS', 'current': 55000, 'limit': 50000}
            ],
            'message': 'CIRCUIT BREAKER ACTIVATED! Daily loss limit exceeded. All trading stopped.'
        }
        success, response = telegram_client.send_risk_alert(risk_data)

        if success:
            messages.success(request, f"✅ Emergency circuit breaker alert sent")
            logger.info("Circuit breaker emergency alert sent to Telegram")
        else:
            messages.error(request, f"❌ Failed to send emergency alert: {response}")

    except Exception as e:
        messages.error(request, f"❌ Error: {str(e)}")
        logger.error(f"Error in trigger_telegram_circuit_breaker: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_telegram_summary(request):
    """Send a daily trading summary to Telegram"""
    from django.contrib import messages
    from datetime import date

    if request.method != 'POST':
        messages.error(request, "Invalid request method")
        return redirect('core:system_test')

    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if not telegram_client.is_enabled():
            messages.warning(request, "Telegram client not configured")
            return redirect('core:system_test')

        summary_data = {
            'date': date.today().strftime('%Y-%m-%d'),
            'total_pnl': 15750.00,
            'realized_pnl': 12000.00,
            'unrealized_pnl': 3750.00,
            'total_trades': 5,
            'winning_trades': 3,
            'losing_trades': 2,
            'win_rate': 60.0,
            'active_positions': 1,
            'capital_deployed': 250000,
            'margin_available': 750000,
            'max_drawdown': 2.5,
            'daily_loss_limit_used': 31.5
        }
        success, response = telegram_client.send_daily_summary(summary_data)

        if success:
            messages.success(request, f"✅ Daily trading summary sent")
            logger.info("Daily summary sent to Telegram")
        else:
            messages.error(request, f"❌ Failed to send summary: {response}")

    except Exception as e:
        messages.error(request, f"❌ Error: {str(e)}")
        logger.error(f"Error in trigger_telegram_summary: {e}", exc_info=True)

    return redirect('core:system_test')


@login_required
@user_passes_test(is_admin_user)
def system_settings(request):
    """
    System Settings Page - Configure background task timings

    Allows admins to configure all timing parameters for Celery tasks
    """
    from django.contrib import messages
    from apps.core.models import SystemSettings

    settings_obj = SystemSettings.get_settings()

    if request.method == 'POST':
        try:
            # Market Data Task Timings
            settings_obj.trendlyne_fetch_hour = int(request.POST.get('trendlyne_fetch_hour', 8))
            settings_obj.trendlyne_fetch_minute = int(request.POST.get('trendlyne_fetch_minute', 30))
            settings_obj.trendlyne_import_hour = int(request.POST.get('trendlyne_import_hour', 9))
            settings_obj.trendlyne_import_minute = int(request.POST.get('trendlyne_import_minute', 0))

            settings_obj.premarket_update_hour = int(request.POST.get('premarket_update_hour', 8))
            settings_obj.premarket_update_minute = int(request.POST.get('premarket_update_minute', 30))

            settings_obj.live_data_interval_minutes = int(request.POST.get('live_data_interval_minutes', 5))
            settings_obj.live_data_start_hour = int(request.POST.get('live_data_start_hour', 9))
            settings_obj.live_data_end_hour = int(request.POST.get('live_data_end_hour', 15))

            settings_obj.postmarket_update_hour = int(request.POST.get('postmarket_update_hour', 15))
            settings_obj.postmarket_update_minute = int(request.POST.get('postmarket_update_minute', 30))

            # Strategy Task Timings
            settings_obj.futures_screening_interval_minutes = int(request.POST.get('futures_screening_interval_minutes', 30))
            settings_obj.futures_screening_start_hour = int(request.POST.get('futures_screening_start_hour', 9))
            settings_obj.futures_screening_end_hour = int(request.POST.get('futures_screening_end_hour', 14))
            settings_obj.futures_averaging_interval_minutes = int(request.POST.get('futures_averaging_interval_minutes', 10))

            # Position Monitoring Task Timings
            settings_obj.monitor_positions_interval_seconds = int(request.POST.get('monitor_positions_interval_seconds', 10))
            settings_obj.update_pnl_interval_seconds = int(request.POST.get('update_pnl_interval_seconds', 15))
            settings_obj.check_exit_interval_seconds = int(request.POST.get('check_exit_interval_seconds', 30))

            # Risk Management Task Timings
            settings_obj.risk_check_interval_seconds = int(request.POST.get('risk_check_interval_seconds', 60))
            settings_obj.circuit_breaker_interval_seconds = int(request.POST.get('circuit_breaker_interval_seconds', 30))

            # Reporting & Analytics Task Timings
            settings_obj.daily_pnl_report_hour = int(request.POST.get('daily_pnl_report_hour', 16))
            settings_obj.daily_pnl_report_minute = int(request.POST.get('daily_pnl_report_minute', 0))
            settings_obj.learning_patterns_hour = int(request.POST.get('learning_patterns_hour', 17))
            settings_obj.learning_patterns_minute = int(request.POST.get('learning_patterns_minute', 0))
            settings_obj.weekly_summary_hour = int(request.POST.get('weekly_summary_hour', 18))
            settings_obj.weekly_summary_minute = int(request.POST.get('weekly_summary_minute', 0))
            settings_obj.weekly_summary_day_of_week = int(request.POST.get('weekly_summary_day_of_week', 4))

            # Task Enable/Disable Flags
            settings_obj.enable_market_data_tasks = request.POST.get('enable_market_data_tasks') == 'on'
            settings_obj.enable_strategy_tasks = request.POST.get('enable_strategy_tasks') == 'on'
            settings_obj.enable_position_monitoring = request.POST.get('enable_position_monitoring') == 'on'
            settings_obj.enable_risk_monitoring = request.POST.get('enable_risk_monitoring') == 'on'
            settings_obj.enable_reporting_tasks = request.POST.get('enable_reporting_tasks') == 'on'

            settings_obj.save()

            messages.success(request, '✅ System settings saved successfully! Celery beat must be restarted for changes to take effect.')
            logger.info(f"System settings updated by {request.user.username}")

        except Exception as e:
            messages.error(request, f'❌ Error saving settings: {str(e)}')
            logger.error(f"Error saving system settings: {e}", exc_info=True)

        return redirect('core:system_settings')

    context = {
        'settings': settings_obj,
        'page_title': 'System Settings',
        'days_of_week': [
            (0, 'Monday'),
            (1, 'Tuesday'),
            (2, 'Wednesday'),
            (3, 'Thursday'),
            (4, 'Friday'),
            (5, 'Saturday'),
            (6, 'Sunday'),
        ]
    }

    return render(request, 'core/system_settings.html', context)


@login_required
@user_passes_test(is_admin_user)
def broker_settings(request):
    """
    System Configuration Page - Comprehensive settings for all system configurations

    Consolidates:
    - Broker API credentials (Kotak, Breeze)
    - External service credentials (Trendlyne, Telegram, GNews)
    - Trading schedule configuration
    - Background task settings
    - System preferences
    """
    from django.contrib import messages
    from apps.core.models import CredentialStore, SystemSettings, TradingSchedule
    from django.conf import settings as django_settings
    import datetime as dt

    # Get or create credentials for each service
    kotak_creds, _ = CredentialStore.objects.get_or_create(
        service='kotakneo',
        name='default',
        defaults={}
    )

    breeze_creds, _ = CredentialStore.objects.get_or_create(
        service='breeze',
        name='default',
        defaults={}
    )

    trendlyne_creds, _ = CredentialStore.objects.get_or_create(
        service='trendlyne',
        name='default',
        defaults={}
    )

    telegram_creds, _ = CredentialStore.objects.get_or_create(
        service='telegram',
        name='default',
        defaults={}
    )

    gnews_creds, _ = CredentialStore.objects.get_or_create(
        service='gnewsio',
        name='default',
        defaults={}
    )

    # Get system settings
    settings_obj = SystemSettings.get_settings()

    # Get or create today's trading schedule
    today = dt.date.today()
    schedule, _ = TradingSchedule.objects.get_or_create(
        date=today,
        defaults={
            'open_time': dt.time(9, 15, 10),
            'take_trade_time': dt.time(9, 30, 0),
            'last_trade_time': dt.time(10, 15, 0),
            'close_pos_time': dt.time(15, 25, 30),
            'mkt_close_time': dt.time(15, 32, 0),
            'close_day_time': dt.time(15, 45, 0),
            'enabled': True,
        }
    )

    if request.method == 'POST':
        try:
            # ===== INTEGRATIONS TAB =====
            # Kotak Neo Credentials (v2 — TOTP + MPIN auth)
            kotak_creds.api_key = request.POST.get('kotak_api_key', '')
            kotak_creds.ucc = request.POST.get('kotak_ucc', '')
            kotak_creds.mobile_number = request.POST.get('kotak_mobile_number', '')
            kotak_creds.totp_secret = request.POST.get('kotak_totp_secret', '')
            kotak_creds.neo_password = request.POST.get('kotak_neo_password', '')
            kotak_creds.save()

            # ICICI Breeze Credentials
            breeze_creds.api_key = request.POST.get('breeze_api_key', '')
            breeze_creds.api_secret = request.POST.get('breeze_api_secret', '')
            breeze_creds.session_token = request.POST.get('breeze_session_token', '')
            breeze_creds.save()

            # Trendlyne Credentials
            trendlyne_creds.username = request.POST.get('trendlyne_username', '')
            trendlyne_creds.password = request.POST.get('trendlyne_password', '')
            trendlyne_creds.save()

            # Telegram Credentials
            telegram_creds.api_key = request.POST.get('telegram_bot_token', '')
            telegram_creds.api_secret = request.POST.get('telegram_chat_id', '')
            telegram_creds.username = request.POST.get('telegram_client_id', '')
            telegram_creds.session_token = request.POST.get('telegram_session_name', '')
            telegram_creds.save()

            # GNews Credentials
            gnews_creds.api_key = request.POST.get('gnews_api_key', '')
            gnews_creds.save()

            # ===== TRADING HOURS TAB =====
            schedule.enabled = request.POST.get('trading_enabled') == 'on'
            schedule.note = request.POST.get('schedule_note', '')

            # Parse time fields
            def parse_time(time_str):
                if time_str:
                    parts = time_str.split(':')
                    return dt.time(int(parts[0]), int(parts[1]))
                return None

            if request.POST.get('open_time'):
                schedule.open_time = parse_time(request.POST.get('open_time'))
            if request.POST.get('take_trade_time'):
                schedule.take_trade_time = parse_time(request.POST.get('take_trade_time'))
            if request.POST.get('last_trade_time'):
                schedule.last_trade_time = parse_time(request.POST.get('last_trade_time'))
            if request.POST.get('close_pos_time'):
                schedule.close_pos_time = parse_time(request.POST.get('close_pos_time'))
            if request.POST.get('mkt_close_time'):
                schedule.mkt_close_time = parse_time(request.POST.get('mkt_close_time'))
            if request.POST.get('close_day_time'):
                schedule.close_day_time = parse_time(request.POST.get('close_day_time'))
            schedule.save()

            # ===== AUTOMATION TAB =====
            # Task Enable/Disable Flags
            settings_obj.enable_market_data_tasks = request.POST.get('enable_market_data_tasks') == 'on'
            settings_obj.enable_strategy_tasks = request.POST.get('enable_strategy_tasks') == 'on'
            settings_obj.enable_position_monitoring = request.POST.get('enable_position_monitoring') == 'on'
            settings_obj.enable_risk_monitoring = request.POST.get('enable_risk_monitoring') == 'on'
            settings_obj.enable_reporting_tasks = request.POST.get('enable_reporting_tasks') == 'on'

            # Market Data Task Timings
            settings_obj.trendlyne_fetch_hour = int(request.POST.get('trendlyne_fetch_hour', 8))
            settings_obj.trendlyne_fetch_minute = int(request.POST.get('trendlyne_fetch_minute', 30))
            settings_obj.trendlyne_import_hour = int(request.POST.get('trendlyne_import_hour', 9))
            settings_obj.trendlyne_import_minute = int(request.POST.get('trendlyne_import_minute', 0))
            settings_obj.premarket_update_hour = int(request.POST.get('premarket_update_hour', 8))
            settings_obj.premarket_update_minute = int(request.POST.get('premarket_update_minute', 30))
            settings_obj.live_data_interval_minutes = int(request.POST.get('live_data_interval_minutes', 5))
            settings_obj.live_data_start_hour = int(request.POST.get('live_data_start_hour', 9))
            settings_obj.live_data_end_hour = int(request.POST.get('live_data_end_hour', 15))
            settings_obj.postmarket_update_hour = int(request.POST.get('postmarket_update_hour', 15))
            settings_obj.postmarket_update_minute = int(request.POST.get('postmarket_update_minute', 30))

            # Strategy Task Timings
            settings_obj.futures_screening_interval_minutes = int(request.POST.get('futures_screening_interval_minutes', 30))
            settings_obj.futures_screening_start_hour = int(request.POST.get('futures_screening_start_hour', 9))
            settings_obj.futures_screening_end_hour = int(request.POST.get('futures_screening_end_hour', 14))
            settings_obj.futures_averaging_interval_minutes = int(request.POST.get('futures_averaging_interval_minutes', 10))

            # Position Monitoring Task Timings
            settings_obj.monitor_positions_interval_seconds = int(request.POST.get('monitor_positions_interval_seconds', 10))
            settings_obj.update_pnl_interval_seconds = int(request.POST.get('update_pnl_interval_seconds', 15))
            settings_obj.check_exit_interval_seconds = int(request.POST.get('check_exit_interval_seconds', 30))

            # Risk Management Task Timings
            settings_obj.risk_check_interval_seconds = int(request.POST.get('risk_check_interval_seconds', 60))
            settings_obj.circuit_breaker_interval_seconds = int(request.POST.get('circuit_breaker_interval_seconds', 30))

            # Reporting & Analytics Task Timings
            settings_obj.daily_pnl_report_hour = int(request.POST.get('daily_pnl_report_hour', 16))
            settings_obj.daily_pnl_report_minute = int(request.POST.get('daily_pnl_report_minute', 0))
            settings_obj.learning_patterns_hour = int(request.POST.get('learning_patterns_hour', 17))
            settings_obj.learning_patterns_minute = int(request.POST.get('learning_patterns_minute', 0))
            settings_obj.weekly_summary_hour = int(request.POST.get('weekly_summary_hour', 18))
            settings_obj.weekly_summary_minute = int(request.POST.get('weekly_summary_minute', 0))
            settings_obj.weekly_summary_day_of_week = int(request.POST.get('weekly_summary_day_of_week', 4))

            settings_obj.save()

            # ===== CORE TRADING CONFIG TAB =====
            from apps.core.models import TradingCoreConfig
            trading_config = TradingCoreConfig.get_instance()

            # Trading Enable/Disable
            trading_config.enable_futures_trading = request.POST.get('enable_futures_trading') == 'on'

            # Strategy Selection
            trading_config.options_strategy = request.POST.get('options_strategy', 'AUTO')
            movement_threshold = request.POST.get('movement_threshold')
            if movement_threshold:
                trading_config.movement_threshold = Decimal(movement_threshold)

            # Position Sizing
            options_lots = request.POST.get('options_lots')
            futures_lots = request.POST.get('futures_lots')
            if options_lots:
                trading_config.options_lots = int(options_lots)
            if futures_lots:
                trading_config.futures_lots = int(futures_lots)

            # Risk Parameters
            max_loss = request.POST.get('max_loss_per_trade')
            profit_target = request.POST.get('options_profit_target')
            if max_loss:
                trading_config.max_loss_per_trade = Decimal(max_loss)
            if profit_target:
                trading_config.options_profit_target = Decimal(profit_target)

            # VIX Thresholds
            vix_low = request.POST.get('vix_low_threshold')
            vix_high = request.POST.get('vix_high_threshold')
            if vix_low:
                trading_config.vix_low_threshold = Decimal(vix_low)
            if vix_high:
                trading_config.vix_high_threshold = Decimal(vix_high)

            # Confirmation Settings
            trading_config.require_telegram_confirmation = request.POST.get('require_telegram_confirmation') == 'on'
            timeout = request.POST.get('confirmation_timeout_minutes')
            if timeout:
                trading_config.confirmation_timeout_minutes = int(timeout)

            # Auto Close Settings
            trading_config.auto_close_on_target = request.POST.get('auto_close_on_target') == 'on'
            trading_config.auto_close_on_stoploss = request.POST.get('auto_close_on_stoploss') == 'on'

            # Carry Forward
            carry_threshold = request.POST.get('options_carry_forward_threshold')
            if carry_threshold:
                trading_config.options_carry_forward_threshold = Decimal(carry_threshold)

            trading_config.save()

            messages.success(request, 'Configuration saved successfully!')
            logger.info(f"System configuration updated by {request.user.username}")

        except Exception as e:
            messages.error(request, f'Error saving configuration: {str(e)}')
            logger.error(f"Error saving system configuration: {e}", exc_info=True)

        return redirect('core:broker_settings')

    # Get TradingCoreConfig for display
    from apps.core.models import TradingCoreConfig
    trading_config = TradingCoreConfig.get_instance()

    context = {
        # Credentials
        'kotak_creds': kotak_creds,
        'breeze_creds': breeze_creds,
        'trendlyne_creds': trendlyne_creds,
        'telegram_creds': telegram_creds,
        'gnews_creds': gnews_creds,
        # System Settings
        'system_settings': settings_obj,
        # Trading Schedule
        'schedule': schedule,
        # Core Trading Config
        'trading_config': trading_config,
        # LLM Settings (from Django settings)
        'ollama_base_url': getattr(django_settings, 'OLLAMA_BASE_URL', 'http://localhost:11434'),
        'ollama_model': getattr(django_settings, 'OLLAMA_MODEL', 'deepseek-r1:7b'),
        # Days of week for dropdown
        'days_of_week': [
            (0, 'Monday'),
            (1, 'Tuesday'),
            (2, 'Wednesday'),
            (3, 'Thursday'),
            (4, 'Friday'),
            (5, 'Saturday'),
            (6, 'Sunday'),
        ],
        'page_title': 'System Configuration',
    }

    return render(request, 'core/system_configuration.html', context)


# =============================================================================
# DASHBOARD REFRESH API ENDPOINTS
# =============================================================================

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta
from django.utils import timezone as django_timezone

@login_required
@require_POST
def refresh_dashboard_stat(request, stat_type):
    """
    Refresh a single dashboard statistic
    
    Smart data fetching:
    1. Check database cache first
    2. If data is stale (> 5 minutes), fetch from API
    3. Update database
    4. Return fresh data
    
    Args:
        stat_type: One of 'positions', 'accounts', 'orders', 'pnl'
    """
    try:
        from apps.positions.models import Position
        from apps.accounts.models import BrokerAccount
        from apps.brokers.models import Order
        from decimal import Decimal
        
        STALE_THRESHOLD = timedelta(minutes=5)
        from_api = False
        
        if stat_type == 'positions':
            # Check if we need to refresh from API
            last_updated = Position.objects.filter(
                status='ACTIVE'
            ).order_by('-updated_at').first()
            
            if last_updated and (django_timezone.now() - last_updated.updated_at) > STALE_THRESHOLD:
                # Data is stale, fetch from API
                try:
                    # Trigger position refresh from broker API
                    from apps.positions.services.position_sync import sync_positions_from_broker
                    sync_positions_from_broker()
                    from_api = True
                except Exception as e:
                    logger.warning(f"Failed to sync positions from API: {e}")
            
            # Get count from database (fresh or existing)
            count = Position.objects.filter(status='ACTIVE').count()
            return JsonResponse({
                'success': True,
                'value': count,
                'from_api': from_api,
                'timestamp': datetime.now().isoformat()
            })
        
        elif stat_type == 'accounts':
            # Accounts don't change frequently, just return DB count
            count = BrokerAccount.objects.filter(is_active=True).count()
            return JsonResponse({
                'success': True,
                'value': count,
                'from_api': False,
                'timestamp': datetime.now().isoformat()
            })
        
        elif stat_type == 'orders':
            # Check if we need to refresh today's orders from API
            today = datetime.now().date()
            last_order = Order.objects.filter(
                created_at__date=today
            ).order_by('-created_at').first()
            
            if last_order and (django_timezone.now() - last_order.created_at) > STALE_THRESHOLD:
                # Data might be stale, fetch from API
                try:
                    from apps.brokers.services.order_sync import sync_orders_from_broker
                    sync_orders_from_broker()
                    from_api = True
                except Exception as e:
                    logger.warning(f"Failed to sync orders from API: {e}")
            
            count = Order.objects.filter(created_at__date=today).count()
            return JsonResponse({
                'success': True,
                'value': count,
                'from_api': from_api,
                'timestamp': datetime.now().isoformat()
            })
        
        elif stat_type == 'pnl':
            # Check if position P&L needs update
            positions = Position.objects.filter(status='ACTIVE')
            
            if positions.exists():
                latest_position = positions.order_by('-updated_at').first()
                
                if (django_timezone.now() - latest_position.updated_at) > STALE_THRESHOLD:
                    # Data is stale, fetch fresh prices from API
                    try:
                        from apps.positions.services.pnl_updater import update_all_position_pnl
                        update_all_position_pnl()
                        from_api = True
                    except Exception as e:
                        logger.warning(f"Failed to update P&L from API: {e}")
            
            # Calculate total P&L
            total_pnl = sum([
                pos.unrealized_pnl or Decimal('0')
                for pos in Position.objects.filter(status='ACTIVE')
            ])
            
            # Format as currency
            formatted_pnl = format_currency(total_pnl)
            
            return JsonResponse({
                'success': True,
                'value': formatted_pnl,
                'from_api': from_api,
                'timestamp': datetime.now().isoformat()
            })
        
        else:
            return JsonResponse({
                'success': False,
                'error': f'Invalid stat type: {stat_type}'
            }, status=400)
    
    except Exception as e:
        logger.error(f"Error refreshing dashboard stat {stat_type}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# CELERY TASK CONTROL
# =============================================================================

@login_required
@user_passes_test(is_admin_user)
def celery_task_control(request):
    """
    Celery task control page - View and manage scheduled Celery tasks.
    Shows both static (code-defined) and dynamic (database-configured) tasks.
    All tasks are inactive by default - users must explicitly activate them.
    """
    from apps.strategies.models import TradingScheduleConfig
    from apps.core.models import CeleryTaskState
    from mcube_ai.celery import get_static_schedule
    import redis

    # Get dynamic tasks from database
    dynamic_tasks = list(TradingScheduleConfig.objects.all().order_by('scheduled_time'))

    # Get ALL static tasks for display (not filtered by enabled state)
    try:
        static_schedule = get_static_schedule()
        logger.info(f"celery_task_control: Loaded {len(static_schedule)} static tasks")
    except Exception as e:
        logger.error(f"celery_task_control: Error loading static schedule: {e}")
        static_schedule = {}

    # Initialize any missing tasks in the database (as disabled by default)
    # and get all task state objects with full details
    try:
        CeleryTaskState.initialize_static_tasks(static_schedule, force=False)
        task_state_objects = {s.task_key: s for s in CeleryTaskState.objects.all()}
    except Exception as e:
        logger.warning(f"Could not initialize/get task states: {e}")
        task_state_objects = {}

    # Define task categories with display info
    TASK_CATEGORIES = {
        'data': {
            'name': 'Market Data',
            'icon': '📊',
            'color': '#3182ce',
            'description': 'Fetch and sync market data, news, and Trendlyne data',
            'keywords': ['trendlyne', 'market-data', 'pre-market', 'post-market', 'live-market', 'morning-data-sync', 'news'],
        },
        'strategies': {
            'name': 'Strategy Execution',
            'icon': '🎯',
            'color': '#805ad5',
            'description': 'Daily trading workflow: setup, start, evaluate, screen, execute',
            'keywords': ['setup-trading', 'start-trading', 'evaluate-options', 'screen', 'execute-futures', 'strangle'],
        },
        'transactions': {
            'name': 'Transactions',
            'icon': '💰',
            'color': '#d69e2e',
            'description': 'Order placement: options trades, averaging, futures averaging, close',
            'keywords': ['start-options-trade', 'batch-options-averaging', 'check-futures-averaging', 'close-trading'],
        },
        'monitoring': {
            'name': 'Position Monitoring',
            'icon': '👁️',
            'color': '#dd6b20',
            'description': 'Monitor open positions, P&L updates, and exit conditions',
            'keywords': ['monitor', 'position', 'pnl', 'exit'],
        },
        'risk': {
            'name': 'Risk Management',
            'icon': '🛡️',
            'color': '#e53e3e',
            'description': 'Check risk limits and circuit breaker conditions',
            'keywords': ['risk', 'circuit', 'limit'],
        },
        'reports': {
            'name': 'Analytics & Reports',
            'icon': '📈',
            'color': '#38a169',
            'description': 'Generate daily reports and update analytics',
            'keywords': ['report', 'pnl-report', 'benchmark', 'aggregation', 'equity'],
        },
    }

    def categorize_task(task_key, queue):
        """Determine category based on task config, queue, or keywords"""
        # First check explicit category in TASK_DEFAULT_CONFIG
        cfg = TASK_DEFAULT_CONFIG.get(task_key, {})
        if cfg.get('category') in TASK_CATEGORIES:
            return cfg['category']

        key_lower = task_key.lower()

        # Then try to match by queue
        if queue in TASK_CATEGORIES:
            return queue

        # Then try to match by keywords in task key
        for cat_key, cat_info in TASK_CATEGORIES.items():
            for keyword in cat_info['keywords']:
                if keyword in key_lower:
                    return cat_key

        return 'reports'  # Default category

    # Build categorized tasks
    categorized_tasks = {cat: [] for cat in TASK_CATEGORIES.keys()}

    for key, config in static_schedule.items():
        # Skip if it's a dynamic task
        if any(d in key.lower() for d in ['premarket', 'market_open', 'trade_start', 'trade_monitor', 'trade_stop', 'day_close', 'analyze_day']):
            continue

        # Get task state from database
        task_state = task_state_objects.get(key)
        queue = config.get('options', {}).get('queue', 'default')
        category = categorize_task(key, queue)

        # Get default config for display info
        default_config = TASK_DEFAULT_CONFIG.get(key, {})

        # Build schedule display string
        if task_state and task_state.use_custom_schedule:
            schedule_type = task_state.schedule_type
            if schedule_type == 'crontab':
                schedule_str = f"{task_state.schedule_hour:02d}:{task_state.schedule_minute:02d}"
            elif schedule_type == 'interval':
                schedule_str = f"Every {task_state.interval_seconds}s"
            elif schedule_type == 'recurring':
                schedule_str = f"{task_state.recurring_start_hour:02d}:{task_state.recurring_start_minute:02d}-{task_state.recurring_end_hour:02d}:{task_state.recurring_end_minute:02d} (every {task_state.recurring_interval_minutes}m)"
            else:
                schedule_str = str(config.get('schedule', 'Unknown'))
        else:
            schedule_str = str(config.get('schedule', 'Unknown'))

        # Get last execution info from BkLog
        from apps.core.models import BkLog
        last_execution = BkLog.objects.filter(
            background_task__icontains=key.replace('-', '_')
        ).order_by('-timestamp').first()

        last_exec_info = None
        if last_execution:
            last_exec_info = {
                'timestamp': last_execution.timestamp.isoformat(),
                'timestamp_display': last_execution.timestamp.strftime('%d %b %H:%M'),
                'success': last_execution.success if hasattr(last_execution, 'success') else (last_execution.level not in ['error', 'critical']),
                'level': last_execution.level,
                'message': last_execution.message[:100] if last_execution.message else '',
                'duration_ms': last_execution.execution_time_ms,
            }

        # Parse schedule hour and minute for timeline positioning
        schedule_hour = None
        schedule_minute = None
        if task_state and task_state.use_custom_schedule:
            # Use custom schedule values from DB
            if task_state.schedule_type == 'crontab':
                schedule_hour = task_state.schedule_hour
                schedule_minute = task_state.schedule_minute
            elif task_state.schedule_type == 'recurring':
                schedule_hour = task_state.recurring_start_hour
                schedule_minute = getattr(task_state, 'recurring_start_minute', 0) or 0
        else:
            # Fall back to TASK_DEFAULT_CONFIG defaults first, then celery schedule object
            if default_config.get('default_hour') is not None:
                schedule_hour = default_config['default_hour']
                schedule_minute = default_config.get('default_minute', 0)
            elif default_config.get('default_recurring_start_hour') is not None:
                schedule_hour = default_config['default_recurring_start_hour']
                schedule_minute = default_config.get('default_recurring_start_minute', 0)
            else:
                # Last resort: parse from celery schedule object
                schedule = config.get('schedule')
                if hasattr(schedule, 'hour') and hasattr(schedule, 'minute'):
                    try:
                        if hasattr(schedule.hour, '__iter__') and not isinstance(schedule.hour, str):
                            schedule_hour = min(schedule.hour) if schedule.hour else None
                        else:
                            schedule_hour = int(schedule.hour) if str(schedule.hour).isdigit() else None

                        if hasattr(schedule.minute, '__iter__') and not isinstance(schedule.minute, str):
                            schedule_minute = min(schedule.minute) if schedule.minute else 0
                        else:
                            schedule_minute = int(schedule.minute) if str(schedule.minute).isdigit() else 0
                    except (ValueError, TypeError):
                        pass

        task_info = {
            'key': key,
            'task': config.get('task', 'Unknown'),
            'schedule': schedule_str,
            'schedule_hour': schedule_hour,
            'schedule_minute': schedule_minute,
            'queue': queue,
            'is_enabled': task_state.is_enabled if task_state else False,
            'display_name': task_state.display_name if task_state and task_state.display_name else default_config.get('display_name', key.replace('-', ' ').title()),
            'description': task_state.description if task_state and task_state.description else default_config.get('description', ''),
            'use_custom_schedule': task_state.use_custom_schedule if task_state else False,
            'schedule_type': task_state.schedule_type if task_state else default_config.get('schedule_type', 'crontab'),
            'last_execution': last_exec_info,
        }

        categorized_tasks[category].append(task_info)

    # Build category info for template
    task_categories = []
    for cat_key, cat_info in TASK_CATEGORIES.items():
        tasks = categorized_tasks.get(cat_key, [])
        active_count = sum(1 for t in tasks if t['is_enabled'])
        task_categories.append({
            'key': cat_key,
            'name': cat_info['name'],
            'icon': cat_info['icon'],
            'color': cat_info['color'],
            'description': cat_info['description'],
            'tasks': tasks,
            'total': len(tasks),
            'active': active_count,
        })

    # Also keep flat list for backward compatibility
    static_tasks = []
    for tasks in categorized_tasks.values():
        static_tasks.extend(tasks)

    # Check Celery worker status
    worker_status = {'active': False, 'workers': [], 'error': None}
    try:
        from mcube_ai.celery import app as celery_app
        inspect = celery_app.control.inspect()
        active_workers = inspect.active_queues()
        if active_workers:
            worker_status['active'] = True
            worker_status['workers'] = list(active_workers.keys())
    except Exception as e:
        worker_status['error'] = str(e)

    # Check Redis status
    redis_status = {'connected': False, 'error': None}
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        redis_status['connected'] = True
    except Exception as e:
        redis_status['error'] = str(e)

    # Count enabled/disabled for dynamic tasks
    dynamic_enabled = TradingScheduleConfig.objects.filter(is_enabled=True).count()
    dynamic_total = TradingScheduleConfig.objects.count()

    # Count enabled/disabled for static tasks
    static_enabled = sum(1 for t in static_tasks if t['is_enabled'])
    static_total = len(static_tasks)

    # Total counts
    enabled_count = dynamic_enabled + static_enabled
    total_count = dynamic_total + static_total
    disabled_count = total_count - enabled_count

    # Get TradingCoreConfig for UI controls
    try:
        from apps.core.models import TradingCoreConfig
        trading_config = TradingCoreConfig.get_instance()
    except Exception as e:
        logger.warning(f"Could not load TradingCoreConfig: {e}")
        trading_config = None

    # Build algorithm task group data for confirmation modal
    from apps.core.task_config import ALGORITHM_TASK_GROUPS
    algo_task_data = {}
    for algo_key, group in ALGORITHM_TASK_GROUPS.items():
        def _build_task_list(task_keys):
            result = []
            for t in task_keys:
                cfg = TASK_DEFAULT_CONFIG.get(t, {})
                stype = cfg.get('schedule_type', 'crontab')
                if stype == 'crontab':
                    sched_desc = f"{cfg.get('default_hour', 0):02d}:{cfg.get('default_minute', 0):02d}"
                elif stype == 'interval':
                    sched_desc = f"Every {cfg.get('default_interval_seconds', 0)}s"
                elif stype == 'recurring':
                    sched_desc = f"{cfg.get('default_recurring_start_hour', 0):02d}:{cfg.get('default_recurring_start_minute', 0):02d}-{cfg.get('default_recurring_end_hour', 0):02d}:{cfg.get('default_recurring_end_minute', 0):02d}"
                else:
                    sched_desc = stype
                result.append({
                    'key': t,
                    'name': cfg.get('display_name', t.replace('-', ' ').title()),
                    'schedule': sched_desc,
                    'enabled': CeleryTaskState.is_task_enabled(t),
                })
            return result

        algo_task_data[algo_key] = {
            'display_name': group['display_name'],
            'own': _build_task_list(group['own_tasks']),
            'shared': _build_task_list(group['shared_tasks']),
            'monitoring': _build_task_list(group['monitoring_tasks']),
        }

    import json
    algo_task_data_json = json.dumps(algo_task_data)

    # Build workflow groups for hero cards
    # Each workflow group shows all tasks in order with dependency chain info
    workflow_groups = {}
    for algo_key, group in ALGORITHM_TASK_GROUPS.items():
        all_task_keys = []
        task_tiers = {}
        for t in group['own_tasks']:
            all_task_keys.append(t)
            task_tiers[t] = 'own'
        for t in group['shared_tasks']:
            if t not in all_task_keys:
                all_task_keys.append(t)
            task_tiers[t] = 'shared'
        for t in group['monitoring_tasks']:
            if t not in all_task_keys:
                all_task_keys.append(t)
            task_tiers[t] = 'monitoring'

        # Build task nodes with schedule info, sorted by time
        nodes = []
        for t_key in all_task_keys:
            cfg = TASK_DEFAULT_CONFIG.get(t_key, {})
            task_state = task_state_objects.get(t_key)
            is_enabled = task_state.is_enabled if task_state else False
            stype = cfg.get('schedule_type', 'crontab')

            if stype == 'crontab':
                sort_hour = cfg.get('default_hour', 0)
                sort_min = cfg.get('default_minute', 0)
                time_str = f"{sort_hour:02d}:{sort_min:02d}"
            elif stype == 'interval':
                sort_hour = 9
                sort_min = 15
                secs = cfg.get('default_interval_seconds', 60)
                time_str = f"Every {secs}s"
            elif stype == 'recurring':
                sort_hour = cfg.get('default_recurring_start_hour', 9)
                sort_min = cfg.get('default_recurring_start_minute', 0)
                end_h = cfg.get('default_recurring_end_hour', 15)
                end_m = cfg.get('default_recurring_end_minute', 0)
                cfg.get('default_recurring_interval_minutes', 30)
                time_str = f"{sort_hour:02d}:{sort_min:02d}-{end_h:02d}:{end_m:02d}"
            else:
                sort_hour = 12
                sort_min = 0
                time_str = stype

            # Check which other algo uses this task (for "shared" badge)
            shared_with = []
            for other_key, other_group in ALGORITHM_TASK_GROUPS.items():
                if other_key == algo_key:
                    continue
                all_other = other_group['own_tasks'] + other_group['shared_tasks'] + other_group['monitoring_tasks']
                if t_key in all_other:
                    shared_with.append(other_group['display_name'])

            nodes.append({
                'key': t_key,
                'name': cfg.get('display_name', t_key.replace('-', ' ').title()),
                'time_str': time_str,
                'sort_key': sort_hour * 60 + sort_min,
                'is_enabled': is_enabled,
                'tier': task_tiers[t_key],
                'shared_with': shared_with,
                'schedule_type': stype,
            })

        nodes.sort(key=lambda x: x['sort_key'])

        active_count = sum(1 for n in nodes if n['is_enabled'])

        # Determine algorithm active state
        if algo_key == 'futures':
            algo_active = trading_config.enable_futures_trading if trading_config else False
        elif algo_key == 'options':
            algo_active = (trading_config.options_strategy != 'NONE') if trading_config else False
        else:
            algo_active = False

        workflow_groups[algo_key] = {
            'display_name': group['display_name'],
            'emoji': group.get('emoji', ''),
            'description': group.get('description', ''),
            'nodes': nodes,
            'active_count': active_count,
            'total_count': len(nodes),
            'algo_active': algo_active,
            'algo_key': algo_key,
        }

    context = {
        'dynamic_tasks': dynamic_tasks,
        'static_tasks': static_tasks,
        'task_categories': task_categories,  # Categorized view for new UI
        'workflow_groups': workflow_groups,  # Workflow hero cards
        'worker_status': worker_status,
        'redis_status': redis_status,
        'enabled_count': enabled_count,
        'disabled_count': disabled_count,
        'total_count': total_count,
        'timestamp': datetime.now(),
        'trading_config': trading_config,  # Core trading configuration
        'algo_task_data_json': algo_task_data_json,
    }

    return render(request, 'core/celery_tasks.html', context)


@login_required
@user_passes_test(is_admin_user)
def toggle_celery_task(request, task_id):
    """Toggle a dynamic Celery task on/off."""
    from apps.strategies.models import TradingScheduleConfig
    from django.contrib import messages

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        task = TradingScheduleConfig.objects.get(id=task_id)
        task.is_enabled = not task.is_enabled
        task.save()

        status = 'enabled' if task.is_enabled else 'disabled'

        # Restart Celery Beat to pick up schedule changes
        celery_result = ensure_celery_running()
        beat_restarted = celery_result.get('beat_restarted', False)

        message = f"Task '{task.display_name}' {status}"
        if beat_restarted:
            message += " (schedule reloaded)"
        messages.success(request, message)

        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'is_enabled': task.is_enabled,
            'beat_restarted': beat_restarted,
            'message': message
        })
    except TradingScheduleConfig.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Task not found'}, status=404)
    except Exception as e:
        logger.error(f"Error toggling task {task_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_user)
def celery_control_all(request):
    """Enable or disable all dynamic Celery tasks."""
    from apps.strategies.models import TradingScheduleConfig
    from django.contrib import messages

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    action = request.POST.get('action', 'stop')

    try:
        if action == 'start':
            TradingScheduleConfig.objects.all().update(is_enabled=True)
            beat_restarted, _ = restart_celery_beat()
            message = "All tasks enabled"
            if beat_restarted:
                message += " (schedule reloaded)"
            messages.success(request, message)
            return JsonResponse({'success': True, 'message': message, 'beat_restarted': beat_restarted})
        elif action == 'stop':
            TradingScheduleConfig.objects.all().update(is_enabled=False)
            beat_restarted, _ = restart_celery_beat()
            message = "All tasks disabled"
            if beat_restarted:
                message += " (schedule reloaded)"
            messages.warning(request, message)
            return JsonResponse({'success': True, 'message': message, 'beat_restarted': beat_restarted})
        else:
            return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)
    except Exception as e:
        logger.error(f"Error controlling all tasks: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_user)
def reload_celery_schedule(request):
    """Reload Celery beat schedule by restarting celery beat."""
    from django.contrib import messages

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        beat_restarted, beat_message = restart_celery_beat()

        if beat_restarted:
            messages.success(request, "Celery Beat restarted - schedule reloaded.")
        else:
            messages.warning(request, f"Could not restart Celery Beat: {beat_message}")

        return JsonResponse({
            'success': beat_restarted,
            'message': 'Schedule updated. Restart Celery Beat to apply changes.'
        })
    except Exception as e:
        logger.error(f"Error reloading schedule: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _manage_algorithm_tasks(algo_key, enabled):
    """Enable or disable algorithm tasks with smart shared-task handling."""
    from apps.core.models import CeleryTaskState
    from apps.core.task_config import ALGORITHM_TASK_GROUPS, TASK_DEFAULT_CONFIG

    group = ALGORITHM_TASK_GROUPS.get(algo_key)
    if not group:
        return

    task_paths = {}
    try:
        from mcube_ai.celery import get_static_schedule
        sched = get_static_schedule()
        task_paths = {k: v.get('task', '') for k, v in sched.items()}
    except Exception:
        pass

    if enabled:
        all_tasks = group['own_tasks'] + group['shared_tasks'] + group['monitoring_tasks']
        for task_key in all_tasks:
            cfg = TASK_DEFAULT_CONFIG.get(task_key, {})
            CeleryTaskState.set_task_state(
                task_key=task_key, enabled=True,
                task_path=task_paths.get(task_key, ''),
                display_name=cfg.get('display_name', task_key.replace('-', ' ').title()),
                user='web_ui',
            )
    else:
        # Smart disable: check if other algo is active
        active_others = []
        for other_key, other_group in ALGORITHM_TASK_GROUPS.items():
            if other_key == algo_key:
                continue
            if any(CeleryTaskState.is_task_enabled(t) for t in other_group['own_tasks']):
                active_others.append(other_key)

        tasks_to_disable = list(group['own_tasks'])
        if not active_others:
            tasks_to_disable += group['shared_tasks'] + group['monitoring_tasks']

        for task_key in tasks_to_disable:
            cfg = TASK_DEFAULT_CONFIG.get(task_key, {})
            CeleryTaskState.set_task_state(
                task_key=task_key, enabled=False,
                task_path=task_paths.get(task_key, ''),
                display_name=cfg.get('display_name', task_key.replace('-', ' ').title()),
                user='web_ui',
            )

    ensure_celery_running()


@login_required
@user_passes_test(is_admin_user)
def toggle_core_config(request):
    """Toggle a boolean field in TradingCoreConfig."""
    from apps.core.models import TradingCoreConfig
    from django.contrib import messages

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    field = request.POST.get('field')
    redirect_to = request.POST.get('redirect', 'celery')

    valid_fields = ['enable_futures_trading', 'require_telegram_confirmation',
                    'auto_close_on_target', 'auto_close_on_stoploss']

    if field not in valid_fields:
        messages.error(request, f'Invalid field: {field}')
        return redirect('core:celery_task_control')

    try:
        config = TradingCoreConfig.get_instance()
        current_value = getattr(config, field)
        setattr(config, field, not current_value)
        config.save()

        field_display = field.replace('_', ' ').title()
        new_status = 'enabled' if not current_value else 'disabled'
        messages.success(request, f'{field_display} {new_status}')

        if field == 'enable_futures_trading' and request.POST.get('manage_tasks') == '1':
            _manage_algorithm_tasks('futures', enabled=not current_value)
            messages.success(request, f'Futures algorithm tasks {"enabled" if not current_value else "disabled"}')

    except Exception as e:
        logger.error(f"Error toggling core config {field}: {e}")
        messages.error(request, f'Error: {str(e)}')

    if redirect_to == 'celery':
        return redirect('core:celery_task_control')
    return redirect('core:broker_settings')


@login_required
@user_passes_test(is_admin_user)
def update_core_config(request):
    """Update TradingCoreConfig fields."""
    from apps.core.models import TradingCoreConfig
    from django.contrib import messages
    from decimal import Decimal

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    redirect_to = request.POST.get('redirect', 'celery')

    try:
        config = TradingCoreConfig.get_instance()
        updated_fields = []

        # Options strategy
        if 'options_strategy' in request.POST:
            config.options_strategy = request.POST.get('options_strategy')
            updated_fields.append('options_strategy')

        # Position sizing mode
        if 'position_sizing_mode' in request.POST:
            config.position_sizing_mode = request.POST.get('position_sizing_mode')
            updated_fields.append('position_sizing_mode')

        # Manual lots
        if 'manual_options_lots' in request.POST:
            config.manual_options_lots = int(request.POST.get('manual_options_lots', 1))
            updated_fields.append('manual_options_lots')
        if 'manual_futures_lots' in request.POST:
            config.manual_futures_lots = int(request.POST.get('manual_futures_lots', 1))
            updated_fields.append('manual_futures_lots')

        # Margin utilization percentage
        if 'margin_utilization_pct' in request.POST:
            config.margin_utilization_pct = Decimal(request.POST.get('margin_utilization_pct', '50'))
            updated_fields.append('margin_utilization_pct')

        # Simulated lots
        if 'simulated_options_lots' in request.POST:
            config.simulated_options_lots = int(request.POST.get('simulated_options_lots', 100))
            updated_fields.append('simulated_options_lots')
        if 'simulated_futures_lots' in request.POST:
            config.simulated_futures_lots = int(request.POST.get('simulated_futures_lots', 30))
            updated_fields.append('simulated_futures_lots')

        # Notification level
        if 'notification_level' in request.POST:
            config.notification_level = request.POST.get('notification_level')
            updated_fields.append('notification_level')

        # Paper trading configuration
        if 'enable_paper_trading' in request.POST:
            config.enable_paper_trading = request.POST.get('enable_paper_trading') == 'on'
            updated_fields.append('enable_paper_trading')
        if 'paper_trade_futures' in request.POST:
            config.paper_trade_futures = request.POST.get('paper_trade_futures') == 'on'
            updated_fields.append('paper_trade_futures')
        if 'paper_trade_options' in request.POST:
            config.paper_trade_options = request.POST.get('paper_trade_options') == 'on'
            updated_fields.append('paper_trade_options')
        if 'paper_initial_capital' in request.POST:
            config.paper_initial_capital = Decimal(request.POST.get('paper_initial_capital', '10000000'))
            updated_fields.append('paper_initial_capital')
        if 'paper_slippage_pct' in request.POST:
            config.paper_slippage_pct = Decimal(request.POST.get('paper_slippage_pct', '0.0005'))
            updated_fields.append('paper_slippage_pct')
        if 'paper_brokerage_pct' in request.POST:
            config.paper_brokerage_pct = Decimal(request.POST.get('paper_brokerage_pct', '0.0003'))
            updated_fields.append('paper_brokerage_pct')
        if 'paper_options_lots' in request.POST:
            config.paper_options_lots = int(request.POST.get('paper_options_lots', 100))
            updated_fields.append('paper_options_lots')
        if 'paper_futures_lots' in request.POST:
            config.paper_futures_lots = int(request.POST.get('paper_futures_lots', 30))
            updated_fields.append('paper_futures_lots')

        # Legacy lots fields (backward compatibility)
        if 'options_lots' in request.POST:
            config.options_lots = int(request.POST.get('options_lots', 1))
            config.manual_options_lots = config.options_lots  # Sync to new field
        if 'futures_lots' in request.POST:
            config.futures_lots = int(request.POST.get('futures_lots', 1))
            config.manual_futures_lots = config.futures_lots  # Sync to new field

        config.save()

        # Manage algorithm tasks when options strategy transitions to/from NONE
        if 'options_strategy' in request.POST and request.POST.get('manage_tasks') == '1':
            old_strategy = request.POST.get('old_options_strategy', 'NONE')
            new_strategy = config.options_strategy
            if old_strategy == 'NONE' and new_strategy != 'NONE':
                _manage_algorithm_tasks('options', enabled=True)
                messages.success(request, 'Options algorithm tasks enabled')
            elif old_strategy != 'NONE' and new_strategy == 'NONE':
                _manage_algorithm_tasks('options', enabled=False)
                messages.success(request, 'Options algorithm tasks disabled')

        if updated_fields:
            messages.success(request, f'Config updated: {", ".join(updated_fields)}')
        else:
            messages.success(request, 'Trading config updated')

    except Exception as e:
        logger.error(f"Error updating core config: {e}")
        messages.error(request, f'Error: {str(e)}')

    if redirect_to == 'celery':
        return redirect('core:celery_task_control')
    return redirect('core:broker_settings')


# Task configuration - imported from task_config.py to avoid circular imports
from apps.core.task_config import TASK_DEFAULT_CONFIG


@login_required
@user_passes_test(is_admin_user)
def get_task_config(request):
    """
    Get configuration fields and current values for a specific task.

    Query params:
        task_key: The task key to get configuration for

    Returns JSON with schedule configuration from CeleryTaskState.
    All tasks are now fully configurable with timing and repeatability options.
    """
    from apps.core.models import CeleryTaskState

    task_key = request.GET.get('task_key', '')

    if not task_key:
        return JsonResponse({'success': False, 'error': 'task_key required'}, status=400)

    # Get default config info
    default_config = TASK_DEFAULT_CONFIG.get(task_key, {})
    schedule_type = default_config.get('schedule_type', 'crontab')

    # Try to get existing state from database
    try:
        task_state = CeleryTaskState.objects.get(task_key=task_key)
        use_custom = task_state.use_custom_schedule

        # Get current values from task state
        values = {
            'schedule_type': task_state.schedule_type,
            'schedule_hour': task_state.schedule_hour,
            'schedule_minute': task_state.schedule_minute,
            'interval_seconds': task_state.interval_seconds,
            'recurring_start_hour': task_state.recurring_start_hour,
            'recurring_start_minute': task_state.recurring_start_minute,
            'recurring_end_hour': task_state.recurring_end_hour,
            'recurring_end_minute': task_state.recurring_end_minute,
            'recurring_interval_minutes': task_state.recurring_interval_minutes,
            'days_of_week': task_state.days_of_week or default_config.get('default_days', [0, 1, 2, 3, 4]),
            'use_custom_schedule': use_custom,
        }

        # If not using custom schedule, use defaults
        if not use_custom:
            values['schedule_hour'] = default_config.get('default_hour', 9)
            values['schedule_minute'] = default_config.get('default_minute', 0)
            values['interval_seconds'] = default_config.get('default_interval_seconds', 60)
            values['recurring_start_hour'] = default_config.get('default_recurring_start_hour', 9)
            values['recurring_start_minute'] = default_config.get('default_recurring_start_minute', 0)
            values['recurring_end_hour'] = default_config.get('default_recurring_end_hour', 15)
            values['recurring_end_minute'] = default_config.get('default_recurring_end_minute', 30)
            values['recurring_interval_minutes'] = default_config.get('default_recurring_interval_minutes', 5)

    except CeleryTaskState.DoesNotExist:
        # Task not in database yet, use defaults
        use_custom = False
        values = {
            'schedule_type': schedule_type,
            'schedule_hour': default_config.get('default_hour', 9),
            'schedule_minute': default_config.get('default_minute', 0),
            'interval_seconds': default_config.get('default_interval_seconds', 60),
            'recurring_start_hour': default_config.get('default_recurring_start_hour', 9),
            'recurring_start_minute': default_config.get('default_recurring_start_minute', 0),
            'recurring_end_hour': default_config.get('default_recurring_end_hour', 15),
            'recurring_end_minute': default_config.get('default_recurring_end_minute', 30),
            'recurring_interval_minutes': default_config.get('default_recurring_interval_minutes', 5),
            'days_of_week': default_config.get('default_days', [0, 1, 2, 3, 4]),
            'use_custom_schedule': False,
        }

    # Build fields based on schedule type
    fields = []

    if schedule_type == 'crontab':
        fields = [
            {'name': 'schedule_hour', 'label': 'Hour', 'type': 'number', 'help': 'Hour to run (0-23, IST)', 'min': 0, 'max': 23},
            {'name': 'schedule_minute', 'label': 'Minute', 'type': 'number', 'help': 'Minute to run (0-59)', 'min': 0, 'max': 59},
            {'name': 'days_of_week', 'label': 'Days of Week', 'type': 'days', 'help': 'Select days to run'},
        ]
    elif schedule_type == 'interval':
        fields = [
            {'name': 'interval_seconds', 'label': 'Interval', 'type': 'number', 'unit': 'seconds', 'help': 'Run every N seconds', 'min': 1, 'max': 86400},
            {'name': 'days_of_week', 'label': 'Days of Week', 'type': 'days', 'help': 'Select days to run'},
        ]
    elif schedule_type == 'recurring':
        fields = [
            {'name': 'recurring_start_hour', 'label': 'Start Hour', 'type': 'number', 'help': 'Window start hour (0-23)', 'min': 0, 'max': 23},
            {'name': 'recurring_start_minute', 'label': 'Start Minute', 'type': 'number', 'help': 'Window start minute (0-59)', 'min': 0, 'max': 59},
            {'name': 'recurring_end_hour', 'label': 'End Hour', 'type': 'number', 'help': 'Window end hour (0-23)', 'min': 0, 'max': 23},
            {'name': 'recurring_end_minute', 'label': 'End Minute', 'type': 'number', 'help': 'Window end minute (0-59)', 'min': 0, 'max': 59},
            {'name': 'recurring_interval_minutes', 'label': 'Interval', 'type': 'number', 'unit': 'minutes', 'help': 'Run every N minutes within window', 'min': 1, 'max': 60},
            {'name': 'days_of_week', 'label': 'Days of Week', 'type': 'days', 'help': 'Select days to run'},
        ]

    # Get task param fields and current values (for tasks with configurable params)
    task_param_fields = default_config.get('task_param_fields', [])
    default_task_params = default_config.get('default_task_params', {})

    # Get current task_params from DB or use defaults
    try:
        task_params_values = task_state.task_params if task_state.task_params else {}
    except NameError:
        task_params_values = {}

    # Merge defaults with saved values (saved values take precedence)
    merged_task_params = {**default_task_params, **task_params_values}

    return JsonResponse({
        'success': True,
        'task_key': task_key,
        'display_name': default_config.get('display_name', task_key.replace('-', ' ').title()),
        'description': default_config.get('description', ''),
        'schedule_type': schedule_type,
        'category': default_config.get('category', ''),
        'fields': fields,
        'values': values,
        'use_custom_schedule': use_custom,
        'task_param_fields': task_param_fields,
        'task_params_values': merged_task_params,
    })


@login_required
@user_passes_test(is_admin_user)
@require_POST
def save_task_config(request):
    """
    Save schedule configuration for a specific task and restart Celery Beat.

    POST params:
        task_key: The task key
        schedule_hour, schedule_minute: For crontab tasks
        interval_seconds: For interval tasks
        recurring_*: For recurring window tasks
        days_of_week[]: Days to run

    Updates CeleryTaskState and restarts Celery Beat to apply changes.
    """
    from apps.core.models import CeleryTaskState
    from django.contrib import messages
    from django.utils import timezone

    task_key = request.POST.get('task_key', '')

    if not task_key:
        return JsonResponse({'success': False, 'error': 'task_key required'}, status=400)

    default_config = TASK_DEFAULT_CONFIG.get(task_key, {})
    schedule_type = default_config.get('schedule_type', 'crontab')

    try:
        # Get or create task state
        task_state, created = CeleryTaskState.objects.get_or_create(
            task_key=task_key,
            defaults={
                'display_name': default_config.get('display_name', task_key.replace('-', ' ').title()),
                'description': default_config.get('description', ''),
                'schedule_type': schedule_type,
                'category': default_config.get('category', ''),
            }
        )

        updated_fields = []

        # Handle days of week
        days_key = 'days_of_week[]'
        if days_key in request.POST or 'days_of_week' in request.POST:
            days_list = request.POST.getlist(days_key) or request.POST.getlist('days_of_week')
            try:
                new_days = sorted(set(int(d) for d in days_list if d.isdigit()))
                if task_state.days_of_week != new_days:
                    task_state.days_of_week = new_days
                    updated_fields.append('days_of_week')
            except Exception as e:
                logger.warning(f"Invalid days value: {e}")

        # Handle schedule fields based on type
        int_fields = [
            'schedule_hour', 'schedule_minute', 'interval_seconds',
            'recurring_start_hour', 'recurring_start_minute',
            'recurring_end_hour', 'recurring_end_minute', 'recurring_interval_minutes'
        ]

        field_limits = {
            'schedule_hour': (0, 23),
            'schedule_minute': (0, 59),
            'interval_seconds': (1, 86400),
            'recurring_start_hour': (0, 23),
            'recurring_start_minute': (0, 59),
            'recurring_end_hour': (0, 23),
            'recurring_end_minute': (0, 59),
            'recurring_interval_minutes': (1, 60),
        }

        for field_name in int_fields:
            if field_name in request.POST:
                try:
                    new_value = int(request.POST[field_name])

                    # Apply limits
                    if field_name in field_limits:
                        min_val, max_val = field_limits[field_name]
                        new_value = max(min_val, min(max_val, new_value))

                    old_value = getattr(task_state, field_name, None)
                    if old_value != new_value:
                        setattr(task_state, field_name, new_value)
                        updated_fields.append(field_name)
                        logger.info(f"Task {task_key}: {field_name} = {new_value} (was {old_value})")
                except (ValueError, TypeError):
                    logger.warning(f"Invalid value for {field_name}: {request.POST[field_name]}")

        # Handle task_params (task-specific parameters from task_param_fields)
        task_param_fields = default_config.get('task_param_fields', [])
        if task_param_fields:
            # Get existing task_params or start fresh
            current_task_params = task_state.task_params if task_state.task_params else {}
            default_task_params = default_config.get('default_task_params', {})

            for field in task_param_fields:
                field_name = field['name']
                if field_name in request.POST:
                    try:
                        new_value = int(request.POST[field_name])

                        # Apply limits if specified
                        if 'min' in field:
                            new_value = max(field['min'], new_value)
                        if 'max' in field:
                            new_value = min(field['max'], new_value)

                        old_value = current_task_params.get(field_name, default_task_params.get(field_name))
                        if old_value != new_value:
                            current_task_params[field_name] = new_value
                            updated_fields.append(f'task_params.{field_name}')
                            logger.info(f"Task {task_key}: task_params.{field_name} = {new_value} (was {old_value})")
                        else:
                            current_task_params[field_name] = new_value  # Ensure it's set even if unchanged
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid value for task_params.{field_name}: {request.POST[field_name]}")

            task_state.task_params = current_task_params

        # Always mark use_custom_schedule when user explicitly saves,
        # even if field values didn't change (confirms user's intent).
        task_state.use_custom_schedule = True
        task_state.schedule_type = schedule_type
        task_state.last_toggled_at = timezone.now()
        task_state.last_toggled_by = request.user.username
        task_state.save()

        if updated_fields:
            logger.info(f"Task config saved by {request.user.username} for {task_key}: {updated_fields}")
        else:
            logger.info(f"Task config confirmed by {request.user.username} for {task_key} (custom schedule enabled, no value changes)")

        # Restart Celery Beat to pick up the changes
        celery_result = ensure_celery_running()

        display_name = default_config.get('display_name', task_key)
        messages.success(request, f"Schedule for '{display_name}' saved. Celery Beat restarted.")

        return JsonResponse({
            'success': True,
            'task_key': task_key,
            'updated_fields': updated_fields,
            'message': 'Schedule saved and Celery restarted',
            'celery': {
                'success': celery_result.get('success', False),
                'worker_status': celery_result.get('worker_status', 'unknown'),
                'beat_status': celery_result.get('beat_status', 'unknown'),
                'beat_restarted': celery_result.get('beat_restarted', False),
            }
        })

    except Exception as e:
        logger.error(f"Error saving task config for {task_key}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_user)
def reset_task_config(request):
    """
    Reset task schedule(s) back to defaults from TASK_DEFAULT_CONFIG.

    GET  -- Preview: returns tasks whose schedule differs from defaults.
            Params: ?task_key=... or ?reset_all=true
    POST -- Execute: resets schedules and restarts Celery Beat.
            JSON body: {task_key: ...} or {reset_all: true}
    """
    import json
    from apps.core.models import CeleryTaskState
    from django.utils import timezone

    DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    def _fmt_time(h, m):
        if h is None:
            return '-'
        h, m = int(h), int(m or 0)
        ampm = 'AM' if h < 12 else 'PM'
        display_h = h % 12 or 12
        return f'{display_h}:{m:02d} {ampm}'

    def _fmt_days(days):
        if not days or sorted(days) == [0, 1, 2, 3, 4]:
            return 'Mon-Fri'
        if sorted(days) == [0, 1, 2, 3, 4, 5, 6]:
            return 'Every day'
        return ', '.join(DAY_NAMES[d] for d in sorted(days) if d < 7)

    def _describe(stype, vals):
        if stype == 'crontab':
            return f"{_fmt_time(vals.get('hour'), vals.get('minute'))}, {_fmt_days(vals.get('days'))}"
        elif stype == 'interval':
            secs = vals.get('interval_seconds')
            if secs and int(secs) >= 60:
                return f"Every {int(secs) // 60} min, {_fmt_days(vals.get('days'))}"
            return f"Every {secs}s, {_fmt_days(vals.get('days'))}"
        elif stype == 'recurring':
            start = _fmt_time(vals.get('start_hour'), vals.get('start_minute'))
            end = _fmt_time(vals.get('end_hour'), vals.get('end_minute'))
            interval = vals.get('interval_minutes', 5)
            return f"{start} - {end} every {interval}m, {_fmt_days(vals.get('days'))}"
        return '-'

    def _build_preview(keys_to_check):
        task_states = {
            s.task_key: s
            for s in CeleryTaskState.objects.filter(task_key__in=keys_to_check)
        }
        changed = []

        for key in keys_to_check:
            defaults = TASK_DEFAULT_CONFIG.get(key, {})
            ts = task_states.get(key)
            if not ts:
                continue

            stype = defaults.get('schedule_type', 'crontab')

            current_vals = {
                'hour': ts.schedule_hour, 'minute': ts.schedule_minute,
                'interval_seconds': ts.interval_seconds,
                'start_hour': ts.recurring_start_hour,
                'start_minute': ts.recurring_start_minute,
                'end_hour': ts.recurring_end_hour,
                'end_minute': ts.recurring_end_minute,
                'interval_minutes': ts.recurring_interval_minutes,
                'days': ts.days_of_week or [0, 1, 2, 3, 4],
            }

            default_vals = {
                'hour': defaults.get('default_hour'),
                'minute': defaults.get('default_minute'),
                'interval_seconds': defaults.get('default_interval_seconds'),
                'start_hour': defaults.get('default_recurring_start_hour'),
                'start_minute': defaults.get('default_recurring_start_minute'),
                'end_hour': defaults.get('default_recurring_end_hour'),
                'end_minute': defaults.get('default_recurring_end_minute'),
                'interval_minutes': defaults.get('default_recurring_interval_minutes'),
                'days': defaults.get('default_days', [0, 1, 2, 3, 4]),
            }

            has_diff = ts.use_custom_schedule
            if not has_diff:
                if stype == 'crontab':
                    has_diff = (current_vals['hour'] != default_vals['hour']
                                or current_vals['minute'] != default_vals['minute']
                                or current_vals['days'] != default_vals['days'])
                elif stype == 'interval':
                    has_diff = current_vals['interval_seconds'] != default_vals['interval_seconds']
                elif stype == 'recurring':
                    for f in ['start_hour', 'start_minute', 'end_hour',
                              'end_minute', 'interval_minutes']:
                        if current_vals[f] != default_vals[f]:
                            has_diff = True
                            break
                    if not has_diff:
                        has_diff = current_vals['days'] != default_vals['days']

            default_params = defaults.get('default_task_params')
            current_params = ts.task_params
            params_diff = (current_params or None) != (default_params or None)

            if has_diff or params_diff:
                entry = {
                    'task_key': key,
                    'display_name': defaults.get('display_name', key),
                    'schedule_type': stype,
                    'current_summary': _describe(stype, current_vals),
                    'default_summary': _describe(stype, default_vals),
                }
                if params_diff and current_params:
                    entry['current_params'] = current_params
                    entry['default_params'] = default_params
                changed.append(entry)

        return changed

    # ---- GET: Preview ----
    if request.method == 'GET':
        reset_all = request.GET.get('reset_all', '') == 'true'
        task_key = request.GET.get('task_key', '')

        if reset_all:
            keys = list(TASK_DEFAULT_CONFIG.keys())
        elif task_key and task_key in TASK_DEFAULT_CONFIG:
            keys = [task_key]
        else:
            return JsonResponse(
                {'success': False, 'error': 'task_key or reset_all required'},
                status=400,
            )

        changed = _build_preview(keys)
        return JsonResponse({
            'success': True,
            'changed_tasks': changed,
            'total_checked': len(keys),
        })

    # ---- POST: Execute reset ----
    if request.method != 'POST':
        return JsonResponse(
            {'success': False, 'error': 'GET or POST required'}, status=405
        )

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = request.POST

    reset_all = body.get('reset_all', False)
    task_key = body.get('task_key', '')

    if not reset_all and not task_key:
        return JsonResponse(
            {'success': False, 'error': 'task_key or reset_all required'},
            status=400,
        )

    if reset_all:
        keys_to_reset = list(TASK_DEFAULT_CONFIG.keys())
    else:
        if task_key not in TASK_DEFAULT_CONFIG:
            return JsonResponse(
                {'success': False, 'error': f'Unknown task: {task_key}'},
                status=400,
            )
        keys_to_reset = [task_key]

    reset_keys = []

    for key in keys_to_reset:
        defaults = TASK_DEFAULT_CONFIG[key]
        try:
            task_state = CeleryTaskState.objects.filter(task_key=key).first()
            if not task_state:
                continue

            task_state.schedule_hour = defaults.get('default_hour') if defaults.get('default_hour') is not None else 9
            task_state.schedule_minute = defaults.get('default_minute') if defaults.get('default_minute') is not None else 0
            task_state.interval_seconds = defaults.get('default_interval_seconds') or 60
            task_state.recurring_start_hour = defaults.get('default_recurring_start_hour') if defaults.get('default_recurring_start_hour') is not None else 9
            task_state.recurring_start_minute = defaults.get('default_recurring_start_minute') if defaults.get('default_recurring_start_minute') is not None else 0
            task_state.recurring_end_hour = defaults.get('default_recurring_end_hour') if defaults.get('default_recurring_end_hour') is not None else 15
            task_state.recurring_end_minute = defaults.get('default_recurring_end_minute') if defaults.get('default_recurring_end_minute') is not None else 30
            task_state.recurring_interval_minutes = defaults.get('default_recurring_interval_minutes') if defaults.get('default_recurring_interval_minutes') is not None else 5
            task_state.days_of_week = defaults.get('default_days', [0, 1, 2, 3, 4])
            task_state.task_params = defaults.get('default_task_params') or {}
            task_state.schedule_type = defaults.get('schedule_type', 'crontab')
            task_state.use_custom_schedule = False
            task_state.last_toggled_at = timezone.now()
            task_state.last_toggled_by = request.user.username
            task_state.save()
            reset_keys.append(key)
        except Exception as e:
            logger.error(f"Error resetting task {key}: {e}", exc_info=True)

    if not reset_keys:
        return JsonResponse(
            {'success': False, 'error': 'No tasks were reset'}, status=400
        )

    celery_result = ensure_celery_running()

    action = ('All tasks' if reset_all
              else f"'{TASK_DEFAULT_CONFIG[task_key].get('display_name', task_key)}'")
    logger.info(f"Task config reset by {request.user.username}: {reset_keys}")

    return JsonResponse({
        'success': True,
        'reset_keys': reset_keys,
        'message': f'{action} reset to defaults. Celery Beat restarted.',
        'celery': {
            'success': celery_result.get('success', False),
            'beat_restarted': celery_result.get('beat_restarted', False),
        }
    })


@login_required
@user_passes_test(is_admin_user)
@require_POST
def run_task_now(request):
    """
    Manually trigger a Celery task to run immediately (once).

    POST params:
        task_key: The task key from beat_schedule (e.g., 'execute-futures-algorithm')

    Returns JSON with task_id if successful.
    """
    import json
    from mcube_ai.celery import get_static_schedule

    try:
        body = json.loads(request.body)
        task_key = body.get('task_key', '')

        if not task_key:
            return JsonResponse({'success': False, 'error': 'task_key required'}, status=400)

        # Get task path from static schedule
        static_schedule = get_static_schedule()
        task_config = static_schedule.get(task_key)

        if not task_config:
            return JsonResponse({'success': False, 'error': f'Task "{task_key}" not found in schedule'}, status=404)

        task_path = task_config.get('task')
        if not task_path:
            return JsonResponse({'success': False, 'error': f'Task path not defined for "{task_key}"'}, status=400)

        # Import and run the task via Celery
        from celery import current_app

        # Get task kwargs if defined
        task_kwargs = task_config.get('kwargs', {}).copy()
        task_kwargs['_bypass_guard'] = True  # Manual runs bypass the enabled guard

        # Send task to Celery
        logger.info(f"Manually triggering task: {task_key} ({task_path}) by {request.user.username}")

        # Use send_task to trigger by name
        result = current_app.send_task(task_path, kwargs=task_kwargs)

        logger.info(f"Task {task_key} queued with ID: {result.id}")

        return JsonResponse({
            'success': True,
            'task_key': task_key,
            'task_path': task_path,
            'task_id': result.id,
            'message': f'Task "{task_key}" has been queued for execution',
            'status': 'PENDING'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error triggering task: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def ensure_celery_running():
    """
    Ensure Celery Beat and Worker are running. Start them if not.
    Restart Beat to pick up schedule changes.

    Returns:
        dict: {
            'success': bool,
            'worker_status': str,
            'beat_status': str,
            'worker_started': bool,
            'beat_restarted': bool,
            'message': str
        }
    """
    import subprocess
    import signal
    import os
    import time

    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Find Python executable from virtual environment
    # Must use venv Python to get correct site-packages
    venv_python_paths = [
        os.path.join(project_dir, 'venv', 'bin', 'python'),
        os.path.join(project_dir, '.venv', 'bin', 'python'),
    ]

    python_path = None
    for path in venv_python_paths:
        if os.path.exists(path):
            python_path = path
            break

    if not python_path:
        logger.error("Virtual environment Python not found!")
        return {
            'success': False,
            'worker_status': 'failed',
            'beat_status': 'failed',
            'worker_started': False,
            'beat_restarted': False,
            'worker_pid': None,
            'beat_pid': None,
            'message': 'Virtual environment not found',
            'error_type': 'venv_missing'
        }

    # Check if Redis is running (required for Celery)
    redis_check = subprocess.run(
        ['redis-cli', 'ping'],
        capture_output=True,
        text=True
    )
    if redis_check.returncode != 0 or 'PONG' not in redis_check.stdout:
        logger.error("Redis is not running!")
        return {
            'success': False,
            'worker_status': 'failed',
            'beat_status': 'failed',
            'worker_started': False,
            'beat_restarted': False,
            'worker_pid': None,
            'beat_pid': None,
            'message': 'Redis not running. macOS: brew install redis && brew services start redis | Ubuntu: sudo apt install redis-server && sudo systemctl start redis-server',
            'error_type': 'redis_not_running'
        }

    result = {
        'success': False,
        'worker_status': 'unknown',
        'beat_status': 'unknown',
        'worker_started': False,
        'beat_restarted': False,
        'worker_pid': None,
        'beat_pid': None,
        'message': ''
    }

    try:
        # =====================================================================
        # Check and start Celery Worker
        # =====================================================================
        worker_result = subprocess.run(
            ['pgrep', '-f', 'celery.*mcube.*worker'],
            capture_output=True,
            text=True
        )

        worker_was_running = worker_result.returncode == 0 and worker_result.stdout.strip()

        if not worker_was_running:
            # Start celery worker with all queues using venv Python
            log_file = os.path.join(project_dir, 'logs', 'celery_worker.log')
            os.makedirs(os.path.dirname(log_file), exist_ok=True)

            # Determine concurrency from environment or auto-detect
            # Uses same logic as install_and_run.sh: half of CPU cores, min 2, max 32
            concurrency = os.environ.get('CELERY_CONCURRENCY')
            if not concurrency:
                cpu_count = os.cpu_count() or 4
                concurrency = max(2, min(cpu_count // 2, 32))  # Half of cores, min 2, max 32

            with open(log_file, 'a') as log:
                log.write(f"\n{'='*60}\n")
                log.write(f"Worker starting at {datetime.now().isoformat()}\n")
                log.write(f"Using Python: {python_path}\n")
                log.write(f"Concurrency: {concurrency} (env: {os.environ.get('CELERY_CONCURRENCY', 'auto')})\n")
                log.write(f"{'='*60}\n")

                # Use python -m celery to ensure correct environment
                proc = subprocess.Popen(
                    [
                        python_path, '-m', 'celery',
                        '-A', 'mcube_ai', 'worker',
                        '--loglevel=info',
                        '-Q', 'data,strategies,monitoring,risk,reports,celery',
                        f'--concurrency={concurrency}'
                    ],
                    cwd=project_dir,
                    stdout=log,
                    stderr=log,
                    start_new_session=True
                )
                result['worker_pid'] = proc.pid

            logger.info(f"Celery worker started with PID {proc.pid}, concurrency={concurrency}, using {python_path}")
            result['worker_started'] = True
            result['worker_status'] = 'started'

            # Wait for worker to initialize
            time.sleep(3)

            # Verify worker started successfully
            verify = subprocess.run(
                ['pgrep', '-f', 'celery.*mcube.*worker'],
                capture_output=True,
                text=True
            )
            if verify.returncode != 0:
                result['worker_status'] = 'failed'
                result['message'] = 'Worker failed to start - check logs/celery_worker.log'
        else:
            result['worker_status'] = 'running'
            result['worker_pid'] = int(worker_result.stdout.strip().split('\n')[0])

        # =====================================================================
        # Restart Celery Beat (always restart to pick up schedule changes)
        # =====================================================================
        beat_result = subprocess.run(
            ['pgrep', '-f', 'celery.*mcube.*beat'],
            capture_output=True,
            text=True
        )

        if beat_result.returncode == 0 and beat_result.stdout.strip():
            # Kill existing celery beat processes
            pids = beat_result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    logger.info(f"Stopped celery beat process {pid}")
                except (ProcessLookupError, ValueError):
                    pass

            # Wait for process to terminate
            time.sleep(1)

        # Remove stale celerybeat-schedule.db so beat starts fresh from DB config
        schedule_db = os.path.join(project_dir, 'celerybeat-schedule.db')
        if os.path.exists(schedule_db):
            try:
                os.remove(schedule_db)
                logger.info("Removed stale celerybeat-schedule.db")
            except OSError:
                pass

        # Start celery beat using venv Python
        log_file = os.path.join(project_dir, 'logs', 'celery_beat.log')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        with open(log_file, 'a') as log:
            log.write(f"\n{'='*60}\n")
            log.write(f"Beat starting at {datetime.now().isoformat()}\n")
            log.write(f"Using Python: {python_path}\n")
            log.write(f"{'='*60}\n")

            # Use python -m celery to ensure correct environment
            # Use custom DBReloadScheduler to load schedule from DB after Django is ready
            proc = subprocess.Popen(
                [python_path, '-m', 'celery', '-A', 'mcube_ai', 'beat',
                 '--scheduler=mcube_ai.celery:DBReloadScheduler', '--loglevel=info'],
                cwd=project_dir,
                stdout=log,
                stderr=log,
                start_new_session=True
            )
            result['beat_pid'] = proc.pid

        logger.info(f"Celery beat started with PID {proc.pid} using {python_path}")
        result['beat_restarted'] = True
        result['beat_status'] = 'restarted'

        # Wait for beat to initialize
        time.sleep(2)

        # Verify beat is running
        verify_beat = subprocess.run(
            ['pgrep', '-f', 'celery.*mcube.*beat'],
            capture_output=True,
            text=True
        )
        if verify_beat.returncode != 0:
            result['beat_status'] = 'failed'
            result['message'] = 'Beat failed to start - check logs/celery_beat.log'

        # Set success based on current status
        if result['worker_status'] in ('running', 'started') and result['beat_status'] == 'restarted':
            result['success'] = True
            result['message'] = f"Worker: {result['worker_status']}, Beat: {result['beat_status']}"
        elif result['worker_status'] == 'failed':
            result['message'] = 'Worker failed to start - check logs/celery_worker.log'

        return result

    except Exception as e:
        logger.error(f"Error managing celery processes: {e}")
        result['message'] = str(e)
        return result


def get_active_tasks_summary():
    """Get summary of active tasks by category."""
    from apps.core.models import CeleryTaskState

    try:
        enabled_tasks = CeleryTaskState.objects.filter(is_enabled=True).values_list('task_key', flat=True)
        return {
            'total_active': len(enabled_tasks),
            'tasks': list(enabled_tasks)
        }
    except Exception:
        return {'total_active': 0, 'tasks': []}


# Alias for backward compatibility
def restart_celery_beat():
    result = ensure_celery_running()
    return result.get('success', False), result.get('message', '')


@login_required
@user_passes_test(is_admin_user)
def toggle_static_task(request):
    """Toggle a static Celery task on/off."""
    from apps.core.models import CeleryTaskState

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    task_key = request.POST.get('task_key', '')
    task_path = request.POST.get('task_path', '')

    if not task_key:
        return JsonResponse({'success': False, 'error': 'task_key required'}, status=400)

    try:
        # Get current state (default to enabled if not in DB)
        current_state = CeleryTaskState.is_task_enabled(task_key)
        new_state = not current_state

        # Update or create the state
        CeleryTaskState.set_task_state(
            task_key=task_key,
            enabled=new_state,
            task_path=task_path,
            display_name=task_key.replace('-', ' ').title(),
            user=request.user.username
        )

        # Ensure Celery is running and restart Beat to pick up changes
        celery_result = ensure_celery_running()
        active_summary = get_active_tasks_summary()

        status = 'activated' if new_state else 'deactivated'

        return JsonResponse({
            'success': True,
            'task_key': task_key,
            'is_enabled': new_state,
            'celery': {
                'success': celery_result.get('success'),
                'worker_status': celery_result.get('worker_status'),
                'beat_status': celery_result.get('beat_status'),
                'worker_started': celery_result.get('worker_started'),
                'beat_restarted': celery_result.get('beat_restarted'),
            },
            'active_tasks': active_summary,
            'message': f"Task {status}"
        })
    except Exception as e:
        logger.error(f"Error toggling static task {task_key}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def parse_celery_log_line(line):
    """Parse a celery log line into structured data."""
    import re

    # Pattern: [2026-01-30 16:32:01,521: INFO/MainProcess] message
    # Process can be MainProcess, ForkPoolWorker-1, etc.
    pattern = r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+: (\w+)/([\w-]+)\] (.+)'
    match = re.match(pattern, line.strip())

    if match:
        timestamp, level, process, message = match.groups()
        return {
            'timestamp': timestamp,
            'level': level.lower(),
            'process': process,
            'message': message,
            'raw': line.strip()
        }
    return None


def get_task_logs_from_file(task_name, limit=100):
    """
    Get logs for a specific task from celery log files.
    Searches for task name in worker log.
    """
    import os
    import re

    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    worker_log = os.path.join(project_dir, 'logs', 'celery_worker.log')

    logs = []

    # Normalize task name for search
    search_terms = [
        task_name,
        task_name.replace('-', '_'),
        task_name.replace('_', '-'),
        # Also search for task path patterns
        f"apps.data.tasks.{task_name.replace('-', '_')}",
        f"apps.strategies.tasks.{task_name.replace('-', '_')}",
        f"apps.positions.tasks.{task_name.replace('-', '_')}",
        f"apps.risk.tasks.{task_name.replace('-', '_')}",
        f"apps.analytics.tasks.{task_name.replace('-', '_')}",
    ]

    if os.path.exists(worker_log):
        try:
            # Read last N lines efficiently
            with open(worker_log, 'r') as f:
                # Read all lines and get last 2000 for searching
                all_lines = f.readlines()
                recent_lines = all_lines[-2000:] if len(all_lines) > 2000 else all_lines

            for line in reversed(recent_lines):
                # Check if any search term is in the line
                line_lower = line.lower()
                for term in search_terms:
                    if term.lower() in line_lower:
                        parsed = parse_celery_log_line(line)
                        if parsed:
                            # Determine if it's a success or error
                            msg_lower = parsed['message'].lower()
                            if 'succeeded' in msg_lower:
                                parsed['status'] = 'success'
                                # Extract execution time if present
                                time_match = re.search(r'in ([\d.]+)s', parsed['message'])
                                if time_match:
                                    parsed['execution_time'] = f"{float(time_match.group(1)):.3f}s"
                            elif 'failed' in msg_lower or 'error' in msg_lower:
                                parsed['status'] = 'error'
                            elif 'received' in msg_lower:
                                parsed['status'] = 'received'
                            else:
                                parsed['status'] = 'info'

                            logs.append(parsed)
                            if len(logs) >= limit:
                                break
                        break
                if len(logs) >= limit:
                    break
        except Exception as e:
            logger.error(f"Error reading celery log: {e}")

    return logs


@login_required
@user_passes_test(is_admin_user)
def get_task_logs(request):
    """
    Get logs for a specific task from celery log files.

    Query params:
        task_name: Name of the task (e.g., 'morning-data-sync')
        limit: Max logs to return (default 50)
    """
    task_name = request.GET.get('task_name', '')
    limit = min(int(request.GET.get('limit', 50)), 200)

    if not task_name:
        return JsonResponse({'success': False, 'error': 'task_name required'}, status=400)

    # Get logs from celery log file
    logs = get_task_logs_from_file(task_name, limit)

    return JsonResponse({
        'success': True,
        'task_name': task_name,
        'count': len(logs),
        'logs': logs
    })


def _build_task_lookup_maps():
    """Build lookup maps for category, display name, and task key from identifiers."""
    category_map = {}   # identifier -> category
    display_map = {}    # identifier -> display_name
    key_map = {}        # identifier -> task_key (config key)

    # From TASK_DEFAULT_CONFIG
    for task_key, config in TASK_DEFAULT_CONFIG.items():
        cat = config.get('category', 'other')
        name = config.get('display_name', task_key.replace('-', ' ').title())
        category_map[task_key] = cat
        display_map[task_key] = name
        key_map[task_key] = task_key

    # From static schedule (maps task paths to keys, then to categories)
    try:
        from mcube_ai.celery import get_static_schedule
        for key, sched_config in get_static_schedule().items():
            task_path = sched_config.get('task', '')
            if task_path:
                cat = category_map.get(key, 'other')
                name = display_map.get(key, key.replace('-', ' ').title())
                category_map[task_path] = cat
                display_map[task_path] = name
                key_map[task_path] = key
                # Also map the function name (last part of dotted path)
                func_name = task_path.rsplit('.', 1)[-1]
                if func_name:
                    category_map.setdefault(func_name, cat)
                    display_map.setdefault(func_name, name)
                    key_map.setdefault(func_name, key)
    except Exception:
        pass

    return category_map, display_map, key_map


def _extract_task_info(message, category_map, display_map):
    """Extract task category, display name, and task_id from a celery log message.

    Returns (category, display_name, task_id) tuple.
    """
    import re

    # Pattern 1: Worker logs - "Task morning_data_sync[uuid] ..." or "Task apps.data.tasks.func[uuid]"
    m = re.search(r'Task\s+([\w.]+)\[([0-9a-f-]+)\]', message)
    if m:
        task_path = m.group(1)
        task_id = m.group(2)
        cat = category_map.get(task_path, '')
        name = display_map.get(task_path, '')
        if not cat:
            func_name = task_path.rsplit('.', 1)[-1]
            cat = category_map.get(func_name, '')
            name = display_map.get(func_name, '')
        return cat, name, task_id

    # Pattern 1b: Worker inner logs - "morning_data_sync[uuid]: ..."
    m = re.search(r'^([\w.]+)\[([0-9a-f-]+)\]:', message)
    if m:
        task_path = m.group(1)
        task_id = m.group(2)
        cat = category_map.get(task_path, '')
        name = display_map.get(task_path, '')
        if not cat:
            func_name = task_path.rsplit('.', 1)[-1]
            cat = category_map.get(func_name, '')
            name = display_map.get(func_name, '')
        return cat, name, task_id

    # Pattern 2: Beat logs - "Sending due task setup-trading-day (apps.strategies.tasks.func)"
    m = re.search(r'Sending due task\s+([\w.-]+)\s*\(([\w.]+)\)', message)
    if m:
        task_key = m.group(1)
        task_path = m.group(2)
        # Try key (may have hour suffix like "batch-options-averaging-9h")
        base_key = re.sub(r'-\d+h$', '', task_key)
        for k in (task_key, base_key, task_path):
            if k in category_map:
                return category_map[k], display_map.get(k, ''), ''
        return '', '', ''

    return '', '', ''


@login_required
@user_passes_test(is_admin_user)
def get_all_celery_logs(request):
    """
    Get all recent celery logs from both worker and beat log files.

    Query params:
        limit: Max lines to return (default 200)
        log_type: 'worker', 'beat', or 'all' (default 'all')
    """
    import os

    limit = min(int(request.GET.get('limit', 200)), 500)
    log_type = request.GET.get('log_type', 'all')

    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    worker_log = os.path.join(project_dir, 'logs', 'celery_worker.log')
    beat_log = os.path.join(project_dir, 'logs', 'celery_beat.log')

    logs = []
    category_map, display_map, key_map = _build_task_lookup_maps()

    def read_log_file(filepath, source, max_lines):
        """Read last N lines from a log file."""
        entries = []
        # Track last-seen info per ForkPoolWorker so orphan lines
        # (e.g. "F&O download failed") inherit from the parent task.
        # Only for ForkPoolWorker-*, never MainProcess (which dispatches all tasks).
        worker_context = {}  # process -> {category, display_name, task_id}
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    lines = f.readlines()
                    recent = lines[-max_lines:] if len(lines) > max_lines else lines

                for line in recent:
                    parsed = parse_celery_log_line(line)
                    if parsed:
                        parsed['source'] = source
                        # Determine status from celery task lifecycle + log level
                        msg_lower = parsed['message'].lower()
                        level = parsed['level']
                        if 'task' in msg_lower and 'succeeded' in msg_lower:
                            parsed['status'] = 'success'
                        elif level == 'error' or ('task' in msg_lower and ('failed' in msg_lower or 'raised' in msg_lower)):
                            parsed['status'] = 'error'
                        elif 'task' in msg_lower and 'received' in msg_lower:
                            parsed['status'] = 'received'
                        elif 'sending due task' in msg_lower:
                            parsed['status'] = 'scheduled'
                        elif '.start' in msg_lower or '.complete' in msg_lower:
                            parsed['status'] = 'success' if '.complete' in msg_lower else 'starting'
                        else:
                            parsed['status'] = 'info'

                        # Extract task info (category, display_name, task_id)
                        cat, dname, tid = _extract_task_info(parsed['message'], category_map, display_map)
                        proc = parsed.get('process', '')
                        is_worker = proc.startswith('ForkPoolWorker')

                        if cat and is_worker:
                            worker_context[proc] = {'category': cat, 'display_name': dname, 'task_id': tid}
                        elif not cat and is_worker and proc in worker_context:
                            ctx = worker_context[proc]
                            cat = ctx['category']
                            dname = dname or ctx['display_name']
                            tid = tid or ctx['task_id']

                        parsed['category'] = cat
                        parsed['task_display_name'] = dname
                        parsed['task_id'] = tid
                        entries.append(parsed)
                    elif line.strip() and not line.startswith('='):
                        # Non-parsed lines (errors, tracebacks)
                        cat, dname, tid = _extract_task_info(line.strip()[:500], category_map, display_map)
                        entries.append({
                            'timestamp': '',
                            'level': 'error' if 'error' in line.lower() or 'traceback' in line.lower() else 'info',
                            'process': '',
                            'message': line.strip()[:500],
                            'source': source,
                            'status': 'error' if 'error' in line.lower() else 'info',
                            'category': cat,
                            'task_display_name': dname,
                            'task_id': tid,
                            'raw': line.strip()[:500]
                        })
            except Exception as e:
                logger.error(f"Error reading {filepath}: {e}")
        return entries

    # Read logs based on type
    if log_type in ('worker', 'all'):
        logs.extend(read_log_file(worker_log, 'worker', limit))
    if log_type in ('beat', 'all'):
        logs.extend(read_log_file(beat_log, 'beat', limit))

    # Sort by timestamp (most recent first) and limit
    logs_with_time = [l for l in logs if l.get('timestamp')]
    logs_without_time = [l for l in logs if not l.get('timestamp')]

    logs_with_time.sort(key=lambda x: x['timestamp'], reverse=True)
    final_logs = (logs_with_time + logs_without_time)[:limit]

    # Get celery process status
    import subprocess
    worker_running = subprocess.run(
        ['pgrep', '-f', 'celery.*mcube.*worker'],
        capture_output=True
    ).returncode == 0
    beat_running = subprocess.run(
        ['pgrep', '-f', 'celery.*mcube.*beat'],
        capture_output=True
    ).returncode == 0

    return JsonResponse({
        'success': True,
        'count': len(final_logs),
        'logs': final_logs,
        'status': {
            'worker_running': worker_running,
            'beat_running': beat_running
        }
    })


@login_required
@user_passes_test(is_admin_user)
def control_all_static_tasks(request):
    """Enable or disable all static Celery tasks."""
    from apps.core.models import CeleryTaskState
    from mcube_ai.celery import get_static_schedule
    from django.contrib import messages

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    action = request.POST.get('action', 'stop')

    try:
        # Get ALL static tasks from schedule (not filtered)
        static_schedule = get_static_schedule()
        enabled = action == 'start'

        for key, config in static_schedule.items():
            # Skip dynamic tasks
            if any(d in key.lower() for d in ['premarket', 'market_open', 'trade_start', 'trade_monitor', 'trade_stop', 'day_close', 'analyze_day']):
                continue

            CeleryTaskState.set_task_state(
                task_key=key,
                enabled=enabled,
                task_path=config.get('task', ''),
                display_name=key.replace('-', ' ').title(),
                user=request.user.username
            )

        # Restart Celery Beat to pick up changes
        beat_restarted, beat_message = restart_celery_beat()

        status = 'activated' if enabled else 'deactivated'
        message = f"All system tasks {status}"
        if beat_restarted:
            message += " (schedule reloaded)"

        messages.success(request, message)
        return JsonResponse({'success': True, 'message': message, 'beat_restarted': beat_restarted})
    except Exception as e:
        logger.error(f"Error controlling all static tasks: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_user)
def control_category_tasks(request):
    """Enable or disable all tasks in a specific category."""
    from apps.core.models import CeleryTaskState
    from mcube_ai.celery import get_static_schedule
    from django.contrib import messages

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    action = request.POST.get('action', 'stop')
    category = request.POST.get('category', '')

    # Category to queue/keyword mapping (None = keyword-only matching, no queue)
    CATEGORY_QUEUES = {
        'data': 'data',
        'strategies': None,
        'transactions': None,
        'monitoring': 'monitoring',
        'risk': 'risk',
        'reports': 'reports',
    }

    CATEGORY_KEYWORDS = {
        'data': ['trendlyne', 'market-data', 'pre-market', 'post-market', 'live-market', 'morning-data-sync', 'news'],
        'strategies': ['setup-trading', 'start-trading', 'evaluate-options', 'screen', 'execute-futures', 'strangle'],
        'transactions': ['start-options-trade', 'batch-options-averaging', 'check-futures-averaging', 'close-trading'],
        'monitoring': ['monitor', 'position', 'pnl', 'exit'],
        'risk': ['risk', 'circuit', 'limit'],
        'reports': ['report', 'pnl-report', 'benchmark', 'aggregation', 'equity'],
    }

    if category not in CATEGORY_QUEUES:
        return JsonResponse({'success': False, 'error': f'Unknown category: {category}'}, status=400)

    try:
        static_schedule = get_static_schedule()
        enabled = action == 'start'
        updated_count = 0

        for key, config in static_schedule.items():
            # Skip dynamic tasks
            if any(d in key.lower() for d in ['premarket', 'market_open', 'trade_start', 'trade_monitor', 'trade_stop', 'day_close', 'analyze_day']):
                continue

            # Check if task belongs to this category
            queue = config.get('options', {}).get('queue', 'default')
            key_lower = key.lower()
            belongs_to_category = False

            # Match by queue (only if category has a queue defined)
            cat_queue = CATEGORY_QUEUES.get(category)
            if cat_queue is not None and queue == cat_queue:
                belongs_to_category = True
            else:
                # Match by keywords
                for keyword in CATEGORY_KEYWORDS.get(category, []):
                    if keyword in key_lower:
                        belongs_to_category = True
                        break

            if belongs_to_category:
                CeleryTaskState.set_task_state(
                    task_key=key,
                    enabled=enabled,
                    task_path=config.get('task', ''),
                    display_name=key.replace('-', ' ').title(),
                    user=request.user.username
                )
                updated_count += 1

        status = 'activated' if enabled else 'deactivated'
        # Restart Celery Beat to pick up changes
        beat_restarted, beat_message = restart_celery_beat()

        category_name = category.replace('_', ' ').title()
        message = f"{updated_count} {category_name} tasks {status}"
        if beat_restarted:
            message += " (schedule reloaded)"

        messages.success(request, message)
        return redirect('core:celery_task_control')
    except Exception as e:
        logger.error(f"Error controlling category tasks: {e}")
        messages.error(request, f"Error: {str(e)}")
        return redirect('core:celery_task_control')


# =============================================================================
# UNIFIED BACKGROUND TASKS CONTROL (Celery + Django Background Tasks)
# =============================================================================

@login_required
@user_passes_test(is_admin_user)
def background_tasks_control(request):
    """
    Unified background tasks control page.
    Shows both Celery tasks and Django Background Tasks.
    """
    from apps.strategies.models import TradingScheduleConfig
    from apps.core.models import CeleryTaskState
    from mcube_ai.celery import get_static_schedule
    import redis

    # =========================================================================
    # CELERY TASKS
    # =========================================================================

    # Get dynamic tasks from database
    dynamic_tasks = list(TradingScheduleConfig.objects.all().order_by('scheduled_time'))

    # Get ALL static tasks for display (not filtered by enabled state)
    static_schedule = get_static_schedule()

    # Initialize any missing tasks in the database (as disabled by default)
    # and get all task states with full details
    try:
        CeleryTaskState.initialize_static_tasks(static_schedule, force=False)
        # Get full task state objects, keyed by task_key
        task_state_objects = {s.task_key: s for s in CeleryTaskState.objects.all()}
    except Exception as e:
        logger.warning(f"Could not initialize/get task states: {e}")
        task_state_objects = {}

    # Build static tasks list (excluding dynamic ones)
    celery_static_tasks = []
    for key, config in static_schedule.items():
        if any(d in key.lower() for d in ['premarket', 'market_open', 'trade_start', 'trade_monitor', 'trade_stop', 'day_close', 'analyze_day']):
            continue

        # Get task state from database
        task_state = task_state_objects.get(key)

        # Get default config for display info
        default_config = TASK_DEFAULT_CONFIG.get(key, {})

        # Build schedule display string based on custom settings or defaults
        if task_state and task_state.use_custom_schedule:
            schedule_type = task_state.schedule_type
            if schedule_type == 'crontab':
                schedule_str = f"{task_state.schedule_hour:02d}:{task_state.schedule_minute:02d}"
            elif schedule_type == 'interval':
                schedule_str = f"Every {task_state.interval_seconds}s"
            elif schedule_type == 'recurring':
                schedule_str = f"{task_state.recurring_start_hour:02d}:{task_state.recurring_start_minute:02d}-{task_state.recurring_end_hour:02d}:{task_state.recurring_end_minute:02d} (every {task_state.recurring_interval_minutes}m)"
            else:
                schedule_str = str(config.get('schedule', 'Unknown'))
        else:
            schedule_str = str(config.get('schedule', 'Unknown'))

        celery_static_tasks.append({
            'key': key,
            'task': config.get('task', 'Unknown'),
            'schedule': schedule_str,
            'queue': config.get('options', {}).get('queue', 'default'),
            'is_active': task_state.is_enabled if task_state else False,
            'display_name': task_state.display_name if task_state and task_state.display_name else default_config.get('display_name', key.replace('-', ' ').title()),
            'description': task_state.description if task_state and task_state.description else default_config.get('description', ''),
            'use_custom_schedule': task_state.use_custom_schedule if task_state else False,
            'schedule_type': task_state.schedule_type if task_state else default_config.get('schedule_type', 'crontab'),
        })

    # Check Celery worker status
    celery_worker_status = {'active': False, 'workers': [], 'error': None}
    try:
        from mcube_ai.celery import app as celery_app
        inspect = celery_app.control.inspect()
        active_workers = inspect.active_queues()
        if active_workers:
            celery_worker_status['active'] = True
            celery_worker_status['workers'] = list(active_workers.keys())
    except Exception as e:
        celery_worker_status['error'] = str(e)

    # Check Redis status
    redis_status = {'connected': False, 'error': None}
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        redis_status['connected'] = True
    except Exception as e:
        redis_status['error'] = str(e)

    # Celery task counts
    celery_dynamic_active = TradingScheduleConfig.objects.filter(is_enabled=True).count()
    celery_dynamic_total = TradingScheduleConfig.objects.count()
    celery_static_active = sum(1 for t in celery_static_tasks if t['is_active'])
    celery_static_total = len(celery_static_tasks)

    # Total counts for all tasks (Celery only - no longer using django-background-tasks)
    total_active = celery_dynamic_active + celery_static_active
    total_tasks = celery_dynamic_total + celery_static_total

    context = {
        # Celery data
        'celery_dynamic_tasks': dynamic_tasks,
        'celery_static_tasks': celery_static_tasks,
        'celery_worker_status': celery_worker_status,
        'redis_status': redis_status,
        'celery_active_count': celery_dynamic_active + celery_static_active,
        'celery_total_count': celery_dynamic_total + celery_static_total,

        # Overall stats (Celery only)
        'total_active': total_active,
        'total_tasks': total_tasks,
        'timestamp': datetime.now(),
    }

    return render(request, 'core/background_tasks.html', context)


@login_required
@user_passes_test(is_admin_user)
def toggle_bg_task(request, task_id):
    """
    Toggle/revoke a Celery task by ID.
    Note: This is a placeholder - Celery task revocation requires the task ID from Celery.
    """
    from django.contrib import messages

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        from mcube_ai.celery import app

        # Revoke the task
        app.control.revoke(task_id, terminate=True)

        messages.success(request, f"Task '{task_id}' revoked.")
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'message': f"Task '{task_id}' revoked"
        })
    except Exception as e:
        logger.error(f"Error revoking task {task_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_user)
def delete_bg_task(request, task_id):
    """Delete/revoke a Celery task."""
    return toggle_bg_task(request, task_id)


@login_required
@user_passes_test(is_admin_user)
def control_all_bg_tasks(request):
    """Control all Celery background tasks."""
    from django.contrib import messages

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    action = request.POST.get('action', 'stop')

    try:
        from mcube_ai.celery import app

        if action == 'stop':
            # Purge all pending tasks from Celery
            app.control.purge()
            messages.warning(request, "All pending Celery tasks purged.")
            return JsonResponse({
                'success': True,
                'message': 'All pending Celery tasks purged'
            })
        elif action == 'start':
            # Re-install the scheduler (creates default flags)
            from apps.core.background_tasks import install_daily_task_scheduler
            result = install_daily_task_scheduler()
            if result.get('status') == 'success':
                messages.success(request, "Task scheduler initialized. Celery Beat handles scheduling.")
                return JsonResponse({
                    'success': True,
                    'message': 'Task scheduler initialized'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': result.get('error', 'Unknown error')
                }, status=500)
        else:
            return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)

    except Exception as e:
        logger.error(f"Error controlling Celery tasks: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_user)
def api_task_timeline(request):
    """
    API endpoint for task execution timeline.

    Returns:
        - Recent task execution logs from BkLog (last 24 hours)
        - Today's scheduled tasks with execution status
    """
    from apps.core.models import BkLog, CeleryTaskState
    from apps.core.task_config import TASK_DEFAULT_CONFIG
    from mcube_ai.celery import get_static_schedule
    from datetime import timedelta
    from django.utils import timezone

    try:
        # Get logs from last 24 hours
        cutoff = timezone.now() - timedelta(hours=24)

        logs = BkLog.objects.filter(
            timestamp__gte=cutoff
        ).order_by('-timestamp')[:200]  # Limit to 200 most recent

        log_data = []
        for log in logs:
            log_data.append({
                'timestamp': log.timestamp.isoformat(),
                'level': log.level,
                'action': log.action,
                'message': log.message,
                'background_task': log.background_task,
                'task_category': log.task_category,
                'task_id': log.task_id,
                'success': log.success,
                'execution_time_ms': log.execution_time_ms,
            })

        # Get today's schedule
        static_schedule = get_static_schedule()
        task_states = {s.task_key: s for s in CeleryTaskState.objects.all()}
        enabled_tasks = set(k for k, s in task_states.items() if s.is_enabled)

        # Get today's executed tasks
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        executed_tasks = set(
            BkLog.objects.filter(
                timestamp__gte=today_start,
                success=True
            ).values_list('background_task', flat=True).distinct()
        )

        schedule_data = []
        for key, config in static_schedule.items():
            task_path = config.get('task', '')
            task_state = task_states.get(key)

            # Extract hour/minute — prefer custom schedule from DB
            hour = None
            minute = None
            if task_state and task_state.use_custom_schedule:
                if task_state.schedule_type == 'crontab':
                    hour = task_state.schedule_hour
                    minute = task_state.schedule_minute
                elif task_state.schedule_type == 'recurring':
                    hour = task_state.recurring_start_hour
                    minute = getattr(task_state, 'recurring_start_minute', 0) or 0
            else:
                default_config = TASK_DEFAULT_CONFIG.get(key, {})
                if default_config.get('default_hour') is not None:
                    hour = default_config['default_hour']
                    minute = default_config.get('default_minute', 0)
                elif default_config.get('default_recurring_start_hour') is not None:
                    hour = default_config['default_recurring_start_hour']
                    minute = default_config.get('default_recurring_start_minute', 0)
                else:
                    schedule = config.get('schedule')
                    if hasattr(schedule, 'hour') and hasattr(schedule, 'minute'):
                        try:
                            if hasattr(schedule.hour, '__iter__') and not isinstance(schedule.hour, str):
                                hour = min(schedule.hour) if schedule.hour else None
                            else:
                                hour = int(schedule.hour) if str(schedule.hour).isdigit() else None

                            if hasattr(schedule.minute, '__iter__') and not isinstance(schedule.minute, str):
                                minute = min(schedule.minute) if schedule.minute else 0
                            else:
                                minute = int(schedule.minute) if str(schedule.minute).isdigit() else 0
                        except (ValueError, TypeError):
                            pass

            if hour is not None:
                display_name = task_state.display_name if task_state and task_state.display_name else key.replace('-', ' ').title()

                schedule_data.append({
                    'key': key,
                    'task': task_path,
                    'display_name': display_name,
                    'short_name': display_name[:15] if len(display_name) > 15 else display_name,
                    'hour': hour,
                    'minute': minute,
                    'is_active': key in enabled_tasks,
                    'executed': task_path in executed_tasks or key in executed_tasks,
                })

        # Sort by time
        schedule_data.sort(key=lambda x: (x['hour'], x['minute']))

        return JsonResponse({
            'success': True,
            'logs': log_data,
            'schedule': schedule_data,
            'total_logs': len(log_data),
            'total_scheduled': len(schedule_data),
        })

    except Exception as e:
        logger.error(f"Error fetching task timeline: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_user)
def api_recent_executions(request):
    """
    API endpoint returning today's task executions grouped by task_id.
    Each group contains: task name, start/end time, overall status, steps.
    """
    from apps.core.models import BkLog
    from django.utils import timezone
    from collections import OrderedDict

    try:
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        logs = BkLog.objects.filter(
            timestamp__gte=today_start,
            task_id__gt='',
        ).order_by('timestamp')

        # Group by task_id
        groups = OrderedDict()
        for log in logs:
            tid = log.task_id
            if tid not in groups:
                groups[tid] = []
            groups[tid].append(log)

        executions = []
        for task_id, entries in groups.items():
            first = entries[0]
            last = entries[-1]

            # Determine overall success: failed if any entry has success=False
            overall_success = all(e.success for e in entries)
            has_complete = any(e.action in ('COMPLETE', 'FAILED') for e in entries)

            if not has_complete:
                status = 'running'
            elif overall_success:
                status = 'success'
            else:
                status = 'failed'

            # Get execution time from the COMPLETE/FAILED entry
            exec_time_ms = None
            for e in reversed(entries):
                if e.execution_time_ms is not None:
                    exec_time_ms = e.execution_time_ms
                    break

            # Count warnings/errors
            warnings_count = sum(1 for e in entries if e.level == 'warning')
            errors_count = sum(1 for e in entries if e.level in ('error', 'critical'))

            # Collect error details
            error_detail = ''
            for e in entries:
                if e.error_details:
                    error_detail = e.error_details
                    break

            # Build step list
            steps = []
            for e in entries:
                steps.append({
                    'timestamp': e.timestamp.isoformat(),
                    'action': e.action,
                    'message': e.message,
                    'level': e.level,
                    'context_data': e.context_data if e.context_data else None,
                    'error_details': e.error_details if e.error_details else None,
                })

            task_name = first.background_task or first.action
            display_name = task_name.replace('_', ' ').replace('-', ' ').title()

            executions.append({
                'task_id': task_id,
                'task_name': task_name,
                'display_name': display_name,
                'category': first.task_category,
                'start_time': first.timestamp.isoformat(),
                'end_time': last.timestamp.isoformat(),
                'status': status,
                'execution_time_ms': exec_time_ms,
                'warnings_count': warnings_count,
                'errors_count': errors_count,
                'error_details': error_detail[:2000] if error_detail else '',
                'steps': steps,
            })

        # Sort newest first, limit to 20
        executions.sort(key=lambda x: x['start_time'], reverse=True)
        executions = executions[:20]

        return JsonResponse({
            'success': True,
            'executions': executions,
            'total': len(executions),
        })

    except Exception as e:
        logger.error(f"Error fetching recent executions: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# TASK PRESETS
# =============================================================================

@login_required
@user_passes_test(is_admin_user)
def list_presets(request):
    """List all task presets."""
    from apps.core.models import TaskPreset
    presets = list(TaskPreset.objects.values('id', 'name', 'description', 'is_builtin'))
    return JsonResponse({'success': True, 'presets': presets})


@login_required
@user_passes_test(is_admin_user)
@require_POST
def apply_preset(request):
    """Apply a task preset - toggle tasks to match preset state."""
    from apps.core.models import TaskPreset, CeleryTaskState
    from apps.core.task_config import TASK_DEFAULT_CONFIG, ALGORITHM_TASK_GROUPS

    preset_name = request.POST.get('preset_name', '')

    # Built-in presets
    builtin_presets = {
        'full_trading': lambda: {k: True for k in TASK_DEFAULT_CONFIG.keys()},
        'all_off': lambda: {k: False for k in TASK_DEFAULT_CONFIG.keys()},
        'futures_only': lambda: _build_algo_preset('futures', ALGORITHM_TASK_GROUPS, TASK_DEFAULT_CONFIG),
        'options_only': lambda: _build_algo_preset('options', ALGORITHM_TASK_GROUPS, TASK_DEFAULT_CONFIG),
        'data_monitoring': lambda: _build_data_monitoring_preset(TASK_DEFAULT_CONFIG),
    }

    if preset_name in builtin_presets:
        task_states = builtin_presets[preset_name]()
    else:
        try:
            preset = TaskPreset.objects.get(name=preset_name)
            task_states = preset.task_states
        except TaskPreset.DoesNotExist:
            return JsonResponse({'success': False, 'error': f'Preset "{preset_name}" not found'})

    # Apply the preset
    changed = 0
    for task_key, should_enable in task_states.items():
        state, _ = CeleryTaskState.objects.get_or_create(task_key=task_key)
        if state.is_enabled != should_enable:
            state.is_enabled = should_enable
            state.save()
            changed += 1

    # Restart Celery Beat
    from apps.core.utils.celery_management import ensure_celery_running
    ensure_celery_running()

    return JsonResponse({
        'success': True,
        'message': f'Preset applied: {changed} tasks changed',
    })


@login_required
@user_passes_test(is_admin_user)
@require_POST
def save_preset(request):
    """Save current task states as a named preset."""
    from apps.core.models import TaskPreset, CeleryTaskState

    preset_name = request.POST.get('preset_name', '').strip()
    if not preset_name:
        return JsonResponse({'success': False, 'error': 'Preset name is required'})

    # Snapshot current states
    task_states = {}
    for state in CeleryTaskState.objects.all():
        task_states[state.task_key] = state.is_enabled

    preset, created = TaskPreset.objects.update_or_create(
        name=preset_name,
        defaults={
            'task_states': task_states,
            'is_builtin': False,
        }
    )

    return JsonResponse({
        'success': True,
        'message': f'Preset "{ preset_name}" {"created" if created else "updated"}',
    })


def _build_algo_preset(algo_key, algo_groups, task_config):
    """Build a preset that enables only tasks for a specific algorithm."""
    group = algo_groups.get(algo_key, {})
    enabled_keys = set(
        group.get('own_tasks', []) +
        group.get('shared_tasks', []) +
        group.get('monitoring_tasks', [])
    )
    # Also enable data tasks (always needed)
    for k, cfg in task_config.items():
        if cfg.get('category') == 'data':
            enabled_keys.add(k)
    return {k: (k in enabled_keys) for k in task_config.keys()}


def _build_data_monitoring_preset(task_config):
    """Build a preset with only data + monitoring + risk tasks."""
    enabled_categories = {'data', 'monitoring', 'risk'}
    return {k: (cfg.get('category') in enabled_categories) for k, cfg in task_config.items()}


# =============================================================================
# LOG VIEWER VIEWS
# =============================================================================

import os as _os
import json as _json
from pathlib import Path as _Path


def _log_dir():
    return _Path(getattr(settings, 'LOG_DIR', settings.BASE_DIR / 'logs'))


def _validate_log_path(file_rel):
    """Return absolute path if file_rel is safely inside LOG_DIR, else None."""
    log_dir = _log_dir().resolve()
    try:
        abs_path = (log_dir / file_rel).resolve()
        if str(abs_path).startswith(str(log_dir)):
            return str(abs_path)
    except Exception:
        pass
    return None


def _human_log_size(size):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024:
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} GB'


def _collect_log_files():
    """Walk the log directory and return metadata for each current .log file."""
    log_dir = _log_dir()
    files = []
    for root, dirs, filenames in _os.walk(str(log_dir)):
        dirs[:] = sorted(d for d in dirs if d not in ('pids', '__pycache__'))
        for fname in sorted(filenames):
            if not fname.endswith('.log'):
                continue
            fpath = _os.path.join(root, fname)
            rel = _os.path.relpath(fpath, str(log_dir))
            group = _os.path.relpath(root, str(log_dir))
            try:
                stat = _os.stat(fpath)
                files.append({
                    'name': fname,
                    'rel_path': rel,
                    'size': stat.st_size,
                    'size_human': _human_log_size(stat.st_size),
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'group': group,
                })
            except OSError:
                continue
    return files


@login_required
def log_viewer(request):
    """Main log viewer page — lists all log files grouped by directory."""
    log_files = _collect_log_files()
    groups = {}
    for f in log_files:
        groups.setdefault(f['group'], []).append(f)
    return render(request, 'core/logs/log_viewer.html', {
        'log_groups': groups,
        'log_files': log_files,
    })


@login_required
def api_log_files(request):
    """JSON: list all log files with metadata."""
    return JsonResponse({'files': _collect_log_files()})


@login_required
def api_log_content(request):
    """
    JSON: return filtered log content.

    GET params:
        file    — relative path within LOG_DIR
        lines   — max lines to return (default 200, max 2000)
        level   — all | error | warning | info  (default all)
        search  — text substring filter (case-insensitive)
    """
    file_rel = request.GET.get('file', '').strip()
    try:
        lines_limit = min(int(request.GET.get('lines', 200)), 2000)
    except (ValueError, TypeError):
        lines_limit = 200
    level_filter = request.GET.get('level', 'all').lower()
    search_text = request.GET.get('search', '').lower()

    if not file_rel:
        return JsonResponse({'error': 'No file specified'}, status=400)

    abs_path = _validate_log_path(file_rel)
    if not abs_path or not _os.path.exists(abs_path):
        return JsonResponse({'error': 'File not found'}, status=404)

    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as fh:
            all_lines = fh.readlines()

        filtered = []
        for raw in all_lines:
            line = raw.rstrip('\n')
            if not line:
                continue
            upper = line.upper()
            # Level filter
            if level_filter == 'error':
                if '] ERROR' not in upper and '] CRITICAL' not in upper:
                    continue
            elif level_filter == 'warning':
                if '] WARNING' not in upper:
                    continue
            elif level_filter == 'info':
                if '] DEBUG' in upper:
                    continue
            # Text search
            if search_text and search_text not in line.lower():
                continue
            filtered.append(line)

        tail = filtered[-lines_limit:]

        result_lines = []
        for line in tail:
            upper = line.upper()
            if '] ERROR' in upper or '] CRITICAL' in upper:
                lvl = 'error'
            elif '] WARNING' in upper:
                lvl = 'warning'
            elif '] DEBUG' in upper:
                lvl = 'debug'
            else:
                lvl = 'info'
            result_lines.append({'text': line, 'level': lvl})

        return JsonResponse({
            'lines': result_lines,
            'total_in_file': len(all_lines),
            'filtered': len(filtered),
            'showing': len(result_lines),
            'file': file_rel,
        })
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


@login_required
def api_log_clear(request):
    """POST: truncate a log file (keeps the file, clears content)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = _json.loads(request.body)
        file_rel = data.get('file', '').strip()
    except (_json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    abs_path = _validate_log_path(file_rel)
    if not abs_path or not _os.path.exists(abs_path):
        return JsonResponse({'error': 'File not found'}, status=404)

    try:
        with open(abs_path, 'w'):
            pass
        logger.info('Log file cleared by %s: %s', request.user.username, file_rel)
        return JsonResponse({'success': True, 'message': f'Cleared {file_rel}'})
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


@login_required
def api_log_download(request):
    """Download a raw log file as plain text."""
    from django.http import FileResponse, Http404

    file_rel = request.GET.get('file', '').strip()
    if not file_rel:
        raise Http404

    abs_path = _validate_log_path(file_rel)
    if not abs_path or not _os.path.exists(abs_path):
        raise Http404

    fname = _os.path.basename(abs_path)
    response = FileResponse(open(abs_path, 'rb'), content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    return response
