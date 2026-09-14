"""Normalize Model 30 contribution rows into router-training rows."""

from __future__ import annotations

import json
from typing import Any

ROUTER_FIELDNAMES = [
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
    "task_description",
]


def router_fieldnames() -> list[str]:
    """Return router CSV field names, including runner-only feature columns."""
    return list(ROUTER_FIELDNAMES)


def is_router_training_row(row: dict[str, Any]) -> bool:
    """Return true when a row is already in router-training shape."""
    return all(row.get(column) not in {None, ""} for column in ("planner_model", "coder_model"))


def is_compact_wavemill_row(row: dict[str, Any]) -> bool:
    """Return true for the compact Wavemill contribution shape accepted in production."""
    inputs = row.get("inputs")
    return (
        isinstance(inputs, dict)
        and "task_id" in row
        and "success_under_budget" in row
        and "actual_cost_usd" in row
    )


def benchmark_row_to_router_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert an assembled benchmark contribution row into router CSV shape."""
    descriptor = _descriptor(row)
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    allowed_models = [str(value) for value in row.get("allowed_models", []) if str(value)]
    selected_models = [str(value) for value in row.get("selected_models", []) if str(value)]
    planner_model, coder_model, reviewer_model = _selected_by_role(selected_models)
    expected_success = row.get("estimated_success_under_budget")
    if expected_success is None:
        expected_success = 1.0 if row.get("completed_successfully") is True else 0.0
    max_cost = row.get("max_cost_usd")
    actual_cost = row.get("actual_cost_usd")
    under_budget = (
        isinstance(max_cost, (int, float))
        and isinstance(actual_cost, (int, float))
        and actual_cost <= max_cost
    )
    completed = row.get("completed_successfully") is True
    score = 1.0 if completed and under_budget else 0.0

    converted = _empty_router_row()
    converted.update(
        {
            "schema_version": "wavemill-hokusai-router-dataset-v1",
            "run_id_hash": str(row.get("eval_id", "")),
            "task_id_hash": str(row.get("row_id", "")),
            "timestamp": str(row.get("observed_at", "")),
            "task_type": str(descriptor.get("task_type") or metadata.get("task_type") or "unknown"),
            "language": str(descriptor.get("language") or metadata.get("language") or "unknown"),
            "domain": str(descriptor.get("domain") or metadata.get("domain") or "backend"),
            "complexity": str(
                descriptor.get("complexity")
                or descriptor.get("estimated_complexity")
                or metadata.get("complexity")
                or ""
            ),
            "repo_size_bucket": str(
                descriptor.get("repo_size_bucket") or metadata.get("repo_size_bucket") or "medium"
            ),
            "description_length_bucket": "medium",
            "requires_tests": str(
                descriptor.get("requires_tests") or metadata.get("requires_tests") or False
            ).lower(),
            "risk_level": str(descriptor.get("risk_level") or metadata.get("risk_level") or "low"),
            "max_cost_usd": _optional_number(max_cost),
            "available_planner_models": _json_list(allowed_models),
            "available_coder_models": _json_list(allowed_models),
            "available_reviewer_models": _json_list(allowed_models),
            "planner_model": planner_model,
            "coder_model": coder_model,
            "reviewer_model": reviewer_model,
            "route_source": "contribution",
            "expected_success_probability": _optional_number(expected_success),
            "expected_cost_usd": _optional_number(row.get("estimated_cost_usd") or actual_cost),
            "confidence": _optional_number(expected_success),
            "completed_successfully": str(completed).lower(),
            "score": str(score),
            "under_budget": str(under_budget).lower(),
            "actual_cost_usd": _optional_number(actual_cost),
            "actual_time_seconds": _optional_number(row.get("actual_time_seconds")),
        }
    )
    converted["task_description"] = _descriptor_text(descriptor, row)
    return converted


def compact_wavemill_row_to_router_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert the live compact Wavemill contribution shape into router CSV shape."""
    inputs = row.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("compact Wavemill row is missing inputs")
    planner_model = str(inputs.get("planner_model") or "")
    coder_model = str(inputs.get("coder_model") or "")
    reviewer_model = str(inputs.get("reviewer_model") or "")
    selected_models = [model for model in (planner_model, coder_model, reviewer_model) if model]
    success_under_budget = bool(row.get("success_under_budget"))
    rubric_score = inputs.get("rubric_mean_score")
    score = rubric_score if isinstance(rubric_score, (int, float)) else float(success_under_budget)

    converted = _empty_router_row()
    converted.update(
        {
            "schema_version": "wavemill-hokusai-router-dataset-v1",
            "run_id_hash": str(row.get("task_id") or ""),
            "task_id_hash": str(row.get("task_id") or ""),
            "task_type": str(inputs.get("task_type") or "unknown"),
            "language": str(inputs.get("language") or "unknown"),
            "domain": str(inputs.get("domain") or "backend"),
            "repo_size_bucket": str(inputs.get("repo_size_bucket") or "medium"),
            "description_length_bucket": "medium",
            "requires_tests": str(bool(inputs.get("requires_tests"))).lower(),
            "risk_level": str(inputs.get("risk_level") or "low"),
            "available_planner_models": _json_list(selected_models),
            "available_coder_models": _json_list(selected_models),
            "available_reviewer_models": _json_list(selected_models),
            "planner_model": planner_model,
            "coder_model": coder_model,
            "reviewer_model": reviewer_model,
            "route_source": "contribution",
            "expected_success_probability": str(float(success_under_budget)),
            "expected_cost_usd": _optional_number(row.get("actual_cost_usd")),
            "confidence": str(float(success_under_budget)),
            "completed_successfully": str(success_under_budget).lower(),
            "score": _optional_number(score),
            "under_budget": str(success_under_budget).lower(),
            "actual_cost_usd": _optional_number(row.get("actual_cost_usd")),
            "actual_time_seconds": _optional_number(row.get("wall_clock_seconds")),
            "intervention_count": _optional_number(inputs.get("intervention_count")),
            "rubric_version": _optional_number(inputs.get("rubric_version")),
            "rubric_mean_score": _optional_number(inputs.get("rubric_mean_score")),
            "rubric_determinative_boundary": _optional_number(inputs.get("determinative_boundary")),
            "task_description": str(row.get("task_id") or ""),
        }
    )
    return converted


