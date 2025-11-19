"""
Custom exceptions for broker integrations
"""


class BreezeAuthenticationError(Exception):
    """
    Raised when Breeze API authentication fails or session expires
    """
    def __init__(self, message="Breeze authentication failed. Please re-login.", original_error=None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class BreezeAPIError(Exception):
    """
    Raised when Breeze API returns an error response
    """
    def __init__(self, message="Breeze API error", status_code=None, response=None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)
