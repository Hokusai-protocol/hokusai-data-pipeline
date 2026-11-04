"""Server-side authoritative fidelity classification for contribution rows.

Model 30 (technical task router) training only benefits from rows that carry
enough signal to recompute *success under budget* server-side: a task
descriptor, an allowed model set, the selected workflow models, a numeric
budget, a numeric observed cost, and a completion signal. Lightweight harness
integrations (Claude Code / Codex SDK plugins) emit a leaner
``harness_outcome_row/v1`` shape that may or may not carry all of those fields.

This module classifies every submitted row into exactly one fidelity tier so
low-fidelity rows can be persisted for telemetry/calibration without polluting
the success-under-budget training set:

* ``training_eligible`` -- has descriptor + allowed + selected (coder & reviewer)
  + numeric budget + numeric observed cost + completion signal. Harness rows in
  this tier are normalized into the canonical ``technical_task_router_row/v1``
  shape so they flow through the existing assembler unchanged.
* ``partial`` -- has route/model identity and a completion signal but is missing
  a numeric cost or budget, so success-under-budget is uncomputable. Persisted
  and counted as accepted, but excluded from the training set.
* ``non_ranking`` -- has an explicit singleton candidate pool. Persisted for
  telemetry/debugging, but excluded from ranking training because no comparison
  was possible.
* ``invalid`` -- missing route identity or model selection entirely. Rejected;
  not persisted as accepted.
* ``passthrough`` -- a row that does not present as a router/harness outcome row
  (e.g. the legacy compact Wavemill ``SubmitDataContributionRow`` shape or other
  accepted rows). Accepted and left byte-for-byte unchanged for backward
  compatibility; the existing assembler continues to decide its eligibility.

The classification here is authoritative: the ``training_eligible`` /
``partial`` tier assigned at intake is persisted alongside the batch and honored
by ``scripts/model_30/assemble_training_set.py``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from src.api.services.routing_join import (
    ROUTE_ROLES,
    find_recommendation_copy,
    routing_outcome_errors,
)
from src.model_30.canonical_row import (
    STAGE_TO_ROLE,
    RowCost,
    has_route_roles,
    price_row,
)

# Canonical rich benchmark row schema versions. These are already validated by
# the assembler against the JSON schema and must not be weakened here.
TECHNICAL_TASK_ROUTER_ROW_V1 = "technical_task_router_row/v1"
TECHNICAL_TASK_ROUTER_ROW_V2 = "technical_task_router_row/v2"
# The SDK's router row versions share these names with the server's canonical
# benchmark rows but not their shape: SDK rows key ``selected_models`` by role
# and carry ``budget_usd`` instead of ``row_id`` / ``eval_id`` / ``max_cost_usd``.
# ``technical_task_router_row/v3`` exists only in the SDK shape (HOK-3364).
TECHNICAL_TASK_ROUTER_ROW_V3 = "technical_task_router_row/v3"
# v3 plus per-stage executed models and token facts (HOK-3412). The server
# reprices v4 rows from ``stage_executions[].task_cost`` and never trains on the
# contributor-reported ``actual_cost_usd`` (HOK-3413).
TECHNICAL_TASK_ROUTER_ROW_V4 = "technical_task_router_row/v4"
_SDK_ROUTER_ROW_VERSIONS = frozenset({TECHNICAL_TASK_ROUTER_ROW_V3, TECHNICAL_TASK_ROUTER_ROW_V4})

# Lighter harness outcome row emitted by SDK plugin integrations.
HARNESS_OUTCOME_ROW_V1 = "harness_outcome_row/v1"
# Harness row plus the routing-outcome block (HOK-3364).
HARNESS_OUTCOME_ROW_V2 = "harness_outcome_row/v2"
_HARNESS_ROW_VERSIONS = frozenset({HARNESS_OUTCOME_ROW_V1, HARNESS_OUTCOME_ROW_V2})
# Rows that must carry a valid routing-outcome block.
_ROUTING_OUTCOME_ROW_VERSIONS = frozenset(
    {HARNESS_OUTCOME_ROW_V2, TECHNICAL_TASK_ROUTER_ROW_V3, TECHNICAL_TASK_ROUTER_ROW_V4}
)

# Mirrors the SDK's v4 contract (hokusai-sdk packages/core/src/contribution/schema.ts).
_STAGE_EXECUTION_FIELDS = frozenset(
    {"stage", "executed_model", "model_evidence", "harness", "task_cost"}
)
_STAGE_EXECUTION_STAGES = frozenset(
    {*STAGE_TO_ROLE, "ci-fix", "conflict-resolution", "ready-remediation"}
)
_MODEL_EVIDENCE_KINDS = frozenset({"provider_response", "session_telemetry", "requested_only"})
_TASK_COST_COVERAGES = frozenset({"complete", "partial", "unavailable", "known_zero"})
_TASK_COST_SUMMARY_V1 = "task_cost_summary/v1"
_TASK_COST_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)
_HARNESS_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_SDK_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_MINTED_ID_PATTERN = re.compile(
    r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
    r"|[0-7][0-9A-HJKMNP-TV-Z]{25})$"
)
# The task-cost contract's stricter list (``TASK_COST_FORBIDDEN_KEYS``), compared
# after lowercasing and removing ``_`` and ``-``.
TASK_COST_FORBIDDEN_KEYS = frozenset(
    {
        "accountid",
        "apikey",
        "authorization",
        "branch",
        "content",
        "credentials",
        "cwd",
        "description",
        "dir",
        "directory",
        "email",
        "evalrecord",
        "filepath",
        "hostname",
        "issuebody",
        "messages",
        "originalprompt",
        "password",
        "path",
        "prompt",
        "prompthash",
        "rawinput",
        "repo",
        "repository",
        "secret",
        "tasktext",
        "text",
        "token",
        "transcript",
        "userid",
        "username",
        "workspace",
        "worktree",
    }
)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_TASK_DESCRIPTOR_SCHEMA = _REPO_ROOT / "schema" / "hokusai_task_descriptor.v1.json"

# Scorer ref and schema version the normalized canonical row must carry so the
# assembler's ``technical_task_router_row.v1.json`` validation accepts it.
_CANONICAL_SCORER_REF = "technical_task_router.success_under_budget/v1"

# Raw prompt/text fields that must never appear in a redacted contribution row.
# Mirrors ``FORBIDDEN_KEYS`` in wavemill's hokusai-contribution-schema.ts so the
# server preserves the same redaction guarantee for the harness row shape.
FORBIDDEN_KEYS = frozenset(
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


class FidelityTier(str, Enum):
    """Authoritative server-assigned fidelity tier for a contribution row."""

    TRAINING_ELIGIBLE = "training_eligible"
    PARTIAL = "partial"
    NON_RANKING = "non_ranking"
    INVALID = "invalid"
    PASSTHROUGH = "passthrough"


@dataclass(frozen=True)
class RowClassification:
    """Result of classifying a single submitted row."""

    tier: FidelityTier
    # The row to persist. For ``training_eligible`` harness rows this is the
    # normalized canonical row; for every other accepted tier it is the row as
    # submitted. ``None`` for ``invalid`` rows (which are not persisted).
    row: dict[str, Any] | None
    reason: str | None = None
    descriptor_warnings: list[dict[str, str]] = field(default_factory=list)
    # Server repricing of the submitted row (HOK-3413); ``None`` for rows that
    # are not role-keyed router rows.
    cost: RowCost | None = None


@dataclass
class BatchClassification:
    """Aggregate classification for a submitted batch of rows."""

    accepted_rows: list[dict[str, Any]] = field(default_factory=list)
    # Per accepted row, aligned to ``accepted_rows`` by index.
    accepted_tiers: list[str] = field(default_factory=list)
    # Per accepted row: its index in the submission, and its repricing.
    accepted_indices: list[int] = field(default_factory=list)
    accepted_costs: list[RowCost | None] = field(default_factory=list)
    # Rejected (invalid) rows: original submission index + human-readable reason.
    rejected: list[dict[str, Any]] = field(default_factory=list)
    descriptor_warnings: list[dict[str, Any]] = field(default_factory=list)
    training_eligible_count: int = 0
    partial_count: int = 0
    non_ranking_count: int = 0
    passthrough_count: int = 0

    @property
    def accepted_count(self: BatchClassification) -> int:
        """Return the number of accepted rows (training_eligible + partial + passthrough)."""
        return len(self.accepted_rows)

    @property
    def rejected_count(self: BatchClassification) -> int:
        """Return the number of rows rejected as invalid."""
        return len(self.rejected)

    @property
    def has_only_partial(self: BatchClassification) -> bool:
        """Return True when accepted rows are telemetry-only and none are training-usable."""
        return (
            (self.partial_count > 0 or self.non_ranking_count > 0)
            and self.training_eligible_count == 0
            and self.passthrough_count == 0
        )


def _coerce_number(value: Any) -> float | None:
    """Return a finite float for numeric values, else None. Bools are rejected."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number
    return None


