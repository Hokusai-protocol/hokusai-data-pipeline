"""Custom exceptions for Hokusai data validation."""


class ValidationError(Exception):
    """Base exception for validation errors."""
    pass


class UnsupportedFormatError(ValidationError):
    """Raised when file format is not supported."""
    pass


class SchemaValidationError(ValidationError):
    """Raised when schema validation fails."""
    pass


class PIIDetectionError(ValidationError):
    """Raised when PII detection fails."""
    pass


class HashGenerationError(ValidationError):
    """Raised when hash generation fails."""
    pass


class ManifestGenerationError(ValidationError):
    """Raised when manifest generation fails."""
    pass


class FileLoadError(ValidationError):
    """Raised when file loading fails."""
    pass