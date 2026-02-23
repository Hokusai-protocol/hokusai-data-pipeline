"""Internal endpoint for deferred inference outcome ingestion."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import get_contributor_logger
from src.api.schemas.inference_log import OutcomeSubmission, OutcomeSubmissionResponse
from src.api.services.contributor_logger import (
    ContributorLogger,
    InferenceLogNotFoundError,
    InferenceLogOwnershipError,
)
from src.middleware.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["outcomes"])


@router.post("/outcomes", response_model=OutcomeSubmissionResponse)
async def submit_outcome(
    submission: OutcomeSubmission,
    auth: dict[str, Any] = Depends(require_auth),
    contributor_logger: ContributorLogger = Depends(get_contributor_logger),
) -> OutcomeSubmissionResponse:
    """Record deferred outcome values for a previously created inference log."""
    api_token_id = auth.get("api_key_id")
    if not api_token_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        contributor_logger.record_outcome(
            inference_log_id=submission.inference_log_id,
            api_token_id=str(api_token_id),
            outcome_score=submission.outcome_score,
            outcome_type=submission.outcome_type,
        )
    except InferenceLogNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inference log not found",
        ) from exc
    except InferenceLogOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inference log access denied",
        ) from exc
    except Exception as exc:
        logger.error("Failed to record outcome for %s: %s", submission.inference_log_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record outcome",
        ) from exc

    return OutcomeSubmissionResponse(inference_log_id=submission.inference_log_id)
