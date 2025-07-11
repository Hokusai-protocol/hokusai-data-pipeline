"""Authentication exceptions for Hokusai SDK."""


class HokusaiAuthError(Exception):
    """Base authentication error."""
    pass


class AuthenticationError(HokusaiAuthError):
    """Invalid or missing API key."""
    pass


class AuthorizationError(HokusaiAuthError):
    """Valid key but insufficient permissions."""
    pass


class RateLimitError(HokusaiAuthError):
    """Rate limit exceeded."""
    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after