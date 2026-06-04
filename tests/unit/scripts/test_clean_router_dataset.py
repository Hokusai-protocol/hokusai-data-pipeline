from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.model_30.clean_router_dataset import clean_router_datasets
from scripts.model_30.register_technical_task_router import validate_router_dataset_model_ids

FIELDNAMES = [
    "available_planner_models",
    "available_coder_models",
    "available_reviewer_models",
    "planner_model",
    "coder_model",
    "reviewer_model",
    "task_type",
    "completed_successfully",
    "score",
    "actual_cost_usd",
    "actual_time_seconds",
    "actual_time_seconds_measured_zero",
]


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _base_row(task_type: str, duration: str, *, measured_zero: str = "") -> dict[str, str]:
    return {
        "available_planner_models": '["gpt-5.4"]',
        "available_coder_models": '["gpt-5.4"]',
        "available_reviewer_models": '["gpt-5.4"]',
        "planner_model": "gpt-5.4",
        "coder_model": "gpt-5.4",
        "reviewer_model": "gpt-5.4",
        "task_type": task_type,
        "completed_successfully": "true",
        "score": "0.9",
        "actual_cost_usd": "0.12",
        "actual_time_seconds": duration,
        "actual_time_seconds_measured_zero": measured_zero,
    }


def test_clean_router_dataset_normalizes_nonpositive_durations_and_reports_coverage(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "dirty-router-dataset.csv"
    output_path = tmp_path / "clean-router-dataset.csv"
    report_path = tmp_path / "clean-router-dataset.report.json"
    _write_rows(
        input_path,
        [
            _base_row("positive-a", "42.5"),
            _base_row("positive-b", "100"),
            _base_row("synthetic-zero", "0"),
            _base_row("negative-duration", "-5"),
            _base_row("missing-duration", ""),
            _base_row("measured-zero", "0", measured_zero="true"),
        ],
    )

    report = clean_router_datasets([input_path], output_path, report_path)
    written_report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(output_path.open(newline="", encoding="utf-8")))
    summary = validate_router_dataset_model_ids(output_path)

    assert summary.row_count == 6
    assert report == written_report
    assert report["output_rows"] == 6
    assert report["duplicate_rows_skipped"] == 0
    assert report["dropped_rows"] == 0
    assert report["duration_coverage"] == {
        "total_rows": 6,
        "missing": 3,
        "originally_missing": 1,
        "nonpositive_normalized": 2,
        "measured_zero_count": 1,
        "positive_count": 2,
        "positive_coverage_fraction": 2 / 6,
        "positive_median_seconds": 71.25,
        "positive_mean_seconds": 71.25,
    }

    by_task_type = {row["task_type"]: row for row in rows}
    assert by_task_type["positive-a"]["actual_time_seconds"] == "42.5"
    assert by_task_type["positive-b"]["actual_time_seconds"] == "100"
    assert by_task_type["synthetic-zero"]["actual_time_seconds"] == ""
    assert by_task_type["negative-duration"]["actual_time_seconds"] == ""
    assert by_task_type["missing-duration"]["actual_time_seconds"] == ""
    assert by_task_type["measured-zero"]["actual_time_seconds"] == "0"


def test_clean_router_dataset_deduplicates_after_duration_normalization(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "duplicate-router-dataset.csv"
    output_path = tmp_path / "duplicate-router-dataset.clean.csv"
    rows = [
        _base_row("duplicate-normalized", "0"),
        _base_row("duplicate-normalized", ""),
    ]
    _write_rows(input_path, rows)

    report = clean_router_datasets([input_path], output_path)
    written_rows = list(csv.DictReader(output_path.open(newline="", encoding="utf-8")))

    assert report["output_rows"] == 1
    assert report["duplicate_rows_skipped"] == 1
    assert report["duration_coverage"] == {
        "total_rows": 1,
        "missing": 1,
        "originally_missing": 0,
        "nonpositive_normalized": 1,
        "measured_zero_count": 0,
        "positive_count": 0,
        "positive_coverage_fraction": 0.0,
        "positive_median_seconds": None,
        "positive_mean_seconds": None,
    }
    assert written_rows[0]["actual_time_seconds"] == ""


def test_clean_router_dataset_preserves_invalid_model_drop_behavior(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "invalid-router-dataset.csv"
    output_path = tmp_path / "invalid-router-dataset.clean.csv"
    report_path = tmp_path / "invalid-router-dataset.report.json"
    _write_rows(
        input_path,
        [
            {
                **_base_row("valid-row", "60"),
                "available_planner_models": '["gpt-5.4","<synthetic>"]',
            },
            {
                **_base_row("invalid-selected-model", "0"),
                "reviewer_model": "deep",
            },
        ],
    )

    report = clean_router_datasets([input_path, input_path], output_path, report_path)
    written_rows = list(csv.DictReader(output_path.open(newline="", encoding="utf-8")))

    assert report["input_rows"] == 4
    assert report["output_rows"] == 1
    assert report["duplicate_rows_skipped"] == 1
    assert report["dropped_rows"] == 2
    assert report["removed_available_model_ids"] == {"<synthetic>": 2}
    assert report["drop_reasons"] == {"reviewer_model:invalid:deep": 2}
    assert report["duration_coverage"] == {
        "total_rows": 1,
        "missing": 0,
        "originally_missing": 0,
        "nonpositive_normalized": 0,
        "measured_zero_count": 0,
        "positive_count": 1,
        "positive_coverage_fraction": 1.0,
        "positive_median_seconds": 60.0,
        "positive_mean_seconds": 60.0,
    }
    assert len(written_rows) == 1
    assert written_rows[0]["available_planner_models"] == '["gpt-5.4"]'
