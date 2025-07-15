"""API endpoints for authentication and API key management."""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, validator

from src.auth.api_key_service import (
    APIKeyService,
    APIKeyNotFoundError,
    APIKeyValidationError,
)
from src.database.connection import DatabaseConnection
from src.database.operations import APIKeyDatabaseOperations


# Pydantic models for API requests/responses
class CreateAPIKeyRequest(BaseModel):
    """Request model for creating an API key."""
    name: str = Field(..., min_length=1, max_length=100)
    environment: str = Field(default="production", pattern="^(production|test|development)$")
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)
    rate_limit_per_hour: int = Field(default=1000, ge=1, le=100000)
    allowed_ips: Optional[List[str]] = Field(default=None, max_items=20)
    
    @validator('name')
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()
    
    @validator('allowed_ips')
    def validate_ips(cls, v):
        if v:
            # Basic IP validation
            import re
            ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
            for ip in v:
                if not ip_pattern.match(ip):
                    raise ValueError(f'Invalid IP address: {ip}')
        return v


class CreateAPIKeyResponse(BaseModel):
    """Response model for API key creation."""
    key: str
    key_id: str
    name: str
    created_at: datetime
    expires_at: Optional[datetime]
    message: str = "Save this key securely. It will not be shown again."


class APIKeyInfo(BaseModel):
    """API key information (without the actual key)."""
    key_id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool
    expires_at: Optional[datetime]


class ListAPIKeysResponse(BaseModel):
    """Response model for listing API keys."""
    keys: List[APIKeyInfo]
    total: int


class APIKeyUsageStats(BaseModel):
    """API key usage statistics."""
    key_id: str
    total_requests: int
    requests_today: int
    requests_this_hour: int
    average_response_time_ms: float
    error_rate: float
    top_endpoints: List[dict]


# Create router
router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def get_api_key_service() -> APIKeyService:
    """Dependency to get API key service."""
    db_conn = DatabaseConnection()
    db_ops = APIKeyDatabaseOperations(db_conn)
    return APIKeyService(db_ops)


def get_current_user(request: Request) -> str:
    """Get current user from request state."""
    if not hasattr(request.state, "user_id"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request.state.user_id


@router.post("/keys", response_model=CreateAPIKeyResponse, status_code=201)
async def create_api_key(
    request: CreateAPIKeyRequest,
    user_id: str = Depends(get_current_user),
    service: APIKeyService = Depends(get_api_key_service)
):
    """Create a new API key."""
    try:
        # Calculate expiration if specified
        expires_at = None
        if request.expires_in_days:
            expires_at = datetime.now() + timedelta(days=request.expires_in_days)
        
        # Generate API key
        api_key = service.generate_api_key(
            user_id=user_id,
            key_name=request.name,
            environment=request.environment,
            expires_at=expires_at,
            rate_limit_per_hour=request.rate_limit_per_hour,
            allowed_ips=request.allowed_ips
        )
        
        return CreateAPIKeyResponse(
            key=api_key.key,
            key_id=api_key.key_id,
            name=api_key.name,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create API key: {str(e)}")


@router.get("/keys", response_model=ListAPIKeysResponse)
async def list_api_keys(
    active_only: bool = False,
    user_id: str = Depends(get_current_user),
    service: APIKeyService = Depends(get_api_key_service)
):
    """List API keys for the current user."""
    try:
        keys = service.list_api_keys(user_id, active_only=active_only)
        
        return ListAPIKeysResponse(
            keys=[
                APIKeyInfo(
                    key_id=key.key_id,
                    name=key.name,
                    key_prefix=key.key_prefix,
                    created_at=key.created_at,
                    last_used_at=key.last_used_at,
                    is_active=key.is_active,
                    expires_at=key.expires_at
                )
                for key in keys
            ],
            total=len(keys)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list API keys: {str(e)}")


@router.delete("/keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    user_id: str = Depends(get_current_user),
    service: APIKeyService = Depends(get_api_key_service)
):
    """Revoke an API key."""
    try:
        service.revoke_api_key(user_id, key_id)
        return {"message": "API key revoked successfully"}
        
    except APIKeyNotFoundError:
        raise HTTPException(status_code=404, detail="API key not found")
    except APIKeyValidationError:
        raise HTTPException(status_code=403, detail="Not authorized to revoke this key")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to revoke API key: {str(e)}")


@router.post("/keys/{key_id}/rotate", response_model=CreateAPIKeyResponse)
async def rotate_api_key(
    key_id: str,
    user_id: str = Depends(get_current_user),
    service: APIKeyService = Depends(get_api_key_service)
):
    """Rotate an API key (revoke old, create new with same settings)."""
    try:
        api_key = service.rotate_api_key(user_id, key_id)
        
        return CreateAPIKeyResponse(
            key=api_key.key,
            key_id=api_key.key_id,
            name=api_key.name,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
            message="Key rotated successfully. Save the new key securely."
        )
        
    except APIKeyNotFoundError:
        raise HTTPException(status_code=404, detail="API key not found")
    except APIKeyValidationError:
        raise HTTPException(status_code=403, detail="Not authorized to rotate this key")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rotate API key: {str(e)}")


@router.get("/keys/{key_id}/usage", response_model=APIKeyUsageStats)
async def get_api_key_usage(
    key_id: str,
    hours: int = 24,
    user_id: str = Depends(get_current_user),
    service: APIKeyService = Depends(get_api_key_service)
):
    """Get usage statistics for an API key."""
    try:
        # Verify ownership
        key_data = service.db.get_api_key(key_id)
        if not key_data or key_data["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="API key not found")
        
        # Get usage stats
        stats = service.db.get_usage_stats(key_id, hours)
        
        # Get top endpoints (would require additional query)
        top_endpoints = []  # TODO: Implement endpoint tracking
        
        # Calculate hourly and daily stats
        hourly_stats = service.db.get_usage_stats(key_id, 1)
        daily_stats = service.db.get_usage_stats(key_id, 24)
        
        return APIKeyUsageStats(
            key_id=key_id,
            total_requests=stats["total_requests"],
            requests_today=daily_stats["total_requests"],
            requests_this_hour=hourly_stats["total_requests"],
            average_response_time_ms=stats["avg_response_time"],
            error_rate=stats["error_rate"],
            top_endpoints=top_endpoints
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get usage stats: {str(e)}")