"""Benchmark specification API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.dependencies import get_benchmark_spec_service, get_current_user
from src.api.services.governance.benchmark_specs import (
    BenchmarkSpecConflictError,
    BenchmarkSpecService,
)

router = APIRouter(prefix="/api/v1/benchmarks", tags=["benchmarks"])


class BenchmarkSpecCreateRequest(BaseModel):
    """Payload for benchmark spec registration."""

    model_id: str
    dataset_id: str
    dataset_version: str
    eval_split: str
    metric_name: str
    metric_direction: str = Field(pattern="^(higher_is_better|lower_is_better)$")
    tiebreak_rules: dict[str, Any] | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    eval_container_digest: str | None = None
    is_active: bool = True


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_benchmark_spec(
    request: BenchmarkSpecCreateRequest,
    service: BenchmarkSpecService = Depends(get_benchmark_spec_service),
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Register a new immutable benchmark specification."""
    try:
        return service.register_spec(**request.model_dump())
    except BenchmarkSpecConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("")
async def list_benchmark_specs(
    model_id: str | None = Query(default=None),
    service: BenchmarkSpecService = Depends(get_benchmark_spec_service),
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List benchmark specs, optionally filtered by model id."""
    specs = service.list_specs(model_id=model_id)
    return {"count": len(specs), "items": specs}


@router.get("/{spec_id}")
async def get_benchmark_spec(
    spec_id: str,
    service: BenchmarkSpecService = Depends(get_benchmark_spec_service),
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get benchmark spec details by id."""
    spec = service.get_spec(spec_id)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benchmark spec not found",
        )
    return spec
