"""One canonical Model 30 training record per contributed router row (HOK-3413).

Contributors are paid for data that improves Model 30, so the server never
trains on the dollar figure a contributor reports. Every intake path builds the
same record here:

* each role's (and each repair stage's) executed model, the evidence for it,
  its token totals, and its cost **repriced from tokens** with Hokusai's price
  table (``usage_cost.price_usage_by_model``, the same function the offline
  Wavemill collector uses);
* a ``cost_status`` saying whether that cost can be trained on;
* the task descriptor, outcome, comparison group, the routing join (HOK-3365)
  and the contributor-reported cost, kept as evidence only.

``cost_status`` values:

* ``priced`` -- every stage has token evidence and every model is priced;
* ``unpriced_model`` -- a model Hokusai has no price for (unknown, never 0);
* ``no_token_evidence`` -- v1-v3 rows, or a stage whose ``task_cost`` has no
  usage (``coverage: unavailable``);
* ``coverage_partial`` -- usage is a lower bound (``coverage: partial`` or a
  counter not reported);
* ``recorded_total`` -- frozen pre-May 2026 Wavemill history only (HOK-3414):
  the harness-recorded total, with no tokens to reprice. Never assigned to a
  contribution.

Only ``priced`` costs train cost; every row with a valid outcome trains success.
A stage whose model evidence is ``requested_only`` never counts as execution of
its model: the role keeps ``requested_model`` and its ``executed_model`` is null.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from src.model_30.model_identity import (
    hokusai_price_snapshot,
    normalize_model_id,
    price_table_version,
)
from src.model_30.usage_cost import (
    finite_number,
    price_usage_by_model,
    usage_from_task_cost_segments,
)

CANONICAL_ROW_SCHEMA_VERSION = "model_30_canonical_row/v1"
ROUTER_ROW_V4 = "technical_task_router_row/v4"

COST_PRICED = "priced"
COST_UNPRICED_MODEL = "unpriced_model"
COST_NO_TOKEN_EVIDENCE = "no_token_evidence"
COST_COVERAGE_PARTIAL = "coverage_partial"
COST_RECORDED_TOTAL = "recorded_total"
# Worst first: a row reports the first status any of its stages has.
COST_STATUSES = (
    COST_NO_TOKEN_EVIDENCE,
    COST_UNPRICED_MODEL,
    COST_COVERAGE_PARTIAL,
    COST_RECORDED_TOTAL,
    COST_PRICED,
)

STAGE_TO_ROLE = {"planning": "planner", "coding": "coder", "review": "reviewer"}
ROUTE_ROLES = ("planner", "coder", "reviewer")
REQUESTED_ONLY = "requested_only"

_TOKEN_FIELDS = (
    ("input", "input_tokens"),
    ("output", "output_tokens"),
    ("cache_read", "cache_read_tokens"),
    ("cache_write", "cache_write_tokens"),
)


def worst_cost_status(statuses: Iterable[str]) -> str:
    """Return the worst of *statuses*; ``no_token_evidence`` when there are none."""
    present = set(statuses)
    if not present:
        return COST_NO_TOKEN_EVIDENCE
    return next(status for status in COST_STATUSES if status in present)


@dataclass(frozen=True)
class StageCost:
    """Repriced cost of one ``stage_executions`` entry."""

    stage: str
    executed_model: str | None
    requested_model: str
    model_evidence: str | None
    harness: str | None
    tokens: dict[str, float]
    cost_usd: float | None
    cost_status: str
    unpriced_models: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RowCost:
    """Repriced cost of a whole row."""

    stages: list[StageCost]
    cost_usd: float | None
    cost_status: str

    @property
    def priced(self: RowCost) -> bool:
        """Return True when the row's cost can train cost."""
        return self.cost_status == COST_PRICED


def _stage_tokens(task_cost: Mapping[str, Any]) -> dict[str, float]:
    tokens = {name: 0.0 for name, _ in _TOKEN_FIELDS}
    for segment in task_cost.get("model_segments") or []:
        usage = segment.get("usage") if isinstance(segment, Mapping) else None
        if not isinstance(usage, Mapping):
            continue
        for name, sdk_field in _TOKEN_FIELDS:
            tokens[name] += finite_number(usage.get(sdk_field)) or 0.0
    return tokens


