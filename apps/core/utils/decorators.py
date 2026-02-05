"""
Common Decorators

Reusable decorators for cross-cutting concerns like error handling,
authentication, validation, and logging. Consolidates duplicate patterns
found across views and services.

This eliminates 40+ duplicate exception handling blocks in views.py
"""

import functools
import html as html_mod
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


# High-frequency interval tasks that should NOT send Telegram notifications
_SILENT_TASK_KEYS = frozenset({
    'monitor-all-positions',
    'update-position-pnl',
    'check-exit-conditions',
    'check-risk-limits-all-accounts',
    'monitor-circuit-breakers',
})

# Categories that get Telegram lifecycle notifications (started / success / failed)
_NOTIFIED_CATEGORIES = frozenset({'data', 'strategies', 'transactions', 'monitoring', 'risk', 'reports'})

# Category display labels for Telegram messages
_CATEGORY_LABELS = {
    'data': 'Market Data',
    'strategies': 'Strategy',
    'transactions': 'Transactions',
    'monitoring': 'Monitoring',
    'risk': 'Risk',
    'reports': 'Reports',
}


def _get_task_display_name(task_key):
    """Return the human-readable display name for a task key."""
    from apps.core.task_config import TASK_DEFAULT_CONFIG
    config = TASK_DEFAULT_CONFIG.get(task_key, {})
    return config.get('display_name', task_key.replace('-', ' ').title())


def _get_task_category(task_key):
    """Return the category string for a task key, or '' if unknown."""
    from apps.core.task_config import TASK_DEFAULT_CONFIG
    config = TASK_DEFAULT_CONFIG.get(task_key, {})
    return config.get('category', '')


def _notify_task_started(task_key):
    """Send a compact Telegram message when a task starts.

    Returns the message_id so _notify_task_completion can edit the same message.
    Skips silent/high-frequency tasks and categories not in _NOTIFIED_CATEGORIES.
    """
    try:
        if task_key in _SILENT_TASK_KEYS:
            return None
        category = _get_task_category(task_key)
        if category not in _NOTIFIED_CATEGORIES:
            return None

        from apps.alerts.services.telegram_client import get_telegram_client

        client = get_telegram_client()
        if not client.is_enabled():
            return None

        display_name = html_mod.escape(_get_task_display_name(task_key))
        cat_label = _CATEGORY_LABELS.get(category, category.title())
        msg = f"🔄 <b>{display_name}</b>  ·  {cat_label}"

        ok, msg_id = client.send_message(msg)
        if ok:
            return msg_id
        logger.warning(f"Telegram start notification failed for {task_key}: {msg_id}")
        return None
    except Exception:
        logger.warning(f"Failed to send start notification for {task_key}", exc_info=True)
        return None


def _format_result_details(result):
    """Build expandable detail lines from a task result dict."""
    lines = []
    if not isinstance(result, dict):
        return lines
    for k, v in result.items():
        if k in ('status', 'success'):
            continue
        label = k.replace('_', ' ').title()
        if isinstance(v, dict):
            parts = [f"{sk}={sv}" for sk, sv in v.items()]
            lines.append(f"{label}: {', '.join(parts)}")
        elif isinstance(v, list):
            lines.append(f"{label}: {len(v)} items")
        elif isinstance(v, (str, int, float)):
            lines.append(f"{label}: {v}")
    return lines


def _fetch_bklog_steps(celery_task_id):
    """Query BkLog for step-by-step entries for a task execution.

    Returns (steps_list, warnings_count, errors_count).
    """
    if not celery_task_id:
        return [], 0, 0
    try:
        from apps.core.models import BkLog
        from django.utils import timezone

        entries = BkLog.objects.filter(task_id=celery_task_id).order_by('timestamp')
        steps = []
        warnings = errors = 0
        for e in entries:
            local_ts = timezone.localtime(e.timestamp)
            steps.append({
                'time': local_ts.strftime('%H:%M:%S'),
                'action': e.action,
                'message': e.message[:200],
                'level': e.level,
            })
            if e.level == 'warning':
                warnings += 1
            if e.level in ('error', 'critical'):
                errors += 1
        return steps, warnings, errors
    except Exception:
        return [], 0, 0


