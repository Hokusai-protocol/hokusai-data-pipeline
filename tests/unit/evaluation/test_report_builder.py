from __future__ import annotations

import json

import pandas as pd

from src.evaluation.attribution.report_builder import build_report, enrich_neighbor_provenance


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _enc(neighbors: list[dict]) -> str:
    return json.dumps(neighbors, sort_keys=True, separators=(",", ":"))


BLOCKS = [
    {
        "row_start": 0,
        "row_end": 2,
        "account_id": "user-1",
        "wallet": "0x" + "1" * 40,
        "submission_id": "sub-a",
    },
    {
        "row_start": 3,
        "row_end": 9,
        "account_id": "user-2",
        "wallet": None,
        "submission_id": "sub-b",
    },
]


def test_enrich_maps_row_index_to_block_identity() -> None:
    candidate = _frame(
        [
            {
                "row_id": "a",
                "completed_successfully": True,
                "neighbor_provenance": _enc(
                    [
                        {"training_row_index": 0, "weight": 3.0},
                        {"training_row_index": 5, "weight": 1.0},
                    ]
                ),
            }
        ]
    )

    enriched = enrich_neighbor_provenance(candidate, BLOCKS)
    neighbors = json.loads(enriched.iloc[0]["neighbor_provenance"])
    by_idx = {n["training_row_index"]: n for n in neighbors}

    assert by_idx[0]["account_id"] == "user-1"
    assert by_idx[0]["wallet"] == "0x" + "1" * 40
    assert by_idx[0]["submission_id"] == "sub-a"
    assert by_idx[5]["account_id"] == "user-2"
    assert by_idx[5]["submission_id"] == "sub-b"
    assert "wallet" not in by_idx[5]  # block wallet is None -> not attached


def test_build_report_is_account_centric() -> None:
    baseline = _frame(
        [{"row_id": "a", "completed_successfully": False, "neighbor_provenance": "[]"}]
    )
    candidate = _frame(
        [
            {
                "row_id": "a",
                "completed_successfully": True,
                "neighbor_provenance": _enc(
                    [
                        {"training_row_index": 0, "weight": 3.0},
                        {"training_row_index": 5, "weight": 1.0},
                    ]
                ),
            }
        ]
    )

    report = build_report(
        baseline,
        candidate,
        manifest_blocks=BLOCKS,
        model_id="30",
        baseline_run_id="b",
        candidate_run_id="c",
        created_at="2026-06-05T00:00:00Z",
    )

    contributors = report["contributors"]
    assert [c["account_id"] for c in contributors] == ["user-1", "user-2"]
    assert [c["weight_bps"] for c in contributors] == [7500, 2500]
    assert all("wallet" not in c or c.get("account_id") for c in contributors)


def test_neighbor_outside_any_block_is_dropped() -> None:
    baseline = _frame(
        [{"row_id": "a", "completed_successfully": False, "neighbor_provenance": "[]"}]
    )
    candidate = _frame(
        [
            {
                "row_id": "a",
                "completed_successfully": True,
                "neighbor_provenance": _enc(
                    [
                        {"training_row_index": 0, "weight": 1.0},  # -> user-1
                        {"training_row_index": 999, "weight": 1.0},  # no block -> no identity
                    ]
                ),
            }
        ]
    )

    report = build_report(
        baseline,
        candidate,
        manifest_blocks=BLOCKS,
        model_id="30",
        baseline_run_id="b",
        candidate_run_id="c",
        created_at="2026-06-05T00:00:00Z",
    )

    assert [c["account_id"] for c in report["contributors"]] == ["user-1"]
    assert report["contributors"][0]["weight_bps"] == 10000
