from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts import run_contribution_training_flow as flow


def _config(path: Path, tmp_path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "model_id": "30",
                "run_name": "test-run",
                "as_of": "2026-06-24T00:00:00Z",
                "output_dir": str(tmp_path / "out"),
                "s3_bucket": "bucket",
                "holdout_dataset": str(tmp_path / "holdout.csv"),
                "baseline_model_uri": "models:/Technical Task Router@production",
                "model_30": {"router_dataset_filename": "dataset.csv", "k_neighbors": 3},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_config_validates_model_id(tmp_path: Path) -> None:
    config_path = _config(tmp_path / "workflow.json", tmp_path)

    config = flow.load_config(config_path)

    assert config.model_id == "30"
    assert config.model_config["k_neighbors"] == 3


def test_convert_contribution_row_to_router_csv_shape() -> None:
    converted = flow.contribution_row_to_router_csv_row(
        {
            "schema_version": "technical_task_router_row/v1",
            "row_id": "row-1",
            "benchmark_spec_id": "benchmark",
            "eval_id": "eval-1",
            "model_id": "30",
            "task_descriptor": {
                "description": "Fix an API retry bug",
                "task_type": "bugfix",
                "language": "python",
                "domain": "backend",
                "requires_tests": True,
            },
            "allowed_models": ["gpt-5.4", "claude-sonnet-4-6"],
            "selected_models": ["gpt-5.4"],
            "max_cost_usd": 2.0,
            "actual_cost_usd": 1.0,
            "estimated_success_under_budget": 0.7,
            "completed_successfully": True,
            "scorer_ref": "technical_task_router.success_under_budget/v1",
            "observed_at": "2026-06-01T00:00:00Z",
        }
    )

    assert converted["task_description"] == "Fix an API retry bug"
    assert converted["available_coder_models"] == '["gpt-5.4","claude-sonnet-4-6"]'
    assert converted["planner_model"] == "gpt-5.4"
    assert converted["coder_model"] == "gpt-5.4"
    assert converted["reviewer_model"] == "gpt-5.4"
    assert converted["completed_successfully"] == "true"
    assert converted["under_budget"] == "true"
    assert converted["score"] == "1.0"


def test_convert_compact_wavemill_row_to_router_csv_shape() -> None:
    converted = flow.contribution_row_to_router_csv_row(
        {
            "task_id": "redacted-201c916a0488b3cb",
            "harness": "wavemill",
            "actual_cost_usd": 13.1073375,
            "success_under_budget": True,
            "wall_clock_seconds": 2114.466,
            "inputs": {
                "schema_version": "1.2",
                "planner_model": "gpt-5.5",
                "coder_model": "gpt-5.4",
                "reviewer_model": "claude-sonnet-4-6",
                "intervention_count": 0,
                "rubric_mean_score": 0.97,
                "rubric_version": "1.0",
                "determinative_boundary": "no_interventions",
            },
        }
    )

    assert converted["task_id_hash"] == "redacted-201c916a0488b3cb"
    assert converted["planner_model"] == "gpt-5.5"
    assert converted["coder_model"] == "gpt-5.4"
    assert converted["reviewer_model"] == "claude-sonnet-4-6"
    assert converted["available_coder_models"] == '["gpt-5.5","gpt-5.4","claude-sonnet-4-6"]'
    assert converted["completed_successfully"] == "true"
    assert converted["under_budget"] == "true"
    assert converted["score"] == "0.97"
    assert converted["actual_time_seconds"] == "2114.466"


def test_prepare_converts_jsonl_to_csv(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "dataset.jsonl"
    csv_path = tmp_path / "dataset.csv"
    jsonl_path.write_text(
        json.dumps(
            {
                "row_id": "row-1",
                "eval_id": "eval-1",
                "task_descriptor": {"task_type": "feature"},
                "allowed_models": ["gpt-5.4"],
                "selected_models": ["gpt-5.4"],
                "max_cost_usd": 1.0,
                "actual_cost_usd": 0.5,
                "completed_successfully": True,
                "observed_at": "2026-06-01T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = flow.convert_jsonl_to_router_csv(jsonl_path, csv_path)

    assert report["rows_written"] == 1
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["planner_model"] == "gpt-5.4"
    assert rows[0]["coder_model"] == "gpt-5.4"
    assert rows[0]["reviewer_model"] == "gpt-5.4"


def test_plan_stage_writes_manifest_without_executing(tmp_path: Path) -> None:
    config = flow.load_config(_config(tmp_path / "workflow.json", tmp_path))

    report = flow.run_stage(config, "plan", dry_run=True)

    manifest = json.loads(Path(report["run_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["stage"] == "plan"
    assert manifest["promotion_enabled"] is False
    assert "evaluate" in manifest["planned_commands"]
    assert "assembled/manifest.json" in " ".join(manifest["planned_commands"]["evaluate"])
