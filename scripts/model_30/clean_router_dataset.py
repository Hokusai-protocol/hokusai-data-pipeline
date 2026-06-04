"""Clean and validate Wavemill router exports for Model 30 registration.

Positive `actual_time_seconds` values are treated as duration evidence. Zero or
negative durations are normalized to a blank cell unless the source explicitly
marks an exact zero as measured via `actual_time_seconds_measured_zero`.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30.register_technical_task_router import (  # noqa: E402
    MODEL_ID_PATTERN,
    SELECTED_MODEL_ID_COLUMNS,
    _parse_model_values,
    validate_router_dataset_model_ids,
)

AVAILABLE_MODEL_ID_COLUMNS = (
    "available_planner_models",
    "available_coder_models",
    "available_reviewer_models",
)

ROLE_SELECTED_MODEL_COLUMNS = {
    "available_planner_models": "planner_model",
    "available_coder_models": "coder_model",
    "available_reviewer_models": "reviewer_model",
}

DURATION_COLUMN = "actual_time_seconds"
MEASURED_ZERO_COLUMN = "actual_time_seconds_measured_zero"
TRUTHY_VALUES = {"1", "true", "yes", "y"}


def clean_router_datasets(
    input_paths: list[Path],
    output_path: Path,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Merge, clean, write, and validate Wavemill router CSV exports."""
    rows, fieldnames = _read_rows(input_paths)
    cleaned_rows: list[dict[str, str]] = []
    seen_rows: set[str] = set()
    report: dict[str, Any] = {
        "input_files": [str(path) for path in input_paths],
        "input_rows": len(rows),
        "output_rows": 0,
        "duplicate_rows_skipped": 0,
        "dropped_rows": 0,
        "drop_reasons": {},
        "removed_available_model_ids": {},
        "validation": {},
    }

    drop_reasons: Counter[str] = Counter()
    removed_available_model_ids: Counter[str] = Counter()
    duration_counts: Counter[str] = Counter()
    positive_durations: list[float] = []

    for row_number, row in rows:
        row_copy = dict(row)
        drop_reason = _clean_row(row_copy, row_number, removed_available_model_ids)
        if drop_reason is not None:
            drop_reasons[drop_reason] += 1
            continue

        normalized_duration, positive_duration, duration_category = _normalize_duration(row_copy)
        if DURATION_COLUMN in row_copy:
            row_copy[DURATION_COLUMN] = normalized_duration

        fingerprint = json.dumps(row_copy, sort_keys=True, separators=(",", ":"))
        if fingerprint in seen_rows:
            report["duplicate_rows_skipped"] += 1
            continue
        seen_rows.add(fingerprint)
        cleaned_rows.append(row_copy)
        duration_counts[duration_category] += 1
        if positive_duration is not None:
            positive_durations.append(positive_duration)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(cleaned_rows)

    summary = validate_router_dataset_model_ids(output_path)
    report["output_rows"] = len(cleaned_rows)
    report["dropped_rows"] = sum(drop_reasons.values())
    report["drop_reasons"] = dict(sorted(drop_reasons.items()))
    report["removed_available_model_ids"] = dict(sorted(removed_available_model_ids.items()))
    report["duration_coverage"] = _build_duration_coverage_report(
        len(cleaned_rows),
        duration_counts,
        positive_durations,
    )
    report["validation"] = summary.to_mlflow_dict()

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
        report_path.write_text(report_text, encoding="utf-8")

    return report


def _read_rows(input_paths: list[Path]) -> tuple[list[tuple[int, dict[str, str]]], list[str]]:
    rows: list[tuple[int, dict[str, str]]] = []
    fieldnames: list[str] | None = None
    for input_path in input_paths:
        with input_path.open(newline="", encoding="utf-8") as input_file:
            reader = csv.DictReader(input_file)
            if reader.fieldnames is None:
                raise ValueError(f"Router dataset has no CSV header: {input_path}")
            if fieldnames is None:
                fieldnames = list(reader.fieldnames)
            elif list(reader.fieldnames) != fieldnames:
                raise ValueError(
                    f"Router dataset header mismatch in {input_path}; "
                    "regenerate exports with the same Wavemill exporter version."
                )

            rows.extend((row_number, row) for row_number, row in enumerate(reader, start=2))

    if fieldnames is None:
        raise ValueError("At least one router dataset input is required")
    return rows, fieldnames


