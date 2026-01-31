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
from apps.brokers.integrations.breeze import BreezeAPI

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
                pos.calculate_unrealized_pnl() or Decimal('0')
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
                result = fetcher.fetch_fno_data()

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
                result = fetcher.fetch_fno_data()

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

        # Attempt login
        neo = NeoAPI()
        success = neo.login()

        if success:
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
            messages.error(request, f"❌ Kotak Neo login failed for {creds.username}")

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
            # Token is valid for today, attempt auto-login without asking for token
            logger.info("Breeze has valid token from today, attempting auto-login")
            session_token = creds.session_token
            # Don't save again, just use existing token
            skip_save = True
        else:
            # Token missing or expired, show form
            logger.info("Breeze token missing or expired, showing form")
            context = {
                'username': creds.username,
                'api_key': creds.api_key,
            }
            return render(request, 'core/breeze_token_input.html', context)

    elif request.method == 'POST':
        # Get session token from form
        session_token = request.POST.get('session_token', '').strip()
        if not session_token:
            messages.error(request, "Session token is required")
            return redirect('core:verify_breeze_login')

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
        import chromedriver_autoinstaller
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
        from datetime import datetime, timedelta

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
        from selenium import webdriver
        from bs4 import BeautifulSoup
        import pandas as pd

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
        from apps.data.tools import trendlyne
        from apps.data.tools.trendlyne import (
            get_all_trendlyne_data,
            getFnOData,
            getMarketSnapshotData,
            getTrendlyneForecasterData
        )

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
        from apps.accounts.models import BrokerAccount

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
            pnl = latest.calculate_unrealized_pnl()
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
        from datetime import datetime
        kotak_creds = CredentialStore.objects.filter(service='kotakneo').first()

        if kotak_creds:
            # Check session for verification status
            kotak_verified = request.session.get('kotak_login_verified', False) if request else False
            kotak_time = request.session.get('kotak_login_time', '') if request else ''

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
            breeze_time = request.session.get('breeze_login_time', '') if request else ''

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
        account = BrokerAccount.objects.filter(is_active=True).first()

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
            tests.append({
                'name': '🔌 vLLM Server Connection',
                'status': 'pass',
                'message': f'✓ Connected to {client.base_url} | Model: {client.model[:50]}...',
                'description': '<b>Tests:</b> Connection to vLLM server. <b>Success means:</b> Your 70B Llama model is accessible and ready.',
                'trigger_url': reverse('llm:test_connection'),
                'trigger_label': '🔄 Test Connection',
            })
        else:
            tests.append({
                'name': '🔌 vLLM Server Connection',
                'status': 'fail',
                'message': '✗ LLM not running on the server',
                'description': '<b>Start LLM:</b> <code>cd /home/anupamvm/vllm && docker compose up -d && docker logs -f vllm-70b</code>',
                'trigger_url': reverse('llm:test_connection'),
                'trigger_label': '🔄 Retry Connection',
            })
    except Exception as e:
        tests.append({
            'name': '🔌 vLLM Server Connection',
            'status': 'fail',
            'message': f'✗ Error: {str(e)}',
            'description': '<b>Start LLM:</b> <code>cd /home/anupamvm/vllm && docker compose up -d && docker logs -f vllm-70b</code>',
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
                module = importlib.import_module(module_name)
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

    # Test 2: Test simple message (with response validation)
    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if telegram_client.is_enabled():
            test_message = "Test message from mCube System Test Page"
            success, response = telegram_client.send_message(test_message)

            tests.append({
                'name': 'Send Simple Message',
                'status': 'pass' if success else 'fail',
                'message': response if success else f'Send failed: {response}',
                'trigger_url': '/core/test/trigger-telegram-simple/',
                'trigger_label': 'Send Again',
            })
        else:
            tests.append({
                'name': 'Send Simple Message',
                'status': 'warning',
                'message': 'Skipped - Telegram not configured',
                'trigger_url': '/core/test/trigger-telegram-simple/',
                'trigger_label': 'Test (Configure First)',
            })
    except Exception as e:
        tests.append({
            'name': 'Send Simple Message',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: Test priority message (CRITICAL)
    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if telegram_client.is_enabled():
            test_message = "This is a critical test message"
            success, response = telegram_client.send_priority_message(test_message, priority='CRITICAL')

            tests.append({
                'name': 'Send Priority Message (CRITICAL)',
                'status': 'pass' if success else 'fail',
                'message': 'Critical alert sent' if success else f'Failed: {response}',
                'trigger_url': '/core/test/trigger-telegram-critical/',
                'trigger_label': 'Trigger',
            })
        else:
            tests.append({
                'name': 'Send Priority Message (CRITICAL)',
                'status': 'warning',
                'message': 'Skipped - Telegram not configured',
                'trigger_url': '/core/test/trigger-telegram-critical/',
                'trigger_label': 'Test (Configure First)',
            })
    except Exception as e:
        tests.append({
            'name': 'Send Priority Message (CRITICAL)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 4: Test position alert (SL_HIT)
    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if telegram_client.is_enabled():
            position_data = {
                'account_name': 'DEMO_ACCOUNT',
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

            tests.append({
                'name': 'Position Alert - Stop-Loss Hit',
                'status': 'pass' if success else 'fail',
                'message': 'SL_HIT alert sent with full position details' if success else f'Failed: {response}',
                'trigger_url': '/core/test/trigger-telegram-sl-alert/',
                'trigger_label': 'Send Alert',
            })
        else:
            tests.append({
                'name': 'Position Alert - Stop-Loss Hit',
                'status': 'warning',
                'message': 'Skipped - Telegram not configured',
                'trigger_url': '/core/test/trigger-telegram-sl-alert/',
                'trigger_label': 'Test (Configure First)',
            })
    except Exception as e:
        tests.append({
            'name': 'Position Alert - Stop-Loss Hit',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 5: Test position alert (TARGET_HIT)
    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if telegram_client.is_enabled():
            position_data = {
                'account_name': 'DEMO_ACCOUNT',
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

            tests.append({
                'name': 'Position Alert - Target Hit',
                'status': 'pass' if success else 'fail',
                'message': 'TARGET_HIT alert sent' if success else f'Failed: {response}',
                'trigger_url': '/core/test/trigger-telegram-target-alert/',
                'trigger_label': 'Send Alert',
            })
        else:
            tests.append({
                'name': 'Position Alert - Target Hit',
                'status': 'warning',
                'message': 'Skipped - Telegram not configured',
                'trigger_url': '/core/test/trigger-telegram-target-alert/',
                'trigger_label': 'Test (Configure First)',
            })
    except Exception as e:
        tests.append({
            'name': 'Position Alert - Target Hit',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 6: Test risk alert (WARNING)
    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if telegram_client.is_enabled():
            risk_data = {
                'account_name': 'DEMO_ACCOUNT',
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

            tests.append({
                'name': 'Risk Alert - Warning',
                'status': 'pass' if success else 'fail',
                'message': 'Risk warning sent' if success else f'Failed: {response}',
                'trigger_url': '/core/test/trigger-telegram-risk-alert/',
                'trigger_label': 'Send Alert',
            })
        else:
            tests.append({
                'name': 'Risk Alert - Warning',
                'status': 'warning',
                'message': 'Skipped - Telegram not configured',
                'trigger_url': '/core/test/trigger-telegram-risk-alert/',
                'trigger_label': 'Test (Configure First)',
            })
    except Exception as e:
        tests.append({
            'name': 'Risk Alert - Warning',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 7: Test risk alert (EMERGENCY - Circuit Breaker)
    try:
        from apps.alerts.services import get_telegram_client
        telegram_client = get_telegram_client()

        if telegram_client.is_enabled():
            risk_data = {
                'account_name': 'DEMO_ACCOUNT',
                'action_required': 'EMERGENCY_EXIT',
                'trading_allowed': False,
                'active_circuit_breakers': 1,
                'breached_limits': [
                    {'type': 'DAILY_LOSS', 'current': 55000, 'limit': 50000}
                ],
                'message': 'CIRCUIT BREAKER ACTIVATED! Daily loss limit exceeded. All trading stopped.'
            }
            success, response = telegram_client.send_risk_alert(risk_data)

            tests.append({
                'name': 'Risk Alert - Circuit Breaker (Emergency)',
                'status': 'pass' if success else 'fail',
                'message': 'Emergency alert sent (trading disabled)' if success else f'Failed: {response}',
                'trigger_url': '/core/test/trigger-telegram-circuit-breaker/',
                'trigger_label': 'Send Alert',
            })
        else:
            tests.append({
                'name': 'Risk Alert - Circuit Breaker (Emergency)',
                'status': 'warning',
                'message': 'Skipped - Telegram not configured',
                'trigger_url': '/core/test/trigger-telegram-circuit-breaker/',
                'trigger_label': 'Test (Configure First)',
            })
    except Exception as e:
        tests.append({
            'name': 'Risk Alert - Circuit Breaker (Emergency)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 8: Test daily summary
    try:
        from apps.alerts.services import get_telegram_client
        from datetime import date
        telegram_client = get_telegram_client()

        if telegram_client.is_enabled():
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

            tests.append({
                'name': 'Daily Trading Summary',
                'status': 'pass' if success else 'fail',
                'message': 'Daily summary sent with complete statistics' if success else f'Failed: {response}',
                'trigger_url': '/core/test/trigger-telegram-summary/',
                'trigger_label': 'Send Summary',
            })
        else:
            tests.append({
                'name': 'Daily Trading Summary',
                'status': 'warning',
                'message': 'Skipped - Telegram not configured',
                'trigger_url': '/core/test/trigger-telegram-summary/',
                'trigger_label': 'Test (Configure First)',
            })
    except Exception as e:
        tests.append({
            'name': 'Daily Trading Summary',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 9: Alert Manager integration (database storage)
    try:
        from apps.alerts.services import get_alert_manager
        alert_manager = get_alert_manager()

        # Create a test system alert
        test_alert = alert_manager.create_system_alert(
            alert_type='SYSTEM_TEST',
            title='System Test Alert',
            message='Testing AlertManager integration with database storage',
            priority='INFO',
            send_telegram=True
        )

        if test_alert:
            # Verify alert was stored
            from apps.alerts.models import Alert
            stored_alert = Alert.objects.filter(id=test_alert.id).first()

            tests.append({
                'name': 'AlertManager - Database Integration',
                'status': 'pass' if stored_alert else 'fail',
                'message': f'Alert stored in DB (ID: {test_alert.id}) with {test_alert.logs.count()} delivery logs' if stored_alert else 'Alert not found in database',
            })
        else:
            tests.append({
                'name': 'AlertManager - Database Integration',
                'status': 'fail',
                'message': 'Failed to create alert',
            })
    except Exception as e:
        tests.append({
            'name': 'AlertManager - Database Integration',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 10: Alert log verification (response tracking)
    try:
        from apps.alerts.models import Alert, AlertLog

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
            # Kotak Neo Credentials
            kotak_creds.api_key = request.POST.get('kotak_api_key', '')
            kotak_creds.api_secret = request.POST.get('kotak_api_secret', '')
            kotak_creds.username = request.POST.get('kotak_username', '')
            kotak_creds.password = request.POST.get('kotak_password', '')
            kotak_creds.neo_password = request.POST.get('kotak_neo_password', '')
            kotak_creds.pan = request.POST.get('kotak_pan', '').upper()
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

            messages.success(request, 'Configuration saved successfully!')
            logger.info(f"System configuration updated by {request.user.username}")

        except Exception as e:
            messages.error(request, f'Error saving configuration: {str(e)}')
            logger.error(f"Error saving system configuration: {e}", exc_info=True)

        return redirect('core:broker_settings')

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
    # and get all task states
    try:
        CeleryTaskState.initialize_static_tasks(static_schedule, force=False)
        task_states = CeleryTaskState.get_all_states()
    except Exception as e:
        logger.warning(f"Could not initialize/get task states: {e}")
        task_states = {}

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
            'description': 'Daily trading workflow: setup, start, options, futures, close',
            'keywords': ['setup-trading', 'start-trading', 'options', 'futures', 'screen', 'averaging', 'strangle', 'close-trading', 'batch-options'],
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
        """Determine category based on task key and queue"""
        key_lower = task_key.lower()

        # First try to match by queue
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

        # Get enabled state (default to False/inactive if not in DB)
        is_enabled = task_states.get(key, False)
        queue = config.get('options', {}).get('queue', 'default')
        category = categorize_task(key, queue)

        # Get config fields for this task if available
        config_info = TASK_CONFIG_FIELDS.get(key, {})

        task_info = {
            'key': key,
            'task': config.get('task', 'Unknown'),
            'schedule': str(config.get('schedule', 'Unknown')),
            'queue': queue,
            'is_enabled': is_enabled,
            'config_fields': config_info.get('fields', []),
            'display_name': config_info.get('display_name', key),
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

    context = {
        'dynamic_tasks': dynamic_tasks,
        'static_tasks': static_tasks,
        'task_categories': task_categories,  # Categorized view for new UI
        'worker_status': worker_status,
        'redis_status': redis_status,
        'enabled_count': enabled_count,
        'disabled_count': disabled_count,
        'total_count': total_count,
        'timestamp': datetime.now(),
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
        messages.success(request, f"Task '{task.display_name}' {status} successfully.")

        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'is_enabled': task.is_enabled,
            'message': f"Task '{task.display_name}' {status}"
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


# Task configuration field mappings - uses fields from SystemSettings model
# schedule_type: 'crontab' (fixed time) or 'interval' (recurring)
# category_flag: The SystemSettings enable flag for this category
# NOTE: Only includes fields that exist in SystemSettings model. Fields without model backing
#       will use defaults and won't persist (shown for display purposes).
TASK_CONFIG_FIELDS = {
    # =========================================================================
    # MARKET DATA TASKS
    # =========================================================================
    'morning-data-sync': {
        'display_name': 'Morning Data Sync',
        'description': 'Full morning data synchronization including market data, news, and indices',
        'schedule_type': 'crontab',
        'category': 'data',
        'category_flag': 'enable_market_data_tasks',
        'fields': []  # No configurable fields in SystemSettings
    },
    'update-pre-market-data': {
        'display_name': 'Pre-Market Data Update',
        'description': 'Fetches pre-market data before market opens',
        'schedule_type': 'crontab',
        'category': 'data',
        'category_flag': 'enable_market_data_tasks',
        'fields': [
            {'name': 'premarket_update_hour', 'label': 'Hour', 'type': 'number', 'help': 'Hour to run (0-23)', 'min': 0, 'max': 23, 'default': 8},
            {'name': 'premarket_update_minute', 'label': 'Minute', 'type': 'number', 'help': 'Minute (0-59)', 'min': 0, 'max': 59, 'default': 50},
        ]
    },
    'update-live-market-data': {
        'display_name': 'Live Market Data Update',
        'description': 'Updates live market data during trading hours',
        'schedule_type': 'interval',
        'category': 'data',
        'category_flag': 'enable_market_data_tasks',
        'fields': [
            {'name': 'live_data_interval_minutes', 'label': 'Interval', 'type': 'number', 'unit': 'minutes', 'help': 'Update every N minutes', 'min': 1, 'max': 60, 'default': 5},
            {'name': 'live_data_start_hour', 'label': 'Start Hour', 'type': 'number', 'help': 'Start updating from this hour', 'min': 0, 'max': 23, 'default': 9},
            {'name': 'live_data_end_hour', 'label': 'End Hour', 'type': 'number', 'help': 'Stop updating after this hour', 'min': 0, 'max': 23, 'default': 15},
        ]
    },
    'update-post-market-data': {
        'display_name': 'Post-Market Data Update',
        'description': 'Updates data after market close for end-of-day analysis',
        'schedule_type': 'crontab',
        'category': 'data',
        'category_flag': 'enable_market_data_tasks',
        'fields': [
            {'name': 'postmarket_update_hour', 'label': 'Hour', 'type': 'number', 'help': 'Hour to run (0-23)', 'min': 0, 'max': 23, 'default': 15},
            {'name': 'postmarket_update_minute', 'label': 'Minute', 'type': 'number', 'help': 'Minute (0-59)', 'min': 0, 'max': 59, 'default': 35},
        ]
    },

    # =========================================================================
    # STRATEGY EXECUTION TASKS
    # =========================================================================
    'setup-trading-day': {
        'display_name': 'Setup Trading Day',
        'description': 'Prepares system for trading day (loads strategies, checks accounts)',
        'schedule_type': 'crontab',
        'category': 'strategies',
        'category_flag': 'enable_strategy_tasks',
        'fields': []  # No configurable fields in SystemSettings - uses fixed schedule
    },
    'start-trading-day': {
        'display_name': 'Start Trading Day',
        'description': 'Initiates trading at market open',
        'schedule_type': 'crontab',
        'category': 'strategies',
        'category_flag': 'enable_strategy_tasks',
        'fields': []  # No configurable fields - runs at market open
    },
    'evaluate-options-strategy': {
        'display_name': 'Evaluate Options Strategy',
        'description': 'Analyzes market conditions and selects options strategies',
        'schedule_type': 'crontab',
        'category': 'strategies',
        'category_flag': 'enable_strategy_tasks',
        'fields': []  # No configurable fields
    },
    'start-options-trade': {
        'display_name': 'Start Options Trade',
        'description': 'Executes options trades based on strategy evaluation',
        'schedule_type': 'crontab',
        'category': 'strategies',
        'category_flag': 'enable_strategy_tasks',
        'fields': []  # No configurable fields
    },
    'batch-options-averaging': {
        'display_name': 'Options Averaging (Batch)',
        'description': 'Runs averaging logic for options positions at regular intervals',
        'schedule_type': 'recurring',
        'category': 'strategies',
        'category_flag': 'enable_strategy_tasks',
        'fields': []  # Complex recurring - not easily configurable
    },
    'batch-options-averaging-10am': {
        'display_name': 'Options Averaging (10 AM)',
        'description': 'Continues options averaging after 10 AM',
        'schedule_type': 'recurring',
        'category': 'strategies',
        'category_flag': 'enable_strategy_tasks',
        'fields': []  # Complex recurring - not easily configurable
    },
    'screen-futures-opportunities': {
        'display_name': 'Futures Screening',
        'description': 'Scans for futures trading opportunities',
        'schedule_type': 'interval',
        'category': 'strategies',
        'category_flag': 'enable_strategy_tasks',
        'fields': [
            {'name': 'futures_screening_interval_minutes', 'label': 'Interval', 'type': 'number', 'unit': 'minutes', 'help': 'Screen every N minutes', 'min': 5, 'max': 120, 'default': 30},
            {'name': 'futures_screening_start_hour', 'label': 'Start Hour', 'type': 'number', 'help': 'Start from this hour', 'min': 0, 'max': 23, 'default': 9},
            {'name': 'futures_screening_end_hour', 'label': 'End Hour', 'type': 'number', 'help': 'Stop after this hour', 'min': 0, 'max': 23, 'default': 14},
        ]
    },
    'check-futures-averaging': {
        'display_name': 'Futures Averaging Check',
        'description': 'Checks and executes averaging for futures positions',
        'schedule_type': 'interval',
        'category': 'strategies',
        'category_flag': 'enable_strategy_tasks',
        'fields': [
            {'name': 'futures_averaging_interval_minutes', 'label': 'Interval', 'type': 'number', 'unit': 'minutes', 'help': 'Check every N minutes', 'min': 1, 'max': 60, 'default': 10},
        ]
    },
    'close-trading-day': {
        'display_name': 'Close Trading Day',
        'description': 'Closes positions and finalizes trading day',
        'schedule_type': 'crontab',
        'category': 'strategies',
        'category_flag': 'enable_strategy_tasks',
        'fields': []  # Fixed schedule - closes before market close
    },

    # =========================================================================
    # POSITION MONITORING TASKS
    # =========================================================================
    'monitor-all-positions': {
        'display_name': 'Position Monitoring',
        'description': 'Real-time monitoring of all open positions',
        'schedule_type': 'interval',
        'category': 'monitoring',
        'category_flag': 'enable_position_monitoring',
        'fields': [
            {'name': 'monitor_positions_interval_seconds', 'label': 'Interval', 'type': 'number', 'unit': 'seconds', 'help': 'Monitor every N seconds', 'min': 5, 'max': 300, 'default': 10},
        ]
    },
    'update-position-pnl': {
        'display_name': 'P&L Update',
        'description': 'Updates profit/loss for all positions',
        'schedule_type': 'interval',
        'category': 'monitoring',
        'category_flag': 'enable_position_monitoring',
        'fields': [
            {'name': 'update_pnl_interval_seconds', 'label': 'Interval', 'type': 'number', 'unit': 'seconds', 'help': 'Update P&L every N seconds', 'min': 5, 'max': 300, 'default': 15},
        ]
    },
    'check-exit-conditions': {
        'display_name': 'Exit Conditions Check',
        'description': 'Checks stop-loss, target, and other exit conditions',
        'schedule_type': 'interval',
        'category': 'monitoring',
        'category_flag': 'enable_position_monitoring',
        'fields': [
            {'name': 'check_exit_interval_seconds', 'label': 'Interval', 'type': 'number', 'unit': 'seconds', 'help': 'Check exits every N seconds', 'min': 10, 'max': 300, 'default': 30},
        ]
    },

    # =========================================================================
    # RISK MANAGEMENT TASKS
    # =========================================================================
    'check-risk-limits-all-accounts': {
        'display_name': 'Risk Limits Check',
        'description': 'Monitors risk limits across all trading accounts',
        'schedule_type': 'interval',
        'category': 'risk',
        'category_flag': 'enable_risk_monitoring',
        'fields': [
            {'name': 'risk_check_interval_seconds', 'label': 'Interval', 'type': 'number', 'unit': 'seconds', 'help': 'Check risk every N seconds', 'min': 30, 'max': 600, 'default': 60},
        ]
    },
    'monitor-circuit-breakers': {
        'display_name': 'Circuit Breaker Monitor',
        'description': 'Monitors market circuit breakers and trading halts',
        'schedule_type': 'interval',
        'category': 'risk',
        'category_flag': 'enable_risk_monitoring',
        'fields': [
            {'name': 'circuit_breaker_interval_seconds', 'label': 'Interval', 'type': 'number', 'unit': 'seconds', 'help': 'Monitor every N seconds', 'min': 10, 'max': 300, 'default': 30},
        ]
    },

    # =========================================================================
    # REPORTING & ANALYTICS TASKS
    # =========================================================================
    'generate-daily-pnl-report': {
        'display_name': 'Daily P&L Report',
        'description': 'Generates end-of-day profit/loss report',
        'schedule_type': 'crontab',
        'category': 'reports',
        'category_flag': 'enable_reporting_tasks',
        'fields': [
            {'name': 'daily_pnl_report_hour', 'label': 'Hour', 'type': 'number', 'help': 'Hour to generate report (0-23)', 'min': 0, 'max': 23, 'default': 16},
            {'name': 'daily_pnl_report_minute', 'label': 'Minute', 'type': 'number', 'help': 'Minute (0-59)', 'min': 0, 'max': 59, 'default': 0},
        ]
    },
    'sync-benchmark-data': {
        'display_name': 'Sync Benchmark Data',
        'description': 'Syncs benchmark indices for performance comparison',
        'schedule_type': 'crontab',
        'category': 'reports',
        'category_flag': 'enable_reporting_tasks',
        'fields': []  # No configurable fields in SystemSettings
    },
    'daily-data-aggregation': {
        'display_name': 'Daily Data Aggregation',
        'description': 'Aggregates daily trading data for analytics',
        'schedule_type': 'crontab',
        'category': 'reports',
        'category_flag': 'enable_reporting_tasks',
        'fields': []  # No configurable fields in SystemSettings
    },
    'update-equity-curves': {
        'display_name': 'Update Equity Curves',
        'description': 'Updates equity curves for portfolio tracking',
        'schedule_type': 'crontab',
        'category': 'reports',
        'category_flag': 'enable_reporting_tasks',
        'fields': []  # No configurable fields in SystemSettings
    },
}


@login_required
@user_passes_test(is_admin_user)
def get_task_config(request):
    """
    Get configuration fields and current values for a specific task.

    Query params:
        task_key: The task key to get configuration for

    Returns JSON with fields definition and current values from SystemSettings.
    """
    from apps.core.models import SystemSettings

    task_key = request.GET.get('task_key', '')

    if not task_key:
        return JsonResponse({'success': False, 'error': 'task_key required'}, status=400)

    config_info = TASK_CONFIG_FIELDS.get(task_key)

    if not config_info:
        return JsonResponse({
            'success': True,
            'task_key': task_key,
            'display_name': task_key,
            'description': '',
            'schedule_type': 'unknown',
            'category': '',
            'category_flag': '',
            'fields': [],
            'values': {},
            'message': 'No configurable options for this task'
        })

    # Get current values from SystemSettings
    try:
        settings = SystemSettings.get_settings()
        values = {}
        for field in config_info['fields']:
            field_name = field['name']
            field_type = field.get('type', 'number')

            if hasattr(settings, field_name):
                val = getattr(settings, field_name)
                # Handle JSON fields (like days of week)
                if field_type == 'days' and isinstance(val, str):
                    import json
                    try:
                        val = json.loads(val)
                    except:
                        val = field.get('default', [0, 1, 2, 3, 4])
                values[field_name] = val
            else:
                values[field_name] = field.get('default', 0 if field_type == 'number' else [])

        # Get category enable flag value
        category_flag = config_info.get('category_flag', '')
        if category_flag and hasattr(settings, category_flag):
            values[category_flag] = getattr(settings, category_flag)

    except Exception as e:
        logger.error(f"Error getting SystemSettings: {e}")
        values = {}
        for f in config_info['fields']:
            default = f.get('default', 0 if f.get('type') == 'number' else [])
            values[f['name']] = default

    return JsonResponse({
        'success': True,
        'task_key': task_key,
        'display_name': config_info.get('display_name', task_key),
        'description': config_info.get('description', ''),
        'schedule_type': config_info.get('schedule_type', 'crontab'),
        'category': config_info.get('category', ''),
        'category_flag': config_info.get('category_flag', ''),
        'fields': config_info['fields'],
        'values': values,
    })


@login_required
@user_passes_test(is_admin_user)
@require_POST
def save_task_config(request):
    """
    Save configuration for a specific task and restart Celery Beat.

    POST params:
        task_key: The task key
        <field_name>: Field values to update

    Updates SystemSettings and restarts Celery Beat to apply changes.
    """
    from apps.core.models import SystemSettings
    from django.contrib import messages

    task_key = request.POST.get('task_key', '')

    if not task_key:
        return JsonResponse({'success': False, 'error': 'task_key required'}, status=400)

    config_info = TASK_CONFIG_FIELDS.get(task_key)

    if not config_info:
        return JsonResponse({'success': False, 'error': 'Task has no configurable options'}, status=400)

    try:
        import json
        settings = SystemSettings.get_settings()
        updated_fields = []

        for field in config_info['fields']:
            field_name = field['name']
            field_type = field.get('type', 'number')

            if field_type == 'days':
                # Handle days of week as a list from checkboxes
                days_key = f"{field_name}[]"
                if days_key in request.POST or field_name in request.POST:
                    # Get list of selected days
                    days_list = request.POST.getlist(days_key) or request.POST.getlist(field_name)
                    try:
                        new_value = [int(d) for d in days_list if d.isdigit()]
                        new_value = sorted(set(new_value))  # Remove duplicates and sort

                        # Store as JSON string if the field expects it
                        if hasattr(settings, field_name):
                            old_value = getattr(settings, field_name)
                            # Convert old value to list for comparison
                            if isinstance(old_value, str):
                                try:
                                    old_value = json.loads(old_value)
                                except:
                                    old_value = []

                            if old_value != new_value:
                                # Store as JSON string
                                setattr(settings, field_name, json.dumps(new_value))
                                updated_fields.append(field_name)
                                logger.info(f"Task config updated: {field_name} = {new_value} (was {old_value})")
                    except Exception as e:
                        logger.warning(f"Invalid days value for {field_name}: {e}")

            elif field_name in request.POST:
                try:
                    new_value = int(request.POST[field_name])

                    # Validate min/max
                    if 'min' in field and new_value < field['min']:
                        new_value = field['min']
                    if 'max' in field and new_value > field['max']:
                        new_value = field['max']

                    if hasattr(settings, field_name):
                        old_value = getattr(settings, field_name, None)
                        if old_value != new_value:
                            setattr(settings, field_name, new_value)
                            updated_fields.append(field_name)
                            logger.info(f"Task config updated: {field_name} = {new_value} (was {old_value})")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid value for {field_name}: {request.POST[field_name]}")

        # Handle category enable flag
        category_flag = config_info.get('category_flag', '')
        if category_flag and category_flag in request.POST:
            try:
                new_value = request.POST[category_flag].lower() in ('true', '1', 'on', 'yes')
                if hasattr(settings, category_flag):
                    old_value = getattr(settings, category_flag, False)
                    if old_value != new_value:
                        setattr(settings, category_flag, new_value)
                        updated_fields.append(category_flag)
                        logger.info(f"Category flag updated: {category_flag} = {new_value}")
            except Exception as e:
                logger.warning(f"Invalid category flag value: {e}")

        if updated_fields:
            settings.save()
            logger.info(f"SystemSettings saved by {request.user.username} for task {task_key}: {updated_fields}")

            # Restart Celery Beat to pick up the changes
            celery_result = ensure_celery_running()

            messages.success(request, f"Configuration for '{config_info.get('display_name', task_key)}' saved and Celery restarted.")

            return JsonResponse({
                'success': True,
                'task_key': task_key,
                'updated_fields': updated_fields,
                'message': 'Configuration saved and Celery restarted',
                'celery': {
                    'success': celery_result.get('success', False),
                    'worker_status': celery_result.get('worker_status', 'unknown'),
                    'beat_status': celery_result.get('beat_status', 'unknown'),
                    'beat_restarted': celery_result.get('beat_restarted', False),
                }
            })
        else:
            return JsonResponse({
                'success': True,
                'task_key': task_key,
                'updated_fields': [],
                'message': 'No changes detected',
                'celery': {}
            })

    except Exception as e:
        logger.error(f"Error saving task config for {task_key}: {e}", exc_info=True)
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
            'message': 'Redis not running. Run: brew install redis && brew services start redis',
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

            with open(log_file, 'a') as log:
                log.write(f"\n{'='*60}\n")
                log.write(f"Worker starting at {datetime.now().isoformat()}\n")
                log.write(f"Using Python: {python_path}\n")
                log.write(f"{'='*60}\n")

                # Use python -m celery to ensure correct environment
                proc = subprocess.Popen(
                    [
                        python_path, '-m', 'celery',
                        '-A', 'mcube_ai', 'worker',
                        '--loglevel=info',
                        '-Q', 'data,strategies,monitoring,risk,reports,celery',
                        '--concurrency=2'
                    ],
                    cwd=project_dir,
                    stdout=log,
                    stderr=log,
                    start_new_session=True
                )
                result['worker_pid'] = proc.pid

            logger.info(f"Celery worker started with PID {proc.pid} using {python_path}")
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

        # Start celery beat using venv Python
        log_file = os.path.join(project_dir, 'logs', 'celery_beat.log')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        with open(log_file, 'a') as log:
            log.write(f"\n{'='*60}\n")
            log.write(f"Beat starting at {datetime.now().isoformat()}\n")
            log.write(f"Using Python: {python_path}\n")
            log.write(f"{'='*60}\n")

            # Use python -m celery to ensure correct environment
            proc = subprocess.Popen(
                [python_path, '-m', 'celery', '-A', 'mcube_ai', 'beat', '--loglevel=info'],
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
    from django.contrib import messages

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

    def read_log_file(filepath, source, max_lines):
        """Read last N lines from a log file."""
        entries = []
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    lines = f.readlines()
                    recent = lines[-max_lines:] if len(lines) > max_lines else lines

                for line in recent:
                    parsed = parse_celery_log_line(line)
                    if parsed:
                        parsed['source'] = source
                        # Determine status
                        msg_lower = parsed['message'].lower()
                        if 'succeeded' in msg_lower:
                            parsed['status'] = 'success'
                        elif 'failed' in msg_lower or 'error' in msg_lower:
                            parsed['status'] = 'error'
                        elif 'received' in msg_lower:
                            parsed['status'] = 'received'
                        elif 'sending due task' in msg_lower:
                            parsed['status'] = 'scheduled'
                        elif 'starting' in msg_lower:
                            parsed['status'] = 'starting'
                        else:
                            parsed['status'] = 'info'
                        entries.append(parsed)
                    elif line.strip() and not line.startswith('='):
                        # Non-parsed lines (errors, tracebacks)
                        entries.append({
                            'timestamp': '',
                            'level': 'error' if 'error' in line.lower() or 'traceback' in line.lower() else 'info',
                            'process': '',
                            'message': line.strip()[:500],
                            'source': source,
                            'status': 'error' if 'error' in line.lower() else 'info',
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

    # Category to queue/keyword mapping
    CATEGORY_QUEUES = {
        'data': 'data',
        'strategies': 'strategies',
        'monitoring': 'monitoring',
        'risk': 'risk',
        'reports': 'reports',
    }

    CATEGORY_KEYWORDS = {
        'data': ['trendlyne', 'market-data', 'pre-market', 'post-market', 'live-market', 'morning-data-sync', 'news'],
        'strategies': ['setup-trading', 'start-trading', 'options', 'futures', 'screen', 'averaging', 'strangle', 'close-trading', 'batch-options', 'evaluate-options'],
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

            # Match by queue
            if queue == CATEGORY_QUEUES.get(category):
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
    from mcube_ai.celery import get_all_tasks_for_display, get_static_schedule
    import redis

    # =========================================================================
    # CELERY TASKS
    # =========================================================================

    # Get dynamic tasks from database
    dynamic_tasks = list(TradingScheduleConfig.objects.all().order_by('scheduled_time'))

    # Get ALL static tasks for display (not filtered by enabled state)
    static_schedule = get_static_schedule()

    # Initialize any missing tasks in the database (as disabled by default)
    # and get all task states
    try:
        CeleryTaskState.initialize_static_tasks(static_schedule, force=False)
        task_states = CeleryTaskState.get_all_states()
    except Exception as e:
        logger.warning(f"Could not initialize/get task states: {e}")
        task_states = {}

    # Build static tasks list (excluding dynamic ones)
    celery_static_tasks = []
    for key, config in static_schedule.items():
        if any(d in key.lower() for d in ['premarket', 'market_open', 'trade_start', 'trade_monitor', 'trade_stop', 'day_close', 'analyze_day']):
            continue
        # Default to False (inactive) if not in database
        is_active = task_states.get(key, False)
        celery_static_tasks.append({
            'key': key,
            'task': config.get('task', 'Unknown'),
            'schedule': str(config.get('schedule', 'Unknown')),
            'queue': config.get('options', {}).get('queue', 'default'),
            'is_active': is_active,
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