@lru_cache(maxsize=1)
def _task_descriptor_validator() -> jsonschema.protocols.Validator:
    schema = json.loads(_TASK_DESCRIPTOR_SCHEMA.read_text(encoding="utf-8"))
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    return validator_cls(schema)


def _descriptor_path(error: jsonschema.ValidationError) -> str:
    parts = ["task_descriptor", *(str(part) for part in error.absolute_path)]
    return ".".join(parts)


def _validate_harness_task_descriptor(row: dict[str, Any]) -> list[dict[str, str]]:
    if row.get("schema_version") not in _HARNESS_ROW_VERSIONS:
        return []
    descriptor = row.get("task_descriptor")
    if not isinstance(descriptor, dict):
        return [
            {
                "path": "task_descriptor",
                "message": "task_descriptor must be an object",
            }
        ]
    errors = sorted(
        _task_descriptor_validator().iter_errors(descriptor),
        key=lambda error: list(error.absolute_path),
    )
    return [
        {
            "path": _descriptor_path(error),
            "message": error.message,
        }
        for error in errors
    ]


def _extract_allowed_models(row: dict[str, Any]) -> list[str]:
    allowed = row.get("allowed_models")
    if isinstance(allowed, list):
        return [str(model) for model in allowed if isinstance(model, str) and model]
    return []


