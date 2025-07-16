"""Custom exceptions for Hokusai SDK."""


class HokusaiException(Exception):
    """Base exception for all Hokusai SDK errors."""
    pass


class MLflowConnectionError(HokusaiException):
    """Raised when unable to connect to MLflow server."""
    
    def __init__(self, message: str = None, tracking_uri: str = None):
        if message is None:
            message = "Failed to connect to MLflow server"
        
        if tracking_uri:
            message = f"{message} at {tracking_uri}"
            
        super().__init__(message)
        self.tracking_uri = tracking_uri


class MLflowAuthenticationError(HokusaiException):
    """Raised when MLflow authentication fails."""
    
    def __init__(self, message: str = None, status_code: int = None):
        if message is None:
            if status_code == 403:
                message = "MLflow authentication error (HTTP 403): Access forbidden"
            elif status_code == 401:
                message = "MLflow authentication error (HTTP 401): Invalid credentials"
            else:
                message = "MLflow authentication failed"
                
        super().__init__(message)
        self.status_code = status_code


class ModelNotFoundError(HokusaiException):
    """Raised when a requested model is not found."""
    
    def __init__(self, model_id: str = None, model_name: str = None, version: str = None):
        if model_id:
            message = f"Model not found: {model_id}"
        elif model_name and version:
            message = f"Model not found: {model_name} version {version}"
        elif model_name:
            message = f"Model not found: {model_name}"
        else:
            message = "Model not found"
            
        super().__init__(message)
        self.model_id = model_id
        self.model_name = model_name
        self.version = version


class MethodNotImplementedError(HokusaiException):
    """Raised when a method is not yet implemented."""
    
    def __init__(self, method_name: str = None, class_name: str = None):
        if method_name and class_name:
            message = f"Method {class_name}.{method_name}() is not implemented"
        elif method_name:
            message = f"Method {method_name}() is not implemented"
        else:
            message = "Method not implemented"
            
        super().__init__(message)
        self.method_name = method_name
        self.class_name = class_name


class InvalidParameterError(HokusaiException):
    """Raised when invalid parameters are provided."""
    
    def __init__(self, parameter_name: str = None, message: str = None):
        if message is None and parameter_name:
            message = f"Invalid parameter: {parameter_name}"
        elif message is None:
            message = "Invalid parameter"
            
        super().__init__(message)
        self.parameter_name = parameter_name


class ConfigurationError(HokusaiException):
    """Raised when configuration is invalid or missing."""
    
    def __init__(self, message: str = None, missing_key: str = None):
        if message is None and missing_key:
            message = f"Missing required configuration: {missing_key}"
        elif message is None:
            message = "Invalid configuration"
            
        super().__init__(message)
        self.missing_key = missing_key