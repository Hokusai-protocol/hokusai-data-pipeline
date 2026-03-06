"""Benchmark specification CRUD API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from src.api.dependencies import get_audit_logger, get_benchmark_spec_service
from src.api.schemas.benchmark_spec import (
    BenchmarkSpecCreate,
    BenchmarkSpecListResponse,
    BenchmarkSpecResponse,
    BenchmarkSpecUpdate,
)
from src.api.services.governance.audit_logger import AuditLogger
from src.api.services.governance.benchmark_specs import (
    BenchmarkSpecConflictError,
    BenchmarkSpecService,
)
from src.middleware.auth import require_auth

router = APIRouter(prefix="/api/v1/benchmarks", tags=["benchmarks"])


def _schema_to_model_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Map Pydantic schema field names to SQLAlchemy model field names."""
    mapped: dict[str, Any] = {}
    field_map = {
        "dataset_reference": "dataset_id",
        "input_columns": "input_schema",
        "target_column": "output_schema",
        "metadata": "tiebreak_rules",
    }
    for schema_key, model_key in field_map.items():
        if schema_key in data and data[schema_key] is not None:
            if schema_key == "input_columns":
                mapped[model_key] = {"columns": data[schema_key]}
            elif schema_key == "target_column":
                mapped[model_key] = {"target_column": data[schema_key]}
            else:
                mapped[model_key] = data[schema_key]
    for field in [
        "model_id",
        "provider",
        "eval_split",
        "metric_name",
        "metric_direction",
        "dataset_version",
    ]:
        if field in data and data[field] is not None:
            mapped[field] = data[field]
    return mapped


def _model_to_response(data: dict[str, Any]) -> dict[str, Any]:
    """Map service dict (model field names) to response schema field names."""
    input_schema = data.get("input_schema") or {}
    output_schema = data.get("output_schema") or {}
    return {
        "spec_id": data["spec_id"],
        "model_id": data["model_id"],
        "provider": data.get("provider", "hokusai"),
        "dataset_reference": data.get("dataset_id", ""),
        "eval_split": data.get("eval_split", ""),
        "target_column": output_schema.get("target_column", ""),
        "input_columns": input_schema.get("columns", []),
        "metric_name": data.get("metric_name", ""),
        "metric_direction": data.get("metric_direction", ""),
        "dataset_version": data.get("dataset_version"),
        "metadata": data.get("tiebreak_rules"),
        "created_at": data.get("created_at"),
        "updated_at": None,
        "is_active": data.get("is_active", True),
    }


@router.post("", response_model=BenchmarkSpecResponse, status_code=status.HTTP_201_CREATED)
async def create_benchmark_spec(
    request: BenchmarkSpecCreate,
    service: BenchmarkSpecService = Depends(get_benchmark_spec_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Create a new benchmark specification."""
    data = request.model_dump()
    model_fields = _schema_to_model_fields(data)
    model_fields.setdefault("dataset_version", "latest")
    model_fields.setdefault("input_schema", {})
    model_fields.setdefault("output_schema", {})
    try:
        result = service.register_spec(**model_fields)
    except BenchmarkSpecConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_logger.log(
        action="benchmark_spec.created",
        resource_type="benchmark_spec",
        resource_id=result["spec_id"],
        user_id=_auth.get("user_id", "unknown"),
        outcome="success",
    )
    return _model_to_response(result)


@router.get("/{spec_id}", response_model=BenchmarkSpecResponse)
async def get_benchmark_spec(
    spec_id: str,
    service: BenchmarkSpecService = Depends(get_benchmark_spec_service),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Get a benchmark spec by ID."""
    spec = service.get_spec(spec_id)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BenchmarkSpec not found",
        )
    return _model_to_response(spec)


@router.get("", response_model=BenchmarkSpecListResponse)
async def list_benchmark_specs(
    model_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: BenchmarkSpecService = Depends(get_benchmark_spec_service),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """List benchmark specs, optionally filtered by model ID, with pagination."""
    items, total = service.list_specs_paginated(model_id=model_id, page=page, page_size=page_size)
    return {
        "items": [_model_to_response(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.put("/{spec_id}", response_model=BenchmarkSpecResponse)
async def update_benchmark_spec(
    spec_id: str,
    request: BenchmarkSpecUpdate,
    service: BenchmarkSpecService = Depends(get_benchmark_spec_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Update a benchmark spec (dataset replacement support)."""
    data = request.model_dump(exclude_unset=True)
    model_changes = _schema_to_model_fields(data)
    result = service.update_spec_fields(spec_id, model_changes)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BenchmarkSpec not found",
        )
    audit_logger.log(
        action="benchmark_spec.updated",
        resource_type="benchmark_spec",
        resource_id=spec_id,
        user_id=_auth.get("user_id", "unknown"),
        outcome="success",
    )
    return _model_to_response(result)


@router.delete("/{spec_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_benchmark_spec(
    spec_id: str,
    service: BenchmarkSpecService = Depends(get_benchmark_spec_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> None:
    """Delete a benchmark spec."""
    deleted = service.delete_spec(spec_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BenchmarkSpec not found",
        )
    audit_logger.log(
        action="benchmark_spec.deleted",
        resource_type="benchmark_spec",
        resource_id=spec_id,
        user_id=_auth.get("user_id", "unknown"),
        outcome="success",
    )
