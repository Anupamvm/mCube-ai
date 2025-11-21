"""
Custom Exception Classes

Defines domain-specific exceptions for better error handling and debugging.
Provides clear, meaningful exceptions instead of generic Python exceptions.

These exceptions can be caught and handled appropriately in views and services,
providing better error messages to users and more context for logging.
"""


class mCubeBaseException(Exception):
    """
    Base exception for all mCube-ai custom exceptions.

    All custom exceptions should inherit from this for easier exception handling.
    Provides a default_message attribute that can be overridden.
    """
    default_message = "An error occurred in mCube Trading System"

    def __init__(self, message: str = None, details: dict = None):
        """
        Initialize exception with message and optional details.

        Args:
            message: Error message (uses default_message if not provided)
            details: Dictionary of additional context/details
        """
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert exception to dictionary for JSON responses."""
        return {
            'error': self.message,
            'error_type': self.__class__.__name__,
            'details': self.details
        }


# ============================================================================
# Broker-related exceptions
# ============================================================================

class BrokerAuthenticationError(mCubeBaseException):
    """
    Raised when broker authentication fails or session is invalid.

    Examples:
        - Breeze/Neo login expired
        - Invalid credentials
        - Session not found
    """
    default_message = "Broker authentication failed"


class BrokerAPIError(mCubeBaseException):
    """
    Raised when broker API returns an error or unexpected response.

    Examples:
        - API timeout
        - Invalid response format
        - Rate limit exceeded
    """
    default_message = "Broker API error"


class OrderExecutionError(mCubeBaseException):
    """
    Raised when order placement or modification fails.

    Examples:
        - Insufficient margin
        - Invalid order parameters
        - Market closed
        - Order rejected by exchange
    """
    default_message = "Order execution failed"


# ============================================================================
# Data-related exceptions
# ============================================================================

class MarketDataError(mCubeBaseException):
    """
    Raised when market data fetch or processing fails.

    Examples:
        - Symbol not found
        - Invalid expiry date
        - Data source unavailable
    """
    default_message = "Market data error"


class InvalidContractError(mCubeBaseException):
    """
    Raised when contract details are invalid or not found.

    Examples:
        - Invalid futures symbol
        - Expired contract
        - Contract not found in database
    """
    default_message = "Invalid contract"


# ============================================================================
# Validation exceptions
# ============================================================================

class InvalidInputError(mCubeBaseException):
    """
    Raised when user input validation fails.

    Examples:
        - Negative quantity
        - Invalid strike price
        - Missing required parameters
    """
    default_message = "Invalid input provided"


class ValidationError(mCubeBaseException):
    """
    Raised when business logic validation fails.

    Examples:
        - Margin insufficient
        - Risk limits exceeded
        - Position limits violated
    """
    default_message = "Validation failed"


# ============================================================================
# Strategy/Algorithm exceptions
# ============================================================================

class AlgorithmError(mCubeBaseException):
    """
    Raised when trading algorithm execution fails.

    Examples:
        - Algorithm logic error
        - Missing required data
        - Configuration invalid
    """
    default_message = "Algorithm execution failed"


class PositionSizingError(mCubeBaseException):
    """
    Raised when position sizing calculation fails.

    Examples:
        - Cannot calculate margin
        - Lot size invalid
        - Risk calculation error
    """
    default_message = "Position sizing failed"


# ============================================================================
# Configuration exceptions
# ============================================================================

class ConfigurationError(mCubeBaseException):
    """
    Raised when system configuration is invalid or missing.

    Examples:
        - Missing environment variables
        - Invalid settings
        - Required service unavailable
    """
    default_message = "Configuration error"


# ============================================================================
# Database exceptions
# ============================================================================

class DatabaseError(mCubeBaseException):
    """
    Raised when database operations fail.

    Examples:
        - Connection failed
        - Query timeout
        - Constraint violation
    """
    default_message = "Database operation failed"


# ============================================================================
# External Service exceptions
# ============================================================================

class ExternalServiceError(mCubeBaseException):
    """
    Raised when external service (Trendlyne, etc.) fails.

    Examples:
        - API unavailable
        - Response timeout
        - Invalid response format
    """
    default_message = "External service error"


class LLMServiceError(mCubeBaseException):
    """
    Raised when LLM service (OpenAI, Claude, etc.) fails.

    Examples:
        - API rate limit
        - Invalid response
        - Service unavailable
    """
    default_message = "LLM service error"


# ============================================================================
# Permission exceptions
# ============================================================================

class InsufficientPermissionsError(mCubeBaseException):
    """
    Raised when user doesn't have required permissions.

    Examples:
        - Auto-trade disabled
        - Manual execution not allowed
        - Read-only access
    """
    default_message = "Insufficient permissions"


# ============================================================================
# Helper function for exception handling
# ============================================================================

def handle_exception_gracefully(exception: Exception) -> dict:
    """
    Convert any exception to a standardized error dictionary.

    Args:
        exception: Any Python exception

    Returns:
        Dictionary with error details suitable for JSON response

    Usage:
        try:
            risky_operation()
        except Exception as e:
            error_dict = handle_exception_gracefully(e)
            return JsonResponse(error_dict, status=500)
    """
    # If it's our custom exception, use its to_dict method
    if isinstance(exception, mCubeBaseException):
        return {
            'success': False,
            **exception.to_dict()
        }

    # For standard Python exceptions, create basic error dict
    return {
        'success': False,
        'error': str(exception),
        'error_type': exception.__class__.__name__
    }
