from __future__ import annotations

import csv
import json
from argparse import Namespace
from pathlib import Path

from scripts.model_30.collect_wavemill_router_corpus import (
    FIELDNAMES,
    collect_router_corpus,
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


def test_collect_router_corpus_derives_and_merges_cross_repo_sources(tmp_path: Path) -> None:
    repo_a_eval = tmp_path / "repo-a" / ".wavemill" / "evals" / "evals.jsonl"
    repo_b_csv = tmp_path / "repo-b" / ".wavemill" / "evals" / "hokusai-router-dataset.csv"
    output_path = tmp_path / "out" / "router.csv"
    report_path = tmp_path / "out" / "report.json"
    raw_path = tmp_path / "out" / "raw.csv"
    _write_eval(repo_a_eval, _eval_record())
    csv_row, reason = eval_record_to_router_row(
        _eval_record(id="eval-2", score=0.8),
        source_repo="repo-b",
    )
    assert reason is None
    assert csv_row is not None
    csv_row["run_id_hash"] = "prebuilt-run"
    _write_router_csv(repo_b_csv, csv_row)

    report = collect_router_corpus(
        Namespace(
            search_root=[str(tmp_path)],
            output=str(output_path),
            raw_output=str(raw_path),
            clean_report=None,
            report=str(report_path),
            include_eval_jsonl=True,
            include_router_csv=True,
            derive_when_router_csv_present=False,
            include_worktrees=False,
        )
    )
    rows = list(csv.DictReader(output_path.open(newline="", encoding="utf-8")))
    written_report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report == written_report
    assert report["eval_jsonl"]["rows_derived"] == 1
    assert report["router_csv_exports"] == [str(repo_b_csv.resolve())]
    assert report["clean_report"]["input_rows"] == 2
    assert report["clean_report"]["output_rows"] == 2
    assert len(rows) == 2
    assert len({row["source_repo_hash"] for row in rows}) == 2


def test_collect_router_corpus_skips_eval_derivation_when_same_dir_has_router_csv(
    tmp_path: Path,
) -> None:
    eval_path = tmp_path / "repo-a" / ".wavemill" / "evals" / "evals.jsonl"
    csv_path = tmp_path / "repo-a" / ".wavemill" / "evals" / "hokusai-router-dataset.csv"
    output_path = tmp_path / "out" / "router.csv"
    _write_eval(eval_path, _eval_record(id="eval-from-jsonl"))
    csv_row, reason = eval_record_to_router_row(
        _eval_record(id="eval-from-csv"),
        source_repo="repo-a",
    )
    assert reason is None
    assert csv_row is not None
    csv_row["run_id_hash"] = "prebuilt-run"
    _write_router_csv(csv_path, csv_row)

    report = collect_router_corpus(
        Namespace(
            search_root=[str(tmp_path)],
            output=str(output_path),
            raw_output=None,
            clean_report=None,
            report=None,
            include_eval_jsonl=True,
            include_router_csv=True,
            derive_when_router_csv_present=False,
            include_worktrees=False,
        )
    )
    rows = list(csv.DictReader(output_path.open(newline="", encoding="utf-8")))

    assert report["eval_jsonl"]["rows_derived"] == 0
    assert report["eval_jsonl"]["files_skipped_existing_router_csv"] == [str(eval_path.resolve())]
    assert report["clean_report"]["input_files"] == [str(csv_path.resolve())]
    assert len(rows) == 1
    assert rows[0]["run_id_hash"] == "prebuilt-run"
