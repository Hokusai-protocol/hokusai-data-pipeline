"""Prediction API endpoints for deployed models."""

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...config.providers import ProviderConfigManager
from ...database.config import DatabaseConfig
from ...database.deployed_models import DeployedModelStatus, get_session
from ...services.deployment_service import DeploymentService
from ...services.providers.base_provider import ProviderConfig
from ..middleware.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


# Pydantic models for request/response
class PredictionRequest(BaseModel):
    """Request model for predictions."""

    inputs: dict[str, Any] = Field(..., description="Input data for the model")


class PredictionResponse(BaseModel):
    """Response model for predictions."""

    success: bool
    predictions: list[dict[str, Any]] = Field(default_factory=list)
    response_time_ms: int
    error_message: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelInfoResponse(BaseModel):
    """Response model for model information."""

    id: str
    model_id: str
    provider: str
    status: str
    endpoint_url: Optional[str] = None
    instance_type: str
    error_message: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ModelListResponse(BaseModel):
    """Response model for model list."""

    models: list[ModelInfoResponse]
    total: int


class ModelStatusResponse(BaseModel):
    """Response model for model status."""

    success: bool
    status: Optional[str] = None
    database_status: Optional[str] = None
    provider_status: Optional[str] = None
    error_message: Optional[str] = None


# Dependency functions
def get_deployment_service() -> DeploymentService:
    """Get deployment service instance."""
    config = DatabaseConfig.from_env()
    database_url = config.get_connection_string()
    db_session = get_session(database_url)
    return DeploymentService(db_session=db_session)


def get_provider_configs() -> dict[str, ProviderConfig]:
    """Get provider configurations from environment."""
    return ProviderConfigManager.get_all_configs()


@router.post(
    "/models/{deployed_model_id}/predict",
    response_model=PredictionResponse,
    summary="Make a prediction using a deployed model",
    description="Send input data to a deployed model and receive predictions",
)
async def predict(
    deployed_model_id: UUID,
    request: PredictionRequest,
    deployment_service: DeploymentService = Depends(get_deployment_service),
    provider_configs: dict[str, ProviderConfig] = Depends(get_provider_configs),
    auth: dict[str, Any] = Depends(require_auth),
) -> PredictionResponse:
    """Make a prediction using a deployed model.

    Args:
    ----
        deployed_model_id: UUID of the deployed model
        request: Prediction request with inputs
        deployment_service: Service for managing deployments
        provider_configs: Provider configurations
        auth: Authentication information

    Returns:
    -------
        Prediction response with results

    Raises:
    ------
        HTTPException: If prediction fails or model not found

    """
    try:
        result = await deployment_service.predict(
            deployed_model_id=str(deployed_model_id),
            inputs=request.inputs,
            provider_configs=provider_configs,
        )

        if not result["success"]:
            # Determine appropriate status code based on error
            if "not found" in result.get("error_message", "").lower():
                raise HTTPException(status_code=404, detail=result)
            else:
                raise HTTPException(status_code=400, detail=result)

        return PredictionResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in predict endpoint: {str(e)}")
        raise HTTPException(
            status_code=500, detail={"success": False, "error_message": "Internal server error"}
        )


@router.get(
    "/models/{deployed_model_id}",
    response_model=ModelInfoResponse,
    summary="Get information about a deployed model",
    description="Retrieve detailed information about a specific deployed model",
)
async def get_model_info(
    deployed_model_id: UUID,
    deployment_service: DeploymentService = Depends(get_deployment_service),
    auth: dict[str, Any] = Depends(require_auth),
) -> ModelInfoResponse:
    """Get information about a deployed model.

    Args:
    ----
        deployed_model_id: UUID of the deployed model
        deployment_service: Service for managing deployments
        auth: Authentication information

    Returns:
    -------
        Model information

    Raises:
    ------
        HTTPException: If model not found

    """
    try:
        model_info = deployment_service.get_deployed_model_info(str(deployed_model_id))

        if not model_info:
            raise HTTPException(status_code=404, detail={"error": "Model not found"})

        return ModelInfoResponse(**model_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_model_info endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail={"error": "Internal server error"})


@router.get(
    "/models",
    response_model=ModelListResponse,
    summary="List deployed models",
    description="Retrieve a list of all deployed models with optional filtering",
)
async def list_models(
    status: Optional[str] = Query(None, description="Filter by deployment status"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    deployment_service: DeploymentService = Depends(get_deployment_service),
    auth: dict[str, Any] = Depends(require_auth),
) -> ModelListResponse:
    """List deployed models.

    Args:
    ----
        status: Optional status filter
        provider: Optional provider filter
        deployment_service: Service for managing deployments
        auth: Authentication information

    Returns:
    -------
        List of deployed models

    """
    try:
        # Convert status string to enum if provided
        status_filter = None
        if status:
            try:
                status_filter = DeployedModelStatus(status.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail={"error": f"Invalid status: {status}"})

        models = deployment_service.list_deployed_models(status=status_filter, provider=provider)

        model_responses = [ModelInfoResponse(**model) for model in models]

        return ModelListResponse(models=model_responses, total=len(model_responses))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in list_models endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail={"error": "Internal server error"})


@router.get(
    "/models/{deployed_model_id}/status",
    response_model=ModelStatusResponse,
    summary="Get deployment status of a model",
    description="Check the current deployment status of a model across database and provider",
)
async def get_model_status(
    deployed_model_id: UUID,
    deployment_service: DeploymentService = Depends(get_deployment_service),
    provider_configs: dict[str, ProviderConfig] = Depends(get_provider_configs),
    auth: dict[str, Any] = Depends(require_auth),
) -> ModelStatusResponse:
    """Get deployment status of a model.

    Args:
    ----
        deployed_model_id: UUID of the deployed model
        deployment_service: Service for managing deployments
        provider_configs: Provider configurations
        auth: Authentication information

    Returns:
    -------
        Model status information

    Raises:
    ------
        HTTPException: If model not found or status check fails

    """
    try:
        result = await deployment_service.get_deployment_status(
            deployed_model_id=str(deployed_model_id), provider_configs=provider_configs
        )

        if not result["success"]:
            if "not found" in result.get("error_message", "").lower():
                raise HTTPException(status_code=404, detail=result)
            else:
                raise HTTPException(status_code=400, detail=result)

        return ModelStatusResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_model_status endpoint: {str(e)}")
        raise HTTPException(
            status_code=500, detail={"success": False, "error_message": "Internal server error"}
        )
