"""
Centralized error handling utilities for the mCube Trading System.

This module provides decorators and utilities to replace generic exception
handlers with specific, actionable error handling patterns.

Problem:
    The codebase has 594+ instances of generic `except Exception as e` which:
    - Makes debugging difficult (no stack traces)
    - Hides specific error types
    - Returns inconsistent error messages to users
    - Makes it hard to handle different errors differently

Solution:
    - Specific exception classes for different error scenarios
    - Decorators for common error handling patterns
    - Consistent error response format
    - Proper logging with context

Usage:
    @handle_api_errors
    def my_view(request):
        # Your code here
        # Errors are automatically caught and formatted

Classes:
    BrokerAPIException - Broker API call failures
    DataValidationException - Invalid input data
    AuthenticationException - Auth failures
    ConfigurationException - Missing/invalid config

Decorators:
    @handle_api_errors - For Django view functions
    @handle_broker_errors - For broker API calls
    @retry_on_failure - Retry failed operations
"""

import logging
import traceback
import functools
import time
from typing import Callable, Optional, Any, Dict
from django.http import JsonResponse
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class BrokerAPIException(Exception):
    """
    Exception for broker API call failures.

    Use this when broker APIs (Neo, Breeze, etc.) return errors.

    Attributes:
        broker: Broker name ('neo', 'breeze')
        operation: Operation being performed ('place_order', 'get_margin')
        original_error: Original exception or error message
    """
    def __init__(self, message: str, broker: str = '', operation: str = '', original_error: Any = None):
        self.message = message
        self.broker = broker
        self.operation = operation
        self.original_error = original_error
        super().__init__(self.message)

    def __str__(self):
        parts = [self.message]
        if self.broker:
            parts.append(f"Broker: {self.broker}")
        if self.operation:
            parts.append(f"Operation: {self.operation}")
        return " | ".join(parts)


class DataValidationException(Exception):
    """
    Exception for data validation failures.

    Use this when user input or API data fails validation.

    Attributes:
        field: Field that failed validation
        value: Invalid value
        reason: Why validation failed
    """
    def __init__(self, message: str, field: str = '', value: Any = None, reason: str = ''):
        self.message = message
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(self.message)


class AuthenticationException(Exception):
    """
    Exception for authentication failures.

    Use this when broker authentication fails or sessions expire.
    """
    pass


class ConfigurationException(Exception):
    """
    Exception for configuration errors.

    Use this when required settings/config are missing or invalid.
    """
    pass


class RateLimitException(Exception):
    """
    Exception for API rate limiting.

    Use this when broker APIs return rate limit errors (429).
    """
    pass


class PermissionDeniedException(Exception):
    """
    Exception for permission/authorization failures.

    Use this when operations are forbidden (403).
    """
    pass


# ============================================================================
# ERROR RESPONSE FORMATTING
# ============================================================================

def format_error_response(
    error: Exception,
    status_code: int = 500,
    include_traceback: bool = False,
    extra_context: Optional[Dict] = None
) -> Dict:
    """
    Format exception into consistent JSON error response.

    Args:
        error: Exception object
        status_code: HTTP status code (default: 500)
        include_traceback: Include full traceback (only in DEBUG mode)
        extra_context: Additional context to include in response

    Returns:
        dict: Formatted error response

    Example:
        >>> try:
        ...     raise BrokerAPIException("Order failed", broker="neo")
        ... except Exception as e:
        ...     response = format_error_response(e, status_code=400)
        >>> response['error']
        'Order failed'
    """
    error_data = {
        'error': str(error),
        'error_type': error.__class__.__name__,
        'success': False
    }

    # Add specific error details for custom exceptions
    if isinstance(error, BrokerAPIException):
        error_data['broker'] = error.broker
        error_data['operation'] = error.operation
        if error.original_error:
            error_data['original_error'] = str(error.original_error)

    elif isinstance(error, DataValidationException):
        error_data['field'] = error.field
        error_data['reason'] = error.reason
        if error.value is not None:
            error_data['invalid_value'] = str(error.value)

    # Add extra context if provided
    if extra_context:
        error_data.update(extra_context)

    # Add traceback in DEBUG mode only
    if include_traceback:
        try:
            from django.conf import settings
            if settings.DEBUG:
                error_data['traceback'] = traceback.format_exc()
        except:
            pass

    return error_data


# ============================================================================
# DECORATORS
# ============================================================================

