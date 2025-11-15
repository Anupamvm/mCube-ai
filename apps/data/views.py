"""
Data collection views for mCube Trading System

Handles Trendlyne data scraping and collection endpoints
"""

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .trendlyne import (
    init_driver_with_download,
    login_to_trendlyne,
    get_all_trendlyne_data
)


@login_required
@require_http_methods(["GET"])
def trendlyne_login_view(request):
    """
    Test Trendlyne login credentials

    GET /data/trendlyne/login/
    Returns success or failure message
    """
    try:
        driver = init_driver_with_download("trendlynedata/tmp")
        success = login_to_trendlyne(driver)
        driver.quit()

        if success:
            return JsonResponse({
                'status': 'success',
                'message': 'Trendlyne login successful'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Trendlyne login failed'
            }, status=401)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error during login: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def trendlyne_fetch_data_view(request):
    """
    Trigger full Trendlyne data collection pipeline

    POST /data/trendlyne/fetch/
    Downloads F&O data, market snapshot, and analyst consensus data
    """
    try:
        success = get_all_trendlyne_data()

        if success:
            return JsonResponse({
                'status': 'success',
                'message': 'All Trendlyne data fetched and saved to apps/data/tldata/'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Trendlyne data fetch failed. Check server logs.'
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error while fetching data: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def trendlyne_status_view(request):
    """
    Check Trendlyne integration status

    GET /data/trendlyne/status/
    Returns credential status and last data fetch info
    """
    from apps.core.models import CredentialStore
    import os
    from django.conf import settings

    try:
        creds = CredentialStore.objects.filter(service='trendlyne').first()
        data_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata')

        status = {
            'credentials_configured': bool(creds),
            'data_directory_exists': os.path.exists(data_dir),
        }

        if creds:
            status['credential_name'] = creds.name
            status['last_updated'] = creds.last_session_update.isoformat() if creds.last_session_update else None

        if os.path.exists(data_dir):
            files = os.listdir(data_dir)
            status['files_count'] = len(files)
            status['latest_files'] = files[:5] if files else []

        return JsonResponse(status)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
