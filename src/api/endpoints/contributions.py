"""Contribution ingestion endpoint for model-specific submissions."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from src.api.dependencies import get_contribution_service
from src.api.schemas.contribution import (
    ContributionAcceptedResponse,
    ContributionLifecycleResponse,
    ContributionRequest,
)
from src.api.services.contribution_service import (
    ContributionConflictError,
    ContributionLifecycleUnavailableError,
    ContributionModelNotFoundError,
    ContributionPersistenceUnavailableError,
    ContributionService,
    ContributionValidationError,
)
from src.middleware.auth import require_auth

router = APIRouter(prefix="/api/v1/models", tags=["contributions"])
lifecycle_router = APIRouter(prefix="/api/v1/contributions", tags=["contributions"])


@router.post(
    "/{model_id}/contributions",
    response_model=ContributionAcceptedResponse,
    responses={
        400: {"description": "Contribution payload is semantically invalid"},
        401: {"description": "Authentication required"},
        404: {"description": "Registered model not found"},
        409: {"description": "Idempotency conflict"},
        413: {"description": "Request body too large"},
        503: {"description": "Contribution persistence unavailable"},
    },
)
async def submit_contribution(
    model_id: str,
    contribution: ContributionRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    auth: dict[str, Any] = Depends(require_auth),
    service: ContributionService = Depends(get_contribution_service),
) -> JSONResponse:
    """Accept a contribution batch for a registered model."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > service.max_body_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "error": "payload_too_large",
                        "maxBodyBytes": service.max_body_bytes,
                    },
                )
        except ValueError:
            pass

    try:
        accepted = await asyncio.to_thread(
            service.accept_contribution,
            model_id=model_id,
            request=contribution,
            idempotency_key=idempotency_key,
            auth=auth,
        )
    except ContributionModelNotFoundError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "model_not_found", "model_id": exc.model_id},
        )
    except ContributionValidationError as exc:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=exc.detail)
    except ContributionConflictError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "idempotency_conflict",
                "submissionId": exc.submission_id,
            },
        )
    except ContributionPersistenceUnavailableError as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "persistence_unavailable",
                "detail": str(exc),
            },
        )

    return JSONResponse(
        status_code=accepted.status_code,
        content=accepted.response.model_dump(by_alias=True),
    )


@lifecycle_router.get(
    "/{submission_id}/lifecycle",
    response_model=ContributionLifecycleResponse,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Lifecycle record not found"},
        503: {"description": "Lifecycle persistence unavailable"},
    },
)
async def get_contribution_lifecycle(
    submission_id: str,
    auth: dict[str, Any] = Depends(require_auth),
    service: ContributionService = Depends(get_contribution_service),
) -> JSONResponse:
    """Return current processing lifecycle state for an accepted submission."""
    del auth

    try:
        lifecycle = await asyncio.to_thread(service.get_lifecycle_state, submission_id)
    except ContributionLifecycleUnavailableError as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "lifecycle_unavailable", "detail": str(exc)},
        )

    if lifecycle is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "lifecycle_not_found", "submission_id": submission_id},
        )

    response = ContributionLifecycleResponse(
        submission_id=lifecycle.submission_id,
        state=lifecycle.state,
        accepted_row_count=lifecycle.accepted_row_count,
        rejected_row_count=lifecycle.rejected_row_count,
        reason=lifecycle.reason,
        metadata=lifecycle.processing_metadata,
        training_run_id=lifecycle.training_run_id,
        evaluation_run_id=lifecycle.evaluation_run_id,
        created_at=lifecycle.created_at,
        updated_at=lifecycle.updated_at,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(by_alias=True, mode="json"),
    )
