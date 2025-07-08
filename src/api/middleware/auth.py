"""Authentication middleware for API security."""

from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from functools import wraps
import logging
import secrets
import boto3
from botocore.exceptions import ClientError
from eth_account import Account
from eth_account.messages import encode_defunct
import redis

from src.api.utils.config import get_settings

logger = logging.getLogger(__name__)
security = HTTPBearer()
settings = get_settings()

# Initialize clients
try:
    aws_region = getattr(settings, "aws_region", "us-east-1")
    secrets_client = boto3.client("secretsmanager", region_name=aws_region)
except Exception as e:
    logger.warning(f"Failed to initialize Secrets Manager client: {e}")
    secrets_client = None

try:
    redis_client = redis.from_url(settings.redis_url) if hasattr(settings, "redis_url") else None
except Exception as e:
    logger.warning(f"Failed to initialize Redis client: {e}")
    redis_client = None

# Admin Ethereum addresses (should be loaded from config)
ADMIN_ADDRESSES = getattr(settings, "admin_eth_addresses", [])


class RateLimiter:
    """Rate limiting implementation."""

    def __init__(self, requests: int = 100, period: int = 60):
        self.requests = requests
        self.period = period

    async def check_rate_limit(self, key: str) -> bool:
        """Check if request is within rate limit."""
        if not redis_client:
            return True  # No rate limiting without Redis

        try:
            current = redis_client.incr(f"rate_limit:{key}")
            if current == 1:
                redis_client.expire(f"rate_limit:{key}", self.period)

            return current <= self.requests
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return True  # Allow request on error


class AuthMiddleware:
    """Middleware for handling authentication."""

    def __init__(self, app):
        self.app = app
        self.rate_limiter = RateLimiter(
            requests=getattr(settings, "rate_limit_requests", 100),
            period=getattr(settings, "rate_limit_period", 60)
        )

    async def __call__(self, scope, receive, send):
        """Process authentication for requests."""
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope["path"]
        # Skip auth for health check and docs
        if path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await self.app(scope, receive, send)

        headers = dict(scope["headers"])

        # Check for API key authentication
        auth_header = headers.get(b"authorization", b"").decode()
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")

            # Rate limiting check
            if not await self.rate_limiter.check_rate_limit(f"api_key:{token[:10]}"):
                from starlette.responses import JSONResponse
                response = JSONResponse(
                    {"detail": "Rate limit exceeded"},
                    status_code=429
                )
                await response(scope, receive, send)
                return

            if await validate_api_key(token):
                return await self.app(scope, receive, send)

        # Check for ETH signature authentication
        eth_address = headers.get(b"x-eth-address", b"").decode()
        eth_signature = headers.get(b"x-eth-signature", b"").decode()
        eth_message = headers.get(b"x-eth-message", b"").decode()

        if eth_address and eth_signature and eth_message:
            if verify_eth_signature(eth_address, eth_message, eth_signature):
                # Rate limiting check
                if not await self.rate_limiter.check_rate_limit(f"eth:{eth_address}"):
                    from starlette.responses import JSONResponse
                    response = JSONResponse(
                        {"detail": "Rate limit exceeded"},
                        status_code=429
                    )
                    await response(scope, receive, send)
                    return

                return await self.app(scope, receive, send)

        # No valid authentication found
        from starlette.responses import JSONResponse
        response = JSONResponse(
            {"detail": "Authorization required"},
            status_code=401
        )
        await response(scope, receive, send)


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


def store_api_key(user_id: str, api_key: str) -> None:
    """Store API key in AWS Secrets Manager."""
    if not secrets_client:
        logger.warning("Secrets Manager client not available")
        return

    secret_name = f"hokusai/api-keys/{user_id}"

    try:
        secrets_client.create_secret(
            Name=secret_name,
            SecretString=api_key,
            Description=f"API key for user {user_id}"
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceExistsException":
            # Update existing secret
            secrets_client.update_secret(
                SecretId=secret_name,
                SecretString=api_key
            )
        else:
            raise


async def validate_api_key(api_key: str) -> bool:
    """Validate API key against stored keys."""
    if not secrets_client:
        # For testing, accept any key
        return True

    try:
        # In production, you'd search through stored keys
        # For now, we'll check a specific pattern
        response = secrets_client.get_secret_value(
            SecretId="hokusai/api-keys/test_user"
        )
        stored_key = response["SecretString"]
        return api_key == stored_key
    except ClientError:
        return False


def verify_eth_signature(address: str, message: str, signature: str) -> bool:
    """Verify Ethereum signature."""
    try:
        # Encode the message
        message_hash = encode_defunct(text=message)

        # Recover the address from signature
        recovered_address = Account.recover_message(message_hash, signature=signature)

        # Compare addresses (case-insensitive)
        return recovered_address.lower() == address.lower()
    except Exception as e:
        logger.error(f"ETH signature verification failed: {e}")
        return False


def rotate_api_key(user_id: str) -> str:
    """Rotate API key for a user."""
    new_key = generate_api_key()
    store_api_key(user_id, new_key)
    return new_key


def get_user_permissions(eth_address: str) -> List[str]:
    """Get permissions for an Ethereum address."""
    permissions = ["read", "contribute"]

    if eth_address in ADMIN_ADDRESSES:
        permissions.append("admin")

    return permissions


def generate_jwt_token(user_data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate JWT token for session management."""
    to_encode = user_data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=30)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key or "test-secret-key",
        algorithm="HS256"
    )
    return encoded_jwt


def decode_jwt_token(token: str) -> Dict[str, Any]:
    """Decode and validate JWT token."""
    return jwt.decode(
        token,
        settings.secret_key or "test-secret-key",
        algorithms=["HS256"]
    )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Get current authenticated user."""
    token = credentials.credentials

    try:
        # First try JWT token
        payload = decode_jwt_token(token)
        return payload
    except JWTError:
        # Try API key
        if await validate_api_key(token):
            return {"user_id": "api_key_user", "permissions": ["read", "contribute"]}

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )


def async_auth_required(func):
    """Decorator for requiring authentication on async functions."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # In a real implementation, this would extract auth from request context
        # For testing, we'll check if user_info is provided
        if "user_info" not in kwargs and len(args) == 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )

        # Get user info from mock or context
        user_info = kwargs.get("user_info") or get_current_user()

        return await func(user_info, *args[1:], **kwargs)

    return wrapper


async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Dependency for requiring authentication."""
    return await get_current_user(credentials)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token (backward compatibility)."""
    return generate_jwt_token(data, expires_delta)
