"""Custom exceptions for Hokusai ML Platform
"""


class HokusaiError(Exception):
    """Base exception for all Hokusai errors"""

    pass


class TokenNotFoundError(HokusaiError):
    """Raised when a token is not found in the database"""

    def __init__(self, token_id: str):
        self.token_id = token_id
        super().__init__(f"Token '{token_id}' not found in database")


class TokenInvalidStatusError(HokusaiError):
    """Raised when a token is not in a valid status for the operation"""

    def __init__(self, token_id: str, current_status: str, required_status: str):
        self.token_id = token_id
        self.current_status = current_status
        self.required_status = required_status
        super().__init__(
            f"Token '{token_id}' is in '{current_status}' status. "
            f"Required status: '{required_status}'"
        )


class ModelValidationError(HokusaiError):
    """Raised when model validation fails"""

    def __init__(self, message: str, model_path: str = None):
        self.model_path = model_path
        super().__init__(message)


class MetricValidationError(HokusaiError):
    """Raised when metric validation fails"""

    def __init__(self, metric_name: str, value: float = None, reason: str = None):
        self.metric_name = metric_name
        self.value = value
        message = f"Invalid metric '{metric_name}'"
        if value is not None:
            message += f" with value {value}"
        if reason:
            message += f": {reason}"
        super().__init__(message)


class DatabaseConnectionError(HokusaiError):
    """Raised when database connection fails"""

    def __init__(self, message: str, db_host: str = None, db_name: str = None):
        self.db_host = db_host
        self.db_name = db_name
        super().__init__(message)


class MLflowError(HokusaiError):
    """Raised when MLflow operations fail"""

    def __init__(self, operation: str, message: str):
        self.operation = operation
        super().__init__(f"MLflow {operation} failed: {message}")


class EventPublishError(HokusaiError):
    """Raised when event publishing fails"""

    def __init__(self, event_type: str, reason: str):
        self.event_type = event_type
        super().__init__(f"Failed to publish event '{event_type}': {reason}")
