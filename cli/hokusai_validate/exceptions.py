"""Custom exceptions for Hokusai data validation."""


class ValidationError(Exception):
    """Base exception for validation errors."""



class UnsupportedFormatError(ValidationError):
    """Raised when file format is not supported."""



class SchemaValidationError(ValidationError):
    """Raised when schema validation fails."""



class PIIDetectionError(ValidationError):
    """Raised when PII detection fails."""



class HashGenerationError(ValidationError):
    """Raised when hash generation fails."""



class ManifestGenerationError(ValidationError):
    """Raised when manifest generation fails."""



class FileLoadError(ValidationError):
    """Raised when file loading fails."""

