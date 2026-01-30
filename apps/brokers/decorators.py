"""
Breeze API Decorators

Decorators for consistent Breeze authentication error handling across views.

Usage:
    from apps.brokers.decorators import breeze_api_view, breeze_page_view

    # For API endpoints (returns JSON)
    @breeze_api_view
    def get_positions(request):
        client = get_authenticated_breeze_client()
        return JsonResponse({'positions': ...})

    # For page views (redirects to login)
    @breeze_page_view
    def positions_page(request):
        client = get_authenticated_breeze_client()
        return render(request, 'positions.html', {...})
"""

import logging
from functools import wraps
from urllib.parse import urlencode

from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib import messages

from apps.brokers.exceptions import BreezeAuthenticationError

logger = logging.getLogger(__name__)


def breeze_api_view(view_func):
    """
    Decorator for API views that use Breeze.

    Catches BreezeAuthenticationError and returns consistent JSON response
    with auth_required flag and login URL.

    Usage:
        @breeze_api_view
        def api_get_positions(request):
            from apps.brokers.services.breeze_session import get_authenticated_breeze_client
            client = get_authenticated_breeze_client()
            # ... use client
            return JsonResponse({'success': True, 'data': ...})

    On auth error, returns:
        {
            'success': False,
            'auth_required': True,
            'login_url': '/brokers/breeze/login/',
            'error': 'Session expired...'
        }
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except BreezeAuthenticationError as e:
            logger.warning(f"Breeze auth error in {view_func.__name__}: {e.message}")

            # Build login URL with redirect back to current page
            next_url = request.get_full_path()
            login_url = f"{e.login_url}?{urlencode({'next': next_url})}"

            return JsonResponse({
                'success': False,
                'auth_required': True,
                'requires_otp': e.requires_otp,
                'login_url': login_url,
                'error': e.message
            })
        except Exception as e:
            # Check if it's a session-related error we missed
            error_str = str(e).lower()
            if any(kw in error_str for kw in ['session', 'expired', 'authentication', 'unauthorized', 'login', 'token']):
                logger.warning(f"Caught session error in {view_func.__name__}: {e}")
                next_url = request.get_full_path()
                login_url = f"/brokers/breeze/login/?{urlencode({'next': next_url})}"

                return JsonResponse({
                    'success': False,
                    'auth_required': True,
                    'login_url': login_url,
                    'error': f'Breeze session expired: {e}'
                })
            raise

    return wrapper


def breeze_page_view(view_func):
    """
    Decorator for page views that use Breeze.

    Catches BreezeAuthenticationError and redirects to login page
    with 'next' parameter to return after login.

    Usage:
        @breeze_page_view
        def positions_page(request):
            from apps.brokers.services.breeze_session import get_authenticated_breeze_client
            client = get_authenticated_breeze_client()
            # ... use client
            return render(request, 'positions.html', {...})
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except BreezeAuthenticationError as e:
            logger.warning(f"Breeze auth error in {view_func.__name__}: {e.message}")

            # Add message for user
            messages.warning(request, f"Breeze session expired. Please re-authenticate. ({e.message})")

            # Redirect to login with return URL
            next_url = request.get_full_path()
            login_url = f"{e.login_url}?{urlencode({'next': next_url})}"

            return redirect(login_url)
        except Exception as e:
            # Check if it's a session-related error we missed
            error_str = str(e).lower()
            if any(kw in error_str for kw in ['session', 'expired', 'authentication', 'unauthorized', 'login', 'token']):
                logger.warning(f"Caught session error in {view_func.__name__}: {e}")

                messages.warning(request, f"Breeze session expired. Please re-authenticate.")

                next_url = request.get_full_path()
                login_url = f"/brokers/breeze/login/?{urlencode({'next': next_url})}"

                return redirect(login_url)
            raise

    return wrapper


def handle_breeze_auth_error(request, error: Exception, is_ajax: bool = None) -> JsonResponse:
    """
    Utility function to handle Breeze authentication errors.

    Can be called directly in views that don't use decorators.

    Args:
        request: Django request object
        error: The exception that was raised
        is_ajax: If True, return JSON. If False, redirect. If None, auto-detect.

    Returns:
        JsonResponse or HttpResponseRedirect

    Usage:
        try:
            client = get_authenticated_breeze_client()
        except BreezeAuthenticationError as e:
            return handle_breeze_auth_error(request, e)
    """
    if is_ajax is None:
        # Auto-detect based on request headers
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('Accept', '')
        )

    next_url = request.get_full_path()
    login_url = '/brokers/breeze/login/'

    if isinstance(error, BreezeAuthenticationError):
        login_url = error.login_url
        message = error.message
        requires_otp = error.requires_otp
    else:
        message = str(error)
        requires_otp = True  # Assume OTP needed for unknown errors

    full_login_url = f"{login_url}?{urlencode({'next': next_url})}"

    if is_ajax:
        return JsonResponse({
            'success': False,
            'auth_required': True,
            'requires_otp': requires_otp,
            'login_url': full_login_url,
            'error': message
        })
    else:
        messages.warning(request, f"Breeze session expired. Please re-authenticate.")
        return redirect(full_login_url)