def contribution_row_to_router_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize any accepted Model 30 contribution row into router CSV shape."""
    if is_router_training_row(row):
        converted = _empty_router_row()
        converted.update({key: value for key, value in row.items() if key in converted})
        return converted
    if is_compact_wavemill_row(row):
        return compact_wavemill_row_to_router_csv_row(row)
    return benchmark_row_to_router_csv_row(row)


def _empty_router_row() -> dict[str, Any]:
    return {field: "" for field in router_fieldnames()}


def _json_list(values: Any) -> str:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        values = []
    return json.dumps([str(value) for value in values if str(value)], separators=(",", ":"))


def _descriptor(row: dict[str, Any]) -> dict[str, Any]:
    descriptor = row.get("task_descriptor")
    return descriptor if isinstance(descriptor, dict) else {}


def _descriptor_text(descriptor: dict[str, Any], row: dict[str, Any]) -> str:
    for key in ("description", "task_description", "title", "prompt"):
        value = descriptor.get(key) or row.get(key)
        if value:
            return str(value)
    return json.dumps(descriptor, sort_keys=True, separators=(",", ":"))


def _selected_by_role(selected_models: list[str]) -> tuple[str, str, str]:
    if not selected_models:
        return "", "", ""
    if len(selected_models) == 1:
        return selected_models[0], selected_models[0], selected_models[0]
    if len(selected_models) == 2:
        return selected_models[0], selected_models[1], selected_models[1]
    return selected_models[0], selected_models[1], selected_models[2]


def _optional_number(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
