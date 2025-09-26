"""Authentication middleware for API endpoints."""

from typing import Any

from fastapi import Header, HTTPException


async def require_auth(authorization: str = Header(None)) -> dict[str, Any]:
    """Require authentication for API endpoints.

    Args:
    ----
        authorization: Authorization header

    Returns:
    -------
        Dictionary with user information

    Raises:
    ------
        HTTPException: If authentication fails

    """
    if not authorization:
        raise HTTPException(status_code=401, detail={"error": "Missing authorization header"})

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"error": "Invalid authorization format"})

    token = authorization.replace("Bearer ", "")

    # In a real implementation, this would validate the token
    # For now, just check if it's not empty
    if not token:
        raise HTTPException(status_code=401, detail={"error": "Missing token"})

    # Return mock user info for testing
    return {"user_id": "test-user", "token": token}
