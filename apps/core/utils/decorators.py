"""
Common Decorators

Reusable decorators for cross-cutting concerns like error handling,
authentication, validation, and logging. Consolidates duplicate patterns
found across views and services.

This eliminates 40+ duplicate exception handling blocks in views.py
"""

import functools
import time
import logging
from typing import Callable, Any, Dict, Optional
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)


def handle_exceptions(view_func: Callable) -> Callable:
    """
    Decorator to handle exceptions in views and return standardized JSON error responses.

    Consolidates 40+ duplicate exception handling blocks found in views.py.
    Provides consistent error formatting and logging across all endpoints.

    Usage:
        @handle_exceptions
        def my_view(request):
            # Your view logic
            return JsonResponse({'success': True})

    Returns standardized error response:
        {
            'success': False,
            'error': 'Error message',
            'details': 'Additional details if available'
        }
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)

        except PermissionError as e:
            logger.warning(f"Permission denied in {view_func.__name__}: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'details': str(e)
            }, status=403)

        except ValueError as e:
            logger.warning(f"Invalid input in {view_func.__name__}: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Invalid input',
                'details': str(e)
            }, status=400)

        except Exception as e:
            logger.error(f"Error in {view_func.__name__}: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e),
                'view': view_func.__name__
            }, status=500)

    return wrapper


def require_broker_auth(broker_type: Optional[str] = None):
    """
    Decorator to ensure broker authentication before executing view.

    Consolidates 22+ duplicate authentication checks in views.py.

    Args:
        broker_type: Specific broker to check ('breeze', 'neo', or None for any)

    Usage:
        @require_broker_auth(broker_type='breeze')
        def place_order(request):
            # Order placement logic

    Returns error response if not authenticated:
        {
            'success': False,
            'auth_required': True,
            'message': 'Please login to your broker first',
            'broker': 'breeze'
        }
    """
    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from apps.brokers.models import BrokerSession

            try:
                # Check for active broker session
                session = BrokerSession.objects.filter(
                    user=request.user,
                    is_active=True
                ).first()

                # If specific broker required, verify it matches
                if broker_type and session:
                    if session.broker != broker_type.upper():
                        return JsonResponse({
                            'success': False,
                            'auth_required': True,
                            'message': f'Please login to {broker_type.upper()} broker',
                            'broker': broker_type.lower()
                        })

                # If no active session found
                if not session:
                    return JsonResponse({
                        'success': False,
                        'auth_required': True,
                        'message': 'Please login to your broker first',
                        'broker': broker_type.lower() if broker_type else 'any'
                    })

                # Store session in request for easy access in view
                request.broker_session = session

                return view_func(request, *args, **kwargs)

            except Exception as e:
                logger.error(f"Error checking broker auth in {view_func.__name__}: {e}")
                return JsonResponse({
                    'success': False,
                    'error': 'Authentication check failed',
                    'details': str(e)
                }, status=500)

        return wrapper
    return decorator


def validate_input(schema: Dict[str, Any]):
    """
    Decorator to validate request input against a schema.

    Args:
        schema: Dictionary defining expected fields and their types
            Example: {
                'symbol': {'type': str, 'required': True},
                'quantity': {'type': int, 'required': False, 'default': 1}
            }

    Usage:
        @validate_input({
            'symbol': {'type': str, 'required': True},
            'quantity': {'type': int, 'required': True, 'min': 1}
        })
        def place_order(request):
            # Access validated data
            data = request.validated_data

    Adds 'validated_data' attribute to request object.
    Returns error response if validation fails.
    """
    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            import json

            try:
                # Parse request body
                if request.method == 'POST':
                    if request.content_type == 'application/json':
                        data = json.loads(request.body)
                    else:
                        data = request.POST.dict()
                else:
                    data = request.GET.dict()

                validated = {}
                errors = []

                # Validate each field in schema
                for field_name, rules in schema.items():
                    field_type = rules.get('type')
                    required = rules.get('required', False)
                    default = rules.get('default')
                    min_val = rules.get('min')
                    max_val = rules.get('max')

                    value = data.get(field_name)

                    # Check required
                    if required and value is None:
                        errors.append(f"'{field_name}' is required")
                        continue

                    # Use default if not provided
                    if value is None:
                        validated[field_name] = default
                        continue

                    # Type conversion
                    try:
                        if field_type == int:
                            value = int(value)
                        elif field_type == float:
                            value = float(value)
                        elif field_type == bool:
                            value = value if isinstance(value, bool) else value.lower() in ('true', '1', 'yes')
                    except (ValueError, AttributeError):
                        errors.append(f"'{field_name}' must be of type {field_type.__name__}")
                        continue

                    # Range validation
                    if min_val is not None and value < min_val:
                        errors.append(f"'{field_name}' must be >= {min_val}")
                        continue
                    if max_val is not None and value > max_val:
                        errors.append(f"'{field_name}' must be <= {max_val}")
                        continue

                    validated[field_name] = value

                # Return errors if validation failed
                if errors:
                    return JsonResponse({
                        'success': False,
                        'error': 'Validation failed',
                        'validation_errors': errors
                    }, status=400)

                # Add validated data to request
                request.validated_data = validated

                return view_func(request, *args, **kwargs)

            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid JSON in request body'
                }, status=400)

            except Exception as e:
                logger.error(f"Validation error in {view_func.__name__}: {e}")
                return JsonResponse({
                    'success': False,
                    'error': 'Validation error',
                    'details': str(e)
                }, status=400)

        return wrapper
    return decorator


def log_execution_time(view_func: Callable) -> Callable:
    """
    Decorator to log execution time of view functions.

    Useful for performance monitoring and identifying slow endpoints.

    Usage:
        @log_execution_time
        def expensive_view(request):
            # Long running logic
            return JsonResponse({'success': True})

    Logs: "View 'expensive_view' executed in 2.34s"
    """
    @functools.wraps(view_func)
    def wrapper(*args, **kwargs):
        start_time = time.time()

        result = view_func(*args, **kwargs)

        execution_time = time.time() - start_time
        logger.info(f"View '{view_func.__name__}' executed in {execution_time:.2f}s")

        return result

    return wrapper


def require_post_method(view_func: Callable) -> Callable:
    """
    Decorator to ensure view only accepts POST requests.

    Usage:
        @require_post_method
        def submit_order(request):
            # POST logic only
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.method != 'POST':
            return JsonResponse({
                'success': False,
                'error': 'Method not allowed',
                'allowed_methods': ['POST']
            }, status=405)

        return view_func(request, *args, **kwargs)

    return wrapper


def cache_result(timeout: int = 300):
    """
    Decorator to cache view results for specified timeout.

    Args:
        timeout: Cache timeout in seconds (default: 300 = 5 minutes)

    Usage:
        @cache_result(timeout=60)  # Cache for 1 minute
        def get_market_data(request):
            # Expensive market data fetch
            return JsonResponse({'data': ...})

    Note: Requires Django cache framework to be configured
    """
    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from django.core.cache import cache

            # Generate cache key from view name and arguments
            cache_key = f"{view_func.__name__}:{str(args)}:{str(kwargs)}"

            # Try to get from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {view_func.__name__}")
                return cached_result

            # Execute view and cache result
            result = view_func(request, *args, **kwargs)
            cache.set(cache_key, result, timeout)

            return result

        return wrapper
    return decorator