def price_stage(entry: Mapping[str, Any]) -> StageCost:
    """Reprice one v4 ``stage_executions`` entry from its ``task_cost`` tokens."""
    task_cost = entry.get("task_cost") if isinstance(entry.get("task_cost"), Mapping) else {}
    segments = [s for s in task_cost.get("model_segments") or [] if isinstance(s, Mapping)]
    coverage = task_cost.get("coverage")
    requested = normalize_model_id(entry.get("executed_model"))
    evidence = entry.get("model_evidence")
    executed = None if evidence == REQUESTED_ONLY else requested

    priced = price_usage_by_model(
        usage_from_task_cost_segments(segments), hokusai_price_snapshot(), reprice="always"
    )
    tokens = _stage_tokens(task_cost)
    if not segments:
        # A declared known zero is a fact; an unmeasured stage is not.
        status = COST_PRICED if coverage == "known_zero" else COST_NO_TOKEN_EVIDENCE
    elif priced.unpriced:
        status = COST_UNPRICED_MODEL
    elif coverage == "partial" or priced.partial:
        status = COST_COVERAGE_PARTIAL
    elif coverage == "unavailable":
        status = COST_NO_TOKEN_EVIDENCE
    else:
        status = COST_PRICED
    cost = sum(bucket["cost"] for bucket in priced.per_model.values())
    return StageCost(
        stage=str(entry.get("stage")),
        executed_model=executed,
        requested_model=requested,
        model_evidence=evidence if isinstance(evidence, str) else None,
        harness=entry.get("harness") if isinstance(entry.get("harness"), str) else None,
        tokens=tokens,
        cost_usd=round(cost, 10) if status == COST_PRICED else None,
        cost_status=status,
        unpriced_models=sorted(set(priced.unpriced)),
    )


def price_row(row: Mapping[str, Any]) -> RowCost:
    """Reprice a contributed row. Rows without ``stage_executions`` have no token evidence."""
    executions = row.get("stage_executions")
    if row.get("schema_version") != ROUTER_ROW_V4 or not isinstance(executions, list):
        return RowCost(stages=[], cost_usd=None, cost_status=COST_NO_TOKEN_EVIDENCE)
    stages = [price_stage(entry) for entry in executions if isinstance(entry, Mapping)]
    status = worst_cost_status(stage.cost_status for stage in stages)
    total = (
        round(sum(stage.cost_usd or 0.0 for stage in stages), 10) if status == COST_PRICED else None
    )
    return RowCost(stages=stages, cost_usd=total, cost_status=status)


def _sum_tokens(stages: list[StageCost]) -> dict[str, float]:
    return {name: sum(stage.tokens[name] for stage in stages) for name, _ in _TOKEN_FIELDS}


def _role_record(role: str, selected: Any, stages: list[StageCost]) -> dict[str, Any]:
    """One role's record. The last stage for a role is the one that ran it to completion."""
    requested = normalize_model_id(selected) if isinstance(selected, str) and selected else None
    if not stages:
        return {
            "requested_model": requested,
            "executed_model": None,
            "model_evidence": None,
            "harness": None,
            "stage_count": 0,
            "tokens": None,
            "cost_usd": None,
            "cost_status": COST_NO_TOKEN_EVIDENCE,
        }
    last = stages[-1]
    status = worst_cost_status(stage.cost_status for stage in stages)
    return {
        "requested_model": requested or last.requested_model,
        "executed_model": last.executed_model,
        "model_evidence": last.model_evidence,
        "harness": last.harness,
        "stage_count": len(stages),
        "tokens": _sum_tokens(stages),
        "cost_usd": (
            round(sum(stage.cost_usd or 0.0 for stage in stages), 10)
            if status == COST_PRICED
            else None
        ),
        "cost_status": status,
    }


def _success(row: Mapping[str, Any]) -> bool | None:
    result = row.get("completion_result")
    if isinstance(result, str):
        return result == "success"
    if isinstance(row.get("completed_successfully"), bool):
        return bool(row["completed_successfully"])
    return None


