"""Unit tests for dataset hash extraction and validation in DeltaOne."""

from __future__ import annotations

import pytest

from src.evaluation.deltaone_evaluator import DeltaOneEvaluator


def test_extract_metrics_accepts_matching_sha256_hash(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    run = make_mlflow_run("candidate", dataset_hash="sha256:" + "b" * 64)
    client = make_fake_deltaone_mlflow_client({"candidate": run})
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0)

    hem = evaluator._extract_metrics_from_run("candidate")

    assert hem.dataset_hash == "sha256:" + "b" * 64


def test_extract_metrics_prefers_tag_hash_over_param_hash(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    run = make_mlflow_run(
        "candidate",
        dataset_hash="sha256:" + "c" * 64,
        params={"dataset_hash": "sha256:" + "d" * 64},
    )
    client = make_fake_deltaone_mlflow_client({"candidate": run})
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0)

    hem = evaluator._extract_metrics_from_run("candidate")

    assert hem.dataset_hash == "sha256:" + "c" * 64


def test_extract_metrics_rejects_missing_hash(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    run = make_mlflow_run("candidate")
    run.data.tags.pop("hokusai.dataset.hash")
    client = make_fake_deltaone_mlflow_client({"candidate": run})
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0)

    with pytest.raises(ValueError, match="Missing dataset hash"):
        evaluator._extract_metrics_from_run("candidate")


def test_extract_metrics_rejects_non_canonical_hash_format(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    run = make_mlflow_run("candidate", dataset_hash="sha256:ABC123")
    client = make_fake_deltaone_mlflow_client({"candidate": run})
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0)

    with pytest.raises(ValueError, match="exact 'sha256:<64 lowercase hex>'"):
        evaluator._extract_metrics_from_run("candidate")
