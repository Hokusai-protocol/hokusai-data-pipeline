"""Evaluate Model 30 router artifacts against a fixed technical-task holdout.

MLflow authentication follows the SDK environment, including
``MLFLOW_TRACKING_TOKEN`` when the registry requires bearer auth.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
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

SCORER_REFS: tuple[str, ...] = (
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
    benchmark_spec_id: str = "technical-task-router-baseline-v1",
    eval_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate a pyfunc-like router model and return metrics plus provenance."""
    holdout = load_holdout_rows(holdout_path)
    eval_id = eval_id or f"model-30-eval-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    benchmark_rows = _build_benchmark_rows(
        model,
        rows=holdout.rows,
        model_id=model_id,
        benchmark_spec_id=benchmark_spec_id,
        eval_id=eval_id,
        objectives=objectives,
    )
    metrics = _score_benchmark_rows(benchmark_rows)
    duration_coverage = _duration_coverage(benchmark_rows)
    return {
        "model_id": model_id,
        "holdout_dataset": str(holdout_path),
        "holdout_dataset_sha256": f"sha256:{_dataset_sha256(holdout_path)}",
        "benchmark_spec_id": benchmark_spec_id,
        "eval_id": eval_id,
        "row_counts": {
            "input_rows": holdout.total_rows,
            "evaluated_rows": len(holdout.rows),
            "benchmark_rows": len(benchmark_rows),
            "quarantined_rows": holdout.total_rows - len(holdout.rows),
        },
        "quarantine_reasons": holdout.quarantine_reasons,
        "objectives": objectives,
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
) -> dict[str, Any]:
    """Return candidate-vs-baseline metric deltas suitable for reward logic."""
    baseline_metrics = baseline_report["metrics"]
    candidate_metrics = candidate_report["metrics"]
    deltas = {
        key: _metric_delta(baseline_metrics[key], candidate_metrics[key])
        for key in sorted(set(baseline_metrics) & set(candidate_metrics))
    }
    return {
        "baseline_model_id": baseline_report["model_id"],
        "candidate_model_id": candidate_report["model_id"],
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "deltas": deltas,
        "primary_metric": "technical_task_router.benchmark_score_v1",
        "primary_delta": deltas.get("technical_task_router.benchmark_score_v1", 0.0),
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
) -> list[dict[str, Any]]:
    benchmark_rows: list[dict[str, Any]] = []
    observed_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for row_index, row in enumerate(rows):
        for objective in objectives:
            features = _features_from_holdout_row(row, objective)
            prediction = _predict_one(model, features)
            strategy = prediction.get("recommended_strategy") or {}
            selected_models = _prediction_selected_models(prediction, strategy)
            benchmark_rows.append(
                {
                    "schema_version": "technical_task_router_row/v1",
                    "row_id": _row_id(row, row_index, objective),
                    "benchmark_spec_id": benchmark_spec_id,
                    "eval_id": eval_id,
                    "model_id": model_id,
                    "task_descriptor": _task_descriptor(row),
                    "allowed_models": _allowed_models(row),
                    "selected_models": selected_models,
                    "max_cost_usd": _required_float(row, "max_cost_usd"),
                    "actual_cost_usd": _required_float(row, "actual_cost_usd"),
                    "completed_successfully": _coerce_bool(row.get("completed_successfully")),
                    "scorer_ref": "technical_task_router.success_under_budget/v1",
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
            )
    return benchmark_rows


def _score_benchmark_rows(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    metrics = {_metric_key(ref): float(resolve_scorer(ref).callable_(rows)) for ref in SCORER_REFS}
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


def _metric_delta(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None:
        return None
    return candidate - baseline


def _log_metrics(metrics: dict[str, float | None], *, prefix: str = "") -> None:
    for key, value in metrics.items():
        if value is None:
            continue
        mlflow.log_metric(f"{prefix}{key}", float(value))


def _features_from_holdout_row(row: dict[str, str], objective: str) -> dict[str, Any]:
    allowed_models = json.dumps(_allowed_models(row), separators=(",", ":"))
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
        "available_planner_models": row.get("available_planner_models"),
        "available_coder_models": row.get("available_coder_models"),
        "available_reviewer_models": row.get("available_reviewer_models"),
        "preferred_models": allowed_models,
        "max_cost_usd": _required_float(row, "max_cost_usd"),
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


def _allowed_models(row: dict[str, str]) -> list[str]:
    models: list[str] = []
    for column in ROLE_AVAILABLE_COLUMNS.values():
        models.extend(_parse_model_values(row.get(column, "")))
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


def _row_id(row: dict[str, str], row_index: int, objective: str) -> str:
    source = row.get("task_id_hash") or row.get("run_id_hash") or str(row_index)
    return f"{source}:{objective}"


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
    parser.add_argument("--tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI"))
    parser.add_argument("--experiment-name", default="technical-task-router-evaluation")
    parser.add_argument("--run-name", default="model-30-baseline-evaluation")
    parser.add_argument("--output-report")
    parser.add_argument("--log-mlflow", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run Model 30 holdout evaluation."""
    args = parse_args()
    objectives = parse_objectives(args.objectives)
    holdout_path = Path(args.holdout_dataset).expanduser().resolve()
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
        )
        baseline_report["model_uri"] = args.baseline_model_uri
        candidate_report = evaluate_model(
            mlflow.pyfunc.load_model(args.candidate_model_uri),
            model_id=args.candidate_model_id,
            holdout_path=holdout_path,
            objectives=objectives,
        )
        candidate_report["model_uri"] = args.candidate_model_uri
        report = {
            "baseline": _report_without_rows(baseline_report),
            "candidate": _report_without_rows(candidate_report),
            "comparison": compare_models(baseline_report, candidate_report),
        }
    else:
        if not args.model_uri:
            raise ValueError("Provide --model-uri or both comparison model URIs")
        model_report = evaluate_model(
            mlflow.pyfunc.load_model(args.model_uri),
            model_id=args.model_id,
            holdout_path=holdout_path,
            objectives=objectives,
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
