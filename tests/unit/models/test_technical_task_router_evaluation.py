"""Unit coverage for Model 30 holdout evaluation and baseline comparison."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from scripts.model_30.evaluate_technical_task_router import (
    _build_benchmark_rows,
    _NeighborResolver,
    compare_models,
    evaluate_model,
    load_holdout_rows,
    parse_objectives,
)


class FixedRouterModel:
    """Small pyfunc-like test router."""

    def __init__(self, *, model_id: str, success_probability: float = 0.8) -> None:
        self.model_id = model_id
        self.success_probability = success_probability

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        objective = frame.iloc[0]["routing_objective"]
        return pd.DataFrame(
            [
                {
                    "selected_model": self.model_id,
                    "selected_models": [self.model_id],
                    "confidence": self.success_probability,
                    "estimated_cost_usd": 0.3,
                    "neighbor_provenance": [
                        {"training_row_index": 0, "distance": 0.1, "weight": 0.9},
                        {"training_row_index": 1, "distance": 0.2, "weight": 0.8},
                    ],
                    "recommended_strategy": {
                        "objective": objective,
                        "planner_model": self.model_id,
                        "coder_model": self.model_id,
                        "reviewer_model": self.model_id,
                        "stages": ["plan", "code", "review"],
                        "estimated_success_under_budget": self.success_probability,
                        "estimated_cost_usd": 0.3,
                        "estimated_duration_seconds": 100.0,
                        "confidence": self.success_probability,
                        "support": 1,
                        "rationale": "fixed test strategy",
                    },
                }
            ]
        )


def _write_holdout(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "run_id_hash",
        "task_id_hash",
        "task_type",
        "language",
        "domain",
        "complexity",
        "repo_size_bucket",
        "files_touched_bucket",
        "description_length_bucket",
        "requires_tests",
        "is_migration",
        "cross_service",
        "ui_heavy",
        "risk_level",
        "max_cost_usd",
        "available_planner_models",
        "available_coder_models",
        "available_reviewer_models",
        "planner_model",
        "coder_model",
        "reviewer_model",
        "expected_cost_usd",
        "completed_successfully",
        "actual_cost_usd",
        "actual_time_seconds",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _valid_row(task_id: str, *, completed: bool = True) -> dict[str, Any]:
    return {
        "run_id_hash": f"run-{task_id}",
        "task_id_hash": task_id,
        "task_type": "feature",
        "language": "py",
        "domain": "backend",
        "complexity": "5",
        "repo_size_bucket": "medium",
        "files_touched_bucket": "2_5",
        "description_length_bucket": "medium",
        "requires_tests": "true",
        "is_migration": "false",
        "cross_service": "false",
        "ui_heavy": "false",
        "risk_level": "medium",
        "max_cost_usd": "1.0",
        "available_planner_models": '["gpt-5.4","claude-sonnet-4-6"]',
        "available_coder_models": '["gpt-5.4","claude-sonnet-4-6"]',
        "available_reviewer_models": '["gpt-5.4","claude-sonnet-4-6"]',
        "planner_model": "gpt-5.4",
        "coder_model": "gpt-5.4",
        "reviewer_model": "gpt-5.4",
        "expected_cost_usd": "0.4",
        "completed_successfully": str(completed).lower(),
        "actual_cost_usd": "0.4",
        "actual_time_seconds": "120",
    }


def test_load_holdout_rows_quarantines_invalid_rows(tmp_path: Path) -> None:
    holdout_path = tmp_path / "holdout.csv"
    missing_budget = _valid_row("missing-budget")
    missing_budget["max_cost_usd"] = ""
    outside_available = _valid_row("outside-available")
    outside_available["planner_model"] = "claude-opus-4-6"
    _write_holdout(holdout_path, [_valid_row("valid"), missing_budget, outside_available])

    holdout = load_holdout_rows(holdout_path)

    assert len(holdout.rows) == 1
    assert holdout.total_rows == 3
    assert holdout.quarantine_reasons == {
        "max_cost_usd:missing_or_nonpositive": 1,
        "planner_model:outside_available": 1,
    }


def test_evaluate_model_scores_all_objectives(tmp_path: Path) -> None:
    holdout_path = tmp_path / "holdout.csv"
    _write_holdout(holdout_path, [_valid_row("success"), _valid_row("failure", completed=False)])

    report = evaluate_model(
        FixedRouterModel(model_id="gpt-5.4"),
        model_id="baseline",
        holdout_path=holdout_path,
        objectives=list(parse_objectives("all")),
        eval_id="eval-1",
    )

    assert report["row_counts"] == {
        "input_rows": 2,
        "evaluated_rows": 2,
        "benchmark_rows": 6,
        "quarantined_rows": 0,
    }
    assert report["metrics"]["technical_task_router.invalid_selection_rate_v1"] == 0.0
    assert report["metrics"]["technical_task_router.benchmark_score_v1"] == pytest.approx(0.5)
    assert report["metrics"]["technical_task_router.cost_mae_usd_v1"] == pytest.approx(0.1)
    assert report["metrics"]["technical_task_router.duration_mae_seconds_v1"] == pytest.approx(20.0)
    assert report["duration_coverage"] == {
        "evaluated_rows": 6,
        "positive_label_rows": 6,
        "positive_label_fraction": 1.0,
        "rows_with_predictions": 6,
        "prediction_fraction_within_positive_labels": 1.0,
        "duration_mae_available": True,
    }
    assert {row["routing_objective"] for row in report["benchmark_rows"]} == {
        "lowest_cost",
        "fastest_completion",
        "highest_reliability",
    }


def test_compare_models_reports_primary_delta(tmp_path: Path) -> None:
    holdout_path = tmp_path / "holdout.csv"
    _write_holdout(holdout_path, [_valid_row("success")])
    baseline = evaluate_model(
        FixedRouterModel(model_id="gpt-5.4", success_probability=0.5),
        model_id="baseline",
        holdout_path=holdout_path,
        objectives=["highest_reliability"],
        eval_id="eval-1",
    )
    candidate = evaluate_model(
        FixedRouterModel(model_id="claude-sonnet-4-6", success_probability=0.9),
        model_id="candidate",
        holdout_path=holdout_path,
        objectives=["highest_reliability"],
        eval_id="eval-1",
    )

    comparison = compare_models(baseline, candidate)

    assert comparison["baseline_model_id"] == "baseline"
    assert comparison["candidate_model_id"] == "candidate"
    assert comparison["primary_metric"] == "technical_task_router.benchmark_score_v1"
    assert comparison["primary_delta"] == 0.0
    assert comparison["deltas"][
        "technical_task_router.reliability_brier_score_v1"
    ] == pytest.approx(-0.24)


class NullDurationRouterModel(FixedRouterModel):
    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        row = super().predict(frame).iloc[0].to_dict()
        row["recommended_strategy"]["estimated_duration_seconds"] = None
        return pd.DataFrame([row])


def test_evaluate_model_reports_unavailable_duration_mae_without_positive_labels(
    tmp_path: Path,
) -> None:
    holdout_path = tmp_path / "holdout.csv"
    row_a = _valid_row("a")
    row_a["actual_time_seconds"] = "0"
    row_b = _valid_row("b")
    row_b["actual_time_seconds"] = ""
    _write_holdout(holdout_path, [row_a, row_b])

    report = evaluate_model(
        NullDurationRouterModel(model_id="gpt-5.4"),
        model_id="candidate",
        holdout_path=holdout_path,
        objectives=["highest_reliability"],
        eval_id="eval-1",
    )

    assert report["metrics"]["technical_task_router.duration_mae_seconds_v1"] is None
    assert report["duration_coverage"] == {
        "evaluated_rows": 2,
        "positive_label_rows": 0,
        "positive_label_fraction": 0.0,
        "rows_with_predictions": 0,
        "prediction_fraction_within_positive_labels": None,
        "duration_mae_available": False,
    }


def test_compare_models_keeps_duration_delta_null_when_metric_unavailable(tmp_path: Path) -> None:
    holdout_path = tmp_path / "holdout.csv"
    row = _valid_row("a")
    row["actual_time_seconds"] = "0"
    _write_holdout(holdout_path, [row])

    baseline = evaluate_model(
        NullDurationRouterModel(model_id="gpt-5.4", success_probability=0.5),
        model_id="baseline",
        holdout_path=holdout_path,
        objectives=["highest_reliability"],
        eval_id="eval-1",
    )
    candidate = evaluate_model(
        NullDurationRouterModel(model_id="claude-sonnet-4-6", success_probability=0.9),
        model_id="candidate",
        holdout_path=holdout_path,
        objectives=["highest_reliability"],
        eval_id="eval-1",
    )

    comparison = compare_models(baseline, candidate)

    assert comparison["deltas"]["technical_task_router.duration_mae_seconds_v1"] is None
    assert comparison["guardrail_deltas"]["technical_task_router.duration_mae_seconds_v1"] is None


def test_build_benchmark_rows_resolves_neighbor_provenance(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "model_30_training_manifest/v1",
                "as_of": "2026-06-04T00:00:00Z",
                "dataset_hash": "sha256:" + "a" * 64,
                "manifest_digest": "sha256:" + "b" * 64,
                "row_count": 2,
                "model_id": "30",
                "blocks": [
                    {
                        "submission_id": "sub-a",
                        "wallet": "0x" + "1" * 40,
                        "s3_key": "s3://bucket/a",
                        "row_start": 0,
                        "row_end": 0,
                        "row_count": 1,
                        "reward_hold": False,
                    },
                    {
                        "submission_id": "sub-b",
                        "wallet": "0x" + "2" * 40,
                        "s3_key": "s3://bucket/b",
                        "row_start": 1,
                        "row_end": 1,
                        "row_count": 1,
                        "reward_hold": False,
                    },
                ],
                "quarantine_count": 0,
                "duplicates_dropped": [],
                "wallet_policy": "hold",
            }
        ),
        encoding="utf-8",
    )
    resolver = _NeighborResolver.from_manifest(manifest_path)

    rows = _build_benchmark_rows(
        FixedRouterModel(model_id="gpt-5.4"),
        rows=[_valid_row("success")],
        model_id="candidate",
        benchmark_spec_id="spec-1",
        eval_id="eval-1",
        objectives=["highest_reliability"],
        neighbor_resolver=resolver,
    )

    provenance = rows[0]["neighbor_provenance"]
    assert provenance[0]["row_id"] == "sub-a:0"
    assert provenance[0]["submission_id"] == "sub-a"
    assert provenance[0]["wallet"] == "0x" + "1" * 40
    assert provenance[1]["row_id"] == "sub-b:0"


def test_neighbor_resolver_raises_for_out_of_range_index(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "model_30_training_manifest/v1",
                "as_of": "2026-06-04T00:00:00Z",
                "dataset_hash": "sha256:" + "a" * 64,
                "manifest_digest": "sha256:" + "b" * 64,
                "row_count": 1,
                "model_id": "30",
                "blocks": [
                    {
                        "submission_id": "sub-a",
                        "wallet": "0x" + "1" * 40,
                        "s3_key": "s3://bucket/a",
                        "row_start": 0,
                        "row_end": 0,
                        "row_count": 1,
                        "reward_hold": False,
                    }
                ],
                "quarantine_count": 0,
                "duplicates_dropped": [],
                "wallet_policy": "hold",
            }
        ),
        encoding="utf-8",
    )

    resolver = _NeighborResolver.from_manifest(manifest_path)

    with pytest.raises(ValueError, match="training_row_index 4"):
        resolver.resolve(4)
