"""Canonical Model 30 rows <-> the router CSV the trainer reads (HOK-3414).

Training reads canonical rows only (``model_30_canonical_row/v1``, see
``canonical_row.py``). This module holds the one mapping in each direction:

* ``canonical_to_router_row``: canonical row -> router CSV row. The corpus
  builder (``scripts/model_30/build_router_corpus.py``) uses it for every source:
  v4 contributions and frozen Wavemill history alike.
* ``router_row_to_canonical``: router CSV row -> canonical row. Used only by the
  one-off legacy converter that freezes pre-v4 Wavemill history into the store
  (``scripts/model_30/convert_legacy_to_canonical.py``).

The router CSV is a wide, string-typed format. Canonical rows are typed: numbers
are floats, flags are booleans, and a value nobody recorded is ``None`` (never 0
or ``false``).

Cost trust: the builder writes a row's cost labels (``actual_cost_usd``,
``under_budget``, ``budget_violation``, per-role cost) only when its
``cost_status`` is in the trusted set. Every other row still trains success.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Collection, Mapping
from typing import Any

from src.model_30.canonical_row import (
    CANONICAL_ROW_SCHEMA_VERSION,
    COST_NO_TOKEN_EVIDENCE,
    COST_PRICED,
    COST_RECORDED_TOTAL,
    COST_UNPRICED_MODEL,
    ROUTE_ROLES,
)

ROUTER_DATASET_SCHEMA_VERSION = "wavemill-hokusai-router-dataset-v1"
LEGACY_SOURCE_KIND = "legacy_freeze"
CONTRIBUTION_SOURCE_KIND = "contribution"
# v10 trained cost on token-repriced rows and on the pre-May export's recorded
# totals (non-OpenAI only). This default reproduces it; pass a narrower set to
# train cost on token evidence only.
DEFAULT_TRUSTED_COST_STATUSES = frozenset({COST_PRICED, COST_RECORDED_TOTAL})

FIELDNAMES = [
    "schema_version",
    "run_id_hash",
    "task_id_hash",
    "timestamp",
    "source_repo_hash",
    "is_challenge",
    "challenge_pair_hash",
    "task_type",
    "language",
    "domain",
    "complexity",
    "repo_size_bucket",
    "files_touched_bucket",
    "description_length_bucket",
    "is_greenfield",
    "is_migration",
    "requires_tests",
    "cross_service",
    "ui_heavy",
    "risk_level",
    "max_cost_usd",
    "available_planner_models",
    "available_coder_models",
    "available_reviewer_models",
    "planner_model",
    "planner_agent",
    "coder_model",
    "coder_agent",
    "reviewer_model",
    "reviewer_agent",
    "plan_depth",
    "code_depth",
    "review_mode",
    "route_source",
    "router_mode",
    "routing_mode",
    "expected_success_probability",
    "expected_cost_usd",
    "confidence",
    "risk_score",
    "completed_successfully",
    "score",
    "score_band",
    "under_budget",
    "actual_cost_usd",
    "actual_time_seconds",
    "intervention_count",
    "workflow_cost_status",
    "budget_violation",
    "rubric_version",
    "rubric_criterion_count",
    "rubric_mean_score",
    "rubric_completeness",
    "rubric_correctness",
    "rubric_code_quality",
    "rubric_intervention_impact",
    "rubric_autonomy",
    "rubric_determinative_boundary",
    "rubric_provenance",
    # HOK-3401: executed-route provenance and token economics.
    "executed_route_source",
    "cost_status",
    "planner_input_tokens",
    "planner_cache_tokens",
    "planner_output_tokens",
    "planner_cost_usd",
    "coder_input_tokens",
    "coder_cache_tokens",
    "coder_output_tokens",
    "coder_cost_usd",
    "reviewer_input_tokens",
    "reviewer_cache_tokens",
    "reviewer_output_tokens",
    "reviewer_cost_usd",
    "aux_cost_usd",
    # HOK-3404: aux split; partner spend is excluded from actual_cost_usd.
    "challenge_partner_cost_usd",
    "subagent_cost_usd",
]

DESCRIPTOR_STRINGS = (
    "task_type",
    "language",
    "domain",
    "repo_size_bucket",
    "files_touched_bucket",
    "description_length_bucket",
    "risk_level",
)
DESCRIPTOR_FLAGS = ("is_greenfield", "is_migration", "requires_tests", "cross_service", "ui_heavy")
DESCRIPTOR_NUMBERS = ("complexity",)
ROUTING_STRINGS = (
    "plan_depth",
    "code_depth",
    "review_mode",
    "route_source",
    "router_mode",
    "routing_mode",
    "workflow_cost_status",
    "executed_route_source",
)
ROUTING_NUMBERS = ("expected_success_probability", "expected_cost_usd", "confidence", "risk_score")
RUBRIC_STRINGS = ("rubric_version", "rubric_determinative_boundary", "rubric_provenance")
RUBRIC_NUMBERS = (
    "rubric_criterion_count",
    "rubric_mean_score",
    "rubric_completeness",
    "rubric_correctness",
    "rubric_code_quality",
    "rubric_intervention_impact",
    "rubric_autonomy",
)
COST_BREAKDOWN = ("aux_cost_usd", "challenge_partner_cost_usd", "subagent_cost_usd")
ROUTER_ID_FIELDS = ("run_id_hash", "task_id_hash", "source_repo_hash", "challenge_pair_hash")
ROLE_TOKEN_KINDS = ("input", "cache", "output")


def stable_hash(value: str | None) -> str:
    """Return the router CSV's 16-hex pseudonymous id (as the Wavemill collector did)."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def agent_for_model(model_id: str | None) -> str:
    """Router CSV ``*_agent``: the harness family a model runs under."""
    model = model_id or ""
    if model.startswith("claude-"):
        return "claude"
    if model.startswith("gpt-"):
        return "codex"
    if model.startswith("deepseek-"):
        return "deepseek"
    return "unknown"


