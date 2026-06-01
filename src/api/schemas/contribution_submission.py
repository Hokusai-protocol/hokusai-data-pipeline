"""Schemas for Wavemill / Hokusai-site contribution submission payloads."""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

TECHNICAL_TASK_ROUTER_ROW_SCHEMA_VERSION = "technical_task_router_row/v1"

MAX_CONTRIBUTION_ROWS = 10_000

FORBIDDEN_ROW_KEYS = frozenset(
    {
        "prompt",
        "messages",
        "task_text",
        "raw_input",
        "eval_record",
        "originalprompt",
        "original_prompt",
        "description",
        "issue_body",
    }
)

ContributionScalar = Union[str, int, float, bool, None]  # noqa: UP007

CompletionResult = Literal["success", "failure"]


def _assert_no_forbidden_keys(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_ROW_KEYS:
                location = ".".join((*path, str(key)))
                raise ValueError(f"Forbidden field at {location}")
            _assert_no_forbidden_keys(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_forbidden_keys(item, (*path, str(index)))


class TechnicalTaskRouterSelectedModels(BaseModel):
    """Selected planner/coder/reviewer for a technical task router row."""

    model_config = ConfigDict(extra="allow")

    planner: str | None = None
    coder: str
    reviewer: str


class SubmitDataContributionRow(BaseModel):
    """Legacy submit-data row shape (no schema_version)."""

    model_config = ConfigDict(extra="allow")

    success_under_budget: bool
    inputs: dict[str, Any] | None = None
    actual_cost_usd: float | None = Field(default=None, ge=0)
    wall_clock_seconds: float | None = Field(default=None, ge=0)
    task_id: str | None = None
    harness: str | None = None


class TechnicalTaskRouterContributionRowV1(BaseModel):
    """Technical task router contribution row (schema_version v1)."""

    model_config = ConfigDict(extra="allow")

    schema_version: Literal["technical_task_router_row/v1"]
    task_descriptor: dict[str, Any]
    allowed_models: list[str]
    selected_models: TechnicalTaskRouterSelectedModels
    budget_usd: float | None = Field(default=None, ge=0)
    actual_cost_usd: float | None = Field(default=None, ge=0)
    wall_clock_seconds: float | None = Field(default=None, ge=0)
    success_under_budget: bool
    completion_result: CompletionResult
    scorer_ref: str | None = None
    observed_at: str
    task_id: str | None = None
    harness: str | None = None


class ContributionMetadata(BaseModel):
    """Optional metadata envelope sent alongside the rows."""

    model_config = ConfigDict(extra="allow")

    idempotency_key: str | None = Field(default=None, max_length=256)


class ContributionSubmissionRequest(BaseModel):
    """Request envelope accepted at POST /api/v1/models/{model_id}/contributions.

    Supports both the Wavemill envelope (``rows`` plus optional ``metadata``)
    and the hokusai-site envelope (``modelId``, ``benchmarkSpecId``, ``rows``,
    optional ``schemaVersion``/``templateId``). Either envelope is accepted and
    validated by the same route.
    """

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        protected_namespaces=(),
    )

    rows: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=MAX_CONTRIBUTION_ROWS,
    )
    metadata: ContributionMetadata | None = None

    model_id: int | None = Field(default=None, alias="modelId")
    benchmark_spec_id: str | None = Field(default=None, alias="benchmarkSpecId")
    schema_version: str | None = Field(default=None, alias="schemaVersion")
    template_id: str | None = Field(default=None, alias="templateId")

    @field_validator("rows")
    @classmethod
    def _check_forbidden_keys(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for index, row in enumerate(rows):
            try:
                _assert_no_forbidden_keys(row)
            except ValueError as exc:
                raise ValueError(f"rows[{index}]: {exc}") from exc
        return rows


class ContributionSubmissionResponse(BaseModel):
    """Response envelope returned for an accepted contribution submission."""

    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    status: Literal["accepted"] = "accepted"
    submission_id: str = Field(serialization_alias="submissionId")
    job_id: str = Field(serialization_alias="jobId")
    job_ids: list[str] = Field(serialization_alias="jobIds")
    submitted_rows: int = Field(serialization_alias="submittedRows")
    model_id: int | str = Field(serialization_alias="modelId")
    idempotency_key: str | None = Field(
        default=None,
        serialization_alias="idempotencyKey",
    )
    row_schema_counts: dict[str, int] = Field(
        default_factory=dict,
        serialization_alias="rowSchemaCounts",
    )


def classify_row(row: dict[str, Any]) -> str:
    """Return a coarse row-schema classification for logging."""
    schema_version = row.get("schema_version")
    if schema_version == TECHNICAL_TASK_ROUTER_ROW_SCHEMA_VERSION:
        return "technical_task_router_row_v1"
    if isinstance(schema_version, str) and schema_version:
        return f"unknown:{schema_version[:64]}"
    if "success_under_budget" in row:
        return "submit_data_row"
    return "generic"


__all__ = [
    "TECHNICAL_TASK_ROUTER_ROW_SCHEMA_VERSION",
    "MAX_CONTRIBUTION_ROWS",
    "FORBIDDEN_ROW_KEYS",
    "ContributionMetadata",
    "ContributionScalar",
    "ContributionSubmissionRequest",
    "ContributionSubmissionResponse",
    "SubmitDataContributionRow",
    "TechnicalTaskRouterContributionRowV1",
    "TechnicalTaskRouterSelectedModels",
    "classify_row",
]
