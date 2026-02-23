from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

# Auth-hook note: fake MLflow clients here intentionally avoid live
# Authorization headers and MLFLOW_TRACKING_TOKEN handling.
from src.evaluation.deltaone_evaluator import (
    DeltaOneEvaluator,
    _calculate_percentage_point_difference,
)


def _make_run(
    run_id: str,
    *,
    metric_name: str = "accuracy",
    metric_value: float = 0.87,
    n_examples: str = "1000",
    dataset_hash: str = "sha256:" + "a" * 64,
    model_id: str = "model-a",
    start_time: int = 1_700_000_000_000,
    experiment_id: str = "1",
    contributor_tags: dict[str, str] | None = None,
) -> SimpleNamespace:
    tags = {
        "hokusai.primary_metric": metric_name,
        "hokusai.dataset.num_samples": n_examples,
        "hokusai.dataset.hash": dataset_hash,
        "hokusai.model_id": model_id,
    }
    if contributor_tags:
        tags.update(contributor_tags)

    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id, start_time=start_time, experiment_id=experiment_id),
        data=SimpleNamespace(
            metrics={metric_name: metric_value},
            tags=tags,
            params={},
        ),
    )


class _FakeMlflowClient:
    def __init__(
        self,
        runs: dict[str, SimpleNamespace],
        search_runs_result: list[SimpleNamespace] | None = None,
    ):
        self._runs = runs
        self._search_runs_result = search_runs_result or []
        self.tags_set: dict[str, dict[str, str]] = {}
        self.get_run_calls: list[str] = []

    def get_run(self, run_id: str) -> SimpleNamespace:
        self.get_run_calls.append(run_id)
        return self._runs[run_id]

    def search_runs(
        self,
        experiment_ids: list[str],
        filter_string: str,
        max_results: int,
        order_by: list[str],
    ) -> list[SimpleNamespace]:
        return self._search_runs_result

    def set_tag(self, run_id: str, key: str, value: str) -> None:
        self.tags_set.setdefault(run_id, {})[key] = value


def test_extract_metrics_from_run_uses_single_mlflow_call() -> None:
    client = _FakeMlflowClient({"run-1": _make_run("run-1")})
    evaluator = DeltaOneEvaluator(mlflow_client=client)

    hem = evaluator._extract_metrics_from_run("run-1")

    assert hem.metric_name == "accuracy"
    assert hem.metric_value == pytest.approx(0.87)
    assert hem.sample_size == 1000
    assert hem.experiment_id == "1"
    assert client.get_run_calls == ["run-1"]


def test_percentage_point_calculation_uses_ratio_to_pp_conversion() -> None:
    assert _calculate_percentage_point_difference(0.85, 0.87) == pytest.approx(2.0)
    assert _calculate_percentage_point_difference(0.50, 0.51) == pytest.approx(1.0)


def test_confidence_interval_significance_known_case() -> None:
    evaluator = DeltaOneEvaluator(mlflow_client=_FakeMlflowClient({}))

    significant, ci_low, ci_high = evaluator._is_statistically_significant(
        baseline_metric=0.85,
        current_metric=0.87,
        baseline_n=10_000,
        current_n=10_000,
    )

    assert significant is True
    assert ci_low > 0.0
    assert ci_high > ci_low


def test_evaluate_rejects_when_cooldown_active() -> None:
    now = datetime.now(timezone.utc)
    previous_eval_run = SimpleNamespace(
        info=SimpleNamespace(run_id="older-run"),
        data=SimpleNamespace(
            tags={"hokusai.deltaone.evaluated_at": (now - timedelta(hours=1)).isoformat()}
        ),
    )

    runs = {
        "candidate": _make_run("candidate", metric_value=0.90, n_examples="2000"),
        "baseline": _make_run("baseline", metric_value=0.86, n_examples="2000"),
    }
    client = _FakeMlflowClient(runs, search_runs_result=[previous_eval_run])
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=24, min_examples=800)

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason.startswith("cooldown_active")


def test_evaluate_rejects_when_sample_size_too_small() -> None:
    runs = {
        "candidate": _make_run("candidate", metric_value=0.90, n_examples="400"),
        "baseline": _make_run("baseline", metric_value=0.86, n_examples="1200"),
    }
    client = _FakeMlflowClient(runs)
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0, min_examples=800)

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason == "insufficient_samples"


def test_evaluate_rejects_when_dataset_hash_mismatch() -> None:
    runs = {
        "candidate": _make_run(
            "candidate",
            metric_value=0.90,
            n_examples="2000",
            dataset_hash="sha256:" + "a" * 64,
        ),
        "baseline": _make_run(
            "baseline",
            metric_value=0.86,
            n_examples="2000",
            dataset_hash="sha256:" + "b" * 64,
        ),
    }
    client = _FakeMlflowClient(runs)
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0, min_examples=800)

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason == "dataset_hash_mismatch"


def test_evaluate_end_to_end_significant_improvement() -> None:
    runs = {
        "candidate": _make_run(
            "candidate",
            metric_value=0.87,
            n_examples="10000",
            contributor_tags={
                "contributor_id": "prompt-author-123",
                "hokusai.contributor.prompt_author_id": "prompt-author-123",
                "hokusai.contributor.training_data_uploader_id": "uploader-456",
                "hokusai.contributor.human_labeler_id": "labeler-789",
            },
        ),
        "baseline": _make_run("baseline", metric_value=0.85, n_examples="10000"),
    }
    client = _FakeMlflowClient(runs)
    evaluator = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
        min_examples=800,
        delta_threshold_pp=1.0,
    )

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is True
    assert decision.reason == "accepted"
    assert decision.delta_percentage_points == pytest.approx(2.0)
    assert "hokusai.deltaone.accepted" in client.tags_set["candidate"]
    assert client.tags_set["candidate"]["hokusai.deltaone.contributor_id"] == "prompt-author-123"
    assert (
        client.tags_set["candidate"]["hokusai.deltaone.hokusai.contributor.prompt_author_id"]
        == "prompt-author-123"
    )
    assert (
        client.tags_set["candidate"][
            "hokusai.deltaone.hokusai.contributor.training_data_uploader_id"
        ]
        == "uploader-456"
    )
    assert (
        client.tags_set["candidate"]["hokusai.deltaone.hokusai.contributor.human_labeler_id"]
        == "labeler-789"
    )


def test_evaluate_end_to_end_not_significant() -> None:
    runs = {
        "candidate": _make_run("candidate", metric_value=0.87, n_examples="1000"),
        "baseline": _make_run("baseline", metric_value=0.85, n_examples="1000"),
    }
    client = _FakeMlflowClient(runs)
    evaluator = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
        min_examples=800,
        delta_threshold_pp=1.0,
    )

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason == "not_statistically_significant"
