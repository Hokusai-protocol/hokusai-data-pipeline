"""Tests for the 2026-11 Model 30 retrain tooling."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.model_30.merge_legacy_router_export import (
    merge_router_exports,
    relabel_success_from_score,
)
from scripts.model_30.role_replay_report import agreement_lift
from scripts.model_30.temporal_split_router_benchmark import temporal_split

COLUMNS = [
    "run_id_hash",
    "timestamp",
    "planner_model",
    "coder_model",
    "reviewer_model",
    "score",
    "completed_successfully",
]


def _frame(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS).astype(str)


def test_relabel_success_uses_score_threshold() -> None:
    frame = _frame(
        [
            ("a", "2026-03-01T00:00:00Z", "p", "c", "r", "0.7", "true"),  # placeholder
            ("b", "2026-03-02T00:00:00Z", "p", "c", "r", "0.95", "false"),  # placeholder
            ("c", "2026-03-03T00:00:00Z", "p", "c", "r", "0.85", "true"),
            ("d", "2026-03-04T00:00:00Z", "p", "c", "r", "", "true"),  # no score
        ]
    )
    out, changed = relabel_success_from_score(frame)
    assert list(out["completed_successfully"]) == ["false", "true", "true", "false"]
    assert changed == 3


def test_merge_drops_legacy_duplicates_and_applies_cutoff() -> None:
    legacy = _frame(
        [
            ("L1", "2026-05-10T10:00:00.123Z", "p", "c", "r", "0.9", "true"),
            ("L2", "2026-05-12T10:00:00.000Z", "p", "c", "r", "0.9", "true"),  # dup of D1
        ]
    )
    derived = _frame(
        [
            ("D1", "2026-05-12T10:00:00.999Z", "p", "c", "r", "0.9", "true"),
            ("D2", "2026-11-02T00:00:00Z", "p", "c", "r", "0.9", "true"),  # after cutoff
        ]
    )
    merged, report = merge_router_exports(legacy, derived, before="2026-11-01")
    assert list(merged["run_id_hash"]) == ["L1", "D1"]
    assert report["legacy_duplicates_dropped"] == 1
    assert report["merged_rows"] == 2
    assert set(merged["provenance_source"]) == {"legacy_router_csv", "derived_evals_jsonl"}


def test_merge_rejects_mismatched_columns() -> None:
    legacy = _frame([("L1", "2026-05-10T00:00:00Z", "p", "c", "r", "0.9", "true")])
    derived = legacy.drop(columns=["score"])
    with pytest.raises(ValueError, match="different columns"):
        merge_router_exports(legacy, derived)


def test_temporal_split_keeps_challenge_pairs_together(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.model_30.temporal_split_router_benchmark._quarantine_reason",
        lambda row: "bad" if row.get("run_id_hash") == "q" else None,
    )
    rows = [
        {"run_id_hash": "t", "timestamp": "2026-09-01", "challenge_pair_hash": ""},
        # pair straddles the cutoff; earliest member is before it -> both train
        {"run_id_hash": "p1", "timestamp": "2026-09-30", "challenge_pair_hash": "X"},
        {"run_id_hash": "p2", "timestamp": "2026-10-02", "challenge_pair_hash": "X"},
        {"run_id_hash": "h", "timestamp": "2026-10-05", "challenge_pair_hash": ""},
        {"run_id_hash": "q", "timestamp": "2026-10-06", "challenge_pair_hash": ""},
        {"run_id_hash": "late", "timestamp": "2026-11-03", "challenge_pair_hash": ""},
    ]
    train, holdout, quarantined, report = temporal_split(
        rows, cutoff="2026-10-01", end="2026-11-01"
    )
    assert [r["run_id_hash"] for r in train] == ["t", "p1", "p2"]
    assert [r["run_id_hash"] for r in holdout] == ["h"]
    assert [r["run_id_hash"] for r in quarantined] == ["q"]
    assert report["excluded_after_end"] == 1
    assert report["quarantine_reasons"] == {"bad": 1}


def test_agreement_lift_sign_and_ci() -> None:
    agree = [True] * 8 + [False] * 2 + [False] * 8 + [True] * 2
    good = [True] * 10 + [False] * 10
    result = agreement_lift(agree, good, boot=200)
    assert result["agree_good"] == 0.8
    assert result["agree_bad"] == 0.2
    assert result["lift"] == pytest.approx(0.6)
    low, high = result["lift_ci90"]
    assert low <= 0.6 <= high
