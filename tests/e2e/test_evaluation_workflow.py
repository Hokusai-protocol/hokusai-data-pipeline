"""End-to-end workflow tests for evaluation and DeltaOne decisioning."""

from __future__ import annotations

import pytest

from src.evaluation.deltaone_evaluator import DeltaOneEvaluator


def test_evaluation_to_deltaone_pipeline_happy_path(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    runs = {
        "candidate": make_mlflow_run(
            "candidate",
            metric_name="accuracy",
            metric_value=0.89,
            n_examples="15000",
            dataset_hash="sha256:" + "a" * 64,
            model_id="model-a",
        ),
        "baseline": make_mlflow_run(
            "baseline",
            metric_name="accuracy",
            metric_value=0.86,
            n_examples="15000",
            dataset_hash="sha256:" + "a" * 64,
            model_id="model-a",
        ),
    }
    client = make_fake_deltaone_mlflow_client(runs)
    evaluator = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
        min_examples=800,
        delta_threshold_pp=1.0,
    )

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is True
    assert decision.reason == "accepted"
    assert decision.delta_percentage_points == pytest.approx(3.0)
    assert client.tags_set["candidate"]["hokusai.deltaone.reason"] == "accepted"


def test_evaluation_to_deltaone_pipeline_failure_path(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    runs = {
        "candidate": make_mlflow_run("candidate", metric_value=0.87, n_examples="2000"),
        "baseline": make_mlflow_run("baseline", metric_value=0.86, n_examples="2000"),
    }
    client = make_fake_deltaone_mlflow_client(runs)
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0, delta_threshold_pp=1.0)

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason in {"delta_below_threshold", "not_statistically_significant"}
    assert client.tags_set["candidate"]["hokusai.deltaone.accepted"] == "false"
