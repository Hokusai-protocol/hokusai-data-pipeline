"""Schemas for Hokusai contribution ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContributionMetadata(BaseModel):
    """Optional caller-provided metadata for a contribution batch."""

    model_config = ConfigDict(extra="allow")

    idempotency_key: str | None = None


class ContributionRequest(BaseModel):
    """Normalized contribution submission body accepted from Wavemill and hokusai-site."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, protected_namespaces=())

    model_id: str | None = Field(default=None, alias="modelId")
    benchmark_spec_id: str | None = Field(default=None, alias="benchmarkSpecId")
    rows: list[dict[str, Any]] = Field(..., min_length=1, max_length=10000)
    metadata: ContributionMetadata = Field(default_factory=ContributionMetadata)
    schema_version: str | None = Field(default=None, alias="schemaVersion")
    template_id: str | None = Field(default=None, alias="templateId")

    @field_validator("rows")
    @classmethod
    def validate_rows(
        cls: type[ContributionRequest], rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Reject non-object rows with a clear validation error."""
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise TypeError(f"rows[{index}] must be an object")
        return rows


class ContributionAcceptedResponse(BaseModel):
    """Response returned to contribution clients after acceptance or replay."""

    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    accepted: bool = True
    model_id: str = Field(..., alias="modelId")
    submission_id: str = Field(..., alias="submissionId")
    job_id: str | None = Field(default=None, alias="jobId")
    job_ids: list[str] = Field(default_factory=list, alias="jobIds")
    rows_accepted: int = Field(..., alias="rowsAccepted")
    submitted_rows: int = Field(..., alias="submittedRows")
    token_reward: int = Field(default=0, alias="tokenReward")
    idempotent_replay: bool = Field(default=False, alias="idempotentReplay")


class ContributionLifecycleResponse(BaseModel):
    """Current processing lifecycle state for a contribution submission."""

    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    submission_id: str = Field(..., alias="submission_id")
    state: str
    accepted_row_count: int
    rejected_row_count: int
    reason: str | None = None
    processing_metadata: dict[str, Any] | None = Field(default=None, alias="metadata")
    training_run_id: str | None = None
    evaluation_run_id: str | None = None
    created_at: datetime
    updated_at: datetime
