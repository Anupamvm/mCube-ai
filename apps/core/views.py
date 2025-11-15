"""
Core views for mCube Trading System

This module contains system-wide views including the comprehensive test page.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import connection
from django.conf import settings
import requests
import logging
from datetime import datetime, timedelta
from decimal import Decimal

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
            from apps.orders.models import Order

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
                'total_pnl': total_pnl,
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

    # Define allowed documentation files
    allowed_docs = {
        'quick_start': 'QUICK_START.md',
        'setup_guide': 'SETUP_GUIDE.md',
        'celery_setup': 'CELERY_SETUP.md',
        'telegram_bot': 'TELEGRAM_BOT_GUIDE.md',
        'url_config': 'URL_CONFIGURATION.md',
        'auth_guide': 'AUTHENTICATION_GUIDE.md',
        'fixes_summary': 'FIXES_SUMMARY.md',
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
        'accounts': test_accounts(),
        'llm': test_llm(),
        'redis': test_redis(),
        'background_tasks': test_background_tasks(),
        'django_admin': test_django_admin(),
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
        response = requests.get('https://trendlyne.com', timeout=10)

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
                'message': f'HTTP {response.status_code}',
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

    # Test 4: Trendlyne data directory
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
            tests.append({
                'name': 'Trendlyne Data Directory',
                'status': 'pass',
                'message': f'Found {len(existing_dirs)} data dirs with {total_files} CSV files',
            })
        else:
            tests.append({
                'name': 'Trendlyne Data Directory',
                'status': 'fail',
                'message': 'No data directories found (not downloaded yet)',
            })
    except Exception as e:
        tests.append({
            'name': 'Trendlyne Data Directory',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 5: F&O Data freshness
    try:
        import os
        from django.conf import settings
        from datetime import datetime, timedelta

        data_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata')

        if os.path.exists(data_dir):
            fno_files = [f for f in os.listdir(data_dir) if f.startswith('fno_data_') and f.endswith('.csv')]

            if fno_files:
                fno_files.sort(reverse=True)
                latest_file = fno_files[0]
                file_path = os.path.join(data_dir, latest_file)
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                age_days = (datetime.now() - file_time).days

                status = 'pass' if age_days <= 7 else 'fail'
                tests.append({
                    'name': 'F&O Data Freshness',
                    'status': status,
                    'message': f'Latest: {latest_file} ({age_days} days old)',
                })
            else:
                tests.append({
                    'name': 'F&O Data Freshness',
                    'status': 'fail',
                    'message': 'No F&O data files found',
                })
        else:
            tests.append({
                'name': 'F&O Data Freshness',
                'status': 'fail',
                'message': 'Data directory not found',
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
            snapshot_files = [f for f in os.listdir(data_dir) if f.startswith('market_snapshot_') and f.endswith('.csv')]

            if snapshot_files:
                snapshot_files.sort(reverse=True)
                latest_file = snapshot_files[0]
                file_path = os.path.join(data_dir, latest_file)
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                age_days = (datetime.now() - file_time).days

                status = 'pass' if age_days <= 7 else 'fail'
                tests.append({
                    'name': 'Market Snapshot Data',
                    'status': status,
                    'message': f'Latest: {latest_file} ({age_days} days old)',
                })
            else:
                tests.append({
                    'name': 'Market Snapshot Data',
                    'status': 'fail',
                    'message': 'No market snapshot files found',
                })
        else:
            tests.append({
                'name': 'Market Snapshot Data',
                'status': 'fail',
                'message': 'Data directory not found',
            })
    except Exception as e:
        tests.append({
            'name': 'Market Snapshot Data',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 7: Forecaster Data (21 pages)
    try:
        import os
        from django.conf import settings

        data_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'trendlynedata')

        if os.path.exists(data_dir):
            forecaster_files = [f for f in os.listdir(data_dir) if f.startswith('trendlyne_') and f.endswith('.csv')]

            if forecaster_files:
                tests.append({
                    'name': 'Forecaster Data (21 Pages)',
                    'status': 'pass' if len(forecaster_files) >= 15 else 'fail',
                    'message': f'Found {len(forecaster_files)} forecaster CSV files',
                })
            else:
                tests.append({
                    'name': 'Forecaster Data (21 Pages)',
                    'status': 'fail',
                    'message': 'No forecaster data files found',
                })
        else:
            tests.append({
                'name': 'Forecaster Data (21 Pages)',
                'status': 'fail',
                'message': 'Data directory not found',
            })
    except Exception as e:
        tests.append({
            'name': 'Forecaster Data (21 Pages)',
            'status': 'fail',
            'message': f'Error: {str(e)}',
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
        from apps.orders.models import Order
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
        from apps.orders.models import Execution
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
        from apps.orders.models import Order
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
                'message': f'Latest position P&L: {pnl}',
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


def test_accounts():
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

    # Test 2: API credentials
    try:
        from apps.accounts.models import APICredential
        count = APICredential.objects.count()
        valid = APICredential.objects.filter(is_valid=True).count()

        tests.append({
            'name': 'API Credentials',
            'status': 'pass' if count > 0 else 'fail',
            'message': f'Total: {count}, Valid: {valid}' if count > 0 else 'No credentials configured',
        })
    except Exception as e:
        tests.append({
            'name': 'API Credentials',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: Capital calculation
    try:
        from apps.accounts.models import BrokerAccount
        account = BrokerAccount.objects.filter(is_active=True).first()

        if account:
            available = account.get_available_capital()
            total_pnl = account.get_total_pnl()
            tests.append({
                'name': 'Capital Calculations',
                'status': 'pass',
                'message': f'Available: {available}, Total P&L: {total_pnl}',
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
    """Test LLM integration functionalities"""
    tests = []

    # Test 1: Ollama connectivity
    try:
        ollama_url = settings.OLLAMA_BASE_URL
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)

        if response.status_code == 200:
            models = response.json().get('models', [])
            tests.append({
                'name': 'Ollama Connection',
                'status': 'pass',
                'message': f'Connected. Found {len(models)} models',
            })
        else:
            tests.append({
                'name': 'Ollama Connection',
                'status': 'fail',
                'message': f'HTTP {response.status_code}',
            })
    except Exception as e:
        tests.append({
            'name': 'Ollama Connection',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 2: LLM validation records
    try:
        from apps.llm.models import LLMValidation
        count = LLMValidation.objects.count()
        recent = LLMValidation.objects.order_by('-created_at').first()

        tests.append({
            'name': 'LLM Validations',
            'status': 'pass',
            'message': f'Found {count} validations. Latest: {recent.symbol if recent else "None"}',
        })
    except Exception as e:
        tests.append({
            'name': 'LLM Validations',
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })

    # Test 3: LLM prompts
    try:
        from apps.llm.models import LLMPrompt
        count = LLMPrompt.objects.count()
        active = LLMPrompt.objects.filter(is_active=True).count()

        tests.append({
            'name': 'LLM Prompt Templates',
            'status': 'pass',
            'message': f'Total: {count}, Active: {active}',
        })
    except Exception as e:
        tests.append({
            'name': 'LLM Prompt Templates',
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
    """Test background task system"""
    tests = []

    # Test 1: Background task model access
    try:
        from background_task.models import Task
        pending = Task.objects.filter(locked_by__isnull=True).count()
        completed = Task.objects.filter(failed_at__isnull=True).exclude(locked_by__isnull=True).count()
        failed = Task.objects.filter(failed_at__isnull=False).count()

        tests.append({
            'name': 'Background Tasks',
            'status': 'pass',
            'message': f'Pending: {pending}, Completed: {completed}, Failed: {failed}',
        })
    except Exception as e:
        tests.append({
            'name': 'Background Tasks',
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
