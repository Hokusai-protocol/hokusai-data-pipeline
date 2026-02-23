"""Unit tests for DeltaOne cooldown enforcement."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.evaluation.deltaone_evaluator import DeltaOneEvaluator


def _decision_run(run_id: str, evaluated_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id),
        data=SimpleNamespace(tags={"hokusai.deltaone.evaluated_at": evaluated_at.isoformat()}),
    )


def test_cooldown_active_blocks_when_recent_eval_exists(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    now = datetime.now(timezone.utc)
    client = make_fake_deltaone_mlflow_client(
        {"candidate": make_mlflow_run("candidate")},
        search_runs_result=[_decision_run("prev", now - timedelta(hours=2))],
    )
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=24)

    ok, blocked_until = evaluator._check_cooldown(
        model_id="model-a",
        dataset_hash="sha256:" + "a" * 64,
        experiment_id="1",
        now=now,
        current_run_id="candidate",
    )

    assert ok is False
    assert blocked_until is not None
    assert blocked_until > now


def test_cooldown_expired_allows_evaluation(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    now = datetime.now(timezone.utc)
    client = make_fake_deltaone_mlflow_client(
        {"candidate": make_mlflow_run("candidate")},
        search_runs_result=[_decision_run("prev", now - timedelta(hours=48))],
    )
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=24)

    ok, blocked_until = evaluator._check_cooldown(
        model_id="model-a",
        dataset_hash="sha256:" + "a" * 64,
        experiment_id="1",
        now=now,
        current_run_id="candidate",
    )

    assert ok is True
    assert blocked_until is not None
    assert blocked_until < now


def test_cooldown_zero_hours_short_circuits_without_query(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    client = make_fake_deltaone_mlflow_client({"candidate": make_mlflow_run("candidate")})
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0)

    ok, blocked_until = evaluator._check_cooldown(
        model_id="model-a",
        dataset_hash="sha256:" + "a" * 64,
        experiment_id="1",
        now=datetime.now(timezone.utc),
        current_run_id="candidate",
    )

    assert ok is True
    assert blocked_until is None
    assert client.search_runs_calls == []
