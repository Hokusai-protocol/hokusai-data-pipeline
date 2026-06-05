from __future__ import annotations

import json
import logging
from pathlib import Path

import jsonschema
import pandas as pd

from src.evaluation.attribution.neighbor_provenance import attribute


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _encoded(neighbors: list[dict[str, object]]) -> str:
    return json.dumps(neighbors, sort_keys=True, separators=(",", ":"))


def _schema() -> dict[str, object]:
    return json.loads(Path("schema/attribution_report.v1.json").read_text(encoding="utf-8"))


def test_attribute_selects_only_failure_to_success_rows(caplog) -> None:
    caplog.set_level(logging.INFO, logger="src.evaluation.attribution.neighbor_provenance")
    baseline = _frame(
        [
            {"row_id": "a", "completed_successfully": False, "neighbor_provenance": "[]"},
            {"row_id": "b", "completed_successfully": True, "neighbor_provenance": "[]"},
        ]
    )
    candidate = _frame(
        [
            {
                "row_id": "a",
                "completed_successfully": True,
                "neighbor_provenance": _encoded(
                    [{"wallet": "0x" + "1" * 40, "submission_id": "sub-a", "weight": 1.0}]
                ),
            },
            {
                "row_id": "b",
                "completed_successfully": True,
                "neighbor_provenance": _encoded(
                    [{"wallet": "0x" + "2" * 40, "submission_id": "sub-b", "weight": 1.0}]
                ),
            },
            {
                "row_id": "candidate-only",
                "completed_successfully": True,
                "neighbor_provenance": _encoded(
                    [{"wallet": "0x" + "3" * 40, "submission_id": "sub-c", "weight": 1.0}]
                ),
            },
        ]
    )

    report = attribute(
        baseline,
        candidate,
        model_id="30",
        baseline_run_id="base",
        candidate_run_id="cand",
        created_at="2026-06-05T00:00:00Z",
    )

    assert report["rows_improved"] == 1
    assert [item["wallet"] for item in report["contributors"]] == ["0x" + "1" * 40]
    assert "candidate-only row(s)" in caplog.text


def test_attribute_weight_bps_normalization_is_deterministic() -> None:
    baseline = _frame(
        [
            {"row_id": "a", "completed_successfully": False, "neighbor_provenance": "[]"},
            {"row_id": "b", "completed_successfully": False, "neighbor_provenance": "[]"},
            {"row_id": "c", "completed_successfully": False, "neighbor_provenance": "[]"},
        ]
    )
    candidate = _frame(
        [
            {
                "row_id": row_id,
                "completed_successfully": True,
                "neighbor_provenance": _encoded(
                    [{"wallet": wallet, "submission_id": submission_id, "weight": 1.0}]
                ),
            }
            for row_id, wallet, submission_id in (
                ("a", "0x" + "1" * 40, "sub-a"),
                ("b", "0x" + "2" * 40, "sub-b"),
                ("c", "0x" + "3" * 40, "sub-c"),
            )
        ]
    )

    report = attribute(
        baseline,
        candidate,
        model_id="30",
        baseline_run_id="base",
        candidate_run_id="cand",
        created_at="2026-06-05T00:00:00Z",
    )

    assert [item["weight_bps"] for item in report["contributors"]] == [3334, 3333, 3333]
    assert report["weight_bps_total"] == 10000


def test_attribute_handles_single_contributor_and_zero_improved_rows() -> None:
    improved = attribute(
        _frame([{"row_id": "a", "completed_successfully": False, "neighbor_provenance": "[]"}]),
        _frame(
            [
                {
                    "row_id": "a",
                    "completed_successfully": True,
                    "neighbor_provenance": _encoded(
                        [{"wallet": "0x" + "1" * 40, "submission_id": "sub-a", "weight": 1.0}]
                    ),
                }
            ]
        ),
        model_id="30",
        baseline_run_id="base",
        candidate_run_id="cand",
        created_at="2026-06-05T00:00:00Z",
    )
    empty = attribute(
        _frame([{"row_id": "a", "completed_successfully": True, "neighbor_provenance": "[]"}]),
        _frame([{"row_id": "a", "completed_successfully": True, "neighbor_provenance": "[]"}]),
        model_id="30",
        baseline_run_id="base",
        candidate_run_id="cand",
        created_at="2026-06-05T00:00:00Z",
    )

    assert [item["weight_bps"] for item in improved["contributors"]] == [10000]
    assert empty["contributors"] == []
    assert empty["weight_bps_total"] == 0


def test_attribute_is_deterministic_and_schema_valid() -> None:
    baseline = _frame(
        [{"row_id": "a", "completed_successfully": False, "neighbor_provenance": "[]"}]
    )
    candidate = _frame(
        [
            {
                "row_id": "a",
                "completed_successfully": True,
                "neighbor_provenance": _encoded(
                    [
                        {"wallet": "0x" + "1" * 40, "submission_id": "sub-a", "weight": 3.0},
                        {"wallet": "0x" + "2" * 40, "submission_id": "sub-b", "weight": 1.0},
                    ]
                ),
            }
        ]
    )

    first = attribute(
        baseline,
        candidate,
        model_id="30",
        baseline_run_id="base",
        candidate_run_id="cand",
        created_at="2026-06-05T00:00:00Z",
    )
    second = attribute(
        baseline,
        candidate,
        model_id="30",
        baseline_run_id="base",
        candidate_run_id="cand",
        created_at="2026-06-05T00:00:00Z",
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    jsonschema.validate(instance=first, schema=_schema())


def test_attribute_splits_weight_within_row_and_merges_same_wallet_slots() -> None:
    baseline = _frame(
        [{"row_id": "a", "completed_successfully": False, "neighbor_provenance": "[]"}]
    )
    candidate = _frame(
        [
            {
                "row_id": "a",
                "completed_successfully": True,
                "neighbor_provenance": _encoded(
                    [
                        {"wallet": "0x" + "1" * 40, "submission_id": "sub-a", "weight": 2.0},
                        {"wallet": "0x" + "1" * 40, "submission_id": "sub-b", "weight": 1.0},
                        {"wallet": "0x" + "2" * 40, "submission_id": "sub-c", "weight": 1.0},
                    ]
                ),
            }
        ]
    )

    report = attribute(
        baseline,
        candidate,
        model_id="30",
        baseline_run_id="base",
        candidate_run_id="cand",
        created_at="2026-06-05T00:00:00Z",
    )

    assert report["contributors"][0]["wallet"] == "0x" + "1" * 40
    assert report["contributors"][0]["raw_score"] == 0.75
    assert report["contributors"][0]["submission_ids"] == ["sub-a", "sub-b"]
    assert report["contributors"][1]["raw_score"] == 0.25
