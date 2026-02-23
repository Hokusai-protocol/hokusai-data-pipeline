"""Evaluation API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Path, status

from src.api.dependencies import get_evaluation_service
from src.api.schemas.evaluations import (
    EvaluationManifestResponse,
    EvaluationRequest,
    EvaluationResponse,
    EvaluationStatusResponse,
)
from src.api.services.evaluation_service import EvaluationService
from src.middleware.auth import require_auth

router = APIRouter(prefix="/api/v1", tags=["evaluations"])


@router.post(
    "/models/{model_id}/evaluate",
    response_model=EvaluationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_evaluation(
    background_tasks: BackgroundTasks,
    request: EvaluationRequest,
    model_id: str = Path(..., min_length=1),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    service: EvaluationService = Depends(get_evaluation_service),
    _auth: dict = Depends(require_auth),
) -> EvaluationResponse:
    """Trigger an asynchronous evaluation run for a model."""
    response = service.create_evaluation(
        model_id=model_id,
        payload=request,
        idempotency_key=idempotency_key,
    )
    background_tasks.add_task(service.execute_evaluation_job, str(response.job_id))
    return response


@router.get(
    "/evaluations/{job_id}/status",
    response_model=EvaluationStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_evaluation_status(
    job_id: UUID,
    service: EvaluationService = Depends(get_evaluation_service),
    _auth: dict = Depends(require_auth),
) -> EvaluationStatusResponse:
    """Get asynchronous evaluation job status."""
    return service.get_status(str(job_id))


@router.get(
    "/evaluations/{job_id}/manifest",
    response_model=EvaluationManifestResponse,
    status_code=status.HTTP_200_OK,
)
async def get_evaluation_manifest(
    job_id: UUID,
    service: EvaluationService = Depends(get_evaluation_service),
    _auth: dict = Depends(require_auth),
) -> EvaluationManifestResponse:
    """Retrieve manifest for a completed evaluation job."""
    return service.get_manifest(str(job_id))