# --- CSV cell parsing / formatting -------------------------------------------------


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return None
    return text in {"1", "true", "yes", "y"}


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _models(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(m) for m in value if str(m).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [text]
    return [str(m) for m in parsed if str(m).strip()] if isinstance(parsed, list) else [text]


def format_number(value: Any) -> str:
    """CSV cell for a number: ``''`` when unknown, else the shortest exact form."""
    number = _number(value)
    if number is None:
        return ""
    if number.is_integer() and abs(number) < 1e15:
        return str(int(number))
    return repr(number)


def _format_flag(value: Any) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _json_list(values: Collection[str]) -> str:
    return json.dumps(list(values), separators=(",", ":"))


# --- legacy router row -> canonical ---------------------------------------------


def legacy_cost_status(router_cost_status: str, cost_usd: float | None) -> str:
    """Map the collector's per-row ``cost_status`` onto the canonical vocabulary.

    * ``recorded`` / ``repriced`` / ``recovered:*`` with a cost: repriced from
      tokens -> ``priced``.
    * ``untrusted:*`` / ``no_token_usage``: the tokens can't be used ->
      ``no_token_evidence``.
    * blank with a cost: the pre-May export's harness-recorded total, no tokens
      -> ``recorded_total``.
    """
    status = router_cost_status.strip()
    if status == "unpriced_model":
        return COST_UNPRICED_MODEL
    if cost_usd is None:
        return COST_NO_TOKEN_EVIDENCE
    if status in {"recorded", "repriced"} or status.startswith("recovered:"):
        return COST_PRICED
    if not status:
        return COST_RECORDED_TOTAL
    return COST_NO_TOKEN_EVIDENCE


def _legacy_role(row: Mapping[str, Any], role: str) -> dict[str, Any]:
    tokens = {kind: _number(row.get(f"{role}_{kind}_tokens")) for kind in ROLE_TOKEN_KINDS}
    cost = _number(row.get(f"{role}_cost_usd"))
    return {
        "requested_model": None,
        "executed_model": _text(row.get(f"{role}_model")),
        "model_evidence": "wavemill_eval_record",
        "harness": None,
        "agent": _text(row.get(f"{role}_agent")),
        "stage_count": None,
        "tokens": tokens if any(v is not None for v in tokens.values()) else None,
        "cost_usd": cost,
        "cost_status": COST_PRICED if cost is not None else COST_NO_TOKEN_EVIDENCE,
    }


def router_row_to_canonical(
    row: Mapping[str, Any],
    *,
    freeze_id: str,
    row_index: int,
    origin: str,
    price_source: str,
) -> dict[str, Any]:
    """Convert one frozen-history router CSV row to a canonical row.

    *origin* names where the row came from (``derived:evals.jsonl`` or
    ``legacy:hokusai-router-dataset.csv``); *price_source* names the price table
    its costs were computed with.
    """
    cost = _number(row.get("actual_cost_usd"))
    router_status = str(row.get("cost_status") or "")
    available = {role: _models(row.get(f"available_{role}_models")) for role in ROUTE_ROLES}
    submission_id = f"legacy/{freeze_id}"
    pair = _text(row.get("challenge_pair_hash"))
    return {
        "schema_version": CANONICAL_ROW_SCHEMA_VERSION,
        "canonical_row_id": f"{submission_id}:{row_index}",
        "submission_id": submission_id,
        "row_index": row_index,
        "source_schema_version": _text(row.get("schema_version")),
        "fidelity_tier": "training_eligible",
        "task_id": _text(row.get("task_id_hash")),
        "observed_at": _text(row.get("timestamp")),
        "task_descriptor": {
            **{key: _text(row.get(key)) for key in DESCRIPTOR_STRINGS},
            **{key: _flag(row.get(key)) for key in DESCRIPTOR_FLAGS},
            **{key: _number(row.get(key)) for key in DESCRIPTOR_NUMBERS},
        },
        "allowed_models": sorted({m for models in available.values() for m in models}),
        "available_models": available,
        "budget_usd": _number(row.get("max_cost_usd")),
        "success": _flag(row.get("completed_successfully")),
        "completion_result": None,
        "quality": {
            "score": _number(row.get("score")),
            "score_band": _text(row.get("score_band")),
            "intervention_count": _number(row.get("intervention_count")),
            "rubric": {
                **{key: _text(row.get(key)) for key in RUBRIC_STRINGS},
                **{key: _number(row.get(key)) for key in RUBRIC_NUMBERS},
            },
        },
        "duration_seconds": _number(row.get("actual_time_seconds")),
        "under_budget": _flag(row.get("under_budget")),
        "budget_violation": _flag(row.get("budget_violation")),
        "roles": {role: _legacy_role(row, role) for role in ROUTE_ROLES},
        "repair_stages": [],
        "cost_usd": cost,
        "cost_status": legacy_cost_status(router_status, cost),
        "cost_detail": router_status or None,
        "cost_breakdown": {key: _number(row.get(key)) for key in COST_BREAKDOWN},
        "unpriced_models": [],
        "price_table_version": price_source,
        "comparison_group": (
            {"id": pair, "role_varied": None} if _flag(row.get("is_challenge")) else None
        ),
        "routing_join": None,
        "routing_context": {
            **{key: _text(row.get(key)) for key in ROUTING_STRINGS},
            **{key: _number(row.get(key)) for key in ROUTING_NUMBERS},
        },
        "router_ids": {key: _text(row.get(key)) for key in ROUTER_ID_FIELDS},
        "contributor_id": None,
        "source": {
            "kind": LEGACY_SOURCE_KIND,
            "harness": "wavemill",
            "sdk_version": None,
            "freeze_id": freeze_id,
            "origin": origin,
        },
        "contributor_reported_cost_usd": None,
    }


# --- canonical -> router row -----------------------------------------------------


def source_kind(record: Mapping[str, Any]) -> str:
    """``legacy_freeze`` for frozen history, else ``contribution``."""
    source = record.get("source") if isinstance(record.get("source"), Mapping) else {}
    return str(source.get("kind") or CONTRIBUTION_SOURCE_KIND)


def _router_ids(record: Mapping[str, Any]) -> dict[str, str]:
    stored = record.get("router_ids") if isinstance(record.get("router_ids"), Mapping) else {}
    if stored:
        return {key: str(stored.get(key) or "") for key in ROUTER_ID_FIELDS}
    group = record.get("comparison_group")
    group_id = group.get("id") if isinstance(group, Mapping) else None
    return {
        "run_id_hash": stable_hash(str(record.get("canonical_row_id") or "")),
        "task_id_hash": stable_hash(str(record.get("task_id") or "")),
        "source_repo_hash": stable_hash(str(record.get("contributor_id") or "")),
        "challenge_pair_hash": stable_hash(str(group_id or "")),
    }


def _available(record: Mapping[str, Any], role: str) -> list[str]:
    by_role = record.get("available_models")
    if isinstance(by_role, Mapping) and by_role.get(role) is not None:
        return list(by_role[role])
    return list(record.get("allowed_models") or [])


def _role_cache(tokens: Mapping[str, Any]) -> float | None:
    if "cache" in tokens:
        return _number(tokens.get("cache"))
    read, write = _number(tokens.get("cache_read")), _number(tokens.get("cache_write"))
    if read is None and write is None:
        return None
    return (read or 0.0) + (write or 0.0)


def _role_columns(role: str, record: Mapping[str, Any], trusted: bool) -> dict[str, str]:
    data = (record.get("roles") or {}).get(role) or {}
    model = data.get("executed_model") or data.get("requested_model") or ""
    tokens = data.get("tokens") if isinstance(data.get("tokens"), Mapping) else {}
    return {
        f"{role}_model": model,
        f"{role}_agent": data.get("agent") or agent_for_model(model),
        f"{role}_input_tokens": format_number(tokens.get("input")),
        f"{role}_cache_tokens": format_number(_role_cache(tokens)) if tokens else "",
        f"{role}_output_tokens": format_number(tokens.get("output")),
        f"{role}_cost_usd": format_number(data.get("cost_usd")) if trusted else "",
    }


def _aux_cost(record: Mapping[str, Any]) -> float | None:
    """Spend outside the three roles: v4 repair stages (frozen rows store their split)."""
    repairs = record.get("repair_stages") or []
    if not repairs:
        return None
    costs = [_number(stage.get("cost_usd")) for stage in repairs]
    return None if any(c is None for c in costs) else sum(c for c in costs if c is not None)


def _budget_flags(
    record: Mapping[str, Any], cost: float | None, budget: float | None
) -> tuple[bool | None, bool | None]:
    """Return stored flags (frozen history), else derive them from a trusted cost.

    Frozen pre-May rows keep the export's ``budget_violation`` even without a
    cost (v10 trained on it). Contributions store none, so an untrusted cost
    gives no budget labels.
    """
    under, violation = record.get("under_budget"), record.get("budget_violation")
    if under is None and violation is None and cost is not None and budget is not None:
        return cost <= budget, cost > budget
    return under, violation


def canonical_to_router_row(
    record: Mapping[str, Any],
    *,
    trusted_cost_statuses: Collection[str] = DEFAULT_TRUSTED_COST_STATUSES,
) -> dict[str, str]:
    """Return the router CSV row for one canonical row."""
    trusted = record.get("cost_status") in trusted_cost_statuses
    cost = _number(record.get("cost_usd")) if trusted else None
    budget = _number(record.get("budget_usd"))
    under, violation = _budget_flags(record, cost, budget)
    legacy = source_kind(record) == LEGACY_SOURCE_KIND
    descriptor = record.get("task_descriptor") or {}
    quality = record.get("quality") or {}
    rubric = quality.get("rubric") or {}
    routing = record.get("routing_context") or {}
    breakdown = record.get("cost_breakdown") or {"aux_cost_usd": _aux_cost(record)}
    success = record.get("success")
    score = _number(quality.get("score"))
    if score is None and success is not None:
        score = 1.0 if success else 0.0
    row: dict[str, str] = {
        "schema_version": ROUTER_DATASET_SCHEMA_VERSION,
        **_router_ids(record),
        "timestamp": str(record.get("observed_at") or ""),
        "is_challenge": _format_flag(record.get("comparison_group") is not None),
        **{key: str(descriptor.get(key) or "") for key in DESCRIPTOR_STRINGS},
        **{key: _format_flag(descriptor.get(key)) for key in DESCRIPTOR_FLAGS},
        **{key: format_number(descriptor.get(key)) for key in DESCRIPTOR_NUMBERS},
        "max_cost_usd": format_number(budget),
        **{
            f"available_{role}_models": _json_list(_available(record, role)) for role in ROUTE_ROLES
        },
        **{
            column: value
            for role in ROUTE_ROLES
            for column, value in _role_columns(role, record, trusted).items()
        },
        **{key: str(routing.get(key) or "") for key in ROUTING_STRINGS},
        **{key: format_number(routing.get(key)) for key in ROUTING_NUMBERS},
        "completed_successfully": _format_flag(success),
        "score": format_number(score),
        "score_band": str(quality.get("score_band") or ""),
        "intervention_count": format_number(quality.get("intervention_count")),
        **{key: str(rubric.get(key) or "") for key in RUBRIC_STRINGS},
        **{key: format_number(rubric.get(key)) for key in RUBRIC_NUMBERS},
        "under_budget": _format_flag(under),
        "budget_violation": _format_flag(violation),
        "actual_cost_usd": format_number(cost),
        "actual_time_seconds": format_number(record.get("duration_seconds")),
        # Frozen rows keep the collector's detailed status; contributions the canonical one.
        "cost_status": str(
            (record.get("cost_detail") if legacy else record.get("cost_status")) or ""
        ),
        **{key: format_number(breakdown.get(key)) for key in COST_BREAKDOWN},
    }
    if not legacy:
        row["executed_route_source"] = "stage_executions"
    return {name: row.get(name, "") for name in FIELDNAMES}
