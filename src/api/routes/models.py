"""Model-related API endpoints."""

from fastapi import APIRouter, HTTPException, Depends, status, Request
import logging
import re

from src.api.models import (
    ModelRegistration, ModelRegistrationResponse,
    ModelLineageResponse, ContributorImpactResponse,
    ErrorResponse
)
from src.services.model_registry import HokusaiModelRegistry
from src.services.performance_tracker import PerformanceTracker
from src.api.middleware.auth import require_auth
from src.api.utils.config import get_settings
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
settings = get_settings()

# Initialize services
registry = HokusaiModelRegistry(tracking_uri=settings.mlflow_tracking_uri)
tracker = PerformanceTracker()


@router.get(
    "/{model_id}/lineage",
    response_model=ModelLineageResponse,
    responses={404: {"model": ErrorResponse}}
)
@limiter.limit("100/minute")
async def get_model_lineage(request: Request, model_id: str, _=Depends(require_auth)):
    """Get complete improvement history of a model."""
    try:
        lineage = registry.get_model_lineage(model_id)
        
        return ModelLineageResponse(
            model_id=model_id,
            lineage=lineage,
            total_versions=len(lineage),
            latest_version=lineage[-1]["version"] if lineage else "0"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting model lineage: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve model lineage"
        )


@router.post(
    "/register",
    response_model=ModelRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}}
)
@limiter.limit("20/minute")
async def register_model(
    request: Request,
    registration: ModelRegistration,
    _=Depends(require_auth)
):
    """Register a new model from GTM-agent or other sources."""
    try:
        # For now, we'll assume it's a baseline model
        # In production, you'd determine this based on the request
        result = registry.register_baseline(
            model=registration.model_data,  # This would be loaded from the reference
            model_type=registration.model_type,
            metadata=registration.metadata
        )
        
        return ModelRegistrationResponse(
            model_id=result["model_id"],
            model_name=result["model_name"],
            version=result["version"],
            registration_timestamp=result["registration_timestamp"]
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error registering model: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register model"
        )


@router.get(
    "/contributors/{address}/impact",
    response_model=ContributorImpactResponse,
    responses={400: {"model": ErrorResponse}}
)
@limiter.limit("100/minute")
async def get_contributor_impact(request: Request, address: str, _=Depends(require_auth)):
    """Get total impact of a contributor across all models."""
    # Validate Ethereum address
    pattern = r"^0x[a-fA-F0-9]{40}$"
    if not re.match(pattern, address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Ethereum address format"
        )
    
    try:
        # This would query the tracking data
        # For now, returning mock data
        impact_data = tracker.get_contributor_impact(address)
        
        return ContributorImpactResponse(
            address=address,
            total_models_improved=impact_data.get("total_models_improved", 0),
            total_improvement_score=impact_data.get("total_improvement_score", 0.0),
            contributions=impact_data.get("contributions", []),
            first_contribution=impact_data.get("first_contribution"),
            last_contribution=impact_data.get("last_contribution")
        )
    except Exception as e:
        logger.error(f"Error getting contributor impact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve contributor impact"
        )