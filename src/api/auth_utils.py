"""Authentication utility functions for service communication."""

import os
import uuid
from typing import Any, Optional


def get_auth_headers(request: Optional[Any] = None) -> dict[str, str]:
    """Get authentication headers for service calls.

    Args:
    ----
        request: Optional request object to extract headers from

    Returns:
    -------
        Dictionary of authentication headers

    """
    # Initialize headers with existing headers if available, otherwise empty dict
    if request and hasattr(request, "headers"):
        # Start with a copy of existing headers to preserve them
        headers = dict(request.headers) if hasattr(request.headers, "__iter__") else {}
        # Ensure we have the critical auth headers
        if "Authorization" not in headers and "Authorization" in request.headers:
            headers["Authorization"] = request.headers["Authorization"]
        if "X-User-ID" not in headers and "X-User-ID" in request.headers:
            headers["X-User-ID"] = request.headers["X-User-ID"]
    else:
        # Start with empty dict and add service account token
        headers: dict[str, str] = {}
        token = os.environ.get("SERVICE_AUTH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

    # Always add request ID for tracing
    headers["X-Request-ID"] = str(uuid.uuid4())

    return headers


def validate_token(auth_header: Optional[str]) -> Optional[str]:
    """Validate an authentication token format.

    Args:
    ----
        auth_header: Authorization header value

    Returns:
    -------
        Token if valid, None otherwise

    """
    if not auth_header:
        return None

    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]  # Remove 'Bearer ' prefix

    # Basic validation - check it looks like a JWT
    parts = token.split(".")
    if len(parts) != 3:
        return None

    return token


def get_user_from_token(token: str) -> Optional[dict[str, Any]]:
    """Extract user information from token.

    Args:
    ----
        token: JWT token

    Returns:
    -------
        User information dict or None

    """
    # In production, this would decode and validate the JWT
    # For now, return a mock user
    return {
        "user_id": "extracted-user-id",
        "email": "user@example.com",
        "permissions": ["read", "write"],
    }
