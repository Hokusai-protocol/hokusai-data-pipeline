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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Canonical rich benchmark row schema versions. These are already validated by
# the assembler against the JSON schema and must not be weakened here.
TECHNICAL_TASK_ROUTER_ROW_V1 = "technical_task_router_row/v1"
TECHNICAL_TASK_ROUTER_ROW_V2 = "technical_task_router_row/v2"

# Lighter harness outcome row emitted by SDK plugin integrations.
HARNESS_OUTCOME_ROW_V1 = "harness_outcome_row/v1"

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


@dataclass
class BatchClassification:
    """Aggregate classification for a submitted batch of rows."""

    accepted_rows: list[dict[str, Any]] = field(default_factory=list)
    # Per accepted row, aligned to ``accepted_rows`` by index.
    accepted_tiers: list[str] = field(default_factory=list)
    # Rejected (invalid) rows: original submission index + human-readable reason.
    rejected: list[dict[str, Any]] = field(default_factory=list)
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
    if schema_version == HARNESS_OUTCOME_ROW_V1:
        return True
    return (
        isinstance(row.get("selected_models"), dict)
        or "allowed_models" in row
        or "completion_result" in row
    )


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
    row_id = _canonical_row_id(row)
    eval_id = row.get("inference_log_id") or row.get("task_id") or row_id
    observed_at = row.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at:
        observed_at = datetime.now(timezone.utc).isoformat()

    harness_metadata = row.get("harness_metadata")
    metadata: dict[str, Any] = {"source_schema_version": HARNESS_OUTCOME_ROW_V1}
    if isinstance(harness_metadata, dict):
        metadata["harness_metadata"] = harness_metadata
    if isinstance(row.get("harness"), str):
        metadata["harness"] = row["harness"]

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


def _classify_router_outcome_row(
    row: dict[str, Any],
    *,
    benchmark_spec_id: str | None,
    model_id: str,
) -> RowClassification:
    # Canonical rich rows keep their existing, stricter contract untouched.
    if row.get("schema_version") in (
        TECHNICAL_TASK_ROUTER_ROW_V1,
        TECHNICAL_TASK_ROUTER_ROW_V2,
    ):
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
        )

    allowed_models = _extract_allowed_models(row)
    selected_models, has_roles = _extract_selected_models(row)
    if not selected_models:
        return RowClassification(
            tier=FidelityTier.INVALID, row=None, reason="missing_selected_models"
        )
    if not allowed_models:
        return RowClassification(
            tier=FidelityTier.INVALID, row=None, reason="missing_allowed_models"
        )
    if not _has_ranking_candidate_pool(allowed_models):
        return RowClassification(tier=FidelityTier.NON_RANKING, row=row)

    budget = _coerce_number(row.get("budget_usd"))
    if budget is None:
        budget = _coerce_number(row.get("max_cost_usd"))
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
        return RowClassification(tier=FidelityTier.TRAINING_ELIGIBLE, row=normalized)

    # Has route/model identity but cannot support success-under-budget training.
    return RowClassification(tier=FidelityTier.PARTIAL, row=row)


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
        if tier is FidelityTier.INVALID:
            result.rejected.append(
                {"index": index, "reason": classification.reason or "invalid_row"}
            )
            continue

        result.accepted_rows.append(classification.row if classification.row is not None else row)
        result.accepted_tiers.append(tier.value)
        if tier is FidelityTier.TRAINING_ELIGIBLE:
            result.training_eligible_count += 1
        elif tier is FidelityTier.PARTIAL:
            result.partial_count += 1
        elif tier is FidelityTier.NON_RANKING:
            result.non_ranking_count += 1
        else:
            result.passthrough_count += 1
    return result
