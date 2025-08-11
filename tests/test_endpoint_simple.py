"""Simple test to verify endpoint authentication exclusions."""

from unittest.mock import Mock
from src.middleware.auth import APIKeyAuthMiddleware

def test_authentication_excluded_paths():
    """Test that all required paths are excluded from authentication."""
    # Create a mock app
    mock_app = Mock()
    middleware = APIKeyAuthMiddleware(app=mock_app)
    
    # These paths should be excluded from authentication
    required_exclusions = [
        "/health",
        "/ready",
        "/live", 
        "/version",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
        "/api/v1/dspy/health",
        "/api/health/mlflow"
    ]
    
    print("Current excluded paths:", middleware.excluded_paths)
    
    for path in required_exclusions:
        assert path in middleware.excluded_paths, f"{path} is not excluded from authentication"
    
    print("✅ All required paths are excluded from authentication")

if __name__ == "__main__":
    test_authentication_excluded_paths()