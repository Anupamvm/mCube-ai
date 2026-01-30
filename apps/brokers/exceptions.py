"""
Custom exceptions for broker integrations
"""


class BreezeAuthenticationError(Exception):
    """
    Raised when Breeze API authentication fails or session expires.

    Attributes:
        message: Error message
        requires_login: If True, user needs to re-authenticate
        requires_otp: If True, OTP entry is needed (browser-based login)
        login_url: URL to redirect user for login
        original_error: Original exception that caused this error

    Usage:
        try:
            client = get_breeze_client()
        except BreezeAuthenticationError as e:
            if e.requires_login:
                return redirect(e.login_url)
    """
    def __init__(
        self,
        message="Breeze authentication failed. Please re-login.",
        original_error=None,
        requires_login: bool = False,
        requires_otp: bool = False,
        login_url: str = '/brokers/breeze/login/'
    ):
        self.message = message
        self.original_error = original_error
        self.requires_login = requires_login
        self.requires_otp = requires_otp
        self.login_url = login_url
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON responses."""
        return {
            'success': False,
            'auth_required': self.requires_login,
            'requires_otp': self.requires_otp,
            'login_url': self.login_url,
            'error': self.message
        }


class BreezeAPIError(Exception):
    """
    Raised when Breeze API returns an error response
    """
    def __init__(self, message="Breeze API error", status_code=None, response=None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)