def _notify_task_completion(task_key, elapsed_seconds, result=None, error=None,
                            message_id=None, celery_task_id=''):
    """Edit the started message (or send a new one) with expandable completion details.

    Uses Telegram's <blockquote expandable> so the chat stays compact — the user
    sees just the task name and taps to expand timing / results / errors.

    When celery_task_id is provided, queries BkLog for step-by-step execution
    details to include in the expandable section.
    """
    try:
        if task_key in _SILENT_TASK_KEYS:
            return
        if _get_task_category(task_key) not in _NOTIFIED_CATEGORIES:
            return

        from apps.alerts.services.telegram_client import get_telegram_client

        client = get_telegram_client()
        if not client.is_enabled():
            return

        display_name = _get_task_display_name(task_key)

        # Fetch BkLog step details
        steps, warn_count, err_count = _fetch_bklog_steps(celery_task_id)

        esc = html_mod.escape  # escape <, >, & in dynamic content

        if error is not None:
            error_str = esc(str(error)[:500])
            header = f"❌ <b>{esc(display_name)}</b>"
            # Summary line
            summary_parts = [f"⏱ {elapsed_seconds:.1f}s"]
            if steps:
                summary_parts.append(f"{len(steps)} steps")
            if warn_count:
                summary_parts.append(f"⚠️ {warn_count}")
            if err_count:
                summary_parts.append(f"❌ {err_count}")
            summary = ' · '.join(summary_parts)

            detail_lines = [summary]
            if steps:
                detail_lines.append('─────────')
                for s in steps:
                    detail_lines.append(f"{s['time']} {esc(s['action'])} · {esc(s['message'])}")
            detail_lines.append(f"\nError: {error_str}")
            details = '\n'.join(detail_lines)
        else:
            header = f"✅ <b>{esc(display_name)}</b>"
            summary_parts = [f"⏱ {elapsed_seconds:.1f}s"]
            if steps:
                summary_parts.append(f"{len(steps)} steps")
            if warn_count:
                summary_parts.append(f"⚠️ {warn_count}")
            summary = ' · '.join(summary_parts)

            detail_lines = [summary]
            if steps:
                detail_lines.append('─────────')
                for s in steps:
                    detail_lines.append(f"{s['time']} {esc(s['action'])} · {esc(s['message'])}")
            else:
                # Fallback to result dict for tasks without TaskLogger
                detail_lines.extend(_format_result_details(result))
            details = '\n'.join(detail_lines)

        msg = f"{header}\n<blockquote expandable>{details}</blockquote>"

        # Try editing the original "started" message first
        if message_id:
            ok, detail = client.edit_message(int(message_id), msg)
            if ok:
                return
            logger.warning(f"Could not edit message {message_id} for {task_key}: {detail}")

        # Fallback: send as a new message
        ok, detail = client.send_message(msg)
        if not ok:
            logger.warning(f"Telegram completion notification failed for {task_key}: {detail}")
    except Exception:
        logger.warning(f"Failed to send completion notification for {task_key}", exc_info=True)


def task_enabled_guard(task_key):
    """
    Decorator to check if a Celery task is enabled before executing.

    Tasks are disabled by default and must be explicitly enabled via the
    background tasks UI. If a task is disabled, execution is skipped and
    a log message is recorded.

    Args:
        task_key: The task key from beat_schedule (e.g., 'fetch-trendlyne-data-daily'),
                  or a list of keys if the same function is used by multiple schedule entries.
                  If a list is provided, the task runs if ANY key is enabled.

    Usage:
        @shared_task(name='fetch_trendlyne_data', bind=True)
        @task_enabled_guard('morning-data-sync')
        def morning_data_sync(self):
            # Task logic - only runs if task is enabled
            pass

        # For tasks with multiple schedule entries:
        @shared_task(name='apps.strategies.tasks.batch_options_averaging', bind=True)
        @task_enabled_guard(['batch-options-averaging', 'batch-options-averaging-10am'])
        def batch_options_averaging(self):
            pass

    Returns:
        - If enabled: Executes the task normally
        - If disabled: Returns {'status': 'skipped', 'reason': 'Task disabled'}
    """
    task_keys = task_key if isinstance(task_key, (list, tuple)) else [task_key]
    primary_key = task_keys[0]

    def decorator(task_func: Callable) -> Callable:
        @functools.wraps(task_func)
        def wrapper(*args, **kwargs):
            # Allow manual "Run Now" to bypass the guard
            bypass = kwargs.pop('_bypass_guard', False)

            if not bypass:
                from apps.core.models import CeleryTaskState

                # Check if ANY of the task keys is enabled
                enabled = any(CeleryTaskState.is_task_enabled(k) for k in task_keys)
                if not enabled:
                    keys_str = ', '.join(task_keys)
                    logger.info(f"Task '{keys_str}' is disabled. Skipping execution.")
                    return {
                        'status': 'skipped',
                        'reason': 'Task disabled',
                        'task_key': primary_key
                    }

            # Extract Celery task_id for BkLog correlation (bound tasks)
            celery_task_id = ''
            if args and hasattr(args[0], 'request'):
                celery_task_id = getattr(args[0].request, 'id', '') or ''

            # Execute the task with timing
            start = time.time()
            msg_id = _notify_task_started(primary_key)
            try:
                result = task_func(*args, **kwargs)
                elapsed = time.time() - start
                _notify_task_completion(primary_key, elapsed, result=result,
                                       message_id=msg_id, celery_task_id=celery_task_id)
                return result
            except Exception as exc:
                elapsed = time.time() - start
                _notify_task_completion(primary_key, elapsed, error=str(exc),
                                       message_id=msg_id, celery_task_id=celery_task_id)
                raise

        return wrapper
    return decorator
