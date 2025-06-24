"""Authentication middleware for API security."""

from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import logging

from src.api.utils.config import get_settings

logger = logging.getLogger(__name__)
security = HTTPBearer()
settings = get_settings()


class AuthMiddleware:
    """Middleware for handling authentication."""
    
    async def __call__(self, request: Request, call_next):
        """Process authentication for requests."""
        # Skip auth for health check and docs
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # For now, just check for Authorization header
        # In production, implement proper JWT validation
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authentication"
            )
        
        response = await call_next(request)
        return response


async def require_auth(credentials: HTTPAuthorizationCredentials = security):
    """Dependency for requiring authentication."""
    token = credentials.credentials
    
    try:
        # In production, validate JWT token here
        # For now, just check if token exists
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        
        # Decode and validate token
        # payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        # return payload
        
        return {"user_id": "authenticated_user"}
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    
    # In production, use proper secret key
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm="HS256")
    return encoded_jwt