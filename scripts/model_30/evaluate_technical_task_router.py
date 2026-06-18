"""Evaluate Model 30 router artifacts against a fixed technical-task holdout.

MLflow authentication follows the SDK environment, including
``MLFLOW_TRACKING_TOKEN`` when the registry requires bearer auth.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mlflow
import mlflow.pyfunc
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.scorers import resolve_scorer  # noqa: E402
from src.utils.metric_naming import derive_mlflow_name  # noqa: E402

V1_SCORER_REFS: tuple[str, ...] = (
    "technical_task_router.feasibility/v1",
    "technical_task_router.success_under_budget/v1",
    "technical_task_router.benchmark_score/v1",
    "technical_task_router.invalid_selection_rate/v1",
    "technical_task_router.cost_mae_usd/v1",
    "technical_task_router.duration_mae_seconds/v1",
    "technical_task_router.reliability_brier_score/v1",
    "technical_task_router.lowest_cost_success_under_budget/v1",
    "technical_task_router.fastest_completion_success_under_budget/v1",
    "technical_task_router.highest_reliability_success_under_budget/v1",
)
V2_SCORER_REFS: tuple[str, ...] = (
    "technical_task_router.feasibility/v1",
    "technical_task_router.success_under_budget/v1",
    "technical_task_router.benchmark_score/v1",
    "technical_task_router.invalid_selection_rate/v1",
    "technical_task_router.cost_efficiency/v2",
    "technical_task_router.sparse_cell_generalization/v2",
    "technical_task_router.candidate_pool_robustness/v2",
    "technical_task_router.benchmark_score/v2",
    "technical_task_router.cost_mae_usd/v1",
    "technical_task_router.duration_mae_seconds/v1",
    "technical_task_router.reliability_brier_score/v1",
    "technical_task_router.lowest_cost_success_under_budget/v1",
    "technical_task_router.fastest_completion_success_under_budget/v1",
    "technical_task_router.highest_reliability_success_under_budget/v1",
)

DEFAULT_V1_PRIMARY_METRIC = "technical_task_router.benchmark_score_v1"
DEFAULT_V2_PRIMARY_METRIC = "technical_task_router.benchmark_score_v2"
V1_BENCHMARK_SPEC_ID = "technical-task-router-baseline-v1"
V2_BENCHMARK_SPEC_ID = "technical_task_router.benchmark_score/v2"
V2_SCENARIOS: tuple[str, ...] = (
    "production_pool",
    "challenger_present",
    "dominant_model_removed",
    "low_budget",
    "sparse_cell",
)
CHALLENGER_MODELS: tuple[str, ...] = ("qwen3-coder-plus",)
DOMINANT_MODEL_PREFIXES: tuple[str, ...] = ("gpt-5.4",)
LOW_BUDGET_MULTIPLIER = 0.5

OBJECTIVES: tuple[str, ...] = ("lowest_cost", "fastest_completion", "highest_reliability")
ROLE_AVAILABLE_COLUMNS = {
    "planner": "available_planner_models",
    "coder": "available_coder_models",
    "reviewer": "available_reviewer_models",
}
ROLE_SELECTED_COLUMNS = {
    "planner": "planner_model",
    "coder": "coder_model",
    "reviewer": "reviewer_model",
}


@dataclass(frozen=True)
class HoldoutRows:
    """Validated holdout rows and quarantine diagnostics."""

    rows: list[dict[str, str]]
    total_rows: int
    quarantine_reasons: dict[str, int]


@dataclass(frozen=True)
class DurationCoverage:
    """Duration label coverage summary for benchmark rows."""

    evaluated_rows: int
    positive_label_rows: int
    rows_with_predictions: int

    @property
    def positive_label_fraction(self: DurationCoverage) -> float:
        return self.positive_label_rows / self.evaluated_rows if self.evaluated_rows else 0.0

    @property
    def prediction_fraction_within_positive_labels(self: DurationCoverage) -> float | None:
        if self.positive_label_rows == 0:
            return None
        return self.rows_with_predictions / self.positive_label_rows


@dataclass(frozen=True)
class _NeighborBlock:
    row_start: int
    row_end: int
    submission_id: str
    wallet: str | None
    account_id: str | None


class _NeighborResolver:
    """Resolve training row indices back to manifest contributor provenance."""

    def __init__(self: _NeighborResolver, blocks: list[_NeighborBlock]) -> None:
        self._blocks = sorted(blocks, key=lambda block: block.row_start)
        self._starts = [block.row_start for block in self._blocks]

    @classmethod
    def from_manifest(
        cls: type[_NeighborResolver],
        manifest_path: Path,
    ) -> _NeighborResolver:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        blocks = [
            _NeighborBlock(
                row_start=int(block["row_start"]),
                row_end=int(block["row_end"]),
                submission_id=str(block["submission_id"]),
                wallet=str(block["wallet"]) if block.get("wallet") is not None else None,
                account_id=str(block["account_id"])
                if block.get("account_id") is not None
                else None,
            )
            for block in manifest.get("blocks", [])
        ]
        return cls(blocks)

    def resolve(self: _NeighborResolver, training_row_index: int) -> dict[str, Any]:
        if not self._blocks:
            raise ValueError("Training manifest has no blocks to resolve neighbor provenance")
        position = bisect.bisect_right(self._starts, training_row_index) - 1
        if position < 0:
            raise ValueError(f"training_row_index {training_row_index} not found in manifest")
        block = self._blocks[position]
        if training_row_index > block.row_end:
            raise ValueError(f"training_row_index {training_row_index} not found in manifest")
        row_offset = training_row_index - block.row_start
        return {
            "row_id": f"{block.submission_id}:{row_offset}",
            "submission_id": block.submission_id,
            "wallet": block.wallet,
            "account_id": block.account_id,
        }


def load_holdout_rows(path: Path) -> HoldoutRows:
    """Load and validate a Wavemill router CSV holdout for benchmark evaluation."""
    rows: list[dict[str, str]] = []
    quarantine_reasons: Counter[str] = Counter()
    total_rows = 0
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total_rows += 1
            reason = _quarantine_reason(row)
            if reason is not None:
                quarantine_reasons[reason] += 1
                continue
            rows.append(row)

    if total_rows == 0:
        raise ValueError(f"Holdout dataset is empty: {path}")
    if not rows:
        raise ValueError(
            "Holdout dataset has no valid evaluation rows after quarantine: "
            f"{dict(sorted(quarantine_reasons.items()))}"
        )
    return HoldoutRows(
        rows=rows,
        total_rows=total_rows,
        quarantine_reasons=dict(sorted(quarantine_reasons.items())),
    )


def evaluate_model(
    model: Any,
    *,
    model_id: str,
    holdout_path: Path,
    objectives: list[str],
    benchmark_spec_id: str | None = None,
    benchmark_version: str = "v2",
    primary_metric: str | None = None,
    eval_id: str | None = None,
    neighbor_resolver: _NeighborResolver | None = None,
) -> dict[str, Any]:
    """Evaluate a pyfunc-like router model and return metrics plus provenance."""
    holdout = load_holdout_rows(holdout_path)
    eval_id = eval_id or f"model-30-eval-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    benchmark_version = _normalize_benchmark_version(benchmark_version)
    benchmark_spec_id = benchmark_spec_id or _default_benchmark_spec_id(benchmark_version)
    primary_metric = primary_metric or _default_primary_metric(benchmark_version)
    benchmark_rows = _build_benchmark_rows(
        model,
        rows=holdout.rows,
        model_id=model_id,
        benchmark_spec_id=benchmark_spec_id,
        eval_id=eval_id,
        objectives=objectives,
        benchmark_version=benchmark_version,
        neighbor_resolver=neighbor_resolver,
    )
    metrics = _score_benchmark_rows(benchmark_rows, benchmark_version=benchmark_version)
    duration_coverage = _duration_coverage(benchmark_rows)
    scenario_counts = _scenario_counts(benchmark_rows)
    support_coverage = _support_coverage(benchmark_rows, benchmark_version=benchmark_version)
    return {
        "model_id": model_id,
        "holdout_dataset": str(holdout_path),
        "holdout_dataset_sha256": f"sha256:{_dataset_sha256(holdout_path)}",
        "benchmark_spec_id": benchmark_spec_id,
        "benchmark_version": benchmark_version,
        "primary_metric": primary_metric,
        "eval_id": eval_id,
        "row_counts": {
            "input_rows": holdout.total_rows,
            "evaluated_rows": len(holdout.rows),
            "benchmark_rows": len(benchmark_rows),
            "quarantined_rows": holdout.total_rows - len(holdout.rows),
        },
        "quarantine_reasons": holdout.quarantine_reasons,
        "objectives": objectives,
        "scenario_counts": scenario_counts,
        "support_coverage": support_coverage,
        "metrics": metrics,
        "duration_coverage": {
            "evaluated_rows": duration_coverage.evaluated_rows,
            "positive_label_rows": duration_coverage.positive_label_rows,
            "positive_label_fraction": duration_coverage.positive_label_fraction,
            "rows_with_predictions": duration_coverage.rows_with_predictions,
            "prediction_fraction_within_positive_labels": (
                duration_coverage.prediction_fraction_within_positive_labels
            ),
            "duration_mae_available": metrics["technical_task_router.duration_mae_seconds_v1"]
            is not None,
        },
        "benchmark_rows": benchmark_rows,
    }


def compare_models(
    baseline_report: dict[str, Any],
    candidate_report: dict[str, Any],
    *,
    primary_metric: str | None = None,
) -> dict[str, Any]:
    """Return candidate-vs-baseline metric deltas suitable for reward logic."""
    baseline_metrics = baseline_report["metrics"]
    candidate_metrics = candidate_report["metrics"]
    deltas = {
        key: _metric_delta(baseline_metrics[key], candidate_metrics[key])
        for key in sorted(set(baseline_metrics) & set(candidate_metrics))
    }
    primary_metric = (
        primary_metric
        or candidate_report.get("primary_metric")
        or baseline_report.get("primary_metric")
        or DEFAULT_V2_PRIMARY_METRIC
    )
    return {
        "baseline_model_id": baseline_report["model_id"],
        "candidate_model_id": candidate_report["model_id"],
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "deltas": deltas,
        "primary_metric": primary_metric,
        "primary_delta": deltas.get(primary_metric, 0.0),
        "guardrail_deltas": {
            key: value
            for key, value in deltas.items()
            if key
            in {
                "technical_task_router.invalid_selection_rate_v1",
                "technical_task_router.cost_mae_usd_v1",
                "technical_task_router.duration_mae_seconds_v1",
                "technical_task_router.reliability_brier_score_v1",
            }
        },
    }


def log_report_to_mlflow(report: dict[str, Any], *, artifact_name: str) -> None:
    """Log metrics and report artifacts to the active MLflow run."""
    _log_metrics(report.get("metrics", {}))
    mlflow.set_tag("hokusai.model_30.holdout_hash", report["holdout_dataset_sha256"])
    mlflow.set_tag("hokusai.model_30.holdout_rows", str(report["row_counts"]["evaluated_rows"]))
    mlflow.set_tag(
        "hokusai.model_30.quarantined_rows",
        str(report["row_counts"]["quarantined_rows"]),
    )
    duration_coverage = report.get("duration_coverage", {})
    mlflow.set_tag(
        "hokusai.model_30.duration_positive_label_rows",
        str(duration_coverage.get("positive_label_rows", 0)),
    )
    mlflow.set_tag(
        "hokusai.model_30.duration_positive_label_fraction",
        str(duration_coverage.get("positive_label_fraction", 0.0)),
    )
    mlflow.set_tag(
        "hokusai.model_30.duration_mae_available",
        str(duration_coverage.get("duration_mae_available", False)).lower(),
    )
    mlflow.set_tag("hokusai.model_30.benchmark_version", report.get("benchmark_version", "v1"))
    mlflow.set_tag("hokusai.model_30.primary_metric", report.get("primary_metric", ""))
    _log_per_row_artifact(report)
    mlflow.log_dict(_report_without_rows(report), artifact_name)


def log_comparison_to_mlflow(comparison: dict[str, Any]) -> None:
    """Log candidate-vs-baseline deltas to the active MLflow run."""
    for prefix in ("baseline", "candidate"):
        _log_metrics(comparison[f"{prefix}_metrics"], prefix=f"{prefix}_")
    _log_metrics(comparison["deltas"], prefix="delta_")
    mlflow.log_dict(comparison, "model_30_baseline_comparison.json")


def _build_benchmark_rows(
    model: Any,
    *,
    rows: list[dict[str, str]],
    model_id: str,
    benchmark_spec_id: str,
    eval_id: str,
    objectives: list[str],
    benchmark_version: str = "v2",
    neighbor_resolver: _NeighborResolver | None = None,
) -> list[dict[str, Any]]:
    benchmark_rows: list[dict[str, Any]] = []
    observed_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    scenarios = _scenarios_for_benchmark_version(benchmark_version)
    for row_index, row in enumerate(rows):
        for objective in objectives:
            for scenario in scenarios:
                scenario_context = _scenario_context(row, scenario)
                features = _features_from_holdout_row(row, objective, scenario_context)
                prediction = _predict_one(model, features)
                strategy = prediction.get("recommended_strategy") or {}
                selected_models = _prediction_selected_models(prediction, strategy)
                benchmark_row = {
                    "schema_version": _row_schema_version(benchmark_version),
                    "row_id": _row_id(row, row_index, objective, scenario),
                    "benchmark_spec_id": benchmark_spec_id,
                    "eval_id": eval_id,
                    "model_id": model_id,
                    "task_descriptor": _task_descriptor(row),
                    "allowed_models": scenario_context["allowed_models"],
                    "selected_models": selected_models,
                    "max_cost_usd": scenario_context["max_cost_usd"],
                    "actual_cost_usd": _required_float(row, "actual_cost_usd"),
                    "completed_successfully": _coerce_bool(row.get("completed_successfully")),
                    "scorer_ref": _row_scorer_ref(benchmark_version),
                    "observed_at": observed_at,
                    "estimated_cost_usd": _prediction_float(
                        strategy, prediction, "estimated_cost_usd"
                    ),
                    "estimated_duration_seconds": _optional_float(
                        strategy.get("estimated_duration_seconds")
                    ),
                    "estimated_success_under_budget": _optional_float(
                        strategy.get("estimated_success_under_budget")
                    ),
                    "actual_time_seconds": _optional_float(row.get("actual_time_seconds")),
                    "routing_objective": objective,
                    "metadata": {
                        "source_run_id_hash": row.get("run_id_hash"),
                        "source_task_id_hash": row.get("task_id_hash"),
                        "historical_selected_models": _historical_selected_models(row),
                    },
                }
                if benchmark_version == "v2":
                    benchmark_row.update(
                        {
                            "scenario": scenario,
                            "candidate_pool_id": scenario_context["candidate_pool_id"],
                            "selected_strategy": _selected_strategy(
                                strategy, prediction, objective
                            ),
                        }
                    )
                    benchmark_row["per_row_metrics"] = _per_row_v2_metrics(benchmark_row)
                neighbor_provenance = prediction.get("neighbor_provenance")
                if neighbor_resolver is not None and isinstance(neighbor_provenance, list):
                    benchmark_row["neighbor_provenance"] = [
                        {
                            **neighbor_resolver.resolve(int(neighbor["training_row_index"])),
                            "training_row_index": int(neighbor["training_row_index"]),
                            "distance": float(neighbor["distance"]),
                            "weight": float(neighbor["weight"]),
                        }
                        for neighbor in neighbor_provenance
                    ]
                benchmark_rows.append(benchmark_row)
    return benchmark_rows


def _score_benchmark_rows(
    rows: list[dict[str, Any]],
    *,
    benchmark_version: str = "v2",
) -> dict[str, float | None]:
    scorer_refs = V2_SCORER_REFS if benchmark_version == "v2" else V1_SCORER_REFS
    metrics = {_metric_key(ref): float(resolve_scorer(ref).callable_(rows)) for ref in scorer_refs}
    metrics["technical_task_router.duration_mae_seconds_v1"] = _duration_mae(rows)
    return metrics


def _duration_coverage(rows: list[dict[str, Any]]) -> DurationCoverage:
    positive_label_rows = 0
    rows_with_predictions = 0
    for row in rows:
        actual_duration = _positive_float(row.get("actual_time_seconds"))
        if actual_duration is None:
            continue
        positive_label_rows += 1
        if _finite_float(row.get("estimated_duration_seconds")) is not None:
            rows_with_predictions += 1
    return DurationCoverage(
        evaluated_rows=len(rows),
        positive_label_rows=positive_label_rows,
        rows_with_predictions=rows_with_predictions,
    )


def _duration_mae(rows: list[dict[str, Any]]) -> float | None:
    errors: list[float] = []
    for row in rows:
        actual_duration = _positive_float(row.get("actual_time_seconds"))
        estimated_duration = _finite_float(row.get("estimated_duration_seconds"))
        if actual_duration is None or estimated_duration is None:
            continue
        errors.append(abs(estimated_duration - actual_duration))
    if not errors:
        return None
    return sum(errors) / len(errors)


def _scenario_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter(str(row.get("scenario", "production_pool")) for row in rows)
    return dict(sorted(counts.items()))


def _support_coverage(
    rows: list[dict[str, Any]],
    *,
    benchmark_version: str,
) -> dict[str, Any]:
    scenarios = V2_SCENARIOS if benchmark_version == "v2" else ("production_pool",)
    scenario_counts = _scenario_counts(rows)
    return {
        "required_scenarios": list(scenarios),
        "covered_scenarios": [
            scenario for scenario in scenarios if scenario_counts.get(scenario, 0) > 0
        ],
        "missing_scenarios": [
            scenario for scenario in scenarios if scenario_counts.get(scenario, 0) == 0
        ],
    }


def _metric_delta(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None:
        return None
    return candidate - baseline


def _log_metrics(metrics: dict[str, float | None], *, prefix: str = "") -> None:
    for key, value in metrics.items():
        if value is None:
            continue
        mlflow.log_metric(f"{prefix}{key}", float(value))


def _log_per_row_artifact(report: dict[str, Any]) -> None:
    rows = report.get("benchmark_rows")
    if not rows:
        return
    flattened_rows = [_flatten_per_row_metrics(row) for row in rows]
    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_path = Path(tmpdir) / "model_30_benchmark_rows.parquet"
        pd.DataFrame(flattened_rows).to_parquet(artifact_path, index=False)
        mlflow.log_artifact(str(artifact_path), artifact_path="eval_results")
    report["per_row_artifact"] = "eval_results/model_30_benchmark_rows.parquet"


def _flatten_per_row_metrics(row: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(row)
    per_row_metrics = flattened.pop("per_row_metrics", {})
    for key, value in per_row_metrics.items():
        flattened[key] = value
    return flattened


def _normalize_benchmark_version(benchmark_version: str) -> str:
    normalized = str(benchmark_version).strip().lower()
    if normalized not in {"v1", "v2"}:
        raise ValueError(f"Unknown benchmark version: {benchmark_version!r}")
    return normalized


def _default_benchmark_spec_id(benchmark_version: str) -> str:
    return V2_BENCHMARK_SPEC_ID if benchmark_version == "v2" else V1_BENCHMARK_SPEC_ID


def _default_primary_metric(benchmark_version: str) -> str:
    return DEFAULT_V2_PRIMARY_METRIC if benchmark_version == "v2" else DEFAULT_V1_PRIMARY_METRIC


def _scenarios_for_benchmark_version(benchmark_version: str) -> tuple[str, ...]:
    return V2_SCENARIOS if benchmark_version == "v2" else ("production_pool",)


def _row_schema_version(benchmark_version: str) -> str:
    return f"technical_task_router_row/{benchmark_version}"


def _row_scorer_ref(benchmark_version: str) -> str:
    if benchmark_version == "v2":
        return "technical_task_router.benchmark_score/v2"
    return "technical_task_router.success_under_budget/v1"


def _scenario_context(row: dict[str, str], scenario: str) -> dict[str, Any]:
    role_available = _role_available_models(row)
    max_cost_usd = _required_float(row, "max_cost_usd")
    if scenario == "challenger_present":
        role_available = {
            role: _unique_ordered([*models, *CHALLENGER_MODELS])
            for role, models in role_available.items()
        }
        candidate_pool_id = "qwen-challenger-2026-06"
    elif scenario == "dominant_model_removed":
        role_available = {
            role: _remove_dominant_models(models) or models
            for role, models in role_available.items()
        }
        candidate_pool_id = "dominant-model-removed-2026-06"
    elif scenario == "low_budget":
        max_cost_usd = max_cost_usd * LOW_BUDGET_MULTIPLIER
        candidate_pool_id = "low-budget-2026-06"
    elif scenario == "sparse_cell":
        candidate_pool_id = _sparse_candidate_pool_id(row)
    elif scenario == "production_pool":
        candidate_pool_id = "production-2026-06"
    else:
        raise ValueError(f"Unknown benchmark scenario: {scenario!r}")

    allowed_models: list[str] = []
    for models in role_available.values():
        allowed_models.extend(models)
    return {
        "scenario": scenario,
        "candidate_pool_id": candidate_pool_id,
        "role_available_models": role_available,
        "allowed_models": _unique_ordered(allowed_models),
        "max_cost_usd": max_cost_usd,
    }


def _remove_dominant_models(models: list[str]) -> list[str]:
    return [
        model
        for model in models
        if not any(model.startswith(prefix) for prefix in DOMINANT_MODEL_PREFIXES)
    ]


def _sparse_candidate_pool_id(row: dict[str, str]) -> str:
    parts = [
        "sparse",
        str(row.get("task_type") or "unknown"),
        str(row.get("domain") or "unknown"),
        str(row.get("complexity") or "unknown"),
        "2026-06",
    ]
    return "-".join(part.strip().lower().replace("_", "-") for part in parts if part)


def _selected_strategy(
    strategy: dict[str, Any],
    prediction: dict[str, Any],
    objective: str,
) -> dict[str, Any]:
    selected_model = prediction.get("selected_model")
    return {
        "planner_model": str(strategy.get("planner_model") or selected_model or ""),
        "coder_model": str(strategy.get("coder_model") or selected_model or ""),
        "reviewer_model": str(strategy.get("reviewer_model") or selected_model or ""),
        "routing_objective": str(strategy.get("objective") or objective),
    }


def _per_row_v2_metrics(row: dict[str, Any]) -> dict[str, float]:
    success = float(_row_success_under_budget(row))
    cost_efficiency = success * (
        1.0 - min(max(float(row["actual_cost_usd"]) / float(row["max_cost_usd"]), 0.0), 1.0)
    )
    scenario = row.get("scenario")
    sparse = success if scenario == "sparse_cell" else 0.0
    robustness = (
        success
        if scenario in {"challenger_present", "dominant_model_removed", "low_budget"}
        else 0.0
    )
    return {
        "technical_task_router.success_under_budget_v1": success,
        "technical_task_router.cost_efficiency_v2": cost_efficiency,
        "technical_task_router.sparse_cell_generalization_v2": sparse,
        "technical_task_router.candidate_pool_robustness_v2": robustness,
    }


def _row_success_under_budget(row: dict[str, Any]) -> bool:
    selected_models = row.get("selected_models")
    allowed_models = row.get("allowed_models")
    if not isinstance(selected_models, list) or not isinstance(allowed_models, list):
        return False
    if not set(selected_models).issubset(set(allowed_models)):
        return False
    return row.get("completed_successfully") is True and (
        float(row["actual_cost_usd"]) <= float(row["max_cost_usd"])
    )


def _features_from_holdout_row(
    row: dict[str, str],
    objective: str,
    scenario_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scenario_context = scenario_context or _scenario_context(row, "production_pool")
    allowed_models = json.dumps(scenario_context["allowed_models"], separators=(",", ":"))
    role_available = scenario_context["role_available_models"]
    return {
        "schema_version": "technical_task_router_inputs/v2",
        "task_descriptor": json.dumps(_task_descriptor(row), sort_keys=True),
        "task_description": _task_description(row),
        "task_type": row.get("task_type"),
        "language": row.get("language"),
        "domain": row.get("domain"),
        "complexity": row.get("complexity"),
        "repo_size_bucket": row.get("repo_size_bucket"),
        "files_touched_bucket": row.get("files_touched_bucket"),
        "description_length_bucket": row.get("description_length_bucket"),
        "risk_level": row.get("risk_level"),
        "requires_tests": row.get("requires_tests"),
        "is_migration": row.get("is_migration"),
        "ui_heavy": row.get("ui_heavy"),
        "cross_service": row.get("cross_service"),
        "allowed_models": allowed_models,
        "available_planner_models": json.dumps(role_available["planner"], separators=(",", ":")),
        "available_coder_models": json.dumps(role_available["coder"], separators=(",", ":")),
        "available_reviewer_models": json.dumps(role_available["reviewer"], separators=(",", ":")),
        "preferred_models": allowed_models,
        "max_cost_usd": scenario_context["max_cost_usd"],
        "expected_cost_usd": _optional_float(row.get("expected_cost_usd")),
        "workflow_stages": '["plan","code","review"]',
        "routing_objective": objective,
    }


def _task_descriptor(row: dict[str, str]) -> dict[str, Any]:
    return {
        "task_type": row.get("task_type"),
        "language": row.get("language"),
        "domain": row.get("domain"),
        "complexity": row.get("complexity"),
        "repo_size_bucket": row.get("repo_size_bucket"),
        "files_touched_bucket": row.get("files_touched_bucket"),
        "description_length_bucket": row.get("description_length_bucket"),
        "requires_tests": _coerce_bool(row.get("requires_tests")),
        "is_migration": _coerce_bool(row.get("is_migration")),
        "cross_service": _coerce_bool(row.get("cross_service")),
        "ui_heavy": _coerce_bool(row.get("ui_heavy")),
        "risk_level": row.get("risk_level"),
    }


def _task_description(row: dict[str, str]) -> str:
    parts = [
        row.get("task_type"),
        row.get("language"),
        row.get("domain"),
        row.get("complexity"),
        row.get("risk_level"),
    ]
    return " ".join(str(part) for part in parts if part)


def _quarantine_reason(row: dict[str, str]) -> str | None:
    if (
        _optional_float(row.get("max_cost_usd")) is None
        or _required_float(row, "max_cost_usd") <= 0
    ):
        return "max_cost_usd:missing_or_nonpositive"
    if _optional_float(row.get("actual_cost_usd")) is None:
        return "actual_cost_usd:missing_or_invalid"
    if row.get("completed_successfully") in (None, ""):
        return "completed_successfully:missing"
    for role, available_column in ROLE_AVAILABLE_COLUMNS.items():
        selected = str(row.get(ROLE_SELECTED_COLUMNS[role]) or "").strip()
        available = _parse_model_values(row.get(available_column, ""))
        if not selected:
            return f"{ROLE_SELECTED_COLUMNS[role]}:missing"
        if selected not in available:
            return f"{ROLE_SELECTED_COLUMNS[role]}:outside_available"
    return None


def _prediction_selected_models(prediction: dict[str, Any], strategy: dict[str, Any]) -> list[str]:
    selected = prediction.get("selected_models")
    if isinstance(selected, list) and selected:
        return [str(model) for model in selected if model]
    return _unique_ordered(
        [
            strategy.get("planner_model"),
            strategy.get("coder_model"),
            strategy.get("reviewer_model"),
            prediction.get("selected_model"),
        ]
    )


def _predict_one(model: Any, features: dict[str, Any]) -> dict[str, Any]:
    frame = pd.DataFrame([features])
    try:
        prediction = model.predict(frame)
    except TypeError:
        prediction = model.predict(None, frame)
    return prediction.iloc[0].to_dict()


def _metric_key(scorer_ref: str) -> str:
    return derive_mlflow_name(scorer_ref).replace("/", "_")


def _prediction_float(
    strategy: dict[str, Any],
    prediction: dict[str, Any],
    key: str,
) -> float:
    return _optional_float(strategy.get(key)) or _optional_float(prediction.get(key)) or 0.0


def _historical_selected_models(row: dict[str, str]) -> list[str]:
    return _unique_ordered(row.get(column) for column in ROLE_SELECTED_COLUMNS.values())


def _role_available_models(row: dict[str, str]) -> dict[str, list[str]]:
    return {
        role: _parse_model_values(row.get(column, ""))
        for role, column in ROLE_AVAILABLE_COLUMNS.items()
    }


def _allowed_models(row: dict[str, str]) -> list[str]:
    models: list[str] = []
    for role_models in _role_available_models(row).values():
        models.extend(role_models)
    return _unique_ordered(models)


def _parse_model_values(raw_value: str | None) -> list[str]:
    value = str(raw_value or "").strip()
    if not value:
        return []
    if value.startswith("["):
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            return []
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [value]


def _row_id(row: dict[str, str], row_index: int, objective: str, scenario: str) -> str:
    source = row.get("task_id_hash") or row.get("run_id_hash") or str(row_index)
    return f"{source}:{objective}:{scenario}"


def _dataset_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_float(row: dict[str, str], key: str) -> float:
    value = _optional_float(row.get(key))
    if value is None:
        raise ValueError(f"Missing numeric field {key!r}")
    return value


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _finite_float(value: Any) -> float | None:
    numeric = _optional_float(value)
    if numeric is None or not pd.notna(numeric):
        return None
    return numeric


def _positive_float(value: Any) -> float | None:
    numeric = _finite_float(value)
    if numeric is None or numeric <= 0:
        return None
    return numeric


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _unique_ordered(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _report_without_rows(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "benchmark_rows"}


def parse_objectives(raw: str) -> list[str]:
    """Parse objective CLI value."""
    if raw == "all":
        return list(OBJECTIVES)
    objectives = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = sorted(set(objectives) - set(OBJECTIVES))
    if invalid:
        raise ValueError(f"Unknown routing objective(s): {invalid}")
    return objectives


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout-dataset", required=True)
    parser.add_argument("--model-uri", help="Single model URI to evaluate.")
    parser.add_argument("--baseline-model-uri", help="Baseline model URI for comparison.")
    parser.add_argument("--candidate-model-uri", help="Candidate model URI for comparison.")
    parser.add_argument("--model-id", default="model-30-router")
    parser.add_argument("--baseline-model-id", default="model-30-baseline")
    parser.add_argument("--candidate-model-id", default="model-30-candidate")
    parser.add_argument("--objectives", default="all")
    parser.add_argument("--benchmark-version", choices=("v1", "v2"), default="v2")
    parser.add_argument("--primary-metric")
    parser.add_argument("--benchmark-spec-id")
    parser.add_argument("--tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI"))
    parser.add_argument("--experiment-name", default="technical-task-router-evaluation")
    parser.add_argument("--run-name", default="model-30-baseline-evaluation")
    parser.add_argument("--output-report")
    parser.add_argument("--training-manifest")
    parser.add_argument("--log-mlflow", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run Model 30 holdout evaluation."""
    args = parse_args()
    objectives = parse_objectives(args.objectives)
    holdout_path = Path(args.holdout_dataset).expanduser().resolve()
    neighbor_resolver = (
        _NeighborResolver.from_manifest(Path(args.training_manifest).expanduser().resolve())
        if args.training_manifest
        else None
    )
    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)

    if args.baseline_model_uri or args.candidate_model_uri:
        if not args.baseline_model_uri or not args.candidate_model_uri:
            raise ValueError("--baseline-model-uri and --candidate-model-uri must be used together")
        baseline_report = evaluate_model(
            mlflow.pyfunc.load_model(args.baseline_model_uri),
            model_id=args.baseline_model_id,
            holdout_path=holdout_path,
            objectives=objectives,
            benchmark_spec_id=args.benchmark_spec_id,
            benchmark_version=args.benchmark_version,
            primary_metric=args.primary_metric,
            neighbor_resolver=neighbor_resolver,
        )
        baseline_report["model_uri"] = args.baseline_model_uri
        candidate_report = evaluate_model(
            mlflow.pyfunc.load_model(args.candidate_model_uri),
            model_id=args.candidate_model_id,
            holdout_path=holdout_path,
            objectives=objectives,
            benchmark_spec_id=args.benchmark_spec_id,
            benchmark_version=args.benchmark_version,
            primary_metric=args.primary_metric,
            neighbor_resolver=neighbor_resolver,
        )
        candidate_report["model_uri"] = args.candidate_model_uri
        report = {
            "baseline": _report_without_rows(baseline_report),
            "candidate": _report_without_rows(candidate_report),
            "comparison": compare_models(
                baseline_report,
                candidate_report,
                primary_metric=args.primary_metric,
            ),
        }
    else:
        if not args.model_uri:
            raise ValueError("Provide --model-uri or both comparison model URIs")
        model_report = evaluate_model(
            mlflow.pyfunc.load_model(args.model_uri),
            model_id=args.model_id,
            holdout_path=holdout_path,
            objectives=objectives,
            benchmark_spec_id=args.benchmark_spec_id,
            benchmark_version=args.benchmark_version,
            primary_metric=args.primary_metric,
            neighbor_resolver=neighbor_resolver,
        )
        model_report["model_uri"] = args.model_uri
        report = _report_without_rows(model_report)

    if args.log_mlflow:
        mlflow.set_experiment(args.experiment_name)
        with mlflow.start_run(run_name=args.run_name):
            if "comparison" in report:
                mlflow.set_tag("hokusai.model_30.baseline_model_uri", args.baseline_model_uri)
                mlflow.set_tag("hokusai.model_30.candidate_model_uri", args.candidate_model_uri)
                mlflow.set_tag(
                    "hokusai.model_30.holdout_hash",
                    report["baseline"]["holdout_dataset_sha256"],
                )
                mlflow.set_tag(
                    "hokusai.model_30.holdout_rows",
                    str(report["baseline"]["row_counts"]["evaluated_rows"]),
                )
                mlflow.set_tag(
                    "hokusai.model_30.quarantined_rows",
                    str(report["baseline"]["row_counts"]["quarantined_rows"]),
                )
                log_comparison_to_mlflow(report["comparison"])
                mlflow.log_dict(report, "model_30_evaluation_report.json")
            else:
                log_report_to_mlflow(report, artifact_name="model_30_evaluation_report.json")

    report_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output_report:
        output_path = Path(args.output_report).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_text, encoding="utf-8")
    print(report_text, end="")  # noqa: T201


if __name__ == "__main__":
    main()
