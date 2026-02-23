"""Unit tests for DeltaOne acceptance decision logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.evaluation.deltaone_evaluator import DeltaOneEvaluator


def _cooldown_run(run_id: str, evaluated_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id),
        data=SimpleNamespace(tags={"hokusai.deltaone.evaluated_at": evaluated_at.isoformat()}),
    )


def test_delta_one_accepts_when_all_conditions_met(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    runs = {
        "candidate": make_mlflow_run("candidate", metric_value=0.89, n_examples="12000"),
        "baseline": make_mlflow_run("baseline", metric_value=0.86, n_examples="12000"),
    }
    client = make_fake_deltaone_mlflow_client(runs)
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0, delta_threshold_pp=1.0)

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is True
    assert decision.reason == "accepted"
    assert decision.delta_percentage_points > 1.0
    assert client.tags_set["candidate"]["hokusai.deltaone.accepted"] == "true"


def test_delta_one_rejects_when_delta_below_threshold(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    runs = {
        "candidate": make_mlflow_run("candidate", metric_value=0.865, n_examples="12000"),
        "baseline": make_mlflow_run("baseline", metric_value=0.86, n_examples="12000"),
    }
    client = make_fake_deltaone_mlflow_client(runs)
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0, delta_threshold_pp=1.0)

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason == "delta_below_threshold"


def test_delta_one_rejects_when_cooldown_active(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    now = datetime.now(timezone.utc)
    runs = {
        "candidate": make_mlflow_run("candidate", metric_value=0.90, n_examples="12000"),
        "baseline": make_mlflow_run("baseline", metric_value=0.86, n_examples="12000"),
    }
    client = make_fake_deltaone_mlflow_client(
        runs,
        search_runs_result=[_cooldown_run("older-run", now - timedelta(hours=2))],
    )
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=24)

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason.startswith("cooldown_active_until_")


def test_delta_one_rejects_when_dataset_hashes_do_not_match(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    runs = {
        "candidate": make_mlflow_run("candidate", dataset_hash="sha256:" + "a" * 64),
        "baseline": make_mlflow_run("baseline", dataset_hash="sha256:" + "b" * 64),
    }
    evaluator = DeltaOneEvaluator(
        mlflow_client=make_fake_deltaone_mlflow_client(runs),
        cooldown_hours=0,
    )

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason == "dataset_hash_mismatch"


def test_delta_one_rejects_when_sample_size_is_too_small(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    runs = {
        "candidate": make_mlflow_run("candidate", n_examples="300"),
        "baseline": make_mlflow_run("baseline", n_examples="1200"),
    }
    evaluator = DeltaOneEvaluator(
        mlflow_client=make_fake_deltaone_mlflow_client(runs),
        cooldown_hours=0,
        min_examples=800,
    )

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason == "insufficient_samples"
