"""Evaluation schedule configuration CRUD API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from src.api.dependencies import get_audit_logger, get_evaluation_schedule_service
from src.api.schemas.evaluation_schedule import (
    EvaluationScheduleCreate,
    EvaluationScheduleResponse,
    EvaluationScheduleUpdate,
)
from src.api.services.governance.audit_logger import AuditLogger
from src.api.services.governance.evaluation_schedule import (
    EvaluationScheduleService,
    NoBenchmarkSpecError,
    ScheduleAlreadyExistsError,
)
from src.middleware.auth import require_auth

router = APIRouter(
    prefix="/api/v1/models/{model_id}/evaluation-schedule",
    tags=["evaluation-schedule"],
)


@router.post("", response_model=EvaluationScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_evaluation_schedule(
    model_id: str,
    request: EvaluationScheduleCreate,
    service: EvaluationScheduleService = Depends(get_evaluation_schedule_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Create an evaluation schedule for a model."""
    try:
        result = service.create_schedule(
            model_id=model_id,
            cron_expression=request.cron_expression,
            enabled=request.enabled,
        )
    except NoBenchmarkSpecError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ScheduleAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    audit_logger.log(
        action="evaluation_schedule.created",
        resource_type="evaluation_schedule",
        resource_id=result["id"],
        user_id=_auth.get("user_id", "unknown"),
        outcome="success",
    )
    return result


@router.get("", response_model=EvaluationScheduleResponse)
async def get_evaluation_schedule(
    model_id: str,
    service: EvaluationScheduleService = Depends(get_evaluation_schedule_service),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Get the evaluation schedule for a model."""
    schedule = service.get_schedule(model_id)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No evaluation schedule found for model {model_id}",
        )
    return schedule


@router.put("", response_model=EvaluationScheduleResponse)
async def update_evaluation_schedule(
    model_id: str,
    request: EvaluationScheduleUpdate,
    service: EvaluationScheduleService = Depends(get_evaluation_schedule_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Update the evaluation schedule for a model."""
    changes = request.model_dump(exclude_unset=True)
    result = service.update_schedule(model_id, changes)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No evaluation schedule found for model {model_id}",
        )
    audit_logger.log(
        action="evaluation_schedule.updated",
        resource_type="evaluation_schedule",
        resource_id=result["id"],
        user_id=_auth.get("user_id", "unknown"),
        outcome="success",
    )
    return result


@router.delete("")
async def delete_evaluation_schedule(
    model_id: str,
    service: EvaluationScheduleService = Depends(get_evaluation_schedule_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> Response:
    """Delete the evaluation schedule for a model."""
    deleted = service.delete_schedule(model_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No evaluation schedule found for model {model_id}",
        )
    audit_logger.log(
        action="evaluation_schedule.deleted",
        resource_type="evaluation_schedule",
        resource_id=model_id,
        user_id=_auth.get("user_id", "unknown"),
        outcome="success",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
