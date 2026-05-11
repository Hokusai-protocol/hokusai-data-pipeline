"""Benchmark specification CRUD API routes."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from src.api.dependencies import (
    get_audit_logger,
    get_benchmark_spec_service,
    get_dataset_validator,
    get_pii_detector,
)
from src.api.schemas.benchmark_spec import (
    BenchmarkSpecCreate,
    BenchmarkSpecListResponse,
    BenchmarkSpecResponse,
    BenchmarkSpecUpdate,
    DatasetUploadResponse,
    _is_remote_dataset_reference,
)
from src.api.services.dataset_validator import DatasetValidationError, DatasetValidator
from src.api.services.governance.audit_logger import AuditLogger
from src.api.services.governance.benchmark_specs import (
    BenchmarkSpecConflictError,
    BenchmarkSpecService,
    PIIFoundError,
)
from src.api.services.privacy.pii_detector import PIIDetector
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
        "baseline_value",
        "eval_spec",
    ]:
        if field in data and data[field] is not None:
            mapped[field] = data[field]
    return mapped


def _synthesize_legacy_eval_spec(data: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal eval spec from legacy scalar fields when eval_spec is absent."""
    tiebreak_rules = data.get("tiebreak_rules") or {}
    return {
        "primary_metric": {
            "name": data.get("metric_name", ""),
            "direction": data.get("metric_direction", "higher_is_better"),
            "threshold": data.get("baseline_value"),
        },
        "secondary_metrics": [],
        "guardrails": [],
        "min_examples": tiebreak_rules.get("min_examples"),
    }


def _model_to_response(data: dict[str, Any]) -> dict[str, Any]:
    """Map service dict (model field names) to response schema field names."""
    input_schema = data.get("input_schema") or {}
    output_schema = data.get("output_schema") or {}
    eval_spec = data.get("eval_spec") or None
    if eval_spec is None:
        eval_spec = _synthesize_legacy_eval_spec(data)
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
        "baseline_value": data.get("baseline_value"),
        "eval_spec": eval_spec,
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
    if not _is_remote_dataset_reference(data.get("dataset_reference")):
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


@router.delete("/{spec_id}")
async def delete_benchmark_spec(
    spec_id: str,
    service: BenchmarkSpecService = Depends(get_benchmark_spec_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> Response:
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
    return Response(status_code=status.HTTP_204_NO_CONTENT)


MAX_UPLOAD_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {".csv", ".parquet"}


@router.post(
    "/upload/{model_id}",
    response_model=DatasetUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_benchmark_dataset(
    model_id: str,
    file: UploadFile = File(...),
    eval_split: str = Form(default="test"),
    metric_name: str = Form(default="accuracy"),
    metric_direction: str = Form(default="higher_is_better"),
    target_column: str = Form(default="target"),
    input_columns: str = Form(default=""),
    allow_pii: bool = Form(default=False),
    service: BenchmarkSpecService = Depends(get_benchmark_spec_service),
    pii_detector: PIIDetector = Depends(get_pii_detector),
    dataset_validator: DatasetValidator = Depends(get_dataset_validator),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Upload a dataset file to S3 and create a BenchmarkSpec with provider=hokusai."""
    filename = file.filename or "upload.csv"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV and Parquet files are supported",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds maximum upload size",
        )

    # Parse input_columns from comma-separated string
    columns = [c.strip() for c in input_columns.split(",") if c.strip()] if input_columns else []

    spec_fields: dict[str, Any] = {
        "eval_split": eval_split,
        "metric_name": metric_name,
        "metric_direction": metric_direction,
        "input_schema": {"columns": columns},
        "output_schema": {"target_column": target_column},
    }

    try:
        result = service.upload_dataset(
            model_id=model_id,
            filename=filename,
            file_bytes=file_bytes,
            pii_detector=pii_detector,
            allow_pii=allow_pii,
            spec_fields=spec_fields,
            dataset_validator=dataset_validator,
        )
    except DatasetValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.result.to_dict(),
        ) from exc
    except PIIFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    audit_logger.log(
        action="benchmark_spec.dataset_uploaded",
        resource_type="benchmark_spec",
        resource_id=result["spec_id"],
        user_id=_auth.get("user_id", "unknown"),
        details={"s3_uri": result["s3_uri"], "filename": filename},
        outcome="success",
    )
    return result
