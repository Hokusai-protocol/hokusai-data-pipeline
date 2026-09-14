from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

from scripts.model_30.attribute_retraining import (
    DEFAULT_V1_PRIMARY_METRIC,
    DEFAULT_V2_PRIMARY_METRIC,
    _build_cohorts,
    _default_primary_metric,
    _identity_by_row_index,
)


def _block(
    *,
    submission_id: str,
    row_start: int,
    row_end: int,
    account_id: str | None = None,
    wallet: str | None = None,
) -> dict[str, object]:
    return {
        "submission_id": submission_id,
        "row_start": row_start,
        "row_end": row_end,
        "row_count": row_end - row_start + 1,
        "account_id": account_id,
        "wallet": wallet,
    }


def test_build_cohorts_groups_by_account_id_preferring_account_over_wallet() -> None:
    manifest = {
        "blocks": [
            _block(submission_id="s1", row_start=0, row_end=1, account_id="user-a", wallet="0xaa"),
            _block(submission_id="s2", row_start=2, row_end=2, account_id="user-a"),
            _block(submission_id="s3", row_start=3, row_end=3, wallet="0xbb"),
        ]
    }

    cohorts = {cohort.cohort_id: cohort for cohort in _build_cohorts(manifest)}

    # account_id keys its cohort and carries the wallet through; the wallet-only block is its own.
    assert set(cohorts) == {"user-a", "0xbb"}
    assert cohorts["user-a"].account_id == "user-a"
    assert cohorts["user-a"].wallet == "0xaa"
    assert cohorts["user-a"].row_count == 3
    assert cohorts["user-a"].submission_ids == ("s1", "s2")
    assert cohorts["0xbb"].account_id is None
    assert cohorts["0xbb"].wallet == "0xbb"


def test_build_cohorts_skips_blocks_with_no_identity() -> None:
    manifest = {
        "blocks": [
            _block(submission_id="s1", row_start=0, row_end=0),  # no account_id, no wallet
            _block(submission_id="s2", row_start=1, row_end=1, account_id="user-a"),
        ]
    }

    cohorts = _build_cohorts(manifest)

    assert [cohort.cohort_id for cohort in cohorts] == ["user-a"]


def test_default_primary_metric_uses_v2_composite() -> None:
    # Reward attribution must key off the v2 composite by default; v1 stays selectable
    # only as a rollback diagnostic.
    assert _default_primary_metric("v2") == DEFAULT_V2_PRIMARY_METRIC
    assert DEFAULT_V2_PRIMARY_METRIC == "technical_task_router.benchmark_score_v2"
    assert _default_primary_metric("v1") == DEFAULT_V1_PRIMARY_METRIC


def test_trainer_evaluate_attributes_on_resolved_primary_metric() -> None:
    from scripts.model_30.attribute_retraining import _Model30SubsetTrainer

    metrics = {
        "technical_task_router.benchmark_score_v1": 0.40,
        "technical_task_router.benchmark_score_v2": 0.72,
    }

    trainer = _Model30SubsetTrainer.__new__(_Model30SubsetTrainer)
    trainer._model_id = "30"
    trainer._holdout_path = Path("holdout.csv")
    trainer._benchmark_version = "v2"
    trainer._primary_metric = DEFAULT_V2_PRIMARY_METRIC

    captured: dict[str, Any] = {}

    def _fake_evaluate_model(_handle: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"metrics": metrics}

    with (
        mock.patch(
            "scripts.model_30.evaluate_technical_task_router.evaluate_model",
            _fake_evaluate_model,
        ),
        mock.patch(
            "scripts.model_30.evaluate_technical_task_router.parse_objectives",
            lambda _value: ["all"],
        ),
    ):
        score = trainer.evaluate(handle=object(), eval_seed=0)

    # The attributed score is the v2 composite, and the v2 benchmark version is propagated.
    assert score == 0.72
    assert captured["benchmark_version"] == "v2"


def test_identity_by_row_index_maps_rows_to_account_identity() -> None:
    blocks = [
        _block(submission_id="s1", row_start=0, row_end=1, account_id="user-a", wallet="0xaa"),
        _block(submission_id="s2", row_start=2, row_end=2, wallet="0xbb"),
        _block(submission_id="s3", row_start=3, row_end=3),  # no identity
    ]

    identities = _identity_by_row_index(blocks=blocks, row_count=4)

    assert identities == ["user-a", "user-a", "0xbb", None]
