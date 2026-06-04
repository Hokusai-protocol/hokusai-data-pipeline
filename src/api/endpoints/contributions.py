"""Contribution ingestion endpoint for model-specific submissions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from src.api.dependencies import get_contribution_service
from src.api.schemas.contribution import ContributionAcceptedResponse, ContributionRequest
from src.api.services.contribution_service import (
    ContributionConflictError,
    ContributionModelNotFoundError,
    ContributionPersistenceUnavailableError,
    ContributionService,
    ContributionValidationError,
)
from src.middleware.auth import require_auth

router = APIRouter(prefix="/api/v1/models", tags=["contributions"])


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
        accepted = service.accept_contribution(
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
