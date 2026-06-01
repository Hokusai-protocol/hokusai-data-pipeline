"""Contribution submission endpoint for Wavemill / Hokusai-site uploads.

Wavemill's contribution drain POSTs to ``/api/v1/models/{model_id}/contributions``
with ``{ rows, metadata }``. The hokusai-site Next.js route forwards a richer
envelope (``{ modelId, benchmarkSpecId, rows, schemaVersion?, templateId? }``)
to the same upstream path. This module owns that route, validates either
envelope, and returns a Wavemill/site-compatible accepted response.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ...middleware.auth import require_auth
from ..middleware.validation_logging import (
    classify_client_ip,
    get_or_generate_request_id,
)
from ..schemas.contribution_submission import (
    ContributionSubmissionRequest,
    ContributionSubmissionResponse,
    classify_row,
)
from .model_registry_entries import MODEL_CONFIGS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/models", tags=["contributions"])


def _resolve_model_id(model_id: str) -> None:
    """Reject unknown model IDs with the same 404 shape as model serving."""
    if model_id not in MODEL_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")


def _validate_body_model_id(route_model_id: str, body_model_id: int | None) -> None:
    """Ensure body modelId, when supplied, matches the route segment."""
    if body_model_id is None:
        return
    try:
        route_as_int = int(route_model_id)
    except (TypeError, ValueError) as exc:
        # Route model id is a non-integer registry key. Reject any mismatch.
        raise HTTPException(
            status_code=400,
            detail="Payload modelId must match route modelId",
        ) from exc
    if route_as_int != body_model_id:
        raise HTTPException(
            status_code=400,
            detail="Payload modelId must match route modelId",
        )


@router.post(
    "/{model_id}/contributions",
    status_code=202,
    response_model=ContributionSubmissionResponse,
    response_model_by_alias=True,
)
async def submit_contributions(
    model_id: str,
    payload: ContributionSubmissionRequest,
    http_request: Request,
    auth: dict[str, Any] = Depends(require_auth),
) -> JSONResponse:
    """Accept a Wavemill / hokusai-site contribution batch for a registered model.

    Returns 202 with ``{ status, submissionId, jobId, jobIds, submittedRows,
    modelId }`` plus optional ``idempotencyKey`` and ``rowSchemaCounts`` for
    observability. Wavemill treats any 2xx as accepted and consumes
    ``jobIds``/``jobId``/``submissionId`` from the response body.
    """
    request_id = get_or_generate_request_id(http_request)
    http_request.state.request_id = request_id

    _resolve_model_id(model_id)
    _validate_body_model_id(model_id, payload.model_id)

    submission_id = str(uuid4())
    job_id = submission_id
    idempotency_header = http_request.headers.get("Idempotency-Key")
    idempotency_key = idempotency_header or (
        payload.metadata.idempotency_key if payload.metadata else None
    )

    row_schema_counts = Counter(classify_row(row) for row in payload.rows)

    logger.info(
        "contribution_submission_accepted",
        extra={
            "event_type": "contribution_submission_accepted",
            "request_id": request_id,
            "submission_id": submission_id,
            "model_id": model_id,
            "row_count": len(payload.rows),
            "row_schema_counts": dict(row_schema_counts),
            "idempotency_key": idempotency_key,
            "benchmark_spec_id": payload.benchmark_spec_id,
            "envelope_schema_version": payload.schema_version,
            "template_id": payload.template_id,
            "api_key_id": auth.get("api_key_id"),
            "user_id": auth.get("user_id"),
            "client_ip_class": classify_client_ip(
                http_request.client.host if http_request.client else None
            ),
            "user_agent": (http_request.headers.get("user-agent") or "")[:200] or None,
        },
    )

    try:
        response_model_id = int(model_id)
    except ValueError:
        # Registry currently only uses integer-shaped keys; non-integer keys
        # would have been rejected upstream by _resolve_model_id if missing,
        # but fall back to the route string for forward compatibility.
        response_model_id = model_id  # type: ignore[assignment]

    response_model = ContributionSubmissionResponse(
        submission_id=submission_id,
        job_id=job_id,
        job_ids=[job_id],
        submitted_rows=len(payload.rows),
        model_id=response_model_id,
        idempotency_key=idempotency_key,
        row_schema_counts=dict(row_schema_counts),
    )

    return JSONResponse(
        status_code=202,
        content=response_model.model_dump(by_alias=True),
        headers={"X-Request-ID": request_id},
    )
