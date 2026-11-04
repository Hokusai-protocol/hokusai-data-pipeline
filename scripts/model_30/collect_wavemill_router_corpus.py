"""Derive router rows from Wavemill eval records (legacy converter internals, HOK-3414).

This is not a training entry point. Model 30 trains from canonical rows only
(``scripts/model_30/build_router_corpus.py``). The one reader of eval records is
the legacy converter (``scripts/model_30/convert_legacy_to_canonical.py``), which
calls ``derive_router_rows`` once to freeze Wavemill history into the store.
Prebuilt router CSV exports are never read here: they went stale (HOK-3391).
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30.executed_route import (  # noqa: E402
    challenge_partner_models,
    load_challenge_records,
    resolve_executed_route,
    route_economics,
)
from scripts.model_30.recover_session_usage import record_key  # noqa: E402
from src.model_30.model_identity import (  # noqa: E402
    is_supported_model_id,
    latest_snapshot,
    normalize_model_id,
)
from src.model_30.router_corpus import (  # noqa: E402
    FIELDNAMES,  # noqa: F401  (re-exported for tests)
    ROUTER_DATASET_SCHEMA_VERSION,
    agent_for_model,
    format_number,
    stable_hash,
)

EVAL_FILENAME = "evals.jsonl"


def discover_wavemill_eval_files(
    search_roots: list[Path],
    *,
    include_worktrees: bool = False,
) -> list[Path]:
    """Return current Wavemill eval logs under the provided roots."""
    files: set[Path] = set()
    for root in search_roots:
        if root.is_file() and root.name == EVAL_FILENAME:
            files.add(root.resolve())
            continue
        if not root.exists():
            continue
        files.update(path.resolve() for path in root.glob(f"**/.wavemill/evals/{EVAL_FILENAME}"))
    return sorted(path for path in files if include_worktrees or not _is_worktree_path(path))


def derive_router_rows(
    search_roots: list[Path],
    *,
    recovered_usage: dict[str, Any] | None = None,
    include_worktrees: bool = False,
) -> tuple[list[dict[str, str]], dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    """Derive router rows from every ``evals.jsonl`` under *search_roots*.

    Returns ``(rows, report, price_snapshots)``. *recovered_usage* is the
    ``records`` map from ``recover_session_usage.py`` (HOK-3402).
    """
    eval_files = discover_wavemill_eval_files(search_roots, include_worktrees=include_worktrees)
    rows: list[dict[str, str]] = []
    report: dict[str, Any] = {
        "source_files": [],
        "records_read": 0,
        "rows_derived": 0,
        "records_skipped": 0,
        "skip_reasons": {},
    }
    skip_reasons: Counter[str] = Counter()
    # Challenge pairs are often recorded in a different repo than the eval that
    # ran them, so resolve against every discovered challenge-records file.
    challenge_records: dict[str, dict[str, Any]] = {}
    for eval_file in eval_files:
        challenge_records.update(load_challenge_records(eval_file.parent))
    report["challenge_records_loaded"] = len(challenge_records)
    recovered_usage = recovered_usage or {}
    report["recovered_usage_records_loaded"] = len(recovered_usage)
    fallback_snapshot = latest_snapshot(_pricing_snapshots(eval_files)) if recovered_usage else {}
    price_snapshots: list[tuple[str, dict[str, Any]]] = []
    for eval_file in eval_files:
        file_report = _derive_rows_from_eval_file(
            eval_file,
            rows,
            skip_reasons,
            challenge_records,
            price_snapshots,
            recovered_usage,
            fallback_snapshot,
        )
        report["source_files"].append(file_report)
        for key in ("records_read", "rows_derived", "records_skipped"):
            report[key] += file_report[key]
    report["skip_reasons"] = dict(sorted(skip_reasons.items()))
    return rows, report, price_snapshots


def _derive_rows_from_eval_file(
    eval_file: Path,
    output_rows: list[dict[str, str]],
    skip_reasons: Counter[str],
    challenge_records: dict[str, dict[str, Any]] | None = None,
    price_snapshots: list[tuple[str, dict[str, Any]]] | None = None,
    recovered_usage: dict[str, Any] | None = None,
    fallback_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_repo = _source_repo_name(eval_file)
    file_report = {
        "path": str(eval_file),
        "source_repo": source_repo,
        "records_read": 0,
        "rows_derived": 0,
        "records_skipped": 0,
        "skip_reasons": {},
    }
    file_skip_reasons: Counter[str] = Counter()
    if challenge_records is None:
        challenge_records = load_challenge_records(eval_file.parent)
    with eval_file.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            file_report["records_read"] += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                _record_skip("malformed_json", skip_reasons, file_skip_reasons)
                continue

            if price_snapshots is not None and isinstance(record.get("pricingSnapshot"), dict):
                price_snapshots.append(
                    (str(record.get("timestamp") or ""), record["pricingSnapshot"])
                )
            row, reason = eval_record_to_router_row(
                record,
                source_repo=source_repo,
                challenge_records=challenge_records,
                recovered_usage=recovered_usage,
                fallback_snapshot=fallback_snapshot,
            )
            if reason is not None:
                _record_skip(reason, skip_reasons, file_skip_reasons)
                continue
            if row is None:
                _record_skip("empty_row", skip_reasons, file_skip_reasons)
                continue
            row["run_id_hash"] = stable_hash(f"{eval_file}:{line_number}:{record.get('id', '')}")
            output_rows.append(row)
            file_report["rows_derived"] += 1

    file_report["records_skipped"] = sum(file_skip_reasons.values())
    file_report["skip_reasons"] = dict(sorted(file_skip_reasons.items()))
    return file_report


def eval_record_to_router_row(
    record: dict[str, Any],
    *,
    source_repo: str,
    challenge_records: dict[str, dict[str, Any]] | None = None,
    recovered_usage: dict[str, Any] | None = None,
    fallback_snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, str] | None, str | None]:
    """Convert one Wavemill eval record to the router training CSV row shape."""
    if not (record.get("trainingEligible") or record.get("budgetEvalEligible")):
        return None, "not_training_or_budget_eligible"

    task_descriptor = _dict(record.get("taskDescriptor"))
    stages = _dict(task_descriptor.get("stages"))
    if not stages:
        stages = _dict(_dict(record.get("routeProvenance")).get("activeRoute"))
    route_prediction = _dict(record.get("routePrediction"))
    constraints = _dict(task_descriptor.get("constraints")) or _dict(record.get("constraints"))
    heuristic = _dict(_dict(task_descriptor.get("signals")).get("heuristic"))
    learned = _dict(_dict(task_descriptor.get("signals")).get("learned"))
    task_context = _dict(record.get("taskContext"))
    repo_context = _dict(record.get("repoContext"))
    outcome = _dict(record.get("outcome"))
    outcomes = _dict(record.get("outcomes"))
    rubric = _dict(task_descriptor.get("rubric")) or _dict(record.get("rubricEval"))
    rubric_criteria = _dict(_dict(rubric.get("criteria_scores")) or _dict(rubric.get("criteria")))

    planner_model = _stage_model(stages, "planner")
    coder_model = _stage_model(stages, "coder") or _string(record.get("modelId"))
    reviewer_model = _stage_model(stages, "reviewer")
    if not planner_model or not coder_model or not reviewer_model:
        return None, "missing_stage_model"

    resolution, reason = _executed_route(
        record,
        {"planner": planner_model, "coder": coder_model, "reviewer": reviewer_model},
        challenge_records,
    )
    if resolution is None:
        return None, reason
    planner_model = resolution.route["planner"]
    coder_model = resolution.route["coder"]
    reviewer_model = resolution.route["reviewer"]

    available_models = _string_list(
        constraints.get("models_available") or constraints.get("allowed_models")
    )
    if not available_models:
        return None, "missing_available_models"
    available_models = _normalized_pool(available_models, resolution.route)

    max_cost = _number(constraints.get("max_cost_usd") or record.get("maxCostUsd"))
    if max_cost is None:
        max_cost = _number(_dict(record.get("constraints")).get("maxCostUsd"))
    if max_cost is None or max_cost <= 0:
        max_cost = 25.0

    actual_cost = _first_number(
        record.get("workflowCost"),
        outcome.get("total_cost_usd"),
        record.get("estimatedCost"),
        route_prediction.get("expectedCostUsd"),
    )
    economics = route_economics(
        record,
        resolution.route,
        challenge_partner_models(record, resolution.route, challenge_records),
        (recovered_usage or {}).get(record_key(record)),
        fallback_snapshot,
    )
    if economics.cost_status == "unpriced_model":
        return None, "unpriced_model_cost"
    actual_cost = _route_actual_cost(economics, actual_cost)

    score = _first_number(
        record.get("score"),
        outcome.get("overall_score"),
        rubric.get("mean_score"),
    )
    if score is None:
        score = 1.0 if _completed_successfully(record, outcomes) else 0.0

    task_type = _first_string(
        heuristic.get("task_type"),
        route_prediction.get("taskType"),
        task_context.get("taskType"),
        "unknown",
    )
    language = _first_string(_first_item(heuristic.get("languages")), "unknown")
    domain = _first_string(
        learned.get("domain"),
        task_context.get("requiresDomainKnowledge"),
        "unknown",
    )
    complexity = _first_number(learned.get("complexity"), route_prediction.get("complexityScore"))
    files_touched = _first_number(
        heuristic.get("files_touched"),
        _dict(record.get("difficultySignals")).get("filesTouched"),
    )
    risk_score = _first_number(
        route_prediction.get("riskScore"),
        _dict(record.get("difficultySignals")).get("riskScore"),
    )
    timestamp = _first_string(record.get("timestamp"), record.get("observed_at"), "")

    row = {
        "schema_version": ROUTER_DATASET_SCHEMA_VERSION,
        "run_id_hash": "",
        "task_id_hash": stable_hash(_first_string(record.get("id"), record.get("issueId"), "")),
        "timestamp": timestamp,
        "source_repo_hash": stable_hash(source_repo),
        "is_challenge": _bool_string(bool(record.get("challengePairId"))),
        "challenge_pair_hash": stable_hash(_string(record.get("challengePairId"))),
        "task_type": task_type,
        "language": language,
        "domain": domain,
        "complexity": _format_number(complexity) if complexity is not None else "",
        "repo_size_bucket": _repo_size_bucket(repo_context),
        "files_touched_bucket": _files_bucket(files_touched),
        "description_length_bucket": _description_length_bucket(record.get("originalPrompt")),
        "is_greenfield": _bool_string(heuristic.get("is_greenfield")),
        "is_migration": _bool_string(heuristic.get("has_migration")),
        "requires_tests": _bool_string(heuristic.get("has_tests")),
        "cross_service": _bool_string(heuristic.get("cross_service")),
        "ui_heavy": _bool_string(heuristic.get("has_ui")),
        "risk_level": _risk_level(risk_score),
        "max_cost_usd": _format_number(max_cost),
        "available_planner_models": _json_list(available_models),
        "available_coder_models": _json_list(available_models),
        "available_reviewer_models": _json_list(available_models),
        "planner_model": planner_model,
        "planner_agent": agent_for_model(planner_model),
        "coder_model": coder_model,
        "coder_agent": agent_for_model(coder_model),
        "reviewer_model": reviewer_model,
        "reviewer_agent": agent_for_model(reviewer_model),
        "plan_depth": _first_string(stages.get("planDepth"), record.get("planDepth"), ""),
        "code_depth": _first_string(stages.get("codeDepth"), record.get("codeDepth"), ""),
        "review_mode": _first_string(stages.get("reviewMode"), record.get("reviewMode"), ""),
        "route_source": _first_string(
            _dict(record.get("routeProvenance")).get("decisionSource"),
            "",
        ),
        "router_mode": _first_string(_dict(record.get("routeProvenance")).get("routerMode"), ""),
        "routing_mode": _first_string(_dict(record.get("routeProvenance")).get("routingMode"), ""),
        "expected_success_probability": _format_optional_number(
            route_prediction.get("expectedSuccess")
        ),
        "expected_cost_usd": _format_optional_number(route_prediction.get("expectedCostUsd")),
        "confidence": _format_optional_number(route_prediction.get("confidence")),
        "risk_score": _format_optional_number(risk_score),
        "completed_successfully": _bool_string(_completed_successfully(record, outcomes)),
        "score": _format_number(score),
        "score_band": _first_string(record.get("scoreBand"), ""),
        "under_budget": "" if actual_cost is None else _bool_string(actual_cost <= max_cost),
        "actual_cost_usd": "" if actual_cost is None else _format_number(actual_cost),
        "actual_time_seconds": _format_optional_number(_duration_seconds(record, outcome)),
        "intervention_count": _format_optional_number(record.get("interventionCount")),
        "workflow_cost_status": _first_string(record.get("workflowCostStatus"), ""),
        "budget_violation": "" if actual_cost is None else _bool_string(actual_cost > max_cost),
        "rubric_version": _first_string(rubric.get("rubric_version"), ""),
        "rubric_criterion_count": _format_optional_number(
            rubric.get("criterion_count") or len(rubric_criteria)
        ),
        "rubric_mean_score": _format_optional_number(
            rubric.get("mean_score") or _mean_rubric_score(rubric_criteria)
        ),
        "rubric_completeness": _format_optional_number(
            _rubric_score(rubric_criteria, "completeness")
        ),
        "rubric_correctness": _format_optional_number(
            _rubric_score(rubric_criteria, "correctness")
        ),
        "rubric_code_quality": _format_optional_number(
            _rubric_score(rubric_criteria, "code_quality")
        ),
        "rubric_intervention_impact": _format_optional_number(
            _rubric_score(rubric_criteria, "intervention_impact")
        ),
        "rubric_autonomy": _format_optional_number(_rubric_score(rubric_criteria, "autonomy")),
        "rubric_determinative_boundary": _first_string(
            rubric.get("determinative_boundary"),
            "",
        ),
        "rubric_provenance": "wavemill-evals-jsonl",
        "executed_route_source": resolution.source,
        "cost_status": economics.cost_status,
        **{
            f"{role}_{kind}": _format_optional_number(values.get(role))
            for role in ("planner", "coder", "reviewer")
            for kind, values in (
                ("input_tokens", economics.role_input_tokens),
                ("cache_tokens", economics.role_cache_tokens),
                ("output_tokens", economics.role_output_tokens),
                ("cost_usd", economics.role_cost_usd),
            )
        },
        "aux_cost_usd": _format_optional_number(economics.aux_cost_usd),
        "challenge_partner_cost_usd": _format_optional_number(economics.challenge_partner_cost_usd),
        "subagent_cost_usd": _format_optional_number(economics.subagent_cost_usd),
    }
    return row, None


def _pricing_snapshots(eval_files: list[Path]) -> list[tuple[str, dict[str, Any]]]:
    """``(timestamp, pricingSnapshot)`` pairs from every eval record in *eval_files*."""
    snapshots = []
    for eval_file in eval_files:
        with eval_file.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict) and isinstance(record.get("pricingSnapshot"), dict):
                    snapshots.append(
                        (str(record.get("timestamp") or ""), record["pricingSnapshot"])
                    )
    return snapshots


def _executed_route(
    record: dict[str, Any],
    stage_route: dict[str, str],
    challenge_records: dict[str, dict[str, Any]] | None,
) -> tuple[Any, str | None]:
    """Resolve the executed route; return (resolution, None) or (None, skip reason)."""
    resolution = resolve_executed_route(record, stage_route, challenge_records)
    if resolution.exclusion_reason is not None:
        return None, resolution.exclusion_reason
    if not all(is_supported_model_id(m) for m in resolution.route.values()):
        return None, "unsupported_executed_model"
    return resolution, None


def _normalized_pool(models: list[str], route: dict[str, str]) -> list[str]:
    """Catalog-spelled available models, always including the executed route."""
    return sorted(
        {normalize_model_id(m) for m in models if is_supported_model_id(m)} | set(route.values())
    )


def _route_actual_cost(economics: Any, recorded_cost: float | None) -> float | None:
    """Repriced cost when known; None when token data is contaminated (HOK-3402)."""
    if economics.cost_status.startswith("untrusted:"):
        return None
    if economics.total_cost_usd is not None:
        return economics.total_cost_usd
    return 0.0 if recorded_cost is None else recorded_cost


def _record_skip(reason: str, global_counter: Counter[str], file_counter: Counter[str]) -> None:
    global_counter[reason] += 1
    file_counter[reason] += 1


def _source_repo_name(path: Path) -> str:
    parts = path.resolve().parts
    if ".wavemill" not in parts:
        return path.parent.name
    index = parts.index(".wavemill")
    return parts[index - 1] if index > 0 else path.parent.name


def _is_worktree_path(path: Path) -> bool:
    return "worktrees" in path.resolve().parts


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _first_string(*values: Any) -> str:
    for value in values:
        text = _string(value)
        if text:
            return text
    return ""


def _first_item(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({str(item).strip() for item in value if str(item).strip()})
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value.strip()]
        return _string_list(parsed)
    return []


def _stage_model(stages: dict[str, Any], role: str) -> str:
    stage = _dict(stages.get(role))
    return _first_string(stage.get("model"), stages.get(f"{role}_model"))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first_number(*values: Any) -> float | None:
    for value in values:
        number = _number(value)
        if number is not None:
            return number
    return None


def _format_number(value: Any) -> str:
    # Exact (HOK-3414): frozen history must not keep the old 6-significant-figure ``%g``.
    return format_number(_number(value))


def _format_optional_number(value: Any) -> str:
    return _format_number(value)


def _json_list(values: list[str]) -> str:
    return json.dumps(values, separators=(",", ":"))


def _bool_string(value: Any) -> str:
    if isinstance(value, str):
        return "true" if value.strip().lower() in {"1", "true", "yes", "y"} else "false"
    return "true" if bool(value) else "false"


def _repo_size_bucket(repo_context: dict[str, Any]) -> str:
    loc = _number(_dict(repo_context.get("repoSize")).get("loc"))
    if loc is None:
        return "unknown"
    if loc < 25_000:
        return "small"
    if loc < 150_000:
        return "medium"
    return "large"


def _files_bucket(value: Any) -> str:
    count = _number(value)
    if count is None:
        return "unknown"
    if count <= 1:
        return "1"
    if count <= 5:
        return "2_5"
    if count <= 15:
        return "6_15"
    return "16_plus"


def _description_length_bucket(value: Any) -> str:
    token_count = len(_string(value).split())
    if token_count <= 200:
        return "short"
    if token_count <= 1000:
        return "medium"
    return "long"


def _risk_level(value: Any) -> str:
    risk_score = _number(value)
    if risk_score is None:
        return "unknown"
    if risk_score < 6:
        return "low"
    if risk_score < 14:
        return "medium"
    return "high"


def _completed_successfully(record: dict[str, Any], outcomes: dict[str, Any]) -> bool:
    if isinstance(outcomes.get("success"), bool):
        return bool(outcomes["success"])
    score = _number(record.get("score"))
    if score is not None:
        return score >= 0.7
    return bool(record.get("trainingEligible") or record.get("budgetEvalEligible"))


def _duration_seconds(record: dict[str, Any], outcome: dict[str, Any]) -> float | None:
    duration = _first_number(
        record.get("timeSeconds"),
        _dict(record.get("phaseDurationsSeconds")).get("total"),
    )
    if duration is not None:
        return duration
    minutes = _number(outcome.get("total_time_minutes"))
    return minutes * 60.0 if minutes is not None else None


def _rubric_score(criteria: dict[str, Any], key: str) -> float | None:
    value = criteria.get(key)
    if isinstance(value, dict):
        return _number(value.get("score"))
    return _number(value)


def _mean_rubric_score(criteria: dict[str, Any]) -> float | None:
    scores = [
        score for score in (_rubric_score(criteria, key) for key in criteria) if score is not None
    ]
    return sum(scores) / len(scores) if scores else None
