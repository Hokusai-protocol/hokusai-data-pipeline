"""Unit coverage for Model 30 holdout evaluation and baseline comparison."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from scripts.model_30.evaluate_technical_task_router import (
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