def _has_ranking_candidate_pool(allowed_models: list[str]) -> bool:
    """Return True when a row can support a model-vs-model ranking decision."""
    return len(set(allowed_models)) >= 2


def _extract_selected_models(row: dict[str, Any]) -> tuple[list[str], bool]:
    """Return (selected model ids, has_coder_and_reviewer_roles)."""
    selected = row.get("selected_models")
    if isinstance(selected, list):
        models = [str(model) for model in selected if isinstance(model, str) and model]
        return models, len(models) >= 2
    if isinstance(selected, dict):
        planner = selected.get("planner")
        coder = selected.get("coder")
        reviewer = selected.get("reviewer")
        models = [
            str(model) for model in (planner, coder, reviewer) if isinstance(model, str) and model
        ]
        has_roles = (
            isinstance(coder, str) and bool(coder) and isinstance(reviewer, str) and bool(reviewer)
        )
        return models, has_roles
    return [], False


def _has_completion_signal(row: dict[str, Any]) -> bool:
    return (
        "success_under_budget" in row
        or "completion_result" in row
        or "completed_successfully" in row
    )


def _looks_like_router_outcome_row(row: dict[str, Any]) -> bool:
    """Return True when a row presents as a router/harness outcome row.

    Legacy compact Wavemill ``SubmitDataContributionRow`` rows (which carry
    ``inputs`` + ``success_under_budget`` but no top-level ``selected_models`` /
    ``allowed_models`` / ``completion_result``) are intentionally excluded so
    their long-standing acceptance and assembler treatment are unchanged.
    """
    schema_version = row.get("schema_version")
    if schema_version in _HARNESS_ROW_VERSIONS or schema_version in _SDK_ROUTER_ROW_VERSIONS:
        return True
    return (
        isinstance(row.get("selected_models"), dict)
        or "allowed_models" in row
        or "completion_result" in row
    )


