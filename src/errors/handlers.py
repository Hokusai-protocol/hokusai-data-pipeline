"""
Error handling and logging configuration for Hokusai ML Platform
"""
import logging
import sys
import traceback
from typing import Optional, Dict, Any
from datetime import datetime
import json


def configure_logging(level: str = "INFO", log_file: Optional[str] = None,
                     format_string: Optional[str] = None):
    """
    Configure logging for the application
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
        format_string: Custom format string for log messages
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        handlers=[]
    )
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(format_string))
    logging.getLogger().addHandler(console_handler)
    
    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(format_string))
        logging.getLogger().addHandler(file_handler)
        
    # Set specific loggers to appropriate levels
    logging.getLogger("hokusai").setLevel(getattr(logging, level.upper()))
    logging.getLogger("mlflow").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


class ErrorHandler:
    """Handles errors with proper logging and recovery strategies"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("hokusai.errors")
        self.error_counts: Dict[str, int] = {}
        self.last_errors: Dict[str, Any] = {}
        
    def handle_error(self, error: Exception, context: Optional[Dict[str, Any]] = None,
                    raise_error: bool = True, max_retries: int = 0) -> bool:
        """
        Handle an error with logging and optional retry logic
        
        Args:
            error: The exception that occurred
            context: Additional context information
            raise_error: Whether to re-raise the error after handling
            max_retries: Maximum number of retries for this error type
            
        Returns:
            True if error was handled successfully (or retries available), False otherwise
        """
        error_type = type(error).__name__
        error_key = f"{error_type}:{str(error)}"
        
        # Track error occurrences
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        self.last_errors[error_type] = {
            "error": str(error),
            "timestamp": datetime.utcnow().isoformat(),
            "context": context,
            "traceback": traceback.format_exc()
        }
        
        # Log the error
        self._log_error(error, context)
        
        # Check if we should retry
        if self.error_counts[error_key] <= max_retries:
            self.logger.info(
                f"Retry {self.error_counts[error_key]}/{max_retries} for {error_type}"
            )
            return True
            
        # Reset error count after max retries
        self.error_counts[error_key] = 0
        
        if raise_error:
            raise error
            
        return False
        
    def _log_error(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Log error with appropriate level and details"""
        error_type = type(error).__name__
        
        # Create error message
        error_msg = f"{error_type}: {str(error)}"
        
        if context:
            error_msg += f"\nContext: {json.dumps(context, indent=2, default=str)}"
            
        # Log with appropriate level based on error type
        if error_type in ["TokenNotFoundError", "MetricValidationError"]:
            self.logger.warning(error_msg)
        elif error_type in ["DatabaseConnectionError", "MLflowError"]:
            self.logger.error(error_msg, exc_info=True)
        else:
            self.logger.error(error_msg, exc_info=True)
            
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of errors encountered"""
        return {
            "error_counts": dict(self.error_counts),
            "last_errors": dict(self.last_errors),
            "total_errors": sum(self.error_counts.values())
        }
        
    def clear_error_history(self):
        """Clear error tracking history"""
        self.error_counts.clear()
        self.last_errors.clear()
        
    @staticmethod
    def create_user_friendly_message(error: Exception) -> str:
        """Create a user-friendly error message"""
        error_messages = {
            "TokenNotFoundError": "The specified token does not exist. Please check the token ID and try again.",
            "TokenInvalidStatusError": "The token is not in the correct status for this operation.",
            "ModelValidationError": "The model failed validation. Please check the model format and requirements.",
            "MetricValidationError": "The metric value is invalid. Please check the metric name and value range.",
            "DatabaseConnectionError": "Unable to connect to the database. Please check your connection settings.",
            "MLflowError": "An error occurred with MLflow. Please check your MLflow configuration.",
            "EventPublishError": "Failed to publish event. Please check your event configuration."
        }
        
        error_type = type(error).__name__
        default_msg = f"An error occurred: {str(error)}"
        
        return error_messages.get(error_type, default_msg)