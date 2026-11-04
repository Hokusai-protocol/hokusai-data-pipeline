from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.model_30.collect_wavemill_router_corpus import (
    FIELDNAMES,
    derive_router_rows,
    discover_wavemill_eval_files,
    eval_record_to_router_row,
)


def _write_eval(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _eval_record(**overrides: object) -> dict:
    record = {
        "id": "eval-1",
        "timestamp": "2026-06-15T00:00:00.000Z",
        "trainingEligible": True,
        "budgetEvalEligible": True,
        "score": 0.95,
        "scoreBand": "Minor Feedback",
        "workflowCost": 2.5,
        "workflowCostStatus": "success",
        "timeSeconds": 1200,
        "interventionCount": 0,
        "taskDescriptor": {
            "signals": {
                "heuristic": {
                    "task_type": "feature",
                    "languages": ["python", "typescript"],
                    "files_touched": 4,
                    "is_greenfield": False,
                    "has_migration": True,
                    "has_tests": True,
                    "cross_service": False,
                    "has_ui": False,
                },
                "learned": {
                    "complexity": 4,
                    "domain": "backend",
                },
            },
            "constraints": {
                "max_cost_usd": 25,
                "models_available": ["gpt-5.4", "claude-sonnet-4-6"],
            },
            "stages": {
                "planner": {"model": "claude-sonnet-4-6"},
                "coder": {"model": "gpt-5.4", "cost_usd": 2.5},
                "reviewer": {"model": "claude-sonnet-4-6"},
            },
            "rubric": {
                "criterion_count": 5,
                "mean_score": 0.96,
                "criteria_scores": {
                    "completeness": 0.97,
                    "correctness": 0.95,
                    "code_quality": 0.94,
                    "intervention_impact": 1.0,
                    "autonomy": 0.95,
                },
                "determinative_boundary": "no_interventions",
            },
        },
        "routePrediction": {
            "expectedSuccess": 0.7,
            "expectedCostUsd": 3.0,
            "confidence": 0.8,
            "riskScore": 9,
        },
        "repoContext": {
            "repoSize": {"loc": 100000},
        },
        "outcomes": {"success": True},
    }
    record.update(overrides)
    return record


def _write_router_csv(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerow(row)


def test_discover_wavemill_eval_files_finds_current_logs_only(tmp_path: Path) -> None:
    eval_path = tmp_path / "repo-a" / ".wavemill" / "evals" / "evals.jsonl"
    backup_path = tmp_path / "repo-a" / ".wavemill" / "evals" / "evals.jsonl.backup"
    _write_eval(eval_path, _eval_record())
    _write_eval(backup_path, _eval_record(id="backup"))

    assert discover_wavemill_eval_files([tmp_path]) == [eval_path.resolve()]


def test_discover_wavemill_eval_files_excludes_worktrees_by_default(tmp_path: Path) -> None:
    repo_eval = tmp_path / "repo-a" / ".wavemill" / "evals" / "evals.jsonl"
    worktree_eval = (
        tmp_path / "worktrees" / "repo-a-feature" / ".wavemill" / "evals" / "evals.jsonl"
    )
    _write_eval(repo_eval, _eval_record())
    _write_eval(worktree_eval, _eval_record(id="worktree"))

    assert discover_wavemill_eval_files([tmp_path]) == [repo_eval.resolve()]
    assert discover_wavemill_eval_files([tmp_path], include_worktrees=True) == [
        repo_eval.resolve(),
        worktree_eval.resolve(),
    ]


def test_eval_record_to_router_row_maps_wavemill_task_descriptor() -> None:
    row, reason = eval_record_to_router_row(_eval_record(), source_repo="repo-a")

    assert reason is None
    assert row is not None
    assert row["schema_version"] == "wavemill-hokusai-router-dataset-v1"
    assert row["task_type"] == "feature"
    assert row["language"] == "python"
    assert row["domain"] == "backend"
    assert row["planner_model"] == "claude-sonnet-4-6"
    assert row["coder_model"] == "gpt-5.4"
    assert row["reviewer_model"] == "claude-sonnet-4-6"
    assert row["available_coder_models"] == '["claude-sonnet-4-6","gpt-5.4"]'
    assert row["completed_successfully"] == "true"
    assert row["under_budget"] == "true"
    assert row["risk_level"] == "medium"
    assert row["rubric_code_quality"] == "0.94"


def test_derive_router_rows_reads_every_repo_and_ignores_prebuilt_router_csvs(
    tmp_path: Path,
) -> None:
    """HOK-3391/3414: a router CSV next to evals.jsonl never replaces derivation."""
    repo_a_eval = tmp_path / "repo-a" / ".wavemill" / "evals" / "evals.jsonl"
    repo_b_eval = tmp_path / "repo-b" / ".wavemill" / "evals" / "evals.jsonl"
    stale_csv = tmp_path / "repo-a" / ".wavemill" / "evals" / "hokusai-router-dataset.csv"
    _write_eval(repo_a_eval, _eval_record())
    _write_eval(repo_b_eval, _eval_record(id="eval-2", score=0.8))
    stale_row, reason = eval_record_to_router_row(_eval_record(id="stale"), source_repo="repo-a")
    assert reason is None and stale_row is not None
    stale_row["run_id_hash"] = "prebuilt-run"
    _write_router_csv(stale_csv, stale_row)

    rows, report, snapshots = derive_router_rows([tmp_path])

    assert report["rows_derived"] == 2
    assert len(rows) == 2
    assert "prebuilt-run" not in {row["run_id_hash"] for row in rows}
    assert len({row["source_repo_hash"] for row in rows}) == 2
    assert snapshots == []


def test_derived_numbers_are_exact_not_six_significant_figures() -> None:
    row, reason = eval_record_to_router_row(
        _eval_record(workflowCost=17.316243, timeSeconds=4040.6812),
        source_repo="repo-a",
    )
    assert reason is None and row is not None
    assert row["actual_time_seconds"] == "4040.6812"