def _is_canonical_benchmark_row(row: dict[str, Any]) -> bool:
    """Return True for the server's canonical benchmark row shape.

    Matching ``schema_version`` alone is not enough: the SDK emits rows with
    the same v1/v2 names whose ``selected_models`` is a role map. Those are
    classified and normalized like harness rows.
    """
    return row.get("schema_version") in (
        TECHNICAL_TASK_ROUTER_ROW_V1,
        TECHNICAL_TASK_ROUTER_ROW_V2,
    ) and isinstance(row.get("selected_models"), list)


def _routing_outcome_block(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return the routing-outcome block to keep through normalization, if any."""
    selected = row.get("selected_models")
    if "inference_log_id" not in row and "overrides" not in row:
        return None
    block: dict[str, Any] = {}
    if row.get("inference_log_id") is not None:
        block["inference_log_id"] = str(row["inference_log_id"])
    if isinstance(row.get("overrides"), list):
        block["overrides"] = row["overrides"]
    if isinstance(selected, dict):
        block["selected_models"] = {
            role: selected[role] for role in ROUTE_ROLES if isinstance(selected.get(role), str)
        }
    return block


def _forbidden_task_cost_key(value: Any, path: str) -> str | None:
    stack: list[tuple[str, Any]] = [(path, value)]
    while stack:
        current_path, current = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                child_path = f"{current_path}.{key}"
                normalized = str(key).lower().replace("_", "").replace("-", "")
                if normalized in TASK_COST_FORBIDDEN_KEYS:
                    return child_path
                stack.append((child_path, child))
        elif isinstance(current, list):
            stack.extend((f"{current_path}.{i}", item) for i, item in enumerate(current))
    return None


def _is_count(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _task_cost_errors(task_cost: Any, label: str, task_id: Any) -> list[str]:
    """Check the parts of a ``task_cost_summary/v1`` that repricing reads, plus redaction."""
    if not isinstance(task_cost, dict):
        return [f"{label} must be a task_cost_summary/v1 object"]
    forbidden = _forbidden_task_cost_key(task_cost, label)
    if forbidden is not None:
        return [f"forbidden field at {forbidden}"]
    errors: list[str] = []
    if task_cost.get("schema_version") != _TASK_COST_SUMMARY_V1:
        errors.append(f"{label}.schema_version must be {_TASK_COST_SUMMARY_V1}")
    if isinstance(task_id, str) and task_cost.get("task_id") != task_id:
        errors.append(f"{label}.task_id must equal the row's task_id")
    if task_cost.get("coverage") not in _TASK_COST_COVERAGES:
        allowed = ", ".join(sorted(_TASK_COST_COVERAGES))
        errors.append(f"{label}.coverage must be one of: {allowed}")
    segments = task_cost.get("model_segments")
    if not isinstance(segments, list):
        return [*errors, f"{label}.model_segments must be an array"]
    for index, segment in enumerate(segments):
        errors.extend(_segment_errors(segment, f"{label}.model_segments[{index}]"))
    return errors


def _segment_errors(segment: Any, label: str) -> list[str]:
    if not isinstance(segment, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    model = segment.get("model")
    if not isinstance(model, str) or not model.strip():
        errors.append(f"{label}.model must be a non-empty model id")
    usage = segment.get("usage")
    if not isinstance(usage, dict):
        return [*errors, f"{label}.usage must be an object"]
    for token_field in _TASK_COST_TOKEN_FIELDS:
        value = usage.get(token_field)
        if value is not None and not _is_count(value):
            errors.append(f"{label}.usage.{token_field} must be a count or null")
    return errors


def stage_execution_errors(row: dict[str, Any]) -> list[str]:  # noqa: C901
    """Why a v4 row's stage facts are invalid; ``[]`` when they are valid.

    Mirrors the SDK's ``stageExecutionErrors``: a non-empty ``stage_executions``
    array of well-formed entries; per base stage, the last entry's
    ``executed_model`` equals the matching ``selected_models`` role; a valid
    ``comparison_group``; ``integration`` only ``{}``; a version-string
    ``sdk_version``. Each ``task_cost`` is checked for what repricing reads and
    for the task-cost contract's forbidden keys.
    """
    errors: list[str] = []
    executions = row.get("stage_executions")
    if not isinstance(executions, list) or not executions:
        return ["stage_executions must be a non-empty array"]
    last_by_stage: dict[str, Any] = {}
    for index, entry in enumerate(executions):
        label = f"stage_executions[{index}]"
        if not isinstance(entry, dict) or not set(entry) <= _STAGE_EXECUTION_FIELDS:
            errors.append(
                f"{label} must be an object with only: {', '.join(sorted(_STAGE_EXECUTION_FIELDS))}"
            )
            continue
        stage = entry.get("stage")
        if stage not in _STAGE_EXECUTION_STAGES:
            allowed = ", ".join(sorted(_STAGE_EXECUTION_STAGES))
            errors.append(f"{label}.stage must be one of: {allowed}")
        model = entry.get("executed_model")
        if not isinstance(model, str) or not model.strip():
            errors.append(f"{label}.executed_model must be a non-empty model id")
        if entry.get("model_evidence") not in _MODEL_EVIDENCE_KINDS:
            errors.append(
                f"{label}.model_evidence must be one of: {', '.join(sorted(_MODEL_EVIDENCE_KINDS))}"
            )
        harness = entry.get("harness")
        if not isinstance(harness, str) or not _HARNESS_SLUG_PATTERN.match(harness):
            errors.append(f"{label}.harness must be a harness slug")
        if "task_cost" not in entry:
            errors.append(f"{label}.task_cost is required")
        else:
            errors.extend(
                _task_cost_errors(entry["task_cost"], f"{label}.task_cost", row.get("task_id"))
            )
        if stage in STAGE_TO_ROLE:
            last_by_stage[stage] = model
    selected = row.get("selected_models") if isinstance(row.get("selected_models"), dict) else {}
    for stage, model in last_by_stage.items():
        role = STAGE_TO_ROLE[stage]
        if selected.get(role) != model:
            errors.append(
                f"the last {stage} stage's executed_model must equal selected_models.{role}"
            )

    group = row.get("comparison_group")
    if group is not None:
        if not isinstance(group, dict) or not set(group) <= {"id", "role_varied"}:
            errors.append("comparison_group must be an object with only id and role_varied")
        else:
            if not isinstance(group.get("id"), str) or not _MINTED_ID_PATTERN.match(group["id"]):
                errors.append("comparison_group.id must be a minted pair id (UUID or ULID)")
            if group.get("role_varied") not in ROUTE_ROLES:
                roles = ", ".join(ROUTE_ROLES)
                errors.append(f"comparison_group.role_varied must be one of: {roles}")
    if "integration" in row and row["integration"] != {}:
        errors.append("integration is reserved (HOK-3343); only {} is accepted")
    version = row.get("sdk_version")
    if version is not None and (
        not isinstance(version, str) or not _SDK_VERSION_PATTERN.match(version)
    ):
        errors.append("sdk_version must be a version string")
    return errors


def _contains_forbidden_field(value: Any) -> str | None:
    """Return the dotted path of the first forbidden key found, else None."""
    stack: list[tuple[str, Any]] = [("", value)]
    while stack:
        path, current = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                child_path = f"{path}.{key}" if path else str(key)
                if str(key).lower() in FORBIDDEN_KEYS:
                    return child_path
                stack.append((child_path, child))
        elif isinstance(current, list):
            for index, item in enumerate(current):
                stack.append((f"{path}.{index}" if path else str(index), item))
    return None


def _completed_successfully(row: dict[str, Any]) -> bool:
    completion_result = row.get("completion_result")
    if isinstance(completion_result, str):
        return completion_result == "success"
    if isinstance(row.get("completed_successfully"), bool):
        return bool(row["completed_successfully"])
    return bool(row.get("success_under_budget"))


def _canonical_row_id(row: dict[str, Any]) -> str:
    task_id = row.get("task_id")
    if isinstance(task_id, str) and task_id:
        return task_id
    digest = hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return f"harness-{digest[:24]}"


def normalize_harness_row_to_canonical(
    row: dict[str, Any],
    *,
    benchmark_spec_id: str | None,
    model_id: str,
) -> dict[str, Any]:
    """Normalize a training-eligible harness row into a canonical v1 row.

    The output validates against ``schema/technical_task_router_row.v1.json``
    (``additionalProperties: false``) so it flows through the existing training
    assembler exactly like a rich benchmark row.
    """
    allowed_models = _extract_allowed_models(row)
    selected_models, _ = _extract_selected_models(row)
    budget = _coerce_number(row.get("budget_usd"))
    if budget is None:
        budget = _coerce_number(row.get("max_cost_usd"))
    actual_cost = _coerce_number(row.get("actual_cost_usd"))
    if row.get("schema_version") == TECHNICAL_TASK_ROUTER_ROW_V4:
        # The server's repriced cost, never the contributor-reported figure.
        actual_cost = price_row(row).cost_usd
    row_id = _canonical_row_id(row)
    # ``eval_id`` is an identifier only. It is never an inference link: the
    # link comes from ``metadata.routing_outcome.inference_log_id`` via the
    # routing join (HOK-3365).
    eval_id = row_id
    observed_at = row.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at:
        observed_at = datetime.now(timezone.utc).isoformat()

    harness_metadata = row.get("harness_metadata")
    metadata: dict[str, Any] = {
        "source_schema_version": str(row.get("schema_version") or HARNESS_OUTCOME_ROW_V1)
    }
    routing_outcome = _routing_outcome_block(row)
    if routing_outcome is not None:
        metadata["routing_outcome"] = routing_outcome
    if isinstance(harness_metadata, dict):
        metadata["harness_metadata"] = harness_metadata
    if isinstance(row.get("harness"), str):
        metadata["harness"] = row["harness"]
    if row.get("schema_version") == TECHNICAL_TASK_ROUTER_ROW_V4:
        metadata["contributor_reported_cost_usd"] = _coerce_number(row.get("actual_cost_usd"))

    canonical: dict[str, Any] = {
        "schema_version": TECHNICAL_TASK_ROUTER_ROW_V1,
        "row_id": row_id,
        "benchmark_spec_id": benchmark_spec_id or "harness_outcome",
        "eval_id": str(eval_id),
        "model_id": str(model_id),
        "task_descriptor": row.get("task_descriptor") or {},
        "allowed_models": allowed_models,
        "selected_models": selected_models,
        "max_cost_usd": budget,
        "actual_cost_usd": actual_cost,
        "completed_successfully": _completed_successfully(row),
        "scorer_ref": _CANONICAL_SCORER_REF,
        "observed_at": observed_at,
        "metadata": metadata,
    }
    wall_clock = _coerce_number(row.get("wall_clock_seconds"))
    if wall_clock is not None:
        canonical["actual_time_seconds"] = wall_clock
    return canonical


def _classify_router_outcome_row(  # noqa: C901
    row: dict[str, Any],
    *,
    benchmark_spec_id: str | None,
    model_id: str,
) -> RowClassification:
    descriptor_warnings = _validate_harness_task_descriptor(row)
    # Canonical rich rows keep their existing, stricter contract untouched.
    if _is_canonical_benchmark_row(row):
        allowed_models = _extract_allowed_models(row)
        if allowed_models and not _has_ranking_candidate_pool(allowed_models):
            return RowClassification(tier=FidelityTier.NON_RANKING, row=row)
        return RowClassification(tier=FidelityTier.TRAINING_ELIGIBLE, row=row)

    forbidden_path = _contains_forbidden_field(row)
    if forbidden_path is not None:
        return RowClassification(
            tier=FidelityTier.INVALID,
            row=None,
            reason=f"forbidden_field:{forbidden_path}",
            descriptor_warnings=descriptor_warnings,
        )

    if row.get("schema_version") in _ROUTING_OUTCOME_ROW_VERSIONS:
        # Hokusai joins the recommendation from the inference log; a row that
        # stores its own copy could disagree with it.
        copy_path = find_recommendation_copy(row)
        if copy_path is not None:
            return RowClassification(
                tier=FidelityTier.INVALID,
                row=None,
                reason=f"recommendation_copy:{copy_path}",
                descriptor_warnings=descriptor_warnings,
            )
        routing_errors = routing_outcome_errors(row)
        if routing_errors:
            return RowClassification(
                tier=FidelityTier.INVALID,
                row=None,
                reason=f"invalid_routing_outcome:{routing_errors[0]}",
                descriptor_warnings=descriptor_warnings,
            )
    if row.get("schema_version") == TECHNICAL_TASK_ROUTER_ROW_V4:
        stage_errors = stage_execution_errors(row)
        if stage_errors:
            return RowClassification(
                tier=FidelityTier.INVALID,
                row=None,
                reason=f"invalid_stage_executions:{stage_errors[0]}",
                descriptor_warnings=descriptor_warnings,
            )
    cost = price_row(row) if has_route_roles(row) else None

    allowed_models = _extract_allowed_models(row)
    selected_models, has_roles = _extract_selected_models(row)
    if not selected_models:
        return RowClassification(
            tier=FidelityTier.INVALID,
            row=None,
            reason="missing_selected_models",
            descriptor_warnings=descriptor_warnings,
        )
    if not allowed_models:
        return RowClassification(
            tier=FidelityTier.INVALID,
            row=None,
            reason="missing_allowed_models",
            descriptor_warnings=descriptor_warnings,
        )
    if not _has_ranking_candidate_pool(allowed_models):
        return RowClassification(
            tier=FidelityTier.NON_RANKING,
            row=row,
            descriptor_warnings=descriptor_warnings,
            cost=cost,
        )

    budget = _coerce_number(row.get("budget_usd"))
    if budget is None:
        budget = _coerce_number(row.get("max_cost_usd"))
    if row.get("schema_version") == TECHNICAL_TASK_ROUTER_ROW_V4:
        # Only a repriced cost can make a v4 row cost-eligible (HOK-3413).
        actual_cost = cost.cost_usd if cost is not None else None
    else:
        actual_cost = _coerce_number(row.get("actual_cost_usd"))
    descriptor = row.get("task_descriptor")

    training_eligible = (
        isinstance(descriptor, dict)
        and has_roles
        and budget is not None
        and budget > 0
        and actual_cost is not None
        and actual_cost >= 0
        and _has_completion_signal(row)
    )
    if training_eligible:
        normalized = normalize_harness_row_to_canonical(
            row, benchmark_spec_id=benchmark_spec_id, model_id=model_id
        )
        return RowClassification(
            tier=FidelityTier.TRAINING_ELIGIBLE,
            row=normalized,
            descriptor_warnings=descriptor_warnings,
            cost=cost,
        )

    # Has route/model identity but cannot support success-under-budget training.
    return RowClassification(
        tier=FidelityTier.PARTIAL,
        row=row,
        descriptor_warnings=descriptor_warnings,
        cost=cost,
    )


def classify_row(
    row: dict[str, Any],
    *,
    benchmark_spec_id: str | None = None,
    model_id: str = "30",
) -> RowClassification:
    """Classify a single submitted row into its authoritative fidelity tier."""
    if _looks_like_router_outcome_row(row):
        return _classify_router_outcome_row(
            row, benchmark_spec_id=benchmark_spec_id, model_id=model_id
        )
    # Not a router/harness outcome row: accept unchanged (legacy/compact shapes).
    return RowClassification(tier=FidelityTier.PASSTHROUGH, row=row)


def classify_batch(
    rows: list[dict[str, Any]],
    *,
    benchmark_spec_id: str | None = None,
    model_id: str = "30",
) -> BatchClassification:
    """Classify a batch, partitioning accepted rows from rejected invalid rows."""
    result = BatchClassification()
    for index, row in enumerate(rows):
        classification = classify_row(row, benchmark_spec_id=benchmark_spec_id, model_id=model_id)
        tier = classification.tier
        for warning in classification.descriptor_warnings:
            result.descriptor_warnings.append({"index": index, **warning})
        if tier is FidelityTier.INVALID:
            result.rejected.append(
                {"index": index, "reason": classification.reason or "invalid_row"}
            )
            continue

        result.accepted_rows.append(classification.row if classification.row is not None else row)
        result.accepted_tiers.append(tier.value)
        result.accepted_indices.append(index)
        result.accepted_costs.append(classification.cost)
        if tier is FidelityTier.TRAINING_ELIGIBLE:
            result.training_eligible_count += 1
        elif tier is FidelityTier.PARTIAL:
            result.partial_count += 1
        elif tier is FidelityTier.NON_RANKING:
            result.non_ranking_count += 1
        else:
            result.passthrough_count += 1
    return result
