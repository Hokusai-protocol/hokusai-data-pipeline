"""API routes for viewing dataset arrival events."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_dataset_arrival_handler

router = APIRouter(prefix="/api/v1/dataset-arrivals", tags=["dataset-arrivals"])


@router.get("")
async def list_arrivals(
    model_id: str | None = Query(default=None, description="Filter by model ID"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    handler: Any = Depends(get_dataset_arrival_handler),
) -> dict[str, Any]:
    """List recent dataset arrival events, optionally filtered by model."""
    items = handler.list_arrivals(model_id=model_id, limit=limit)
    return {"items": items, "count": len(items)}