def _clean_row(
    row: dict[str, str],
    row_number: int,
    removed_available_model_ids: Counter[str],
) -> str | None:
    selected_models: dict[str, str] = {}
    for column in SELECTED_MODEL_ID_COLUMNS:
        try:
            values = _parse_model_values(row.get(column, ""))
        except (json.JSONDecodeError, ValueError):
            return f"{column}:malformed"
        if len(values) != 1:
            return f"{column}:empty_or_list"
        model_id = values[0]
        if not MODEL_ID_PATTERN.match(model_id):
            return f"{column}:invalid:{model_id}"
        selected_models[column] = model_id

    for column in AVAILABLE_MODEL_ID_COLUMNS:
        try:
            values = _parse_model_values(row.get(column, ""))
        except (json.JSONDecodeError, ValueError):
            return f"{column}:malformed"

        valid_values = []
        for model_id in values:
            if MODEL_ID_PATTERN.match(model_id):
                valid_values.append(model_id)
            else:
                removed_available_model_ids[model_id] += 1

        if not valid_values:
            selected_column = ROLE_SELECTED_MODEL_COLUMNS[column]
            valid_values = [selected_models[selected_column]]

        row[column] = json.dumps(sorted(set(valid_values)), separators=(",", ":"))

    del row_number
    return None


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in TRUTHY_VALUES


def _parse_duration(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        parsed = float(stripped)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _normalize_duration(row: dict[str, str]) -> tuple[str, float | None, str]:
    raw_value = row.get(DURATION_COLUMN)
    stripped_value = raw_value.strip() if raw_value is not None else ""
    parsed_value = _parse_duration(raw_value)
    if parsed_value is None:
        return "", None, "originally_missing"
    if parsed_value > 0:
        return stripped_value, parsed_value, "positive"
    if parsed_value == 0 and _is_truthy(row.get(MEASURED_ZERO_COLUMN)):
        return stripped_value or "0", None, "measured_zero"
    return "", None, "nonpositive_normalized"


def _build_duration_coverage_report(
    output_rows: int,
    duration_counts: Counter[str],
    positive_durations: list[float],
) -> dict[str, Any]:
    originally_missing = duration_counts["originally_missing"]
    nonpositive_normalized = duration_counts["nonpositive_normalized"]
    positive_count = duration_counts["positive"]
    measured_zero_count = duration_counts["measured_zero"]
    positive_coverage_fraction = positive_count / output_rows if output_rows else 0.0
    return {
        "total_rows": output_rows,
        "missing": originally_missing + nonpositive_normalized,
        "originally_missing": originally_missing,
        "nonpositive_normalized": nonpositive_normalized,
        "measured_zero_count": measured_zero_count,
        "positive_count": positive_count,
        "positive_coverage_fraction": positive_coverage_fraction,
        "positive_median_seconds": median(positive_durations) if positive_durations else None,
        "positive_mean_seconds": mean(positive_durations) if positive_durations else None,
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Input Wavemill router CSV export. Repeat to merge additional exports.",
    )
    parser.add_argument("--output", required=True, help="Cleaned CSV output path.")
    parser.add_argument("--report", help="Optional JSON cleanup report path.")
    return parser.parse_args()


def main() -> None:
    """Run the router dataset cleaner."""
    args = parse_args()
    report = clean_router_datasets(
        [Path(path).expanduser().resolve() for path in args.input],
        Path(args.output).expanduser().resolve(),
        Path(args.report).expanduser().resolve() if args.report else None,
    )
    print(json.dumps(report, indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()