def _available_models(row: Mapping[str, Any]) -> dict[str, list[str]] | None:
    """Per-role pools from the SDK's ``available_models`` block, catalog-spelled."""
    block = row.get("available_models")
    if not isinstance(block, Mapping):
        return None
    pools = {}
    for role in ROUTE_ROLES:
        models = block.get(f"{role}_models")
        if isinstance(models, list):
            pools[role] = [normalize_model_id(m) for m in models if isinstance(m, str) and m]
    return pools or None


def build_canonical_row(
    row: Mapping[str, Any],
    *,
    submission_id: str,
    row_index: int,
    fidelity_tier: str,
    routing_join: Mapping[str, Any] | None,
    contributor_id: str | None,
    row_cost: RowCost | None = None,
) -> dict[str, Any]:
    """Build the canonical record for one accepted, role-keyed router row."""
    cost = row_cost if row_cost is not None else price_row(row)
    selected = row.get("selected_models") if isinstance(row.get("selected_models"), Mapping) else {}
    by_role: dict[str, list[StageCost]] = {role: [] for role in ROUTE_ROLES}
    repairs: list[StageCost] = []
    for stage in cost.stages:
        role = STAGE_TO_ROLE.get(stage.stage)
        (by_role[role] if role else repairs).append(stage)
    roles = {
        role: _role_record(role, selected.get(role), by_role[role])
        for role in ROUTE_ROLES
        if selected.get(role) or by_role[role]
    }
    group = row.get("comparison_group")
    return {
        "schema_version": CANONICAL_ROW_SCHEMA_VERSION,
        "canonical_row_id": f"{submission_id}:{row_index}",
        "submission_id": submission_id,
        "row_index": row_index,
        "source_schema_version": row.get("schema_version"),
        "fidelity_tier": fidelity_tier,
        "task_id": row.get("task_id") if isinstance(row.get("task_id"), str) else None,
        "observed_at": row.get("observed_at") if isinstance(row.get("observed_at"), str) else None,
        "task_descriptor": dict(row.get("task_descriptor") or {}),
        "allowed_models": [
            normalize_model_id(model)
            for model in row.get("allowed_models") or []
            if isinstance(model, str) and model
        ],
        "available_models": _available_models(row),
        "budget_usd": finite_number(row.get("budget_usd", row.get("max_cost_usd"))),
        "success": _success(row),
        "completion_result": (
            row.get("completion_result") if isinstance(row.get("completion_result"), str) else None
        ),
        # Contributions carry no quality score; the corpus builder derives it from success.
        "quality": None,
        "duration_seconds": finite_number(row.get("wall_clock_seconds")),
        # Derived from the repriced cost and the budget when the corpus is built.
        "under_budget": None,
        "budget_violation": None,
        "roles": roles,
        "repair_stages": [
            {
                "stage": stage.stage,
                "executed_model": stage.executed_model,
                "requested_model": stage.requested_model,
                "model_evidence": stage.model_evidence,
                "harness": stage.harness,
                "tokens": stage.tokens,
                "cost_usd": stage.cost_usd,
                "cost_status": stage.cost_status,
            }
            for stage in repairs
        ],
        "cost_usd": cost.cost_usd,
        "cost_status": cost.cost_status,
        "cost_detail": None,
        "cost_breakdown": None,
        "unpriced_models": sorted({m for stage in cost.stages for m in stage.unpriced_models}),
        "price_table_version": price_table_version(),
        "comparison_group": dict(group) if isinstance(group, Mapping) else None,
        "routing_join": dict(routing_join) if routing_join is not None else None,
        "routing_context": None,
        # Pseudonymous router-CSV ids are derived from the ids above at build time.
        "router_ids": None,
        "contributor_id": contributor_id,
        "source": {
            "kind": "contribution",
            "harness": row.get("harness") if isinstance(row.get("harness"), str) else None,
            "sdk_version": (
                row.get("sdk_version") if isinstance(row.get("sdk_version"), str) else None
            ),
        },
        "contributor_reported_cost_usd": finite_number(row.get("actual_cost_usd")),
    }


def has_route_roles(row: Mapping[str, Any]) -> bool:
    """Return True for role-keyed router rows (SDK router and harness rows)."""
    return isinstance(row.get("selected_models"), Mapping)
