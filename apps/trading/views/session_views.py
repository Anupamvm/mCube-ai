"""
Session Views - Broker Authentication Management

Handles broker session token updates for Breeze (ICICI) and Neo (Kotak).
These views are called when users re-authenticate with their brokers after
session expiry.

Refactored to use new decorators from apps.core.utils for cleaner code.

Extracted from apps/trading/views.py as part of refactoring.
"""

import json
import logging
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone

from apps.core.models import CredentialStore
from apps.core.utils import handle_exceptions, validate_input

logger = logging.getLogger(__name__)


@login_required
@require_POST
@handle_exceptions
def update_breeze_session(request):
    """
    Update Breeze (ICICI Direct) session token after user re-authentication.

    When a Breeze session expires, the frontend prompts the user to login again.
    After successful login, this endpoint updates the session token in the database.

    Request Body (JSON):
        {
            "session_token": "new_session_token_from_breeze"
        }

    Returns:
        JsonResponse: Success/failure status and message

    Responses:
        200 OK:
            {
                "success": True,
                "message": "Session token updated successfully"
            }

        400 Bad Request:
            {
                "success": False,
                "error": "Session token is required"
            }

        404 Not Found:
            {
                "success": False,
                "error": "Breeze credentials not found in database"
            }

    Note:
        This view uses the @handle_exceptions decorator which automatically
        catches and formats exceptions.
    """
    body = json.loads(request.body)
    session_token = body.get('session_token', '').strip()

    # Validate session token provided
    if not session_token:
        return JsonResponse({
            'success': False,
            'error': 'Session token is required'
        }, status=400)

    # Fetch Breeze credentials from database
    creds = CredentialStore.objects.filter(service='breeze').first()
    if not creds:
        return JsonResponse({
            'success': False,
            'error': 'Breeze credentials not found in database'
        }, status=404)

    # Update session token and timestamp
    creds.session_token = session_token
    creds.last_session_update = timezone.now()
    creds.save()

    logger.info(f"Breeze session token updated successfully by {request.user}")

    return JsonResponse({
        'success': True,
        'message': 'Session token updated successfully'
    })


@login_required
@require_POST
@handle_exceptions
def update_neo_session(request):
    """
    Update Neo (Kotak Securities) session token after user re-authentication.

    When a Neo session expires, the frontend prompts the user to login again.
    After successful login, this endpoint updates the session token in the database.

    Request Body (JSON):
        {
            "session_token": "new_session_token_from_neo"
        }

    Returns:
        JsonResponse: Success/failure status and message

    Responses:
        200 OK:
            {
                "success": True,
                "message": "Session token updated successfully"
            }

        400 Bad Request:
            {
                "success": False,
                "error": "Session token is required"
            }

        404 Not Found:
            {
                "success": False,
                "error": "Neo credentials not found in database"
            }

    Note:
        - Tries both 'kotak_neo' and 'neo' service names for compatibility
        - Uses @handle_exceptions decorator for automatic error handling
    """
    body = json.loads(request.body)
    session_token = body.get('session_token', '').strip()

    # Validate session token provided
    if not session_token:
        return JsonResponse({
            'success': False,
            'error': 'Session token is required'
        }, status=400)

    # Fetch Neo credentials from database (try both service names)
    creds = CredentialStore.objects.filter(service='kotak_neo').first()
    if not creds:
        # Try alternate service name for backward compatibility
        creds = CredentialStore.objects.filter(service='neo').first()

    if not creds:
        return JsonResponse({
            'success': False,
            'error': 'Neo credentials not found in database'
        }, status=404)

    # Update session token and timestamp
    creds.session_token = session_token
    creds.last_session_update = timezone.now()
    creds.save()

    logger.info(f"Neo session token updated successfully by {request.user}")

    return JsonResponse({
        'success': True,
        'message': 'Session token updated successfully'
    })
