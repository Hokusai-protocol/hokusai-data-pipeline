"""Pydantic models for token mint hook input/output contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TokenMintRequest(BaseModel):
    """Input payload for a token mint request."""

    model_id: str = Field(..., min_length=1, description="Model identifier")
    token_id: str = Field(..., min_length=1, description="Token identifier")
    delta_value: float = Field(..., ge=0, description="Value delta used for reward minting")
    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        description="Optional idempotency key for deduplication in downstream mint service",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenMintResult(BaseModel):
    """Result payload returned by the token mint hook."""

    status: Literal["success", "failed", "skipped", "dry_run"]
    audit_ref: str = Field(..., min_length=1, description="Audit UUID for this mint invocation")
    timestamp: datetime
    error: str | None = None
