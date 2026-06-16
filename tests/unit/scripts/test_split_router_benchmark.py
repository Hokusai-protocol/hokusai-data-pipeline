from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.model_30.collect_wavemill_router_corpus import FIELDNAMES
from scripts.model_30.split_router_benchmark import split_router_benchmark


def _base_row(**overrides: str) -> dict[str, str]:
    row = {fieldname: "" for fieldname in FIELDNAMES}
    row.update(
        {
            "schema_version": "wavemill-hokusai-router-dataset-v1",
            "run_id_hash": "run-default",
            "task_id_hash": "task-default",
            "source_repo_hash": "repo-default",
            "task_type": "feature",
            "domain": "backend",
            "complexity": "medium",
            "max_cost_usd": "10",
            "available_planner_models": '["gpt-5.4","claude-sonnet-4-6"]',
            "available_coder_models": '["gpt-5.4","claude-sonnet-4-6"]',
            "available_reviewer_models": '["gpt-5.4","claude-sonnet-4-6"]',
            "planner_model": "claude-sonnet-4-6",
            "coder_model": "gpt-5.4",
            "reviewer_model": "claude-sonnet-4-6",
            "completed_successfully": "true",
            "actual_cost_usd": "2.5",
        }
    )
    row.update(overrides)
    return row


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _read_rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(newline="", encoding="utf-8")))


def test_split_router_benchmark_filters_quarantine_rows_before_splitting(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "router.csv"
    train_path = tmp_path / "train.csv"
    holdout_path = tmp_path / "holdout.csv"
    quarantine_path = tmp_path / "quarantine.csv"
    report_path = tmp_path / "report.json"
    rows = [
        _base_row(run_id_hash=f"valid-{index}", task_id_hash=f"task-{index}") for index in range(6)
    ]
    rows.extend(
        [
            _base_row(run_id_hash="missing-budget", max_cost_usd=""),
            _base_row(run_id_hash="outside-pool", coder_model="qwen3-coder-plus"),
        ]
    )
    _write_rows(input_path, rows)

    report = split_router_benchmark(
        input_path,
        train_path,
        holdout_path,
        quarantine_path=quarantine_path,
        report_path=report_path,
        holdout_fraction=0.5,
        seed="test-seed",
    )
    written_report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report == written_report
    assert report["row_counts"]["input_rows"] == 8
    assert report["row_counts"]["valid_rows"] == 6
    assert report["row_counts"]["quarantined_rows"] == 2
    assert report["quarantine_reasons"] == {
        "coder_model:outside_available": 1,
        "max_cost_usd:missing_or_nonpositive": 1,
    }
    assert len(_read_rows(train_path)) + len(_read_rows(holdout_path)) == 6
    assert {row["run_id_hash"] for row in _read_rows(quarantine_path)} == {
        "missing-budget",
        "outside-pool",
    }


def test_split_router_benchmark_keeps_task_groups_on_one_side(tmp_path: Path) -> None:
    input_path = tmp_path / "router.csv"
    train_path = tmp_path / "train.csv"
    holdout_path = tmp_path / "holdout.csv"
    rows: list[dict[str, str]] = []
    for group_index in range(8):
        for row_index in range(2):
            rows.append(
                _base_row(
                    source_repo_hash=f"repo-{group_index % 2}",
                    task_id_hash=f"task-{group_index}",
                    run_id_hash=f"run-{group_index}-{row_index}",
                    task_type="feature" if group_index % 2 == 0 else "bugfix",
                    domain="backend" if group_index % 3 else "frontend",
                    complexity="high" if group_index % 2 else "medium",
                )
            )
    _write_rows(input_path, rows)

    report = split_router_benchmark(
        input_path,
        train_path,
        holdout_path,
        holdout_fraction=0.5,
        seed="group-test",
    )

    train_tasks = {row["task_id_hash"] for row in _read_rows(train_path)}
    holdout_tasks = {row["task_id_hash"] for row in _read_rows(holdout_path)}
    assert train_tasks
    assert holdout_tasks
    assert train_tasks.isdisjoint(holdout_tasks)
    assert report["group_counts"]["valid_groups"] == 8
    assert report["row_counts"]["train_rows"] + report["row_counts"]["holdout_rows"] == 16
    assert report["distributions"]["task_type"]["valid"] == {"bugfix": 8, "feature": 8}


def test_split_router_benchmark_conservative_repair_recovers_provenance_rows(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "router.csv"
    train_path = tmp_path / "train.csv"
    holdout_path = tmp_path / "holdout.csv"
    quarantine_path = tmp_path / "quarantine.csv"
    rows = [
        _base_row(
            run_id_hash="missing-budget-recoverable",
            task_id_hash="missing-budget-recoverable",
            max_cost_usd="",
            actual_cost_usd="12",
            budget_violation="false",
        ),
        _base_row(
            run_id_hash="outside-pool-recoverable",
            task_id_hash="outside-pool-recoverable",
            coder_model="qwen3-coder-plus",
        ),
        _base_row(
            run_id_hash="missing-budget-too-expensive",
            task_id_hash="missing-budget-too-expensive",
            max_cost_usd="",
            actual_cost_usd="30",
            budget_violation="false",
        ),
        _base_row(
            run_id_hash="missing-budget-no-cost",
            task_id_hash="missing-budget-no-cost",
            max_cost_usd="",
            actual_cost_usd="",
            budget_violation="false",
        ),
    ]
    _write_rows(input_path, rows)

    report = split_router_benchmark(
        input_path,
        train_path,
        holdout_path,
        quarantine_path=quarantine_path,
        holdout_fraction=0.5,
        seed="repair-test",
        repair_mode="conservative",
    )
    valid_rows = [*_read_rows(train_path), *_read_rows(holdout_path)]
    valid_by_run_id = {row["run_id_hash"]: row for row in valid_rows}

    assert report["row_counts"]["input_rows"] == 4
    assert report["row_counts"]["valid_rows"] == 2
    assert report["row_counts"]["quarantined_rows"] == 2
    assert report["initial_quarantine_reasons"] == {
        "coder_model:outside_available": 1,
        "max_cost_usd:missing_or_nonpositive": 3,
    }
    assert report["quarantine_reasons"] == {"max_cost_usd:missing_or_nonpositive": 2}
    assert report["repair_reasons"] == {
        "available_coder_models:added_selected_model": 1,
        "max_cost_usd:inferred_legacy_default": 1,
    }
    assert valid_by_run_id["missing-budget-recoverable"]["max_cost_usd"] == "25"
    assert (
        valid_by_run_id["missing-budget-recoverable"]["max_cost_usd_source"]
        == "inferred_legacy_default"
    )
    assert valid_by_run_id["outside-pool-recoverable"]["available_models_repair"] == (
        "added_selected_model"
    )
    assert (
        "qwen3-coder-plus" in valid_by_run_id["outside-pool-recoverable"]["available_coder_models"]
    )

    quarantine_run_ids = {row["run_id_hash"] for row in _read_rows(quarantine_path)}
    assert quarantine_run_ids == {"missing-budget-too-expensive", "missing-budget-no-cost"}