def handle_api_errors(func: Callable) -> Callable:
    """
    Decorator for Django API views to handle errors consistently.

    This decorator:
    - Catches all exceptions
    - Logs them with context
    - Returns formatted JSON error responses
    - Handles specific exception types appropriately

    Usage:
        @handle_api_errors
        def my_view(request):
            # Your code here
            return JsonResponse({'success': True, 'data': ...})

    Example:
        @handle_api_errors
        def place_order_view(request):
            broker = request.POST.get('broker')
            if not broker:
                raise DataValidationException(
                    "Missing broker parameter",
                    field='broker',
                    reason='Required field not provided'
                )
            # ... rest of code
    """
    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        try:
            return func(request, *args, **kwargs)

        except DataValidationException as e:
            # User input validation errors - 400 Bad Request
            logger.warning(f"Validation error in {func.__name__}: {e}")
            response_data = format_error_response(e, status_code=400)
            return JsonResponse(response_data, status=400)

        except AuthenticationException as e:
            # Authentication failures - 401 Unauthorized
            logger.error(f"Authentication error in {func.__name__}: {e}")
            response_data = format_error_response(e, status_code=401)
            return JsonResponse(response_data, status=401)

        except BrokerAPIException as e:
            # Broker API errors - 502 Bad Gateway (external service issue)
            logger.error(f"Broker API error in {func.__name__}: {e}")
            logger.error(f"Broker: {e.broker}, Operation: {e.operation}")
            response_data = format_error_response(e, status_code=502)
            return JsonResponse(response_data, status=502)

        except ConfigurationException as e:
            # Configuration errors - 500 Internal Server Error
            logger.error(f"Configuration error in {func.__name__}: {e}")
            response_data = format_error_response(e, status_code=500)
            return JsonResponse(response_data, status=500)

        except RateLimitException as e:
            # Rate limiting - 429 Too Many Requests
            logger.warning(f"Rate limit exceeded in {func.__name__}: {e}")
            response_data = format_error_response(e, status_code=429)
            return JsonResponse(response_data, status=429)

        except PermissionDeniedException as e:
            # Permission denied - 403 Forbidden
            logger.warning(f"Permission denied in {func.__name__}: {e}")
            response_data = format_error_response(e, status_code=403)
            return JsonResponse(response_data, status=403)

        except ValidationError as e:
            # Django validation errors - 400 Bad Request
            logger.warning(f"Django validation error in {func.__name__}: {e}")
            response_data = {
                'error': str(e),
                'error_type': 'ValidationError',
                'success': False
            }
            return JsonResponse(response_data, status=400)

        except Exception as e:
            # Unexpected errors - 500 Internal Server Error
            logger.exception(f"Unexpected error in {func.__name__}: {e}")
            response_data = format_error_response(
                e,
                status_code=500,
                include_traceback=True,
                extra_context={'view': func.__name__}
            )
            return JsonResponse(response_data, status=500)

    return wrapper


def handle_broker_errors(broker_name: str = ''):
    """
    Decorator for broker API functions to handle errors consistently.

    This decorator:
    - Catches broker API exceptions
    - Logs them with broker context
    - Re-raises as BrokerAPIException for consistent handling

    Args:
        broker_name: Name of broker ('neo', 'breeze', etc.)

    Usage:
        @handle_broker_errors(broker_name='neo')
        def place_order(symbol, quantity):
            # Broker API calls here
            return result

    Example:
        @handle_broker_errors(broker_name='breeze')
        def get_margin():
            try:
                return breeze.get_funds()
            except Exception as e:
                # Will be wrapped in BrokerAPIException automatically
                raise
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)

            except BrokerAPIException:
                # Already wrapped, re-raise as-is
                raise

            except Exception as e:
                # Wrap in BrokerAPIException
                operation = func.__name__
                logger.error(f"Broker error in {operation}: {e}")

                raise BrokerAPIException(
                    message=f"Broker API call failed: {str(e)}",
                    broker=broker_name,
                    operation=operation,
                    original_error=e
                )

        return wrapper
    return decorator


def retry_on_failure(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff_multiplier: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator to retry failed operations with exponential backoff.

    Useful for transient failures like network errors, rate limits, etc.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        delay_seconds: Initial delay between retries (default: 1.0)
        backoff_multiplier: Multiply delay by this after each attempt (default: 2.0)
        exceptions: Tuple of exceptions to catch (default: all exceptions)

    Usage:
        @retry_on_failure(max_attempts=3, delay_seconds=2.0)
        def fetch_data_from_api():
            # Code that might fail transiently
            return api.get_data()

    Example:
        @retry_on_failure(max_attempts=5, delay_seconds=0.5, backoff_multiplier=1.5)
        def place_order(symbol, quantity):
            # Retry up to 5 times with increasing delays
            return broker.place_order(symbol, quantity)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 1
            current_delay = delay_seconds

            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    if attempt == max_attempts:
                        # Last attempt failed, raise the error
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise

                    # Log retry attempt
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )

                    # Wait before retry
                    time.sleep(current_delay)

                    # Increase delay for next attempt (exponential backoff)
                    current_delay *= backoff_multiplier
                    attempt += 1

        return wrapper
    return decorator


def safe_execute(func: Callable, default_return: Any = None, log_errors: bool = True) -> Any:
    """
    Safely execute a function and return default value on error.

    Useful for optional operations where failure shouldn't crash the app.

    Args:
        func: Function to execute
        default_return: Value to return if function fails (default: None)
        log_errors: Whether to log errors (default: True)

    Returns:
        Function result or default_return on error

    Example:
        >>> result = safe_execute(lambda: risky_operation(), default_return={})
        >>> # Returns {} if risky_operation() fails, otherwise returns actual result
    """
    try:
        return func()
    except Exception as e:
        if log_errors:
            logger.warning(f"safe_execute: {func.__name__ if hasattr(func, '__name__') else 'function'} failed: {e}")
        return default_return


# ============================================================================
# CONTEXT MANAGERS
# ============================================================================

class LogExecutionTime:
    """
    Context manager to log execution time of code blocks.

    Usage:
        with LogExecutionTime("Fetch option chain"):
            data = fetch_option_chain()
        # Logs: "Fetch option chain completed in 2.34s"
    """
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        logger.debug(f"Starting: {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time
        if exc_type is None:
            logger.info(f"{self.operation_name} completed in {elapsed:.2f}s")
        else:
            logger.error(f"{self.operation_name} failed after {elapsed:.2f}s: {exc_val}")
        return False  # Don't suppress exceptions
